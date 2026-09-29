# R60 — Appliance Reliability & Lifecycle Hardening

Status: `IMPLEMENTED_TESTING_DEFERRED`  
Package: `2.0.0-60`  
Schema: `mc11-topology-change-planning-1` (unchanged)

R60 is production-readiness hardening, not a new MC feature slice. MC-11 remains final and all device changes still require the existing Automation Request / Structured Change authority.

**R60 local/offline and clean-extract qualification (2026-09-24):** repository regression is **418 collected / 410 passed / 8 skipped / 0 failed**; R60 focused lifecycle/qualification coverage is **24/24 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, launcher/Q2/R60 `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The dependency-free helper RPM contains **99 payload files**; two source-tree builds and two clean-extract builds are byte-identical and independently verified, SHA-256 `901142aab3041272d0929360bee1d555f5e5600fa428fd771bcbdceff75469ad`. The initial R60 campaign on the current non-AlmaLinux runner records **3 LOCAL_REGRESSION PASS / 0 FAIL / 0 BLOCKED_ENVIRONMENT / 10 NOT_RUN / 0 LIVE_PRODUCTION PASS** because destructive appliance hooks were not authorized/executed in this runner. These results do not promote R60 beyond `IMPLEMENTED_TESTING_DEFERRED`; live AlmaLinux R59→R60 upgrade/rollback, systemd/SELinux/reboot/crash/disk-pressure and PostgreSQL rollback-database gates remain separate live evidence.

## Lifecycle invariants

1. Only a supported R59 appliance is accepted by the transactional R60 upgrade wrapper.
2. Before package replacement, local NetConfig state and `/etc/default/netconfig` are snapshotted with SHA-256 evidence and a free-space reserve.
3. Symlinked/non-regular local state fails closed.
4. External vault-master, PostgreSQL-password, evidence-signing and configured TLS files are fingerprinted but not copied into qualification evidence.
5. NetConfig units are stopped and runtime-masked during DNF package replacement so scriptlets cannot silently restart the application mid-transaction.
6. Package identity, CLI smoke, systemd-unit validation and preservation checks must pass before the prior service state is restored.
7. Any upgrade/smoke/preservation failure enters deterministic rollback. Failure to prove downgrade or local-state restore becomes `RECOVERY_REQUIRED`.
8. SQLite rollback restores the complete pre-upgrade local state after package downgrade.
9. PostgreSQL rollback never hot-restores over the active database. A checksummed pre-upgrade dump must be restored into a separate rollback database and validated before destructive upgrade testing; after package/local-state rollback, NetConfig can be explicitly repointed to that database.
10. Snapshot retention is explicit; operators may list oldest snapshots beyond a bounded keep count but deletion is not automatic in the lifecycle helper.

## Commands

Local state operations (offline-safe; they do not initialize the Manager/database before restore):

```text
netconfig lifecycle snapshot --output /secure/netconfig-r60/pre-upgrade
netconfig lifecycle verify /secure/netconfig-r60/pre-upgrade
netconfig lifecycle verify-live /secure/netconfig-r60/pre-upgrade
netconfig lifecycle restore-local /secure/netconfig-r60/pre-upgrade --confirm RESTORE_LOCAL_STATE
netconfig lifecycle retention-candidates --root /secure/netconfig-r60 --keep 3
netconfig lifecycle switch-postgres-rollback --target-dbname netconfig_r60_rollback --confirm SWITCH_POSTGRES_ROLLBACK
```

Controlled R59→R60 package transition:

```text
sudo ./packaging/r60-lifecycle-upgrade.sh \
  --target-rpm ./netconfig-2.0.0-60.el10.noarch.rpm \
  --rollback-rpm ./netconfig-2.0.0-59.el10.noarch.rpm \
  --allow-destructive
```

PostgreSQL deployments additionally supply `--postgres-rollback-db` and a root-only readiness marker proving that a checksum-bound pre-upgrade backup has been restored and validated in the named separate database.

## Disk, log, retention and maintenance truth

The lifecycle snapshot performs a free-space preflight before copying state and refuses insufficient capacity. NetConfig application logs are emitted to stderr/stdout and managed by systemd/journald rather than an unbounded product-owned log file; R60 live qualification therefore validates journal/log retention at the appliance layer. Existing bounded product-retention mechanisms remain authoritative for telemetry, correlation runs, diagnostics, monitor history and configuration versions. PostgreSQL maintenance/recovery remains a live qualification concern and is not inferred from SQLite tests.

## Qualification

Run local and live R60 gates with:

```text
./packaging/r60-qualify.sh --output-dir /secure/evidence/r60-local --include-local
sudo ./packaging/r60-qualify.sh --output-dir /secure/evidence/r60-live \
  --live --allow-destructive --hook-dir /secure/netconfig-r60-hooks
```

Gate states are only `PASS`, `FAIL`, `BLOCKED_ENVIRONMENT`, or `NOT_RUN`. A local snapshot/rollback simulation is never a live AlmaLinux, PostgreSQL, reboot or disk-pressure PASS.
