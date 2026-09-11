# NetConfig

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

NetConfig is a network configuration, diagnostics, topology/intelligence, alerting, and controlled-change platform. SQLite remains the default development/single-node backend; PostgreSQL is an explicit fail-closed distributed-core option.

## Q-1 production runtime qualification

Q-1 adds production-readiness controls without changing PH-3 protocol behavior:

- `netconfig qualify` emits a secret-free, configuration-aware runtime preflight. PostgreSQL client tools are required when the PostgreSQL core is active; `gnmic` is required only when an enabled gNMI profile exists.
- `netconfig storage backup-postgres --output FILE` creates an atomic custom-format core backup plus SHA-256 sidecar using `pg_dump`.
- `netconfig storage restore-postgres --input FILE --target-dbname DRILL --confirm RESTORE_DATABASE` verifies integrity and restores only to a separate drill/standby database; it refuses to overwrite the active configured core database.
- PostgreSQL client authentication uses a short-lived mode-0600 `PGPASSFILE`; secrets never appear in command argv.
- `packaging/q1-source-gates.sh`, `packaging/q1-qualify-postgres.sh`, and `packaging/q1-qualify-almalinux.sh` provide fail-closed source, real-PostgreSQL, and AlmaLinux/RPM qualification entry points.
- The real PostgreSQL integration tier covers concurrent `SKIP LOCKED` claims, advisory-lock leadership/session-loss release, node heartbeats, SQLite migration sequence repair, and pg_dump/pg_restore recovery drill.

Q-1 remains `IMPLEMENTED_TESTING_DEFERRED` until the applicable live gates are executed. This environment does not contain PostgreSQL client/server tooling, Ruff/mypy, or AlmaLinux 10, so those gates are recorded as `NOT_RUN`, never as passing.

## PH-3 structured adapters

PH-3 adds bounded structured southbound support without creating generic remote execution:

- **NETCONF:** SSH subsystem transport, server hello/capability negotiation, fixed `<get>` and `<get-config>` reads, running/candidate/startup awareness from advertised capabilities, confirmed-commit/rollback capability reporting, hard response limits, timeout enforcement, and DTD/entity-rejecting XML parsing. Base-1.1-only chunked peers remain deferred.
- **RESTCONF:** HTTPS discovery, strict host/path/query validation, TLS verification by default, optional CA bundle and vault-resolved mTLS material, bounded JSON/XML reads, and an internal approval-gated JSON subtree replace primitive with pre-read, post-read verification, and best-effort pre-image rollback. Generic URL/method/body forwarding is not exposed by Web/API/CLI.
- **gNMI:** allow-resolved `gnmic`, Capabilities, Get, bounded ONCE Subscribe, typed path validation, TLS/mTLS-capable runtime configuration, deadlines, response-size limits, mode-0600 ephemeral credential files, and secret-free argv. gNMI Set is not exposed.

Structured collection remains fail-closed. CLI fallback occurs only when a device profile explicitly enables it. Protocol trace evidence is metadata-only. Credentials are resolved from the encrypted vault at execution time.

## Development and verification

Use Python 3.12. The source tree is directly testable without installing the package:

```bash
PYTHONPATH=opt/netconfig pytest -q
PYTHONPATH=opt/netconfig pytest -q tests/test_qualification_q1.py
PYTHONPATH=opt/netconfig pytest -q tests/test_platform_hardening_ph3.py
PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py
python -m compileall -q opt/netconfig
```

See `DEVELOPMENT.md`, `ROADMAP.md`, `SECURITY.md`, `API.md`, `TESTING.md`, and `TESTING_RESULT_2026-09-12.md` for implementation and qualification truth. Do not promote Q-1 or PH-3 to `TESTED` or `RELEASED` from offline/fake-driver evidence alone.
