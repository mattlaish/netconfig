# NetConfig

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 45 — Operator UX Simplification

Release 45 addresses operator usability rather than adding a new Network Intelligence phase. The main navigation no longer exposes a duplicate **Network Intelligence** entry because that function already exists inside **Operations**. `/operations` now opens a task-oriented **Overview** explaining which workflow to use for one-off structured changes, desired state, campaigns, telemetry, intelligence, automation requests, model packs, and HA/DR. The repaired automation ledger is renamed **Automation Requests** to make its purpose explicit.

`/protocols` remains route-compatible but is presented as **Device Collection**: current read protocols are shown first, **Collect now** is the normal action, and NETCONF/RESTCONF/gNMI profile editing is placed under an Advanced disclosure. The MIB library now explains that MIBs are dictionaries rather than product features, surfaces only useful counts and lookup by default, and hides the raw file inventory under Advanced. Per-device SNMP pages likewise hide raw OID walks and vendor MIB values under Advanced sections; normal operational interface, ARP, and MAC/FDB views remain first-class.

There is no schema or public REST contract change. Package release advances to `2.0.0-45` because shipped web/runtime source changed. Status remains `IMPLEMENTED_TESTING_DEFERRED`; NI-7 remains the feature baseline and Q-1 remains open.

**Release 45 qualification on the archive-derived workspace:** repository tests executed in four bounded groups total **221 passed / 8 skipped / 0 failed**; the eight skips are seven live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console regressions cover the Operations overview, single-surface Network Intelligence navigation, Automation Requests HTTP rendering, Device Collection guidance, and MIB purpose/advanced-library presentation. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because the executable is unavailable. The offline RPM builder emitted `netconfig-2.0.0-45.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `91cfea8b74a4c9b65472bafd59852513bf30a1adb9d87f5c6be3023e4a246efd`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.
## 2026-09-18 design decisions — site resilience, operator UX, and MIB summaries

These are recorded design decisions for future work. They do **not** create a new implementation phase, do not change the Release 45 runtime, and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

- **Distributed collection is justified by site survivability, not only scale.** A site must continue observing local network state even when its WAN/uplink path to the central NetConfig controller is lost. This addresses the failure mode where a central monitor can detect a fault but cannot deliver the alert because the same path needed for notification has failed.
- **Central Controller responsibilities:** global inventory, global topology/correlation, aggregated analytics, cross-site visibility, central audit, and configuration/change-control workflows.
- **Site Edge / Collector responsibilities:** read-only device polling, local cache/spool, local health evaluation, local alert generation/history, local UI, store-and-forward telemetry, and an independent heartbeat to the controller. Site isolation must be represented explicitly rather than treated as generic collector failure.
- **Collectors are read-only by default.** Allowed collection operations include SNMP GET/WALK, NETCONF GET/read, RESTCONF GET/read, and gNMI subscribe/read. Configuration push and arbitrary SSH are prohibited by default. Future distributed write execution must use a separate **Execution Node** or an explicitly authorized execution role with the existing change-control safety boundaries.
- **Alert-path resilience:** local alerts must be persisted when the controller/primary notification path is unreachable and replayed/synchronized after connectivity returns. Future optional fallback notification channels may include a local relay, secondary WAN, LTE/5G, SMS, or other out-of-band paths; none are claimed implemented by this documentation decision.
- **Configuration terminology:** user-facing `Configuration Baselines` should be described as **Configuration Baselines / Templates & Drift** so the baseline/template/drift use case is immediately understandable.
- **Approval scope:** retain the existing approval/request functionality for compatibility and safety, but do not expand the approval model now. Future integration may delegate/bridge approval authority to systems such as ServiceNow/SOAR while preserving NetConfig execution-time validation and fail-closed safety checks.
- **MIB UX direction:** raw MIB/OID data remains available for advanced troubleshooting, but normal operator views should summarize collected evidence into feature-oriented sensor cards/health indicators such as **Loop Protection — enabled ports / loop detected / last event**, PoE, STP, LACP, port errors, thermal/fan/PSU state, FDB/ARP coverage, and similar operational meaning.
- **I/O rule for visualization:** sensor cards should reuse already-collected DB/cache evidence by default. Visualization alone must not shorten poll intervals or add new device walks. New OIDs, higher-frequency polling, or additional collection breadth require a separate explicit design/qualification decision.


## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.


## Current roadmap position

NI-7 is the current feature baseline. The post-NI-7 roadmap review is complete and no new development phase is assigned. Q-1 remains open for production/service qualification; future NI-8/Q-2 or other feature work requires an explicit roadmap decision.

## Historical Release 43 — Console Sidebar Theme Refresh

Release 43 reworks the user-visible console chrome only: it converts the crowded top navigation into a persistent left sidebar, applies the supplied green theme variables and interaction styling, and removes organization-specific branding from the visible UI. There is **no schema or API change** in this refresh. Release 42's deterministic offline RPM builder/verifier remains available under `tools/rpm-builder/` with the same `SOURCE_DATE_EPOCH=1789689600` default, and production qualification still depends on canonical AlmaLinux 10 `rpmbuild`, DNF install/upgrade, systemd restart/reboot, SELinux behavior, and the remaining Q-1 live gates.

Focused regression for this refresh covers compileall plus the UI web-console tests, including a new assertion for sidebar rendering and neutral branding.

> **Release 43 RPM status:** source identity now targets `netconfig-2.0.0-43.el10.noarch.rpm`. The offline helper remains available for unsigned structural verification, but canonical AlmaLinux `rpmbuild` production packaging and DNF/systemd/SELinux qualification remain deferred.

## Release 41 — Corrective REST + Git/Ruff Hardening

Release 41 is a corrective hardening release on top of the Release 40 NI-7 baseline. It fixes the dead `POST /api/v1/campaigns/{id}/retry` route by reading the form-encoded `wave` value through the same list-valued `form` contract used by sibling branches, and adds HTTP regression coverage for retry with and without an explicit wave. It also adds a Git-index executable-mode regression so clean-clone mode truth is checked as `100755`, not inferred from ZIP metadata, and removes the identified Ruff F821/B018/B905/B007/F401/F841-style debt without broadening the lint ignore set.

Current repository regression is **213 passed / 7 skipped / 0 failed**. The seven skips remain the existing PostgreSQL backup/live and OpenSSH/Net-SNMP service-backed gates. Ruff `0.16.7` remains **NOT_RUN on this isolated runner** because the executable cannot be downloaded or installed here; source-side rule-family inventory is supporting evidence only and is not recorded as Ruff PASS. Q-1 live PostgreSQL/protocol/vendor/device/AlmaLinux gates remain deferred.


Documentation truth map: see `DOCUMENTATION_STATUS.md` for the current-vs-historical file index and qualification interpretation.

## Historical Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

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

Production packaging targets **AlmaLinux 10** with RPM identity `netconfig-2.0.0-48.el10.noarch`.

```bash
sudo dnf install ./netconfig-2.0.0-48.el10.noarch.rpm
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

## Documentation truth sync

All maintained Markdown is indexed by `DOCUMENTATION_STATUS.md`. Historical release files retain their original measured evidence but are explicitly labeled so they cannot be mistaken for the current Release 43 state. The documentation-only sync does not change runtime/schema/API behavior.
## Release 50 MC-2 — Sensor history

Release 50 adds durable Sensor observations and meaningful state transitions, bounded retention, read-only history/transition APIs, and a recent-transition timeline on the device health page. History consumes persisted Sensor/evidence state only; it does not add device polling.

## Release 51 MC-3 — Normalized Operational Evidence

Release 51 establishes the cross-domain evidence envelope used by later correlation slices. `operational_events` now preserves legacy NI-3 fields while adding `domain`, `entity_type`, `entity_id`, `resource`, `status`, `observed_at`, and `evidence_ref`; every new event is normalized at the event-storage boundary into one of the defined operational domains. Existing SNMP trap and syslog collectors remain compatible and are not rewritten.

MC-3 bridges only **durable Sensor state transitions** into events. The manager captures a Sensor-transition high-water mark before its existing DB-only Sensor refresh and publishes only newly persisted transitions afterwards. Unchanged Sensor observations do not create events. Recovery transitions are represented explicitly, and a transition to `UNKNOWN` is informational evidence loss rather than an automatic critical event. Sensor-derived event references use `sensor-transition:<id>` so a durable transition can be correlated back to MC-2 history and re-bridging is idempotent.

The Events API supports normalized filtering and event detail reads, and the Events WebUI shows domain, provenance/source, affected entity/resource, evidence reference, event time, and the current related Sensor state when one can be resolved. No MC-3 path adds device polling or new device I/O.

## Release 51 pre-MC4 compatibility hotfix

The current Release 51 source includes a pre-MC4 compatibility patch while retaining `2.0.0-51` and `IMPLEMENTED_TESTING_DEFERRED` status. SNMPv3 standard AES-192/AES-256 now use Net-SNMP-compatible Blumenthal key extension; Cisco/Reeder AES-192/AES-256 are explicit compatibility choices (`aes192c` / `aes256c`).

Topology now keeps every managed inventory device visible even when LLDP/CDP is unavailable. Persisted FDB/MAC evidence may add a clearly-labelled `INFERRED` path when a managed MAC identity matches uniquely; inferred paths are not direct adjacency and are not used by downstream-impact traversal. `/topology` provides a dependency-free draggable/pannable/zoomable SVG canvas whose layout is browser-local only. `GET /api/v1/topology/graph` exposes the same read-only graph. These features reuse persisted evidence and do not increase polling/device I/O.

