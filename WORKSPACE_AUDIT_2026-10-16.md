# NetConfig working-folder reconciliation — 2026-10-16

## Scope and conclusion

The sole active Windows source root is `C:\Users\mattlai\Projects\netconfig`.
The current chat, **研究 netconfig RPM last stage**, is still associated in the App
with the shared `DevSecOps project` at
`C:\Users\mattlai\Documents\ChatGPT\dev project`. Launch cwd and source workdir
are different. Earlier claims that the working folder had been switched did not
actually change that App association. This was an agent workflow error.

Reviewed all **133 accessible preceding turns** in this chat, reaching the start,
plus local files, prior promotion evidence and the alternate source tree. This is
not a claim to have audited inaccessible conversations, another agent's unsaved
state or all GitHub branches. No Git commands were run.

## Verified timeline (all times UTC+8)

| Time | Evidence / disposition |
| --- | --- |
| 2026-08-17 14:37:43 | Original RPM investigation starts in the old `dev project`; legitimate original scope. |
| 2026-08-17 16:11:23 | Settings menu edits target the extracted `netconfig-2.0.0-14-rpm`; this predates the later root selection. Current source includes the settings subpages. |
| 2026-08-18 12:20:17 | User explicitly selects `C:\Users\mattlai\Projects\netconfig` and asks to continue from `AI_HANDOFF.md`. Assistant says it switched, but App launch cwd remains old. That turn's recorded source edits target the correct new root. |
| 2026-08-18 15:20:26 | Asked for the working folder, assistant reports the correct source path without disclosing the unchanged launch cwd. First explicit misleading folder-status response after selection. |
| 2026-08-18 through 2026-08-27 | Accessible recorded product file edits target `Projects\netconfig`, including Application isolation and System regression. No earlier post-selection alternate-tree product edit was found in this history. |
| 2026-10-13 | Documentation maintenance reads/writes canonical files via explicit paths; external helper location alone is not a missing source change. Some historical baseline pointers remained ambiguous. |
| 2026-10-15 21:44:28 request | Five Web UI gaps lead to product editing in `dev project\netconfig-web-controls-20261015`. First verified alternate active editing tree after the user's root selection. |
| 2026-10-16 around 00:43 | Six runtime modules, one regression test file and fifteen Markdown files (22 total) promoted to the canonical root, with original-file backup and promotion report. |
| 2026-10-16 reconciliation | All **468 non-cache staged files** compared byte-for-byte with the canonical tree before repair: **468 identical, 0 different, 0 stage-only**. No unpromoted staged change was found. |

## Repairs

- Workspace lock leads canonical AGENTS/CLAUDE, AI_HANDOFF, DEV_BASELINE,
  HANDOVER_PROMPT and README. Old artifact pointers are explicitly historical;
  the former AGENTS instruction to adopt an extracted/package tree is removed.
- A NetConfig-only AGENTS routing guard in the shared launch directory redirects
  future NetConfig work without changing other projects or their README.
- `tools/run_windows_source_tests.py` anchors cwd, source imports and pytest
  configuration to its owning tree. Detached copies fail closed. Optional test
  dependencies use an explicit environment setting, not an embedded old path.
  The old external helper forwards to this runner instead of testing caller cwd.
- The redundant full Web-controls editing tree is moved to an external temporary
  recovery archive after content verification. It is not merged over current files.
  Original RPM extraction and test/dependency fixtures remain historical artifacts;
  none is an active source root. No unrelated project files are changed.
- `patch.md`, TESTING and DOCUMENTATION_STATUS record the correction. Historical
  test counts and release evidence remain unchanged and explicitly historical.

## Recovery

The 22-file prior promotion backup is
`C:\Users\mattlai\AppData\Local\Temp\netconfig-web-controls-backup-20261016-v90cj6g1`
(`promotion-report.json`). The earlier 67-document backup is
`C:\Users\mattlai\AppData\Local\Temp\netconfig-doc-sync-20261013-zkw9q6tu`.
This repair's recovery directory is
`C:\Users\mattlai\AppData\Local\Temp\netconfig-workspace-reconciliation-20261016-23ed19c174eb422e89bd72fd616afbe8`.
Its `reconciliation-report.json` records fresh original-file hashes, backup paths
and the retired tree at `retired-web-controls-source`. The small repair-only edit
set is archived separately as `repair-files`; it is not a complete source tree.
These temporary recovery files are local, not Git history or permanent backups.

## Validation and remaining boundary

Validation completed on the canonical source using the new maintained runner:

- **51 PASS**: 3 workspace-runner regressions, 45 Web control regressions and 3
  existing canonical-state/compound-statement/PH-1 structural assertions.
- Legacy selftest: **ALL PASS**, including Application-only and System-only cases.
- Invoking the old compatibility helper from the old launch folder reports the
  canonical root, cwd and source import path correctly. A detached runner refuses
  caller-cwd fallback; the Windows PTY guard raises rather than simulating SSH.
- New runner/test compile **2/2 PASS** without writing bytecode. Ruff check of
  runner, test and compatibility helper: **PASS**.
- All original **468** non-cache staged-file hashes rechecked after repair:
  **0 unexpected changes**. Product runtime is unchanged by this reconciliation.
  Source Markdown inventory is **68**; old full development copy is no longer in
  the launch directory and is recoverable in the archive above.
- Initial pytest setup hit an existing inaccessible `pytest-of-mattlai` Temp
  directory (4 PASS / 47 setup errors, not a product failure). Re-running with a
  fresh unique `--basetemp` produced the completed 51 PASS result. No existing
  Temp permissions were changed. Restricted-context path checks also required
  scoped approval; this confirms the App/sandbox boundary is still distinct.

Evidence recorded 2026-10-16 09:43:43 UTC+8 (Taiwan). This is developer tooling
and documentation maintenance, not product runtime, RPM or live qualification.
Package identity stays `2.0.0-67.2`, status `IMPLEMENTED_TESTING_DEFERRED`; generated
metadata/fingerprints must be refreshed only as part of the next candidate freeze.

The App association itself is **not changed**. Available tools expose no safe way
to replace this chat's source folder or register the canonical folder as a project.
The shared App project also contains other chats; globally repointing it would
create another drift. A user-side App project/folder move is still required to
align the launch cwd and sandbox with the canonical source. Meanwhile every
NetConfig command must explicitly target the canonical root and request scoped
approval when access is required. Do not claim the App cwd has been fixed.
