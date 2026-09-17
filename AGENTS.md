## Git

> **Canonical project state — 2026-09-17:** **CURRENT IMPLEMENTATION BASELINE** = **Release 40 / NI-7 L3/VRF Path & Route Dependency Intelligence** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-40`; NI-1 through NI-7 and Enterprise Operations are implemented in source. Q-1 live PostgreSQL/protocol/vendor/device/AlmaLinux gates remain deferred/`NOT_RUN`; Release 40 does not promote them to PASS.

> **Release 34 continuation:** use the complete Release 34 source baseline. UI-1 is source-implemented; Q-1 live qualification remains outstanding. Do not treat historical Release 33 CURRENT/NEXT prose as active state.


> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

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
