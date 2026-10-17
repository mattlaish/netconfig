# R67 LIVE_RC hook contract

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](../../ROADMAP.md) and [AI_HANDOFF.md](../../AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

These fixed-name hooks are examples only. They deliberately return `20` (`BLOCKED_ENVIRONMENT`) until an independent operator replaces each body with a bounded test for the named production gate. R67 accepts live execution only with `NETCONFIG_R67_LIVE_RC=1`; exit `0` means PASS, `20` means BLOCKED_ENVIRONMENT, `21` means NOT_RUN, and any other non-zero exit means FAIL.

Every hook receives `NETCONFIG_R67_GATE_ID`, `NETCONFIG_R67_RESULT_PATH`, `NETCONFIG_R67_REPO_ROOT`, and `NETCONFIG_R67_CANDIDATE_SHA256`. Evidence is valid only for that exact candidate fingerprint. Any source/package change invalidates prior R67 live evidence.
