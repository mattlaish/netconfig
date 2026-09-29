## R60 upgrade and rollback

For production qualification of an existing R59 appliance, do not run a bare `dnf upgrade` as the lifecycle proof. Use `packaging/r60-lifecycle-upgrade.sh` with both the R60 target RPM and the exact supported R59 rollback RPM, plus `--allow-destructive`. The wrapper retains its pre-upgrade snapshot after success for bounded operator retention. PostgreSQL deployments must prepare a checksummed dump and a separately restored/validated rollback database before the wrapper is authorized.

## Q2 production qualification

R59 remains the product RPM identity. Production qualification is executed from the complete source baseline with `packaging/q2-qualify.sh`; the helper does not change the RPM version/release and cannot promote release state. AlmaLinux install/upgrade/rollback/restart/reboot gates must run only on a disposable qualification appliance with explicit destructive authorization. See `Q2_PRODUCTION_QUALIFICATION.md`.

# NetConfig Release 45 — RPM Installation

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Release 48 package identity

Current RPM identity is `netconfig-2.0.0-48.el10.noarch`. The offline helper RPM is built only after the final source-artifact integrity gate; canonical AlmaLinux 10 `rpmbuild`/DNF/systemd/SELinux qualification remains separate and deferred until actually run.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.


**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-24:** The monitoring/correlation roadmap is active. MC-1 through MC-9 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next formal slice is **MC-10 / Release 58 — Correlation Production Hardening & Qualification**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. MC-11 / Release 59 remains the final Topology-Aware Change Planning slice. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 45 — Operator UX Simplification

Release 45 addresses operator usability rather than adding a new Network Intelligence phase. The main navigation no longer exposes a duplicate **Network Intelligence** entry because that function already exists inside **Operations**. `/operations` now opens a task-oriented **Overview** explaining which workflow to use for one-off structured changes, desired state, campaigns, telemetry, intelligence, automation requests, model packs, and HA/DR. The repaired automation ledger is renamed **Automation Requests** to make its purpose explicit.

`/protocols` remains route-compatible but is presented as **Device Collection**: current read protocols are shown first, **Collect now** is the normal action, and NETCONF/RESTCONF/gNMI profile editing is placed under an Advanced disclosure. The MIB library now explains that MIBs are dictionaries rather than product features, surfaces only useful counts and lookup by default, and hides the raw file inventory under Advanced. Per-device SNMP pages likewise hide raw OID walks and vendor MIB values under Advanced sections; normal operational interface, ARP, and MAC/FDB views remain first-class.

There is no schema or public REST contract change. Package release advances to `2.0.0-45` because shipped web/runtime source changed. Status remains `IMPLEMENTED_TESTING_DEFERRED`; NI-7 remains the feature baseline and Q-1 remains open.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


## Release 43 — Console Sidebar Theme Refresh

Release 43 changes the console presentation layer only: the main navigation moves to a left sidebar, the supplied green theme is applied across shared UI chrome, and organization-specific branding is removed from the visible interface. Package identity is bumped because runtime source changed, but there is no schema or REST contract change.

> **Release 43 RPM status:** `tools/rpm-builder/` remains available to emit and verify an unsigned `netconfig-2.0.0-44.el10.noarch.rpm` offline. This does not replace canonical AlmaLinux 10 `rpmbuild`, DNF install/upgrade, systemd, and SELinux qualification.

Current helper-built package identity: **`netconfig-2.0.0-48.el10.noarch.rpm`**. It is offline-structurally verified but not yet canonically qualified on AlmaLinux 10.
Production package target: **AlmaLinux 10**.

## Build the RPM on AlmaLinux 10

```bash
sudo dnf install -y rpm-build python3.12 systemd-rpm-macros
chmod 0755 packaging/*.sh
./packaging/build-rpm.sh
./packaging/inspect-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
```

Do the build on a build VM/host, not on the production NetConfig server.

## Install or upgrade

```bash
sudo ./packaging/install-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
```

Equivalent package-manager command:

```bash
sudo dnf install ./netconfig-2.0.0-48.el10.noarch.rpm
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

## R67.2 fresh PostgreSQL Core installation

This path is **fresh-install only**. It is not SQLite→PostgreSQL migration, upgrade, force-install, or recovery of an operational appliance. The normal RPM path remains SQLite-first.

Before running the helper, install an organization-approved **psycopg 3** runtime that imports from `/usr/bin/python3.12`:

```bash
/usr/bin/python3.12 -c 'import psycopg; print(psycopg.__version__)'
```

Prepare a root-readable file containing only the PostgreSQL role password, then run the packaged helper. A distinct Core database is the default:

```bash
sudo /usr/libexec/netconfig/bootstrap-postgres-core \
  --password-file /root/netconfig-postgres-password \
  --host 127.0.0.1 \
  --dbname netconfig_core \
  --db-user netconfig
```

For a remote PostgreSQL host, pre-create the database and role there and pass `--host`; the helper validates that the target database has no existing public tables before it bootstraps NetConfig. Local `127.0.0.1`, `localhost`, and `::1` targets can have the role/database provisioned by the helper.

The helper installs `/etc/netconfig/postgres-core-password` as `root:netconfig` mode `0640`, creates explicit systemd drop-ins for both `netconfig-web.service` and `netconfig-backup.service` using `LoadCredential=postgres-core-password:...`, bootstraps the schema, saves Core PostgreSQL settings only after preflight succeeds, creates the first administrator interactively, starts Web/backup timer, and runs storage-status validation.

If a fresh bootstrap is interrupted, rerun the **same arguments** with `--resume`. Resume requires the stored argument fingerprint and refuses an operational SQLite Core, pre-existing untracked settings, a completed installation, or a different/non-fresh PostgreSQL user set.

Do not use the Interface History password field as the Core credential. R67.2 separates these settings in the Console.

