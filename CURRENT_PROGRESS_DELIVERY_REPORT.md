# NetConfig Current Progress Delivery Report

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

## Release 48 current status

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

Release 48 adds the persisted read-only Sensor Engine/API over existing evidence. Historical release evidence below remains unchanged and must not be read as the current package identity.


**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 45 — Operator UX Simplification

Release 45 addresses operator usability rather than adding a new Network Intelligence phase. The main navigation no longer exposes a duplicate **Network Intelligence** entry because that function already exists inside **Operations**. `/operations` now opens a task-oriented **Overview** explaining which workflow to use for one-off structured changes, desired state, campaigns, telemetry, intelligence, automation requests, model packs, and HA/DR. The repaired automation ledger is renamed **Automation Requests** to make its purpose explicit.

`/protocols` remains route-compatible but is presented as **Device Collection**: current read protocols are shown first, **Collect now** is the normal action, and NETCONF/RESTCONF/gNMI profile editing is placed under an Advanced disclosure. The MIB library now explains that MIBs are dictionaries rather than product features, surfaces only useful counts and lookup by default, and hides the raw file inventory under Advanced. Per-device SNMP pages likewise hide raw OID walks and vendor MIB values under Advanced sections; normal operational interface, ARP, and MAC/FDB views remain first-class.

There is no schema or public REST contract change. Package release advances to `2.0.0-45` because shipped web/runtime source changed. Status remains `IMPLEMENTED_TESTING_DEFERRED`; NI-7 remains the feature baseline and Q-1 remains open.

**Release 45 qualification on the archive-derived workspace:** repository tests executed in four bounded groups total **221 passed / 8 skipped / 0 failed**; the eight skips are seven live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console regressions cover the Operations overview, single-surface Network Intelligence navigation, Automation Requests HTTP rendering, Device Collection guidance, and MIB purpose/advanced-library presentation. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because the executable is unavailable. The offline RPM builder emitted `netconfig-2.0.0-45.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `91cfea8b74a4c9b65472bafd59852513bf30a1adb9d87f5c6be3023e4a246efd`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.


## Baseline

- Release: **42 — Offline RPM Builder Integration**
- Application/RPM source identity: **`2.0.0-43`**
- Status: **`IMPLEMENTED_TESTING_DEFERRED`**
- Feature baseline: **NI-7 — L3/VRF Path & Route Dependency Intelligence** (`ni7-l3-route-1`)
- Roadmap: **no new development phase assigned**; Q-1 remains open qualification work

## Delivered implementation

- Campaign retry REST route corrected to read list-valued `form["wave"]`; route-level tests cover explicit and omitted wave.
- NI-1 through NI-7 and Enterprise Operations remain implemented in source.
- Release 41 campaign-retry correctness fix and HTTP regression coverage remain inherited.
- Release 43 adds the dependency-free deterministic offline RPM builder/verifier under `tools/rpm-builder/`.
- Git reproducibility qualification for the Release 43 candidate verifies twelve required executable paths at index mode `100755`.
- The offline helper RPM is reproducibility evidence only and is not a substitute for canonical AlmaLinux 10 package qualification.

## Qualification truth

- Release 43 Git fresh-clone candidate evidence: **218 passed / 7 skipped / 0 failed**.
- Release 43 archive-derived source evidence: **217 passed / 8 skipped / 0 failed**; the extra skip is the Git-index mode test because `.git` is absent.
- Legacy selftest, compileall, launcher compile, shell syntax and source-manifest checks are recorded as PASS for that frozen Release 43 candidate.
- Offline helper RPM reproducibility/verifier evidence is PASS for SHA-256 `0bc3abca0b3349593f67593930e9c8e1298cfe511a42d24d38f4f2d26babc7c2`; canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.
- Ruff `0.16.7`: **NOT_RUN**. mypy: **NOT_RUN**.
- Q-1 live PostgreSQL, OpenSSH/Net-SNMP, vendor/device/scale and AlmaLinux installed-runtime qualification: **DEFERRED / NOT_RUN**.
- Current all-Markdown truth sync verification: **40/40 Markdown PASS**, **217 passed / 8 skipped / 0 failed**, selftest **ALL PASS**, compileall/launcher/shell/CR checks **PASS**; Ruff remains **NOT_RUN**.

## Boundary

This baseline is not `TESTED` or `RELEASED`. Historical documents retain their original measured counts for provenance.
