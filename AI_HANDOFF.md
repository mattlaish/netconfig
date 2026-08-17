# AI Development Handoff

## Project
NetConfig (`netconfig-2.0.0-14`)

## Objective
Continue development and improvement of the NetConfig platform from the
reconstructed RPM payload while preserving its existing behavior and packaging
layout.

## Current Status
- The repository contains one commit (`eab14e1`, initial import) on `main`,
  tracking `origin/main`.
- This is an extracted RPM filesystem payload, not a conventional build tree.
  Application code is under `opt/netconfig/`; RPM integration files are under
  `etc/`, `usr/`, and `var/`.
- The application is a standard-library-only Python package. It uses the system
  OpenSSH client through a PTY for device access and SQLite for persistent state.
- No functional source changes have been made during baseline review.

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
There is currently no source build definition: no RPM spec, `pyproject.toml`,
`setup.py`, requirements file, Makefile, tox/pytest configuration, or CI config.
The imported payload is directly runnable in its installed filesystem layout.

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

## Test and Environment Results (2026-08-17)
- Host runtime: macOS, Python 3.9.6, OpenSSH 10.3p1.
- `python3 selftest.py`: all checks through monitoring passed (crypto vectors,
  vault, store/traversal protection, scrubbing, SNMP codecs/key derivation,
  users/RBAC, automation, compliance, drift, groups, interface samples,
  concurrent DB use, rename/retention, SHA-2/AES variants, and alert engine).
  The suite then aborted while importing `netconfig.web`; it did not execute the
  final settings-page checks or print `ALL PASS`.
- `compileall` with redirected cache: all modules compile except `web.py`.
- `python3 -m netconfig.cli --help` and `platforms`: successful on Python 3.9.6.
- `Manager` initialization against a temporary directory: successful.
- No live network-device, SNMP-agent, web-server, systemd, RPM, or end-to-end
  approval/execution test was performed.

## Known Issues and Gaps
1. **Python compatibility / web blocker:** `netconfig/web.py:753` embeds a string
   containing `\\u2014` inside an f-string expression. Python 3.9 rejects this with
   `SyntaxError: f-string expression part cannot include a backslash`. This makes
   the web console unusable and prevents the bundled self-test from completing
   on the documented minimum Python version.
2. **Runtime contract is inconsistent:** `INSTALL.md` says Python 3.9+, while the
   installed launcher has a hard-coded `#!/usr/bin/python3.12` shebang. Python
   3.12 was not available on the review host, so the installed launcher itself
   could not be exercised.
3. **Packaging source is incomplete:** the RPM spec, source archive/build script,
   and original RPM are absent. A reproducible next RPM cannot currently be
   built from this repository alone.
4. **Documentation/layout drift:** `INSTALL.md` advertises an absent `install.sh`
   and `/opt/netconfig/bin/netconfig`, but the payload contains
   `usr/bin/netconfig`. It also retains a v1 section saying the product is not a
   push tool, not multi-user, and logs into the web UI with the vault password;
   later v2 documentation and current code describe approval-based writes,
   user/RBAC login, and a separately unlocked vault.
5. **Executable metadata gap:** Git records `usr/bin/netconfig` as mode `100644`,
   not executable. The extracted filesystem modes are generally `0664`; RPM mode
   metadata was not preserved by the import and must be recovered/defined before
   packaging.
6. **Integration coverage is missing:** the self-test is broad but is a single
   script and does not cover real OpenSSH/device prompts, real vendor SNMP,
   HTTP request flows, systemd sandbox behavior, installation/upgrade, or RPM
   output. Existing docs explicitly note that configuration push was tested only
   with a fake Cisco device/local sshd and that real vendor behavior varies.
7. **Platform-dependent module:** `transport.py` imports `pty`; runtime support is
   Unix-specific. Linux remains the intended deployment target.

## Important Decisions
- Preserve the extracted filesystem layout until packaging sources are
  reconstructed; make application changes under `opt/netconfig/` and packaging
  changes under their payload paths.
- Treat Python 3.9 compatibility as the documented contract unless the project
  deliberately raises the minimum and updates launcher, docs, and tests together.
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

## In Progress
No implementation is in progress. Baseline review is complete.

## Recommended Next Step
Make the smallest source fix to the Python 3.9-incompatible f-string in
`netconfig/web.py`, then rerun the full self-test and compile check with an
isolated temporary data/cache directory. If that passes, reconcile and enforce
the supported Python version across the launcher and documentation. Afterward,
reconstruct the RPM spec/build inputs and add a Linux packaging/integration test
before making broader functional changes.

## Last Verified
2026-08-17 in the repository working tree on macOS with Python 3.9.6. Only
`AI_HANDOFF.md` was intentionally changed by this baseline task.
