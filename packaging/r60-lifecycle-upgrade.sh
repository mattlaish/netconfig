#!/usr/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${NETCONFIG_R60_PYTHON:-/usr/bin/python3.12}
TARGET_RPM=""
ROLLBACK_RPM=""
SNAPSHOT_ROOT=/var/lib/netconfig/lifecycle-snapshots
ALLOW_DESTRUCTIVE=0
PG_ROLLBACK_DB=""
PG_READY_MARKER=""
CONFIG_PATH=/etc/default/netconfig

usage() {
  cat <<'USAGE'
usage: sudo ./packaging/r60-lifecycle-upgrade.sh \
  --target-rpm ./netconfig-2.0.0-60.el10.noarch.rpm \
  --rollback-rpm ./netconfig-2.0.0-59.el10.noarch.rpm \
  --allow-destructive \
  [--snapshot-root /var/lib/netconfig/lifecycle-snapshots] \
  [--postgres-rollback-db netconfig_r60_rollback \
   --postgres-ready-marker /root/netconfig-r60-postgres-ready.json]

R60 transactional appliance upgrade wrapper. Supported source release: 59.
The wrapper snapshots local state before the DNF transaction, runtime-masks NetConfig
services during package replacement, verifies preservation, and on any upgrade/smoke
failure performs an explicit RPM downgrade plus local-state restore.

For PostgreSQL deployments, rollback cannot safely rely on an in-place migrated DB.
Before running this wrapper, restore the checksummed pre-upgrade pg_dump into a
separate rollback database and validate it. Supply a root-only readiness marker with:
  {"ready":true,"validated":true,"rollback_database":"NAME","backup_sha256":"<64 hex>"}
On rollback, local state is restored first and then settings are deliberately repointed
to that pre-restored rollback database. The wrapper never hot-restores over the active DB.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target-rpm) TARGET_RPM=${2:-}; shift 2 ;;
    --rollback-rpm) ROLLBACK_RPM=${2:-}; shift 2 ;;
    --snapshot-root) SNAPSHOT_ROOT=${2:-}; shift 2 ;;
    --allow-destructive) ALLOW_DESTRUCTIVE=1; shift ;;
    --postgres-rollback-db) PG_ROLLBACK_DB=${2:-}; shift 2 ;;
    --postgres-ready-marker) PG_READY_MARKER=${2:-}; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "R60 lifecycle upgrade must run as root" >&2; exit 2; }
[[ $ALLOW_DESTRUCTIVE -eq 1 ]] || { echo "refusing destructive lifecycle operation without --allow-destructive" >&2; exit 21; }
[[ -n $TARGET_RPM && -f $TARGET_RPM && ! -L $TARGET_RPM ]] || { echo "target RPM missing/unsafe" >&2; exit 2; }
[[ -n $ROLLBACK_RPM && -f $ROLLBACK_RPM && ! -L $ROLLBACK_RPM ]] || { echo "rollback RPM missing/unsafe" >&2; exit 2; }
[[ -x $PYTHON ]] || { echo "required Python not found: $PYTHON" >&2; exit 20; }
# shellcheck disable=SC1091
source /etc/os-release
[[ ${ID:-} == almalinux && ${VERSION_ID%%.*} == 10 ]] || { echo "R60 production lifecycle target is AlmaLinux 10" >&2; exit 20; }
for tool in rpm dnf systemctl systemd-analyze stat sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 20; }
done

identity() { rpm -qp --queryformat '%{NAME} %{VERSION} %{RELEASE} %{ARCH}\n' "$1"; }
read -r t_name t_ver t_rel t_arch < <(identity "$TARGET_RPM")
read -r r_name r_ver r_rel r_arch < <(identity "$ROLLBACK_RPM")
[[ $t_name == netconfig && $t_ver == 2.0.0 && ${t_rel%%.*} == 60 && $t_arch == noarch ]] || {
  echo "target must be NetConfig 2.0.0 release 60: $(identity "$TARGET_RPM")" >&2; exit 1; }
[[ $r_name == netconfig && $r_ver == 2.0.0 && ${r_rel%%.*} == 59 && $r_arch == noarch ]] || {
  echo "rollback package must be NetConfig 2.0.0 release 59: $(identity "$ROLLBACK_RPM")" >&2; exit 1; }
installed=$(rpm -q --queryformat '%{NAME} %{VERSION} %{RELEASE} %{ARCH}\n' netconfig 2>/dev/null || true)
[[ -n $installed ]] || { echo "R60 lifecycle upgrade requires an installed NetConfig release 59" >&2; exit 1; }
read -r i_name i_ver i_rel i_arch <<<"$installed"
[[ $i_name == netconfig && $i_ver == 2.0.0 && ${i_rel%%.*} == 59 && $i_arch == noarch ]] || {
  echo "supported upgrade source is release 59, installed: $installed" >&2; exit 1; }
[[ "$r_ver-${r_rel%%.*}" == "$i_ver-${i_rel%%.*}" ]] || { echo "rollback RPM does not match installed source release" >&2; exit 1; }

mkdir -p "$SNAPSHOT_ROOT"
chmod 0700 "$SNAPSHOT_ROOT"
[[ ! -L $SNAPSHOT_ROOT ]] || { echo "snapshot root must not be a symlink" >&2; exit 1; }
OP_ID="r60-$(date -u +%Y%m%dT%H%M%SZ)-$$"
SNAPSHOT="$SNAPSHOT_ROOT/$OP_ID"
LOCK=/run/netconfig-r60-lifecycle.lock
exec 9>"$LOCK"
flock -n 9 || { echo "another NetConfig lifecycle operation is already running" >&2; exit 1; }

NETCONFIG_HOME=$($PYTHON - "$CONFIG_PATH" <<'PY'
import pathlib,sys
path=pathlib.Path(sys.argv[1])
home='/var/lib/netconfig'
if path.is_file() and not path.is_symlink():
    for raw in path.read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if line.startswith('NETCONFIG_HOME='):
            value=line.split('=',1)[1].strip().strip('"').strip("'")
            if value:
                home=value
print(home)
PY
)
[[ $NETCONFIG_HOME = /* ]] || { echo "NETCONFIG_HOME must be absolute" >&2; exit 1; }

BACKEND=$(PYTHONPATH="$ROOT/opt/netconfig" "$PYTHON" - "$NETCONFIG_HOME" <<'PY'
import sys
from netconfig.config import Paths,load_settings
print(str(load_settings(Paths(sys.argv[1])).get('core_db_backend') or 'sqlite').lower())
PY
)
[[ $BACKEND == sqlite || $BACKEND == postgres ]] || { echo "unsupported core_db_backend: $BACKEND" >&2; exit 1; }

if [[ $BACKEND == postgres ]]; then
  [[ -n $PG_ROLLBACK_DB && -n $PG_READY_MARKER ]] || {
    echo "PostgreSQL upgrade requires --postgres-rollback-db and --postgres-ready-marker" >&2; exit 21; }
  [[ -f $PG_READY_MARKER && ! -L $PG_READY_MARKER ]] || { echo "PostgreSQL readiness marker missing/unsafe" >&2; exit 1; }
  mode=$(stat -c '%a' "$PG_READY_MARKER")
  (( (8#$mode & 8#077) == 0 )) || { echo "PostgreSQL readiness marker must not be group/world accessible" >&2; exit 1; }
  "$PYTHON" - "$PG_READY_MARKER" "$PG_ROLLBACK_DB" <<'PY'
import json,re,sys
p,name=sys.argv[1:]
obj=json.load(open(p,encoding='utf-8'))
if obj.get('ready') is not True or obj.get('validated') is not True:
    raise SystemExit('PostgreSQL rollback readiness marker is not ready+validated')
if obj.get('rollback_database') != name:
    raise SystemExit('PostgreSQL rollback database does not match readiness marker')
if not re.fullmatch(r'[0-9a-f]{64}', str(obj.get('backup_sha256') or '')):
    raise SystemExit('PostgreSQL readiness marker lacks a valid backup SHA-256')
PY
fi

unit_enabled() { systemctl is-enabled "$1" 2>/dev/null || true; }
unit_active() { systemctl is-active "$1" 2>/dev/null || true; }
WEB_ENABLED=$(unit_enabled netconfig-web.service)
WEB_ACTIVE=$(unit_active netconfig-web.service)
TIMER_ENABLED=$(unit_enabled netconfig-backup.timer)
TIMER_ACTIVE=$(unit_active netconfig-backup.timer)

PYTHONPATH="$ROOT/opt/netconfig" "$PYTHON" "$ROOT/usr/bin/netconfig" --home "$NETCONFIG_HOME" \
  lifecycle snapshot --output "$SNAPSHOT" --config-path "$CONFIG_PATH" >/dev/null
cat >"$SNAPSHOT/service-state.env" <<EOF
WEB_ENABLED=$WEB_ENABLED
WEB_ACTIVE=$WEB_ACTIVE
TIMER_ENABLED=$TIMER_ENABLED
TIMER_ACTIVE=$TIMER_ACTIVE
SOURCE_PACKAGE=$installed
TARGET_PACKAGE=$t_name $t_ver $t_rel $t_arch
BACKEND=$BACKEND
EOF
chmod 0600 "$SNAPSHOT/service-state.env"
if [[ $BACKEND == postgres ]]; then
  cp --preserve=mode,timestamps "$PG_READY_MARKER" "$SNAPSHOT/postgres-rollback-ready.json"
  chmod 0600 "$SNAPSHOT/postgres-rollback-ready.json"
fi

restore_enablement() {
  case "$WEB_ENABLED" in enabled|enabled-runtime|static|indirect|generated) systemctl enable netconfig-web.service >/dev/null 2>&1 || : ;; disabled) systemctl disable netconfig-web.service >/dev/null 2>&1 || : ;; esac
  case "$TIMER_ENABLED" in enabled|enabled-runtime|static|indirect|generated) systemctl enable netconfig-backup.timer >/dev/null 2>&1 || : ;; disabled) systemctl disable netconfig-backup.timer >/dev/null 2>&1 || : ;; esac
}
restore_runtime_state() {
  if [[ $WEB_ACTIVE == active ]]; then systemctl start netconfig-web.service; else systemctl stop netconfig-web.service >/dev/null 2>&1 || :; fi
  if [[ $TIMER_ACTIVE == active ]]; then systemctl start netconfig-backup.timer; else systemctl stop netconfig-backup.timer >/dev/null 2>&1 || :; fi
}

rollback() {
  local cause=${1:-unknown}
  set +e
  echo "R60 upgrade verification failed; starting deterministic rollback: $cause" >&2
  systemctl stop netconfig-backup.timer netconfig-backup.service netconfig-web.service >/dev/null 2>&1 || :
  systemctl unmask --runtime netconfig-web.service netconfig-backup.service netconfig-backup.timer >/dev/null 2>&1 || :
  if ! dnf downgrade -y "$ROLLBACK_RPM"; then
    echo "RECOVERY_REQUIRED: RPM downgrade failed; snapshot retained at $SNAPSHOT" >&2
    exit 70
  fi
  systemctl daemon-reload >/dev/null 2>&1 || :
  if ! PYTHONPATH="$ROOT/opt/netconfig" "$PYTHON" "$ROOT/usr/bin/netconfig" --home "$NETCONFIG_HOME" \
       lifecycle restore-local "$SNAPSHOT" --config-path "$CONFIG_PATH" --confirm RESTORE_LOCAL_STATE >/dev/null; then
    echo "RECOVERY_REQUIRED: local-state restore failed; snapshot retained at $SNAPSHOT" >&2
    exit 71
  fi
  if ! PYTHONPATH="$ROOT/opt/netconfig" "$PYTHON" "$ROOT/usr/bin/netconfig" --home "$NETCONFIG_HOME" \
       lifecycle verify-live "$SNAPSHOT" --config-path "$CONFIG_PATH" >/dev/null; then
    echo "RECOVERY_REQUIRED: restored local state does not match pre-upgrade snapshot" >&2
    exit 72
  fi
  if [[ $BACKEND == postgres ]]; then
    if ! PYTHONPATH="$ROOT/opt/netconfig" "$PYTHON" "$ROOT/usr/bin/netconfig" --home "$NETCONFIG_HOME" \
         lifecycle switch-postgres-rollback --target-dbname "$PG_ROLLBACK_DB" --confirm SWITCH_POSTGRES_ROLLBACK >/dev/null; then
      echo "RECOVERY_REQUIRED: failed to switch to pre-restored PostgreSQL rollback database" >&2
      exit 73
    fi
  fi
  restore_enablement
  restore_runtime_state
  if ! rpm -q --queryformat '%{VERSION}-%{RELEASE}\n' netconfig | grep -Eq '^2\.0\.0-59([.]|$)'; then
    echo "RECOVERY_REQUIRED: rollback package identity verification failed" >&2
    exit 74
  fi
  /usr/bin/netconfig --help >/dev/null 2>&1 || { echo "RECOVERY_REQUIRED: rollback CLI smoke failed" >&2; exit 75; }
  echo "ROLLBACK_VERIFIED: prior package/local-state baseline restored; snapshot=$SNAPSHOT" >&2
  exit 1
}

systemctl stop netconfig-backup.timer netconfig-backup.service netconfig-web.service >/dev/null 2>&1 || :
systemctl mask --runtime netconfig-web.service netconfig-backup.service netconfig-backup.timer >/dev/null

if ! dnf upgrade -y "$TARGET_RPM"; then
  rollback "dnf upgrade failed"
fi
systemctl daemon-reload
if ! rpm -q --queryformat '%{VERSION}-%{RELEASE}\n' netconfig | grep -Eq '^2\.0\.0-60([.]|$)'; then
  rollback "target package identity mismatch"
fi
if ! /usr/bin/netconfig --help >/dev/null 2>&1; then
  rollback "installed CLI smoke failed"
fi
if ! systemd-analyze verify /usr/lib/systemd/system/netconfig-web.service \
    /usr/lib/systemd/system/netconfig-backup.service /usr/lib/systemd/system/netconfig-backup.timer >/dev/null 2>&1; then
  rollback "systemd unit verification failed"
fi
if ! /usr/bin/netconfig --home "$NETCONFIG_HOME" lifecycle verify "$SNAPSHOT" >/dev/null; then
  rollback "snapshot/external preservation verification failed"
fi

systemctl unmask --runtime netconfig-web.service netconfig-backup.service netconfig-backup.timer >/dev/null 2>&1 || :
restore_enablement
restore_runtime_state
if [[ $WEB_ACTIVE == active ]] && ! systemctl is-active --quiet netconfig-web.service; then
  rollback "web service failed to return to active state"
fi
if [[ $TIMER_ACTIVE == active ]] && ! systemctl is-active --quiet netconfig-backup.timer; then
  rollback "backup timer failed to return to active state"
fi

cat >"$SNAPSHOT/result.json" <<EOF
{"result":"UPGRADE_VERIFIED","source_release":59,"target_release":60,"backend":"$BACKEND","snapshot":"$SNAPSHOT"}
EOF
chmod 0600 "$SNAPSHOT/result.json"
echo "UPGRADE_VERIFIED: NetConfig release 60 installed; preservation snapshot retained at $SNAPSHOT"
