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

echo "Installed RPM smoke checks: PASS"
