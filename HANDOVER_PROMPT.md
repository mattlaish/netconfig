# New Chat Handover Prompt

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.

## Release 34 continuation prompt

Start from the Release 34 FULL source baseline, not Release 33 and not a patch. UI-1 is implemented in source and remains `IMPLEMENTED_TESTING_DEFERRED`. The `/operations` console covers Structured Changes, Telemetry, Model Packs, Desired State, Campaigns, and HA/DR. Do not rebuild these panels from scratch.

All network mutations must continue through durable change requests with frozen snapshot/hash review and separate approval. Do not add a browser bypass, caller-declared approval, arbitrary RPC/URL/protobuf passthrough, or direct device writes. Keep `web.py` below the PH-1 structural gate and place further Operations UI work in `web_ops.py`. Q-1 live qualification and session-expiry debt remain open.


## Release 33 handoff truth

The latest implementation baseline is Release `2.0.0-33`, schema revision `ha1-2`. PH-4, NI-5, VM-1, NA-1, NA-2 and HA-1 are implemented in source and remain `IMPLEMENTED_TESTING_DEFERRED`. Q-1 remains open for production/runtime service-backed qualification. Do not restart PH-3/Q-1 and do not invent the next phase before consolidated Release 33 verification and a new roadmap review.

Preserve these Release 33 invariants: all network mutations use the durable request/approve/execute workflow; automation snapshots/model-pack hashes are frozen and revalidated; `RECOVERY_REQUIRED` blocks blind replay; desired-state rollback is compensating/reverse-order; campaign plans are frozen with stable retry identity; DRAINING/DRAINED HA nodes reject new automation work. Session idle/absolute expiry is still explicitly deferred.

> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

## Historical Q-1 takeover truth

This section records the historical Q-1 handover checkpoint. Q-1 remains `IMPLEMENTED_TESTING_DEFERRED`, but Release 33 supersedes it as the active implementation baseline. Do not restart PH-3/Q-1 or discard their qualification boundaries.

Q-1 source implementation includes `netconfig qualify`; controlled `pg_dump` backup; checksummed, confirmation-gated restore into a separate database; recovery-safe restore without active-core initialization; live PostgreSQL multi-process/leadership/migration/recovery tests; CI PostgreSQL client provisioning; AlmaLinux 10 build/install qualification scripts; Ruff/mypy fail-closed source gate; and systemd backup-unit hardening.

The Q-1 live qualification debt remains: execute the real PostgreSQL gates, Ruff/mypy, and AlmaLinux 10 RPM/systemd installed-runtime gates when suitable infrastructure is available. Do not count `NOT_RUN` as pass. Release 34 UI-1 offline/artifact evidence does not substitute for those live gates.

I am handing over the NetConfig project at **Release 34 / UI-1 implementation baseline**. UI-1 is implemented over PH-4, NI-5, VM-1, NA-1, NA-2 and HA-1 and remains `IMPLEMENTED_TESTING_DEFERRED`. Use the Release 34 FULL source baseline as the active source of truth; Release 33 is the verified parent baseline and Q-1 remains an open qualification track.

Read these first: `DEV_BASELINE.md`, `TESTING.md`, `ROADMAP.md`, `SECURITY.md`, `API.md`, `DEVELOPMENT.md`, `AI_HANDOFF.md`, then the relevant source under `opt/netconfig/netconfig/` and `tests/`.

Important constraints:

- The user handles Git manually. Do not pull/fetch/add/commit/push or mutate repository history/remotes unless explicitly authorized in that chat.
- Deliver implementation changes as a complete modifiable source baseline with tests and packaging/deployment artifacts, not patch-only or documentation-only output.
- Preserve standard-library-first architecture unless a dependency is explicitly justified and approved.
- Console sessions still have no idle/absolute expiry. This is known deferred security debt. Do not implement session expiry unless the user explicitly selects it.
- Do not weaken fail-closed remediation/rollback, secret handling, bearer-token TLS enforcement, token hash-only storage, RBAC/audit, syslog bounds/source correlation, diagnostic redaction/path controls, or incident evidence reference integrity.
- Do not claim Ruff, mypy, RPM, Linux service, protocol-service, or live-device results unless actually run.
- Keep `DEVELOPMENT.md`, `AI_HANDOFF.md`, `ROADMAP.md`, `SECURITY.md`, `API.md`, `TESTING.md`, `patch.md`, and relevant user docs synchronized.

Roadmap structure: the historical 2026-09-07 Slice A-G labels are provenance only. Use `ROADMAP.md` as canonical. **CURRENT IMPLEMENTATION BASELINE is UI-1 / Release 34. NEXT ACTION is applicable Q-1/live qualification followed by roadmap review; no new development phase is auto-assigned.** D.5 is the completed-in-source Diagnostics Track, not Slice E. Historical Slice E remains Platform Hardening -> Web-console structural hardening.

Current D.5 implementation invariants:

- Phase 4A durable Incident lifecycle and Phase 4B reference-only evidence/timeline model remain authoritative.
- SQLite adds `incident_case_exports` additively. Managed archives live under `case-exports/`; diagnostic source bundles remain under `debug-bundles/`.
- A case archive contains Incident-owned metadata, `evidence-links.json`, reference-only `timeline-references.json`, selected linked diagnostic bundles copied byte-for-byte, `README.txt`, `manifest.json`, and `manifest.sha256`.
- Raw authoritative syslog/audit/compliance/config bodies are not copied into case indexes. Explicit unlinked/missing selected bundles fail closed; default all-linked export records pruned linked bundles as missing metadata.
- Export is bounded to 32 diagnostic bundles / 512 MiB aggregate bundle input. Common credential-assignment strings in free-text case metadata are redacted.
- CLI adds `incident export-case|exports`. API adds `/api/v1/incidents/{id}/exports` create/list and `/exports/{export_key}` secure download.
- Dedicated `incident:export` requires operator/approver/admin role. Export create/download is audited.
- Phase 4D signing/verification, Phase 4E bounded protocol trace capture, Phase 4F Incident Web Console, and D.5 closeout retention controls are implemented. Automatic event-correlation rules and external qualification gates remain deferred.

Historical D.5 closeout result: pytest **67 passed / 3 skipped**; focused closeout tests **3 passed**; legacy selftest **ALL PASS**. Current NI-1 regression is **75 passed / 3 skipped**, with focused NI-1 **8 passed** before this Markdown synchronization. Ruff/mypy and live/service-backed qualification remain unavailable/deferred. Re-run applicable tests after any change.

If I say “next phase”, first determine whether the deferred Q-1 live gates have actually been completed. If Q-1 is still `IMPLEMENTED_TESTING_DEFERRED`, continue qualification rather than inventing Q-2. Once Q-1 is genuinely qualified, perform a fresh roadmap review before selecting any next phase. Preserve PH-3 bounded structured-adapter semantics, PH-2 database/distributed-operation truth boundaries, PH-1 CSP/structural hardening, and all completed Network Intelligence/D.5 security invariants.


Phase 4D signing invariants:
- private signing keys are external only (`$CREDENTIALS_DIRECTORY/evidence-signing-key.pem` preferred);
- only Ed25519 keys with restrictive permissions are accepted;
- a configured invalid key must fail closed, never silently downgrade;
- embedded public keys prove cryptographic validity only, while authenticity requires an independent SHA-256 SPKI trust pin;
- preserve backward compatibility for existing unsigned evidence unless signing-required policy is enabled.


Phase 4E trace invariants:
- trace capture is explicit, TTL/event/byte bounded and audited;
- SSH traces never store raw terminal output or credentials; secret-bearing commands become a constant redaction marker with no original-secret-derived hash;
- SNMP traces never store packet bodies, communities or v3 auth/priv material;
- Incident trace linkage is reference/evidence based; case/debug exports include only sanitized trace metadata;
- Historical Phase 4E rule only: NETCONF/RESTCONF trace start failed closed before providers existed. PH-3 implements NETCONF/RESTCONF/gNMI metadata trace providers; continue to preserve bounded metadata-only capture.

D.5 closeout and Phase 4F packages are historical predecessors. The NI-1 package named below is also historical; the PH-3 FULL source baseline named below was the active continuation baseline at that historical point; the active continuation is now Q-1.


Phase 4F Web Console invariants:
- `/incidents` and `/incident` are authenticated human-operator surfaces over existing services, not a new source of truth;
- viewer is read-only; browser mutation requires operator/approver/admin plus CSRF;
- case downloads must reuse integrity/signature/trust verification;
- render Incident-controlled content escaped;
- never permit a trace linked to one Incident to be stopped through another Incident;
- session idle/absolute expiry remains deferred unless explicitly selected.


### Historical D.5 closeout update

The historical D.5 closeout baseline completed the planned D.5 feature phases and closeout maintenance controls. D.5 remains `IMPLEMENTED_TESTING_DEFERRED` because Ruff/mypy, service-backed integration, RPM and live-device qualification are still outstanding. If asked to continue product development without another selection, start with **VLAN-aware endpoint and topology correlation**; do not reopen D.5 feature work unless a concrete defect or deferred qualification item is selected. Session expiry remains deliberately deferred.


Historical D.5 delivery package: `netconfig_d55_closeout_roadmap_refresh_repacked_FULL_source_baseline_2026-09-11.zip`; it is superseded by the NI-1 baseline.


## Historical continuation snapshot — Network Intelligence NI-1

Historical NI-1 note: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip` superseded the earlier D.5 closeout and pre-refresh NI-1 ZIP. At that point CURRENT was **NI-1 VLAN-aware Endpoint Attachment Correlation — IMPLEMENTED_TESTING_DEFERRED** and NEXT was **NI-2 Topology Identity & Downstream Impact**. Preserve the NI-1 invariants: no FDB-ID==VLAN guessing, neighbour-facing ports are transit, multiple direct candidates remain ambiguous, stale evidence is not treated as current, and `endpoint:read` is read-only. RPM source Release is `2.0.0-25`; no RPM/live-vendor qualification is claimed.

Historical NI-1 artifact: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. It is provenance only and must not replace the active Q-1 baseline.


Markdown synchronization validation: Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**. Use `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip` after its final artifact gate.

## Historical continuation snapshot — Network Intelligence NI-2

Historical note: `netconfig_network_intelligence_ni2_FULL_source_baseline_2026-09-11.zip` was the NI-2 baseline. At that historical point the NI-3 FULL source baseline became active and **CURRENT = NI-3 SNMP Traps & Dependency-aware Events — IMPLEMENTED_TESTING_DEFERRED; NEXT = NI-4 Operational Alert & Reporting Lifecycle**. That state is chronology only; the active baseline is Q-1, with PH-3 as the latest feature baseline. Preserve fail-closed unique identity resolution, explicit ambiguity, the LLDP-localPortNum/ifIndex separation, and the `observed_managed_l2_adjacency` truth boundary.

NI-2 candidate artifact evidence: **104/104** stage/extracted identity, **100/100** release payload and each SHA manifest, exact hidden paths, 0755 executable preservation, extracted pytest **83 passed / 3 skipped**, focused NI-2 **8 passed**, selftest **ALL PASS**. Use only the final FULL NI-2 artifact after it reproduces this gate.


## Historical continuation snapshot — Network Intelligence NI-4

Historical NI-4 note: `netconfig_network_intelligence_ni4_FULL_source_baseline_2026-09-11.zip` was the final NI-4 source baseline. Preserve NI-4 invariants: NI-3 dependency-suppressed events do not page; active maintenance suppresses alert promotion but never deletes event evidence; notification retries are bounded; scheduled reports store aggregate operational evidence only; `alerts:write`/`reports:write` require operator-or-higher; browser mutations require CSRF. The legacy monitor-rule alert subsystem remains separate. Next phase is **PH-1 Web-console Structural Hardening**.


NI-4 candidate artifact gate passed with 109/109 files, 105/105 payload manifests, exact hidden paths, preserved 0755 modes, and extracted 99/3 + focused 8 + selftest/compile/shell PASS. Final continuation must use `netconfig_network_intelligence_ni4_FULL_source_baseline_2026-09-11.zip` only after its own clean-extraction gate.

## 2026-09-11 — Historical baseline: Platform Hardening PH-1

Historical PH-1 snapshot: PH-1 decomposes the Web console without changing routes/API semantics: `web.py` delegates bearer API handling to `web_api.py` and presentation/assets to `web_ui.py`; strict per-response CSP nonces are enforced for script/style elements; HTML event/style attributes are denied after render normalization. Current source regression is **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**. Source RPM metadata is `2.0.0-29`. Intended complete artifact: `netconfig_platform_hardening_ph1_FULL_source_baseline_2026-09-11.zip` after final artifact gate. Next recommended phase at that historical point: **PH-2 — PostgreSQL Core & Distributed Operation**.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## Historical completion snapshot — PH-2

Historical PH-3 closeout artifact: `netconfig_platform_hardening_ph3_FULL_source_baseline_2026-09-12_completed.zip`. At that point CURRENT was **PH-3 NETCONF / RESTCONF / gNMI Structured Adapters — IMPLEMENTED_TESTING_DEFERRED** and NEXT ACTION was a roadmap / qualification review. That review selected Q-1; do not revert CURRENT back to PH-3. Preserve PH-3 invariants: NETCONF only emits fixed bounded internal read RPCs; RESTCONF uses validated HTTPS discovery/read paths and exposes no generic URL/method/body passthrough; the internal RESTCONF subtree replace is approval-gated with pre/post verification and rollback; gNMI supports Capabilities/Get/bounded ONCE Subscribe but not Set; credentials remain runtime vault-backed and are never placed in gNMI argv; structured failure does not silently fall back to CLI unless the per-device profile explicitly opts in. Preserve PH-2 database invariants as well. Do not claim live vendor/PostgreSQL/RPM qualification without actual evidence.


## Historical PH-3 closeout — complete in source

PH-3 is `IMPLEMENTED_TESTING_DEFERRED` and implements the bounded structured-adapter contract:

- NETCONF SSH subsystem hello/capability negotiation, fixed `<get>`/`<get-config>`, datastore/candidate/startup and confirmed-commit/rollback capability evidence, strict response/XML limits, no arbitrary RPC or edit-config; base-1.1-only chunk framing remains deferred/fail-closed.
- RESTCONF HTTPS discovery, strict host/path/query/content validation, production TLS verification, optional CA and vault-resolved mTLS, bounded JSON/XML, plus an internal approval-gated JSON subtree replace with pre-read/post-read verification and best-effort pre-image rollback. Generic URL/method/body mutation is not publicly exposed.
- gNMI Capabilities/Get and bounded ONCE Subscribe with typed paths, deadlines, response limits, TLS/mTLS, mode-0600 ephemeral credential config and secret-free argv. gNMI Set is not exposed.
- Runtime vault secret resolution, metadata-only protocol trace, durable audit evidence, fail-closed structured errors and explicit-only CLI fallback.

Offline source evidence before final packaging: **136 passed / 3 skipped**; focused PH-3 **22 passed**. The skipped tests are service-backed OpenSSH, Net-SNMP and PostgreSQL and remain deferred. Do not claim live NETCONF/RESTCONF/gNMI, vendor, TLS/mTLS, packaged `gnmic`, PostgreSQL HA, RPM/systemd, Ruff/mypy, scale/failure, backup/restore/PITR or SMTP/O365 qualification unless actually executed.

Use the final PH-3 full source baseline from 2026-09-12 after its clean-extraction artifact gate. Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable. The next action is the required roadmap / qualification review; do not assign another implementation phase automatically.


# Canonical Architecture Split — PH vs NI

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

Status: `PLANNED`

Scope:

- SNMP polling
- gNMI telemetry
- Streaming metrics
- Interface statistics
- CPU/memory/environment telemetry
- Time-series storage
- Trend analysis
- Performance baseline

## NI-6 — Discovery Analytics

Status: `PLANNED`

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
