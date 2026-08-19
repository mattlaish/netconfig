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
- The Python web-console compatibility blocker is fixed in `web.py`, and the
  documented runtime now matches the Python 3.12 launcher and AlmaLinux 10 target.
- SNMP device views now expose all currently persisted system facts, interfaces,
  ARP and MAC/bridge data, while live walks show resolved names, raw OIDs, values,
  and the uploaded MIB file responsible for each mapping.
- The MIB library now reports per-file resolved/unresolved definitions and name
  conflicts; its lookup results also identify the mapping source.
- The device editor now treats a pure Application device as an endpoint monitor:
  it labels the target as a primary hostname/FQDN and hides SSH port, platform,
  and credential controls. Those controls return for mixed System/Network types.
- Uploaded vendor MIBs now drive bounded collection, not only name mapping:
  resolved enterprise `OBJECT-TYPE` definitions are matched to each device's
  `sysObjectID`, walked at a safe cadence, persisted, and shown on its SNMP page.
- SNMPv3 polling reuses engine discovery and RFC 3414 localized keys throughout
  each device poll instead of recomputing the 1 MB password-to-key operation for
  every OID, addressing the observed single-poller-thread CPU saturation pattern.

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

## Test and Environment Results (2026-08-18)
- Current development host: Windows, Python 3.12.13. Target integration host:
  AlmaLinux 10.2, Python 3.12.13.
- The full bundled self-test completes with `RESULT: ALL PASS` after the web
  compatibility and SNMP/MIB work, including settings-subpage and new MIB
  automap/source/diagnostic tests.
- `compileall` passes for all application modules and `selftest.py`.
- All 28 Python files pass parsing with Python 3.9 grammar mode; Python 3.12+ is
  nevertheless the supported deployment contract, matching AlmaLinux 10 and the
  installed launcher.
- CLI `--help` cannot run on the Windows host because the intended Unix-only SSH
  transport imports `pty`/`termios`. It previously passed on macOS and should be
  rechecked on AlmaLinux.
- No new live network-device, SNMP-agent, web-server, systemd, RPM, or end-to-end
  approval/execution test was performed in this task.

## Known Issues and Gaps
1. **Packaging source is incomplete:** the RPM spec, source archive/build script,
   and original RPM are absent. A reproducible next RPM cannot currently be
   built from this repository alone.
2. **Documentation/layout drift:** `INSTALL.md` advertises an absent `install.sh`
   and `/opt/netconfig/bin/netconfig`, but the payload contains
   `usr/bin/netconfig`. It also retains a v1 section saying the product is not a
   push tool, not multi-user, and logs into the web UI with the vault password;
   later v2 documentation and current code describe approval-based writes,
   user/RBAC login, and a separately unlocked vault.
3. **Executable metadata gap:** Git records `usr/bin/netconfig` as mode `100644`,
   not executable. The extracted filesystem modes are generally `0664`; RPM mode
   metadata was not preserved by the import and must be recovered/defined before
   packaging.
4. **Integration coverage is missing:** the self-test is broad but is a single
   script and does not cover real OpenSSH/device prompts, real vendor SNMP,
   HTTP request flows, systemd sandbox behavior, installation/upgrade, or RPM
   output. Existing docs explicitly note that configuration push was tested only
   with a fake Cisco device/local sshd and that real vendor behavior varies.
5. **Platform-dependent module:** `transport.py` imports `pty`; runtime support is
   Unix-specific. Linux remains the intended deployment target.

## Important Decisions
- Preserve the extracted filesystem layout until packaging sources are
  reconstructed; make application changes under `opt/netconfig/` and packaging
  changes under their payload paths.
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

## In Progress
No implementation is in progress. The compatibility and SNMP/MIB visibility
work is complete and remains uncommitted for the user to handle with Git.

## Recommended Next Step
Validate the expanded SNMP/MIB pages and reduced SNMPv3 CPU use against one real
AlmaLinux-hosted device and representative vendor MIB dependency set. Then reconstruct the RPM spec/build
inputs for AlmaLinux 10.2, restore payload ownership/executable modes, and add a
Linux packaging/integration test.

## Last Verified
2026-08-18 in the repository working tree on Windows with Python 3.12.13.
`manager.py`, `mib.py`, `web.py`, `selftest.py`, `INSTALL.md`, and this handoff
are intentionally modified and remain uncommitted for the user to manage with Git.
