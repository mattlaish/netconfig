# NetConfig Agent Instructions

## Workspace lock — 2026-10-16 (takes precedence over historical pointers)

The sole active Windows source root is `C:\Users\mattlai\Projects\netconfig`.
The chat's launch cwd, `C:\Users\mattlai\Documents\ChatGPT\dev project`, is a different,
shared App project, not this source root. Use an explicit absolute source `workdir`
for every NetConfig command; read/edit/build/test from this tree. Request scoped
approval if the sandbox excludes it. Do not create a second full development copy
to bypass that boundary or adopt an old extracted RPM/ZIP as current source.

Preserve the 2026-10-16 Web UI corrective already in this tree. Follow the top of
`AI_HANDOFF.md` and `patch.md` for current continuation; older release ZIP names and
"active baseline" instructions below are historical, not workspace switches.
Use `tools/run_windows_source_tests.py` for Windows local tests; it anchors cwd,
Python source imports and pytest configuration to its owning source tree.
See `WORKSPACE_AUDIT_2026-10-16.md` for evidence and App-binding limitations.

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Active continuation — 2026-10-13

Continue from the current working tree on R67.2 plus the 2026-09-29 Vendor Profile framework and 2026-10-09 Web UI/NetFlow corrective. No new version has been selected. Do not reuse the old candidate fingerprint or manufacture a live PASS. Resolve release identity, freeze the candidate and execute the twelve LIVE_RC gates before R68 review. No new feature-development phase is assigned; MC-11 is final.

Current source has `/snmp` profile administration, indexed host lookup, bulk topology facts joins, exporter/template diagnostics and Application-only isolation. Preserve System/Network/mixed-type management behavior. Session idle/absolute expiry is already implemented in `web_security_runtime.py` (30 minutes / 12 hours); older deferred-expiry notes are historical. IPFIX decoding, SNMPv3 traps/INFORM, NETCONF base:1.1-only framing and Site Edge/Collector are unassigned future scope.

This handover pass changes Markdown only. It does not rerun full product tests or live gates. Historical 556/542/14 source-test counts belong to the September Vendor Profile checkpoint; the October ledger records nine new focused tests and reports a green suite without an exact new aggregate. Do not combine or invent totals. Any changed packaged Markdown also changes artifact bytes and requires metadata/artifact regeneration before qualification.

Git synchronization and history remain user-managed. Do not run Git commands without explicit current-chat authorization. Completion feedback after a documentation-stage update must end with Taiwan time (UTC+8).

## Git

> **Roadmap disposition — 2026-09-24:** **R59 / MC-11 is the final Monitoring & Correlation functional slice.** Do not create MC-12. After R59, stop feature expansion and use the Release / Qualification track: **Q2 Production Qualification Campaign → R60 Appliance Reliability & Lifecycle Hardening → R61 Scale & Performance Qualification → R62 PostgreSQL / Concurrency / Recovery Hardening → R63 HA / Failure-Domain Engineering → R64 Security Hardening & Independent Abuse Testing → R65 Operator Workflow Completion → R66 Observability / Supportability → R67 Release Candidate / Full Artifact Qualification → R68 v2 Production Release Decision**. Simulation never counts as live PASS; mandatory gates use `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN`.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


> **Historical continuation pointer (superseded):** use **Release 59 / MC-11 Topology-Aware Change Planning** (`2.0.0-59`) as the active full-source baseline once the final artifact gate below is frozen. Preserve `IMPLEMENTED_TESTING_DEFERRED`; do not promote to `TESTED` or `RELEASED` based on source simulation. MC-11 is the final functional slice and does not add direct execution authority. The immediate next track after artifact freeze is **Q2 Production Qualification Campaign**, not MC-12.

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

For ordinary local/terminal development, use the workspace lock above and leave
Git operations to the user. Extracted/package trees are historical evidence or
explicit qualification fixtures, never an implicit replacement working baseline.

Historical development continuation: the former Release 43 pointer is superseded by the canonical state above.
