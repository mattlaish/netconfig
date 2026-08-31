# AI Development Handoff

## Project
NetConfig (reconstructed from `netconfig-2.0.0-14`; current packaging target
`netconfig-2.0.0-16.el10`)

## Objective
Continue development and improvement of the NetConfig platform from the
reconstructed RPM payload while preserving its existing behavior and packaging
layout.

`patch.md` is now the required chronological patch/version ledger. Future AI
work must read and update it together with this overall handoff.
After a completed development stage or README/handover/version-document update,
the final user feedback must end with `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)`.
## AI Git Workflow

AI may perform normal Git operations:

- `git pull`
- `git add`
- `git commit`
- `git push`

Before pushing:

- Run relevant tests and validation checks.
- Update `AI_HANDOFF.md` with completed work, verification results, and next recommended steps.
- Review `git diff` and `git status`.
- Ensure no secrets, credentials, generated binaries, temporary files, or unrelated changes are included.

Never:

- Force push.
- Rewrite history unless explicitly approved.
- Delete branches or change remotes without approval.

## Multi-Agent Coordination

- GitHub is the source of truth.
- Before starting work, synchronize with the latest repository state.
- Do not assume another AI agent's uncommitted local changes exist.
- Do not modify the same repository concurrently with another AI agent unless the work is isolated by branch.
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
tokens (session-cookie auth only today).

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
