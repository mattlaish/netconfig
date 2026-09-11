\# Claude Project Instructions

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

> **Current continuation pointer:** use the Q-1 full source baseline from 2026-09-12 as the active source. Historical CURRENT/NEXT statements below are chronology only. Execute the remaining Q-1 live gates before any promotion to `TESTED`/`RELEASED`; after Q-1 qualification, perform a fresh roadmap review before assigning Q-2.



At the beginning of work:



1\. Read README.md to understand the product.

2\. Read AGENTS.md and follow its permanent development rules.

3\. Read AI\_HANDOFF.md for the current project state and next task.

4\. Read patch.md for the chronological patch/version ledger.



Keep changes focused and run relevant tests.



Update AI\_HANDOFF.md after meaningful development work.

Update patch.md after meaningful development work and before handover.

After completing a development stage or updating README/handover/version
documents, make the final line of the user feedback the current Taiwan time in
this exact format: `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)`.



For local/terminal sessions:

\- The user handles git pull, git add, git commit, and git push manually.

\- Follow AGENTS.md as the authority for whether any Git operation is allowed.



For Claude Code Web/cloud sessions:

\- Use the normal isolated branch / pull-request workflow.

\- Never merge directly into main without user approval.


Current development continuation: use `netconfig_network_intelligence_ni3_FULL_source_baseline_2026-09-11.zip` after final artifact-gate completion as the canonical source baseline; default next implementation is Network Intelligence NI-4. NI-1, NI-2 and D.5 packages are provenance only.
