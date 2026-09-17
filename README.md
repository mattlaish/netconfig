# NetConfig

> **Canonical project state — 2026-09-17:** **CURRENT IMPLEMENTATION BASELINE** = **Release 40 / NI-7 L3/VRF Path & Route Dependency Intelligence** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-40`; NI-1 through NI-7 and Enterprise Operations are implemented in source. Q-1 live PostgreSQL/protocol/vendor/device/AlmaLinux gates remain deferred/`NOT_RUN`; Release 40 does not promote them to PASS.

## Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

Release 40 resumes product development while explicitly leaving Q-1 live qualification deferred. NI-7 adds durable `l3_route_observations`, deterministic VRF-scoped route traversal, `L3_PATH` and `ROUTE_DEPENDENCY` insights, scoped REST endpoints, and Network Intelligence operator workflows. Traversal never crosses VRFs, never infers a managed next device from a next-hop IP, is bounded/cycle-safe, and stops on missing, unmanaged, mixed-terminal, or multipath-ambiguous evidence. Route-dependency results are explicitly **candidates**, not outage claims; observed alternate route evidence is surfaced without guessing ECMP/FIB forwarding choice. No NI-7 API or UI path can execute device configuration; configuration actions remain behind the existing approved Structured Changes / Desired State / Campaign workflow.

Current source regression after NI-7 implementation is **211 passed / 7 skipped / 0 failed**. The seven skips remain the existing PostgreSQL backup/live and OpenSSH/Net-SNMP service-backed gates. Q-1 live qualification remains deferred and does not block this feature baseline.

## Release 39 Q-1 Production Qualification Hardening

Release 39 is a qualification/packaging hardening release, not a new product feature slice. Q-1 found and fixes a guarded-installer defect in Release 38 where `install-rpm.sh` displayed Release 38 but still compared the package release against `37`. Release 39 advances the RPM identity to `2.0.0-39`, pins both Ruff `0.16.7` and mypy `2.3.1`, pins GitHub Actions checkout/setup-python to immutable Node-24-compatible revisions, and adds an AlmaLinux 10 RPM build/static qualification job.

Current source verification after the Q-1 fixes is **206 passed / 7 skipped / 0 failed**, Q-1 focused **12 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell/YAML checks **PASS**, Git index executable modes **8/8 = 100755**, and staged systemd unit verification **PASS**. The current isolated runner does not contain Ruff/mypy/PostgreSQL/OpenSSH/Net-SNMP/RPM tooling and cannot download packages. `netconfig qualify` therefore correctly fails this host's runtime readiness on the required SSH client. Ruff/mypy, PostgreSQL, protocol-service and AlmaLinux target gates remain `NOT_RUN` here; GitHub CI and disposable target environments must provide actual service-backed evidence before promotion. See `Q1_PRODUCTION_QUALIFICATION.md`.

## Historical Release 38 Git reproducibility baseline

Release 38 closes the difference between ZIP/file-system executable bits and Git checkout truth. The eight launcher/packaging entry points are committed as Git mode `100755`, and CI verifies the index mode with `git ls-files --stage` before Ruff or tests. A fresh local clone from the committed object database reproduced all eight executable bits and passed `204 passed / 7 skipped / 0 failed`, legacy selftest `ALL PASS`, compileall, launcher `py_compile`, and packaging shell syntax. Ruff is pinned to `0.16.7` in `requirements-quality.txt` and CI; this runner still records Ruff as **NOT_RUN** because the executable cannot be installed/downloaded here. Ruff and mypy are **NOT_RUN** in the current isolated runner because those tools are unavailable; this is not a PASS claim. See `GIT_REPRODUCIBILITY.md`.

## NI-6 Enterprise Operations & Qualification Hardening

The NI-6 analytics foundation is now a product surface rather than a library-only layer. `Manager.analytics` owns the durable analytics boundary, `network_insights` and `analytics_jobs` persist operator-visible evidence and execution history, bearer API scopes `analytics:read` / `analytics:write` protect the REST surface, and the Web Console exposes an Operations → **Network Intelligence** dashboard.

The console supports durable insight lifecycle (`NEW`, `ACKNOWLEDGED`, `RESOLVED`, `EXPIRED`), type/state/object/search filters, evidence and affected-object drill-down, explicit managed-topology impact simulation, Capacity/Failure Risk/Health refresh, and links to topology, endpoint, event and telemetry evidence. The product boundary is intentionally non-remediating: analytics output contains no device command path. Any change action continues through Structured Changes, Desired State or Campaign approval.

Impact simulation now treats existing resolved managed L2 adjacency as authoritative and directional. Unmanaged/unresolved topology is not traversed. Health supports `UNKNOWN` when there is no evidence.

Source-tree verification before packaging: **202 passed / 7 skipped / 0 failed**, selftest **ALL PASS**, compileall and launcher/package shell syntax **PASS**. `web.py` remains **239,648 bytes / 3,850 lines**, preserving the PH-1 size boundary.

## Installation

Production packaging targets **AlmaLinux 10** with RPM identity `netconfig-2.0.0-40.el10.noarch`.

```bash
sudo dnf install ./netconfig-2.0.0-40.el10.noarch.rpm
sudo -u netconfig /usr/bin/netconfig user add admin \
  --role admin --fullname "NetConfig Administrator"
sudo systemctl enable --now netconfig-web.service netconfig-backup.timer
```

The web console binds to `127.0.0.1:8778` by default; use an SSH tunnel or TLS reverse proxy/WAF for remote administration. Existing upgrades retain `/var/lib/netconfig`, and `/etc/default/netconfig` is installed as `%config(noreplace)`. See `opt/netconfig/INSTALL.md` for the full fresh-install, upgrade, secrets, PostgreSQL, verification, and recovery procedure; use `packaging/build-rpm.sh`, `packaging/inspect-rpm.sh`, and `packaging/install-rpm.sh` for the RPM lifecycle.

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

## NI-6.4 Failure Risk Foundation

NI-6.4 adds deterministic, evidence-backed operational failure-risk analysis in `netconfig.analytics.failure_risk`. The analyzer accepts only normalized allow-listed signals, preserves tenant and evidence references, and emits `FAILURE_RISK` insight data. It does not expose device execution, shutdown, configuration, remediation, or approval-bypass behavior.

Current offline evidence for this delivery: focused NI-6.3/NI-6.4 analytics **9 passed**; full repository **192 passed / 7 skipped**; legacy selftest **ALL PASS**; analytics/source `compileall` **PASS**. The seven skips remain existing live/service-backed PostgreSQL and protocol gates. Q-1/Ruff remains `NOT_RUN` by explicit deferral and is not counted as PASS.



NI-6.6 Health Dashboard: IMPLEMENTED_TESTING_DEFERRED
