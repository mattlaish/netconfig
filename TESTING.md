# NetConfig Testing

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

> **Current continuation pointer:** use the Q-1 full source baseline from 2026-09-12 as the active source. Historical CURRENT/NEXT statements below are chronology only. Execute the remaining Q-1 live gates before any promotion to `TESTED`/`RELEASED`; after Q-1 qualification, perform a fresh roadmap review before assigning Q-2.

## Current Q-1 qualification summary

- CURRENT: **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`).
- Latest feature baseline: PH-3 (`IMPLEMENTED_TESTING_DEFERRED`).
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
