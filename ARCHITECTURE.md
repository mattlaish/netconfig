# NetConfig Architecture

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
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


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.
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

