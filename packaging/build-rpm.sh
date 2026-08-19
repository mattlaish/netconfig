#!/usr/bin/bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=2.0.0
TOPDIR=${RPM_TOPDIR:-"$PROJECT_ROOT/.rpmbuild"}
STAGE=$(mktemp -d "${TMPDIR:-/tmp}/netconfig-rpm.XXXXXX")
SOURCE_ROOT="$STAGE/netconfig-$VERSION"

cleanup() {
    rm -rf -- "$STAGE"
}
trap cleanup EXIT

command -v rpmbuild >/dev/null 2>&1 || {
    echo "rpmbuild is required (AlmaLinux 10: sudo dnf install rpm-build)" >&2
    exit 2
}
test -x /usr/bin/python3.12 || {
    echo "/usr/bin/python3.12 is required" >&2
    exit 2
}

mkdir -p "$TOPDIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} "$SOURCE_ROOT"
cp -a "$PROJECT_ROOT/opt" "$PROJECT_ROOT/usr" "$PROJECT_ROOT/etc" "$SOURCE_ROOT/"
find "$SOURCE_ROOT" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$SOURCE_ROOT" -type f -name '*.py[co]' -delete
# The workspace may have been prepared on Windows. A CRLF shebang makes Linux
# look for an interpreter named '/usr/bin/python3.12\r' and systemd reports 203/EXEC.
find "$SOURCE_ROOT" -type f \( -name '*.py' -o -name '*.md' -o -name '*.service' \
    -o -name '*.timer' -o -name '*.sh' -o -path '*/etc/default/*' \
    -o -path '*/usr/bin/netconfig' \) -exec sed -i 's/\r$//' {} +
tar -C "$STAGE" -czf "$TOPDIR/SOURCES/netconfig-$VERSION.tar.gz" "netconfig-$VERSION"
cp "$PROJECT_ROOT/packaging/netconfig.spec" "$TOPDIR/SPECS/netconfig.spec"

rpmbuild -ba --define "_topdir $TOPDIR" "$TOPDIR/SPECS/netconfig.spec"
find "$TOPDIR/RPMS" "$TOPDIR/SRPMS" -type f -name '*.rpm' \
    -exec cp -f -- {} "$PROJECT_ROOT/" \;

echo "Artifacts:"
find "$PROJECT_ROOT" -maxdepth 1 -type f -name 'netconfig-2.0.0-16*.rpm' -print
