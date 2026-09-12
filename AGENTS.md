## Git

> **Canonical project state — 2026-09-12:** **CURRENT IMPLEMENTATION BASELINE** = **HA-1 — Control-plane HA & Recovery Foundation** (`IMPLEMENTED_TESTING_DEFERRED`). **PH-4, NI-5, VM-1, NA-1, NA-2, and HA-1** are implemented in source; consolidated Release 33 offline regression is green, while live/service-backed qualification remains deferred. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; its live PostgreSQL/AlmaLinux/systemd/service-backed gates remain deferred. No further development phase is assigned until the post-implementation qualification/roadmap review. RPM source Release is `2.0.0-33`.

> **Current continuation pointer:** use the Release 33 full source baseline as the active implementation source. Historical CURRENT/NEXT statements below are chronology only. Use the recorded Release 33 offline/artifact evidence and run the applicable Q-1 live gates before any promotion to `TESTED`/`RELEASED`; then perform a fresh roadmap review before assigning another development phase.

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
