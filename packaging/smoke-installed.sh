#!/usr/bin/bash
set -euo pipefail

rpm -q netconfig
test -x /usr/bin/netconfig
test "$(head -n 1 /usr/bin/netconfig)" = '#!/usr/bin/python3.12'
if LC_ALL=C grep -q $'\r' /usr/bin/netconfig; then
    echo "/usr/bin/netconfig contains Windows CRLF line endings" >&2
    exit 1
fi
test -r /opt/netconfig/netconfig/web.py
test -d /var/lib/netconfig
test "$(stat -c '%U:%G' /var/lib/netconfig)" = "netconfig:netconfig"
systemd-analyze verify /usr/lib/systemd/system/netconfig-web.service \
    /usr/lib/systemd/system/netconfig-backup.service \
    /usr/lib/systemd/system/netconfig-backup.timer

PYCACHE=$(mktemp -d "${TMPDIR:-/tmp}/netconfig-pycache.XXXXXX")
trap 'rm -rf -- "$PYCACHE"' EXIT
sudo -u netconfig env NETCONFIG_HOME=/var/lib/netconfig PYTHONPYCACHEPREFIX="$PYCACHE" \
    /usr/bin/python3.12 /opt/netconfig/selftest.py

# Q-1 runtime preflight is configuration-aware. PostgreSQL client tools and
# gnmic become required only when those production paths are active.
Q1_REPORT=$(mktemp "${TMPDIR:-/tmp}/netconfig-q1-preflight.XXXXXX")
trap 'rm -rf -- "$PYCACHE"; rm -f -- "$Q1_REPORT"' EXIT
sudo -u netconfig env NETCONFIG_HOME=/var/lib/netconfig \
    /usr/bin/netconfig qualify > "$Q1_REPORT"
grep -q '"ok": true' "$Q1_REPORT"

for unit in /usr/lib/systemd/system/netconfig-web.service /usr/lib/systemd/system/netconfig-backup.service; do
    grep -q '^NoNewPrivileges=true$' "$unit"
    grep -q '^ProtectSystem=strict$' "$unit"
    grep -q '^PrivateTmp=true$' "$unit"
    grep -q '^ReadWritePaths=/var/lib/netconfig$' "$unit"
done

echo "Installed RPM smoke checks: PASS"
