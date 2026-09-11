#!/usr/bin/bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"
INSTALL=0
if [[ ${1:-} == "--install" ]]; then
    INSTALL=1
elif [[ $# -gt 0 ]]; then
    echo "usage: $0 [--install]" >&2
    exit 2
fi

# This gate is intentionally target-specific. Running on another distribution is
# NOT_RUN rather than evidence for the declared AlmaLinux 10 package target.
# shellcheck disable=SC1091
source /etc/os-release
if [[ ${ID:-} != "almalinux" || ${VERSION_ID%%.*} != "10" ]]; then
    echo "Q-1 AlmaLinux qualification requires AlmaLinux 10; current=${ID:-unknown} ${VERSION_ID:-unknown}" >&2
    exit 20
fi

for tool in rpmbuild rpm rpm2cpio cpio systemd-analyze /usr/bin/python3.12; do
    if [[ $tool = /* ]]; then
        [[ -x $tool ]] || { echo "missing required tool: $tool" >&2; exit 2; }
    else
        command -v "$tool" >/dev/null 2>&1 || { echo "missing required tool: $tool" >&2; exit 2; }
    fi
done

./packaging/q1-source-gates.sh
rm -rf .rpmbuild
./packaging/build-rpm.sh
RPM=$(find . -maxdepth 1 -type f -name 'netconfig-2.0.0-*.el10.noarch.rpm' -printf '%f\n' | sort -V | tail -1)
[[ -n $RPM ]] || { echo "built binary RPM not found" >&2; exit 1; }
./packaging/inspect-rpm.sh "$RPM"
systemd-analyze verify \
    usr/lib/systemd/system/netconfig-web.service \
    usr/lib/systemd/system/netconfig-backup.service \
    usr/lib/systemd/system/netconfig-backup.timer

if [[ $INSTALL -eq 0 ]]; then
    echo "Q-1 RPM build/static qualification: PASS"
    echo "Installed-runtime gate: NOT_RUN (rerun with --install on a disposable AlmaLinux 10 host)"
    exit 0
fi

if [[ ${NETCONFIG_Q1_ALLOW_INSTALL:-0} != "1" ]]; then
    echo "--install requires NETCONFIG_Q1_ALLOW_INSTALL=1 on a disposable qualification host" >&2
    exit 2
fi
command -v sudo >/dev/null 2>&1 || { echo "sudo is required for --install" >&2; exit 2; }

BEFORE=$(rpm -q netconfig 2>/dev/null || true)
echo "pre-install package: ${BEFORE:-not-installed}"
sudo dnf upgrade -y "./$RPM"
./packaging/smoke-installed.sh
sudo systemctl daemon-reload
sudo systemctl restart netconfig-web.service
systemctl is-active --quiet netconfig-web.service
systemctl status --no-pager netconfig-web.service >/dev/null
systemctl list-timers --all --no-pager | grep -q netconfig-backup.timer
sudo systemctl restart netconfig-web.service
systemctl is-active --quiet netconfig-web.service

echo "Q-1 AlmaLinux RPM install/restart qualification: PASS"
