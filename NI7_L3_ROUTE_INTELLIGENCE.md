# NI-7 — L3/VRF Path & Route Dependency Intelligence

Status: **IMPLEMENTED_TESTING_DEFERRED**

Release 40 adds durable explicit route evidence and deterministic L3/VRF decision-support analytics. The implementation never infers a managed device from next-hop IP, never crosses VRFs, and stops on incomplete, unmanaged, mixed-terminal, loop, or multipath-ambiguous evidence. `ROUTE_DEPENDENCY` output is explicitly a candidate and may show observed alternates; it is not an outage verdict.

Operator surfaces:

- Network Intelligence Operations UI: route evidence, L3 path simulation, route dependency candidate analysis.
- REST API: `/api/v1/analytics/l3/routes`, `/api/v1/analytics/l3/path/simulate`, `/api/v1/analytics/l3/dependencies/analyze`.
- Existing insight lifecycle and evidence drill-down.

Safety: no device command, route mutation, configuration push, automatic remediation, or approval bypass. Remediation remains in Structured Changes / Desired State / Campaign workflows.

Pre-package verification: NI-7 focused **5 passed**; full repository **211 passed / 7 skipped / 0 failed**. Q-1 live service/vendor/AlmaLinux gates remain deferred.
