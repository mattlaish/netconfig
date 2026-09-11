# NetConfig Testing Result — 2026-09-12

## Current Baseline

**Qualification Track Q-1 — Production Runtime & Service-backed Qualification**

Status: `IMPLEMENTED_TESTING_DEFERRED`

Latest feature baseline: **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`)

RPM source metadata: `2.0.0-32`

No Q-2 is assigned. Execute the deferred Q-1 live gates, then perform a fresh roadmap review.

## Q-1 Implementation Delivered in Source

Q-1 adds:

- coherent application/package version truth: Python/project Version `2.0.0`, RPM Release `32`;
- `netconfig qualify` secret-free runtime preflight;
- controlled PostgreSQL core `pg_dump` backup with atomic mode-0600 output and SHA-256 sidecar;
- recovery-safe `pg_restore` into an explicitly separate drill/standby database only;
- short-lived mode-0600 `PGPASSFILE` credential delivery, with no database password in argv;
- real PostgreSQL qualification tests for concurrent `FOR UPDATE SKIP LOCKED`, advisory-lock leadership/session-loss release, node heartbeats, SQLite migration/sequence repair and backup/restore recovery;
- Q-1 source, PostgreSQL and AlmaLinux/RPM/systemd qualification runners;
- hardened backup systemd unit;
- CI PostgreSQL 16/client recovery tooling and service-backed Q-1 test tier;
- complete RPM transfer-source content for tests/CI/control files/canonical ledgers.

No REST API endpoint or bearer-scope change was introduced. Session idle/absolute expiry remains deliberately deferred and unchanged.

## Final Source Regression Before Artifact Packaging

```text
Q-1 focused                 11 passed
PH-2 focused                 9 passed
PH-3 focused                22 passed
Full pytest                147 passed / 7 skipped
Legacy selftest            RESULT: ALL PASS
compileall                  PASS
launcher py_compile         PASS
packaging shell syntax      PASS
source CR offenders         0
required executable modes   7/7 = 0755
web.py structural baseline  3809 lines / 238409 bytes
```

The seven skips are intentional service-backed gates and are not passes:

1. real PostgreSQL multi-node distributed task claim / scheduler leadership;
2. real PostgreSQL advisory-lock release after session loss;
3. real SQLite → PostgreSQL migration and sequence repair;
4. real `pg_dump` / `pg_restore` recovery drill;
5. OpenSSH service-backed integration;
6. Net-SNMP service-backed integration;
7. PostgreSQL interface-history service-backed integration.

## Local Q-1 Environment Truth

The current execution environment is **Debian 13**, not the declared AlmaLinux 10 package target. It does not provide Ruff, mypy, `pg_dump`, `pg_restore`, PostgreSQL server tooling, `rpmbuild`, or RPM tooling. It also lacks the `ssh` executable required by the installed runtime. Therefore:

```text
packaging/q1-source-gates.sh       NOT_RUN (rc=2; Ruff unavailable)
packaging/q1-qualify-postgres.sh   NOT_RUN (rc=2; pg_dump unavailable)
packaging/q1-qualify-almalinux.sh  NOT_RUN (rc=20; host is Debian 13)
packaging/build-rpm.sh             NOT_RUN (rc=2; rpmbuild unavailable)
netconfig qualify                  NOT_READY (required ssh executable absent)
```

An attempted package installation of Ruff/mypy could not proceed because this isolated environment has no external package-name resolution. These tools are therefore not reported as passing. The runtime preflight's refusal to return ready without `ssh` is expected fail-closed behavior; the RPM declares `/usr/bin/ssh` as a runtime requirement.

## Q-1 Live Gates Still Required

Before Q-1 may move beyond `IMPLEMENTED_TESTING_DEFERRED`, execute and retain evidence for the applicable gates:

- `packaging/q1-source-gates.sh` in a Python 3.12+ quality environment with Ruff, mypy and psycopg;
- `packaging/q1-qualify-postgres.sh` against disposable real PostgreSQL with explicitly supplied test credentials and `pg_dump`/`pg_restore`;
- `packaging/q1-qualify-almalinux.sh --install` on disposable AlmaLinux 10 with `NETCONFIG_Q1_ALLOW_INSTALL=1`;
- installed RPM smoke, systemd unit verification, service restart/reboot and credential-delivery behavior;
- successful service-backed OpenSSH/Net-SNMP/PostgreSQL integration tied to the exact candidate artifact.

PostgreSQL HA/failover/PITR, scale/load/failure qualification, representative NETCONF/RESTCONF/gNMI vendor interoperability, production TLS/mTLS/credential rotation, Cisco/Juniper/Arista/Huawei qualification, and live SMTP/O365 remain explicitly deferred unless separately executed.

## Security / Recovery Boundaries Verified Offline

- PostgreSQL backup/restore passwords are not placed in process argv.
- Temporary PostgreSQL password files are mode `0600` and deleted after use.
- Backup output is atomic, mode `0600`, non-empty and SHA-256 recorded.
- Restore requires checksum verification and literal confirmation `RESTORE_DATABASE`.
- Restore refuses the currently configured active core database.
- Recovery-safe restore can operate without opening the failed active core database.
- Production runtime readiness fails closed for missing required dependencies.
- AlmaLinux installation requires both explicit `--install` and `NETCONFIG_Q1_ALLOW_INSTALL=1`.
- Existing PH-1 CSP/RBAC/CSRF, PH-2 storage credential, PH-3 structured-adapter and diagnostic redaction boundaries remain unchanged.

## Artifact Packaging Integrity Gate

Clean Q-1 candidate `netconfig_qualification_q1_candidate_2026-09-12.zip` (SHA-256 `185039eadf8e8e63a8dad358df35f759a7a1f099d5fa6a3456a50e023920a2b1`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; source/extracted byte identity **125/125 PASS**; payload plus each SHA manifest **121/121 PASS**; required executable modes **7/7 = 0755**; extracted Q-1 focused **11 passed**; extracted full regression **147 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.

The final FULL ZIP is rebuilt only after this evidence is synchronized. Its SHA-256 is reported externally with delivery; the final ZIP itself must be independently extracted and retested before delivery.
