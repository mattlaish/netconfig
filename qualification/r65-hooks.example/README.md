# R65 LIVE_OPERATOR hooks

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](../../ROADMAP.md) and [AI_HANDOFF.md](../../AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

These fixed-name hooks are examples only and intentionally non-executable. A designated operator-qualification environment may copy them to a private hook directory, implement each exact journey, mark them executable, and run `packaging/r65-qualify.sh ... --live --hook-dir DIR` with `NETCONFIG_R65_LIVE_OPERATOR=1`.

Exit `0` only with real target evidence, `20` for `BLOCKED_ENVIRONMENT`, and `21` for `NOT_RUN`. Write bounded machine-readable metrics to `$NETCONFIG_R65_RESULT_PATH`. Local/SQLite/simulated evidence must never return a live PASS.
