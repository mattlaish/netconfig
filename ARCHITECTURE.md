# NetConfig Architecture


> **2026-09-29 development update — SNMP Vendor Profile framework:** this working tree adds a data-only, hot-reloadable SNMP Vendor Profile engine on top of the refrozen R67.2 source line. This is a runtime/package payload change, so the previously frozen R67.2 exact-candidate fingerprint and candidate-bound `LIVE_RC` evidence do **not** qualify this working tree. The release identity has intentionally **not** been advanced; that remains an explicit user decision. Project state remains `IMPLEMENTED_TESTING_DEFERRED`; MC-11 remains the final Monitoring / Correlation / Change-Planning feature slice; no MC-12 and no new network-write authority are introduced. Profiles are JSON data, validated fail-closed, bounded to declared numeric OID roots, and cannot execute Python, shell, commands, URLs, or arbitrary expressions.


## MC-11 planning boundary

MC-11 is an evidence/planning layer above existing persisted topology, NI-7 L3/VRF route evidence, endpoint attachment and MC-6 service dependencies. `TopologyChangePlanningService` reads those stores plus MC-11 policy evidence, persists plans, and emits evidence-backed gap/change-point explanations and schema-bounded Structured Change proposals. It does not own device polling, arbitrary command construction, approval, or execution. Candidate what-if operates only on planner state.

## Release 58 / MC-10 correlation hardening layer

`CorrelationHardeningService` sits around the existing MC-7 deterministic correlation engine. It persists execution evidence in `correlation_runs`, supplies bounded per-incident serialization/advisory locking, startup interruption recovery, replay/input/result fingerprinting, skew/truncation diagnostics, metadata retention, self-monitoring and qualification reporting. MC-5 remains the evidence system of record; MC-7 remains the hypothesis engine; MC-9 remains the operator presentation layer. The hardening layer does not poll infrastructure and is not a device/external-product execution plane.

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Release 55 / MC-7 deterministic correlation pipeline

MC-7 sits above the durable evidence and dependency layers rather than replacing them:

```text
Sensor / Event / Alert / Change / Analytics / External evidence
                         |
                         v
             MC-5 Incident evidence timeline
                         |
                         +---- MC-6 Service/Dependency + L3 context
                         |
                         v
              MC-7 deterministic rule engine
                         |
                         v
                  Hypothesis records
             + supporting evidence
             + contradicting evidence
             + confidence / rule version
                         |
                         v
             Incident investigation UI/API
```

The engine never treats event-time proximity as a dependency. Exact entity identity or trusted active CONFIGURED/fresh DISCOVERED MC-6 relationships are required for cross-entity reasoning. Evaluation is bounded and deterministic; unchanged evidence replay is idempotent. The output is a hypothesis, not a root-cause or attack verdict, and the layer has no device polling/configuration authority.


## MC-6 Service & Dependency Graph architecture

MC-6 adds a service-knowledge layer above existing network evidence rather than merging service claims into topology tables. `service_entities` stores stable typed logical/runtime entities. `service_dependencies` stores directed typed evidence with provenance and freshness. Physical LLDP/CDP/FDB topology, endpoint attachment, NI-7 L3 routes, and service dependencies therefore remain separately auditable evidence domains.

The graph path is: `persisted service entity/dependency evidence -> freshness/evidence-state filter -> bounded cycle-safe traversal -> optional ImpactSimulator projection`. Network overlay is a separate read-only path: `persisted NI-7 route observations -> L3RouteAnalyzer -> managed-device overlay`. The L3 analyzer remains authoritative for VRF scope, explicit `next_device`, loop bounds, and multipath ambiguity. A next-hop IP is evidence only and never creates a managed device or service dependency.

`CONFIGURED` and fresh `DISCOVERED` edges participate in normal traversal. `INFERRED` is a candidate and requires explicit opt-in; `UNKNOWN` and stale evidence remain visible but are excluded by default. No event-time proximity creates a service dependency. Hard traversal limits prevent graph cycles or unexpectedly dense data from consuming unbounded CPU/RAM. MC-7 may consume this graph as context, but MC-6 itself produces no causal hypothesis.

## MC-5 Incident evidence architecture

The R53 evidence path is `durable source evidence -> typed validated Incident reference -> deterministic unified timeline -> grouped investigation view`. Incident links snapshot `source_ts`, `received_ts`, and bounded source-clock metadata; they do not clone large raw payloads. Source stores remain authoritative. If a referenced source row is later removed by retention, the Incident preserves the original link/timing and renders an unavailable-evidence marker rather than inventing content.

Normalized change events are generated from existing structured workflow lifecycle transitions. Normalized external events are a bounded durable evidence primitive only; MC-5 has no connector runtime or external action plane. The Web/API/CLI investigation surfaces consume database evidence and do not trigger polling. MC-5 does not infer service dependencies or root cause. Those boundaries remain MC-6 and MC-7 respectively.


## Release 52 — Unified alert and operator-evidence flow

The canonical new-monitoring path is `port/http/tls check -> monitor_results -> Sensor -> durable Sensor transition -> normalized Operational Event -> operational_alerts`. `alert_rules` remain threshold inputs during compatibility migration; the legacy `alerts` table is read-only history for new monitor polls. Stable Sensor keys are the alert correlation identity so severity escalation updates one lifecycle and recovery resolves that same lifecycle. Upgrade-time migration backfills that identity for legacy active rows before the unique-correlation index is relied upon. Manual resolution does not permanently hide a still-firing Sensor: a DB-only reconciliation pass reopens the same lifecycle, and maintenance-covered durable Sensor evidence is re-evaluated after maintenance ends without manufacturing a new transition. Dependency suppression and maintenance remain outside collectors and are evaluated at the Event/Alert boundary.

Endpoint correlation is an evidence join, not a collector: persisted ARP/IP-neighbor rows from L3 devices are joined by MAC to persisted FDB rows from switches, then LLDP/CDP plus explicitly `INFERRED` managed-device path evidence is used only to identify transit-facing candidates. Fresh FDB evidence can still establish a MAC attachment, but stale-only IP-neighbor evidence cannot yield `HIGH` confidence for the combined IP-to-port conclusion. NetFlow summaries are computed from the collector's bounded recent-flow ring and do not increase export or polling load. Config collection overrides remain inside the existing SSH collection path and are restricted to one read-oriented command; RouterOS accepts only exact `/export`, FortiGate/FortiOS has a native `show full-configuration` read profile, and CLI output is validated before it can become configuration truth.

## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

## Release 48 sensor layer

```text
Existing persisted observations
  device_facts / interface_stats / ARP+IP neighbors / FDB+MAC
  l2_neighbors / mapped mib_values
                    |
                    v
              SensorEngine
          normalized persisted sensors
                    |
          +---------+---------+
          |                   |
     read-only API       operator UI/cards
          |
          +---- future Alert Engine (not implemented)
```

The Sensor Engine is a normalization/interpretation boundary, not a collector or execution plane. It cannot poll devices, widen walks, change collection cadence, push configuration, remediate, or execute arbitrary commands.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.


> **Roadmap disposition — 2026-09-24:** **R59 / MC-11 is the final Monitoring & Correlation functional slice.** Do not create MC-12. After R59 use **Q2 Production Qualification Campaign → R60 Lifecycle → R61 Scale → R62 PostgreSQL → R63 HA → R64 Security → R65 Operator Workflow → R66 Supportability → R67 RC → R68 Production Release Decision**. Simulation never counts as live PASS; qualification states are `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN`.
## Future distributed site-resilience architecture (recorded, not implemented)

Distribution is motivated by **failure-domain isolation and site survivability** as well as eventual scale. A remote/site deployment must be able to keep observing local devices when the central controller or WAN path is unavailable.

```text
Central Controller
  - global inventory / topology / analytics
  - cross-site correlation and central UI
  - audit and configuration/change-control plane
          |
          | authenticated control/telemetry channel
          v
Site Edge / Collector
  - read-only local polling
  - local cache/spool and bounded store-and-forward
  - local health evaluation and alert history
  - local UI and independent heartbeat
          |
          v
Local network devices
```

A Site Edge/Collector is **not** a general execution agent. Its default device-facing surface is read-only: SNMP GET/WALK, NETCONF/RESTCONF reads, and gNMI subscribe/read. Configuration push and arbitrary SSH are excluded by default. If distributed network writes are later required, model them as a separate **Execution Node** or an explicitly authorized execution role with current change-request, snapshot, verification, audit, and recovery controls.

During central/WAN isolation, local monitoring and local alert persistence must continue. Unsynchronized telemetry/alerts are replayed after reconnect. Optional out-of-band notification channels are a future design area, not current implementation.


## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.



## PH-5 Intent / Desired State Automation


## Current Release 43 architecture position

Release 43 does not change the NI-7 runtime schema or network-control architectural boundaries. Its offline RPM builder/verifier is packaging/reproducibility tooling outside the runtime decision and mutation planes. The inherited Release 41 campaign-retry fix is HTTP parsing/coverage only. Network Intelligence remains read-only/decision-support; device mutations continue to flow only through the approval-gated Structured Changes / Desired State / Campaign paths.

Status: IMPLEMENTED_TESTING_DEFERRED

Scope: DesiredState, Intent lifecycle, revisions, drift detection, Change Plan generation, PH-4 transaction integration boundary, approval and audit linkage.


## PH-5 API and Operations Surface

Status: IMPLEMENTED_TESTING_DEFERRED

Added PH-5 API helpers, intent workflow surface, and Web Console Intent Automation entry point. Device changes remain delegated to PH-4 transaction workflow.

## NI-6 enterprise product integration

`Web/API -> Manager.analytics -> AnalyticsService -> Capacity/FailureRisk/Health + NI-2 topology truth -> network_insights / analytics_jobs`. The service boundary separates analysis from network execution. Reads are side-effect free; analysis/simulation requires explicit mutation requests. Impact uses `Manager.downstream_impact()` instead of constructing a generic undirected graph, so managed/resolved topology truth remains authoritative.

## MC-3 normalized operational-evidence boundary

The monitoring/correlation pipeline is now:

```text
Persisted device/collector evidence
        ↓
SensorEngine current snapshot
        ↓
MC-2 durable Sensor transition
        ↓
MC-3 OperationalEventStore normalization
        ↓
operational_events → alert lifecycle / WebUI / API / future correlation
```

Normalization occurs at `OperationalEventStore`, so syslog/SNMP-trap collectors can keep their bounded collection behavior while receiving the same cross-domain semantic envelope. Sensor refresh itself never emits an event for unchanged state. Manager bridges only transition rows created after a captured durable high-water mark. `evidence_ref` preserves provenance and the bridge is idempotent for the same Sensor transition.

## R51-HF1 topology evidence boundary

The read-only topology presentation pipeline is now:

`persisted inventory + topology identity/interface + LLDP/CDP + FDB/MAC -> topology.build_graph() -> Manager.topology_graph() -> Web/API`

Inventory membership creates nodes; it does not claim adjacency. Resolved LLDP/CDP creates `OBSERVED` direct edges. Unique FDB/MAC identity correlation may create `INFERRED` paths only; FDB evidence proves reachability through the observing port, not direct physical adjacency. Inferred paths are excluded from downstream-impact traversal and never replace an observed edge. The Web canvas stores only coordinates/viewport in browser local storage and has no write path into network/topology truth.

The graph pipeline consumes persisted evidence and therefore adds no collection cadence or device I/O.


## MC-6 follow-up: L3 routing topology evidence

The physical graph and Layer-3 graph remain distinct evidence domains. CLI collection may produce normalized interface-address and active-route observations; the topology service resolves only fresh same-VRF evidence and emits `DIRECTLY_CONNECTED` and `NEXT_HOP` relationships. Combined topology is a presentation overlay, not a merged authority model. Physical LLDP/CDP evidence, FDB inferred paths, route evidence, endpoint attachment, and service dependencies retain their own provenance.

A next-hop IP is not an inventory identity. Resolution requires a unique match to fresh managed-interface evidence in the same VRF. Ambiguous, stale, cross-VRF, unresolved, or unmanaged next hops remain explicit unknown/ambiguous evidence and do not become managed graph edges. Rendering is DB-only and bounded by persisted evidence; configuration collection is the only new read-side collection hook in this follow-up.

## R56 / MC-8 external evidence ingestion architecture

`ExternalEvidenceService` upgrades the pre-existing durable `external_events` evidence type rather than introducing a parallel event universe. `external_sources` holds source identity, type, one-to-one ingest-token reference, bounded payload/rate policy and operational health; `external_ingest_receipts` gives source-scoped idempotency receipts. Successful normalized evidence is persisted in `external_events` with tenant/source identity, sanitized metadata/payload, source/receive timestamps, connector type and deterministic payload hash, so MC-5 Incident timelines and MC-7 correlation consume the same durable evidence layer.

The boundary is inbound and evidence-only. MC-8 creates no outbound command executor or vendor-response plane. Authentication, schema, size, replay and rate failures are explicit bounded outcomes and health signals rather than silent drops.

## R62 PostgreSQL concurrency/recovery boundary

Production PostgreSQL uses bounded DB-only dedicated transactions for retry-safe work. Serialization failures and deadlocks may be retried within the database transaction boundary; connection loss never triggers automatic write replay. Read-only statements may reconnect and retry once. Existing MC-10 advisory locks, Structured Change resource locks, MC-11 planning identity locks, and external-evidence idempotency locks remain separate purpose-specific concurrency authorities.

## R65 operator-workflow composition

`OperatorWorkflowService` is a read-model/composition boundary over existing stores; it is not an execution engine. Mutating steps continue through MC-11 planning → Workflow approval → Structured Change → verification/recovery/rollback. This preserves one authority path while providing a continuous operator surface.

## R66 supportability read model

`SupportabilityService` is a read-only composition layer over existing authorities. It may inspect persisted DB state and in-process collector status but cannot start collection, poll devices, execute changes, approve requests, or mutate incidents. Web/API/CLI/Prometheus/support-bundle surfaces consume the same bounded aggregate to avoid divergent health truth.

## R67 release-engineering boundary

R67 adds no runtime component or authority. The qualification runner and release-metadata generator operate outside the runtime control plane. Candidate evidence is cryptographically bound to release metadata/source-manifest identity and is invalidated by candidate changes. Runtime architecture and MC-11 authority are unchanged from R66.
