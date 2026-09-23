#!/usr/bin/bash
set -euo pipefail

RPM_PATH=${1:-}
if [[ -z "$RPM_PATH" || "$RPM_PATH" == "-h" || "$RPM_PATH" == "--help" ]]; then
    cat <<'USAGE'
usage: sudo ./packaging/install-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm

Installs or upgrades the NetConfig RPM on AlmaLinux 10. The script deliberately
DOES NOT create the first admin, create/unlock the credential vault, or start the
web service. Those are explicit post-install operator actions.
USAGE
    [[ -n "$RPM_PATH" ]] && exit 0
    exit 2
fi

[[ $EUID -eq 0 ]] || {
    echo "install-rpm.sh must run as root (use sudo)" >&2
    exit 2
}
[[ -f "$RPM_PATH" ]] || {
    echo "RPM not found: $RPM_PATH" >&2
    exit 2
}
# shellcheck disable=SC1091
source /etc/os-release
if [[ ${ID:-} != "almalinux" || ${VERSION_ID%%.*} != "10" ]]; then
    echo "NetConfig production RPM target is AlmaLinux 10; current=${ID:-unknown} ${VERSION_ID:-unknown}" >&2
    exit 20
fi
for tool in dnf rpm systemctl; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "missing required tool: $tool" >&2
        exit 2
    }
done

IDENTITY=$(rpm -qp --queryformat '%{NAME} %{VERSION} %{RELEASE} %{ARCH}\n' "$RPM_PATH")
read -r NAME VERSION RELEASE ARCH <<<"$IDENTITY"
[[ "$NAME" == "netconfig" && "$VERSION" == "2.0.0" && "$ARCH" == "noarch" ]] || {
    echo "unexpected package identity: $IDENTITY" >&2
    exit 1
}
if [[ ${RELEASE%%.*} != "48" ]]; then
    echo "expected NetConfig RPM release 48, got: $IDENTITY" >&2
    exit 1
fi

echo "Installing: $NAME-$VERSION-$RELEASE.$ARCH"
if rpm -q netconfig >/dev/null 2>&1; then
    dnf upgrade -y "$RPM_PATH"
else
    dnf install -y "$RPM_PATH"
fi
systemctl daemon-reload

test -x /usr/bin/netconfig
test -d /opt/netconfig/netconfig
test -d /var/lib/netconfig
test "$(stat -c '%U:%G' /var/lib/netconfig)" = "netconfig:netconfig"

cat <<'NEXT'

NetConfig RPM installation completed.

Fresh install — create the first administrator interactively BEFORE starting the web console:
  sudo -u netconfig /usr/bin/netconfig user add admin --role admin --fullname "NetConfig Administrator"

Then enable the local-only web console and backup timer:
  sudo systemctl enable --now netconfig-web.service netconfig-backup.timer

Verify:
  systemctl is-active netconfig-web.service
  systemctl is-active netconfig-backup.timer
  curl -I http://127.0.0.1:8778/

The web service binds to 127.0.0.1 by default. Use an SSH tunnel or a TLS reverse
proxy/WAF for remote administration; do not expose the plain HTTP listener directly.

Upgrade installs preserve /var/lib/netconfig and /etc/default/netconfig
(%config(noreplace)). Do not recreate the first admin on an existing deployment.
NEXT
