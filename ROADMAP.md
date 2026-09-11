# Roadmap

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

> **Current continuation pointer:** use the Q-1 full source baseline from 2026-09-12 as the active source. Historical CURRENT/NEXT statements below are chronology only. Execute the remaining Q-1 live gates before any promotion to `TESTED`/`RELEASED`; after Q-1 qualification, perform a fresh roadmap review before assigning Q-2.

Status vocabulary for new work: `PLANNED`, `IMPLEMENTED_TESTING_DEFERRED`, `TESTED`, `RELEASED`. Older `IMPLEMENTED` labels predate this vocabulary and should not be interpreted as live-environment qualification.

## Current execution roadmap summary

Only the status vocabulary `PLANNED`, `IMPLEMENTED_TESTING_DEFERRED`, `TESTED`, and `RELEASED` is authoritative for current work. Historical prose later in this file is retained only for provenance.

- **Diagnostics D.5:** `IMPLEMENTED_TESTING_DEFERRED` — feature-complete in source.
- **Network Intelligence NI-1 through NI-4:** `IMPLEMENTED_TESTING_DEFERRED` — complete in source; representative live-device/service qualification remains outstanding.
- **Platform Hardening PH-1:** `IMPLEMENTED_TESTING_DEFERRED` — Web-console structural hardening complete in source.
- **Platform Hardening PH-2:** `IMPLEMENTED_TESTING_DEFERRED` — PostgreSQL core/distributed operation complete in source, with real service-backed qualification debt.
- **Platform Hardening PH-3:** `IMPLEMENTED_TESTING_DEFERRED` — bounded NETCONF/RESTCONF/gNMI structured adapters complete in source, with real vendor/TLS interoperability debt.
- **Qualification Q-1:** `IMPLEMENTED_TESTING_DEFERRED` — current track. Source implementation and offline regression are complete; live PostgreSQL, AlmaLinux RPM/systemd, Ruff/mypy and service-backed gates are not yet all executed in this environment.

Session idle/absolute expiry remains explicitly deferred security debt and is not part of Q-1. No Q-2 is assigned.

### Q-1 — Production Runtime & Service-backed Qualification — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source:

- release/version truth reconciled: Python package/project/RPM Version `2.0.0`, RPM source Release `32`;
- configuration-aware `netconfig qualify` runtime preflight for active storage and required external executables;
- controlled PostgreSQL core backup using atomic custom-format `pg_dump`, SHA-256 sidecar, mode-0600 output and non-interactive authentication;
- controlled PostgreSQL restore drill requiring SHA-256 verification, explicit `RESTORE_DATABASE` confirmation, and a target database different from the active core database;
- PostgreSQL client passwords are delivered only through a short-lived mode-0600 `PGPASSFILE`, never argv; configured libpq SSL mode is preserved;
- recovery-safe restore CLI path does not require opening the active core database before restoring a separate drill/standby target;
- real PostgreSQL service-backed tests for two-node `FOR UPDATE SKIP LOCKED` claim exclusivity, advisory-lock leadership/release on session loss, node heartbeat visibility, SQLite-to-PostgreSQL migration/sequence repair, and pg_dump/pg_restore recovery drill;
- GitHub Actions integration tier now provisions PostgreSQL client tools and executes the Q-1 PostgreSQL live gates when CI runs;
- AlmaLinux 10 qualification harness separates non-mutating RPM build/inspection from explicit disposable-host `--install`; install requires `NETCONFIG_Q1_ALLOW_INSTALL=1`;
- RPM build no longer incorrectly invokes installed-RPM smoke before installation; installed smoke now runs the Q-1 runtime preflight and checks systemd hardening;
- backup systemd unit hardened to the same filesystem/process baseline as the Web service and documents the pre-vault PostgreSQL systemd credential;
- source qualification harness fails closed when Ruff/mypy are absent instead of reporting skipped tooling as success.

Current environment evidence:

- Q-1 focused offline tests: **11 passed**;
- full offline repository: **147 passed / 7 skipped** before final artifact packaging;
- the seven skips are three existing OpenSSH/Net-SNMP/PostgreSQL-history service tests plus four new Q-1 PostgreSQL live gates;
- Ruff/mypy: `NOT_RUN` because the tools are absent and this isolated environment cannot resolve packages;
- PostgreSQL service-backed Q-1 gate: `NOT_RUN` because `pg_dump`/PostgreSQL service tooling is absent;
- AlmaLinux RPM/systemd installed qualification: `NOT_RUN` because the current host is Debian 13, not AlmaLinux 10.

Q-1 remains `IMPLEMENTED_TESTING_DEFERRED`. It must not be promoted until the applicable live gates are actually executed and recorded. After Q-1 qualification, perform a new roadmap review; do not invent Q-2 automatically.

## Current execution roadmap

The lettered Slice A-G sequence below was created for the 2026-09-07 handover as a prioritization aid. It is no longer the primary execution numbering. Current development follows named tracks and numbered track phases; the historical mapping is retained later for provenance.

**Numbering clarification:** D.5 is the standalone Diagnostics Track, not Slice E. Network Intelligence is the active product-development track. The historical Slice B work is being implemented as explicit Network Intelligence phases so completed scope is not overstated.

### Historical current — Network Intelligence Phase NI-1: VLAN-aware Endpoint Attachment Correlation — IMPLEMENTED_TESTING_DEFERRED

- Added IP-MIB `ipNetToPhysicalTable` IPv4/IPv6 neighbour collection with explicit legacy `ipNetToMediaTable` fallback provenance.
- Added Q-BRIDGE-MIB FDB collection with `dot1qVlanFdbId` mapping and bridge-port -> ifIndex resolution. VLAN is reported only when FDB-ID -> VLAN mapping is unique; shared-learning ambiguity is never guessed.
- Added additive `ip_neighbors` and `vlan_fdb` evidence tables while preserving legacy ARP/MAC views for compatibility.
- Added fleet correlation for `IP -> MAC -> VLAN -> switch/port` with evidence freshness, explicit `ATTACHED`/`AMBIGUOUS`/`TRANSIT_ONLY`/`STALE`/`UNRESOLVED` states, and confidence labels.
- LLDP/CDP-facing ports are classified as transit observations, so MACs learned on uplinks are not silently promoted to direct endpoint attachments.
- Added `endpoint:read`, `GET /api/v1/endpoints`, `netconfig endpoints`, and an authenticated Endpoints Web page.
- Offline regression: **75 passed / 3 skipped**; NI-1 focused tests: **8 passed** before final packaging; final artifact-level evidence is recorded in `TESTING.md`.
- RPM source metadata is `2.0.0-25`; no RPM build/install or representative vendor qualification is claimed.

### Historical next at that point — Network Intelligence Phase NI-2: Topology Identity & Downstream Impact — PLANNED

- Enrich topology identity with chassis-ID subtype normalization, chassis MAC, serial/system identity and LLDP system capabilities where evidence exists.
- Resolve interface identity more robustly across LLDP local-port descriptions, ifIndex/ifName/ifDescr and vendor naming variants.
- Build deterministic downstream attachment/impact traversal over managed topology edges without treating inferred identity as authoritative fact.
- Preserve explicit ambiguity and source provenance; do not collapse conflicting observations.


### Markdown-state synchronization note — 2026-09-11

Historical synchronization note: at that checkpoint the project had moved to NI-3/NI-4 planning. The current canonical header and NI-4 section below supersede it; D.5 entries remain implementation history. Current source RPM Release is `2.0.0-28`.

## Diagnostics Track

This feature track is complete in source; external qualification remains outstanding.

- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4B — Incident Timeline.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4C — Support Case Export.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4D — Evidence / manifest signing and verification trust model.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4E — bounded, secret-safe protocol trace capture for CLI/OpenSSH and SNMP, with future structured-provider schema.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4F — Incident Web Console unifying lifecycle, timeline, evidence, traces, bundles and signed support-case workflow.
- **COMPLETED-IN-SOURCE — IMPLEMENTED_TESTING_DEFERRED:** D.5 closeout — opt-in bounded retention/scheduler controls implemented; offline qualification is green, while external CI/service/RPM/live-device gates remain deferred. D.5 is not the active feature track.
- **FEATURE TRACK COMPLETE:** No additional D.5 feature phase is planned before external qualification evidence. The next product-development track is VLAN-aware endpoint/topology correlation.

## Network Intelligence Track

The Network Intelligence track is complete in source through NI-4. All phases remain `IMPLEMENTED_TESTING_DEFERRED` until representative live-device/service qualification is executed.

### NI-1 — VLAN-aware Endpoint Attachment Correlation — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: IP-MIB IPv4/IPv6 neighbour collection, Q-BRIDGE VLAN-aware FDB/FDB-ID resolution, bridge-port→ifIndex mapping, conservative IP→MAC→VLAN→switch→port correlation, transit suppression, staleness/ambiguity handling, and CLI/API/Web visibility.

### NI-2 — Topology Identity & Downstream Impact — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: normalized LLDP/ENTITY-MIB/IF-MIB/chassis identity, managed-neighbour resolution with ambiguity fail-closed behavior, and bounded cycle-safe managed L2 downstream traversal.

### NI-3 — SNMP Traps & Dependency-aware Events — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: bounded SNMP v1/v2c Trap ingestion, normalized operational events, deduplication, targeted re-poll debounce, unified syslog/SNMP event stream, and NI-2 topology-aware temporary suppression. SNMPv3 Trap authentication/privacy and INFORM acknowledgement remain fail-closed/deferred.

### NI-4 — Operational Alert & Reporting Lifecycle — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: OPEN/ACKNOWLEDGED/RESOLVED operational alerts, maintenance windows, suppression provenance, durable notification queue with bounded retry/backoff, scheduled operational reports, and role-gated CLI/API/Web workflows. Notifications/lifecycle schedulers remain disabled by default unless explicitly configured.

## Platform Hardening Track

Historical A-G labels are provenance only. The canonical execution line is PH-1 → PH-2 → PH-3.

### PH-1 — Web-console Structural Hardening — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source: API/UI helper extraction, reduced `web.py`, per-response CSP nonces, `script-src-attr 'none'`, `style-src-attr 'none'`, inline-handler removal, style normalization, and script-context escaping regression coverage. Session idle/absolute expiry remains explicitly deferred.

### PH-2 — PostgreSQL Core & Distributed Operation — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source: explicit fail-closed PostgreSQL core backend, schema bootstrap/translation, sequence repair, cluster heartbeat, durable distributed tasks, PostgreSQL `FOR UPDATE SKIP LOCKED`, scheduler advisory locks, readiness/status, protected pre-vault database credentials, and SQLite→PostgreSQL migration tooling. SQLite remains single-node.

### PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source:

- NETCONF server hello/capability negotiation, fixed bounded `<get>` and `<get-config>` reads, advertised datastore awareness, confirmed-commit/rollback capability reporting, timeout/size limits, and DTD/entity-rejecting XML parsing. Base-1.1-only chunked framing remains deferred.
- RESTCONF HTTPS discovery, strict host/path/query validation, mandatory TLS verification unless an explicit lab-only environment override is set, CA-bundle support, vault-resolved mTLS material, bounded JSON/XML reads, and an internal approval-gated JSON subtree replace primitive with pre-read, post-read verification, and best-effort pre-image rollback. No generic URL/method/body passthrough is exposed through Web/API/CLI.
- gNMI Capabilities, Get, bounded ONCE Subscribe, typed paths, TLS/mTLS-capable runtime configuration, deadline/size enforcement, mode-0600 ephemeral credential config, and secret-free argv. gNMI Set remains deliberately unexposed.
- common fail-closed structured collection, explicit CLI fallback only, runtime vault credential resolution, durable audit/provenance, and metadata-only protocol trace evidence.

Offline evidence before final artifact packaging: **136 passed / 3 skipped**, focused PH-3 **22 passed**. The three skips are the existing service-backed OpenSSH, Net-SNMP, and PostgreSQL tests.

### After PH-3 — Qualification Track Q-1

The required roadmap review selected **Q-1 — Production Runtime & Service-backed Qualification**. Q-1 is implemented in source and currently `IMPLEMENTED_TESTING_DEFERRED`; its remaining live gates are listed in the canonical Q-1 section above. No Q-2 is assigned.

## Historical 2026-09-07 lettered handover mapping

The old A-G labels are retained only to interpret historical handover notes and patch entries; they are not the current execution sequence.
D.5 and Slice E are distinct historical entries: D.5 maps to Diagnostics; Slice E maps only to Platform Hardening / Web-console structural hardening.

| Historical label | Current track/location |
| --- | --- |
| Slice A — Qualification/release gates | Platform Hardening Track -> Qualification and release gate closure |
| Slice B — VLAN-aware endpoint/topology | Network Intelligence Track -> VLAN-aware endpoint and topology correlation |
| Slice C — SNMP traps/events | Network Intelligence Track -> SNMP traps and dependency-aware events |
| Slice D — Alert/reporting lifecycle | Network Intelligence Track -> Alert and reporting lifecycle |
| Slice D.5 — Diagnostics | Diagnostics Track |
| Slice E — Web-console hardening | Platform Hardening Track -> Web-console structural hardening |
| Slice F — PostgreSQL/distributed operation | Platform Hardening Track -> PostgreSQL core and distributed operation |
| Slice G — NETCONF/RESTCONF/gNMI | Platform Hardening Track -> Structured network protocols |

## Slice D.5 — Diagnostic & Support Bundle Framework
Status: IMPLEMENTED_TESTING_DEFERRED

Implemented initial diagnostic bundle foundation: redacted support bundle generation, manifest/checksum metadata, security redaction report, and CLI entry point (`netconfig debug collect`). Deferred: production archive retention policy, Web UI workflow, device-specific captures, and full incident bundle integration.


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


## Slice D.5 Phase 3C — Diagnostics Web Console + Secure Download (2026-09-10)

Status: IMPLEMENTED_TESTING_DEFERRED

- Added the authenticated Diagnostics console for support-bundle list/create/download workflow.
- Added CSRF-protected browser bundle creation and traversal-safe managed-bundle download with audit evidence.
- API download authorization, incident correlation, signing and protocol traces remained later work at this point.


## D.5 Phase 3D — Enterprise Diagnostic Operations

Status: IMPLEMENTED_TESTING_DEFERRED

Added secure debug bundle download API foundation, debug:download scope, RBAC/audit integration. Deferred: incident workflow, signed manifests, retention scheduler UI.


## Slice D.5 Phase 4A — Incident Model Foundation (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added durable `incidents` and `incident_bundles` state with additive SQLite schema creation.
- Added human-readable `INC-YYYY-NNNNNN` IDs, LOW/MEDIUM/HIGH/CRITICAL severity, OPEN/INVESTIGATING/RESOLVED/CLOSED lifecycle, bounded title/description/tags, update metadata, closure metadata, and explicit reopen semantics.
- Added audited CLI create/list/show/update/status/link-bundle/unlink-bundle operations.
- Added scoped JSON API foundation: `incident:read` and operator-or-higher `incident:write`, including create, read, status transition, and diagnostic-bundle link operations.
- Repaired the Phase 3D scope registry so `debug:download` and `debug:admin` are actually creatable by the API-token CLI.
- Kept incident timeline/event correlation, case export, signed manifests, protocol traces, and Incident Web UI out of 4A; those remain Phase 4B+ work.
- Console session idle/absolute expiry remains deliberately deferred and unchanged.

At Phase 4A completion, the next phase was **D.5 Phase 4B — Incident Timeline**; it is now implemented below.


## Slice D.5 Phase 4B — Incident Timeline (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added additive `incident_evidence_links` reference table; it stores only incident/source pointers and bounded link metadata, never copied syslog/audit/compliance/config payloads.
- Added evidence sources: `audit`, `syslog`, `collection`, `compliance`, and immutable `drift` references. Existing incident-bundle links and incident-native audit events are rendered into the same timeline.
- Drift evidence pins the baseline/current archived configuration stamps at link time so later collection cannot rewrite the historical comparison.
- Timeline dereferences authoritative records at read time. Retained links whose source has later been pruned/deleted remain visible as unavailable references instead of silently disappearing.
- Added CLI evidence/timeline operations and scoped REST timeline/evidence endpoints under the existing `incident:read` / operator-or-higher `incident:write` boundary.
- Case export, evidence signing, protocol trace capture, and Incident Web UI remain separate Phase 4C+ work. Console session idle/absolute expiry remains deliberately deferred.

At Phase 4B completion, the next phase was **D.5 Phase 4C — Support Case Export**; it is now implemented below.


## Slice D.5 Phase 4C — Support Case Export (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added managed `case-exports/` storage and additive `incident_case_exports` metadata with export key, filename, creator/time, reason, included/missing bundle indexes, archive size and SHA-256.
- Added bounded case-package generation containing `case.json`, `evidence-links.json`, `timeline-references.json`, selected linked diagnostic bundles, `README.txt`, `manifest.json`, and `manifest.sha256`.
- External audit/syslog/compliance/config bodies are not exported into case indexes. Timeline output is reduced to provenance/reference fields; diagnostic bundles are embedded as opaque byte-for-byte files rather than extracted or rewritten.
- Added dedicated `incident:export` bearer scope requiring operator-or-higher role, plus CLI `incident export-case|exports` and REST create/list/download workflow.
- Export creation/download is audited against the Incident. Explicitly requested unlinked/missing bundles fail closed; default exports preserve missing linked bundles as metadata instead of fabricating replacement evidence.
- Case export limits are 32 bundles / 512 MiB aggregate diagnostic-bundle input. Free-text case metadata applies credential-assignment redaction before export.
- At Phase 4C completion, SHA-256 integrity was implemented while cryptographic authenticity remained for Phase 4D; Phase 4D is now implemented below. Protocol trace capture remains Phase 4E and Incident Web Console remains Phase 4F.
- Console session idle/absolute expiry remains deliberately deferred and unchanged.

Historical Phase 4C next step was **D.5 Phase 4D — Evidence / Manifest Signing**; that phase is now implemented below.


## Slice D.5 Phase 4D — Evidence / Manifest Signing (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added fixed-function Ed25519 signing through the system OpenSSL binary without adding a Python crypto dependency or exposing a generic shell/signer command surface.
- Private signing keys remain external to NetConfig state. Resolution prefers systemd `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem`, then `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE`; key files must be regular non-symlink files with no group/world permission bits.
- Diagnostic bundles and support-case exports auto-sign when a valid signer is configured. `--require-signature`, `NETCONFIG_EVIDENCE_SIGNING_REQUIRED=1`, or the corresponding setting makes creation fail closed if signing is unavailable.
- Signed archives include the public key and signature metadata, while the private key is never embedded. Verification recomputes the manifest SHA-256 and every payload size/hash before validating the Ed25519 signature.
- Authentication trust is independent of the embedded key: SHA-256 SPKI fingerprint pins may be supplied by CLI, settings, or `NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS`; multiple pins support planned key rotation.
- Support-case export records persist signature state/algorithm/fingerprint via additive SQLite columns. Existing Phase 4C unsigned records remain compatible.
- Added CLI `incident verify-export`, `debug verify`, `debug signing-status`, API case-export verify and debug signing/verify surfaces, plus audit evidence for verification and signature failures.
- Signed case download still enforces the durable outer archive size/SHA-256 and additionally verifies the inner signature; configured trust pins fail closed on signer mismatch.
- Phase 4E protocol trace capture and Phase 4F Incident Web Console remain separate. Session idle/absolute expiry remains deliberately deferred.

Next: **D.5 Phase 4E — Protocol Trace Capture**.


## Slice D.5 Phase 4E — Protocol Trace Capture (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added additive `protocol_trace_sessions` and `protocol_trace_events` tables with explicit TTL, status, event budget and metadata-byte budget.
- Implemented `ProtocolTraceStore` with explicit start/stop/list/events lifecycle, audit evidence and optional automatic Incident evidence linkage.
- CLI/OpenSSH capture records connect/command metadata, result, duration and byte counts only. Sensitive commands are replaced by a constant marker before persistence; raw command secrets and terminal output are not trace evidence.
- SNMP capture is context-local and records target/port/attempt, duration and request/response byte counts at the UDP exchange boundary without recording BER packet bodies, community strings or v3 secrets.
- Incident timeline can resolve `protocol_trace` evidence; case exports include sanitized `protocol-traces.json`; diagnostic support bundles include bounded recent trace metadata.
- Added CLI `trace start|list|show|events|stop` and REST `/api/v1/traces` read/capture lifecycle using `trace:read` and role-gated `trace:capture`.
- Historical Phase 4E trace schema anticipated NETCONF/RESTCONF. PH-3 now implements NETCONF/RESTCONF/gNMI metadata trace providers while retaining the same evidence budgets.
- Offline regression: **59 passed / 3 skipped**; Phase 4E focused tests: **10 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**. Ruff/mypy remain NOT RUN in this environment.

Next: **D.5 Phase 4F — Incident Web Console**.


## Slice D.5 Phase 4F — Incident Web Console (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added `/incidents` register/filter UI and `/incident?ref=...` detail UI to the authenticated console.
- Viewer is read-only. Operator/approver/admin can create/edit Incidents, execute server-validated lifecycle transitions, link/unlink diagnostic bundles and reference-only evidence, and start/stop bounded CLI/SNMP traces.
- The detail view unifies Incident metadata, Phase 4B timeline/evidence, Phase 4E trace session/events, diagnostic bundles, and Phase 4C/4D support-case create/verify/download operations.
- All browser mutations retain CSRF checks. Case downloads call the existing integrity/signature verification path before chunked streaming.
- Rendering escapes Incident-controlled title/description/tags/evidence text. Cross-Incident trace stop is rejected.
- No new database schema or parallel Incident data model was introduced. Existing Incident/trace/export services remain authoritative.
- Offline regression after implementation: **64 passed / 3 skipped**; Phase 4F focused Web Console tests: **5 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell checks **PASS**.

Next: **D.5 Closeout / Diagnostic Qualification Review**.


## D.5 Closeout / Diagnostic Qualification Review (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added `diagnostic_maintenance.py` and opt-in background scheduling (`diagnostic_maintenance_interval`, default `0`).
- Added `debug_bundle_keep` (default `10`), `case_export_retention_days` (default `0`), and `protocol_trace_retention_days` (default `0`).
- Case-export cleanup preserves durable export metadata so Incident history shows an unavailable historical export instead of erasing the record.
- Protocol-trace cleanup is intentionally limited to inactive traces with no Incident linkage; Incident evidence is not automatically destroyed by generic retention.
- Added `netconfig debug maintenance` for explicit one-shot maintenance and Monitoring settings for the scheduler/policies.
- Offline closeout result: **67 passed / 3 skipped**, focused closeout **3 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**.
- Ruff/mypy, service-backed OpenSSH/Net-SNMP/PostgreSQL integration, AlmaLinux RPM build/install/systemd runtime, and representative live-device qualification remain **NOT RUN / DEFERRED** in this environment. Therefore D.5 remains `IMPLEMENTED_TESTING_DEFERRED`; feature completion is not equivalent to release qualification.
- Next product-development track: **VLAN-aware endpoint and topology correlation**.

## Network Intelligence progression update — 2026-09-11

### Historical current — NI-2: Topology Identity & Downstream Impact — IMPLEMENTED_TESTING_DEFERRED
- Normalize local LLDP chassis identity, ENTITY-MIB chassis serial/model/name and IF-MIB ifName/ifDescr/ifAlias/physical-address evidence.
- Resolve managed neighbours only when normalized identity evidence uniquely identifies one inventory device; contradictory/non-unique evidence remains `AMBIGUOUS`.
- Provide bounded, cycle-safe downstream traversal over resolved managed L2 adjacency, with optional first-hop root-port scoping in CLI/Web.
- Expose normalized identity and impact through CLI, `topology:read` REST endpoints, and the Topology Web console.
- Offline regression: **83 passed / 3 skipped**; focused NI-2 **8 passed** before final packaging. RPM source metadata: `2.0.0-26`.

### Historical next at that point — NI-3: SNMP Traps & Dependency-aware Events — PLANNED
- Bounded trap receiver for linkDown/linkUp, coldStart/warmStart and authenticationFailure.
- Strict source/device correlation, deduplication and debounce.
- Trigger targeted re-polls rather than fleet-wide polling.
- Merge trap, syslog and poll evidence into one operational event timeline.
- Use resolved topology identity/adjacency for dependency-aware downstream suppression while preserving ambiguity/fail-closed behavior.

## Network Intelligence NI-3 — SNMP Traps & Dependency-aware Events

### Historical current — NI-3 — IMPLEMENTED_TESTING_DEFERRED
- bounded UDP SNMP v1/v2c Trap receiver; default non-privileged port 5162 with external udp/162 forwarding when required
- SNMPv3 traps fail closed until an authenticated USM receiver is implemented; INFORM fails closed because acknowledgements are not implemented
- normalized coldStart/warmStart/linkDown/linkUp/authFailure plus enterprise trap OID preservation
- durable unified operational event stream for traps, syslog and SNMP reachability transitions
- bounded deduplication, targeted SNMP re-poll debounce, dependency suppression TTL
- suppression follows only NI-2 resolved managed-L2 adjacency and never ambiguous/unmanaged edges
- CLI `netconfig events`, Web Events page, and `GET /api/v1/events` with `events:read`
- offline evidence: **91 passed / 3 skipped**; focused NI-3 **8 passed** before packaging
- RPM source metadata: `2.0.0-27`; live Net-SNMP/vendor/RPM qualification remains deferred

### Historical next at that point — NI-4: Operational Alert & Reporting Lifecycle — PLANNED
- acknowledgement/resolution lifecycle, maintenance windows, notification retry/backoff, scheduled reporting, and bounded archive/search workflows


## Network Intelligence NI-4 — Operational Alert & Reporting Lifecycle

### Historical current — NI-4 — IMPLEMENTED_TESTING_DEFERRED
- Promote unsuppressed NI-3 events at/above a configurable severity threshold into a durable operational alert lifecycle.
- Lifecycle states: `OPEN`, `ACKNOWLEDGED`, `RESOLVED`; acknowledge/resolve are role-gated and audited.
- Device-scoped or fleet-wide maintenance windows suppress alert promotion while retaining the authoritative operational event and a durable maintenance-window reference.
- Optional SMTP alert/report delivery uses a durable queue with bounded attempts and exponential backoff; notification worker is opt-in (`operational_lifecycle_interval=0` by default).
- Scheduled operational reports persist run metadata and bounded aggregate summaries over events/alerts/suppressions; no raw trap/community/secret material is copied.
- CLI `netconfig alerts`, scoped REST (`alerts:read/write`, `reports:read/write`) and authenticated `/op-alerts` Web UI are implemented.
- Existing monitor-rule alerts remain a separate compatibility subsystem; NI-4 does not silently migrate or reinterpret them.
- Offline evidence: **99 passed / 3 skipped**; focused NI-4 **8 passed**; legacy selftest **ALL PASS**.
- RPM source metadata: `2.0.0-28`; live SMTP, service-backed integration, representative vendor trap and RPM/systemd qualification remain deferred.

### Historical next at that point — Platform Hardening PH-1: Web-console Structural Hardening — PLANNED
This is the modern continuation of historical Slice E. Decompose the monolithic Web console/server routing, reduce inline UI coupling, tighten CSP-compatible rendering and preserve all existing RBAC/CSRF/API/session truth boundaries. Session idle/absolute expiry remains separately deferred unless explicitly selected.

**Network Intelligence feature track status:** NI-1 through NI-4 are complete in source. External/live qualification remains outstanding and prevents promotion to `TESTED`/`RELEASED`.

## Platform Hardening PH-1 — Web-console Structural Hardening (2026-09-11)

### Historical PH-1 completion — IMPLEMENTED_TESTING_DEFERRED

- Extracted Bearer API routing from `web.py` into `web_api.py` and UI assets/render helpers into `web_ui.py`; `web.py` is now below the PH-1 structural gate of 4,000 lines / 240 KB.
- Enforced per-response CSP nonces for first-party script/style blocks. `script-src-attr 'none'` and `style-src-attr 'none'` are enforced; rendered `style=` attributes are normalized to deterministic nonce-authorized utility classes.
- Removed HTML inline event handlers and replaced destructive-action confirmations with delegated `data-confirm` handling.
- Hardened script-context rendering for dynamic device names and removed secret-name `innerHTML` rendering.
- Existing URL paths, API contract, RBAC, CSRF, session semantics and session-expiry deferral are preserved.
- Verification: source regression **105 passed / 3 skipped**; PH-1 focused **6 passed**; legacy selftest **ALL PASS**; compileall/launcher/package shell syntax **PASS**. Live browser matrix/RPM/service-backed qualification remains deferred.

### Historical next at PH-1 completion — PH-2 PostgreSQL Core & Distributed Operation

Move additional core state behind the storage boundary only with explicit multi-process semantics; add distributed job ownership/leases, duplicate-work prevention and failover tests before any HA claim.

## Platform Hardening PH-2 — PostgreSQL Core & Distributed Operation — HISTORICAL COMPLETION

State: `IMPLEMENTED_TESTING_DEFERRED`.

Implemented in source: optional fail-closed PostgreSQL core database, cross-dialect schema bootstrap/compatibility, schema-revision readiness, protected pre-vault DB credentials, cluster node heartbeat, PostgreSQL advisory-lock singleton schedulers, durable distributed task queue with `FOR UPDATE SKIP LOCKED`, and fail-closed SQLite→PostgreSQL migration tooling. SQLite remains the default single-node development backend.

External qualification still required before `TESTED`/`RELEASED`: real PostgreSQL service and migration drill, concurrent multi-node claims, advisory-lock leader failover, HA/connection-loss behavior, backup/restore/PITR, packaged psycopg and AlmaLinux RPM/systemd deployment, and measured scale.

## Platform Hardening PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters — HISTORICAL COMPLETION

State: `IMPLEMENTED_TESTING_DEFERRED`. Historical mapping: Slice G.

PH-3 now implements the full offline structured-adapter contract described above rather than the earlier read-only MVP. Network configuration mutation remains constrained: generic NETCONF RPC, generic RESTCONF URL/method/body forwarding, and gNMI Set are not exposed. The only structured write primitive currently present is an internal approval-gated RESTCONF JSON subtree replacement with mandatory pre-read, caller-supplied post-read verification, and best-effort pre-image rollback.

Current offline evidence before final packaging: **136 passed / 3 skipped**; focused PH-3 **22 passed**. Live structured-protocol vendor validation, TLS/mTLS interoperability, service-backed PostgreSQL/OpenSSH/Net-SNMP, packaged `gnmic`, AlmaLinux RPM/systemd, Ruff/mypy, scale/failure, and backup/restore/PITR remain deferred.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

### Historical next action after PH-3 — Roadmap / Qualification Review

That review was completed on 2026-09-12 and selected **Qualification Track Q-1 — Production Runtime & Service-backed Qualification**. Q-1 is now the current track; this PH-3 next-action text is chronology only.
