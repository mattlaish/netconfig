# NetConfig RPM build and installation (AlmaLinux 10)

> **Canonical project state — 2026-09-17:** **CURRENT IMPLEMENTATION BASELINE** = **Release 40 / NI-7 L3/VRF Path & Route Dependency Intelligence** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-40`; NI-1 through NI-7 and Enterprise Operations are implemented in source. Q-1 live PostgreSQL/protocol/vendor/device/AlmaLinux gates remain deferred/`NOT_RUN`; Release 40 does not promote them to PASS.

The supported production package target is AlmaLinux 10. Release 39 source uses
RPM identity `netconfig-2.0.0-40.el10.noarch`. Older `2.0.0-34` packages are
historical UI-1 packages and do not identify the current NI-6 delivery.

## Build host

Use a disposable AlmaLinux 10 build host or VM:

```bash
sudo dnf install -y rpm-build python3.12 systemd-rpm-macros
chmod 0755 packaging/*.sh
./packaging/build-rpm.sh
```

Expected outputs in the project root:

- `netconfig-2.0.0-40.el10.noarch.rpm`
- `netconfig-2.0.0-40.el10.src.rpm`

Inspect the binary RPM before installation:

```bash
./packaging/inspect-rpm.sh ./netconfig-2.0.0-40.el10.noarch.rpm
```

## Install / upgrade

The guarded helper validates AlmaLinux 10 and Release 39 package identity:

```bash
sudo ./packaging/install-rpm.sh ./netconfig-2.0.0-40.el10.noarch.rpm
```

Equivalent manual package command:

```bash
sudo dnf install ./netconfig-2.0.0-40.el10.noarch.rpm
sudo systemctl daemon-reload
```

For a **fresh installation**, create the first admin explicitly before starting
the web console:

```bash
sudo -u netconfig /usr/bin/netconfig user add admin \
  --role admin --fullname "NetConfig Administrator"
```

Then enable the local-only web console and backup timer:

```bash
sudo systemctl enable --now netconfig-web.service netconfig-backup.timer
```

The console binds to `127.0.0.1:8778` by default. Use an SSH tunnel or a TLS
reverse proxy/WAF for remote administration; do not directly expose the plain
HTTP listener.

Upgrade semantics are intentionally conservative: `/var/lib/netconfig` is
retained, `/etc/default/netconfig` is `%config(noreplace)`, and the package never
ships runtime database/vault content or a pre-created administrator password.

## Installed-runtime smoke

```bash
./packaging/smoke-installed.sh
```

The smoke checks package identity, launcher line endings, state ownership,
systemd unit hardening, selftest, and configuration-aware runtime qualification.

## Transfer bundle

`packaging/prepare-transfer.ps1` creates the Windows-to-AlmaLinux transfer bundle
using the Release number read from `netconfig.spec`. For this baseline its default
name is:

```text
netconfig-2.0.0-40-rpm-build-source.zip
```

A source change intended for a later distributable package must increment the RPM
Release; never reuse a published Release number for different source.

## Qualification boundary

`q1-source-gates.sh`, `q1-qualify-postgres.sh`, and `q1-qualify-almalinux.sh`
remain the fail-closed qualification entry points. Missing infrastructure is
`NOT_RUN`, not PASS. The Debian artifact runner can validate source and shell
syntax but cannot claim an AlmaLinux RPM build/install result.

## PH-2 PostgreSQL packaging note

Release `2.0.0-30` adds optional PostgreSQL core support. The base RPM remains usable in SQLite mode without psycopg. A deployment that selects `core_db_backend=postgres` must also provide a compatible psycopg 3 driver in the Python 3.12 runtime and a PostgreSQL service credential. The current execution environment has not performed an AlmaLinux RPM build/install with psycopg, so that remains a release qualification gate rather than a claimed package dependency result.


PH-3 note: NETCONF and RESTCONF use existing system/OpenSSL/Python facilities. gNMI collection requires an external `gnmic` binary when selected; the current RPM source does not bundle or claim qualification of that optional executable.


## Q-1 qualification runners

Q-1 adds three fail-closed qualification entry points. They report an unavailable prerequisite as `NOT_RUN` rather than converting it into a pass:

```bash
./packaging/q1-source-gates.sh
./packaging/q1-qualify-postgres.sh
./packaging/q1-qualify-almalinux.sh
```

`q1-source-gates.sh` requires Python 3.12+, pytest, Ruff, mypy and a psycopg-capable development environment, then runs lint/type/compile/focused/full/selftest/shell/line-ending gates. `q1-qualify-postgres.sh` requires a real PostgreSQL service plus `pg_dump`, `pg_restore`, psycopg and an explicitly supplied `NETCONFIG_TEST_PG_PASSWORD`; it executes the real concurrency, advisory-lock/session-loss, migration/sequence and backup/restore drill tests. `q1-qualify-almalinux.sh` requires AlmaLinux 10 and RPM build tooling; package installation is not performed unless both `--install` and `NETCONFIG_Q1_ALLOW_INSTALL=1` are supplied.

Current spec metadata is **Version 2.0.0 / Release 39**. A later source change intended for distribution must increment Release before creating another RPM.
