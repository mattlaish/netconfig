# AI Development Handoff

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.

## Release 34 handoff truth

The current implementation baseline is UI-1 / Release `2.0.0-34`, built directly from the verified Release 33 FULL source artifact (`ca0a8b9d...0dccb`). UI-1 is a Web Console layer over the already-implemented PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 services; it does not replace or bypass those services.

Continue from the Release 34 FULL source baseline. Preserve: durable CR approval and frozen snapshot/hash revalidation for all network writes; admin-only structured recovery/model lifecycle/cluster-node state changes; viewer read-only access; CSRF and CSP nonce enforcement; `web.py` <4000 lines and <240 KB; metadata-only protocol trace; Q-1/live qualification truth; session idle/absolute expiry remains deferred. Do not claim live device/PostgreSQL/RPM qualification from the offline UI-1 evidence.


## Release 33 handoff truth

The latest implementation baseline is Release `2.0.0-33`, schema revision `ha1-2`. PH-4, NI-5, VM-1, NA-1, NA-2 and HA-1 are implemented in source and remain `IMPLEMENTED_TESTING_DEFERRED`. Q-1 remains open for production/runtime service-backed qualification. Do not restart PH-3/Q-1 and do not invent the next phase before consolidated Release 33 verification and a new roadmap review.

Preserve these Release 33 invariants: all network mutations use the durable request/approve/execute workflow; automation snapshots/model-pack hashes are frozen and revalidated; `RECOVERY_REQUIRED` blocks blind replay; desired-state rollback is compensating/reverse-order; campaign plans are frozen with stable retry identity; DRAINING/DRAINED HA nodes reject new automation work. Session idle/absolute expiry is still explicitly deferred.

> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

## Historical checkpoint — Qualification Q-1

Q-1 remains `IMPLEMENTED_TESTING_DEFERRED`, but Release 33 is now the active implementation baseline. The following Q-1 details are retained as historical qualification context; do not revert package metadata or PH-3/Q-1 safety boundaries.

Key Q-1 invariants: PostgreSQL backup/restore is fixed-function only; DB credentials use a short-lived mode-0600 `PGPASSFILE` and never argv; restore requires a verified checksum plus explicit `RESTORE_DATABASE` and may not target the configured active core database; the recovery-safe restore path must not require opening the failed active core first. `netconfig qualify` is configuration-aware. AlmaLinux installation qualification is permitted only on a disposable target with explicit `--install` plus `NETCONFIG_Q1_ALLOW_INSTALL=1`.

Historical Q-1 offline evidence before its package gate: Q-1 focused **11 passed**, full repository **147 passed / 7 skipped**. The four new Q-1 service skips are real PostgreSQL multi-node claim/leadership, session-loss lock release, SQLite migration/sequence repair, and pg_dump/pg_restore recovery. Ruff/mypy, real PostgreSQL tooling, and AlmaLinux 10 are `NOT_RUN` in this environment. Q-1 live gates remain outstanding; Release 34 UI-1 offline/artifact evidence does not promote Q-1 or the feature phases to `TESTED`.

Clean Q-1 candidate `netconfig_qualification_q1_candidate_2026-09-12.zip` (SHA-256 `185039eadf8e8e63a8dad358df35f759a7a1f099d5fa6a3456a50e023920a2b1`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; source/extracted byte identity **125/125 PASS**; payload plus each SHA manifest **121/121 PASS**; required executable modes **7/7 = 0755**; extracted Q-1 focused **11 passed**; extracted full regression **147 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.

## Project
NetConfig (reconstructed from `netconfig-2.0.0-14`; current packaging target
`netconfig-2.0.0-34.el10` per the current source spec; RPM build/install qualification remains deferred until the Q-1 AlmaLinux gate is run)

## Objective
Continue development and improvement of the NetConfig platform from the
reconstructed RPM payload while preserving its existing behavior and packaging
layout.

`patch.md` is now the required chronological patch/version ledger. Future AI
work must read and update it together with this overall handoff.

For the current concise state, verification evidence, and next development order, read
`DEV_BASELINE.md`, `TESTING_RESULT_2026-09-11.md`, and `ROADMAP.md` first. The dated
2026-09-07 handover/testing files are retained as historical context only.
After a completed development stage or README/handover/version-document update,
the final user feedback must end with `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)`.
## AI Git Workflow

The user manages Git synchronization/history manually by default. AI agents must not run
`git pull`, `git fetch`, `git add`, `git commit`, `git push`, branch/history mutation, or
remote-changing commands unless the user explicitly authorizes Git work in the current chat.

When Git work is explicitly authorized, review status/diff first, run relevant tests, update
`AI_HANDOFF.md` and `patch.md`, keep changes focused, and never force-push or rewrite history
without explicit approval.

## Multi-Agent Coordination

- Treat the source package/tree supplied by the user in the current chat as the working baseline.
- GitHub is the upstream source of truth only when the user has already synchronized the tree or explicitly
  authorizes Git access in the current chat; do not proactively synchronize it yourself.
- Do not assume another AI agent's uncommitted local changes exist.
- Avoid concurrent modification of the same tree by multiple agents unless the user has isolated the work.
## Current Status
- Repository synchronization and Git history are managed manually by the user.
  AI agents must not run Git synchronization, staging, commit, or push commands.
- This is an extracted RPM filesystem payload, not a conventional build tree.
  Application code is under `opt/netconfig/`; RPM integration files are under
  `etc/`, `usr/`, and `var/`.
- The application is a standard-library-only Python package. It uses the system
  OpenSSH client through a PTY for device access and SQLite for persistent state.
- The Python web-console compatibility blocker is fixed in `web.py`, and the
  documented runtime now matches the Python 3.12 launcher and AlmaLinux 10 target.
- SNMP device views now expose all currently persisted system facts, interfaces,
  ARP and MAC/bridge data, while live walks show resolved names, raw OIDs, values,
  and the uploaded MIB file responsible for each mapping.
- The MIB library now reports per-file resolved/unresolved definitions and name
  conflicts; its lookup results also identify the mapping source.
- Pure Application devices are endpoint monitors, not managed network devices.
  Their form labels the target as a primary hostname/FQDN, hides and disables
  SSH/SNMP/platform/archive controls, and the server rejects forged or stale
  management values by normalizing the platform to `generic` and clearing
  management references. Their dashboard/detail views omit port, platform,
  auth, collection, current config, SNMP facts, and config backups; bulk config
  collection skips them. Mixed System/Network types retain management features.
- Uploaded vendor MIBs now drive bounded collection, not only name mapping:
  resolved enterprise `OBJECT-TYPE` definitions are matched to each device's
  `sysObjectID`, walked at a safe cadence, persisted, and shown on its SNMP page.
- Net-SNMP Linux collection now accounts for its split namespace: a device with
  sysObjectID enterprise 8072 can collect uploaded definitions below Net-SNMP
  8072, UCD-SNMP 2021, and standard HOST-RESOURCES `.1.3.6.1.2.1.25`. The UI
  distinguishes no matching definitions from a matched tree returning no data.
- System and application compliance no longer inherit a misleading binary-only
  network-config result model. Live probe failures can be `unknown`, application
  health is retained as unscored operational evidence, and only devices without
  failures or unknowns count as compliant. System checks distinguish explicitly
  monitored SMB/RDP exposure; application checks now collect response headers,
  cipher strength, and active TLS 1.0/1.1 probes, then audit HSTS, nosniff, CSP,
  certificate validity/expiry, and legacy TLS without false prerequisite passes.
- The authenticated top bar now includes a persisted Light/Dark theme toggle.
  The low-glare dark palette covers the shared page chrome, panels, tables,
  forms, settings navigation, diffs, badges, login/error pages, and SNMP charts;
  browser preference is used until the user explicitly selects a theme.
- SNMPv3 polling reuses engine discovery and RFC 3414 localized keys throughout
  each device poll instead of recomputing the 1 MB password-to-key operation for
  every OID, addressing the observed single-poller-thread CPU saturation pattern.
- Reproducible RPM source engineering now exists under `packaging/`: an EL10
  `netconfig.spec`, source/binary/SRPM build script, static RPM inspector,
  installed-package smoke test, and build/test instructions. Release `-15` exposed
  a CRLF launcher/shebang failure after Windows-to-Alma transfer; the normalized
  rebuild is intentionally release `-16` so `dnf upgrade` will replace it.

## Architecture Baseline
- `usr/bin/netconfig`: installed launcher; adds `/opt/netconfig` to `sys.path`
  and calls `netconfig.cli.main`.
- `netconfig/cli.py`: argparse command surface for inventory, collection,
  backup, vault, users, automation, workflow, compliance, SNMP, and web.
- `netconfig/manager.py`: orchestration facade connecting inventory, vault,
  SSH transport/drivers, archive, SNMP, sessions, and concurrent bulk work.
- `netconfig/db.py`: shared SQLite connection, additive/idempotent schema and
  migrations for inventory, users/RBAC, workflow/jobs, compliance, monitoring,
  SNMP facts, and audit data.
- `netconfig/inventory.py`, `store.py`, `vault.py`, `users.py`: core persistence,
  versioned configuration storage, encrypted secrets, and identity/RBAC.
- `netconfig/transport.py` + `drivers.py`: OpenSSH-over-PTY expect engine and
  platform-specific CLI behavior.
- `netconfig/workflow.py`, `automation.py`, `compliance.py`: approval workflow,
  command templating, and rule evaluation.
- `netconfig/snmp.py`, `aes.py`, `aead.py`: stdlib-only SNMP and cryptographic
  implementations.
- `netconfig/web.py`: monolithic stdlib `http.server` web console with sessions,
  RBAC, and CSRF checks; it also starts optional monitoring/NetFlow workers.
- `selftest.py`: the only bundled automated test suite; offline vectors and
  storage/workflow round trips.
- `usr/lib/systemd/system/`: web service and weekly backup service/timer.

## Build and Test Procedures
The reconstructed RPM source is under `packaging/`. On AlmaLinux 10, install
`rpm-build` and `python3.12`, then run `packaging/build-rpm.sh`; it creates an
unsigned `-16` noarch RPM and SRPM in the project root. Inspect with
`packaging/inspect-rpm.sh` and validate an installed copy with
`packaging/smoke-installed.sh`. There is still no pyproject/setup, tox/pytest,
or CI configuration because the application remains a direct stdlib payload.

Safe local checks:

```bash
cd opt/netconfig
PYTHONPYCACHEPREFIX=/tmp/netconfig-pycache python3 selftest.py

cd ../..
PYTHONPYCACHEPREFIX=/tmp/netconfig-pycache \
  python3 -m compileall -q opt/netconfig/netconfig opt/netconfig/selftest.py

PYTHONPATH=opt/netconfig python3 -m netconfig.cli --help
```

Notes:
- On macOS, set `PYTHONPYCACHEPREFIX` to a writable temporary path; otherwise
  the system Python may try to write under `~/Library/Caches` and report sandbox
  permission failures unrelated to source correctness.
- Commands that construct `Manager` create the selected/default data directory
  and SQLite database. Use `--home` with a temporary directory for smoke tests.
- Live SSH/SNMP, systemd hardening, filesystem ownership/modes, backup timer,
  and RPM installation require a Linux integration environment and test devices
  or protocol fakes.

## Test and Environment Results (2026-08-19)
- Current development host: Windows, Python 3.12.13. Target integration host:
  AlmaLinux 10.2, Python 3.12.13.
- The full bundled self-test completes with `RESULT: ALL PASS` after the web
  compatibility and SNMP/MIB work, including settings-subpage and new MIB
  automap/source/diagnostic tests, Net-SNMP/UCD/HOST-RESOURCES root matching,
  compliance unknown-state handling, TLS prerequisite handling, and unscored
  application-health evidence. Theme persistence and dark-style presence are
  also covered by the bundled self-test.
- `compileall` passes for all application modules and `selftest.py`.
- All 28 Python files pass parsing with Python 3.9 grammar mode; Python 3.12+ is
  nevertheless the supported deployment contract, matching AlmaLinux 10 and the
  installed launcher.
- CLI `--help` cannot run on the Windows host because the intended Unix-only SSH
  transport imports `pty`/`termios`. It previously passed on macOS and should be
  rechecked on AlmaLinux.
- Packaging payload/spec/script static checks pass on Windows. Release `-15` was
  built and installed on AlmaLinux, but its Windows CRLF launcher caused systemd
  `203/EXEC`; normalizing `/usr/bin/netconfig` recovered the service. Release
  `-16` contains the permanent build/spec regression fix but is not yet built.
  No new live network-device/SNMP-agent or end-to-end integration test ran.
- Final GitHub-push preparation completed without running any Git command:
  Python 3.12 compileall and the full offline self-test pass; the 50-file
  workspace contains no runtime database, cache, RPM/SRPM, private key,
  certificate, high-confidence API token, or file larger than 5 MB. Secret-like
  matches are documented placeholders only. `.gitignore` now excludes Python
  caches, local databases/vaults/MIB indexes, environment/secrets, logs, and RPM
  build outputs. The source `/usr/bin/netconfig` launcher itself is now LF-only,
  in addition to the existing build/spec normalization defense.

## Planned Feature: Config Archive Full-Text Search

Selected as the next development task (2026-08-21). The archive is already
plain, greppable text, but nothing in the product can answer estate-wide
questions such as "which devices still permit Telnet" or "where does
`snmp-server community public` still appear". Compliance answers this only for
its own fixed rule set; there is no free-form query path, in the CLI or the web
console.

### Scope
- Search every device's stored configuration, optionally across retained
  history, from both the CLI and the web console.
- Read-only. No new collection, no device contact, no configuration change.

### Design
- **`store.py` (core):** add `ConfigStore.search(pattern, *, devices=None,
  regex=False, ignore_case=True, scope="current", context=0, max_per_device,
  max_total)`. Return per-device hits carrying the version stamp, line number,
  matched line, and optional context lines. First extract the path-validation
  logic from `read_version` into a private helper that returns a validated
  snapshot path. Both `read_version` and the new search implementation must use
  this helper. Search files line by line from the validated path and stop at the
  configured bounds; never load the complete archive into memory.
- **`scope`:** `current` (default, one file per device), `all` (every retained
  snapshot), or `baseline`.
- **No index in v1.** Retention defaults to 30 versions per device, so a
  bounded linear scan is adequate at expected fleet sizes and preserves the
  "text files, not a blob DB" property that `store.py` documents as a
  deliberate design choice. Measure before adding a SQLite FTS index in
  `db.py`; if one is ever added, treat it as an optimisation with a rebuild
  path, never as the source of truth.
- **`cli.py`:** `netconfig search <pattern> [--device|--group|--tag]
  [--all-versions] [--regex] [--case] [--context N] [--json]`, wired with the
  existing `sub.add_parser(...).set_defaults(func=...)` convention and
  resolving targets through `inventory` the way `bulk` does. Exit non-zero on
  no match so it composes in shell pipelines.
- **`web.py`:** add `/search` to the `routes` map in `_route_get`, gated by
  `_require_auth()` plus the `view` capability. Group results by device, each
  hit linking to the existing `/raw` and `/diff` pages. Add the entry to the
  top navigation.

### Security constraints (must not be skipped)
- Archived configs contain live secrets. `scrub.py` is off by default and its
  own docstring says to treat raw configs as sensitive regardless. Search
  therefore exposes what `/raw` already exposes and must not widen it: gate it
  on the same capability, and decide explicitly whether `viewer` should be able
  to sweep the whole estate for `password 7`. Recommended: keep `view` for
  parity with `/raw`, plus a settings toggle that masks secret-looking matches
  in results by reusing the `scrub` rules.
- The regex arrives from an HTTP form. Cap pattern length, reject pathological
  input, compile once, and enforce match/file/time budgets to bound ReDoS and
  runaway scans. Plain substring is the default; regex is opt-in.
- `sessions/` transcripts (mode 0600) are out of scope for v1. Do not search
  them.
- Record estate-wide searches in the audit trail, consistent with the
  append-only audit convention already used for workflow actions.

### Test plan (fully offline)
Extend `selftest.py` with a temporary `ConfigStore` holding several devices and
versions: substring and regex matches, case sensitivity, context lines, scope
selection, bound enforcement, no-match and empty-archive cases, rejection of
traversal-shaped version stamps through the search path, and scrubbed versus
unscrubbed content. No device, network, or RPM toolchain is required, so this
feature is verifiable end to end in a plain Linux session.

### Other candidates considered
Reviewed against the current code and rejected for now, recorded so they are
not re-derived: negation-aware remediation (the largest real gap --
`manager._remediation_lines` cannot remove added lines, so drift correction is
incomplete; should be paired with a `reload in` / `commit confirmed`
auto-rollback guard before it touches live gear); LLDP/CDP neighbour discovery
and topology (no `lldp`/`cdp`/`neighbor` handling exists anywhere); restore of
an arbitrary archived version (`read_version` exists, nothing pushes it back);
a syslog receiver driving event-triggered collection (`netflow.Collector` is a
reusable bounded UDP listener pattern); and a read-only REST API with scoped
tokens (implemented in the 2026-09-02 read-only API slice).

## Test and Environment Results (2026-08-21, Linux session)
- Verified in a Linux container with Python 3.12.3 at `/usr/bin/python3.12`;
  that container's default `python3` is 3.11.15.
- `python3.12 selftest.py` reports `RESULT: ALL PASS`.
- `python3.12 -m compileall` passes for all 27 modules and `selftest.py`.
- `PYTHONPATH=opt/netconfig python3.12 -m netconfig.cli --help` runs
  successfully. This closes the previously open item that CLI help could not be
  exercised on the Windows host: the Unix-only `pty`/`termios` imports resolve
  normally on Linux.
- Under Python 3.11, `web.py` fails to compile at line 947 (a backslash inside
  an f-string expression). This is expected and not a regression -- PEP 701
  permits it from 3.12 onward -- and it confirms the documented 3.12+ runtime
  contract. Checks in a mixed-version environment must call `python3.12`
  explicitly.
- No CR characters anywhere in the tree; `usr/bin/netconfig` is LF with a
  `#!/usr/bin/python3.12` shebang, and `packaging/netconfig.spec` is at release
  `16%{?dist}` with `-15` and `-16` changelog entries present.
- `rpmbuild`, `rpm` and `dnf` are absent from this container, so the `-16` RPM
  build, inspection, and upgrade verification remain blocked here and still
  require the AlmaLinux 10.2 VM.
- These checks modified no files: bytecode was redirected outside the
  repository and no runtime data directory was created.


## Known Issues and Gaps
1. **Packaging integration is unverified:** the reconstructed spec/build scripts
  need a clean `-16` rebuild and an installed `-15` to `-16` upgrade verification
  on AlmaLinux 10.2. Signing identity and release GPG keys remain undefined.
2. **Documentation drift remains:** the RPM quick-install and manual launcher
   paths are corrected, but `INSTALL.md` still retains a v1 section saying the product is not a
   push tool, not multi-user, and logs into the web UI with the vault password;
   later v2 documentation and current code describe approval-based writes,
   user/RBAC login, and a separately unlocked vault.
3. **Source executable metadata gap:** the extracted workspace does not preserve
   executable bits. The spec installs `/usr/bin/netconfig` as `0755`, and the
   Alma build instructions explicitly chmod packaging scripts before use.
4. **Integration coverage is missing:** the self-test is broad but is a single
   script and does not cover real OpenSSH/device prompts, real vendor SNMP,
   HTTP request flows, systemd sandbox behavior, installation/upgrade, or RPM
   output. Existing docs explicitly note that configuration push was tested only
   with a fake Cisco device/local sshd and that real vendor behavior varies.
5. **Platform-dependent module:** `transport.py` imports `pty`; runtime support is
  Unix-specific. Linux remains the intended deployment target.
6. **Final Linux packaging validation remains:** Windows static checks confirm
   `2.0.0-16.el10`, payload presence, launcher shebang/LF, and documentation
   consistency, but Bash syntax validation, RPM build/inspection, installation,
   and live endpoint/device integration still require AlmaLinux 10.2.

## Important Decisions
- Preserve the extracted filesystem layout; make application changes under
  `opt/netconfig/` and packaging changes under `packaging/` or payload paths.
- Python 3.12+ is the supported runtime, aligned with AlmaLinux 10.2 and the
  installed `/usr/bin/python3.12` launcher.
- Keep tests offline and isolated by default; do not point collection, push,
  remediation, SNMP, monitoring, or NetFlow checks at production equipment.
- Do not treat the numerous defensive `except ...: pass` blocks as unfinished
  work without case-specific analysis; no explicit TODO/FIXME stubs were found.

## Completed
- Read project instructions and prior handoff.
- Inspected repository status, initial commit, full file layout, documentation,
  runtime entry point, service units, core module boundaries, and test suite.
- Identified the available test procedure and ran safe offline/syntax/CLI smoke
  checks.
- Separated a macOS cache-permission artifact from the reproducible `web.py`
  syntax failure.
- Removed the temporary untracked `netconfig-data/` generated by a CLI smoke
  check; no runtime data or user files were retained or modified.
- Fixed the dashboard f-string compatibility blocker in `web.py`.
- Reconciled the documented runtime requirement to Python 3.12+.
- Re-ran grammar, compile and offline self-tests successfully on 2026-08-18.
- Expanded the SNMP device page with contact, location, last error, model/OID
  source, ARP table, and MAC/bridge table using already-collected data.
- Connected uploaded MIB definitions to visible walk/lookup source attribution
  and added per-file missing-parent and duplicate-name diagnostics.
- Added offline tests for uploaded OID mapping, instance suffixes, source MIBs,
  unresolved parents, duplicate definitions, and cached diagnostic reloads.
- Simplified the pure-Application device form without changing stored fields or
  HTTP/TLS monitoring behavior; Python 3.12 compile and full self-test still pass.
- Added bounded MIB-driven vendor polling: maximum 12 roots and 400 values per
  device, no more often than every five minutes in the background; manual Poll
  forces a refresh. New SQLite tables retain current values and poll status.
- Added offline tests for vendor-root matching/isolation, value persistence,
  SNMPv3 localized-key reuse, and engine-discovery reuse. Full self-test and
  Python 3.12 compile pass after these changes.
- Reconstructed the previously missing RPM spec/build flow with systemd
  lifecycle macros, service user creation, explicit modes/ownership,
  `%config(noreplace)`, and runtime-data exclusion. Windows static packaging
  checks pass; no RPM was built locally because this host has no RPM toolchain.
- Replaced the stale `install.sh` quick-install documentation with the EL10 RPM
  procedure and corrected the manual launcher path.
- Corrected pure Application isolation end to end: hidden form values can no
  longer save `arista_eos` or SSH/SNMP state, management-only device-page and
  dashboard data is omitted, and bulk config collection skips endpoint-only
  entries. Existing archives and vault secrets are retained; resaving an
  existing pure Application device normalizes its inventory row.

## In Progress

No implementation is currently in progress. The compatibility and SNMP/MIB
visibility work is complete. Config archive full-text search is specified
above but has not been implemented.

## Recommended Next Step

Implement the config archive full-text search feature specified above:

1. Add `ConfigStore.search` and offline tests in `selftest.py`.
2. Add the `netconfig search` CLI subcommand.
3. Add the `/search` web page.

This feature is self-contained and read-only, and can be developed without
access to network devices or an RPM build environment.

The AlmaLinux packaging and hardware validation remain pending. On an
AlmaLinux 10 build/test VM, run `packaging/build-rpm.sh`, inspect the resulting
binary RPM and SRPM, upgrade the existing installation, and run
`packaging/smoke-installed.sh`. Then validate the expanded SNMP/MIB pages and
reduced SNMPv3 CPU use against a real device and a representative vendor MIB
set.

## Last Verified

2026-08-27 on Windows with Python 3.12.13: `compileall` and the full bundled
offline self-test pass, including Application-only save normalization, endpoint
detail/dashboard isolation, hidden-control submission prevention, and
System-only reverse-regression coverage confirming that management fields,
detail panels, dashboard data, SNMP/config visibility, and collect controls are
preserved. The earlier Linux Python 3.12.3 compile, self-test, and CLI-help
results remain the latest Linux validation. Live web/RPM verification on
AlmaLinux remains outstanding.

Git synchronization and repository history remain under the user's control.

## 2026-08-31 hardening slice

A broad engineering/security/remediation hardening slice was added. See `DEVELOPMENT.md`, `SECURITY.md`, and `ROADMAP.md` for canonical details. Important constraint: **do not implement console session expiry in this slice**. Session idle/absolute expiry is explicitly deferred security debt and should be addressed later as a dedicated change with lifecycle/audit/CSRF tests.

Remediation no longer replays the baseline blindly. Execution now requires a non-scrubbed baseline, fetches fresh live state, builds a semantic vendor-aware plan, arms a rollback guard, applies, re-fetches, verifies, and only then confirms/cancels rollback. IOS/ASA/Arista use timed reload and JunOS uses commit-confirmed; other platforms fail closed until a tested guard exists.

## 2026-09-01 CI / EOL hygiene follow-up

- Ruff CI configuration now explicitly ignores only `E702` as the current semicolon house style; identified unused-import, stray-f-string, exception-chaining, and ambiguous-name findings were fixed in source rather than broadly ignored.
- `.gitattributes` now enforces LF for executable/configuration/source text classes and the current tree was renormalized to LF.
- CI includes an index line-ending check and pytest includes repository-hygiene assertions.
- Do not claim local Ruff PASS from this slice: the sandbox had no Ruff installation and could not reach PyPI. GitHub Actions must provide final Ruff evidence.
- Session lifetime remains intentionally unchanged and deferred as documented security debt.

## 2026-09-02 current implementation delta

The tree now includes LLDP/CDP topology discovery (`topology.py`), persisted neighbour edges and unmanaged-neighbour detection, a dependency-free Topology console, bounded syslog-triggered configuration collection (`syslog_receiver.py`), hashed/scoped read-only bearer API tokens (`apitokens.py` plus `/api/v1/*`), and scheduled compliance/drift email digests (`digest.py`). New SQLite tables are additive: `l2_neighbors`, `syslog_events`, `api_tokens`, and `digest_runs`. API token plaintext is shown only once at CLI creation; only hashes persist. Session expiry is still intentionally deferred and unchanged. Real-device LLDP/CDP and production syslog relay behavior remain deferred validation.


## 2026-09-07 — New-chat handover snapshot

No runtime feature was intentionally changed for this handover. The current source baseline is the
2026-09-02 topology/API/digest slice plus documentation and packaging-reference cleanup.

Canonical next-chat entry points:

- `HANDOVER_2026-09-07.md`
- `TESTING_RESULT_2026-09-07.md`
- `HANDOVER_PROMPT.md`
- `ROADMAP.md`

Verification rerun for handover: pytest **19 passed / 3 skipped**, legacy selftest **RESULT: ALL PASS**,
compileall **PASS**, CR-containing repository text files **0**. Ruff/mypy, the service-backed integration
tier, GitHub Actions, AlmaLinux RPM qualification and live-device tests were not run here and remain
unclaimed.

Historical note: the 2026-09-07 handover originally recommended **Slice A — Qualification and release gate closure**. That A-G ordering is no longer the current execution sequence. Use `ROADMAP.md` Current/Next and track sections instead. That handover was later superseded; the canonical current implementation is recorded in the final D.5 closeout section below; qualification remains a Platform Hardening release-readiness gate.

Console session idle/absolute expiry remains intentionally deferred security debt and must not be
silently implemented without the user's explicit selection.


## Latest Slice D.5 State

Slice D.5 Diagnostic & Support Bundle Framework has started. Current implementation provides CLI bundle generation through `netconfig debug collect`. Continue from this foundation; do not claim full support bundle capability until device capture, API, UI, and integration validation are completed.


## 2026-09-10 — Slice D.5 Phase 2 Diagnostic Support Bundle completion update
- Added device diagnostic capture foundation (`netconfig debug device <name>`).
- Diagnostic exports remain secret-redacted and manifest/checksum validated.
- Current slice remains IMPLEMENTED_TESTING_DEFERRED until REST API, Web UI diagnostics, retention policy, and full device protocol traces are completed.


## Slice D.5 Phase 3 update (2026-09-10)
Implemented diagnostic bundle retention foundation: bundles are stored under the NetConfig state directory, can be listed and cleaned up from CLI, and continue using redaction and manifest integrity. REST API, Web UI diagnostics, trace capture, and signed bundle workflow remain deferred.


## Slice D.5 Phase 3B — Diagnostic API Foundation (2026-09-10)
- Added read-only debug bundle API foundation.
- Added debug:create and debug:read API token scopes.
- Bundle creation remains secret-redacted and audited.
- Status: IMPLEMENTED_TESTING_DEFERRED.
- Deferred: Diagnostics UI, download workflow, incident correlation, protocol trace capture.


## D.5 Phase 3D — Enterprise Diagnostic Operations

Status: IMPLEMENTED_TESTING_DEFERRED

Added secure debug bundle download API foundation, debug:download scope, RBAC/audit integration. Deferred: incident workflow, signed manifests, retention scheduler UI.


## 2026-09-11 — Historical baseline snapshot: D.5 Phase 4A Incident Model Foundation

Treat the Phase 4A FULL source package as the current implementation baseline. New code adds `incidents.py`, additive `incidents`/`incident_bundles` database state, CLI lifecycle operations, and scoped REST incident foundations. Phase 3D bearer scope registration was also repaired (`debug:download`, `debug:admin`).

Do not collapse incident records into alerts or change requests: an Incident is a separate operator-owned investigation/case container. In Phase 4A it may link diagnostic bundles but does not yet own or duplicate syslog, audit, compliance, drift or collection event rows. Phase 4B should build timeline references/views over existing evidence.

Current incident lifecycle: `OPEN -> INVESTIGATING|RESOLVED|CLOSED`; `INVESTIGATING -> RESOLVED|CLOSED`; `RESOLVED -> INVESTIGATING|CLOSED`; `CLOSED -> INVESTIGATING` for explicit reopen. Severity is LOW/MEDIUM/HIGH/CRITICAL. API incident writes require `incident:write` plus operator/approver/admin role.

Next recommended D.5 slice: **Phase 4B — Incident Timeline**. Keep Phase 4C case export, Phase 4D signing, Phase 4E protocol trace capture and Phase 4F UI separate unless the user explicitly combines them. Session idle/absolute expiry remains deliberately deferred.


## 2026-09-11 — Historical baseline snapshot: D.5 Phase 4B Incident Timeline

Treat the Phase 4B FULL source package as the current implementation baseline. `incident_evidence_links` is additive and reference-only. Do not redesign it into an evidence-copy table: audit/syslog/compliance/collection/config archives remain authoritative. Supported external source types are allow-listed as audit, syslog, collection, compliance and drift. Incident-native audit activity and current diagnostic-bundle associations are synthesized directly into timeline output.

Drift correlation is pinned to the baseline/current immutable archive stamps captured at link time. If referenced source data is later pruned, keep the incident link and report `available=false`; do not silently drop history or fabricate replacement evidence. API reads use `incident:read`; link/unlink remains `incident:write` plus operator/approver/admin role.

Verified repository result before packaging: **33 passed / 3 skipped**, incident focused **14 passed**, selftest **ALL PASS**, compileall **PASS**. Ruff/mypy and environment-backed qualification were not run.

Next recommended D.5 slice: **Phase 4C — Support Case Export**. Keep Phase 4D signing, Phase 4E protocol trace capture and Phase 4F Incident Web UI separate. Session idle/absolute expiry remains deliberately deferred.


Phase 4B packaging integrity was validated against the extracted delivery artifact: full source/extracted SHA identity PASS, manifest verification PASS, no traversal/symlink/CR issues, extracted pytest **33 passed / 3 skipped**, extracted selftest **ALL PASS**, and compileall PASS. Treat the FULL Phase 4B ZIP as the handoff baseline, not an earlier workspace or Phase 4A archive.


## 2026-09-11 — Roadmap structure reconciliation

The historical Slice A-G ordering has been demoted to provenance-only context. Current planning is organized as **Current**, **Next**, **Diagnostics Track**, **Network Intelligence Track**, and **Platform Hardening Track** in `ROADMAP.md`. At that historical reconciliation point, current was D.5 Phase 4D and next was D.5 Phase 4E. The latest baseline section below supersedes that historical position. Do not treat historical references saying “Slice A is NEXT” as current instructions.


## 2026-09-11 — Historical baseline snapshot: D.5 Phase 4C Support Case Export

Historical Phase 4C note: that package was the implementation baseline at the time. The Phase 4D FULL source package described below now supersedes it. `SupportCaseExporter` owns managed case archives and `incident_case_exports`; do not fold exported case files into the Incident evidence table or copy authoritative external event/config bodies into Incident state.

Case packages include Incident-owned metadata, reference-only evidence/timeline indexes, selected already-linked diagnostic bundles copied byte-for-byte, SHA-256 manifests and an unsigned trust-boundary note. API export creation/download requires the dedicated `incident:export` scope plus operator-or-higher role; `incident:read` can list export metadata only. Export creation/download is audited.

Current offline result before final packaging: pytest **39 passed / 3 skipped**, focused incident/case tests **20 passed**, legacy selftest **ALL PASS**, compileall **PASS**. Ruff/mypy and service-backed/live qualification remain unclaimed unless a later result records them.

Next recommended D.5 slice: **Phase 4D — Evidence / Manifest Signing**. Define key lifecycle, external signer/trust semantics and verification behavior before adding signatures. Keep Phase 4E protocol trace capture and Phase 4F Incident Web UI separate. Console session idle/absolute expiry remains deliberately deferred.

Phase 4C packaging integrity was validated against a cleanly extracted FULL source candidate: source/extracted SHA identity **94/94 PASS**, manifest payload **90/90 PASS**, no traversal/symlink/CR issues, extracted pytest **39 passed / 3 skipped**, focused incident/case tests **20 passed**, selftest **ALL PASS**, and compileall **PASS**. The final package should remain the handoff source of truth.


## 2026-09-11 — Historical baseline snapshot: D.5 Phase 4D Evidence / Manifest Signing

Treat the Phase 4D FULL source package as the current implementation baseline. Diagnostic bundles and support-case exports can be Ed25519-signed through a fixed OpenSSL adapter. Private key material is external only: prefer `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem`; `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE` is the protected manual/non-systemd fallback. Do not persist or export the private key.

Verification must keep `signature_valid` separate from `trusted`: the archive's embedded public key is not an authenticity anchor. Trust requires an independent SHA-256 SPKI fingerprint pin from settings/environment/CLI. Multiple pins support key rotation. A configured invalid/insecure signer fails closed; unsigned legacy evidence remains compatible unless signing-required policy is enabled.

Next recommended D.5 slice: **Phase 4E — Protocol Trace Capture**. Keep Phase 4F Incident Web UI separate. Console session idle/absolute expiry remains deliberately deferred.


Phase 4D candidate artifact gate: source/extracted identity **96/96 PASS**, manifest payload **92/92 PASS**, ZIP CRC **PASS**, traversal/symlink/CR checks clean, extracted pytest **49 passed / 3 skipped**, focused signing tests **10 passed**, selftest **ALL PASS**, compileall **PASS**. Final handoff package name: `netconfig_d55_phase4d_FULL_source_baseline_2026-09-11.zip`.


## 2026-09-11 — Historical baseline snapshot: D.5 Phase 4E Protocol Trace Capture

Treat the Phase 4E FULL source package as the current implementation baseline. `ProtocolTraceStore` owns bounded metadata-only trace sessions/events. Capture is explicit and currently wired to CLI/OpenSSH `execute()` metadata and SNMP UDP exchange metadata. Never change this into implicit raw terminal/packet capture: passwords, enable secrets, SNMP communities/v3 keys, raw SSH output and raw SNMP BER packets are outside the trace evidence boundary.

Trace sessions may be linked to an Incident and then appear as `protocol_trace` evidence. Case exports include sanitized `protocol-traces.json`; diagnostic support bundles include bounded recent trace metadata. `trace:read` is separate from role-gated `trace:capture`. Historical Phase 4E note: NETCONF/RESTCONF identifiers were future-ready only. PH-3 now implements NETCONF/RESTCONF/gNMI metadata trace providers; raw protocol payloads and credentials remain excluded from trace evidence.

Current offline result: pytest **59 passed / 3 skipped**, Phase 4E focused **10 passed**, selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Ruff/mypy and live/service-backed qualification remain unclaimed.

Next recommended D.5 slice: **Phase 4F — Incident Web Console**. Preserve Phase 4A-4E evidence/RBAC/signing/trace boundaries. Console session idle/absolute expiry remains deliberately deferred.


Phase 4E candidate artifact gate: source/extracted identity **98/98 PASS**, manifest payload **94/94 PASS**, ZIP CRC **PASS**, traversal/symlink checks clean, extracted pytest **59 passed / 3 skipped**, focused protocol-trace tests **10 passed**, selftest **ALL PASS**, compileall **PASS**. Final handoff package name: `netconfig_d55_phase4e_FULL_source_baseline_2026-09-11.zip`.


## 2026-09-11 — Historical baseline snapshot: D.5 Phase 4F Incident Web Console

At that point, the Phase 4F FULL source package was the current implementation baseline. The web console now exposes authenticated Incident register/detail workflows over the existing Phase 4A-4E services; it does not maintain a parallel incident state model. Viewer remains read-only. Operator/approver/admin browser mutations retain CSRF and the existing service-level validation/audit boundaries.

Incident detail integrates lifecycle, reference-only timeline/evidence, bounded sanitized protocol traces, linked diagnostic bundles, and support-case export/verification/download. Case download must continue to call `SupportCaseExporter.record_download()` so durable SHA-256, signed-evidence and configured trust-pin checks remain enforced before streaming. Never replace the safe trace subsystem with raw terminal/packet capture.

Current offline result: pytest **64 passed / 3 skipped**; Phase 4F focused web tests **5 passed**; selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**. Ruff/mypy and live/service-backed qualification remain unclaimed.

Next recommended step: **D.5 Closeout / Diagnostic Qualification Review**. Reconcile remaining retention/scheduler controls and run available CI/lint/type/service-backed qualification before advancing D.5 beyond IMPLEMENTED_TESTING_DEFERRED. Session idle/absolute expiry remains deliberately deferred.

Phase 4F candidate artifact gate: source/extracted identity **99/99 PASS**, manifest payload **95/95 PASS**, ZIP CRC **PASS**, traversal/symlink/CR checks clean, extracted pytest **64 passed / 3 skipped**, focused Incident Web Console tests **5 passed**, selftest **ALL PASS**, compileall **PASS**. Final handoff package name: `netconfig_d55_phase4f_FULL_source_baseline_2026-09-11.zip`.


## 2026-09-11 — Historical baseline snapshot: D.5 Closeout / Diagnostic Qualification Review

At that point, the D.5 closeout FULL source package was the current baseline. D.5 feature phases 1 through 4F are complete in source. Closeout added opt-in bounded diagnostic retention maintenance: support-bundle count retention, case-archive age retention with durable metadata preserved, and unlinked inactive trace retention. Automatic maintenance is disabled by default and Incident-linked protocol traces are excluded from generic pruning.

Current offline result: pytest **67 passed / 3 skipped**, focused closeout **3 passed**, selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**. Ruff/mypy, service-backed OpenSSH/Net-SNMP/PostgreSQL integration, RPM build/install and live-device qualification remain unclaimed. Therefore D.5 remains **IMPLEMENTED_TESTING_DEFERRED**.

Next development track: **VLAN-aware endpoint and topology correlation**. Keep the outstanding D.5 qualification gates visible as qualification debt. Session idle/absolute expiry remains deliberately deferred.

Roadmap naming clarification: D.5 is the standalone **Diagnostics Track**, not historical Slice E. The next VLAN-aware endpoint/topology correlation work is the modern track name for historical **Slice B**. Historical **Slice E** remains **Platform Hardening -> Web-console structural hardening** and is not implied complete by D.5 closeout.


Current closeout delivery package: `netconfig_d55_closeout_FULL_source_baseline_2026-09-11.zip` (checksum recorded in final delivery response and release manifest).


### D.5 closeout candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; source/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## 2026-09-11 — Post-closeout roadmap naming refresh

Historical documentation-only refresh on top of the D.5 closeout source baseline. At that point, **CURRENT = D.5 Closeout / Diagnostic Qualification Review** and **NEXT = Network Intelligence Track -> VLAN-aware endpoint and topology correlation**. D.5 is not historical Slice E: the NEXT item maps historically to **Slice B**; historical **Slice E** remains **Platform Hardening -> Web-console structural hardening**. Runtime/API/schema behavior and RPM spec remain unchanged (`2.0.0-24`).

Verification after the documentation refresh: pytest **67 passed / 3 skipped**, closeout-focused **3 passed**, selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**. Candidate artifact gate: 101/101 file identity, 97/97 manifest payload, three SHA manifests 97/97, ZIP CRC PASS, traversal/symlink clean.

Current handoff package: `netconfig_d55_closeout_roadmap_refresh_repacked_FULL_source_baseline_2026-09-11.zip`.


### Source-baseline packaging repair — 2026-09-11

The roadmap-refresh baseline was repacked after an independent gate found that the ZIP had lost executable bits and active RPM docs still referenced Release 17. The repaired FULL source baseline preserves `0755` for `usr/bin/netconfig` plus the three RPM helper shell scripts, and active build/install examples use `2.0.0-24`. Candidate extraction passed 101/101 file identity, 97/97 manifest payload, all three SHA manifests, CRC/traversal/symlink/CR checks, direct build-script execution (expected exit 2 because `rpmbuild` is unavailable), pytest 67 passed / 3 skipped, closeout 3 passed, and selftest ALL PASS. That repaired D.5 package is a historical predecessor; do not use it as the current handoff artifact after NI-1.


## 2026-09-11 — Historical baseline: Network Intelligence NI-1 VLAN-aware Endpoint Attachment Correlation

Treat `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip` as the current implementation baseline after its final artifact gate. This supersedes the pre-refresh NI-1 and all D.5 packages. D.5 remains complete in source and `IMPLEMENTED_TESTING_DEFERRED`; it is not the active feature track.

NI-1 adds authoritative modern neighbour/FDB evidence in `ip_neighbors` and `vlan_fdb`, collected from IP-MIB `ipNetToPhysicalTable` and Q-BRIDGE-MIB with legacy provenance-preserving fallback. `network_intelligence.py` correlates those records with LLDP/CDP neighbour-facing ports. Never assume Q-BRIDGE FDB ID equals VLAN ID, never promote neighbour-facing/uplink observations to direct endpoint attachment, and never choose one attachment when multiple fresh direct candidates exist.

New public read surface: `endpoint:read`, `GET /api/v1/endpoints`, CLI `netconfig endpoints`, Web `/endpoints`. No enforcement/write API is added. Evidence older than `network_intelligence_max_age_seconds` is stale.

Current pre-package regression: pytest **75 passed / 3 skipped**, NI-1 focused **8 passed**. RPM source metadata is `2.0.0-25`; RPM/live vendor qualification remains unclaimed.

Next recommended phase: **Network Intelligence NI-2 — Topology Identity & Downstream Impact**. Keep SNMP traps/dependency-aware events as the following Network Intelligence phase. Session idle/absolute expiry remains deliberately deferred.

NI-1 source-workspace verification before packaging: pytest **75 passed / 3 skipped**, focused NI-1 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**. Preserve executable modes in the delivery ZIP; the repaired D.5 baseline established `0755` as a release gate for the launcher and RPM helper scripts.

NI-1 candidate artifact gate passed before final repackaging: stage/extracted identity **103/103**, manifest payload and each SHA manifest **99/99**, executable ZIP/extracted modes **0755**, CRC/traversal/symlink/CR checks clean, extracted pytest **75 passed / 3 skipped**, NI-1 focused **8 passed**, selftest **ALL PASS**, compileall **PASS**. Final FULL package must reproduce those results after the documentation evidence is included and manifests are regenerated.


## 2026-09-11 — NI-1 all-Markdown canonical-state synchronization

All 19 Markdown files were synchronized so active planning is unambiguous: **CURRENT = Network Intelligence NI-1**, **NEXT = NI-2**, D.5 is completed in source but remains `IMPLEMENTED_TESTING_DEFERRED`, and historical Slice A-G/D.5 snapshots are explicitly provenance only. Active RPM source references are `2.0.0-25`. Current handoff artifact name: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`.

Workspace validation after the Markdown-only changes: Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**.


## 2026-09-11 — Historical baseline: Network Intelligence NI-2

NI-2 is the active implementation line. It normalizes local LLDP/ENTITY-MIB chassis identity plus IF-MIB interface identity, resolves managed neighbours only from unique identity evidence, records ambiguity instead of guessing, and provides bounded cycle-safe observed-L2 downstream impact. Never reinterpret LLDP localPortNum as ifIndex; never traverse ambiguous/unmanaged edges; never describe NI-2 impact as routing/application/power dependency.

Current source-workspace regression is **83 passed / 3 skipped** with NI-2 focused **8 passed**. Source RPM metadata is `2.0.0-26`. The intended complete handoff artifact is `netconfig_network_intelligence_ni2_FULL_source_baseline_2026-09-11.zip` after the final artifact gate.

Next recommended phase: **Network Intelligence NI-3 — SNMP Traps & Dependency-aware Events**. Do not fold alert lifecycle or platform-hardening work into NI-3 unless explicitly selected.

NI-2 candidate artifact gate passed: stage/extracted identity **104/104**, manifest payload and each SHA manifest **100/100**, hidden-path accuracy PASS, executable ZIP/extracted modes **0755**, archive-security/hygiene checks clean, extracted pytest **83 passed / 3 skipped**, NI-2 focused **8 passed**, selftest **ALL PASS**, compile/syntax checks **PASS**. Final FULL package must reproduce these results after documentation evidence and manifests are regenerated.

NI-2 prefinal artifact reproduced clean extraction and runtime regression after candidate evidence was embedded. Final handoff must use only `netconfig_network_intelligence_ni2_FULL_source_baseline_2026-09-11.zip` after its final independent gate; older candidate/prefinal archives are provenance only.

## 2026-09-11 — Historical baseline: Network Intelligence NI-3

NI-3 adds bounded SNMP v1/v2c trap ingestion, normalized/deduplicated operational events, targeted SNMP re-poll, unified syslog/SNMP reachability events and NI-2 dependency-aware suppression. SNMPv3 traps and INFORM remain fail-closed. Current source-workspace regression is **91 passed / 3 skipped**, focused NI-3 **8 passed**. Source RPM metadata is `2.0.0-27`. Intended complete handoff artifact: `netconfig_network_intelligence_ni3_FULL_source_baseline_2026-09-11.zip` after final artifact gate.

NI-3 candidate artifact gate passed. Final handoff must use `netconfig_network_intelligence_ni3_FULL_source_baseline_2026-09-11.zip` after its own clean-extraction gate; do not use the candidate ZIP as the continuation baseline.


## 2026-09-11 — Historical baseline: Network Intelligence NI-4

NI-4 layers an operational alert/report lifecycle over NI-3 normalized events: configurable severity promotion, audited acknowledge/resolve, device/global maintenance windows, bounded durable notification retry/backoff, scheduled aggregate reports, and CLI/API/Web operator surfaces. Dependency-suppressed or maintenance-covered events remain durable evidence but do not page. Existing monitor-rule alerts remain separate. Current source-workspace regression is **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**. Source RPM metadata is `2.0.0-28`. Intended complete artifact: `netconfig_network_intelligence_ni4_FULL_source_baseline_2026-09-11.zip` after final artifact gate. Next recommended phase: **Platform Hardening PH-1 — Web-console Structural Hardening**.


### NI-4 candidate artifact evidence

Candidate `netconfig_network_intelligence_ni4_candidate_2026-09-11.zip` SHA-256 `17ed1297a863eaca2eeb4a92f5bddcf3ab120804d2526c63339bda79ae1569e3` passed clean system-unzip validation: **109/109** artifact files present, **105/105** Release payload entries and each of the three SHA manifests verified, exact hidden paths retained, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the NI-4/PH-1/Release-28 current-state pointer. Extracted regression: **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## 2026-09-11 — Historical baseline: Platform Hardening PH-1

Historical PH-1 snapshot: PH-1 decomposes the Web console without changing routes/API semantics: `web.py` delegates bearer API handling to `web_api.py` and presentation/assets to `web_ui.py`; strict per-response CSP nonces are enforced for script/style elements; HTML event/style attributes are denied after render normalization. Current source regression is **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**. Source RPM metadata is `2.0.0-29`. Intended complete artifact: `netconfig_platform_hardening_ph1_FULL_source_baseline_2026-09-11.zip` after final artifact gate. Next recommended phase at that historical point: **PH-2 — PostgreSQL Core & Distributed Operation**.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## Historical PH-2 handoff — 2026-09-11

PH-2 is implemented in source and remains `IMPLEMENTED_TESTING_DEFERRED`. SQLite is the default single-node backend. PostgreSQL is an explicit production-core opt-in through `core_db_backend=postgres`; it requires psycopg plus configured `pg_*` connection fields and a pre-vault service credential (`postgres-core-password` or protected `NETCONFIG_DB_PASSWORD_FILE`). Selection is fail-closed; there is no silent fallback to SQLite.

Distributed control-plane primitives now include cluster-node heartbeat, PostgreSQL advisory-lock scheduler leadership, and durable work claiming with `FOR UPDATE SKIP LOCKED`. The generic task queue is a coordination primitive; existing network-device change execution has not been silently changed into an asynchronous remote-worker architecture.

Current offline evidence: PH-2 focused 9 passed; full repository 114 passed / 3 skipped. Do not claim live PostgreSQL, HA, concurrency, migration, RPM, or psycopg deployment qualification until those gates are actually run.

Historical next at PH-2 completion was PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters (historical Slice G). PH-3 is now implemented in source.

### PH-2 candidate artifact evidence

Candidate SHA-256 `6dfd6e554b08883c51a6f268bbe604bf95cc7819dad8f4bda6f023d688807d21` passed the full source/artifact gate: 114/114 files, 110/110 payload/manifests, exact hidden paths, preserved 0755 modes, 19/19 Markdown current-state alignment, extracted 114/3 repository regression, focused PH-2 9/9, selftest/compile/shell PASS. The final FULL baseline is rebuilt after this ledger update so its manifests cover the synchronized documentation.


## Historical PH-3 completion snapshot

PH-3 is implemented in source and remains `IMPLEMENTED_TESTING_DEFERRED`. It is no longer the earlier read-only MVP.

- NETCONF: SSH subsystem hello/capability negotiation; fixed bounded `<get>` and `<get-config>`; advertised running/candidate/startup awareness; confirmed-commit/rollback/validate/xpath capability evidence; response hard limits; safe XML parser; no arbitrary RPC/edit-config surface. Base-1.1-only chunk framing remains deferred/fail-closed.
- RESTCONF: HTTPS discovery, strict host/path/query validation, production TLS verification, optional CA bundle, vault-resolved mTLS, bounded JSON/XML. One internal approval-gated JSON subtree replace performs pre-read/change/post-read verification and best-effort pre-image rollback; generic RESTCONF URL/method/body mutation is not exposed by Web/API/CLI.
- gNMI: Capabilities, Get, typed paths and bounded ONCE Subscribe through allow-resolved `gnmic`; deadline/size enforcement, TLS/mTLS runtime config, mode-0600 ephemeral secret config and secret-free argv. gNMI Set is not exposed.
- Common: runtime vault credentials, fail-closed capability/path/TLS mismatches, metadata-only protocol trace, durable audit evidence, explicit CLI fallback only when configured, and existing RBAC/CSRF/change-safety boundaries retained.

Historical PH-3 source verification before Q-1 was **136 passed / 3 skipped**; focused PH-3 **22 passed**. Q-1 expands the service-backed PostgreSQL qualification surface, so these counts are provenance only. Current Q-1 evidence belongs in `TESTING_RESULT_2026-09-12.md`.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

Real vendor protocol interoperability, TLS/mTLS interoperability, production credential rotation, packaged `gnmic`, live PostgreSQL multi-node/HA, OpenSSH/Net-SNMP services, AlmaLinux RPM/systemd, Ruff/mypy, scale/load/failure, backup/restore/PITR and SMTP/O365 remain deferred.

### Continuation rule

No next implementation phase is assigned. When the user asks for the next phase, perform the roadmap / qualification review first and choose a phase explicitly; do not infer a numbered implementation phase from historical labels.


# Canonical Architecture Split — PH vs NI

## PH — Platform Hardening / Safe Device Change

PH answers:

> How do we safely change network devices?

### PH-4 — Structured Configuration Transaction Engine

Status: `IMPLEMENTED_IN_SOURCE / COMPLETION_HARDENING`

Scope:

- Structured change lifecycle
- Approval binding
- Pre-read snapshot
- Typed NETCONF / RESTCONF / gNMI operations
- Post-change verification
- Rollback and recovery workflow
- Audit evidence and provenance
- Confirmed-commit transaction handling

### PH-5 — Intent / Desired State Automation

Status: `PLANNED`

Scope:

- Desired state model
- Current vs desired comparison
- Drift detection
- Change plan generation
- Intent validation
- Approval workflow integration
- Remediation through PH-4 transaction engine

### PH-6 — Distributed Execution / HA

Status: `PLANNED`

Scope:

- Worker execution model
- Distributed queue
- Execution ownership
- Leader/fencing model
- Failover recovery
- Large-scale change orchestration
- Multi-node reliability


# NI — Network Intelligence

NI answers:

> What exists in the network and what is happening?

## NI-1 — Endpoint Location Correlation

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- IP → MAC correlation
- MAC → VLAN mapping
- VLAN → Switch port mapping
- Endpoint location discovery
- Q-BRIDGE FDB correlation
- Neighbor table correlation

Example:

```
IP
 |
MAC
 |
VLAN
 |
Switch Port
```

## NI-2 — Topology Identity

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- LLDP discovery
- CDP handling
- Device identity
- Chassis identity
- Interface identity
- Neighbor relationship
- Downstream impact traversal

## NI-3 — Network Events

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- SNMP Trap
- Syslog
- Link events
- Authentication events
- Reachability events
- Event normalization

## NI-4 — Alert Lifecycle

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- Alert promotion
- Severity handling
- Acknowledge workflow
- Resolve workflow
- Maintenance suppression
- Notification workflow

## NI-5 — Telemetry

Status: `PLANNED`

Scope:

- SNMP polling
- gNMI telemetry
- Streaming metrics
- Interface statistics
- CPU/memory/environment telemetry
- Time-series storage
- Trend analysis
- Performance baseline

## NI-6 — Discovery Analytics

Status: `PLANNED`

Scope:

### Auto Seed Discovery

- Seed device input
- Credential selection
- Discovery start workflow

### Full Network Crawl

- LLDP/CDP neighbor crawling
- Discovery queue
- Visited device tracking
- Crawl depth control
- Rate limiting
- Failure handling

### Topology Database

Nodes:

- Device
- Interface
- Link
- VLAN
- VRF
- Subnet
- Endpoint

Edges:

- CONNECTED_TO
- ATTACHED_TO
- CARRIES
- ROUTES_TO

### Unified L2/L3 Topology

- MAC path
- VLAN path
- IP path
- VRF path
- Routing relationship

### Topology Visualization

- Interactive topology graph
- Device map
- Link status
- VLAN view
- VRF view
- Path tracing
- Impact highlighting


## Release 35 PH-4 Completion Hardening

- NETCONF confirmed-commit lifecycle state model added.
- Recovery evidence schema integrated as transaction evidence boundary.
- PH-4 regression coverage added.
- Final qualification remains IMPLEMENTED_TESTING_DEFERRED until executed.


# PH-5 Intent / Desired State Automation

Status: IMPLEMENTED_TESTING_DEFERRED

Scope: DesiredState, Intent lifecycle, revisions, drift detection, Change Plan generation, PH-4 transaction integration boundary, approval and audit linkage.


# PH-5 API and Operations Surface

Status: IMPLEMENTED_TESTING_DEFERRED

Added PH-5 API helpers, intent workflow surface, and Web Console Intent Automation entry point. Device changes remain delegated to PH-4 transaction workflow.
