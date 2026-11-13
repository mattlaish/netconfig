# NI-7 — L3/VRF Path & Route Dependency Intelligence

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-11-12:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.14 / Devices and Traffic Console Corrective RPM** (`2.0.0-67.14`, `IMPLEMENTED_TESTING_DEFERRED`). Release 67.14 adds Devices monitoring cards, Traffic auto-refresh and destination lookup, and consistent sign-in and footer package versions. Release 67.13 distinguishes configured static route intent from dynamic and route-table-only observations while preserving Release 67.12 shared-subnet next-hop display, Release 67.11 layered topology and operator UI corrections, Release 67.10 evidence-first topology, Release 67.9 grouped SNMP trends, Release 67.8 Enable credential precedence and Release 67.7 isolated legacy `ssh-rsa`/SHA-1 verification. Existing state is preserved across upgrade. **MC-11 Topology-Aware Change Planning** remains the final feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** and schema `mc11-topology-change-planning-1` remain. **Do not create MC-12.** Offline verification does not replace live Cisco/AlmaLinux qualification. All twelve LIVE_RC gates and an explicit R68 decision remain required. Git stays user-managed.

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

> **Roadmap disposition — 2026-09-24:** The monitoring/correlation roadmap is active. MC-1 through MC-9 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next formal slice is **MC-10 / Release 58 — Correlation Production Hardening & Qualification**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. MC-11 / Release 59 remains the final Topology-Aware Change Planning slice. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

Status: **IMPLEMENTED_TESTING_DEFERRED**

Release 40 adds durable explicit route evidence and deterministic L3/VRF decision-support analytics. The implementation never infers a managed device from next-hop IP, never crosses VRFs, and stops on incomplete, unmanaged, mixed-terminal, loop, or multipath-ambiguous evidence. `ROUTE_DEPENDENCY` output is explicitly a candidate and may show observed alternates; it is not an outage verdict.

Operator surfaces:

- Network Intelligence Operations UI: route evidence, L3 path simulation, route dependency candidate analysis.
- REST API: `/api/v1/analytics/l3/routes`, `/api/v1/analytics/l3/path/simulate`, `/api/v1/analytics/l3/dependencies/analyze`.
- Existing insight lifecycle and evidence drill-down.

Safety: no device command, route mutation, configuration push, automatic remediation, or approval bypass. Remediation remains in Structured Changes / Desired State / Campaign workflows.

Pre-package verification: NI-7 focused **5 passed**; full repository **211 passed / 7 skipped / 0 failed**. Q-1 live service/vendor/AlmaLinux gates remain deferred.

## R54.1 collection/topology integration

NI-7 explicit L3/VRF path evidence is now fed by a read-only MC-6 follow-up collector. Supported CLI drivers may collect normalized interface-address and active routing-table observations during normal configuration collection. The topology resolver may associate a next hop with a managed device only through a unique fresh same-VRF managed-interface address. The UI exposes Physical / Layer 3 / Combined views while retaining explicit UNKNOWN/AMBIGUOUS evidence. Live vendor-output validation remains deferred.
