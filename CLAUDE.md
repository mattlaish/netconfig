\# Claude Project Instructions

> **Canonical project state — 2026-09-17:** **CURRENT IMPLEMENTATION BASELINE** = **Release 40 / NI-7 L3/VRF Path & Route Dependency Intelligence** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-40`; NI-1 through NI-7 and Enterprise Operations are implemented in source. Q-1 live PostgreSQL/protocol/vendor/device/AlmaLinux gates remain deferred/`NOT_RUN`; Release 40 does not promote them to PASS.

> **Release 34 continuation:** use the complete Release 34 source baseline. UI-1 is source-implemented; Q-1 live qualification remains outstanding. Do not treat historical Release 33 CURRENT/NEXT prose as active state.


> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.



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
