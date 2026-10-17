# Q2 live hook examples

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](../../ROADMAP.md) and [AI_HANDOFF.md](../../AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

Copy only the hooks you intend to execute into a separate qualification-host hook directory, make them executable, and replace the fail-closed placeholder with environment-specific validation. Do not point the runner at this example directory as production evidence.

A hook receives:

- `NETCONFIG_Q2_GATE_ID`
- `NETCONFIG_Q2_REPO_ROOT`
- `NETCONFIG_Q2_RESULT_PATH`

Write only non-secret metrics to `NETCONFIG_Q2_RESULT_PATH`. Exit `0` for PASS, `20` for BLOCKED_ENVIRONMENT, `21` for NOT_RUN, and any other non-zero code for FAIL.
