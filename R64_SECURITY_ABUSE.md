# R64 — Security Hardening & Independent Abuse Testing

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-11-12:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.14 / Devices and Traffic Console Corrective RPM** (`2.0.0-67.14`, `IMPLEMENTED_TESTING_DEFERRED`). Release 67.14 adds Devices monitoring cards, Traffic auto-refresh and destination lookup, and consistent sign-in and footer package versions. Release 67.13 distinguishes configured static route intent from dynamic and route-table-only observations while preserving Release 67.12 shared-subnet next-hop display, Release 67.11 layered topology and operator UI corrections, Release 67.10 evidence-first topology, Release 67.9 grouped SNMP trends, Release 67.8 Enable credential precedence and Release 67.7 isolated legacy `ssh-rsa`/SHA-1 verification. Existing state is preserved across upgrade. **MC-11 Topology-Aware Change Planning** remains the final feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** and schema `mc11-topology-change-planning-1` remain. **Do not create MC-12.** Offline verification does not replace live Cisco/AlmaLinux qualification. All twelve LIVE_RC gates and an explicit R68 decision remain required. Git stays user-managed.

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

Status: **IMPLEMENTED_TESTING_DEFERRED**.

R64 hardens existing NetConfig boundaries without adding device-write authority or a new Monitoring / Correlation / Change-Planning slice. MC-11 remains final and its candidate what-if path remains read-only.

Implemented local hardening includes bounded login-throttle identity cardinality; bounded/expiring web sessions with authoritative per-request user-role, disable, and password-reset revalidation; strict request framing and body limits; bounded multipart MIB uploads; generic external 500 responses; public-Microsoft-cloud OAuth authority pinning, tenant validation, redirect refusal and response limits; and streaming signed-archive verification that rejects non-file/non-directory members before dangerous archive materialization.

The fixed-hook R64 campaign separates `LOCAL_REGRESSION`, `LOCAL_ABUSE`, and `LIVE_ABUSE`. Local evidence is not an independent production security assessment. `production_security_claim` can become true only when every required `LIVE_ABUSE` gate passes on the designated target environment. The runner never promotes the release to TESTED or RELEASED.

## Historical R64 verification evidence

Source-tree regression: **498 collected / 484 PASS / 14 SKIP / 0 FAIL**. R64 focused: **21/21 PASS**. MC-11 focused: **12/12 PASS**. Security/compatibility focused set: **102 PASS / 1 expected no-.git SKIP / 0 FAIL**. Initial selected R64 campaign: **6 local PASS / 0 FAIL / 12 BLOCKED_ENVIRONMENT / 0 NOT_RUN / 0 LIVE_ABUSE PASS**; `production_security_claim=false`. The runner all-local nested full-regression invocation exceeded the surrounding execution envelope, so the full regression was executed separately with the same deterministic five-group partition and recorded in the evidence bundle; this does not change its `LOCAL_REGRESSION` class.
