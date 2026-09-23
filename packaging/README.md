# NetConfig RPM build and installation (AlmaLinux 10)

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 45 — Operator UX Simplification

Release 45 addresses operator usability rather than adding a new Network Intelligence phase. The main navigation no longer exposes a duplicate **Network Intelligence** entry because that function already exists inside **Operations**. `/operations` now opens a task-oriented **Overview** explaining which workflow to use for one-off structured changes, desired state, campaigns, telemetry, intelligence, automation requests, model packs, and HA/DR. The repaired automation ledger is renamed **Automation Requests** to make its purpose explicit.

`/protocols` remains route-compatible but is presented as **Device Collection**: current read protocols are shown first, **Collect now** is the normal action, and NETCONF/RESTCONF/gNMI profile editing is placed under an Advanced disclosure. The MIB library now explains that MIBs are dictionaries rather than product features, surfaces only useful counts and lookup by default, and hides the raw file inventory under Advanced. Per-device SNMP pages likewise hide raw OID walks and vendor MIB values under Advanced sections; normal operational interface, ARP, and MAC/FDB views remain first-class.

There is no schema or public REST contract change. Package release advances to `2.0.0-45` because shipped web/runtime source changed. Status remains `IMPLEMENTED_TESTING_DEFERRED`; NI-7 remains the feature baseline and Q-1 remains open.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


## Release 43 — Console Sidebar Theme Refresh

Release 43 keeps the existing offline builder/verifier but changes the shipped runtime source: the web console now uses a left sidebar instead of the crowded top navigation, adopts the supplied green theme palette for shared chrome, and removes organization-specific branding from the visible UI. There is no schema or REST API change in this refresh.

> **Release 43 RPM status:** `tools/rpm-builder/` can still emit and independently verify `netconfig-2.0.0-44.el10.noarch.rpm` offline. That artifact is unsigned and not production-qualified; canonical AlmaLinux `rpmbuild`, DNF install/upgrade, systemd, and SELinux qualification remain deferred.

The supported production package target is AlmaLinux 10. Release 43 source uses
RPM identity `netconfig-2.0.0-44.el10.noarch`. Older `2.0.0-34` packages are
historical UI-1 packages and do not identify the current Release 43 / NI-7 source baseline.

## Build host

Use a disposable AlmaLinux 10 build host or VM:

```bash
sudo dnf install -y rpm-build python3.12 systemd-rpm-macros
chmod 0755 packaging/*.sh
./packaging/build-rpm.sh
```

Expected outputs in the project root:

- `netconfig-2.0.0-48.el10.noarch.rpm`
- `netconfig-2.0.0-48.el10.src.rpm`

Inspect the binary RPM before installation:

```bash
./packaging/inspect-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
```

## Install / upgrade

The guarded helper validates AlmaLinux 10 and Release 48 package identity:

```bash
sudo ./packaging/install-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
```

Equivalent manual package command:

```bash
sudo dnf install ./netconfig-2.0.0-48.el10.noarch.rpm
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
using the Release number read from `netconfig.spec`. For this Release 48 baseline its default
name is:

```text
netconfig-netconfig-2.0.0-48-rpm-build-source.zip
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
