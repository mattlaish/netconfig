# R64 — Security Hardening & Independent Abuse Testing

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

Status: **IMPLEMENTED_TESTING_DEFERRED**.

R64 hardens existing NetConfig boundaries without adding device-write authority or a new Monitoring / Correlation / Change-Planning slice. MC-11 remains final and its candidate what-if path remains read-only.

Implemented local hardening includes bounded login-throttle identity cardinality; bounded/expiring web sessions with authoritative per-request user-role, disable, and password-reset revalidation; strict request framing and body limits; bounded multipart MIB uploads; generic external 500 responses; public-Microsoft-cloud OAuth authority pinning, tenant validation, redirect refusal and response limits; and streaming signed-archive verification that rejects non-file/non-directory members before dangerous archive materialization.

The fixed-hook R64 campaign separates `LOCAL_REGRESSION`, `LOCAL_ABUSE`, and `LIVE_ABUSE`. Local evidence is not an independent production security assessment. `production_security_claim` can become true only when every required `LIVE_ABUSE` gate passes on the designated target environment. The runner never promotes the release to TESTED or RELEASED.

## Historical R64 verification evidence

Source-tree regression: **498 collected / 484 PASS / 14 SKIP / 0 FAIL**. R64 focused: **21/21 PASS**. MC-11 focused: **12/12 PASS**. Security/compatibility focused set: **102 PASS / 1 expected no-.git SKIP / 0 FAIL**. Initial selected R64 campaign: **6 local PASS / 0 FAIL / 12 BLOCKED_ENVIRONMENT / 0 NOT_RUN / 0 LIVE_ABUSE PASS**; `production_security_claim=false`. The runner all-local nested full-regression invocation exceeded the surrounding execution envelope, so the full regression was executed separately with the same deterministic five-group partition and recorded in the evidence bundle; this does not change its `LOCAL_REGRESSION` class.
