# NetConfig Agent Instructions

## Git

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.

The user manages repository synchronization and Git history manually by default.

Do not run these commands unless the user explicitly asks for Git operations in the current chat:

- `git pull` / `git fetch`
- `git add` / `git commit`
- `git push`
- branch creation/deletion, rebases, resets, history rewrites or remote changes

If the user explicitly authorizes Git work:

- inspect status/diff first;
- keep commits small and focused;
- never overwrite unrelated changes;
- never force-push or rewrite history without explicit approval;
- run relevant tests before commit/push;
- update `AI_HANDOFF.md` and `patch.md` before handover;
- ensure no secrets, credentials, generated binaries, temporary files or unrelated changes are included.

For ordinary local/terminal development, treat the extracted/package tree supplied by the user as the
working baseline and leave Git operations to the user.

Current development continuation: use Release 43 / `2.0.0-43` as the source baseline. The post-NI-7 roadmap review is complete and no new development phase is assigned; Q-1 qualification may continue independently. Historical NI/D.5 packages and their `NEXT` pointers are provenance only.
