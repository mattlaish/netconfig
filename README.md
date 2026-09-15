# NetConfig

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.

## Release 34 — UI-1 Unified Automation & Operations Console

UI-1 adds a single `/operations` Web Console for the Release 33 automation plane without creating a second execution path. The console covers PH-4 structured transaction review/recovery, NI-5 telemetry lifecycle and time-series summaries, VM-1 model packs and device bindings, NA-1 desired-state revision/plan/drift/run evidence, NA-2 fleet campaign waves/retry/abort/approval, and HA-1 node lifecycle/recovery-drill evidence.

All network mutation requests continue through the existing durable `change_requests` workflow: submit intent → freeze model/device/resource snapshot and SHA-256 → independent approval → revalidate current snapshot → execute → verify → audit/recovery evidence. The UI cannot supply caller-declared approval, arbitrary RPC XML, arbitrary REST bodies, protobuf requests, or shell/CLI tunnels. Admin-only recovery/model/HA controls remain admin-only in the Web layer and the underlying service/API boundaries.

Release 34 also adds an audited telemetry subscription edit contract; device rebinding is intentionally not supported in-place. Delete/recreate is required to preserve unambiguous device history.

Offline source verification after UI-1 implementation: UI-1 focused **7 passed**; combined UI-1/automation/PH-1/PH-2/PH-3/Q-1 focused **73 passed**; full repository **175 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall, launcher `py_compile`, and packaging shell syntax **PASS**. Ruff/mypy and live/service-backed gates remain `NOT_RUN`/deferred where the required tooling or environment is unavailable.


## Release 33 structured automation expansion

Release 33 builds on PH-3/Q-1 without replacing their safety boundaries. Structured network writes now flow through a single typed transaction plane: submit a durable change request, freeze the resolved device/model/resource plan, obtain separate approval, then execute with pre-read/change/post-read verification and rollback/recovery evidence. Caller-supplied arbitrary RPC XML, REST URLs/bodies, protobuf requests, shell/CLI tunnelling, and caller-declared approval remain prohibited.

The same transaction plane is used by desired-state runs and fleet campaigns. NI-5 adds bounded gNMI telemetry collection and time-series normalization; VM-1 owns model/resource mappings; HA-1 adds drain/readiness/recovery evidence on the PH-2 distributed core. These capabilities are source-complete but remain `IMPLEMENTED_TESTING_DEFERRED` until consolidated and live qualification evidence is recorded.

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
