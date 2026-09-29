# R62 — PostgreSQL / Concurrency / Recovery Hardening

Status: `IMPLEMENTED_TESTING_DEFERRED`

R62 treats SQLite as development/small-lab support and hardens the production PostgreSQL path.

## Invariants

- Unknown-outcome writes/transactions after connection loss are never replayed automatically.
- Read-only SELECT/SHOW/VALUES may reconnect and retry once after a connection-class failure.
- Dedicated DB-only transactions retry only SQLSTATE 40001 and 40P01, with a bounded attempt count.
- Dedicated transaction concurrency is bounded; budget exhaustion fails closed.
- MC-10 correlation retains its incident advisory-lock boundary.
- MC-11 planning remains analysis/proposal-only; same deterministic plan identity is serialized locally and across PostgreSQL nodes.
- External evidence remains inbound-only and same idempotency identity is serialized locally/across PostgreSQL nodes.
- No MC-12 is created.

## Live qualification

Use `packaging/r62-qualify.sh`. Live gates require explicit `NETCONFIG_R62_LIVE_POSTGRES=1` and site-provided fixed hooks. Local/fake-driver/SQLite tests never count as live PostgreSQL PASS.

### R62 source/offline qualification truth — 2026-09-24

- Repository: **453 collected / 442 PASS / 11 SKIP / 0 FAIL**.
- R62 focused: **15/15 PASS**. MC-11 authority regression: **12/12 PASS**.
- Compileall, launcher/R62 py_compile, packaging/hook shell syntax, and legacy selftest: **PASS**.
- Initial R62 campaign on this runner: **3 LOCAL_REGRESSION PASS / 0 FAIL / 12 BLOCKED_ENVIRONMENT / 0 NOT_RUN / 0 LIVE_POSTGRESQL PASS**. Production PostgreSQL claim remains false.
- Offline helper RPM: **99 payload files**, two source-tree rebuilds byte-identical, independent verifier PASS, SHA-256 `c47c4a7a1a8e2c26e86d7f5135965df3beced8fa38e593c7de8df457721edc1b`. This is not canonical live PostgreSQL/AlmaLinux evidence.
- Initial evidence bundle SHA-256: `b723e441bc309bdee8a142071f5e13271ce39c50cfd739728b7e2dccd2e60f4a`.

### R62 verified clean-extract truth

Provisional system-unzip clean extraction reproduced **453 collected / 442 PASS / 11 SKIP / 0 FAIL**; R62 focused **15/15 PASS**, MC-11 focused **12/12 PASS**, compileall/py_compile/shell/selftest PASS. Two clean-extract helper RPM rebuilds were byte-identical to the source-tree helper RPM and independently verified. Final frozen-artifact revalidation is performed after this documentation sync.

