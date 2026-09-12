\# Claude Project Instructions

> **Canonical project state — 2026-09-12:** **CURRENT IMPLEMENTATION BASELINE** = **HA-1 — Control-plane HA & Recovery Foundation** (`IMPLEMENTED_TESTING_DEFERRED`). **PH-4, NI-5, VM-1, NA-1, NA-2, and HA-1** are implemented in source; consolidated Release 33 offline regression is green, while live/service-backed qualification remains deferred. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; its live PostgreSQL/AlmaLinux/systemd/service-backed gates remain deferred. No further development phase is assigned until the post-implementation qualification/roadmap review. RPM source Release is `2.0.0-33`.

> **Current continuation pointer:** use the Release 33 full source baseline as the active implementation source. Historical CURRENT/NEXT statements below are chronology only. Use the recorded Release 33 offline/artifact evidence and run the applicable Q-1 live gates before any promotion to `TESTED`/`RELEASED`; then perform a fresh roadmap review before assigning another development phase.



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
