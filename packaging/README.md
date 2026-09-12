# NetConfig RPM build (AlmaLinux 10)

> **Canonical project state — 2026-09-12:** **CURRENT IMPLEMENTATION BASELINE** = **HA-1 — Control-plane HA & Recovery Foundation** (`IMPLEMENTED_TESTING_DEFERRED`). **PH-4, NI-5, VM-1, NA-1, NA-2, and HA-1** are implemented in source; consolidated Release 33 offline regression is green, while live/service-backed qualification remains deferred. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; its live PostgreSQL/AlmaLinux/systemd/service-backed gates remain deferred. No further development phase is assigned until the post-implementation qualification/roadmap review. RPM source Release is `2.0.0-33`.

> **Current continuation pointer:** use the Release 33 full source baseline as the active implementation source. Historical CURRENT/NEXT statements below are chronology only. Use the recorded Release 33 offline/artifact evidence and run the applicable Q-1 live gates before any promotion to `TESTED`/`RELEASED`; then perform a fresh roadmap review before assigning another development phase.

This directory reconstructs the missing RPM source/build inputs. It builds an
unsigned test binary RPM and SRPM without using Git or including runtime data.


## Prepare the source on Windows

When the working copy is on Windows and the RPM will be built on AlmaLinux,
create a clean transfer bundle in the project root (not under `dist`):

```powershell
cd "C:\path\to\netconfig"
.\packaging\prepare-transfer.ps1
```

With the current spec this produces `netconfig-2.0.0-33-rpm-build-source.zip`. Transfer that one ZIP
file to the AlmaLinux build host. **Release 33 is the current source Release. Before producing a later distributable RPM, bump the spec Release; do not reuse a published release number for newer source.** The bundle contains only the application
payload, RPM tooling, and development/handover documents; it excludes Git data,
runtime state, Python caches, and previous RPM outputs.

## Build host preparation

Use an AlmaLinux 10 build host or disposable VM, not the production server:

```bash
sudo dnf install rpm-build python3.12
chmod +x packaging/*.sh
./packaging/build-rpm.sh
```

Artifacts are copied directly to the NetConfig project directory:

- `netconfig-2.0.0-33.el10.noarch.rpm`
- `netconfig-2.0.0-33.el10.src.rpm`

Inspect before installation:

```bash
./packaging/inspect-rpm.sh ./netconfig-2.0.0-33.el10.noarch.rpm
```

## Safe test sequence

1. Snapshot or clone an AlmaLinux 10.2 test VM.
2. Record `rpm -q netconfig` and back up `/var/lib/netconfig`.
3. Install the new RPM with `sudo dnf upgrade ./netconfig-2.0.0-33.el10.noarch.rpm`.
4. Run `./packaging/smoke-installed.sh`.
5. Start the service and verify the web, SNMP, MIB, backup timer, ownership,
   SELinux journal messages, and upgrade-retained vault/database content.
6. Do not deploy to production until a real-device SNMPv3 CPU/collection soak
   test passes.

The RPM intentionally leaves `/etc/default/netconfig` as `%config(noreplace)`
and owns only the `/var/lib/netconfig` directory, never its runtime contents.
The build also normalizes Linux launcher/unit text to LF; this prevents a
Windows-prepared source tree from producing systemd `203/EXEC` due to a CRLF
shebang.


## Phase 4D evidence signing runtime

The RPM now requires `/usr/bin/openssl` because Ed25519 evidence signing/verification uses a fixed-function OpenSSL adapter. No signing private key is packaged. Supply one separately via a systemd credential or a protected file only when evidence signing is enabled.


---

Historical NI-1 documentation snapshot: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. The current baseline is the Q-1 FULL source artifact described by the canonical header.

## PH-2 PostgreSQL packaging note

Release `2.0.0-30` adds optional PostgreSQL core support. The base RPM remains usable in SQLite mode without psycopg. A deployment that selects `core_db_backend=postgres` must also provide a compatible psycopg 3 driver in the Python 3.12 runtime and a PostgreSQL service credential. The current execution environment has not performed an AlmaLinux RPM build/install with psycopg, so that remains a release qualification gate rather than a claimed package dependency result.


PH-3 note: NETCONF and RESTCONF use existing system/OpenSSL/Python facilities. gNMI collection requires an external `gnmic` binary when selected; the current RPM source does not bundle or claim qualification of that optional executable.


## Q-1 qualification runners

Q-1 adds three fail-closed qualification entry points. They report an unavailable prerequisite as `NOT_RUN` rather than converting it into a pass:

```bash
./packaging/q1-source-gates.sh
./packaging/q1-qualify-postgres.sh
./packaging/q1-qualify-almalinux.sh
```

`q1-source-gates.sh` requires Python 3.12+, pytest, Ruff, mypy and a psycopg-capable development environment, then runs lint/type/compile/focused/full/selftest/shell/line-ending gates. `q1-qualify-postgres.sh` requires a real PostgreSQL service plus `pg_dump`, `pg_restore`, psycopg and an explicitly supplied `NETCONFIG_TEST_PG_PASSWORD`; it executes the real concurrency, advisory-lock/session-loss, migration/sequence and backup/restore drill tests. `q1-qualify-almalinux.sh` requires AlmaLinux 10 and RPM build tooling; package installation is not performed unless both `--install` and `NETCONFIG_Q1_ALLOW_INSTALL=1` are supplied.

Current spec metadata is **Version 2.0.0 / Release 33**. A later source change intended for distribution must increment Release before creating another RPM.
