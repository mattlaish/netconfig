# New Chat Handover Prompt

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.
## Recorded continuation decisions — 2026-09-18

- No new development phase is assigned. Treat the following as future-design constraints, not implemented features.
- Distributed collection is primarily about **site survivability/alert-path resilience**, not merely scale. Central Controller owns global correlation/change control; Site Edge/Collector owns read-only local polling, local cache/spool, local health/alerts/UI, store-and-forward, and heartbeat.
- Collectors are read-only by default: SNMP GET/WALK, NETCONF/RESTCONF read, gNMI subscribe/read. No config push or arbitrary SSH by default. Future writes require a separate Execution Node or explicitly authorized execution role.
- Local alerts must survive central/WAN isolation and synchronize after reconnect; fallback notification channels are future work.
- Use **Configuration Baselines / Templates & Drift** as the preferred user-facing terminology.
- Keep existing approval functionality but do not expand approval orchestration now.
- MIB UX should favor operator-readable sensor summaries from existing collected evidence; raw OIDs remain Advanced, and visualization alone must not add polling load.


## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


> **Latest complete-source target:** `netconfig-2.0.0-46-operator-health-cards-v18.zip` (Release 46 / `2.0.0-46`, `IMPLEMENTED_TESTING_DEFERRED`).

## Current Release 45 continuation prompt

Start from the Release 45 / `2.0.0-45` complete source baseline. Release 41 is historical corrective evidence; do not roll back to Release 40/41 or restart NI-7. NI-7 is implemented in source and remains `IMPLEMENTED_TESTING_DEFERRED`. Preserve same-VRF-only route traversal, explicit managed next-device identity, bounded loop-safe simulation, multipath fail-closed behavior, candidate-only dependency semantics, and the existing approval-gated configuration plane. Do not restart NI-1 through NI-7. Q-1 live qualification remains deferred and may be resumed independently.

## Historical Release 34 continuation prompt

Start from the Release 34 FULL source baseline, not Release 33 and not a patch. UI-1 is implemented in source and remains `IMPLEMENTED_TESTING_DEFERRED`. The `/operations` console covers Structured Changes, Telemetry, Model Packs, Desired State, Campaigns, and HA/DR. Do not rebuild these panels from scratch.

All network mutations must continue through durable change requests with frozen snapshot/hash review and separate approval. Do not add a browser bypass, caller-declared approval, arbitrary RPC/URL/protobuf passthrough, or direct device writes. Keep `web.py` below the PH-1 structural gate and place further Operations UI work in `web_ops.py`. Q-1 live qualification and session-expiry debt remain open.


## Release 33 handoff truth

The latest implementation baseline is Release `2.0.0-33`, schema revision `ha1-2`. PH-4, NI-5, VM-1, NA-1, NA-2 and HA-1 are implemented in source and remain `IMPLEMENTED_TESTING_DEFERRED`. Q-1 remains open for production/runtime service-backed qualification. Do not restart PH-3/Q-1 and do not invent the next phase before consolidated Release 33 verification and a new roadmap review.

Preserve these Release 33 invariants: all network mutations use the durable request/approve/execute workflow; automation snapshots/model-pack hashes are frozen and revalidated; `RECOVERY_REQUIRED` blocks blind replay; desired-state rollback is compensating/reverse-order; campaign plans are frozen with stable retry identity; DRAINING/DRAINED HA nodes reject new automation work. Session idle/absolute expiry is still explicitly deferred.

> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.

## Historical Q-1 takeover truth

This section records the historical Q-1 handover checkpoint. Q-1 remains `IMPLEMENTED_TESTING_DEFERRED`; at that historical checkpoint, Release 33 superseded the earlier Q-1 baseline as the active implementation baseline. Do not restart PH-3/Q-1 or discard their qualification boundaries.

Q-1 source implementation includes `netconfig qualify`; controlled `pg_dump` backup; checksummed, confirmation-gated restore into a separate database; recovery-safe restore without active-core initialization; live PostgreSQL multi-process/leadership/migration/recovery tests; CI PostgreSQL client provisioning; AlmaLinux 10 build/install qualification scripts; Ruff/mypy fail-closed source gate; and systemd backup-unit hardening.

The Q-1 live qualification debt remains: execute the real PostgreSQL gates, Ruff/mypy, and AlmaLinux 10 RPM/systemd installed-runtime gates when suitable infrastructure is available. Do not count `NOT_RUN` as pass. Release 34 UI-1 offline/artifact evidence does not substitute for those live gates.

Historical handover text below describes earlier releases. The current handover baseline is **Release 46 / Operator Health Cards & UX Follow-through**; NI-7 remains the feature baseline and Q-1 remains the open deferred qualification track.

Read these first: `DEV_BASELINE.md`, `TESTING.md`, `ROADMAP.md`, `SECURITY.md`, `API.md`, `DEVELOPMENT.md`, `AI_HANDOFF.md`, then the relevant source under `opt/netconfig/netconfig/` and `tests/`.

Important constraints:

- The user handles Git manually. Do not pull/fetch/add/commit/push or mutate repository history/remotes unless explicitly authorized in that chat.
- Deliver implementation changes as a complete modifiable source baseline with tests and packaging/deployment artifacts, not patch-only or documentation-only output.
- Preserve standard-library-first architecture unless a dependency is explicitly justified and approved.
- Console sessions still have no idle/absolute expiry. This is known deferred security debt. Do not implement session expiry unless the user explicitly selects it.
- Do not weaken fail-closed remediation/rollback, secret handling, bearer-token TLS enforcement, token hash-only storage, RBAC/audit, syslog bounds/source correlation, diagnostic redaction/path controls, or incident evidence reference integrity.
- Do not claim Ruff, mypy, RPM, Linux service, protocol-service, or live-device results unless actually run.
- Keep `DEVELOPMENT.md`, `AI_HANDOFF.md`, `ROADMAP.md`, `SECURITY.md`, `API.md`, `TESTING.md`, `patch.md`, and relevant user docs synchronized.

Roadmap structure: the historical 2026-09-07 Slice A-G labels are provenance only. Use `ROADMAP.md` as canonical. **CURRENT IMPLEMENTATION BASELINE is Release 46 / Operator Health Cards & UX Follow-through (`2.0.0-46`). Ruff/mypy actual execution and Q-1 live qualification remain open; the offline helper RPM is not a substitute for canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification. No NI-8 or Q-2 phase is auto-assigned.** D.5 is the completed-in-source Diagnostics Track, not Slice E. Historical Slice E remains Platform Hardening -> Web-console structural hardening.

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

If I say “next phase”, use the current roadmap disposition first: **no development phase is assigned**. Continue explicitly selected Q-1 qualification work when requested, but do not invent Q-2/NI-8 or select a feature phase merely because qualification remains open. A new development phase requires an explicit roadmap decision. Preserve PH-3 bounded structured-adapter semantics, PH-2 database/distributed-operation truth boundaries, PH-1 CSP/structural hardening, and all completed Network Intelligence/D.5 security invariants.


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

## NI-6.4 handover update — 2026-09-16

NI-6.4 Failure Risk Foundation is implemented in the current delivery artifact and remains `IMPLEMENTED_TESTING_DEFERRED`. Source: `opt/netconfig/netconfig/analytics/failure_risk.py`. Focused analytics: 9 passed including the NI-6.3 capacity regression repair. Full offline regression: 192 passed / 7 skipped. Selftest: ALL PASS. Q-1/Ruff remains NOT_RUN/deferred. Next planned milestone is NI-6.5 Impact Simulation.

## 2026-09-16 NI-6 enterprise-hardening handover

NI-6.1–NI-6.6 are implemented and productized through Manager/API/UI. Durable insights support NEW/ACKNOWLEDGED/RESOLVED/EXPIRED, filters/search, evidence/affected-object drill-down and managed impact simulation. Do not reimplement NI-6 foundation. Preserve non-remediation analytics and route all change action into the existing approval plane. Current source evidence: 202 passed / 7 skipped / 0 failed; Q-1/Ruff and live/service/vendor/scale gates remain deferred.

## 2026-09-23 continuation — R51-HF1 pre-MC4 compatibility hotfix

Continue from Release 51 / MC-3 (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`) with the R51-HF1 pre-MC4 hotfix applied. Standard SNMPv3 `aes192`/`aes256` use Blumenthal key extension; Cisco/Reeder is explicit `aes192c`/`aes256c`. Topology discovery unlocks Vault credentials in-process. Every managed inventory device appears in the graph even without LLDP/CDP; unique persisted FDB/MAC correlation is `INFERRED`, non-direct, and excluded from downstream-impact traversal. `/topology` is now a drag/pan/zoom SVG canvas with browser-local layout only. `GET /api/v1/topology/graph` is read-only and adds no device I/O. MC-4 / Release 52 remains `PLANNED`. Live FortiGate SHA1+AES256 and vendor topology validation remain deferred.
