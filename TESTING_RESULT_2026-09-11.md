# NetConfig Testing Result — 2026-09-11

> **Historical evidence notice — 2026-09-20:** This file preserves evidence and decisions from its named historical release/date. The active implementation baseline is **Release 49 / MC-1 Sensor Integration Unification** (`2.0.0-49`, `IMPLEMENTED_TESTING_DEFERRED`). NI-7 remains the current feature baseline; historical counts and release-specific statements below are intentionally unchanged. Production AlmaLinux `rpmbuild`/DNF/systemd/SELinux and other deferred Q-1 live gates remain authoritative.

> **Current roadmap pointer — 2026-09-18:** This file is retained as historical evidence. The post-NI-7 roadmap review is complete and **no new development phase is currently assigned**. NI-7 remains the current feature baseline and Q-1 remains the open qualification track. Historical “next”, “planned”, or package-baseline statements below are chronology only and do not override current Release 44 truth.

> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.

Implementation line: **Network Intelligence NI-1 — VLAN-aware Endpoint Attachment Correlation**  
Roadmap state: **IMPLEMENTED_TESTING_DEFERRED**  
Current repository regression before this Markdown synchronization: **75 passed / 3 skipped**; focused NI-1: **8 passed**; legacy selftest: **ALL PASS**. Older D.5 sections below are chronological evidence, not current planning state.

## Current NI-1 executed result

- Full repository pytest: **75 passed / 3 skipped**.
- Focused `tests/test_network_intelligence.py`: **8 passed**.
- Legacy selftest: **ALL PASS**.
- compileall / launcher py_compile / packaging shell syntax: **PASS**.
- UTF-8 CR offenders: **0**.

## Historical D.5 chronological evidence

### Phase 4C-era repository/offline gates

- `PYTHONPATH=opt/netconfig pytest -q`: **39 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig pytest -q tests/test_incidents.py`: **20 passed**.
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall -q opt/netconfig/netconfig tests`: **PASS**.
- `python -m py_compile usr/bin/netconfig`: **PASS**.
- `bash -n packaging/build-rpm.sh packaging/inspect-rpm.sh packaging/smoke-installed.sh`: **PASS**.
- Operational text CR scan: **0 offenders**.

The three pytest skips are the existing service-backed integration tests that require `NETCONFIG_INTEGRATION=1` plus OpenSSH, Net-SNMP, and PostgreSQL services.

## Phase 4B focused coverage

The incident suite verifies:

- reference-only audit/syslog/collection/compliance evidence links;
- allow-listed source types and source-existence validation;
- idempotent duplicate link behavior;
- evidence unlink without deleting authoritative source records;
- unavailable-source markers after source retention/deletion;
- immutable drift evidence pinned to archived baseline/current stamps;
- traversal-safe drift archive references;
- unified timeline ordering across incident, incident audit, bundles and linked evidence;
- no copied external syslog/audit/compliance payloads in the link table or timeline response;
- additive `incident_evidence_links` schema creation;
- CLI parser coverage for evidence/timeline operations;
- JSON REST link/read/timeline/unlink workflow under incident scopes.

## Not run / qualification deferred

- Ruff: **NOT RUN** — binary/module unavailable in this execution environment.
- mypy: **NOT RUN** — binary/module unavailable in this execution environment.
- OpenSSH service integration: **SKIPPED / NOT RUN**.
- Net-SNMP service integration: **SKIPPED / NOT RUN**.
- PostgreSQL integration: **SKIPPED / NOT RUN**.
- GitHub Actions: **NOT RUN** here.
- AlmaLinux 10 RPM build/install/upgrade: **NOT RUN**.
- Real-device LLDP/CDP, remediation rollback, syslog relay, and live TLS/reverse-proxy qualification: **NOT RUN**.

## Truth boundary

This result proves the repository/offline Phase 4B behavior in the available environment. It does not promote the slice to TESTED or RELEASED because the documented environment-dependent gates remain outstanding.


## Artifact Packaging Integrity Gate

The candidate FULL source baseline was validated after clean extraction, not only in the source workspace:

- ZIP CRC: **PASS**.
- Path traversal entries: **0**.
- Symlink entries: **0**.
- Required source/test/packaging/documentation paths: **PASS**.
- Source vs extracted complete file-set/SHA identity: **PASS**.
- `RELEASE_MANIFEST.json`: **all payload entries matched size and SHA-256**.
- `source-manifest.sha256`, `HANDOVER_MANIFEST_SHA256.txt`, `RELEASE_MANIFEST_SHA256.txt`: **all entries verified**.
- Critical-file size sanity: **PASS**.
- Launcher and packaging script header/syntax checks: **PASS**.
- Extracted `compileall`: **PASS**.
- Extracted pytest: **33 passed, 3 skipped**.
- Extracted legacy selftest: **RESULT: ALL PASS**.
- Extracted operational-text CR scan: **0 offenders**.


## 2026-09-11 roadmap-structure refresh verification

- Documentation-only roadmap/handover reconciliation; runtime source, database schema and API behavior are unchanged from D.5 Phase 4B.
- Re-ran full repository pytest after the Markdown changes: **33 passed, 3 skipped**.
- Re-ran legacy selftest: **RESULT: ALL PASS**.
- Re-ran application/tests compileall, launcher py_compile and RPM packaging shell syntax: **PASS**.
- Operational-text CR scan: **0 offenders**.
- Ruff/mypy and service-backed/live qualification remain **NOT RUN / deferred** exactly as before.


## Phase 4C focused coverage

The expanded incident/case suite additionally verifies:

- durable additive `incident_case_exports` schema and managed export lookup;
- `incident:export` cannot be issued to viewer tokens and works for operator-or-higher tokens;
- reference-only case indexes do not contain linked authoritative audit/syslog payload bodies;
- common credential assignments in Incident/case free text are redacted in exported JSON;
- linked diagnostic bundles are embedded byte-for-byte and represented by SHA-256 manifest entries;
- selected-bundle export rejects traversal/unlinked/missing explicit selections;
- default all-linked export records a pruned linked bundle as missing metadata;
- aggregate bundle byte-budget fail-closed behavior;
- REST create/list/download scope behavior plus Incident-targeted create/download audit events;
- CLI parser coverage for `incident export-case` and `incident exports`;
- `manifest.sha256` verifies the emitted `manifest.json`;
- post-create archive tampering is detected by durable size/SHA-256 verification before download and produces an integrity-failure audit event;
- HTTP case/debug file delivery uses bounded streaming rather than `read_bytes()` whole-file buffering.

Final artifact-level Phase 4C results are recorded after the final ZIP extraction gate.


## 2026-09-11 Phase 4C artifact packaging integrity gate

The Phase 4C FULL source candidate was cleanly extracted and independently validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; required source/test/packaging/documentation paths **PASS**; source-to-extracted file set and SHA-256 identity **94/94 PASS**; `RELEASE_MANIFEST.json` payload **90/90 PASS**; all three per-file SHA manifests **90/90 PASS**; critical-file size and launcher/script header checks **PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **39 passed / 3 skipped**; extracted incident/case suite **20 passed**; extracted legacy selftest **ALL PASS**; operational-text CR offenders **0**.


## D.5 Phase 4D Evidence / Manifest Signing — executed result

Implementation regression after Phase 4D: **49 passed / 3 skipped**. Focused `tests/test_evidence_signing.py`: **10 passed**. Legacy selftest: **ALL PASS**. Compileall, launcher pycompile and packaging shell syntax: **PASS**. Operational-text CR offenders: **0**. Ruff/mypy were not installed and remain **NOT RUN**. Final extracted-package gate results are appended after final packaging.


### Phase 4D artifact delivery gate

A clean candidate FULL source ZIP was independently extracted and validated before final repackaging: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **96/96 PASS**; `RELEASE_MANIFEST.json` payload **92/92 PASS**; all three per-file SHA manifests **92/92 PASS**; required source/test/packaging/documentation files **PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **49 passed / 3 skipped**; extracted Phase 4D signing suite **10 passed**; extracted legacy selftest **ALL PASS**; UTF-8 CR offenders **0**.


## D.5 Phase 4E — Protocol Trace Capture

- Full pytest: **59 passed / 3 skipped**.
- Focused `tests/test_protocol_trace.py`: **10 passed**.
- Legacy selftest: **ALL PASS**.
- compileall / launcher py_compile / packaging shell syntax: **PASS**.
- Phase 4E validates bounded trace lifecycle, TTL/budget states, secret-safe CLI/SNMP metadata, Incident linkage, support-case trace export, REST trace lifecycle and fail-closed unimplemented structured-protocol providers.
- Ruff/mypy and environment-backed qualification remain NOT RUN/deferred.


### Phase 4E artifact delivery gate

The clean FULL source candidate was independently extracted and validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **98/98 PASS**; `RELEASE_MANIFEST.json` payload **94/94 PASS**; all three per-file SHA manifests **94/94 PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **59 passed / 3 skipped**; extracted Phase 4E protocol-trace suite **10 passed**; extracted legacy selftest **ALL PASS**.


## D.5 Phase 4F — Incident Web Console

Status: **IMPLEMENTED_TESTING_DEFERRED**

Executed before packaging:

- full pytest: **64 passed / 3 skipped**;
- focused `tests/test_incident_web.py`: **5 passed**;
- legacy selftest: **ALL PASS**;
- compileall / launcher py_compile / packaging shell syntax: **PASS**;
- Ruff/mypy: **NOT RUN** (not installed in this environment).

The focused suite covers viewer read-only behavior, operator Incident create/status/evidence workflow, integrated trace/bundle/case-export/download workflow, CSRF fail-closed behavior, cross-Incident trace-stop denial, and HTML escaping of Incident-controlled content.

### Phase 4F artifact delivery gate

The clean candidate FULL source ZIP was independently extracted and validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **99/99 PASS**; release-manifest payload **95/95 PASS**; all three per-file SHA manifests **95/95 PASS**; required source/test/packaging/documentation paths **PASS**; extracted compileall/launcher py_compile/packaging shell syntax **PASS**; extracted pytest **64 passed / 3 skipped**; extracted `tests/test_incident_web.py` **5 passed**; extracted legacy selftest **ALL PASS**; UTF-8 CR offenders **0**.


## D.5 Closeout / Diagnostic Qualification Review

- pytest: **67 passed / 3 skipped**
- focused closeout tests: **3 passed**
- legacy selftest: **ALL PASS**
- compileall: **PASS**
- launcher py_compile: **PASS**
- packaging shell syntax: **PASS**
- UTF-8 CR offenders: **0**
- Ruff: **NOT RUN** (binary unavailable)
- mypy: **NOT RUN** (binary unavailable)
- OpenSSH/Net-SNMP/PostgreSQL service-backed integration: **NOT RUN** (required service binaries unavailable)
- RPM build/install: **NOT RUN** (`rpmbuild` unavailable)
- live-device qualification: **NOT RUN**

Conclusion: D.5 planned feature phases are closed out offline, but the track remains **IMPLEMENTED_TESTING_DEFERRED** until external qualification evidence exists.


### D.5 closeout candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; source/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## Post-closeout roadmap documentation refresh

Scope is documentation-only: clarify that D.5 is not historical Slice E; set canonical NEXT to Network Intelligence Track -> VLAN-aware endpoint/topology correlation (historical Slice B); keep historical Slice E mapped only to Platform Hardening -> Web-console structural hardening; repair stale Phase 4F/current-closeout and RPM source-release metadata. Runtime/API/schema behavior is unchanged. Final regression/artifact evidence is recorded after packaging.

### Post-closeout roadmap refresh executed regression

After the documentation-only roadmap/handoff reconciliation: full pytest **67 passed / 3 skipped**; closeout-focused `tests/test_d5_closeout.py` **3 passed**; legacy selftest **ALL PASS**; compileall, launcher py_compile and packaging shell syntax **PASS**; UTF-8 CR offenders **0**. Ruff/mypy remain **NOT RUN** because binaries are unavailable. Runtime/API/schema behavior was not modified.

### Roadmap-refresh candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; stage/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; required files **PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## Source-baseline packaging repair verification

Repaired candidate artifact: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; source/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each SHA manifest **97/97 PASS**; CR offenders **0**. `usr/bin/netconfig` and all three RPM helper shell scripts are **0755** in ZIP metadata and after extraction. `./packaging/build-rpm.sh` executes directly and exits **2** with the expected `rpmbuild is required` message rather than shell exit **126/Permission denied**. Active packaging/install docs use `2.0.0-24`. Extracted regression: **67 passed / 3 skipped**; closeout-focused **3 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**.

## Network Intelligence NI-1 — VLAN-aware Endpoint Attachment Correlation

Source-workspace verification after implementation: full pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **RESULT: ALL PASS**; compileall **PASS**; launcher py_compile **PASS**; packaging shell syntax **PASS**; UTF-8 CR offenders **0**. The three skips remain the service-backed OpenSSH/Net-SNMP/PostgreSQL integration tests. Ruff/mypy, RPM build/install and representative vendor qualification remain **NOT RUN** in this environment.

Final extracted-artifact evidence is recorded after the NI-1 candidate package gate.

NI-1 candidate artifact gate: **103/103** stage/extracted identity PASS; **99/99** release-manifest payload PASS; all three SHA manifests **99/99 PASS**; executable modes **0755 PASS** in ZIP/extracted filesystem; CRC/traversal/symlink/CR checks clean; direct RPM build helper executes and stops only because `rpmbuild` is unavailable; extracted pytest **75 passed / 3 skipped**; NI-1 focused **8 passed**; selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**.


## NI-1 all-Markdown synchronization — executed result

All 19 Markdown files were updated. Active state is **CURRENT = NI-1**, **NEXT = NI-2**, D.5 is historical/completed-in-source, and active RPM source Release references are `2.0.0-25`. Historical test/changelog sections retain their original phase-specific values.

Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**.

Final refreshed artifact-gate evidence is appended after clean extraction.

## Network Intelligence NI-2 — executed result

Implementation line: **Network Intelligence NI-2 — Topology Identity & Downstream Impact**. Source-workspace regression: **83 passed / 3 skipped**; focused NI-2: **8 passed**. Legacy selftest/compileall/package-artifact results are recorded after the final artifact gate. Live-vendor and RPM qualification remain deferred.

NI-2 candidate artifact gate: **104/104** stage/extracted identity PASS; **100/100** release payload PASS; all three SHA manifests **100/100 PASS**; hidden paths exact; executable modes **0755 PASS**; traversal/symlink/cache/CR checks clean; extracted pytest **83 passed / 3 skipped**; focused NI-2 **8 passed**; selftest **ALL PASS**; compile/syntax checks **PASS**. Final FULL artifact is rebuilt after recording this evidence and must reproduce the same gate.

NI-2 prefinal clean-extraction gate reproduced the candidate result after artifact evidence was added: release payload **100/100 PASS**, executable modes **0755**, extracted pytest **83 passed / 3 skipped**, NI-2 focused **8 passed**, selftest **ALL PASS**, compile/package-shell checks **PASS**. The final FULL baseline is built from this documentation-updated source and independently revalidated before handoff.

## Network Intelligence NI-3 — executed result

Implementation line: **Network Intelligence NI-3 — SNMP Traps & Dependency-aware Events**. Source-workspace regression: **91 passed / 3 skipped**; focused NI-3: **8 passed**. Legacy selftest, compileall, launcher py_compile and packaging shell syntax pass. Artifact-level evidence is recorded after final packaging. Live Net-SNMP/vendor and RPM qualification remain deferred.

### NI-3 candidate artifact gate

Candidate `netconfig_network_intelligence_ni3_candidate_2026-09-11.zip` SHA-256 `8313eb7250d6a1b38da5f8d6e593e8fb7ca90a73831e270cbf35234569848acd` passed clean system-unzip validation: 107/107 stage↔extracted byte identity; 103/103 Release payload and each SHA manifest; exact hidden paths; four executable files retained `0755`; ZIP CRC/path-traversal/symlink/cache/CR gates passed. Extracted regression: **91 passed / 3 skipped**, focused NI-3 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.


## Network Intelligence NI-4 — executed result

Implementation line: **Network Intelligence NI-4 — Operational Alert & Reporting Lifecycle**. Source-workspace regression: **99 passed / 3 skipped**; focused NI-4: **8 passed**. Legacy selftest **ALL PASS**; compileall, launcher py_compile and packaging shell syntax **PASS**. Source RPM metadata is `2.0.0-28`. Artifact-level evidence is appended after final packaging. Live SMTP/service/RPM/vendor qualification remains deferred.


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

## Platform Hardening PH-2 — PostgreSQL Core & Distributed Operation

- Focused PH-2 tests: **9 passed**.
- Full workspace regression: **114 passed / 3 skipped**.
- Live PostgreSQL/HA/RPM qualification: **NOT RUN / DEFERRED**.
- Implemented offline-verifiable contracts: PostgreSQL schema bootstrap/translation, protected core DB credential resolution, storage readiness/revision, advisory-lock scheduler coordination, SKIP LOCKED claim SQL, durable distributed task model, and fail-closed SQLite→PostgreSQL migration tooling.

PH-2 candidate artifact gate: SHA-256 `6dfd6e554b08883c51a6f268bbe604bf95cc7819dad8f4bda6f023d688807d21`; 114/114 full-file identity; 110/110 Release payload and all three SHA manifests; exact hidden paths; 0755 executables; 19/19 Markdown state; extracted 114 passed / 3 skipped + focused PH-2 9 passed + selftest/compile/shell PASS. Final FULL artifact is rebuilt after this evidence update.
