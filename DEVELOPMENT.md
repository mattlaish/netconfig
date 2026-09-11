# Development Ledger

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

> **Current continuation pointer:** use the Q-1 full source baseline from 2026-09-12 as the active source. Historical CURRENT/NEXT statements below are chronology only. Execute the remaining Q-1 live gates before any promotion to `TESTED`/`RELEASED`; after Q-1 qualification, perform a fresh roadmap review before assigning Q-2.

## 2026-09-12 — Qualification Track Q-1 — Production Runtime & Service-backed Qualification

Status: `IMPLEMENTED_TESTING_DEFERRED`. RPM source Release: `2.0.0-32`. No database schema revision is introduced by Q-1; the core schema revision remains `ph3-1`.

Implemented:

- Reconciled package/project/RPM version truth to application Version `2.0.0` and RPM Release 32.
- Added `postgres_backup.py` with fixed-function `pg_dump`/`pg_restore`, atomic backup replacement, mode-0600 backup/checksum files, SHA-256 verification, configured libpq SSL mode, bounded subprocess deadlines, and no password in argv.
- Restore is deliberately a drill/standby workflow: explicit `RESTORE_DATABASE` confirmation is mandatory and the configured active core DB name is refused as a restore target.
- Added a recovery-safe restore CLI branch that loads settings/credentials without opening the active core database first.
- Added `qualification.py` and `netconfig qualify` configuration-aware runtime preflight.
- Added real PostgreSQL Q-1 integration tests for multi-connection `SKIP LOCKED`, advisory-lock leadership/session-loss release, heartbeat visibility, SQLite import/sequence repair, and pg_dump/pg_restore restore drill.
- Expanded GitHub Actions to install PostgreSQL client tools and execute the real Q-1 PostgreSQL tier.
- Added fail-closed source, PostgreSQL, and AlmaLinux 10 qualification scripts. AlmaLinux installation is mutation-gated by both `--install` and `NETCONFIG_Q1_ALLOW_INSTALL=1`.
- Split RPM build from installed smoke: `build-rpm.sh` no longer assumes the package is already installed. Installed smoke now runs `netconfig qualify` and asserts packaged unit hardening.
- Hardened `netconfig-backup.service` consistently with the Web service and documented the pre-vault `postgres-core-password` systemd credential.

Offline evidence before final artifact packaging: Q-1 focused **11 passed**; full repository **147 passed / 7 skipped**. The seven skips are intentional service-backed gates. Ruff/mypy could not be installed because this isolated execution environment has no package-network resolution; `q1-source-gates.sh` therefore exits 2 and records the tooling gate as `NOT_RUN`. `q1-qualify-postgres.sh` exits 2 because PostgreSQL client tools are unavailable. `q1-qualify-almalinux.sh` exits 20 because the current host is Debian 13 rather than AlmaLinux 10. None are counted as passing.

Artifact evidence: Clean Q-1 candidate `netconfig_qualification_q1_candidate_2026-09-12.zip` (SHA-256 `185039eadf8e8e63a8dad358df35f759a7a1f099d5fa6a3456a50e023920a2b1`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; source/extracted byte identity **125/125 PASS**; payload plus each SHA manifest **121/121 PASS**; required executable modes **7/7 = 0755**; extracted Q-1 focused **11 passed**; extracted full regression **147 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.

Session idle/absolute expiry remains explicitly deferred and unchanged. PH-3 structured-protocol behavior is unchanged by Q-1.

## Current implementation pointer — 2026-09-12

**CURRENT:** Qualification Q-1 — Production Runtime & Service-backed Qualification (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE:** PH-3 (`IMPLEMENTED_TESTING_DEFERRED`). **NEXT ACTION:** execute deferred Q-1 live qualification; no Q-2 is assigned. Historical entries below are chronology only. Current RPM source Release is `2.0.0-32`.


## 2026-08-31 — engineering/security/remediation hardening slice

### Implemented

- Added `pyproject.toml` with Python 3.12+ contract, pytest, Ruff, and mypy configuration.
- Added GitHub Actions CI for lint, incremental typing, compileall, pytest, legacy self-test, PostgreSQL, scripted real-OpenSSH integration, and Net-SNMP integration.
- Added focused pytest modules for config remediation modeling, login throttling/security headers, service credentials, SNMP worker concurrency, protocol capabilities, and legacy-regression execution.
- Added `security.py` with process-local bounded login throttling and console security headers.
- Added `observability.py` with structured JSON events and Prometheus text metrics.
- Added `/healthz`, `/readyz`, and `/metrics`; restored HTTP access observability instead of suppressing `log_message`.
- Added failed-login and throttled-login audit events. Successful login/logout now include peer-source audit context.
- Added optional built-in TLS through stdlib `ssl.SSLContext`; CLI accepts `--tls-cert` and `--tls-key`.
- Added service vault bootstrap from systemd credential directory or root-only master file; legacy `NETCONFIG_MASTER` remains fallback compatibility only.
- Replaced service-start recursive root `chown` with systemd `StateDirectory=netconfig`; enabled `MemoryDenyWriteExecute=true` in the packaged web unit.
- Added `configmodel.py` and changed remediation from baseline text replay to fresh-live semantic planning, vendor negation, guarded execution, post-change re-fetch, and semantic verification.
- Remediation now refuses scrubbed baselines and platforms without an implemented automatic rollback guard.
- Added bounded concurrent SNMP polling with metrics.
- Added a thin storage boundary and explicit protocol capability registry for future PostgreSQL-core / NETCONF / RESTCONF / gNMI work.
- Updated remediation approval preview to show the semantic plan from the latest stored current config; execution still re-plans from fresh live state.
- Fixed a duplicate username field in the login page.

### Intentional non-change

Console session expiry was **not** implemented in this slice. The current in-memory session remains valid until logout or process restart. This is explicitly documented as deferred security debt in `SECURITY.md` and `ROADMAP.md` for a later dedicated lifecycle change.

### Validation still required

- Run CI on Python 3.12 with Ruff and mypy installed.
- Run the OpenSSH/Net-SNMP/PostgreSQL integration tier in Linux CI.
- Validate Cisco IOS/ASA and Arista timed-reload interactions on real vendor/lab images.
- Validate JunOS `commit confirmed` behavior and prompt transitions on a real JunOS lab image.
- Validate `MemoryDenyWriteExecute=true` on the exact target distribution/package build.
- Confirm built-in TLS certificate/key permissions and reverse-proxy coexistence in deployment environments.

### Known limitations

- Enforced CSP still permits legacy inline script/style because `web.py` has inline event handlers. Strict nonce CSP is report-only until those are removed.
- The old `selftest.py` remains as a compatibility runner while cases are progressively migrated to pytest.
- The storage abstraction is intentionally thin; the core database is still SQLite/WAL.
- NETCONF/RESTCONF/gNMI are architecture capabilities, not implemented transports yet.

## 2026-09-01 — CI lint and line-ending hygiene follow-up

### Implemented

- Reconciled Ruff with the existing code style so the CI lint gate is actionable: `E702` (multiple statements separated by semicolons) is now an explicit temporary house-style exception instead of an always-failing gate.
- Removed confirmed unused imports and cleaned the identified `F541`, `B904`, and `E741` violations rather than suppressing those rule families.
- Added `.gitattributes` with LF enforcement for Python, shell, systemd units/timers, RPM specs, TOML/YAML, Markdown, and common repository text artifacts.
- Renormalized repository text files to LF. Local verification found zero CRLF/bare-CR UTF-8 text files after normalization.
- Added repository-hygiene pytest coverage and a CI index-EOL check so future CRLF regressions are visible.

### Validation

- `python -m compileall -q opt/netconfig/netconfig tests`: PASS.
- `pytest -q`: PASS (11 passed, 3 integration tests skipped because protocol services are not running locally before this follow-up's new hygiene tests were added; rerun after final packaging records the final count).
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: `RESULT: ALL PASS`.
- Local Ruff execution remains **NOT RUN** because Ruff is not installed in this sandbox and outbound PyPI access is unavailable. The GitHub Actions Ruff step remains the authoritative validation for the exact configured ruleset.

### Deferred security debt unchanged

- Console idle timeout / absolute session expiry remains deliberately deferred. No session-lifetime behavior was changed in this follow-up; see `SECURITY.md` and `ROADMAP.md`.

## 2026-09-02 — topology, event-driven collection, read-only API, scheduled digest slice

### Implemented

- Added `topology.py` with pure LLDP-MIB and CDP-detail parsers, inventory/SNMP-sysName correlation and explicit unmanaged-neighbour classification.
- SNMP network polling now persists LLDP topology; when LLDP returns no neighbours and SSH credentials are available, a read-only `show cdp neighbors detail` fallback is attempted.
- Added a dependency-free `/topology` SVG fleet map and neighbour table plus a manual fleet discovery action.
- Added `syslog_receiver.py`: bounded UDP queue, 8 KiB message cap, source-IP device correlation, common config-change event matching, per-device debounce, immediate archive trigger, persistent recent events and audit evidence. Default listener is non-privileged udp/5514.
- Added `apitokens.py` and additive `api_tokens` schema. Tokens are random bearer credentials, stored only as SHA-256 hashes, have an existing NetConfig role plus explicit read scopes, support CLI create/list/revoke, and are audited on API use.
- Added read-only API endpoints for inventory, topology, drift, latest compliance, latest digest and audit.
- Added `digest.py`: periodic compliance/drift sweep with persisted digest evidence and SMTP/O365 delivery through the existing mailer. Monitoring settings now expose syslog and digest scheduling.
- Added additive topology/syslog/digest database tables and focused pytest coverage.

### Validation

- `PYTHONPATH=opt/netconfig pytest -q`: **19 passed, 3 skipped** (the 3 existing protocol-service integration tests remain environment-gated).
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall`: PASS for changed modules and final tree.

### Deferred / not claimed

- No real-device LLDP/CDP lab run was performed in this environment.
- No production syslog relay/NAT design is claimed; source-IP matching assumes the UDP peer is the managed device. Trusted-relay parsing must be explicit before supporting relayed syslog.
- SNMP traps are not implemented in this slice.
- Session idle/absolute expiry remains deliberately deferred security debt and was not changed.


## 2026-09-07 — new-chat handover and roadmap reconciliation

### Handover preparation

- Added `HANDOVER_2026-09-07.md` as the concise current-state entry point.
- Added `TESTING_RESULT_2026-09-07.md` with exact executed/deferred gate evidence.
- Added `HANDOVER_PROMPT.md` for direct reuse in a new chat.
- Extended `ROADMAP.md` with a prioritized next-slice sequence led by qualification/release closure,
  VLAN-aware IP/MAC/VLAN/port correlation, and SNMP trap/event correlation.
- Reconciled contradictory Git instructions: the user manages Git manually unless explicitly authorizing
  Git operations in the current chat.
- Reconciled stale packaging examples to the current spec Release 17 and made the build script artifact
  listing release-agnostic. No RPM was built.

### Verification

- `PYTHONPATH=opt/netconfig pytest -q`: **19 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall -q opt/netconfig/netconfig tests`: **PASS**.
- LF hygiene scan: **0 CR-containing repository text files**.
- Ruff/mypy, GitHub Actions, service-backed integration, AlmaLinux RPM and live-device gates were not run
  in this handover environment and remain explicitly deferred.

### Runtime behavior

No application runtime feature was intentionally changed. Console session idle/absolute expiry remains
unchanged and deliberately deferred.


## 2026-09-10 — Slice D.5 Diagnostic & Support Bundle Framework

Implemented the first diagnostic/support framework foundation. Added `debug.py` with redacted bundle generation, manifest generation, SHA-256 file inventory, and secret-pattern redaction. Added `netconfig debug collect` CLI command. No plaintext credentials, tokens, vault material, or private keys are exported.

Deferred: full device debug capture, REST debug bundle API, UI diagnostics page, and production incident workflow.


## 2026-09-10 — Slice D.5 Phase 2 Diagnostic Support Bundle completion update
- Added device diagnostic capture foundation (`netconfig debug device <name>`).
- Diagnostic exports remain secret-redacted and manifest/checksum validated.
- Current slice remains IMPLEMENTED_TESTING_DEFERRED until REST API, Web UI diagnostics, retention policy, and full device protocol traces are completed.


## Slice D.5 Phase 3 update (2026-09-10)
Implemented diagnostic bundle retention foundation: bundles are stored under the NetConfig state directory, can be listed and cleaned up from CLI, and continue using redaction and manifest integrity. REST API, Web UI diagnostics, trace capture, and signed bundle workflow remain deferred.


## Slice D.5 Phase 3B — Diagnostic API Foundation (2026-09-10)
- Added read-only debug bundle API foundation.
- Added debug:create and debug:read API token scopes.
- Bundle creation remains secret-redacted and audited.
- Status: IMPLEMENTED_TESTING_DEFERRED.
- Deferred: Diagnostics UI, download workflow, incident correlation, protocol trace capture.


## D.5 Phase 3D — Enterprise Diagnostic Operations

Status: IMPLEMENTED_TESTING_DEFERRED

Added secure debug bundle download API foundation, debug:download scope, RBAC/audit integration. Deferred: incident workflow, signed manifests, retention scheduler UI.


## 2026-09-11 — Slice D.5 Phase 4A: Incident Model Foundation

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added `opt/netconfig/netconfig/incidents.py` as the incident lifecycle service.
- Added additive SQLite `incidents` and `incident_bundles` tables plus status/severity indexes. Existing databases create the new tables in-place without rewriting prior device/history data.
- Incident IDs are generated after insert as `INC-<UTC year>-<six-digit row id>`; the database numeric ID remains internal and both forms can be used for lookup.
- Added bounded input validation for titles, descriptions and tags; fixed severity/status vocabularies; explicit lifecycle transitions; closure/reopen metadata; and append-only audit events for create/update/status/bundle link/unlink operations.
- Added `netconfig incident create|list|show|update|status|link-bundle|unlink-bundle`.
- Added `incident:read` and `incident:write` bearer scopes. `incident:write` cannot be issued to a viewer token and the HTTP API independently re-checks operator-or-higher role at request time.
- Added JSON request-body support to the existing API POST reader while preserving URL-encoded Web-console forms.
- Added `/api/v1/incidents`, `/api/v1/incidents/{id}`, `/api/v1/incidents/{id}/status`, and `/api/v1/incidents/{id}/bundles` foundation endpoints.
- Diagnostic bundle links accept only a basename ending in `.tar.gz` and, in the production Manager path, require the bundle to exist under the managed `debug-bundles` directory.
- Baseline repair: Phase 3D's Web/API download handler already required `debug:download`, but the token registry did not allow that scope. Added `debug:download` and `debug:admin` to `VALID_SCOPES` and centralized managed bundle lookup in `DebugBundle.get_bundle()`.

### Deliberately deferred

- Unified incident timeline/event references (Phase 4B).
- Support-case export (Phase 4C).
- Evidence signing/trust model (Phase 4D).
- Protocol trace capture (Phase 4E).
- Incident Web Console (Phase 4F).
- Console session idle/absolute expiry remains known security debt and was not changed.
- Real CI service tier, real network devices, AlmaLinux RPM build/install and live HTTP/TLS qualification were not run in this environment.

### Repository validation

- Phase 4A focused incident tests: **8 passed**.
- Final full pytest for Phase 4A: **28 passed, 3 skipped**; the three skips are the pre-existing service-backed OpenSSH/Net-SNMP/PostgreSQL integration tests.
- Python runtime used: 3.13.5 under the declared `>=3.12,<3.14` contract.


## 2026-09-11 — Slice D.5 Phase 4B: Incident Timeline

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added additive SQLite `incident_evidence_links` with a unique incident/source reference, linker identity/timestamp, and bounded operator note. Authoritative event/config/report content is intentionally not copied into this table.
- `Incidents.link_evidence()` validates existing audit, syslog, configuration collection (`runs`), and compliance-run IDs before linking. Duplicate links are idempotent.
- `Incidents.link_drift()` captures a reference to the device's then-current baseline and latest immutable archived configuration stamps; timeline resolution compares those exact files, not the later mutable `current.cfg`.
- `Incidents.timeline()` produces one ordered view containing incident creation, incident-native audit activity, current diagnostic-bundle associations, and explicitly linked evidence. Missing/pruned source rows remain as `available=false` timeline markers.
- Added CLI `incident link-evidence`, `link-drift`, `unlink-evidence`, `evidence`, and `timeline`.
- Added API `GET /api/v1/incidents/{id}/timeline`, `GET /api/v1/incidents/{id}/evidence`, `POST /api/v1/incidents/{id}/evidence`, and constrained evidence unlink. Existing `incident:read` and role-gated `incident:write` scopes are reused; no new broad token privilege was introduced.
- API and CLI do not expose a generic SQL/table selector: evidence types are allow-listed and each resolver uses fixed queries.
- RPM source spec Release advanced to 19 for this changed source baseline; no RPM build/install is claimed.

### Design decisions

- Evidence links are references, not evidence copies. This preserves one authoritative source of truth and prevents timeline data from diverging from audit/syslog/compliance/config archives.
- Drift is the exception that needs a composite pointer: the link stores only device/baseline-stamp/current-stamp identifiers. The referenced configuration snapshots remain authoritative.
- Incident-native audit rows are included automatically because their `target` is the incident key. External audit rows require an explicit evidence link.
- Bundle history remains governed by `incident_bundles` plus append-only audit; Phase 4B does not create a competing bundle-evidence table.

### Deliberately deferred

- Phase 4C support-case export.
- Phase 4D evidence signing/trust model.
- Phase 4E protocol trace capture.
- Phase 4F Incident Web Console.
- Automatic event-to-incident correlation rules; Phase 4B establishes the reference/timeline substrate only.
- Console session idle/absolute expiry remains known security debt and is unchanged.
- Ruff/mypy, service-backed integration, AlmaLinux RPM and live-device qualification remain environment-deferred.

### Repository validation

- Phase 4B focused incident tests: **14 passed**.
- Full pytest: **33 passed, 3 skipped**.
- Legacy selftest: **RESULT: ALL PASS**.
- `python -m compileall`: **PASS**.
- Ruff/mypy: **NOT RUN** (not installed in the execution environment).


### Phase 4B artifact delivery gate

The FULL source candidate was also validated after clean ZIP extraction: no traversal/symlink entries, complete source-to-extracted SHA identity, all per-file manifests valid, critical-file/header checks valid, extracted compileall PASS, extracted pytest **33 passed / 3 skipped**, extracted selftest **ALL PASS**, and CR offenders 0. Source-only tests do not substitute for this artifact-level check.


## 2026-09-11 — Roadmap execution-structure reconciliation

- Documentation-only change; runtime source, database schema and API behavior are unchanged.
- Replaced the historical Slice A-G primary execution ordering with canonical **Current / Next / Diagnostics Track / Network Intelligence Track / Platform Hardening Track** planning.
- At that documentation-only refresh, current was **D.5 Phase 4B — Incident Timeline** and next was **D.5 Phase 4C — Support Case Export**; the later Phase 4C section supersedes that planning snapshot.
- Preserved Slice A-G as historical 2026-09-07 handover mapping so older patch/handover records remain interpretable without controlling future sequencing.
- Synchronized `ROADMAP.md`, `AI_HANDOFF.md`, `HANDOVER_PROMPT.md`, `DEV_BASELINE.md`, and `HANDOVER_2026-09-07.md`.
- No session-lifetime behavior changed.


## 2026-09-11 — Slice D.5 Phase 4C: Support Case Export

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added `caseexport.py` with managed `case-exports/` storage and bounded archive construction.
- Added additive SQLite `incident_case_exports` records containing export identity, Incident FK, creator/time, bounded reason, included/missing diagnostic bundle indexes, archive size and SHA-256.
- Case archives contain explicit Incident metadata, reference-only evidence/timeline indexes, selected linked diagnostic bundles copied byte-for-byte, a human-readable README, file manifest and `manifest.sha256`.
- No authoritative syslog body, external audit detail, compliance report body, or configuration text is copied into the case indexes. Phase 4B source pointers remain the provenance boundary.
- Added fail-closed bundle selection: traversal/unlinked/missing explicitly requested bundles are rejected. With default all-linked export, previously pruned bundle files remain visible as missing metadata instead of silently disappearing or being recreated.
- Added 32-bundle / 512 MiB aggregate diagnostic-bundle bounds.
- Added common credential-assignment redaction for Incident title/description/tags, link notes and export reason before case JSON emission.
- Added dedicated role-gated `incident:export` token scope. Viewer tokens cannot be issued this scope.
- Added CLI `incident export-case` and `incident exports`.
- Added REST `POST /api/v1/incidents/{id}/exports`, `GET /api/v1/incidents/{id}/exports`, and guarded `GET /api/v1/incidents/{id}/exports/{export_key}` download.
- Export creation and download append Incident-targeted audit events. Download revalidates durable archive size/SHA-256 and fails closed/audits an integrity mismatch.
- Added streaming file response for case/debug downloads so large bounded archives are not read entirely into process memory.
- RPM source spec Release advanced to 20 for this changed source baseline; no RPM build/install is claimed.

### Deliberately deferred

- Cryptographic evidence/manifest signing and signer trust model (Phase 4D).
- Secret-safe protocol trace capture (Phase 4E).
- Incident Web Console (Phase 4F).
- Automatic correlation rules and closeout retention/scheduler policy remain later work.
- Console session idle/absolute expiry remains known security debt and was not changed.
- Ruff/mypy, service-backed protocol integration, AlmaLinux RPM installation and live-device qualification remain environment-dependent/deferred unless explicitly executed below.

### Repository validation

- Full pytest after Phase 4C implementation: **39 passed, 3 skipped**.
- Focused incident/case suite: **19 passed**.
- Legacy selftest: **RESULT: ALL PASS**.
- Application/tests compileall: **PASS**.

### Phase 4C artifact delivery gate

The FULL source candidate passed clean-extraction artifact verification: 94/94 source/extracted files matched by SHA-256; 90/90 release/per-file manifest payload entries verified; CRC/path traversal/symlink/CR checks passed; extracted pytest **39 passed / 3 skipped**; focused incident/case suite **21 passed**; extracted selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**.


## 2026-09-11 — Slice D.5 Phase 4D: Evidence / Manifest Signing

Implemented an external-key Ed25519 evidence-signing boundary without adding a Python cryptography dependency. `evidence_signing.py` invokes the system OpenSSL executable using fixed arguments only; arbitrary signer commands/shell strings are not supported. Private keys resolve from systemd credentials first and a protected explicit file second, must be regular non-symlink files with restrictive permissions, and are never stored in NetConfig state or evidence archives.

Both diagnostic bundles and Phase 4C support-case exports now auto-sign when a valid signer is configured. Per-operation/global signing-required policy fails closed if signing cannot be performed. Signed archives carry `manifest.signature.json` and `manifest.public.pem`; verification never extracts the archive, validates archive structure, rejects link/device entries and unmanifested regular files, recomputes every payload size/SHA-256, validates `manifest.sha256`, verifies Ed25519, and reports independent trust-pin state.

Support-case export metadata now has additive `signature_state`, `signature_algorithm`, and `signer_fingerprint` columns. Existing databases migrate additively and prior unsigned records remain valid. Case download still validates durable outer archive size/SHA-256, then verifies signed inner evidence and durable signer fingerprint; configured trust pins are enforced.

CLI/API verification and signer-readiness surfaces were added. Key rotation is supported by allowing multiple independent trusted fingerprints. HSM/KMS-backed signers, protocol traces, and Incident Web Console remain deferred. Session expiry remains unchanged/deferred.

Executed repository regression after implementation: **49 passed, 3 skipped**; Phase 4D focused signing tests: **10 passed**; legacy selftest: **ALL PASS**; compileall/launcher pycompile/packaging shell syntax: **PASS**; CR offenders: **0**. Ruff/mypy remain NOT RUN in this environment.


### Phase 4D artifact delivery gate

A clean candidate FULL source ZIP was independently extracted and validated before final repackaging: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **96/96 PASS**; `RELEASE_MANIFEST.json` payload **92/92 PASS**; all three per-file SHA manifests **92/92 PASS**; required source/test/packaging/documentation files **PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **49 passed / 3 skipped**; extracted Phase 4D signing suite **10 passed**; extracted legacy selftest **ALL PASS**; UTF-8 CR offenders **0**.


## 2026-09-11 — Slice D.5 Phase 4E: Protocol Trace Capture

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added `protocoltrace.py` and additive `protocol_trace_sessions` / `protocol_trace_events` schema.
- Added explicit bounded trace lifecycle (`PTR-...`): ACTIVE, STOPPED, EXPIRED and LIMIT_REACHED; TTL 30..3600s, max 5000 events, max 8 MiB serialized metadata per session.
- Added CLI/OpenSSH metadata capture through an optional transport callback. `execute()` records command summary/status/duration/byte counts but never raw device output. Sensitive command text is replaced by a fixed redaction marker and is not hashed from original secret-bearing content.
- Added context-local SNMP UDP-exchange capture using `ContextVar`; stores target/port/attempt/status/duration/byte counts without BER payload, community or v3 secrets. SNMP poll, walk and LLDP discovery enter that context when an active trace exists.
- Added `protocol_trace` Incident evidence resolution/linkage. Starting a trace with `--incident` links the durable trace automatically.
- Added `protocol-traces.json` to support-case exports and bounded recent trace metadata to general/device diagnostic bundles.
- Added `trace:read` plus role-gated `trace:capture`, CLI trace lifecycle and REST trace lifecycle.
- Added future-ready protocol identifiers for NETCONF/RESTCONF while failing trace start closed until those transport providers are actually implemented.
- RPM source Release advanced to 22 for this changed source baseline; no RPM build/install is claimed.

### Verification

- Full pytest: **59 passed, 3 skipped**.
- Phase 4E focused tests: **10 passed**.
- Legacy selftest: **RESULT: ALL PASS**.
- compileall, launcher py_compile and packaging shell syntax: **PASS**.
- Ruff/mypy: **NOT RUN** (not installed in this environment).

### Deferred

- Phase 4F Incident Web Console.
- NETCONF/RESTCONF actual protocol providers and their trace hooks.
- Raw packet capture is intentionally not planned as part of this safe trace subsystem.
- Service-backed integration, live-device qualification and RPM install remain deferred.
- Console session idle/absolute expiry remains separate known security debt.


### Phase 4E artifact delivery gate

The clean FULL source candidate was independently extracted and validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **98/98 PASS**; `RELEASE_MANIFEST.json` payload **94/94 PASS**; all three per-file SHA manifests **94/94 PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **59 passed / 3 skipped**; extracted Phase 4E protocol-trace suite **10 passed**; extracted legacy selftest **ALL PASS**.


## 2026-09-11 — Slice D.5 Phase 4F: Incident Web Console

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added an authenticated `Incidents` console navigation entry, register/filter page, and Incident detail page without introducing a second data model.
- Viewer is read-only; operator/approver/admin can create/update Incidents, request only valid lifecycle transitions, manage existing evidence/bundle links, start/stop bounded CLI/SNMP traces, and create/verify/download support-case exports.
- Unified the Phase 4B timeline, evidence links, Phase 4E trace sessions/events, linked diagnostic bundles, and Phase 4C/4D export/signature state on the Incident detail workflow.
- Preserved CSRF for every browser mutation. Support-case download uses the existing verified chunked-streaming path.
- Added HTML-escaping regression coverage for Incident-controlled fields and fail-closed cross-Incident trace-stop coverage.
- Added `tests/test_incident_web.py`. No schema migration was required.
- RPM source Release advanced to 23 for this changed source baseline; no RPM build/install is claimed.

### Verification

- Full pytest: **64 passed, 3 skipped**.
- Phase 4F focused tests: **5 passed**.
- Legacy selftest: **RESULT: ALL PASS**.
- compileall, launcher py_compile and packaging shell syntax: **PASS**.
- Ruff/mypy: **NOT RUN** in this environment.

### Deferred

- D.5 closeout/qualification, including remaining scheduled retention/cleanup policy.
- Service-backed protocol integration, live-device and RPM qualification.
- Console idle/absolute session expiry remains separate known security debt.

### Phase 4F artifact delivery gate

A clean candidate FULL source package was extracted and independently verified before final repackaging: source/extracted identity **99/99 PASS**, manifest payload **95/95 PASS**, ZIP CRC **PASS**, no path traversal/symlinks/CR offenders, extracted pytest **64 passed / 3 skipped**, focused Phase 4F Web tests **5 passed**, legacy selftest **ALL PASS**, and compileall/launcher/package-shell syntax **PASS**.


## 2026-09-11 — D.5 Closeout / Diagnostic Qualification Review

Added opt-in bounded diagnostic retention maintenance without changing default deployment behavior. `diagnostic_maintenance_interval=0` keeps the scheduler disabled unless an operator enables it. `debug_bundle_keep` limits support-bundle count, `case_export_retention_days` removes old case archive files while retaining durable export metadata, and `protocol_trace_retention_days` removes only inactive traces that are not linked to an Incident. `netconfig debug maintenance` provides an audited one-shot execution path. Monitoring settings expose the same policy.

Closeout regression: **67 passed / 3 skipped**; focused closeout tests **3 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell checks **PASS**; CR offenders **0**. Ruff/mypy, OpenSSH/Net-SNMP/PostgreSQL service-backed integration, AlmaLinux RPM build/install and representative live-device qualification were unavailable and remain explicitly deferred. D.5 therefore remains **IMPLEMENTED_TESTING_DEFERRED** even though its planned feature phases are complete. RPM source metadata advanced to `2.0.0-24`; no RPM build/install is claimed.


### D.5 closeout candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; source/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## 2026-09-11 — Post-closeout roadmap naming reconciliation

Documentation-only clarification; no runtime/API/schema/package-spec behavior changed. Canonical planning now states explicitly that **D.5 is the standalone Diagnostics Track and is not historical Slice E**. The post-D.5 NEXT item, **Network Intelligence Track -> VLAN-aware endpoint and topology correlation**, maps historically to **Slice B**. Historical **Slice E** remains the separate **Platform Hardening -> Web-console structural hardening** backlog item. Stale handoff/baseline metadata that still showed Phase 4F as current or D.5 Closeout as next was updated to the completed closeout state. Current source RPM spec remains `2.0.0-24`; no RPM build/install qualification is claimed.

### Roadmap-refresh candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; stage/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; required files **PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## 2026-09-11 — Source baseline packaging repair

Repaired the post-closeout roadmap-refresh delivery artifact without changing runtime/API/schema behavior. The source-delivery ZIP now preserves executable mode `0755` for `usr/bin/netconfig`, `packaging/build-rpm.sh`, `packaging/inspect-rpm.sh`, and `packaging/smoke-installed.sh`. Active RPM build/install documentation was reconciled from stale `2.0.0-17` examples to the current source Release `2.0.0-24`; historical changelog/patch provenance remains unchanged. Re-run full regression and extracted-artifact mode/documentation checks before publishing the repaired FULL source baseline.

### Repaired source-baseline candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; stage/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; all three SHA manifests **97/97 PASS**; required files **PASS**; UTF-8 CR offenders **0**. ZIP central-directory and extracted filesystem modes are **0755 PASS** for `usr/bin/netconfig`, `packaging/build-rpm.sh`, `packaging/inspect-rpm.sh`, and `packaging/smoke-installed.sh`. Direct `./packaging/build-rpm.sh` execution reaches the script and exits **2** only because `rpmbuild` is unavailable, not **126 Permission denied**. Active build/install docs reference **2.0.0-24**. Extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.


## 2026-09-11 — Network Intelligence Phase NI-1: VLAN-aware Endpoint Attachment Correlation

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added modern IP-MIB `ipNetToPhysicalTable` collection for IPv4/IPv6 with explicit legacy IPv4 fallback provenance.
- Added Q-BRIDGE-MIB VLAN-aware FDB collection, bridge-port -> ifIndex mapping and unique FDB-ID -> VLAN resolution. Shared FDB/VLAN mappings remain unresolved rather than guessed.
- Added additive `ip_neighbors` and `vlan_fdb` tables and compatibility projection into existing ARP/MAC device views.
- Added `network_intelligence.py` correlation with freshness budget, LLDP/CDP transit suppression, explicit ambiguity and confidence.
- Added `endpoint:read`, `/api/v1/endpoints`, `netconfig endpoints [--refresh] [--json]`, authenticated Endpoints Web UI, endpoint metrics and SNMP Settings freshness control.
- Added canned-walk and correlation tests in `tests/test_network_intelligence.py`.
- RPM source Release advanced to `2.0.0-25`; no RPM build/install is claimed.

### Verification before final artifact packaging

- Full pytest: **75 passed / 3 skipped**.
- NI-1 focused tests: **8 passed**.
- D.5 regression remains green.
- Final selftest/compile/package and extracted-artifact results are recorded in `TESTING.md` after packaging.

### Deferred

- NI-2 chassis/system identity normalization and complete downstream impact traversal.
- Representative vendor Q-BRIDGE/IP-MIB qualification and service-backed Net-SNMP integration.
- Existing Ruff/mypy/RPM/live-device qualification debt remains unchanged.

NI-1 source-workspace release checks: full pytest **75 passed / 3 skipped**, focused NI-1 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**, executable launcher/helper modes **0755**.

### NI-1 artifact delivery gate

Candidate FULL source artifact independently passed 103/103 source-to-extracted identity, 99/99 release payload and all SHA manifests, executable-mode preservation, archive-security checks and extracted regression (75 passed / 3 skipped; NI-1 8 passed; selftest ALL PASS). Final FULL baseline is rebuilt after recording this evidence and must pass the same gate again.


## 2026-09-11 — NI-1 all-Markdown canonical-state synchronization

Documentation-only reconciliation across all 19 Markdown files. Runtime source, database schema, API behavior and RPM spec are unchanged. Active state is uniformly **CURRENT = NI-1**, **NEXT = NI-2**; D.5 and the 2026-09-07 A-G ordering are retained only as explicit historical/provenance context. Active source RPM Release remains `2.0.0-25`.

Validation: Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**.

Delivery artifact to publish after artifact gate: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`.

## 2026-09-11 — Network Intelligence NI-2: Topology Identity & Downstream Impact

Status: **IMPLEMENTED_TESTING_DEFERRED**.

NI-2 adds normalized managed-device topology identity from bounded LLDP local-system objects, ENTITY-MIB chassis rows, and the existing IF-MIB interface poll. `topology_device_identity` stores sysName, chassis ID/subtype, normalized chassis MAC, chassis serial/name/model and LLDP capability evidence. `topology_interface_identity` stores ifIndex, ifName, ifDescr, ifAlias and interface physical address without treating LLDP localPortNum as ifIndex.

Managed-neighbour resolution is fail-closed. Inventory name/host, SNMP sysName, chassis ID/MAC and chassis serial are normalized as identity tokens. A token can resolve an observation only when it uniquely identifies one inventory device; conflicting tokens or non-unique tokens make the edge `AMBIGUOUS`, and ambiguous edges are never traversed for impact analysis. No fuzzy hostname or topology guessing is used.

Downstream impact is a bounded, cycle-safe traversal of **observed resolved managed L2 adjacency only**. It can be scoped to a root device and optional first-hop local port. It is explicitly not a routing, STP, application, or power dependency claim. CLI adds `netconfig topology --identities` and `netconfig topology --impact DEVICE`; REST adds `/api/v1/topology/identities` and `/api/v1/topology/impact/{device}` under `topology:read`; the Topology Web page now shows normalized identity, resolution evidence, ambiguity counts and downstream-impact analysis.

Executed source-workspace evidence: full pytest **83 passed / 3 skipped**; NI-2 focused **8 passed**. Live representative-vendor LLDP/ENTITY-MIB/IF-MIB semantics, service-backed integrations, RPM build/install and Ruff/mypy remain deferred/not run in this environment.

### NI-2 artifact delivery gate

Candidate artifact clean-extraction qualification passed: 104/104 complete file identity, 100/100 release payload and SHA manifests, exact hidden-file paths, 0755 launcher/helper preservation, archive-security/hygiene checks, and extracted regression **83 passed / 3 skipped** with NI-2 focused **8 passed** and selftest **ALL PASS**. Final FULL package is rebuilt after this evidence is recorded.

NI-2 prefinal clean-extraction gate reproduced the candidate package evidence after documentation synchronization: 100/100 release payload validation, 0755 executable modes, pytest 83/3, focused NI-2 8/8 and selftest ALL PASS. The final FULL source ZIP is rebuilt from this state.

## 2026-09-11 — Network Intelligence NI-3: SNMP Traps & Dependency-aware Events

Implemented `operational_events.py` and `snmp_trap.py`; additive `operational_events` / `operational_suppressions` persistence; v1/v2c trap normalization; v3/INFORM fail-closed boundaries; syslog and SNMP reachability normalization; dedup, bounded targeted re-poll and NI-2 dependency suppression; CLI/API/Web read surfaces; settings and `events:read`. Source-workspace evidence is **91 passed / 3 skipped**, focused NI-3 **8 passed**, selftest/compile/shell PASS.

NI-3 candidate packaging integrity gate passed with 107/107 full-file identity, 103/103 payload manifests, preserved hidden paths and 0755 modes, and clean-extraction regression **91 passed / 3 skipped** plus focused **8 passed**. Final artifact is rebuilt after this ledger update so the delivered manifests cover the synchronized documentation.


## 2026-09-11 — Network Intelligence NI-4: Operational Alert & Reporting Lifecycle

Implemented `operational_alerts.py` plus additive `operational_alerts`, `maintenance_windows`, `notification_deliveries`, `report_schedules`, and `report_runs` persistence. NI-3 events at/above the configurable severity floor promote to operational alerts only when they are not topology-suppressed and not inside a matching maintenance window. Deduplicated NI-3 events touch the same alert. Added audited acknowledge/resolve lifecycle, bounded durable SMTP retry/backoff, scheduled aggregate operational reports, CLI/API/Web surfaces, role-gated write scopes, and opt-in lifecycle scheduler settings. Existing monitor-rule alerts remain separate. Source-workspace evidence: **99 passed / 3 skipped**, focused NI-4 **8 passed**, selftest/compile/shell PASS.


### NI-4 candidate artifact evidence

Candidate `netconfig_network_intelligence_ni4_candidate_2026-09-11.zip` SHA-256 `17ed1297a863eaca2eeb4a92f5bddcf3ab120804d2526c63339bda79ae1569e3` passed clean system-unzip validation: **109/109** artifact files present, **105/105** Release payload entries and each of the three SHA manifests verified, exact hidden paths retained, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the NI-4/PH-1/Release-28 current-state pointer. Extracted regression: **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## 2026-09-11 — Platform Hardening PH-1 — Web-console Structural Hardening

Implemented structural/security decomposition without changing product routes or API semantics. `web.py` moved Bearer API routing into `web_api.py` and UI assets/helpers into `web_ui.py`; current dispatcher size is below 4,000 lines and 240 KB. Enforced CSP now requires per-response nonces for script/style elements and denies script/style attributes; server-rendered style attributes are converted to deterministic classes in one nonce-authorized style block. HTML event-handler attributes were removed in favor of delegated events. Dynamic graph device names are escaped before script context, and vault-secret names are rendered through `textContent`. Source regression: **105 passed / 3 skipped**; focused PH-1: **6 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**. Session idle/absolute expiry remains deliberately deferred.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## 2026-09-11 — Platform Hardening PH-2 — PostgreSQL Core & Distributed Operation

Status: `IMPLEMENTED_TESTING_DEFERRED`.

Implemented:

- Added explicit `core_db_backend=sqlite|postgres`; SQLite remains the default single-node development backend.
- Added `postgres_core.py`, which bootstraps the full NetConfig core schema on PostgreSQL, translates the existing qmark SQL surface to psycopg placeholders, and provides compatibility for the bounded SQLite `INSERT OR IGNORE/REPLACE` forms used by current code.
- PostgreSQL schema generation converts SQLite `AUTOINCREMENT`, `REAL`, and `BLOB` types to PostgreSQL-compatible `BIGSERIAL`, `DOUBLE PRECISION`, and `BYTEA` equivalents.
- Added schema-revision evidence in `storage_meta` (`ph2-1`) and storage-aware `/readyz` reporting.
- Added protected pre-vault core PostgreSQL credential resolution: `NETCONFIG_DB_PASSWORD_FILE`, systemd `$CREDENTIALS_DIRECTORY/postgres-core-password`, then legacy `NETCONFIG_DB_PASSWORD`. Core DB passwords are never written to `settings.json`.
- Added cluster-node registration/heartbeat and session-scoped PostgreSQL advisory locks for singleton background schedulers.
- Added durable `distributed_tasks` and PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` claiming. SQLite retains process-local single-node claim semantics and is not advertised as distributed-capable.
- Added `netconfig storage status|tasks|enqueue|claim|finish|migrate-sqlite` operator tooling.
- Added fail-closed SQLite→PostgreSQL migration: target application tables must be empty by default; IDs are preserved and PostgreSQL sequences repaired after import.
- Existing interface-history PostgreSQL support remains separate and compatible; the same host/database settings may be reused, but its vault-held password is not used for core startup.
- Updated Web Database settings, systemd credential guidance, readiness, and startup write diagnostics.

Validation completed locally:

- PH-2 focused: 9 passed.
- Full repository: 114 passed / 3 skipped.
- Existing PH-1/NI/D.5 regressions remain green.

Deferred / not claimed:

- Live PostgreSQL server schema bootstrap and data migration.
- Multi-node PostgreSQL contention, HA/failover, advisory-lock failover, and real SKIP LOCKED worker races.
- PostgreSQL backup/restore/point-in-time recovery qualification.
- AlmaLinux packaged psycopg installation and RPM/systemd PostgreSQL deployment.
- Production connection pooling and measured distributed scale.

### PH-2 candidate artifact gate

Candidate `netconfig_platform_hardening_ph2_candidate_2026-09-11.zip` SHA-256 `6dfd6e554b08883c51a6f268bbe604bf95cc7819dad8f4bda6f023d688807d21` passed clean system-unzip validation: **114/114** source-file byte identity, **110/110** `RELEASE_MANIFEST.json` payload and each of the three SHA manifests, exact hidden paths, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the PH-2/PH-3/Release-30 current-state pointer. Extracted regression: **114 passed / 3 skipped**, focused PH-2 **9 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.


## 2026-09-12 — Platform Hardening PH-3 — Structured Southbound Adapters

Status: `IMPLEMENTED_TESTING_DEFERRED`. Historical mapping: Slice G.

### Implemented

- Preserved durable per-device `protocol_profiles`, runtime vault credential resolution, explicit opt-in CLI fallback, profile rename/delete integration, metadata-only structured protocol traces, and `protocol:read` / role-gated `protocol:write` surfaces.
- NETCONF now performs SSH-subsystem server hello/capability negotiation, requires base:1.0 framing support, records candidate/writable-running/startup/confirmed-commit/rollback-on-error/validate/xpath capabilities, exposes fixed bounded `<get>` and `<get-config>` reads, fails closed when a requested datastore is not advertised, and enforces XML byte/node/depth limits with DTD/entity rejection. No caller-supplied RPC XML is exposed.
- RESTCONF now performs HTTPS root discovery with optional host-meta discovery, validates hosts and confines paths/queries to allow-listed RESTCONF resources, validates response content types and bounded JSON/XML payloads, supports CA bundles and vault-resolved mTLS material, and refuses disabled certificate verification unless the lab-only `NETCONFIG_ALLOW_INSECURE_STRUCTURED_TLS=1` override is explicitly set.
- Added an internal approval-gated RESTCONF JSON subtree replacement primitive. It requires a named actor, an approved-change signal and a callable post-read verifier; it performs pre-read, conditional replace where ETag is available, post-read verification, and best-effort pre-image rollback on failure. This primitive is intentionally not exposed as generic Web/API/CLI URL/method/body passthrough.
- gNMI now supports Capabilities, Get and bounded ONCE Subscribe through an allow-resolved absolute `gnmic` binary. Paths use a typed validator/renderer, deadlines and response-size limits are enforced, TLS verification is fail-closed by default, CA/mTLS material is resolved at runtime, secrets are written only to a mode-0600 ephemeral config file and never placed in argv, and error output is secret-redacted. gNMI Set remains deliberately unexposed.
- Added manager/CLI read surfaces for structured capabilities, operational state and gNMI ONCE Subscribe, plus bearer API read endpoints for protocol capabilities/state. Existing Web profile/collect RBAC and CSRF behavior remains unchanged.
- Added hard byte limits to subsystem reads in `SSHTransport` while preserving existing CLI behavior.
- Added missing canonical `README.md`.

### Security and compatibility decisions

- No generic NETCONF RPC, arbitrary RESTCONF URL/method/body forwarding, arbitrary protobuf request, shell tunnelling, or gNMI Set.
- Production RESTCONF/gNMI certificate verification is mandatory by default. The only insecure TLS path is an explicit environment-gated lab override.
- Structured network writes remain subordinate to existing change/approval safety. The only new write primitive is internal and explicitly approval-gated; existing public API/CLI does not expose generic structured mutation.
- Protocol traces remain metadata-only and exclude payload/body/RPC/protobuf/authorization/user/password fields.
- Session idle timeout / absolute expiry remains deliberately deferred and was not changed.
- NETCONF base:1.1-only chunk framing, full NETCONF edit/commit transaction execution, and gNMI Set are not claimed.

### Offline verification before final artifact packaging

- Focused PH-3: **21 passed**.
- Full repository: **136 passed / 3 skipped**.
- The three skips remain the service-backed OpenSSH, Net-SNMP and PostgreSQL integration tests.

Final packaging/selftest/compile/shell/manifest evidence is recorded in `TESTING_RESULT_2026-09-12.md` after the final artifact gate.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

### Deferred/live gates

- real NETCONF server/device and base:1.1-only peers
- real RESTCONF device and vendor YANG/path behavior
- real gNMI endpoint and packaged `gnmic` interoperability
- Cisco/Juniper/Arista/Huawei structured-protocol behavior
- TLS/mTLS certificate interoperability and production credential rotation
- real PostgreSQL service/multi-node/HA/failover/PITR/backup-restore
- service-backed OpenSSH and Net-SNMP
- AlmaLinux RPM build/install and systemd qualification
- Ruff, mypy, scale/concurrency/failure testing, SMTP/O365

### Continuation

No next implementation phase is assigned. Perform the roadmap / qualification review required by the handover before naming another implementation phase.
