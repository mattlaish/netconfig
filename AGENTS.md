# AI Development Instructions

## Before starting work
- Read this file.
- Read AI_HANDOFF.md.
- Read patch.md.
- Inspect Git state only when the user has authorized Git operations. The
  repository owner currently handles Git synchronization manually, so do not
  run Git commands unless explicitly re-authorized.
- Review relevant existing code before modifying it.
- Do not redo completed work unless necessary.

## Development rules
- Keep changes focused.
- Preserve existing functionality unless explicitly changing it.
- Follow the existing project architecture and coding conventions.
- Consider security implications of all changes.
- Never commit real credentials, API keys, or private keys.
- Run relevant tests after changes.

## Handoff rules
Before handing development to another AI:
- Update AI_HANDOFF.md.
- Update patch.md with the current patch status, actual validation, remaining
  integration work, risks, rollback notes, and recommended next step.
- Record what was completed.
- Record what remains unfinished.
- Record important technical decisions.
- Record known bugs or failed approaches.
- Record relevant test/build results.
- Identify the recommended next step.
- After completing a development stage or updating README/handover/version
  documents, end the user-facing final feedback with the current Taiwan time in
  the exact format `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)`. The timestamp must be
  the final line of the response.

## Git
- The repository owner performs Git synchronization manually.
- Do not run pull, push, add, commit, status, diff, checkout, reset, or other Git
  operations unless the user explicitly changes this instruction.
- When Git operations are explicitly authorized, prefer small meaningful commits.
- Do not overwrite unrelated changes.
- Do not force-push unless explicitly instructed.
