#!/usr/bin/env bash
set -euo pipefail

# R67.2 fresh-install-only PostgreSQL Core bootstrap.
# This is intentionally not an upgrade/migration command. Existing operational
# installations must use the lifecycle/migration path instead.

STATE_DIR=/var/lib/netconfig
STATE_FILE="$STATE_DIR/.fresh-postgres-core-bootstrap.state"
COMPLETE_FILE="$STATE_DIR/.fresh-postgres-core-bootstrap.complete"
CRED_DIR=/etc/netconfig
CRED_FILE="$CRED_DIR/postgres-core-password"
HOST=127.0.0.1
PORT=5432
DBNAME=netconfig_core
DBUSER=netconfig
SSLMODE=prefer
ADMIN=admin
FULLNAME="NetConfig Administrator"
PASSWORD_SOURCE=""
RESUME=0

usage() {
  cat <<'EOF'
Usage: sudo ./packaging/bootstrap-postgres-core.sh \
  --password-file /root/netconfig-postgres-password \
  [--host 127.0.0.1] [--port 5432] [--dbname netconfig_core] \
  [--db-user netconfig] [--sslmode prefer] [--admin admin] \
  [--fullname "NetConfig Administrator"] [--resume]

Fresh install only. For remote PostgreSQL, pre-create the database/role and use
that host; local 127.0.0.1/localhost deployments are provisioned automatically.
The script refuses an existing SQLite core and will only --resume the exact same
interrupted fresh bootstrap.
EOF
}

while (($#)); do
  case "$1" in
    --host) HOST=${2:?}; shift 2 ;;
    --port) PORT=${2:?}; shift 2 ;;
    --dbname) DBNAME=${2:?}; shift 2 ;;
    --db-user) DBUSER=${2:?}; shift 2 ;;
    --sslmode) SSLMODE=${2:?}; shift 2 ;;
    --admin) ADMIN=${2:?}; shift 2 ;;
    --fullname) FULLNAME=${2:?}; shift 2 ;;
    --password-file) PASSWORD_SOURCE=${2:?}; shift 2 ;;
    --resume) RESUME=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ ${EUID} -eq 0 ]] || { echo "must run as root" >&2; exit 1; }
[[ -n "$PASSWORD_SOURCE" ]] || { echo "--password-file is required" >&2; exit 2; }
[[ -r "$PASSWORD_SOURCE" ]] || { echo "password source is not readable" >&2; exit 2; }
[[ -s "$PASSWORD_SOURCE" ]] || { echo "password source is empty" >&2; exit 2; }
[[ "$DBNAME" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || { echo "invalid database name" >&2; exit 2; }
[[ "$DBUSER" =~ ^[A-Za-z_][A-Za-z0-9_]{0,62}$ ]] || { echo "invalid database user" >&2; exit 2; }
[[ "$PORT" =~ ^[0-9]+$ ]] || { echo "invalid PostgreSQL port" >&2; exit 2; }
case "$SSLMODE" in disable|allow|prefer|require|verify-ca|verify-full) ;; *) echo "invalid sslmode" >&2; exit 2;; esac

install -d -m 0750 -o netconfig -g netconfig "$STATE_DIR"
FINGERPRINT=$(printf '%s\0' "$HOST" "$PORT" "$DBNAME" "$DBUSER" "$SSLMODE" "$ADMIN" | sha256sum | awk '{print $1}')

if [[ -e "$COMPLETE_FILE" ]]; then
  echo "fresh PostgreSQL Core bootstrap is already complete; use normal lifecycle tooling" >&2
  exit 1
fi
if [[ -e "$STATE_FILE" ]]; then
  old=$(awk -F= '$1=="fingerprint"{print $2}' "$STATE_FILE" || true)
  [[ $RESUME -eq 1 ]] || { echo "interrupted bootstrap state exists; rerun with --resume" >&2; exit 1; }
  [[ "$old" == "$FINGERPRINT" ]] || { echo "--resume arguments do not match interrupted bootstrap" >&2; exit 1; }
else
  [[ $RESUME -eq 0 ]] || { echo "no interrupted bootstrap exists to resume" >&2; exit 1; }
  if [[ -e "$STATE_DIR/settings.json" ]]; then
    echo "refusing fresh PostgreSQL bootstrap: pre-existing settings.json found without resumable bootstrap state" >&2
    exit 1
  fi
  if [[ -s "$STATE_DIR/inventory.db" ]]; then
    echo "refusing fresh PostgreSQL bootstrap: existing SQLite core detected at $STATE_DIR/inventory.db" >&2
    exit 1
  fi
  printf 'fingerprint=%s\n' "$FINGERPRINT" > "$STATE_FILE"
  chown root:root "$STATE_FILE"; chmod 0600 "$STATE_FILE"
fi

phase_done() { grep -qx "phase=$1" "$STATE_FILE" 2>/dev/null; }
mark_phase() { printf 'phase=%s\n' "$1" >> "$STATE_FILE"; }

if ! phase_done preflight; then
  command -v /usr/bin/python3.12 >/dev/null
  command -v sudo >/dev/null
  /usr/bin/python3.12 - <<'PY'
try:
    import psycopg
except Exception as exc:
    raise SystemExit("psycopg 3 is required for PostgreSQL Core: " + str(exc))
major = int(str(getattr(psycopg, "__version__", "0")).split(".", 1)[0])
if major < 3:
    raise SystemExit("psycopg 3 or newer is required")
print("psycopg", psycopg.__version__, "OK")
PY
  [[ -x /usr/bin/netconfig ]] || { echo "/usr/bin/netconfig is not installed" >&2; exit 1; }
  mark_phase preflight
fi

if ! phase_done database; then
  if [[ "$HOST" == "127.0.0.1" || "$HOST" == "localhost" || "$HOST" == "::1" ]]; then
    command -v psql >/dev/null || { echo "psql is required for local PostgreSQL provisioning" >&2; exit 1; }
    command -v createuser >/dev/null || { echo "createuser is required for local PostgreSQL provisioning" >&2; exit 1; }
    command -v createdb >/dev/null || { echo "createdb is required for local PostgreSQL provisioning" >&2; exit 1; }
    if sudo -u postgres psql -X -Atqc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" | grep -qx 1; then
      existing_tables=$(sudo -u postgres psql -X -d "$DBNAME" -Atqc \
        "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename" || true)
      if [[ -n "$existing_tables" ]]; then
        echo "refusing fresh PostgreSQL bootstrap: target database already contains public tables" >&2
        printf '%s\n' "$existing_tables" | head -n 12 >&2
        exit 1
      fi
    fi
    if ! sudo -u postgres psql -X -Atqc "SELECT 1 FROM pg_roles WHERE rolname='${DBUSER}'" | grep -qx 1; then
      sudo -u postgres createuser --login "$DBUSER"
    fi
    # Set role password via stdin, never argv/environment/log output.
    DBUSER_ENV="$DBUSER" PASSWORD_SOURCE_ENV="$PASSWORD_SOURCE" /usr/bin/python3.12 - <<'PY' | sudo -u postgres psql -X -v ON_ERROR_STOP=1 >/dev/null
import os
from pathlib import Path
user=os.environ["DBUSER_ENV"]
pw=Path(os.environ["PASSWORD_SOURCE_ENV"]).read_text().rstrip("\r\n")
if not pw:
    raise SystemExit("password file is empty")
# identifiers were constrained by the shell regex above; quote password as a SQL literal.
print(f"ALTER ROLE \"{user}\" LOGIN PASSWORD '{pw.replace(chr(39), chr(39)*2)}';")
PY
    if ! sudo -u postgres psql -X -Atqc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" | grep -qx 1; then
      sudo -u postgres createdb -O "$DBUSER" "$DBNAME"
    fi
  else
    echo "remote PostgreSQL selected: database/role provisioning is external; connectivity will be validated next"
  fi
  mark_phase database
fi

if ! phase_done credential; then
  install -d -m 0750 -o root -g netconfig "$CRED_DIR"
  install -m 0640 -o root -g netconfig "$PASSWORD_SOURCE" "$CRED_FILE"
  [[ -s "$CRED_FILE" ]] || { echo "credential install failed" >&2; exit 1; }
  for unit in netconfig-web.service netconfig-backup.service; do
    d="/etc/systemd/system/${unit}.d"
    install -d -m 0755 "$d"
    cat > "$d/postgres-core.conf" <<EOF
[Service]
LoadCredential=postgres-core-password:$CRED_FILE
EOF
    chmod 0644 "$d/postgres-core.conf"
  done
  systemctl daemon-reload
  mark_phase credential
fi

if ! phase_done schema; then
  NETCONFIG_HOME="$STATE_DIR" NETCONFIG_DB_PASSWORD_FILE="$CRED_FILE" \
  PYTHONPATH=/opt/netconfig HOST_ENV="$HOST" PORT_ENV="$PORT" DB_ENV="$DBNAME" USER_ENV="$DBUSER" SSL_ENV="$SSLMODE" \
  sudo -u netconfig -E /usr/bin/python3.12 - <<'PY'
import os
import psycopg
from netconfig.config import DEFAULT_SETTINGS
from netconfig.credentials import postgres_core_password
from netconfig.postgres_core import postgres_params, preflight_core_postgres
s=dict(DEFAULT_SETTINGS)
s.update(core_db_backend="postgres", pg_host=os.environ["HOST_ENV"], pg_port=int(os.environ["PORT_ENV"]),
         pg_dbname=os.environ["DB_ENV"], pg_user=os.environ["USER_ENV"], pg_sslmode=os.environ["SSL_ENV"])
pw,src=postgres_core_password()
params=postgres_params(s,password=pw)
# Fresh-install bootstrap never attaches to an existing application database.
# This catches the common mistake of pointing Core at a History-only database.
probe=dict(params)
probe.pop("application_name", None)
with psycopg.connect(**probe, autocommit=True) as conn:
    rows=conn.execute(
        "SELECT tablename FROM pg_catalog.pg_tables "
        "WHERE schemaname='public' ORDER BY tablename"
    ).fetchall()
    existing=[r[0] for r in rows]
if existing:
    raise SystemExit(
        "fresh Core target is not empty; refusing to bootstrap over existing public tables: "
        + ", ".join(existing[:12])
    )
r=preflight_core_postgres(s,password=pw)
if not r.get("ok"):
    raise SystemExit(f"Core PostgreSQL preflight failed at {r.get('stage')}: {r.get('error')}")
print("Core PostgreSQL schema preflight/bootstrap OK", r.get("schema_revision"), "credential", src)
PY
  mark_phase schema
fi

if ! phase_done settings; then
  NETCONFIG_HOME="$STATE_DIR" PYTHONPATH=/opt/netconfig HOST_ENV="$HOST" PORT_ENV="$PORT" DB_ENV="$DBNAME" USER_ENV="$DBUSER" SSL_ENV="$SSLMODE" \
  sudo -u netconfig -E /usr/bin/python3.12 - <<'PY'
import os
from netconfig import config
p=config.Paths(os.environ["NETCONFIG_HOME"])
s=config.load_settings(p)
s.update(core_db_backend="postgres", pg_host=os.environ["HOST_ENV"], pg_port=int(os.environ["PORT_ENV"]),
         pg_dbname=os.environ["DB_ENV"], pg_user=os.environ["USER_ENV"], pg_sslmode=os.environ["SSL_ENV"])
config.save_settings(p,s)
PY
  mark_phase settings
fi

if ! phase_done admin; then
  # A crash can occur after user creation but before the phase checkpoint. Resume
  # accepts only the exact requested existing admin and refuses any other user set.
  if ADMIN_ENV="$ADMIN" NETCONFIG_DB_PASSWORD_FILE="$CRED_FILE" NETCONFIG_HOME="$STATE_DIR" \
     PYTHONPATH=/opt/netconfig sudo -u netconfig -E /usr/bin/python3.12 - <<'PY'
import os
from netconfig.manager import Manager
m=Manager(os.environ["NETCONFIG_HOME"])
try:
    users=m.users.all()
    desired=os.environ["ADMIN_ENV"]
    if not users:
        raise SystemExit(10)
    if len(users) == 1 and users[0]["username"] == desired and users[0]["role"] == "admin":
        raise SystemExit(0)
    raise SystemExit("refusing resume: Core database already contains a different/non-fresh user set")
finally:
    m.close()
PY
  then
    echo "Requested first administrator already exists; accepting idempotent resume."
  else
    rc=$?
    if [[ $rc -ne 10 ]]; then
      exit "$rc"
    fi
    echo "Create the first NetConfig administrator (interactive password prompt follows)."
    NETCONFIG_DB_PASSWORD_FILE="$CRED_FILE" sudo -u netconfig -E /usr/bin/netconfig --home "$STATE_DIR" \
      user add "$ADMIN" --role admin --fullname "$FULLNAME"
  fi
  mark_phase admin
fi

if ! phase_done first_start; then
  systemctl enable --now netconfig-web.service netconfig-backup.timer
  systemctl is-active --quiet netconfig-web.service
  NETCONFIG_DB_PASSWORD_FILE="$CRED_FILE" sudo -u netconfig -E /usr/bin/netconfig --home "$STATE_DIR" storage status >/dev/null
  mark_phase first_start
fi

mv "$STATE_FILE" "$COMPLETE_FILE"
chmod 0600 "$COMPLETE_FILE"
echo "Fresh PostgreSQL Core bootstrap complete: database=$DBNAME user=$DBUSER host=$HOST"
echo "Core credential is wired to both netconfig-web.service and netconfig-backup.service."
