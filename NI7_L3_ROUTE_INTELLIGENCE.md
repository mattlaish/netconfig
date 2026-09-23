# NI-7 — L3/VRF Path & Route Dependency Intelligence

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

Status: **IMPLEMENTED_TESTING_DEFERRED**

Release 40 adds durable explicit route evidence and deterministic L3/VRF decision-support analytics. The implementation never infers a managed device from next-hop IP, never crosses VRFs, and stops on incomplete, unmanaged, mixed-terminal, loop, or multipath-ambiguous evidence. `ROUTE_DEPENDENCY` output is explicitly a candidate and may show observed alternates; it is not an outage verdict.

Operator surfaces:

- Network Intelligence Operations UI: route evidence, L3 path simulation, route dependency candidate analysis.
- REST API: `/api/v1/analytics/l3/routes`, `/api/v1/analytics/l3/path/simulate`, `/api/v1/analytics/l3/dependencies/analyze`.
- Existing insight lifecycle and evidence drill-down.

Safety: no device command, route mutation, configuration push, automatic remediation, or approval bypass. Remediation remains in Structured Changes / Desired State / Campaign workflows.

Pre-package verification: NI-7 focused **5 passed**; full repository **211 passed / 7 skipped / 0 failed**. Q-1 live service/vendor/AlmaLinux gates remain deferred.
