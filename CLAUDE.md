# Claude Project Instructions

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.



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
