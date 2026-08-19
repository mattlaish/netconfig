#!/usr/bin/bash
set -euo pipefail

RPM_PATH=${1:?"usage: inspect-rpm.sh path/to/netconfig.rpm"}
test -f "$RPM_PATH"

echo "== identity =="
rpm -qp --queryformat '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' "$RPM_PATH"
echo "== requirements =="
rpm -qp --requires "$RPM_PATH"
echo "== scripts =="
rpm -qp --scripts "$RPM_PATH"
echo "== payload =="
rpm -qplv "$RPM_PATH"

rpm -qpl "$RPM_PATH" | grep -qx '/usr/bin/netconfig'
rpm -qpl "$RPM_PATH" | grep -qx '/usr/lib/systemd/system/netconfig-web.service'
rpm -qpl "$RPM_PATH" | grep -qx '/usr/lib/systemd/system/netconfig-backup.timer'
rpm -qpl "$RPM_PATH" | grep -qx '/var/lib/netconfig'
if rpm -qpl "$RPM_PATH" | grep -Eq '(__pycache__|\.py[co]$|/var/lib/netconfig/.+)'; then
    echo "unexpected cache/runtime data in RPM" >&2
    exit 1
fi
EXTRACT=$(mktemp -d "${TMPDIR:-/tmp}/netconfig-rpm-inspect.XXXXXX")
trap 'rm -rf -- "$EXTRACT"' EXIT
(cd "$EXTRACT" && rpm2cpio "$RPM_PATH" | cpio -idm --quiet ./usr/bin/netconfig)
test "$(head -n 1 "$EXTRACT/usr/bin/netconfig")" = '#!/usr/bin/python3.12'
if LC_ALL=C grep -q $'\r' "$EXTRACT/usr/bin/netconfig"; then
    echo "packaged launcher contains Windows CRLF line endings" >&2
    exit 1
fi
echo "RPM structure checks: PASS"
