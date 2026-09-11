## Git

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

> **Current continuation pointer:** use the Q-1 full source baseline from 2026-09-12 as the active source. Historical CURRENT/NEXT statements below are chronology only. Execute the remaining Q-1 live gates before any promotion to `TESTED`/`RELEASED`; after Q-1 qualification, perform a fresh roadmap review before assigning Q-2.

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

Current development continuation: use `netconfig_network_intelligence_ni3_FULL_source_baseline_2026-09-11.zip` after final artifact-gate completion as the canonical source baseline; default next implementation is Network Intelligence NI-4. NI-1, NI-2 and D.5 packages are provenance only.
