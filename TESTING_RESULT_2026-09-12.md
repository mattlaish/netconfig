# NetConfig Testing Result — 2026-09-12

## Current Baseline

**CURRENT IMPLEMENTATION BASELINE:** HA-1 — Control-plane HA & Recovery Foundation

Status: `IMPLEMENTED_TESTING_DEFERRED`

Implemented-in-source expansion: **PH-4, NI-5, VM-1, NA-1, NA-2, HA-1**.

Qualification track **Q-1 — Production Runtime & Service-backed Qualification** remains `IMPLEMENTED_TESTING_DEFERRED`; applicable live gates are still deferred.

Application/project Version: `2.0.0`  
RPM source metadata: `2.0.0-33`  
Database schema revision: `ha1-2`

No next development phase is assigned. After Release 33 artifact verification and Q-1 live qualification, perform a fresh roadmap/qualification review.

## Release 33 Consolidated Source Verification

Executed after the implementation expansion and after correcting regressions found by the final focused run.

```text
automation + repo hygiene focused   23 passed
PH-2 focused                         9 passed
PH-3 focused                        22 passed
Q-1 focused                         11 passed
full pytest                        168 passed / 7 skipped
legacy selftest                    RESULT: ALL PASS
compileall                         PASS
launcher py_compile                PASS
packaging shell syntax             PASS
source text CR offenders            0
cache entries after cleanup         0
symlinks                            0
historical E701-style suites        0
required executable modes           7/7 = 0755
web.py structural observation       3855 lines / 239880 bytes
```

The final focused pass found real source defects and they were fixed before the green result:

1. NA-2 `resume()` could continue with unresolved failed/rolled-back targets and `retry_failed()` was advertised by CLI/API but missing in the service. Resume is now fail-closed until explicit retry/abort; explicit retry advances the next attempt identity; `ROLLBACK_FAILED` remains recovery-required rather than blindly replayed.
2. PH-4 typed gNMI Set accidentally changed the PH-3 public generic capability contract. Generic `set` remains false; PH-4 advertises only constrained approval-required typed Set.
3. A source-hygiene refactor placed Web query parsing after API dispatch, causing API GET 500s. Query parsing now occurs before dispatch.

## Seven Intentional Skips

The seven skipped tests are not passes:

1. real PostgreSQL multi-node distributed task claiming;
2. real PostgreSQL advisory-lock leadership/session-loss release;
3. real SQLite → PostgreSQL migration and sequence repair;
4. real PostgreSQL `pg_dump` / `pg_restore` recovery drill;
5. OpenSSH service-backed protocol integration;
6. Net-SNMP service-backed protocol integration;
7. PostgreSQL interface-history/service-backed integration.

## Ruff / mypy Truth

Ruff and mypy are **`NOT_RUN`** in this execution environment. Neither executable nor Python module is installed. `pip` installation failed because the isolated environment cannot resolve external package sources, and direct binary retrieval was also unavailable.

`packaging/q1-source-gates.sh` correctly fails closed with rc=2 at the missing Ruff prerequisite. No Ruff or mypy PASS is claimed.

Source hygiene performed without weakening the configured rules:

- historical E701-style same-line compound suites: **0** by AST structural check;
- text CR/CRLF offenders after cleanup: **0**;
- cache entries before packaging: **0**;
- symlinks: **0**;
- required raw-source executable modes: **7/7 = 0755**;
- Release/version truth is covered by repository hygiene regression tests.

The configured Ruff rule set remains `E`, `F`, `W`, `B`, `UP` with only the pre-existing `E501` and `E702` ignores. No new ignore was added to hide lint debt. Actual Ruff execution remains a required Q-1 gate when a Ruff-capable environment is available.

## Local Q-1 Environment Truth

```text
packaging/q1-source-gates.sh       NOT_RUN (rc=2; Ruff unavailable)
packaging/q1-qualify-postgres.sh   NOT_RUN (rc=2; pg_dump unavailable)
packaging/q1-qualify-almalinux.sh  NOT_RUN (rc=20; host is Debian 13)
packaging/build-rpm.sh             NOT_RUN (rc=2; rpmbuild unavailable)
netconfig qualify                  NOT_READY (rc=1; required ssh executable absent)
```

`netconfig qualify` otherwise confirmed Python 3.13.5, OpenSSL, and SQLite core storage revision `ha1-2`; optional `gnmic` is absent because no enabled gNMI profile requires it in this local preflight. Its refusal to return ready without `ssh` is expected fail-closed behavior.

## Security / Implementation Boundaries

- Public PH-4/NA-1/NA-2 network mutation cannot self-authorize with a caller-provided boolean; it executes through a durable approved `change_requests` record with frozen snapshot/hash verification.
- PH-4 preserves generic-passthrough denial for NETCONF/RESTCONF/gNMI and uses typed/model-pack-resolved operations.
- NA-2 failed/rolled-back targets require explicit retry or abort before resume; rollback failure is recovery-required.
- HA-1 drain state blocks new automation and relinquishes singleton scheduler leadership; automatic database failover is not claimed.
- Session idle/absolute expiry remains explicitly deferred security debt by user direction and was not implemented in Release 33.

## Artifact Packaging Integrity Gate

Clean Release 33 candidate `netconfig_release33_candidate_2026-09-12.zip` (SHA-256 `d03720a411b796458747f7d8976a8fa01f4f40859b5e51341ef031aaa343f538`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; text CR offenders **0**; source/extracted byte identity **132/132 PASS**; payload plus each SHA/release manifest **128/128 PASS**; required executable modes **7/7 = 0755**. From the clean extraction: Release 33 focused **23 passed**, PH-2 **9 passed**, PH-3 **22 passed**, Q-1 **11 passed**, full repository **168 passed / 7 skipped** in the isolated full-suite rerun, legacy selftest **ALL PASS**, and compileall/launcher py_compile/packaging shell syntax **PASS**. A first command that chained all suites hit the execution-tool timeout after full pytest reached ~82%; that interrupted run is not counted as PASS. The same candidate full suite was then rerun alone and completed cleanly (**168 passed / 7 skipped in 22.90s**).

The formal FULL ZIP is rebuilt after synchronizing this candidate evidence and all manifests, then independently clean-extracted and reverified.

## Status

All Release 33 implementation phases remain `IMPLEMENTED_TESTING_DEFERRED`. Offline regression success does not satisfy real PostgreSQL, AlmaLinux/RPM/systemd, real network-device, TLS/mTLS, vendor interoperability, SMTP/O365, scale/failure, or other live qualification gates.
