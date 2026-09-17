# NetConfig Release 39 — RPM Installation

Current package identity: **`netconfig-2.0.0-40.el10.noarch.rpm`**.
Production package target: **AlmaLinux 10**.

## Build the RPM on AlmaLinux 10

```bash
sudo dnf install -y rpm-build python3.12 systemd-rpm-macros
chmod 0755 packaging/*.sh
./packaging/build-rpm.sh
./packaging/inspect-rpm.sh ./netconfig-2.0.0-40.el10.noarch.rpm
```

Do the build on a build VM/host, not on the production NetConfig server.

## Install or upgrade

```bash
sudo ./packaging/install-rpm.sh ./netconfig-2.0.0-40.el10.noarch.rpm
```

Equivalent package-manager command:

```bash
sudo dnf install ./netconfig-2.0.0-40.el10.noarch.rpm
sudo systemctl daemon-reload
```

The RPM preserves existing `/var/lib/netconfig` state and installs
`/etc/default/netconfig` as `%config(noreplace)`.

## Fresh install only: create the first administrator

The package never creates a default password or hidden administrator.

```bash
sudo -u netconfig /usr/bin/netconfig user add admin \
  --role admin --fullname "NetConfig Administrator"
```

Skip this step on upgrades when the user database already exists.

## Enable services

```bash
sudo systemctl enable --now netconfig-web.service netconfig-backup.timer
systemctl is-active netconfig-web.service
systemctl is-active netconfig-backup.timer
```

The console binds to **127.0.0.1:8778** by default. For remote use, prefer:

```bash
ssh -L 8778:127.0.0.1:8778 admin@netconfig-server
```

Then browse to `http://127.0.0.1:8778/`, or deploy a properly configured TLS
reverse proxy/WAF in front of the local listener. Do not expose the default
plain-HTTP listener directly to an untrusted network.

## Verify

From the source/qualification bundle:

```bash
./packaging/smoke-installed.sh
sudo systemctl status --no-pager netconfig-web.service
sudo journalctl -u netconfig-web.service -n 100 --no-pager
sudo -u netconfig /usr/bin/netconfig --home /var/lib/netconfig qualify
```

Optional PostgreSQL, gNMI, live protocol, vendor-device, scale, and Q-1 gates are
not considered PASS unless their required infrastructure is actually used.

See `opt/netconfig/INSTALL.md` for secrets, PostgreSQL, upgrades, backups, and
full operational guidance.
