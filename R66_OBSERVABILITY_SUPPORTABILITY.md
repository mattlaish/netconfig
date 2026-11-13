# R66 — Observability / Supportability

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-11-12:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.14 / Devices and Traffic Console Corrective RPM** (`2.0.0-67.14`, `IMPLEMENTED_TESTING_DEFERRED`). Release 67.14 adds Devices monitoring cards, Traffic auto-refresh and destination lookup, and consistent sign-in and footer package versions. Release 67.13 distinguishes configured static route intent from dynamic and route-table-only observations while preserving Release 67.12 shared-subnet next-hop display, Release 67.11 layered topology and operator UI corrections, Release 67.10 evidence-first topology, Release 67.9 grouped SNMP trends, Release 67.8 Enable credential precedence and Release 67.7 isolated legacy `ssh-rsa`/SHA-1 verification. Existing state is preserved across upgrade. **MC-11 Topology-Aware Change Planning** remains the final feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** and schema `mc11-topology-change-planning-1` remain. **Do not create MC-12.** Offline verification does not replace live Cisco/AlmaLinux qualification. All twelve LIVE_RC gates and an explicit R68 decision remain required. Git stays user-managed.

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

Status: `IMPLEMENTED_TESTING_DEFERRED`  
Package: `2.0.0-66`  
Persisted schema: `mc11-topology-change-planning-1` (unchanged)

## Scope

R66 makes the existing appliance diagnosable without adding a new control plane or mutation authority. `SupportabilityService` exposes a bounded `r66-supportability-1` read model assembled from already-persisted/runtime state: core storage readiness, HA summary, distributed-task backlog/recovery, telemetry due/error/lag/last-success state, external-ingest health, correlation queue/latency state, collector queue/drop/error counters, diagnostic retention, filesystem capacity, process restart/heartbeat age and last-success timestamps for collection/change paths.

The snapshot is read-only. It never polls a device, starts a connector, runs a command, changes policy, executes a Structured Change, or treats an observation as qualification evidence. MC-11 remains the final Monitoring / Correlation / Change-Planning slice; R66 does not create MC-12.

## Operator surfaces

- `GET /api/v1/supportability` requires `debug:read` and returns the bounded secret-free snapshot.
- `netconfig debug status` prints the same read-only model for host operators.
- `/diagnostics` shows the supportability snapshot before support-bundle controls and remains settings-authorized.
- `/metrics` publishes bounded aggregate metrics only; it does not expose device names, node IDs, usernames, tokens, paths, or high-cardinality per-object labels.
- HTTP responses carry a generated `X-Request-ID`; JSON access logging and server-error references use the same request correlation value.

## Support bundle

Support bundles now include `system/supportability.json`. Database metadata records only backend/schema/reachability/distributed capability and no longer embeds the local database filesystem path. Existing recursive redaction, manifest hashing, optional Ed25519 signing, archive bounds and verification remain authoritative.

## Runtime collector visibility

The Web runtime registers already-started NetFlow, syslog and SNMP-trap collectors with the Manager for diagnostics only. R66 reads their existing bounded `status()` surfaces to report running state, queue depth, received/accepted/rejected/drop counts and sanitized last error. Registration grants no lifecycle or packet-processing authority to the supportability service.

## Qualification truth

`qualification/r66_runner.py` separates `LOCAL_REGRESSION`, `LOCAL_SUPPORT`, and `LIVE_SUPPORT`. A production supportability claim requires all ten fixed `LIVE_SUPPORT` gates to be selected and PASS. Local SQLite tests, fake collectors, local HTTP tests, support-bundle tests and offline RPM builds never satisfy a live gate. Gate hooks are fixed-name, bounded, secret-redacted and opt in only with `NETCONFIG_R66_LIVE_SUPPORT=1`.

Required live areas cover health/readiness across restart, Prometheus scrape/cardinality, PostgreSQL outage/recovery, queue backlog/recovery, ingest drops/rejections, connector lag/last-success, correlation backlog/latency, disk/retention lifecycle, independent support-bundle review, and an independent support drill.
