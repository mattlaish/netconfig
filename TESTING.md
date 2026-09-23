# NetConfig Testing


## Release 46 regression

Runtime/UI source changed in Release 46 and was requalified on the Release 46 source workspace. Four bounded non-live groups total **222 passed / 1 skipped / 0 failed**, and the service-backed integration inventory contributes **7 skipped** explicit live prerequisites, for an effective **222 passed / 8 skipped / 0 failed**. The archive-only skip is the Git-index executable-mode check because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. The offline RPM was built twice byte-identically and independently verified. Ruff `0.16.7`, mypy, canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux, PostgreSQL live, and vendor-device live qualification remain `NOT_RUN` unless separately executed.

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.
## Historical 2026-09-18 Release 45 documentation-only design sync

This documentation sync records future site-resilience/distributed-collector and operator-UX decisions only. No runtime, schema, API, packaging script, or RPM identity is changed. Therefore the last executed Release 45 runtime evidence remains **221 passed / 8 skipped / 0 failed** with legacy selftest/compileall/package-shell evidence as previously recorded; Ruff `0.16.7`, mypy, and Q-1 live gates remain `NOT_RUN`/deferred where applicable. This docs-only sync must not be interpreted as new runtime qualification.



## Release 45 operator-UX regression

Required current regression includes: `/operations` task-oriented overview, no duplicate top-level Network Intelligence navigation, `/operations?tab=intents` HTTP 200, Device Collection guidance/advanced profile disclosure, MIB purpose/advanced-library presentation, SNMP raw walk/vendor values behind advanced disclosures, plus the complete repository suite. Live/deferred gates remain unchanged.

### Release 45 bounded regression result

Four bounded repository-test groups total **221 passed / 8 skipped / 0 failed**. The eight skips remain seven live/service prerequisites plus the archive-only Git-index executable-mode test. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution and mypy remain **NOT_RUN**.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.


## Historical Release 43 — Offline RPM Builder Integration

Release 43 adds `tools/rpm-builder/`, a deterministic dependency-free RPM emitter plus an independent offline verifier. The helper reads `packaging/netconfig.spec`, packages only the canonical NetConfig runtime payload, preserves executable/config ownership semantics, encodes lifecycle scriptlets and dependencies, and verifies RPM header digests, gzip/newc payload integrity, source-byte identity, modes, `CONFIG|NOREPLACE`, requirements, and scriptlets. `SOURCE_DATE_EPOCH=1789689600` is the deterministic default for this release. The same source and epoch must produce byte-identical RPMs. This helper is **not** the production qualification authority: canonical AlmaLinux 10 `rpmbuild`, `rpm -qp`, DNF install/upgrade, systemd restart/reboot, SELinux behavior, and remaining Q-1 live gates stay deferred until actually executed.
Release 43 candidate qualification from a real Git fresh clone is **218 passed / 7 skipped / 0 failed**; the seven skips are the existing PostgreSQL/backup and OpenSSH/Net-SNMP live-service gates. The same clone verifies **12/12 required executable paths at Git mode `100755`**, source-manifest integrity, legacy selftest **ALL PASS**, compile/launcher/package-shell checks, and a clean post-test worktree. An archive-derived source tree without `.git` is **217 passed / 8 skipped / 0 failed** because the Git-index mode test correctly skips. The offline builder produced `netconfig-2.0.0-43.el10.noarch.rpm` twice with identical SHA-256 `095b32b594b771e37e83c2cc89a27e9f87d8c5ae925d81ad94510083f0e612a1`; the independent verifier passed RPM header digest, compressed payload digest, gzip/newc parsing, payload/source byte identity, modes, `CONFIG|NOREPLACE`, dependencies, and lifecycle scriptlets. This remains offline evidence only; canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux is `NOT_RUN`.



## Release 41 corrective-hardening verification ledger

HTTP campaign-retry regression and repository/Git-mode hygiene focused coverage are included in the current suite. Final fresh-clone execution from the frozen Release 41 Git baseline is **213 passed / 7 skipped / 0 failed**. The seven skips remain the existing live PostgreSQL/backup and OpenSSH/Net-SNMP service-backed gates. The same fresh clone verifies **8/8 Git index modes = 100755**, `source-manifest.sha256`, legacy selftest **ALL PASS**, compileall, launcher `py_compile`, and packaging shell syntax, and returns to a clean worktree after cache removal. Actual Ruff `0.16.7` execution remains `NOT_RUN` on this isolated runner because the binary cannot be downloaded/installed; no source-side approximation is promoted to Ruff PASS.


## Historical Release 40 NI-7 verification ledger

NI-7 focused tests: **5 passed**. Full source regression before final packaging: **211 passed / 7 skipped / 0 failed**. Coverage includes same-VRF path traversal, explicit terminal route evidence, unresolved next-device fail-closed behavior, multipath ambiguity, distinct dependency-candidate preservation, alternate-route evidence, scoped API, Operations UI/RBAC, and no direct execution surface. The seven existing live/service skips remain deferred Q-1 evidence and are not Release 40 failures.

### Release 40 fresh-clone gate

A clean clone of the frozen Release 40 candidate commit executed the full repository test inventory in bounded groups: **211 passed / 7 skipped / 0 failed**. NI-7 focused **5 passed**. `source-manifest.sha256` / metadata checksums, 8/8 Git `100755` modes, legacy selftest, compileall, launcher compile and packaging shell syntax all passed. Cache cleanup restored a clean worktree. The seven skips remain the pre-existing PostgreSQL/backup and OpenSSH/Net-SNMP service-backed tests.

### Release 40 final delivery qualification

The frozen delivery surface is independently qualified. The full-source Git-archive ZIP contains **199 archive entries**, matches **181/181 Git-tracked files byte-for-byte**, and has **0** path-traversal entries, **0** symlinks, **0** cache/bytecode entries, **0** operational-text CR offenders, and **8/8** required executable files at mode `0755`; source and metadata manifests verify. From its clean extraction, the complete repository test inventory executes as **211 passed / 7 skipped / 0 failed**, with legacy selftest **ALL PASS** and compile/launcher/package-shell checks **PASS**. The clonable Git bundle reproduces the same commit, manifest and 8/8 Git `100755` modes and executes the same **211/7/0** regression plus selftest/compile with a clean post-test worktree. The `2.0.0-40` RPM build-source bundle has no traversal/symlink/cache entries, preserves all eight executable modes, verifies manifests/package identity, and passes **25/25** focused NI-7/repository-hygiene/Q-1 tests. Actual AlmaLinux RPM build/install and Q-1 live service/vendor gates remain `NOT_RUN`/deferred. The final archive SHA-256 is intentionally carried in external `.sha256` sidecars so the payload does not self-reference its own digest.

## Historical Release 39 Q-1 qualification ledger

Release 39 must be evaluated from a clean Git checkout. The local artifact runner can execute pytest/selftest/compile/shell, Git index modes, staged systemd unit syntax/hardening, and fail-closed qualification harness behavior. It cannot claim Ruff/mypy, real PostgreSQL, OpenSSH/Net-SNMP, or AlmaLinux installed-runtime PASS without those tools/services. `Q1_PRODUCTION_QUALIFICATION.md` records the exact gate matrix and exit semantics.

Current pre-final-package evidence: full repository **206 passed / 7 skipped / 0 failed**; Q-1 focused **12 passed**; legacy selftest **ALL PASS**; compileall/launcher `py_compile`/all packaging `bash -n`/workflow YAML parse/CR scan **PASS**; Git index executable modes **8/8 = 100755**; staged installed-filesystem `systemd-analyze verify` **PASS**. `q1-source-gates.sh` = exit `2` (`ruff` unavailable), `q1-qualify-postgres.sh` = exit `2` (`pg_dump` unavailable), `q1-qualify-almalinux.sh` = exit `20` (Debian 13 is not target), and `netconfig qualify` reports this runner not ready because required `ssh` is absent. None of those unavailable target/service gates is counted as PASS.


## Release 38 Git reproducibility qualification

The Git gate is now independent of archive metadata. CI inspects the tracked index mode (`git ls-files --stage`) for `usr/bin/netconfig` and all seven packaging scripts and requires `100755`. Candidate fresh-clone evidence: 8/8 Git modes `100755`; full pytest **204 passed / 7 skipped / 0 failed**; selftest **ALL PASS**; compileall, launcher `py_compile`, and packaging shell syntax **PASS**; worktree remained clean after tests. The local runner cannot install or execute Ruff/mypy, so those gates remain **NOT_RUN**, not PASS.


Ruff is pinned to `0.16.7` in `requirements-quality.txt` and CI; this runner still records Ruff as **NOT_RUN** because the executable cannot be installed/downloaded here.
## Release 34 / UI-1 verification matrix

Offline executed evidence:

- `tests/test_ui1_web_console.py`: **7 passed**;
- combined UI-1 + automation expansion + PH-1 + PH-2 + PH-3 + Q-1 focused suite: **73 passed**;
- full repository: **175 passed / 7 skipped**;
- legacy selftest: **ALL PASS**;
- compileall / launcher `py_compile` / packaging shell syntax: **PASS**;
- source CR offenders **0**, cache entries **0** after cleanup, symlinks **0**, required executable modes **7/7 = 0755**.

The seven skipped tests remain the explicit live/service-backed PostgreSQL and protocol integration gates. Ruff/mypy are `NOT_RUN` because those binaries are unavailable in this environment; absence is not PASS. UI-1 does not change the requirement for real PostgreSQL, AlmaLinux RPM/systemd, OpenSSH/Net-SNMP, NETCONF/RESTCONF/gNMI vendor/TLS, SMTP/O365, scale/load/failure, backup/restore/PITR and other Q-1 qualification.

### UI-1 candidate artifact evidence

Candidate `netconfig_ui1_release34_candidate_2026-09-13.zip` (SHA-256 `760cb9d411e54b991cc1c285e09fdd276c2364d8e4a497da6bd2d6d756e70d2a`) passed clean-extraction verification: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0** before testing; text CR offenders **0**; source/extracted byte identity **138/138 PASS**; payload and each of the three SHA manifests **133/133 PASS**; required executable modes **7/7 = 0755**. From the clean extraction, UI-1 focused **7 passed**, combined UI-1/automation/PH-1/PH-2/PH-3/Q-1 focused **73 passed**, full repository **175 passed / 7 skipped**, legacy selftest **ALL PASS**, and compileall/launcher `py_compile`/packaging shell syntax **PASS**. Ruff, mypy, `rpmbuild`, and PostgreSQL `pg_dump`/`pg_restore` remain **NOT_RUN** because the binaries are unavailable; none are counted as passing.


## Release 33 consolidated verification plan

Release 33 adds focused coverage in `tests/test_automation_expansion.py` for PH-4, NI-5, VM-1, NA-1, NA-2 and HA-1. Final evidence must run only after source/docs freeze and must include: focused expansion tests; PH-2/PH-3/Q-1 focused regressions; full pytest; legacy selftest; compileall and launcher py_compile; shell syntax; CR/cache/symlink/path hygiene; executable-mode checks; Ruff with the configured `E/F/W/B/UP` rule set when a real Ruff binary is available; mypy over the configured security/core plus Release 33 automation boundaries when mypy is available; then clean-extraction repetition against the delivery ZIP itself.

Ruff/mypy may be marked only `PASS` when the actual tools execute successfully. Tool absence is `NOT_RUN`, never PASS. Q-1 real PostgreSQL/AlmaLinux/systemd/OpenSSH/Net-SNMP/vendor/live SMTP gates remain separate and must not be inferred from offline tests.

> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.

## Historical Q-1 baseline qualification summary

- Historical Q-1 state: **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`).
- Historical feature baseline at Q-1 creation: PH-3 (`IMPLEMENTED_TESTING_DEFERRED`).
- Q-1 focused offline suite: **11 passed** before final artifact packaging.
- Full offline repository: **147 passed / 7 skipped** before final artifact packaging.
- Existing service skips: OpenSSH, Net-SNMP, PostgreSQL interface-history.
- New Q-1 service skips: real PostgreSQL multi-node claim/leadership, advisory-lock session-loss release, SQLite→PostgreSQL migration/sequence repair, and pg_dump/pg_restore recovery drill.
- Ruff/mypy: `NOT_RUN` here; tools absent and package installation failed because the environment has no external name resolution.
- PostgreSQL live gate: `NOT_RUN` here; `pg_dump`/`pg_restore` and PostgreSQL server/client tooling absent.
- AlmaLinux 10 RPM/systemd gate: `NOT_RUN` here; current host is Debian 13.

Clean Q-1 candidate `netconfig_qualification_q1_candidate_2026-09-12.zip` (SHA-256 `185039eadf8e8e63a8dad358df35f759a7a1f099d5fa6a3456a50e023920a2b1`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; source/extracted byte identity **125/125 PASS**; payload plus each SHA manifest **121/121 PASS**; required executable modes **7/7 = 0755**; extracted Q-1 focused **11 passed**; extracted full regression **147 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.

Required live Q-1 evidence before promotion: run `packaging/q1-source-gates.sh` in a Python 3.12 environment with Ruff/mypy, run `packaging/q1-qualify-postgres.sh` against disposable real PostgreSQL, and run `packaging/q1-qualify-almalinux.sh --install` on a disposable AlmaLinux 10 host with `NETCONFIG_Q1_ALLOW_INSTALL=1`. Preserve test logs and artifact hashes. Full PostgreSQL HA/PITR, vendor structured-protocol validation, live SMTP/O365, and representative vendor-device qualification remain separate deferred gates unless explicitly executed.

This file is the current canonical test ledger. Historical handover evidence remains in `TESTING_RESULT_2026-09-07.md`.

## Historical PH-3 final qualification summary

- Historical implementation at PH-3 close: **Platform Hardening PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`).
- Historical next action at that point was the roadmap / qualification review that selected Q-1.
- Current source regression before final artifact packaging: **136 passed / 3 skipped**; focused `tests/test_platform_hardening_ph3.py`: **22 passed**. Final selftest/compile/package/artifact evidence is recorded in `TESTING_RESULT_2026-09-12.md`.
- D.5 sections below are retained as chronological qualification evidence only; D.5 is not the active feature track.
- Ruff/mypy, service-backed integration, RPM install/runtime and representative live-vendor NI-1 qualification remain deferred.


## D.5 Phase 4B required gates

Repository/offline gates:

- Full pytest suite.
- Legacy `opt/netconfig/selftest.py` compatibility run.
- `python -m compileall` for application and tests.
- Incident focused tests: all Phase 4A lifecycle/security coverage plus reference-only evidence linking, allow-listed source validation, idempotent links, unavailable-source markers, immutable drift stamp pinning, timeline aggregation, additive schema, CLI parser, and JSON HTTP API evidence/timeline link/read/unlink.
- Source/package artifact extraction, required-path, archive CRC/path traversal/symlink, source-to-extracted checksum, and manifest verification.
- LF/CRLF repository hygiene regression.

Environment-dependent gates:

- Ruff and mypy when installed / GitHub Actions.
- OpenSSH scripted-device integration tier.
- Net-SNMP service integration tier.
- PostgreSQL integration tier.
- AlmaLinux 10 RPM build, inspect, install/upgrade and smoke test.
- Live built-in TLS / reverse-proxy API qualification.
- Real device qualification where later incident timeline sources depend on device behavior.

## Truth boundary

A repository test pass is not a live network or RPM qualification. Skipped service-backed tests and unavailable lint/type binaries must remain explicitly reported. Phase 4B status stays `IMPLEMENTED_TESTING_DEFERRED` until the relevant deferred gates are actually executed.


## 2026-09-11 Phase 4B executed results

- `PYTHONPATH=opt/netconfig pytest -q`: **33 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig pytest -q tests/test_incidents.py`: **14 passed**.
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall -q opt/netconfig/netconfig tests`: **PASS**.
- `bash -n` on RPM packaging scripts and launcher: **PASS**.
- Repository operational-text CR scan: **0 offenders**.
- End-to-end CLI incident smoke: create/list **PASS** (`INC-2026-000001`, HIGH, OPEN).
- Ruff: **NOT RUN** (binary/module unavailable in this environment).
- mypy: **NOT RUN** (binary/module unavailable in this environment).
- OpenSSH/Net-SNMP/PostgreSQL integration: **SKIPPED / NOT RUN**, gated by `NETCONFIG_INTEGRATION=1` plus services.
- AlmaLinux RPM build/install and real-device/network qualification: **NOT RUN**.


## 2026-09-11 Phase 4B artifact packaging integrity gate

The candidate FULL source ZIP was cleanly extracted and independently validated: archive CRC PASS; path traversal 0; symlink entries 0; required paths present; source-to-extracted file set and SHA-256 identity PASS; release/per-file manifests PASS; critical-file size and launcher/script header checks PASS; extracted compileall/launcher pycompile/packaging shell syntax PASS; extracted pytest **33 passed / 3 skipped**; extracted legacy selftest **ALL PASS**; operational-text CR offenders 0.


## 2026-09-11 roadmap-structure refresh verification

- Documentation-only roadmap/handover reconciliation; runtime source, database schema and API behavior are unchanged from D.5 Phase 4B.
- Re-ran full repository pytest after the Markdown changes: **33 passed, 3 skipped**.
- Re-ran legacy selftest: **RESULT: ALL PASS**.
- Re-ran application/tests compileall, launcher py_compile and RPM packaging shell syntax: **PASS**.
- Operational-text CR scan: **0 offenders**.
- Ruff/mypy and service-backed/live qualification remain **NOT RUN / deferred** exactly as before.


## D.5 Phase 4C required gates

Repository/offline gates:

- Full pytest suite and focused incident/case-export suite.
- Legacy `opt/netconfig/selftest.py` compatibility run and `python -m compileall`.
- Additive `incident_case_exports` schema coverage and `incident:export` minimum-role enforcement.
- Case export structure, selected-bundle enforcement, missing-linked-bundle behavior, path/traversal checks and 32-bundle/512-MiB bounds.
- Reference-only export regression proving raw external audit/syslog/compliance/config payloads are not copied into case indexes.
- Embedded diagnostic bundle byte identity plus manifest and `manifest.sha256` verification.
- Durable export archive tamper detection: size/SHA mismatch fails closed before download and appends an integrity-failure audit event.
- API create/list/download authorization and audit coverage.
- Final source/package extraction, required-path, archive CRC/path traversal/symlink, source-to-extracted SHA and manifest verification.

Environment-dependent gates remain Ruff/mypy, OpenSSH/Net-SNMP/PostgreSQL integration, AlmaLinux RPM build/install, live TLS/reverse-proxy and representative real-device qualification.

## 2026-09-11 Phase 4C executed results

- `PYTHONPATH=opt/netconfig pytest -q`: **39 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig pytest -q tests/test_incidents.py`: **20 passed**.
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall -q opt/netconfig/netconfig tests`: **PASS**.
- Ruff/mypy and service-backed/live qualification remain **NOT RUN / deferred** until separately executed.

Phase 4C remains `IMPLEMENTED_TESTING_DEFERRED`; repository/offline success is not a live network/RPM qualification.


## 2026-09-11 Phase 4C artifact packaging integrity gate

The Phase 4C FULL source candidate was cleanly extracted and independently validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; required source/test/packaging/documentation paths **PASS**; source-to-extracted file set and SHA-256 identity **94/94 PASS**; `RELEASE_MANIFEST.json` payload **90/90 PASS**; all three per-file SHA manifests **90/90 PASS**; critical-file size and launcher/script header checks **PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **39 passed / 3 skipped**; extracted incident/case suite **20 passed**; extracted legacy selftest **ALL PASS**; operational-text CR offenders **0**.


## D.5 Phase 4D required gates

- external Ed25519 signer key discovery and systemd-credential precedence;
- reject group/world-readable, symlink/non-regular, oversized and non-Ed25519 private keys;
- signed diagnostic and support-case manifest creation;
- extraction-free archive/path/link/unmanifested-file validation;
- manifest and payload SHA-256/size verification;
- signature verification and independent trust-pin semantics;
- trust-pin mismatch fail-closed for signed case verification/download;
- unsigned legacy evidence compatibility plus explicit/global signing-required fail-closed behavior;
- additive migration of Phase 4C export metadata;
- scoped REST signing status/verify paths and verification audit evidence;
- full repository regression and final extracted-artifact packaging gate.

## 2026-09-11 Phase 4D executed results

- `PYTHONPATH=opt/netconfig pytest -q`: **49 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig pytest -q tests/test_evidence_signing.py`: **10 passed**.
- legacy `selftest.py`: **RESULT: ALL PASS**.
- compileall: **PASS**.
- launcher py_compile: **PASS**.
- packaging shell syntax: **PASS**.
- UTF-8 operational-text CR offenders: **0**.
- Ruff/mypy: **NOT RUN** in the current environment.

Final extracted-artifact evidence is recorded after the final Phase 4D ZIP gate.


### Phase 4D artifact delivery gate

A clean candidate FULL source ZIP was independently extracted and validated before final repackaging: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **96/96 PASS**; `RELEASE_MANIFEST.json` payload **92/92 PASS**; all three per-file SHA manifests **92/92 PASS**; required source/test/packaging/documentation files **PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **49 passed / 3 skipped**; extracted Phase 4D signing suite **10 passed**; extracted legacy selftest **ALL PASS**; UTF-8 CR offenders **0**.


## D.5 Phase 4E required gates

- trace session lifecycle, TTL expiry and event/metadata-byte budget enforcement;
- sensitive CLI command redaction without secret-derived hashes;
- SSH trace callback must not persist device output;
- SNMP UDP trace must not persist request/response BER bodies or community/auth material;
- Incident `protocol_trace` linkage/timeline resolution;
- support-case and diagnostic-bundle sanitized trace inclusion;
- `trace:read` / role-gated `trace:capture` REST lifecycle;
- historical Phase 4E provider-not-implemented behavior is superseded by PH-3; structured trace start now covers NETCONF/RESTCONF/gNMI while retaining capture budgets;
- full regression plus final extracted-artifact source/manifest verification.

## 2026-09-11 Phase 4E executed results

- `PYTHONPATH=opt/netconfig pytest -q`: **59 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig pytest -q tests/test_protocol_trace.py`: **10 passed**.
- legacy `selftest.py`: **RESULT: ALL PASS**.
- compileall: **PASS**.
- launcher py_compile and packaging shell syntax: **PASS**.
- Ruff/mypy: **NOT RUN** in the current environment.
- OpenSSH/Net-SNMP/PostgreSQL service-backed integration and live-device/RPM qualification remain deferred.


### Phase 4E artifact delivery gate

The clean FULL source candidate was independently extracted and validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **98/98 PASS**; `RELEASE_MANIFEST.json` payload **94/94 PASS**; all three per-file SHA manifests **94/94 PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **59 passed / 3 skipped**; extracted Phase 4E protocol-trace suite **10 passed**; extracted legacy selftest **ALL PASS**.


## D.5 Phase 4F required gates

- Incident register/detail render for authenticated users;
- viewer remains read-only and cannot create Incidents or download support-case exports;
- operator lifecycle/evidence operations preserve existing validation/audit behavior;
- trace start/event display/stop workflow and cross-Incident stop rejection;
- diagnostic bundle link plus support-case create/download workflow;
- CSRF rejection for browser mutations;
- HTML escaping for Incident-controlled title/description/tags;
- full regression plus extracted-artifact source/manifest verification.

## 2026-09-11 Phase 4F executed results

- `PYTHONPATH=opt/netconfig pytest -q`: **64 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig pytest -q tests/test_incident_web.py`: **5 passed**.
- legacy `selftest.py`: **RESULT: ALL PASS**.
- compileall, launcher py_compile and packaging shell syntax: **PASS**.
- Ruff/mypy: **NOT RUN** in the current environment.
- OpenSSH/Net-SNMP/PostgreSQL service-backed integration, live-device and RPM qualification remain deferred.

Final extracted-artifact evidence is recorded after the Phase 4F ZIP gate.

### Phase 4F artifact delivery gate

The clean candidate FULL source ZIP was independently extracted and validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **99/99 PASS**; `RELEASE_MANIFEST.json` payload **95/95 PASS**; all three per-file SHA manifests **95/95 PASS**; required source/test/packaging/documentation files **PASS**; critical-file size and launcher/script header checks **PASS**; extracted compileall/launcher py_compile/packaging shell syntax **PASS**; extracted pytest **64 passed / 3 skipped**; extracted Phase 4F Web Console tests **5 passed**; extracted legacy selftest **ALL PASS**; UTF-8 CR offenders **0**.


## D.5 Closeout qualification review — 2026-09-11

Executed locally on Python 3.13.5: repository pytest **67 passed / 3 skipped**, `tests/test_d5_closeout.py` **3 passed**, legacy `selftest.py` **ALL PASS**, compileall **PASS**, launcher py_compile **PASS**, packaging shell syntax **PASS**, and UTF-8 CR scan **0 offenders**. The three integration tests remain skipped because the required OpenSSH, Net-SNMP and PostgreSQL services/binaries are not present. Ruff, mypy and rpmbuild are not installed in this environment, so those gates are **NOT RUN**. No representative live network devices were available. D.5 remains `IMPLEMENTED_TESTING_DEFERRED`.


### D.5 closeout candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; source/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## Post-closeout roadmap documentation refresh — 2026-09-11

Documentation-only change: clarified D.5 vs historical Slice E, updated canonical Current/Next metadata, and repaired stale handoff/source-release labels. No runtime/API/schema behavior changed. Re-run repository regression and artifact gate before publishing the refreshed FULL source baseline.

### Post-closeout roadmap refresh executed regression

After the documentation-only roadmap/handoff reconciliation: full pytest **67 passed / 3 skipped**; closeout-focused `tests/test_d5_closeout.py` **3 passed**; legacy selftest **ALL PASS**; compileall, launcher py_compile and packaging shell syntax **PASS**; UTF-8 CR offenders **0**. Ruff/mypy remain **NOT RUN** because binaries are unavailable. Runtime/API/schema behavior was not modified.

### Roadmap-refresh candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; stage/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; required files **PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## Source baseline packaging repair gate — 2026-09-11

The repaired delivery must preserve executable mode `0755` for `usr/bin/netconfig`, `packaging/build-rpm.sh`, `packaging/inspect-rpm.sh`, and `packaging/smoke-installed.sh`. After clean extraction, direct execution of `./packaging/build-rpm.sh` must reach the script body rather than fail with shell status 126/`Permission denied`; the build itself may still stop later because `rpmbuild` is unavailable in this environment. Active `packaging/README.md` and `opt/netconfig/INSTALL.md` examples must reference current RPM source Release `2.0.0-24`. Historical release references in changelog/engineering ledger entries are not rewritten.

### Repaired source-baseline candidate artifact result

Clean extraction: ZIP CRC **PASS**; traversal **0**; symlinks **0**; stage/extracted SHA identity **101/101 PASS**; release-manifest payload **97/97 PASS**; three SHA manifests **97/97 PASS**; required files **PASS**; CR offenders **0**. Required executable paths retain **0755** both in ZIP metadata and after extraction. Direct `./packaging/build-rpm.sh` no longer fails permission checks: it reaches the script and exits **2** because `rpmbuild` is not installed. Active RPM build/install examples reference `2.0.0-24`. Extracted pytest **67 passed / 3 skipped**; closeout-focused **3 passed**; selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**.


## Network Intelligence NI-1 qualification — 2026-09-11

Required NI-1 coverage: modern IPv4/IPv6 `ipNetToPhysicalTable` normalization; Q-BRIDGE FDB-ID/VLAN/bridge-port mapping; shared-FDB ambiguity; additive schema; LLDP/CDP transit suppression; multiple-direct candidate ambiguity; stale evidence; `endpoint:read` CLI/API contract; full repository regression; legacy selftest; compileall; launcher/shell syntax; source-baseline/archive integrity.

Pre-packaging execution: focused `tests/test_network_intelligence.py` **8 passed**; full pytest **75 passed / 3 skipped**. The three skips remain the existing OpenSSH, Net-SNMP and PostgreSQL service-backed integration tests. Final extracted-artifact evidence is appended after the candidate ZIP gate.

### NI-1 candidate artifact delivery gate

Clean candidate extraction independently passed: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; stage/extracted file-set and SHA-256 identity **103/103 PASS**; `RELEASE_MANIFEST.json` payload **99/99 PASS**; all three per-file SHA manifests **99/99 PASS**; required executable paths retain **0755** in ZIP metadata and extracted filesystem; direct `./packaging/build-rpm.sh` reaches the script body and exits **2** only because `rpmbuild` is unavailable; active RPM build/install docs use `2.0.0-25`; UTF-8 CR offenders **0**. Extracted pytest **75 passed / 3 skipped**; extracted NI-1 focused tests **8 passed**; extracted legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.


## NI-1 all-Markdown synchronization gate — 2026-09-11

Historical NI-1 gate requirement (superseded): every Markdown file carried the then-canonical NI-1 state; this is chronology only and does not override the PH-2 current-state marker above.

Workspace result: Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**.

Final extracted-artifact evidence is recorded after the refreshed FULL source ZIP gate.

## Network Intelligence NI-2 executed tests — 2026-09-11

Source workspace: `pytest -q` => **83 passed / 3 skipped**. Focused `tests/test_network_intelligence_ni2.py` => **8 passed**.

Focused coverage includes LLDP/ENTITY-MIB chassis identity normalization, hex-MAC normalization, unique and conflicting managed-neighbour resolution, bounded cycle-safe and first-hop-port-scoped downstream traversal, additive NI-2 schema, bounded Manager identity collection, CLI parsing, and REST identity/impact endpoints. The same three service-backed OpenSSH/Net-SNMP/PostgreSQL integration tests remain skipped unless the external services are provided.

Deferred qualification remains: representative vendor LLDP/ENTITY-MIB/IF-MIB behavior, large-topology scale/retention calibration, real Net-SNMP service integration, Ruff/mypy, and AlmaLinux RPM build/install/runtime validation.

### NI-2 candidate artifact gate

Candidate FULL source artifact passed clean extraction with **104/104** stage-to-extracted file identity, **100/100** `RELEASE_MANIFEST.json` payload verification, all three SHA manifests **100/100**, exact hidden paths (`.gitattributes`, `.gitignore`, `.github/workflows/ci.yml`), four executable launcher/helper modes `0755` in ZIP metadata and extracted filesystem, zero traversal/symlink/cache/CR findings, extracted pytest **83 passed / 3 skipped**, NI-2 focused **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `./packaging/build-rpm.sh` executes and exits 2 only because `rpmbuild` is unavailable.

NI-2 prefinal artifact reproduced the clean-extraction gate after candidate evidence was embedded: **100/100** release payload PASS, executable modes `0755`, extracted **83 passed / 3 skipped**, focused NI-2 **8 passed**, selftest **ALL PASS**. Final artifact validation is performed on the final ZIP without further modification.

## Network Intelligence NI-3 executed tests — 2026-09-11

- focused `tests/test_network_intelligence_ni3.py`: **8 passed**
- full repository: **91 passed / 3 skipped**
- legacy selftest: **ALL PASS**
- compileall / launcher py_compile / packaging shell syntax: **PASS**
- skipped gates remain the service-backed OpenSSH, Net-SNMP and PostgreSQL integration tests
- real SNMP trap sender/vendor qualification, authenticated SNMPv3 trap receive, AlmaLinux RPM build/install and live dependency suppression validation remain deferred

### NI-3 candidate artifact evidence

Clean system-unzip candidate validation passed: 107/107 full-file identity; 103/103 Release payload and three SHA manifests; hidden paths exact; four executable files `0755`; CRC/traversal/symlink/cache/CR gates PASS; extracted **91 passed / 3 skipped**, NI-3 **8 passed**, selftest/compile/launcher/shell PASS. RPM build remains NOT_RUN because `rpmbuild` is unavailable.


## Network Intelligence NI-4 executed tests — 2026-09-11

- Full repository: **99 passed / 3 skipped**.
- Focused `tests/test_network_intelligence_ni4.py`: **8 passed**.
- Legacy `opt/netconfig/selftest.py`: **ALL PASS**.
- `compileall`, launcher `py_compile`, packaging shell syntax: **PASS**.
- Focused coverage includes severity promotion, maintenance suppression with event preservation, dedup-to-same-alert, acknowledge/resolve auditing, bounded retry/backoff, durable scheduled reports, scoped API/CLI and Web viewer/operator RBAC.
- Live SMTP delivery, OpenSSH/Net-SNMP/PostgreSQL service integration, vendor trap qualification, AlmaLinux RPM/systemd validation, Ruff and mypy remain **NOT RUN / DEFERRED** where unavailable.


### NI-4 candidate artifact evidence

Candidate `netconfig_network_intelligence_ni4_candidate_2026-09-11.zip` SHA-256 `17ed1297a863eaca2eeb4a92f5bddcf3ab120804d2526c63339bda79ae1569e3` passed clean system-unzip validation: **109/109** artifact files present, **105/105** Release payload entries and each of the three SHA manifests verified, exact hidden paths retained, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the NI-4/PH-1/Release-28 current-state pointer. Extracted regression: **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## PH-1 Web-console Structural Hardening verification

- Repository pytest: **105 passed / 3 skipped**.
- PH-1 focused tests: **6 passed**.
- Legacy selftest: **ALL PASS**.
- compileall / launcher py_compile / packaging shell syntax: **PASS**.
- Structural gate: `web.py` **3,767 lines / 235,124 bytes**, below the PH-1 gate of 4,000 lines / 240 KB.
- CSP gate: nonce-based script/style element policy; `script-src-attr 'none'`; `style-src-attr 'none'`; rendered login response contains no inline event or style attributes.
- Deferred: Ruff/mypy unavailable, real OpenSSH/Net-SNMP/PostgreSQL services, live browser matrix, AlmaLinux RPM/systemd and representative live-device qualification.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## Platform Hardening PH-2 test evidence — 2026-09-11

Workspace evidence before packaging:

- `PYTHONPATH=opt/netconfig pytest -q tests/test_platform_hardening_ph2.py` → **9 passed**.
- `PYTHONPATH=opt/netconfig pytest -q` → **114 passed / 3 skipped**.
- Skips remain the existing service-backed OpenSSH, Net-SNMP, and PostgreSQL integration gates.

PH-2 focused coverage includes quoted-qmark-safe SQL translation, SQLite upsert compatibility translation, PostgreSQL schema type conversion, fake-driver schema bootstrap/readiness, `FOR UPDATE SKIP LOCKED` worker claiming, advisory-lock scheduler leadership, SQLite single-claim behavior, protected pre-vault PostgreSQL password-file handling, PostgreSQL parameter construction without persisted passwords, and the storage CLI surface.

Important truth boundary: fake-driver contract tests demonstrate generated SQL and control-plane behavior but are **not** live PostgreSQL qualification. A real PostgreSQL service, concurrency/HA/failover, migration drill, backup/restore, and packaged psycopg environment remain required external gates.

### PH-2 candidate artifact integrity gate

Candidate SHA-256 `6dfd6e554b08883c51a6f268bbe604bf95cc7819dad8f4bda6f023d688807d21`: ZIP CRC PASS; path traversal 0; symlinks 0; 114/114 stage/extracted byte identity; 110/110 Release payload and each SHA manifest; hidden paths exact; four executable files 0755 after system unzip; 19/19 Markdown state PASS; cache/CR 0. Extracted pytest 114 passed / 3 skipped; PH-2 focused 9 passed; selftest ALL PASS; compileall/launcher/package shell syntax PASS; direct `build-rpm.sh` rc=2 solely because `rpmbuild` is unavailable.


## Platform Hardening PH-3 gates — 2026-09-12

Executed before final packaging:

- repository pytest: **136 passed / 3 skipped**;
- focused `tests/test_platform_hardening_ph3.py`: **22 passed**;
- PH-1 structural split/CSP regression remains covered by the full suite;
- protocol registry/capability model marks NETCONF/RESTCONF/gNMI implemented;
- host, profile, RESTCONF path/query, typed gNMI path, and production TLS validation;
- NETCONF server hello/capability negotiation, fixed `<get>` / `<get-config>`, advertised-datastore fail-closed handling, response hard limits, DTD/entity/depth-safe XML parsing, and base-1.1-only fail-closed behavior;
- RESTCONF host-meta/root discovery, content-type validation, bounded malformed/oversized JSON/XML rejection, vault-only credential use, CA/mTLS configuration, and lab-gated insecure TLS;
- internal approval-gated RESTCONF subtree replace with pre-read, post-read verification and rollback-to-pre-image behavior on failed verification;
- gNMI Capabilities, Get, typed paths, ONCE Subscribe, deadline timeout, malformed output rejection, 16 MiB response rejection, mode-0600 ephemeral config, vault-resolved mTLS, secret-free argv and error redaction;
- explicit structured-failure CLI fallback only when configured;
- metadata-only protocol traces and secret redaction;
- profile rename/delete behavior;
- CLI/scopes and Web/API RBAC surfaces, including capabilities/state read endpoints and operator-or-higher protocol writes.

The three skipped integration tests remain intentional deferred service-backed gates for OpenSSH, Net-SNMP, and PostgreSQL. They must not be described as passing.

Still required/not run: real NETCONF/RESTCONF/gNMI devices, vendor-specific Cisco/Juniper/Arista/Huawei behavior, NETCONF 1.1-only/chunked peers, real TLS/mTLS interoperability, packaged `gnmic`, production credential rotation, real PostgreSQL multi-node/concurrency/HA/failover/PITR/backup-restore, service-backed OpenSSH/Net-SNMP, AlmaLinux RPM/systemd, Ruff, mypy, scale/load/failure qualification, and live SMTP/O365.

## PH-3 artifact evidence — 2026-09-12

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

The delivered FULL ZIP is rebuilt after this evidence is recorded and is independently re-extracted/retested before handoff. PH-3 remains `IMPLEMENTED_TESTING_DEFERRED` regardless of offline pass counts until applicable live/service-backed qualification is executed.

## Release 33 consolidated verification result

Status remains `IMPLEMENTED_TESTING_DEFERRED`. Final source-tree evidence before artifact creation:

```text
automation + repo hygiene focused   23 passed
PH-2 focused                         9 passed
PH-3 focused                        22 passed
Q-1 focused                         11 passed
full pytest                        168 passed / 7 skipped
legacy selftest                    RESULT: ALL PASS
compileall                         PASS
launcher py_compile                PASS
packaging shell syntax             PASS
source text CR offenders            0
cache entries after cleanup         0
symlinks                            0
historical E701-style suites        0
required executable modes           7/7 = 0755
Ruff                               NOT_RUN (binary unavailable)
mypy                               NOT_RUN (binary unavailable)
```

The seven skips remain explicit live/service-backed gates: four real PostgreSQL/Q-1 gates and three protocol/service-backed integrations.


During the consolidated focused run, tests exposed and implementation fixed: (1) NA-2 allowed resume with unresolved failed targets and lacked its advertised explicit retry service method; (2) PH-4 gNMI typed Set accidentally changed the PH-3 generic capability contract; and (3) a hygiene refactor moved Web query parsing below the API dispatch. All affected focused suites are green after correction.

Candidate artifact evidence: Clean Release 33 candidate `netconfig_release33_candidate_2026-09-12.zip` (SHA-256 `d03720a411b796458747f7d8976a8fa01f4f40859b5e51341ef031aaa343f538`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; text CR offenders **0**; source/extracted byte identity **132/132 PASS**; payload plus each SHA/release manifest **128/128 PASS**; required executable modes **7/7 = 0755**. From the clean extraction: Release 33 focused **23 passed**, PH-2 **9 passed**, PH-3 **22 passed**, Q-1 **11 passed**, full repository **168 passed / 7 skipped** in the isolated full-suite rerun, legacy selftest **ALL PASS**, and compileall/launcher py_compile/packaging shell syntax **PASS**. A first command that chained all suites hit the execution-tool timeout after full pytest reached ~82%; that interrupted run is not counted as PASS. The same candidate full suite was then rerun alone and completed cleanly (**168 passed / 7 skipped in 22.90s**).


# Historical Architecture Planning Snapshot — PH vs NI

> The status values in this retained planning snapshot describe an earlier roadmap point. They are **not current work assignments**. PH-5/PH-6 and NI phases were subsequently implemented as recorded in later release sections; current status and sequencing are controlled by `ROADMAP.md`, where no new development phase is presently assigned.

## PH — Platform Hardening / Safe Device Change

PH answers:

> How do we safely change network devices?

### PH-4 — Structured Configuration Transaction Engine

Status: `IMPLEMENTED_IN_SOURCE / COMPLETION_HARDENING`

Scope:

- Structured change lifecycle
- Approval binding
- Pre-read snapshot
- Typed NETCONF / RESTCONF / gNMI operations
- Post-change verification
- Rollback and recovery workflow
- Audit evidence and provenance
- Confirmed-commit transaction handling

### PH-5 — Intent / Desired State Automation

Status: `PLANNED`

Scope:

- Desired state model
- Current vs desired comparison
- Drift detection
- Change plan generation
- Intent validation
- Approval workflow integration
- Remediation through PH-4 transaction engine

### PH-6 — Distributed Execution / HA

Status: `PLANNED`

Scope:

- Worker execution model
- Distributed queue
- Execution ownership
- Leader/fencing model
- Failover recovery
- Large-scale change orchestration
- Multi-node reliability


# NI — Network Intelligence

NI answers:

> What exists in the network and what is happening?

## NI-1 — Endpoint Location Correlation

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- IP → MAC correlation
- MAC → VLAN mapping
- VLAN → Switch port mapping
- Endpoint location discovery
- Q-BRIDGE FDB correlation
- Neighbor table correlation

Example:

```
IP
 |
MAC
 |
VLAN
 |
Switch Port
```

## NI-2 — Topology Identity

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- LLDP discovery
- CDP handling
- Device identity
- Chassis identity
- Interface identity
- Neighbor relationship
- Downstream impact traversal

## NI-3 — Network Events

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- SNMP Trap
- Syslog
- Link events
- Authentication events
- Reachability events
- Event normalization

## NI-4 — Alert Lifecycle

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- Alert promotion
- Severity handling
- Acknowledge workflow
- Resolve workflow
- Maintenance suppression
- Notification workflow

## NI-5 — Telemetry

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- SNMP polling
- gNMI telemetry
- Streaming metrics
- Interface statistics
- CPU/memory/environment telemetry
- Time-series storage
- Trend analysis
- Performance baseline

## NI-6 — Network Analytics / Operational Intelligence

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

### Auto Seed Discovery

- Seed device input
- Credential selection
- Discovery start workflow

### Full Network Crawl

- LLDP/CDP neighbor crawling
- Discovery queue
- Visited device tracking
- Crawl depth control
- Rate limiting
- Failure handling

### Topology Database

Nodes:

- Device
- Interface
- Link
- VLAN
- VRF
- Subnet
- Endpoint

Edges:

- CONNECTED_TO
- ATTACHED_TO
- CARRIES
- ROUTES_TO

### Unified L2/L3 Topology

- MAC path
- VLAN path
- IP path
- VRF path
- Routing relationship

### Topology Visualization

- Interactive topology graph
- Device map
- Link status
- VLAN view
- VRF view
- Path tracing
- Impact highlighting


## Release 35 PH-4 Completion Hardening

- NETCONF confirmed-commit lifecycle state model added.
- Recovery evidence schema integrated as transaction evidence boundary.
- PH-4 regression coverage added.
- Final qualification remains IMPLEMENTED_TESTING_DEFERRED until executed.


# PH-5 Intent / Desired State Automation

Status: IMPLEMENTED_TESTING_DEFERRED

Scope: DesiredState, Intent lifecycle, revisions, drift detection, Change Plan generation, PH-4 transaction integration boundary, approval and audit linkage.


# PH-5 API and Operations Surface

Status: IMPLEMENTED_TESTING_DEFERRED

Added PH-5 API helpers, intent workflow surface, and Web Console Intent Automation entry point. Device changes remain delegated to PH-4 transaction workflow.


## PH-6 Distributed Execution / HA
Status: IMPLEMENTED_TESTING_DEFERRED

## NI-6.4 Failure Risk validation — 2026-09-16

Status remains `IMPLEMENTED_TESTING_DEFERRED`.

Executed offline:

- NI-6.3 capacity + NI-6.4 focused analytics: **9 passed**.
- Full repository with `PYTHONPATH=.:opt/netconfig pytest -q`: **192 passed / 7 skipped / 0 failed**.
- Legacy `opt/netconfig/selftest.py`: **ALL PASS**.
- Python `compileall`: **PASS**.

The seven skips remain the existing live/service-backed PostgreSQL backup/restore and protocol integration gates. Q-1 source gate/Ruff remains explicitly deferred and is `NOT_RUN`, not PASS. Real vendor telemetry, real failure scenarios, production-scale calibration, and live infrastructure qualification remain deferred.



NI-6.6 Health Dashboard: IMPLEMENTED_TESTING_DEFERRED

## 2026-09-16 — NI-6 Enterprise Operations hardening

Added `tests/test_analytics_enterprise_workflow.py` covering durable insight lifecycle, managed directional impact, operator UI, viewer read-only behavior, API scopes and persisted API mutations. Source tree after hygiene repair: **202 passed / 7 skipped / 0 failed**. Legacy selftest: **ALL PASS**. Compileall, launcher py_compile and packaging shell syntax: **PASS**. Required executable modes: **7/7 = 0755**. Q-1/Ruff remains **NOT_RUN** by explicit deferral. Final artifact evidence is recorded in `VALIDATION_SUMMARY.md` after clean-extraction repetition.

## NI-6 Enterprise Operations qualification — 2026-09-16

Source: 202 passed / 7 skipped / 0 failed. Clean extraction: 202 passed / 7 skipped / 0 failed. Selftest ALL PASS. CRC, traversal, symlink, cache, CR, executable modes, `source-manifest.sha256` and internal metadata checksum gates PASS. Q-1 Ruff/mypy and live/service-backed gates remain NOT_RUN/deferred.

## Release 37 RPM installation hardening — 2026-09-16

Required source-side checks: repository regression, compileall, `bash -n` on every packaging shell script, Release 37 package identity consistency, install helper fail-closed behavior on non-AlmaLinux systems, cache/CRLF/mode hygiene, and source-manifest verification. The binary RPM build, RPM payload inspection, systemd installed-runtime smoke, and restart test require AlmaLinux 10 and remain `NOT_RUN` when executed only on the Debian artifact runner.

### RPM install v3 clean-artifact evidence

The candidate full-source archive was clean-extracted and requalified: `175/175` full-file byte identity, source/metadata manifests PASS, 8/8 required executable modes at 0755, zero cache/symlink/path-traversal/CR findings, `202 passed / 7 skipped / 0 failed`, legacy selftest `ALL PASS`, packaging shell syntax PASS, and the installer correctly refused a Debian host with exit 20. AlmaLinux binary RPM build/install/restart remains `NOT_RUN` and is not promoted by these offline results.

## Release 40 NI-7 verification

Focused NI-7 tests: **5 passed**. Full source regression before packaging: **211 passed / 7 skipped / 0 failed**. NI-7 coverage includes VRF isolation, explicit terminal routes, unresolved next-device fail-closed behavior, multipath ambiguity, preservation of distinct route dependency candidates, alternate-route evidence, analytics API scope/operator boundary, Operations UI/RBAC, and no direct execution surface. The seven existing service-backed skips remain four PostgreSQL/backup gates and three OpenSSH/Net-SNMP protocol-service gates. Q-1 live qualification is deliberately deferred.

### Release 40 fresh-clone qualification

A clean clone from the Release 40 candidate commit reproduced **8/8 Git index/worktree executable modes**, verified `source-manifest.sha256` and `SHA256SUMS`, completed **211 passed / 7 skipped / 0 failed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell/workflow-YAML checks **PASS**, and returned to a clean Git worktree after test-cache removal. The seven service-backed skips remain deferred Q-1 gates.

## Release 41 documentation truth sync verification

The documentation-only sync was revalidated against the unchanged Release 41 runtime source. Repository non-live tests remain **213 passed / 0 failed**; the seven service-backed PostgreSQL/backup/OpenSSH/Net-SNMP tests remain **skipped**, for an effective Git-checkout total of **213 passed / 7 skipped / 0 failed**. The full-source documentation-sync ZIP is expected to report **212 passed / 8 skipped / 0 failed** because `.git` is intentionally absent and `test_required_git_index_executables_are_100755` therefore skips.

Artifact executable-mode qualification uses a POSIX mode-preserving extractor (`unzip`) plus direct ZIP external-mode inspection. On this runner, Python `zipfile.extractall()` did not restore UNIX executable bits even though the ZIP central-directory metadata correctly recorded `0755`; that extraction method is therefore not used as executable-mode evidence.
## Documentation truth-sync gate — 2026-09-18

This documentation-only maintenance pass covers all 40 Markdown files. Required checks are: every Markdown file carries an explicit current-roadmap or historical pointer; `DOCUMENTATION_STATUS.md` inventories all 40 files; Q-1 is classified current/maintained; current docs identify Release 43 / `2.0.0-43`, NI-7 as the feature baseline, and no assigned next development phase; historical evidence remains labeled as chronology. This gate does not convert Ruff/mypy, AlmaLinux RPM/systemd/SELinux, PostgreSQL, protocol-service, vendor/device, routing/VRF, or scale gates into PASS.

Executed after the Markdown sync: documentation truth scan **PASS (40/40 files)**; archive-style repository regression **217 passed / 8 skipped / 0 failed**; legacy selftest **ALL PASS**; compileall, launcher `py_compile`, shell syntax and operational CR scan **PASS**. `ruff --version` could not be executed because `ruff` is not installed, so `ruff_0_16_7_actual_execution = NOT_RUN`.
### Documentation-sync final artifact gate

Final artifact gate using mode-preserving `unzip`: ZIP CRC **PASS**; source-to-extracted byte identity **190/190 PASS**; Markdown truth markers/inventory **40/40 PASS**; required executable modes **12/12 = 0755**; path traversal **0**; symlinks **0**; cache/pyc/pytest-cache entries **0**; operational CR offenders **0**; `source-manifest.sha256` **PASS**; `SHA256SUMS` **PASS**; extracted pytest **217 passed / 8 skipped / 0 failed**; extracted legacy selftest **ALL PASS**; extracted compileall / launcher `py_compile` / shell syntax **PASS**. Ruff `0.16.7` remains **NOT_RUN** because the executable is unavailable.

Delivery artifact: `netconfig-netconfig-2.0.0-43-sidebar-theme-refresh-v14.zip`. This remains Release 43 / `2.0.0-43`; the gate does not promote project status beyond `IMPLEMENTED_TESTING_DEFERRED`.


## 2026-09-22 — Release 50 working baseline: NetFlow device-form visibility fix

- Fixed the Device edit form so the NetFlow section is visible server-side for `network` devices.
- Root cause: `netflow_section`, `portmon_section`, and `appmon_section` were rendered with inline `style="display:none"`; the JavaScript toggler only changed the `hidden` property, so the inline CSS kept the sections invisible.
- Replaced unconditional inline hiding with server-side `hidden` attributes based on the selected device type; the existing JavaScript toggler continues to update visibility when device-type checkboxes change.
- Added WebUI regressions proving a network-device edit page contains a visible NetFlow section and a non-network application device keeps it hidden.
- No NetFlow collector/parser behavior or device I/O was changed.
- RPM remains deferred until the roadmap implementation is complete.


## 2026-09-22 — UI/CSS regression review

A fresh console review found and corrected cross-cutting presentation regressions introduced by the CSS/theme consolidation: a second `hidden`/`display:none` conflict on the dashboard no-results message; stale custom properties (`--txt`, `--bad`, `--brass`, `--brass2`, `--muted`); checkbox/radio controls inheriting the global 100% input width; dynamic graph markup bypassing theme classes; narrow-screen header wrapping; narrow-screen table overflow; and long Help inline-code overflow. The strict-CSP renderer still converts server-side `style=` attributes into nonce-authorized generated classes, and representative rendered pages were checked to contain zero residual inline-style attributes after transformation. Browser rendering smoke checks at 1440px and 390px showed no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes; Network-device NetFlow remains visible while non-network NetFlow remains hidden.

Focused regression: `tests/test_css_regression_review.py`, `tests/test_ui1_web_console.py`, and `tests/test_platform_hardening_ph1.py` pass together. Full repository evidence must still preserve explicit live/integration skips and must not be promoted to `TESTED` or `RELEASED`.

Final review evidence: focused CSS/WebUI/CSP regression is **27 passed / 0 failed**. Bounded full repository regression totals **248 passed / 8 skipped / 0 failed**. The eight skips are the expected source-archive Git metadata check plus seven explicit live PostgreSQL/backup/protocol-service prerequisites. Representative rendered-page Chromium smoke at 1440px and 390px found no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes. See `CSS_UI_REVIEW_2026-09-22.md`.

## 2026-09-23 — MC-2 focused coverage

MC-2 coverage includes observation creation, unchanged-state suppression, UNKNOWN→OK/WARNING semantics, threshold crossing (OK→WARNING→CRITICAL), noisy numeric suppression, restart-safe duplicate suppression, generator-level interface transition preservation, retention pruning, required history indexes, bounded/filterable history queries, read-only API behavior, invalid status rejection, and WebUI transition rendering. Full repository evidence for the final source artifact is recorded with the Release 50 handoff.
## 2026-09-23 — Release 50 MC-2 regression evidence

Final source-tree regression was executed in bounded groups after the MC-2 runtime/API/WebUI/retention changes: **260 passed / 8 skipped / 0 failed**. The eight skips are the expected source-archive/live-service gates: one Git-index executable-mode check (no `.git` in source ZIP), three live PostgreSQL tests, one PostgreSQL backup/restore drill, and three protocol-service integration tests. `python3 opt/netconfig/selftest.py` reports **RESULT: ALL PASS**; `compileall` passes; packaging/rpm-builder shell syntax passes. Ruff and mypy remain `NOT_RUN`.

## 2026-09-23 — Release 51 MC-3 regression evidence

MC-3 focused coverage (`tests/test_mc3_operational_evidence.py`) is **10 passed / 0 failed**. Coverage includes additive legacy event-schema migration/backfill, required normalized fields/indexes, Manager high-water transition bridging, unchanged Sensor suppression, recovery mapping, informational `UNKNOWN` handling, durable evidence-reference idempotency, legacy syslog/trap normalization, dependency-suppression regression, filtered/detail Event API reads, and Event WebUI detail with related Sensor state.

Final source-tree regression was executed in bounded groups after the MC-3 runtime/schema/API/WebUI changes:

```text
Group 1       58 passed
Group 2       74 passed
Group 3       71 passed
Group 4       67 passed / 1 skipped
Integration   7 skipped
TOTAL         270 passed / 8 skipped / 0 failed
```

The eight skips remain explicit non-passed gates: one Git-index executable-mode check because the source archive has no `.git`, three live PostgreSQL tests, one PostgreSQL backup/restore integration drill, and three protocol-service integration tests. Release 50 → Release 51 SQLite additive migration was also exercised against a real Release 50-created database containing a legacy operational event; normalized columns/indexes were added, `observed_at` was backfilled, and legacy SNMP trap entity/domain semantics were preserved. `opt/netconfig/selftest.py` reports **RESULT: ALL PASS**; `compileall`, launcher/rpm-builder `py_compile`, and packaging/rpm-builder shell syntax pass. Ruff and mypy are `NOT_RUN` because neither executable is available in this runner.

## 2026-09-23 — R51-HF1 pre-MC4 hotfix verification

Status: `IMPLEMENTED_TESTING_DEFERRED`.

Focused compatibility coverage in `tests/test_r51_pre_mc4_hotfix.py` is **8 passed / 0 failed**. It covers Net-SNMP-compatible AES256 Blumenthal extension, explicit Cisco/Reeder AES256 compatibility, FDB inference semantics, observed-edge precedence, persisted manager graph construction, same-process Vault unlock for CLI discovery, interactive Topology Web rendering, and the read-only topology graph API.

Additional topology/Web/PH-1/legacy focused execution is **40 passed / 0 failed**. The complete ordinary repository inventory was executed in four bounded groups: **58 + 74 + 71 + 75 = 278 passed**, with **1 expected source-archive Git-metadata skip**. `tests/integration` contributes **7 explicitly deferred skips**: three live PostgreSQL tests, one PostgreSQL backup/restore drill, and three live protocol-service tests. Aggregate current source evidence: **278 passed / 8 skipped / 0 failed**.

`python3 opt/netconfig/selftest.py` reports **RESULT: ALL PASS**. `python3 -m compileall`, launcher `py_compile`, and `bash -n` over packaging/rpm-builder shell scripts pass. Ruff and mypy remain `NOT_RUN` because neither executable is installed on this runner.

Required live/deferred evidence remains: FortiGate SNMPv3 SHA1+AES256 validation using the repaired client, real vendor LLDP/FDB identity behavior, PostgreSQL/backup/protocol-service integration, and formal roadmap-completion RPM qualification. None is counted as PASS.

