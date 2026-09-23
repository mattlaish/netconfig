# Development Ledger

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


## Historical Release 43 — Offline RPM Builder Integration

Release 43 adds `tools/rpm-builder/`, a deterministic dependency-free RPM emitter plus an independent offline verifier. The helper reads `packaging/netconfig.spec`, packages only the canonical NetConfig runtime payload, preserves executable/config ownership semantics, encodes lifecycle scriptlets and dependencies, and verifies RPM header digests, gzip/newc payload integrity, source-byte identity, modes, `CONFIG|NOREPLACE`, requirements, and scriptlets. `SOURCE_DATE_EPOCH=1789689600` is the deterministic default for this release. The same source and epoch must produce byte-identical RPMs. This helper is **not** the production qualification authority: canonical AlmaLinux 10 `rpmbuild`, `rpm -qp`, DNF install/upgrade, systemd restart/reboot, SELinux behavior, and remaining Q-1 live gates stay deferred until actually executed.
Archive-derived qualification for Release 43 on this runner is **218 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the existing PostgreSQL backup/restore and OpenSSH/Net-SNMP integration gates plus the expected Git-index executable-mode skip because `.git` is intentionally absent from the source archive. Compileall and the focused sidebar/branding console regressions pass. The offline builder emitted `netconfig-2.0.0-43.el10.noarch.rpm` with SHA-256 `0bc3abca0b3349593f67593930e9c8e1298cfe511a42d24d38f4f2d26babc7c2`; the independent verifier passed RPM header digest, compressed payload digest, gzip/newc parsing, payload/source byte identity, modes, `CONFIG|NOREPLACE`, dependencies, and lifecycle scriptlets. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.



## Release 41 — Corrective REST + Git/Ruff Hardening

- Corrected campaign retry REST parsing from the undefined `body` name to `(form.get("wave") or [None])[0]` and added route-level regression for explicit/no-wave retry.
- Added direct Git-index mode regression for every required launcher/package helper; archive mode alone is no longer accepted as Git reproducibility evidence.
- Removed the identified B018/B905/B007/F401/F841-style debt without adding broad Ruff ignores. Actual Ruff execution remains `NOT_RUN` on this runner.
- Final fresh-clone repository regression: **213 passed / 7 skipped / 0 failed**; 8/8 Git index modes `100755`, manifest verification, legacy selftest, compileall/launcher/package-shell checks, and clean post-test worktree all PASS. Live PostgreSQL/backup and OpenSSH/Net-SNMP gates remain deferred.


## Historical Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

NI-7 resumes product development from Release 39 while explicitly leaving Q-1 live gates deferred. It adds durable explicit route observations, VRF-scoped bounded path simulation, route dependency candidates, `L3_PATH`/`ROUTE_DEPENDENCY` persisted insights, REST/API and Operations UI integration, and schema revision `ni7-l3-route-1`. The implementation never infers managed next-device identity from next-hop IP, never crosses VRFs, stops on ambiguous/incomplete evidence, and cannot execute network configuration. Pre-package regression is **211 passed / 7 skipped / 0 failed**.

### Release 40 final delivery qualification

The frozen delivery surface is independently qualified. The full-source Git-archive ZIP contains **199 archive entries**, matches **181/181 Git-tracked files byte-for-byte**, and has **0** path-traversal entries, **0** symlinks, **0** cache/bytecode entries, **0** operational-text CR offenders, and **8/8** required executable files at mode `0755`; source and metadata manifests verify. From its clean extraction, the complete repository test inventory executes as **211 passed / 7 skipped / 0 failed**, with legacy selftest **ALL PASS** and compile/launcher/package-shell checks **PASS**. The clonable Git bundle reproduces the same commit, manifest and 8/8 Git `100755` modes and executes the same **211/7/0** regression plus selftest/compile with a clean post-test worktree. The `2.0.0-40` RPM build-source bundle has no traversal/symlink/cache entries, preserves all eight executable modes, verifies manifests/package identity, and passes **25/25** focused NI-7/repository-hygiene/Q-1 tests. Actual AlmaLinux RPM build/install and Q-1 live service/vendor gates remain `NOT_RUN`/deferred. The final archive SHA-256 is intentionally carried in external `.sha256` sidecars so the payload does not self-reference its own digest.

## Historical Release 39 — Q-1 Production Qualification Hardening

Q-1 execution against Release 38 reproduced the fresh-clone 204/7 regression but exposed a real RPM installer identity defect: `packaging/install-rpm.sh` still compared the RPM Release against `37` while reporting an expected Release `38`. Release 39 fixes the guard and advances the package identity to `2.0.0-39`. The qualification toolchain is also made deterministic: Ruff is pinned to `0.16.7`, mypy to `2.3.1`, GitHub checkout/setup-python actions are pinned to immutable Node-24-compatible commits, and CI gains an AlmaLinux 10 RPM build/static qualification job. No product feature behavior is added. Live installed-runtime and external service gates remain deferred until actually executed.

Executed Release 39 local evidence: Q-1 focused **12 passed**; full repository **206 passed / 7 skipped / 0 failed**; legacy selftest **ALL PASS**; compileall, launcher compile, shell syntax, workflow YAML parse and CR scan **PASS**; staged installed-filesystem `systemd-analyze verify` **PASS**; Git index modes remain **8/8 = 100755**. Q-1 source gate returns exit `2` at the unavailable Ruff prerequisite, PostgreSQL gate exit `2` at missing `pg_dump`, AlmaLinux gate exit `20` on Debian 13, and runtime preflight returns not-ready because the required SSH client is absent. These are recorded as `NOT_RUN`/environment-not-ready rather than PASS.


## Release 38 — Git Reproducibility Hardening

Release 38 fixes the source-control reproducibility gap discovered after Release 37 packaging. Required raw executables are now committed as Git `100755`; CI verifies Git index modes rather than trusting only worktree/ZIP modes. Python 3.12 lint-modernisation changes remove legacy `timezone.utc`, deprecated `typing` collection imports/`Optional`, three confirmed unused imports, ambiguous exception chaining, and legacy `str, Enum` declarations without broadening Ruff ignores. Fresh-clone regression is **204 passed / 7 skipped / 0 failed** with selftest/compile/shell gates PASS. Actual Ruff/mypy execution remains NOT_RUN in this isolated runner. RPM release identity advances to `2.0.0-38` because changed source must not reuse the Release 37 package identity.


Ruff is pinned to `0.16.7` in `requirements-quality.txt` and CI; this runner still records Ruff as **NOT_RUN** because the executable cannot be installed/downloaded here.
## 2026-09-13 — Release 34 — UI-1 Unified Automation & Operations Console

Parent baseline: Release `2.0.0-33`, SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`.

Implementation changes:

- added `opt/netconfig/netconfig/web_ops.py` as a dedicated Web presentation/orchestration mixin so `web.py` remains below the PH-1 structural gate;
- added `/operations` to main navigation with six operator panels covering PH-4, NI-5, VM-1, NA-1, NA-2, and HA-1;
- automation Change Request review now shows frozen submitted/current resolved snapshot SHA-256 and drift state;
- added telemetry subscription update service/API operation with immutable device binding and fail-closed RUNNING-state edit rejection;
- added UI-1 Web regression coverage for viewer/operator/approver/admin boundaries, CSRF, durable approval, telemetry lifecycle, model/HA admin controls, desired-state/campaign approvals, and recovery evidence;
- bumped RPM source Release to `34`; no database schema revision is required by UI-1.

Rejected approaches / design decisions:

- rejected direct structured/desired/campaign network execution from UI forms; those forms submit durable automation CRs only;
- rejected putting UI-1 directly back into the `web.py` monolith; a separate mixin preserves PH-1 structural debt reduction;
- rejected in-place telemetry device rebinding because it makes retained sample/audit history ambiguous; delete/recreate is required;
- rejected weakening recovery authorization: structured recovery/model-pack/cluster-node lifecycle remain admin-only.

Source verification: UI-1 focused **7 passed**; combined focused **73 passed**; full repository **175 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher/shell syntax **PASS**; source CR/cache/symlink offenders **0** after cleanup; required executable modes **7/7 = 0755**. Ruff/mypy are `NOT_RUN` because binaries are unavailable in this isolated environment.

Candidate artifact evidence: `netconfig_ui1_release34_candidate_2026-09-13.zip` (SHA-256 `760cb9d411e54b991cc1c285e09fdd276c2364d8e4a497da6bd2d6d756e70d2a`) passed clean-extraction verification: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0** before testing; text CR offenders **0**; source/extracted byte identity **138/138 PASS**; payload and each of the three SHA manifests **133/133 PASS**; required executable modes **7/7 = 0755**. From that clean extraction, UI-1 focused **7 passed**, combined UI-1/automation/PH-1/PH-2/PH-3/Q-1 focused **73 passed**, full repository **175 passed / 7 skipped**, legacy selftest **ALL PASS**, and compileall/launcher `py_compile`/packaging shell syntax **PASS**. Ruff, mypy, `rpmbuild`, and PostgreSQL `pg_dump`/`pg_restore` remained **NOT_RUN** because those binaries are unavailable in this environment; none are counted as passing.


## 2026-09-12 — Release 33 — Automation / Telemetry / HA expansion

Status: `IMPLEMENTED_TESTING_DEFERRED`. Application/project Version remains `2.0.0`; RPM source Release is `33`; database schema revision is `ha1-2`.

Implemented:

- PH-4 durable structured transaction engine with mandatory real `change_requests` approval references, frozen automation-plan hash validation, per-device/advisory serialization, idempotency, pre/post evidence, explicit rollback state and interrupted-write recovery.
- NETCONF structured writes use generated typed config only and bounded protocol-native transaction semantics where capabilities permit; RESTCONF and gNMI writes remain typed/allow-listed and never expose arbitrary caller payload passthrough.
- NI-5 durable telemetry subscriptions, bounded collection windows, due scheduler, retention, raw samples, normalized scalar points and time-series summaries.
- VM-1 built-in and validated custom vendor/model packs with device binding, resource resolution, strict selector/path validation and immutable spec hash evidence.
- NA-1 desired-state DRAFT/PUBLISHED revisions, target expansion, deterministic model compilation, plan/evaluate/run records, approval-gated apply and reverse-order compensating rollback.
- NA-2 frozen fleet campaigns with canary/waves, stable attempt identity, pause/resume/retry/abort, plan/model drift fail-closed checks and optional wave rollback.
- HA-1 ACTIVE/DRAINING/DRAINED lifecycle, drain-aware automation/scheduler admission, cluster readiness and durable recovery-drill evidence. Automatic PostgreSQL failover is deliberately not claimed.
- CLI/API/RBAC scopes and operational status surfaces were added for automation, telemetry, desired state, campaigns, vendor model packs and HA operations.
- Public write paths no longer accept a caller-declared `approved=true` as authority. Structured change, desired-state apply, campaign wave and structured rollback execution flow through durable request submission, separate approval and execute-time frozen-snapshot verification.
- Source quality gates now enforce executable modes in raw checkouts and extend mypy coverage to the new automation/telemetry/HA core modules. Ruff configuration is unchanged; rule suppression was not used to hide the historical hygiene debt.

Consolidated Release 33 source verification after implementation fixes: automation/repository-hygiene focused **23 passed**; PH-2 **9 passed**; PH-3 **22 passed**; Q-1 **11 passed**; full repository **168 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall, launcher `py_compile`, and packaging shell syntax **PASS**; source text CR offenders **0**, caches **0** after cleanup, symlinks **0**, historical E701-style same-line compound suites **0**, required executable modes **7/7 = 0755**. The final focused run found and fixed NA-2 retry/resume state-machine gaps and PH-3 gNMI/Web regressions before the green result. Ruff and mypy are `NOT_RUN`: the binaries are absent and this isolated environment cannot retrieve them, so no lint/type-check PASS is claimed.

Testing/qualification truth is recorded in `TESTING_RESULT_2026-09-12.md`. Offline success does not promote any phase beyond `IMPLEMENTED_TESTING_DEFERRED`. Session idle/absolute expiry remains deferred by explicit user direction.

Artifact candidate evidence: Clean Release 33 candidate `netconfig_release33_candidate_2026-09-12.zip` (SHA-256 `d03720a411b796458747f7d8976a8fa01f4f40859b5e51341ef031aaa343f538`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; text CR offenders **0**; source/extracted byte identity **132/132 PASS**; payload plus each SHA/release manifest **128/128 PASS**; required executable modes **7/7 = 0755**. From the clean extraction: Release 33 focused **23 passed**, PH-2 **9 passed**, PH-3 **22 passed**, Q-1 **11 passed**, full repository **168 passed / 7 skipped** in the isolated full-suite rerun, legacy selftest **ALL PASS**, and compileall/launcher py_compile/packaging shell syntax **PASS**. A first command that chained all suites hit the execution-tool timeout after full pytest reached ~82%; that interrupted run is not counted as PASS. The same candidate full suite was then rerun alone and completed cleanly (**168 passed / 7 skipped in 22.90s**).

> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.

## 2026-09-12 — Qualification Track Q-1 — Production Runtime & Service-backed Qualification

Status: `IMPLEMENTED_TESTING_DEFERRED`. RPM source Release: `2.0.0-32`. No database schema revision is introduced by Q-1; the core schema revision remains `ph3-1`.

Implemented:

- Reconciled package/project/RPM version truth to application Version `2.0.0` and RPM Release 32.
- Added `postgres_backup.py` with fixed-function `pg_dump`/`pg_restore`, atomic backup replacement, mode-0600 backup/checksum files, SHA-256 verification, configured libpq SSL mode, bounded subprocess deadlines, and no password in argv.
- Restore is deliberately a drill/standby workflow: explicit `RESTORE_DATABASE` confirmation is mandatory and the configured active core DB name is refused as a restore target.
- Added a recovery-safe restore CLI branch that loads settings/credentials without opening the active core database first.
- Added `qualification.py` and `netconfig qualify` configuration-aware runtime preflight.
- Added real PostgreSQL Q-1 integration tests for multi-connection `SKIP LOCKED`, advisory-lock leadership/session-loss release, heartbeat visibility, SQLite import/sequence repair, and pg_dump/pg_restore restore drill.
- Expanded GitHub Actions to install PostgreSQL client tools and execute the real Q-1 PostgreSQL tier.
- Added fail-closed source, PostgreSQL, and AlmaLinux 10 qualification scripts. AlmaLinux installation is mutation-gated by both `--install` and `NETCONFIG_Q1_ALLOW_INSTALL=1`.
- Split RPM build from installed smoke: `build-rpm.sh` no longer assumes the package is already installed. Installed smoke now runs `netconfig qualify` and asserts packaged unit hardening.
- Hardened `netconfig-backup.service` consistently with the Web service and documented the pre-vault `postgres-core-password` systemd credential.

Offline evidence before final artifact packaging: Q-1 focused **11 passed**; full repository **147 passed / 7 skipped**. The seven skips are intentional service-backed gates. Ruff/mypy could not be installed because this isolated execution environment has no package-network resolution; `q1-source-gates.sh` therefore exits 2 and records the tooling gate as `NOT_RUN`. `q1-qualify-postgres.sh` exits 2 because PostgreSQL client tools are unavailable. `q1-qualify-almalinux.sh` exits 20 because the current host is Debian 13 rather than AlmaLinux 10. None are counted as passing.

Artifact evidence: Clean Q-1 candidate `netconfig_qualification_q1_candidate_2026-09-12.zip` (SHA-256 `185039eadf8e8e63a8dad358df35f759a7a1f099d5fa6a3456a50e023920a2b1`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; source/extracted byte identity **125/125 PASS**; payload plus each SHA manifest **121/121 PASS**; required executable modes **7/7 = 0755**; extracted Q-1 focused **11 passed**; extracted full regression **147 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.

Session idle/absolute expiry remains explicitly deferred and unchanged. PH-3 structured-protocol behavior is unchanged by Q-1.

## Current implementation pointer — 2026-09-12

**Historical Release 33 checkpoint:** HA-1 / Release 33 (`IMPLEMENTED_TESTING_DEFERRED`) was the parent implementation baseline before UI-1. Its PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 evidence remains provenance only; the active baseline is Release 34 / UI-1.


## 2026-08-31 — engineering/security/remediation hardening slice

### Implemented

- Added `pyproject.toml` with Python 3.12+ contract, pytest, Ruff, and mypy configuration.
- Added GitHub Actions CI for lint, incremental typing, compileall, pytest, legacy self-test, PostgreSQL, scripted real-OpenSSH integration, and Net-SNMP integration.
- Added focused pytest modules for config remediation modeling, login throttling/security headers, service credentials, SNMP worker concurrency, protocol capabilities, and legacy-regression execution.
- Added `security.py` with process-local bounded login throttling and console security headers.
- Added `observability.py` with structured JSON events and Prometheus text metrics.
- Added `/healthz`, `/readyz`, and `/metrics`; restored HTTP access observability instead of suppressing `log_message`.
- Added failed-login and throttled-login audit events. Successful login/logout now include peer-source audit context.
- Added optional built-in TLS through stdlib `ssl.SSLContext`; CLI accepts `--tls-cert` and `--tls-key`.
- Added service vault bootstrap from systemd credential directory or root-only master file; legacy `NETCONFIG_MASTER` remains fallback compatibility only.
- Replaced service-start recursive root `chown` with systemd `StateDirectory=netconfig`; enabled `MemoryDenyWriteExecute=true` in the packaged web unit.
- Added `configmodel.py` and changed remediation from baseline text replay to fresh-live semantic planning, vendor negation, guarded execution, post-change re-fetch, and semantic verification.
- Remediation now refuses scrubbed baselines and platforms without an implemented automatic rollback guard.
- Added bounded concurrent SNMP polling with metrics.
- Added a thin storage boundary and explicit protocol capability registry for future PostgreSQL-core / NETCONF / RESTCONF / gNMI work.
- Updated remediation approval preview to show the semantic plan from the latest stored current config; execution still re-plans from fresh live state.
- Fixed a duplicate username field in the login page.

### Intentional non-change

Console session expiry was **not** implemented in this slice. The current in-memory session remains valid until logout or process restart. This is explicitly documented as deferred security debt in `SECURITY.md` and `ROADMAP.md` for a later dedicated lifecycle change.

### Validation still required

- Run CI on Python 3.12 with Ruff and mypy installed.
- Run the OpenSSH/Net-SNMP/PostgreSQL integration tier in Linux CI.
- Validate Cisco IOS/ASA and Arista timed-reload interactions on real vendor/lab images.
- Validate JunOS `commit confirmed` behavior and prompt transitions on a real JunOS lab image.
- Validate `MemoryDenyWriteExecute=true` on the exact target distribution/package build.
- Confirm built-in TLS certificate/key permissions and reverse-proxy coexistence in deployment environments.

### Known limitations

- Enforced CSP still permits legacy inline script/style because `web.py` has inline event handlers. Strict nonce CSP is report-only until those are removed.
- The old `selftest.py` remains as a compatibility runner while cases are progressively migrated to pytest.
- The storage abstraction is intentionally thin; the core database is still SQLite/WAL.
- NETCONF/RESTCONF/gNMI are architecture capabilities, not implemented transports yet.

## 2026-09-01 — CI lint and line-ending hygiene follow-up

### Implemented

- Reconciled Ruff with the existing code style so the CI lint gate is actionable: `E702` (multiple statements separated by semicolons) is now an explicit temporary house-style exception instead of an always-failing gate.
- Removed confirmed unused imports and cleaned the identified `F541`, `B904`, and `E741` violations rather than suppressing those rule families.
- Added `.gitattributes` with LF enforcement for Python, shell, systemd units/timers, RPM specs, TOML/YAML, Markdown, and common repository text artifacts.
- Renormalized repository text files to LF. Local verification found zero CRLF/bare-CR UTF-8 text files after normalization.
- Added repository-hygiene pytest coverage and a CI index-EOL check so future CRLF regressions are visible.

### Validation

- `python -m compileall -q opt/netconfig/netconfig tests`: PASS.
- `pytest -q`: PASS (11 passed, 3 integration tests skipped because protocol services are not running locally before this follow-up's new hygiene tests were added; rerun after final packaging records the final count).
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: `RESULT: ALL PASS`.
- Local Ruff execution remains **NOT RUN** because Ruff is not installed in this sandbox and outbound PyPI access is unavailable. The GitHub Actions Ruff step remains the authoritative validation for the exact configured ruleset.

### Deferred security debt unchanged

- Console idle timeout / absolute session expiry remains deliberately deferred. No session-lifetime behavior was changed in this follow-up; see `SECURITY.md` and `ROADMAP.md`.

## 2026-09-02 — topology, event-driven collection, read-only API, scheduled digest slice

### Implemented

- Added `topology.py` with pure LLDP-MIB and CDP-detail parsers, inventory/SNMP-sysName correlation and explicit unmanaged-neighbour classification.
- SNMP network polling now persists LLDP topology; when LLDP returns no neighbours and SSH credentials are available, a read-only `show cdp neighbors detail` fallback is attempted.
- Added a dependency-free `/topology` SVG fleet map and neighbour table plus a manual fleet discovery action.
- Added `syslog_receiver.py`: bounded UDP queue, 8 KiB message cap, source-IP device correlation, common config-change event matching, per-device debounce, immediate archive trigger, persistent recent events and audit evidence. Default listener is non-privileged udp/5514.
- Added `apitokens.py` and additive `api_tokens` schema. Tokens are random bearer credentials, stored only as SHA-256 hashes, have an existing NetConfig role plus explicit read scopes, support CLI create/list/revoke, and are audited on API use.
- Added read-only API endpoints for inventory, topology, drift, latest compliance, latest digest and audit.
- Added `digest.py`: periodic compliance/drift sweep with persisted digest evidence and SMTP/O365 delivery through the existing mailer. Monitoring settings now expose syslog and digest scheduling.
- Added additive topology/syslog/digest database tables and focused pytest coverage.

### Validation

- `PYTHONPATH=opt/netconfig pytest -q`: **19 passed, 3 skipped** (the 3 existing protocol-service integration tests remain environment-gated).
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall`: PASS for changed modules and final tree.

### Deferred / not claimed

- No real-device LLDP/CDP lab run was performed in this environment.
- No production syslog relay/NAT design is claimed; source-IP matching assumes the UDP peer is the managed device. Trusted-relay parsing must be explicit before supporting relayed syslog.
- SNMP traps are not implemented in this slice.
- Session idle/absolute expiry remains deliberately deferred security debt and was not changed.


## 2026-09-07 — new-chat handover and roadmap reconciliation

### Handover preparation

- Added `HANDOVER_2026-09-07.md` as the concise current-state entry point.
- Added `TESTING_RESULT_2026-09-07.md` with exact executed/deferred gate evidence.
- Added `HANDOVER_PROMPT.md` for direct reuse in a new chat.
- Extended `ROADMAP.md` with a prioritized next-slice sequence led by qualification/release closure,
  VLAN-aware IP/MAC/VLAN/port correlation, and SNMP trap/event correlation.
- Reconciled contradictory Git instructions: the user manages Git manually unless explicitly authorizing
  Git operations in the current chat.
- Reconciled stale packaging examples to the current spec Release 17 and made the build script artifact
  listing release-agnostic. No RPM was built.

### Verification

- `PYTHONPATH=opt/netconfig pytest -q`: **19 passed, 3 skipped**.
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall -q opt/netconfig/netconfig tests`: **PASS**.
- LF hygiene scan: **0 CR-containing repository text files**.
- Ruff/mypy, GitHub Actions, service-backed integration, AlmaLinux RPM and live-device gates were not run
  in this handover environment and remain explicitly deferred.

### Runtime behavior

No application runtime feature was intentionally changed. Console session idle/absolute expiry remains
unchanged and deliberately deferred.


## 2026-09-10 — Slice D.5 Diagnostic & Support Bundle Framework

Implemented the first diagnostic/support framework foundation. Added `debug.py` with redacted bundle generation, manifest generation, SHA-256 file inventory, and secret-pattern redaction. Added `netconfig debug collect` CLI command. No plaintext credentials, tokens, vault material, or private keys are exported.

Deferred: full device debug capture, REST debug bundle API, UI diagnostics page, and production incident workflow.


## 2026-09-10 — Slice D.5 Phase 2 Diagnostic Support Bundle completion update
- Added device diagnostic capture foundation (`netconfig debug device <name>`).
- Diagnostic exports remain secret-redacted and manifest/checksum validated.
- Current slice remains IMPLEMENTED_TESTING_DEFERRED until REST API, Web UI diagnostics, retention policy, and full device protocol traces are completed.


## Slice D.5 Phase 3 update (2026-09-10)
Implemented diagnostic bundle retention foundation: bundles are stored under the NetConfig state directory, can be listed and cleaned up from CLI, and continue using redaction and manifest integrity. REST API, Web UI diagnostics, trace capture, and signed bundle workflow remain deferred.


## Slice D.5 Phase 3B — Diagnostic API Foundation (2026-09-10)
- Added read-only debug bundle API foundation.
- Added debug:create and debug:read API token scopes.
- Bundle creation remains secret-redacted and audited.
- Status: IMPLEMENTED_TESTING_DEFERRED.
- Deferred: Diagnostics UI, download workflow, incident correlation, protocol trace capture.


## D.5 Phase 3D — Enterprise Diagnostic Operations

Status: IMPLEMENTED_TESTING_DEFERRED

Added secure debug bundle download API foundation, debug:download scope, RBAC/audit integration. Deferred: incident workflow, signed manifests, retention scheduler UI.


## 2026-09-11 — Slice D.5 Phase 4A: Incident Model Foundation

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added `opt/netconfig/netconfig/incidents.py` as the incident lifecycle service.
- Added additive SQLite `incidents` and `incident_bundles` tables plus status/severity indexes. Existing databases create the new tables in-place without rewriting prior device/history data.
- Incident IDs are generated after insert as `INC-<UTC year>-<six-digit row id>`; the database numeric ID remains internal and both forms can be used for lookup.
- Added bounded input validation for titles, descriptions and tags; fixed severity/status vocabularies; explicit lifecycle transitions; closure/reopen metadata; and append-only audit events for create/update/status/bundle link/unlink operations.
- Added `netconfig incident create|list|show|update|status|link-bundle|unlink-bundle`.
- Added `incident:read` and `incident:write` bearer scopes. `incident:write` cannot be issued to a viewer token and the HTTP API independently re-checks operator-or-higher role at request time.
- Added JSON request-body support to the existing API POST reader while preserving URL-encoded Web-console forms.
- Added `/api/v1/incidents`, `/api/v1/incidents/{id}`, `/api/v1/incidents/{id}/status`, and `/api/v1/incidents/{id}/bundles` foundation endpoints.
- Diagnostic bundle links accept only a basename ending in `.tar.gz` and, in the production Manager path, require the bundle to exist under the managed `debug-bundles` directory.
- Baseline repair: Phase 3D's Web/API download handler already required `debug:download`, but the token registry did not allow that scope. Added `debug:download` and `debug:admin` to `VALID_SCOPES` and centralized managed bundle lookup in `DebugBundle.get_bundle()`.

### Deliberately deferred

- Unified incident timeline/event references (Phase 4B).
- Support-case export (Phase 4C).
- Evidence signing/trust model (Phase 4D).
- Protocol trace capture (Phase 4E).
- Incident Web Console (Phase 4F).
- Console session idle/absolute expiry remains known security debt and was not changed.
- Real CI service tier, real network devices, AlmaLinux RPM build/install and live HTTP/TLS qualification were not run in this environment.

### Repository validation

- Phase 4A focused incident tests: **8 passed**.
- Final full pytest for Phase 4A: **28 passed, 3 skipped**; the three skips are the pre-existing service-backed OpenSSH/Net-SNMP/PostgreSQL integration tests.
- Python runtime used: 3.13.5 under the declared `>=3.12,<3.14` contract.


## 2026-09-11 — Slice D.5 Phase 4B: Incident Timeline

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added additive SQLite `incident_evidence_links` with a unique incident/source reference, linker identity/timestamp, and bounded operator note. Authoritative event/config/report content is intentionally not copied into this table.
- `Incidents.link_evidence()` validates existing audit, syslog, configuration collection (`runs`), and compliance-run IDs before linking. Duplicate links are idempotent.
- `Incidents.link_drift()` captures a reference to the device's then-current baseline and latest immutable archived configuration stamps; timeline resolution compares those exact files, not the later mutable `current.cfg`.
- `Incidents.timeline()` produces one ordered view containing incident creation, incident-native audit activity, current diagnostic-bundle associations, and explicitly linked evidence. Missing/pruned source rows remain as `available=false` timeline markers.
- Added CLI `incident link-evidence`, `link-drift`, `unlink-evidence`, `evidence`, and `timeline`.
- Added API `GET /api/v1/incidents/{id}/timeline`, `GET /api/v1/incidents/{id}/evidence`, `POST /api/v1/incidents/{id}/evidence`, and constrained evidence unlink. Existing `incident:read` and role-gated `incident:write` scopes are reused; no new broad token privilege was introduced.
- API and CLI do not expose a generic SQL/table selector: evidence types are allow-listed and each resolver uses fixed queries.
- RPM source spec Release advanced to 19 for this changed source baseline; no RPM build/install is claimed.

### Design decisions

- Evidence links are references, not evidence copies. This preserves one authoritative source of truth and prevents timeline data from diverging from audit/syslog/compliance/config archives.
- Drift is the exception that needs a composite pointer: the link stores only device/baseline-stamp/current-stamp identifiers. The referenced configuration snapshots remain authoritative.
- Incident-native audit rows are included automatically because their `target` is the incident key. External audit rows require an explicit evidence link.
- Bundle history remains governed by `incident_bundles` plus append-only audit; Phase 4B does not create a competing bundle-evidence table.

### Deliberately deferred

- Phase 4C support-case export.
- Phase 4D evidence signing/trust model.
- Phase 4E protocol trace capture.
- Phase 4F Incident Web Console.
- Automatic event-to-incident correlation rules; Phase 4B establishes the reference/timeline substrate only.
- Console session idle/absolute expiry remains known security debt and is unchanged.
- Ruff/mypy, service-backed integration, AlmaLinux RPM and live-device qualification remain environment-deferred.

### Repository validation

- Phase 4B focused incident tests: **14 passed**.
- Full pytest: **33 passed, 3 skipped**.
- Legacy selftest: **RESULT: ALL PASS**.
- `python -m compileall`: **PASS**.
- Ruff/mypy: **NOT RUN** (not installed in the execution environment).


### Phase 4B artifact delivery gate

The FULL source candidate was also validated after clean ZIP extraction: no traversal/symlink entries, complete source-to-extracted SHA identity, all per-file manifests valid, critical-file/header checks valid, extracted compileall PASS, extracted pytest **33 passed / 3 skipped**, extracted selftest **ALL PASS**, and CR offenders 0. Source-only tests do not substitute for this artifact-level check.


## 2026-09-11 — Roadmap execution-structure reconciliation

- Documentation-only change; runtime source, database schema and API behavior are unchanged.
- Replaced the historical Slice A-G primary execution ordering with canonical **Current / Next / Diagnostics Track / Network Intelligence Track / Platform Hardening Track** planning.
- At that documentation-only refresh, current was **D.5 Phase 4B — Incident Timeline** and next was **D.5 Phase 4C — Support Case Export**; the later Phase 4C section supersedes that planning snapshot.
- Preserved Slice A-G as historical 2026-09-07 handover mapping so older patch/handover records remain interpretable without controlling future sequencing.
- Synchronized `ROADMAP.md`, `AI_HANDOFF.md`, `HANDOVER_PROMPT.md`, `DEV_BASELINE.md`, and `HANDOVER_2026-09-07.md`.
- No session-lifetime behavior changed.


## 2026-09-11 — Slice D.5 Phase 4C: Support Case Export

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added `caseexport.py` with managed `case-exports/` storage and bounded archive construction.
- Added additive SQLite `incident_case_exports` records containing export identity, Incident FK, creator/time, bounded reason, included/missing diagnostic bundle indexes, archive size and SHA-256.
- Case archives contain explicit Incident metadata, reference-only evidence/timeline indexes, selected linked diagnostic bundles copied byte-for-byte, a human-readable README, file manifest and `manifest.sha256`.
- No authoritative syslog body, external audit detail, compliance report body, or configuration text is copied into the case indexes. Phase 4B source pointers remain the provenance boundary.
- Added fail-closed bundle selection: traversal/unlinked/missing explicitly requested bundles are rejected. With default all-linked export, previously pruned bundle files remain visible as missing metadata instead of silently disappearing or being recreated.
- Added 32-bundle / 512 MiB aggregate diagnostic-bundle bounds.
- Added common credential-assignment redaction for Incident title/description/tags, link notes and export reason before case JSON emission.
- Added dedicated role-gated `incident:export` token scope. Viewer tokens cannot be issued this scope.
- Added CLI `incident export-case` and `incident exports`.
- Added REST `POST /api/v1/incidents/{id}/exports`, `GET /api/v1/incidents/{id}/exports`, and guarded `GET /api/v1/incidents/{id}/exports/{export_key}` download.
- Export creation and download append Incident-targeted audit events. Download revalidates durable archive size/SHA-256 and fails closed/audits an integrity mismatch.
- Added streaming file response for case/debug downloads so large bounded archives are not read entirely into process memory.
- RPM source spec Release advanced to 20 for this changed source baseline; no RPM build/install is claimed.

### Deliberately deferred

- Cryptographic evidence/manifest signing and signer trust model (Phase 4D).
- Secret-safe protocol trace capture (Phase 4E).
- Incident Web Console (Phase 4F).
- Automatic correlation rules and closeout retention/scheduler policy remain later work.
- Console session idle/absolute expiry remains known security debt and was not changed.
- Ruff/mypy, service-backed protocol integration, AlmaLinux RPM installation and live-device qualification remain environment-dependent/deferred unless explicitly executed below.

### Repository validation

- Full pytest after Phase 4C implementation: **39 passed, 3 skipped**.
- Focused incident/case suite: **19 passed**.
- Legacy selftest: **RESULT: ALL PASS**.
- Application/tests compileall: **PASS**.

### Phase 4C artifact delivery gate

The FULL source candidate passed clean-extraction artifact verification: 94/94 source/extracted files matched by SHA-256; 90/90 release/per-file manifest payload entries verified; CRC/path traversal/symlink/CR checks passed; extracted pytest **39 passed / 3 skipped**; focused incident/case suite **21 passed**; extracted selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**.


## 2026-09-11 — Slice D.5 Phase 4D: Evidence / Manifest Signing

Implemented an external-key Ed25519 evidence-signing boundary without adding a Python cryptography dependency. `evidence_signing.py` invokes the system OpenSSL executable using fixed arguments only; arbitrary signer commands/shell strings are not supported. Private keys resolve from systemd credentials first and a protected explicit file second, must be regular non-symlink files with restrictive permissions, and are never stored in NetConfig state or evidence archives.

Both diagnostic bundles and Phase 4C support-case exports now auto-sign when a valid signer is configured. Per-operation/global signing-required policy fails closed if signing cannot be performed. Signed archives carry `manifest.signature.json` and `manifest.public.pem`; verification never extracts the archive, validates archive structure, rejects link/device entries and unmanifested regular files, recomputes every payload size/SHA-256, validates `manifest.sha256`, verifies Ed25519, and reports independent trust-pin state.

Support-case export metadata now has additive `signature_state`, `signature_algorithm`, and `signer_fingerprint` columns. Existing databases migrate additively and prior unsigned records remain valid. Case download still validates durable outer archive size/SHA-256, then verifies signed inner evidence and durable signer fingerprint; configured trust pins are enforced.

CLI/API verification and signer-readiness surfaces were added. Key rotation is supported by allowing multiple independent trusted fingerprints. HSM/KMS-backed signers, protocol traces, and Incident Web Console remain deferred. Session expiry remains unchanged/deferred.

Executed repository regression after implementation: **49 passed, 3 skipped**; Phase 4D focused signing tests: **10 passed**; legacy selftest: **ALL PASS**; compileall/launcher pycompile/packaging shell syntax: **PASS**; CR offenders: **0**. Ruff/mypy remain NOT RUN in this environment.


### Phase 4D artifact delivery gate

A clean candidate FULL source ZIP was independently extracted and validated before final repackaging: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **96/96 PASS**; `RELEASE_MANIFEST.json` payload **92/92 PASS**; all three per-file SHA manifests **92/92 PASS**; required source/test/packaging/documentation files **PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **49 passed / 3 skipped**; extracted Phase 4D signing suite **10 passed**; extracted legacy selftest **ALL PASS**; UTF-8 CR offenders **0**.


## 2026-09-11 — Slice D.5 Phase 4E: Protocol Trace Capture

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added `protocoltrace.py` and additive `protocol_trace_sessions` / `protocol_trace_events` schema.
- Added explicit bounded trace lifecycle (`PTR-...`): ACTIVE, STOPPED, EXPIRED and LIMIT_REACHED; TTL 30..3600s, max 5000 events, max 8 MiB serialized metadata per session.
- Added CLI/OpenSSH metadata capture through an optional transport callback. `execute()` records command summary/status/duration/byte counts but never raw device output. Sensitive command text is replaced by a fixed redaction marker and is not hashed from original secret-bearing content.
- Added context-local SNMP UDP-exchange capture using `ContextVar`; stores target/port/attempt/status/duration/byte counts without BER payload, community or v3 secrets. SNMP poll, walk and LLDP discovery enter that context when an active trace exists.
- Added `protocol_trace` Incident evidence resolution/linkage. Starting a trace with `--incident` links the durable trace automatically.
- Added `protocol-traces.json` to support-case exports and bounded recent trace metadata to general/device diagnostic bundles.
- Added `trace:read` plus role-gated `trace:capture`, CLI trace lifecycle and REST trace lifecycle.
- Added future-ready protocol identifiers for NETCONF/RESTCONF while failing trace start closed until those transport providers are actually implemented.
- RPM source Release advanced to 22 for this changed source baseline; no RPM build/install is claimed.

### Verification

- Full pytest: **59 passed, 3 skipped**.
- Phase 4E focused tests: **10 passed**.
- Legacy selftest: **RESULT: ALL PASS**.
- compileall, launcher py_compile and packaging shell syntax: **PASS**.
- Ruff/mypy: **NOT RUN** (not installed in this environment).

### Deferred

- Phase 4F Incident Web Console.
- NETCONF/RESTCONF actual protocol providers and their trace hooks.
- Raw packet capture is intentionally not planned as part of this safe trace subsystem.
- Service-backed integration, live-device qualification and RPM install remain deferred.
- Console session idle/absolute expiry remains separate known security debt.


### Phase 4E artifact delivery gate

The clean FULL source candidate was independently extracted and validated: ZIP CRC **PASS**; path traversal **0**; symlink entries **0**; source/extracted file set and SHA-256 identity **98/98 PASS**; `RELEASE_MANIFEST.json` payload **94/94 PASS**; all three per-file SHA manifests **94/94 PASS**; extracted compileall/launcher pycompile/packaging shell syntax **PASS**; extracted pytest **59 passed / 3 skipped**; extracted Phase 4E protocol-trace suite **10 passed**; extracted legacy selftest **ALL PASS**.


## 2026-09-11 — Slice D.5 Phase 4F: Incident Web Console

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added an authenticated `Incidents` console navigation entry, register/filter page, and Incident detail page without introducing a second data model.
- Viewer is read-only; operator/approver/admin can create/update Incidents, request only valid lifecycle transitions, manage existing evidence/bundle links, start/stop bounded CLI/SNMP traces, and create/verify/download support-case exports.
- Unified the Phase 4B timeline, evidence links, Phase 4E trace sessions/events, linked diagnostic bundles, and Phase 4C/4D export/signature state on the Incident detail workflow.
- Preserved CSRF for every browser mutation. Support-case download uses the existing verified chunked-streaming path.
- Added HTML-escaping regression coverage for Incident-controlled fields and fail-closed cross-Incident trace-stop coverage.
- Added `tests/test_incident_web.py`. No schema migration was required.
- RPM source Release advanced to 23 for this changed source baseline; no RPM build/install is claimed.

### Verification

- Full pytest: **64 passed, 3 skipped**.
- Phase 4F focused tests: **5 passed**.
- Legacy selftest: **RESULT: ALL PASS**.
- compileall, launcher py_compile and packaging shell syntax: **PASS**.
- Ruff/mypy: **NOT RUN** in this environment.

### Deferred

- D.5 closeout/qualification, including remaining scheduled retention/cleanup policy.
- Service-backed protocol integration, live-device and RPM qualification.
- Console idle/absolute session expiry remains separate known security debt.

### Phase 4F artifact delivery gate

A clean candidate FULL source package was extracted and independently verified before final repackaging: source/extracted identity **99/99 PASS**, manifest payload **95/95 PASS**, ZIP CRC **PASS**, no path traversal/symlinks/CR offenders, extracted pytest **64 passed / 3 skipped**, focused Phase 4F Web tests **5 passed**, legacy selftest **ALL PASS**, and compileall/launcher/package-shell syntax **PASS**.


## 2026-09-11 — D.5 Closeout / Diagnostic Qualification Review

Added opt-in bounded diagnostic retention maintenance without changing default deployment behavior. `diagnostic_maintenance_interval=0` keeps the scheduler disabled unless an operator enables it. `debug_bundle_keep` limits support-bundle count, `case_export_retention_days` removes old case archive files while retaining durable export metadata, and `protocol_trace_retention_days` removes only inactive traces that are not linked to an Incident. `netconfig debug maintenance` provides an audited one-shot execution path. Monitoring settings expose the same policy.

Closeout regression: **67 passed / 3 skipped**; focused closeout tests **3 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell checks **PASS**; CR offenders **0**. Ruff/mypy, OpenSSH/Net-SNMP/PostgreSQL service-backed integration, AlmaLinux RPM build/install and representative live-device qualification were unavailable and remain explicitly deferred. D.5 therefore remains **IMPLEMENTED_TESTING_DEFERRED** even though its planned feature phases are complete. RPM source metadata advanced to `2.0.0-24`; no RPM build/install is claimed.


### D.5 closeout candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; source/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## 2026-09-11 — Post-closeout roadmap naming reconciliation

Documentation-only clarification; no runtime/API/schema/package-spec behavior changed. Canonical planning now states explicitly that **D.5 is the standalone Diagnostics Track and is not historical Slice E**. The post-D.5 NEXT item, **Network Intelligence Track -> VLAN-aware endpoint and topology correlation**, maps historically to **Slice B**. Historical **Slice E** remains the separate **Platform Hardening -> Web-console structural hardening** backlog item. Stale handoff/baseline metadata that still showed Phase 4F as current or D.5 Closeout as next was updated to the completed closeout state. Current source RPM spec remains `2.0.0-24`; no RPM build/install qualification is claimed.

### Roadmap-refresh candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; stage/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; each of the three SHA manifests **97/97 PASS**; required files **PASS**; UTF-8 CR offenders **0**; extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.

## 2026-09-11 — Source baseline packaging repair

Repaired the post-closeout roadmap-refresh delivery artifact without changing runtime/API/schema behavior. The source-delivery ZIP now preserves executable mode `0755` for `usr/bin/netconfig`, `packaging/build-rpm.sh`, `packaging/inspect-rpm.sh`, and `packaging/smoke-installed.sh`. Active RPM build/install documentation was reconciled from stale `2.0.0-17` examples to the current source Release `2.0.0-24`; historical changelog/patch provenance remains unchanged. Re-run full regression and extracted-artifact mode/documentation checks before publishing the repaired FULL source baseline.

### Repaired source-baseline candidate artifact gate

Clean candidate extraction verified: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; stage/extracted file identity **101/101 PASS**; `RELEASE_MANIFEST.json` payload **97/97 PASS**; all three SHA manifests **97/97 PASS**; required files **PASS**; UTF-8 CR offenders **0**. ZIP central-directory and extracted filesystem modes are **0755 PASS** for `usr/bin/netconfig`, `packaging/build-rpm.sh`, `packaging/inspect-rpm.sh`, and `packaging/smoke-installed.sh`. Direct `./packaging/build-rpm.sh` execution reaches the script and exits **2** only because `rpmbuild` is unavailable, not **126 Permission denied**. Active build/install docs reference **2.0.0-24**. Extracted pytest **67 passed / 3 skipped**; extracted closeout-focused tests **3 passed**; extracted legacy selftest **ALL PASS**; extracted compileall/launcher/package-shell syntax **PASS**.


## 2026-09-11 — Network Intelligence Phase NI-1: VLAN-aware Endpoint Attachment Correlation

Status: **IMPLEMENTED_TESTING_DEFERRED**

### Delivered

- Added modern IP-MIB `ipNetToPhysicalTable` collection for IPv4/IPv6 with explicit legacy IPv4 fallback provenance.
- Added Q-BRIDGE-MIB VLAN-aware FDB collection, bridge-port -> ifIndex mapping and unique FDB-ID -> VLAN resolution. Shared FDB/VLAN mappings remain unresolved rather than guessed.
- Added additive `ip_neighbors` and `vlan_fdb` tables and compatibility projection into existing ARP/MAC device views.
- Added `network_intelligence.py` correlation with freshness budget, LLDP/CDP transit suppression, explicit ambiguity and confidence.
- Added `endpoint:read`, `/api/v1/endpoints`, `netconfig endpoints [--refresh] [--json]`, authenticated Endpoints Web UI, endpoint metrics and SNMP Settings freshness control.
- Added canned-walk and correlation tests in `tests/test_network_intelligence.py`.
- RPM source Release advanced to `2.0.0-25`; no RPM build/install is claimed.

### Verification before final artifact packaging

- Full pytest: **75 passed / 3 skipped**.
- NI-1 focused tests: **8 passed**.
- D.5 regression remains green.
- Final selftest/compile/package and extracted-artifact results are recorded in `TESTING.md` after packaging.

### Deferred

- NI-2 chassis/system identity normalization and complete downstream impact traversal.
- Representative vendor Q-BRIDGE/IP-MIB qualification and service-backed Net-SNMP integration.
- Existing Ruff/mypy/RPM/live-device qualification debt remains unchanged.

NI-1 source-workspace release checks: full pytest **75 passed / 3 skipped**, focused NI-1 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**, executable launcher/helper modes **0755**.

### NI-1 artifact delivery gate

Candidate FULL source artifact independently passed 103/103 source-to-extracted identity, 99/99 release payload and all SHA manifests, executable-mode preservation, archive-security checks and extracted regression (75 passed / 3 skipped; NI-1 8 passed; selftest ALL PASS). Final FULL baseline is rebuilt after recording this evidence and must pass the same gate again.


## 2026-09-11 — NI-1 all-Markdown canonical-state synchronization

Documentation-only reconciliation across all 19 Markdown files. Runtime source, database schema, API behavior and RPM spec are unchanged. Active state is uniformly **CURRENT = NI-1**, **NEXT = NI-2**; D.5 and the 2026-09-07 A-G ordering are retained only as explicit historical/provenance context. Active source RPM Release remains `2.0.0-25`.

Validation: Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**.

Delivery artifact to publish after artifact gate: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`.

## 2026-09-11 — Network Intelligence NI-2: Topology Identity & Downstream Impact

Status: **IMPLEMENTED_TESTING_DEFERRED**.

NI-2 adds normalized managed-device topology identity from bounded LLDP local-system objects, ENTITY-MIB chassis rows, and the existing IF-MIB interface poll. `topology_device_identity` stores sysName, chassis ID/subtype, normalized chassis MAC, chassis serial/name/model and LLDP capability evidence. `topology_interface_identity` stores ifIndex, ifName, ifDescr, ifAlias and interface physical address without treating LLDP localPortNum as ifIndex.

Managed-neighbour resolution is fail-closed. Inventory name/host, SNMP sysName, chassis ID/MAC and chassis serial are normalized as identity tokens. A token can resolve an observation only when it uniquely identifies one inventory device; conflicting tokens or non-unique tokens make the edge `AMBIGUOUS`, and ambiguous edges are never traversed for impact analysis. No fuzzy hostname or topology guessing is used.

Downstream impact is a bounded, cycle-safe traversal of **observed resolved managed L2 adjacency only**. It can be scoped to a root device and optional first-hop local port. It is explicitly not a routing, STP, application, or power dependency claim. CLI adds `netconfig topology --identities` and `netconfig topology --impact DEVICE`; REST adds `/api/v1/topology/identities` and `/api/v1/topology/impact/{device}` under `topology:read`; the Topology Web page now shows normalized identity, resolution evidence, ambiguity counts and downstream-impact analysis.

Executed source-workspace evidence: full pytest **83 passed / 3 skipped**; NI-2 focused **8 passed**. Live representative-vendor LLDP/ENTITY-MIB/IF-MIB semantics, service-backed integrations, RPM build/install and Ruff/mypy remain deferred/not run in this environment.

### NI-2 artifact delivery gate

Candidate artifact clean-extraction qualification passed: 104/104 complete file identity, 100/100 release payload and SHA manifests, exact hidden-file paths, 0755 launcher/helper preservation, archive-security/hygiene checks, and extracted regression **83 passed / 3 skipped** with NI-2 focused **8 passed** and selftest **ALL PASS**. Final FULL package is rebuilt after this evidence is recorded.

NI-2 prefinal clean-extraction gate reproduced the candidate package evidence after documentation synchronization: 100/100 release payload validation, 0755 executable modes, pytest 83/3, focused NI-2 8/8 and selftest ALL PASS. The final FULL source ZIP is rebuilt from this state.

## 2026-09-11 — Network Intelligence NI-3: SNMP Traps & Dependency-aware Events

Implemented `operational_events.py` and `snmp_trap.py`; additive `operational_events` / `operational_suppressions` persistence; v1/v2c trap normalization; v3/INFORM fail-closed boundaries; syslog and SNMP reachability normalization; dedup, bounded targeted re-poll and NI-2 dependency suppression; CLI/API/Web read surfaces; settings and `events:read`. Source-workspace evidence is **91 passed / 3 skipped**, focused NI-3 **8 passed**, selftest/compile/shell PASS.

NI-3 candidate packaging integrity gate passed with 107/107 full-file identity, 103/103 payload manifests, preserved hidden paths and 0755 modes, and clean-extraction regression **91 passed / 3 skipped** plus focused **8 passed**. Final artifact is rebuilt after this ledger update so the delivered manifests cover the synchronized documentation.


## 2026-09-11 — Network Intelligence NI-4: Operational Alert & Reporting Lifecycle

Implemented `operational_alerts.py` plus additive `operational_alerts`, `maintenance_windows`, `notification_deliveries`, `report_schedules`, and `report_runs` persistence. NI-3 events at/above the configurable severity floor promote to operational alerts only when they are not topology-suppressed and not inside a matching maintenance window. Deduplicated NI-3 events touch the same alert. Added audited acknowledge/resolve lifecycle, bounded durable SMTP retry/backoff, scheduled aggregate operational reports, CLI/API/Web surfaces, role-gated write scopes, and opt-in lifecycle scheduler settings. Existing monitor-rule alerts remain separate. Source-workspace evidence: **99 passed / 3 skipped**, focused NI-4 **8 passed**, selftest/compile/shell PASS.


### NI-4 candidate artifact evidence

Candidate `netconfig_network_intelligence_ni4_candidate_2026-09-11.zip` SHA-256 `17ed1297a863eaca2eeb4a92f5bddcf3ab120804d2526c63339bda79ae1569e3` passed clean system-unzip validation: **109/109** artifact files present, **105/105** Release payload entries and each of the three SHA manifests verified, exact hidden paths retained, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the NI-4/PH-1/Release-28 current-state pointer. Extracted regression: **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## 2026-09-11 — Platform Hardening PH-1 — Web-console Structural Hardening

Implemented structural/security decomposition without changing product routes or API semantics. `web.py` moved Bearer API routing into `web_api.py` and UI assets/helpers into `web_ui.py`; current dispatcher size is below 4,000 lines and 240 KB. Enforced CSP now requires per-response nonces for script/style elements and denies script/style attributes; server-rendered style attributes are converted to deterministic classes in one nonce-authorized style block. HTML event-handler attributes were removed in favor of delegated events. Dynamic graph device names are escaped before script context, and vault-secret names are rendered through `textContent`. Source regression: **105 passed / 3 skipped**; focused PH-1: **6 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**. Session idle/absolute expiry remains deliberately deferred.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## 2026-09-11 — Platform Hardening PH-2 — PostgreSQL Core & Distributed Operation

Status: `IMPLEMENTED_TESTING_DEFERRED`.

Implemented:

- Added explicit `core_db_backend=sqlite|postgres`; SQLite remains the default single-node development backend.
- Added `postgres_core.py`, which bootstraps the full NetConfig core schema on PostgreSQL, translates the existing qmark SQL surface to psycopg placeholders, and provides compatibility for the bounded SQLite `INSERT OR IGNORE/REPLACE` forms used by current code.
- PostgreSQL schema generation converts SQLite `AUTOINCREMENT`, `REAL`, and `BLOB` types to PostgreSQL-compatible `BIGSERIAL`, `DOUBLE PRECISION`, and `BYTEA` equivalents.
- Added schema-revision evidence in `storage_meta` (`ph2-1`) and storage-aware `/readyz` reporting.
- Added protected pre-vault core PostgreSQL credential resolution: `NETCONFIG_DB_PASSWORD_FILE`, systemd `$CREDENTIALS_DIRECTORY/postgres-core-password`, then legacy `NETCONFIG_DB_PASSWORD`. Core DB passwords are never written to `settings.json`.
- Added cluster-node registration/heartbeat and session-scoped PostgreSQL advisory locks for singleton background schedulers.
- Added durable `distributed_tasks` and PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` claiming. SQLite retains process-local single-node claim semantics and is not advertised as distributed-capable.
- Added `netconfig storage status|tasks|enqueue|claim|finish|migrate-sqlite` operator tooling.
- Added fail-closed SQLite→PostgreSQL migration: target application tables must be empty by default; IDs are preserved and PostgreSQL sequences repaired after import.
- Existing interface-history PostgreSQL support remains separate and compatible; the same host/database settings may be reused, but its vault-held password is not used for core startup.
- Updated Web Database settings, systemd credential guidance, readiness, and startup write diagnostics.

Validation completed locally:

- PH-2 focused: 9 passed.
- Full repository: 114 passed / 3 skipped.
- Existing PH-1/NI/D.5 regressions remain green.

Deferred / not claimed:

- Live PostgreSQL server schema bootstrap and data migration.
- Multi-node PostgreSQL contention, HA/failover, advisory-lock failover, and real SKIP LOCKED worker races.
- PostgreSQL backup/restore/point-in-time recovery qualification.
- AlmaLinux packaged psycopg installation and RPM/systemd PostgreSQL deployment.
- Production connection pooling and measured distributed scale.

### PH-2 candidate artifact gate

Candidate `netconfig_platform_hardening_ph2_candidate_2026-09-11.zip` SHA-256 `6dfd6e554b08883c51a6f268bbe604bf95cc7819dad8f4bda6f023d688807d21` passed clean system-unzip validation: **114/114** source-file byte identity, **110/110** `RELEASE_MANIFEST.json` payload and each of the three SHA manifests, exact hidden paths, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the PH-2/PH-3/Release-30 current-state pointer. Extracted regression: **114 passed / 3 skipped**, focused PH-2 **9 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.


## 2026-09-12 — Platform Hardening PH-3 — Structured Southbound Adapters

Status: `IMPLEMENTED_TESTING_DEFERRED`. Historical mapping: Slice G.

### Implemented

- Preserved durable per-device `protocol_profiles`, runtime vault credential resolution, explicit opt-in CLI fallback, profile rename/delete integration, metadata-only structured protocol traces, and `protocol:read` / role-gated `protocol:write` surfaces.
- NETCONF now performs SSH-subsystem server hello/capability negotiation, requires base:1.0 framing support, records candidate/writable-running/startup/confirmed-commit/rollback-on-error/validate/xpath capabilities, exposes fixed bounded `<get>` and `<get-config>` reads, fails closed when a requested datastore is not advertised, and enforces XML byte/node/depth limits with DTD/entity rejection. No caller-supplied RPC XML is exposed.
- RESTCONF now performs HTTPS root discovery with optional host-meta discovery, validates hosts and confines paths/queries to allow-listed RESTCONF resources, validates response content types and bounded JSON/XML payloads, supports CA bundles and vault-resolved mTLS material, and refuses disabled certificate verification unless the lab-only `NETCONFIG_ALLOW_INSECURE_STRUCTURED_TLS=1` override is explicitly set.
- Added an internal approval-gated RESTCONF JSON subtree replacement primitive. It requires a named actor, an approved-change signal and a callable post-read verifier; it performs pre-read, conditional replace where ETag is available, post-read verification, and best-effort pre-image rollback on failure. This primitive is intentionally not exposed as generic Web/API/CLI URL/method/body passthrough.
- gNMI now supports Capabilities, Get and bounded ONCE Subscribe through an allow-resolved absolute `gnmic` binary. Paths use a typed validator/renderer, deadlines and response-size limits are enforced, TLS verification is fail-closed by default, CA/mTLS material is resolved at runtime, secrets are written only to a mode-0600 ephemeral config file and never placed in argv, and error output is secret-redacted. gNMI Set remains deliberately unexposed.
- Added manager/CLI read surfaces for structured capabilities, operational state and gNMI ONCE Subscribe, plus bearer API read endpoints for protocol capabilities/state. Existing Web profile/collect RBAC and CSRF behavior remains unchanged.
- Added hard byte limits to subsystem reads in `SSHTransport` while preserving existing CLI behavior.
- Added missing canonical `README.md`.

### Security and compatibility decisions

- No generic NETCONF RPC, arbitrary RESTCONF URL/method/body forwarding, arbitrary protobuf request, shell tunnelling, or gNMI Set.
- Production RESTCONF/gNMI certificate verification is mandatory by default. The only insecure TLS path is an explicit environment-gated lab override.
- Structured network writes remain subordinate to existing change/approval safety. The only new write primitive is internal and explicitly approval-gated; existing public API/CLI does not expose generic structured mutation.
- Protocol traces remain metadata-only and exclude payload/body/RPC/protobuf/authorization/user/password fields.
- Session idle timeout / absolute expiry remains deliberately deferred and was not changed.
- NETCONF base:1.1-only chunk framing, full NETCONF edit/commit transaction execution, and gNMI Set are not claimed.

### Offline verification before final artifact packaging

- Focused PH-3: **21 passed**.
- Full repository: **136 passed / 3 skipped**.
- The three skips remain the service-backed OpenSSH, Net-SNMP and PostgreSQL integration tests.

Final packaging/selftest/compile/shell/manifest evidence is recorded in `TESTING_RESULT_2026-09-12.md` after the final artifact gate.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

### Deferred/live gates

- real NETCONF server/device and base:1.1-only peers
- real RESTCONF device and vendor YANG/path behavior
- real gNMI endpoint and packaged `gnmic` interoperability
- Cisco/Juniper/Arista/Huawei structured-protocol behavior
- TLS/mTLS certificate interoperability and production credential rotation
- real PostgreSQL service/multi-node/HA/failover/PITR/backup-restore
- service-backed OpenSSH and Net-SNMP
- AlmaLinux RPM build/install and systemd qualification
- Ruff, mypy, scale/concurrency/failure testing, SMTP/O365

### Continuation

No next implementation phase is assigned. Perform the roadmap / qualification review required by the handover before naming another implementation phase.


# Historical Architecture Planning Snapshot — PH vs NI

> The status values in this retained planning snapshot describe an earlier roadmap point. They are **not current work assignments**. PH-5/PH-6 and NI phases were subsequently implemented as recorded in later release sections; current status and sequencing are controlled by `ROADMAP.md`, where no new development phase is presently assigned.

## PH — Platform Hardening / Safe Device Change

PH answers:

> How do we safely change network devices?

### PH-4 — Structured Configuration Transaction Engine

Status: `IMPLEMENTED_IN_SOURCE / COMPLETION_HARDENING`

Scope:

- Structured change lifecycle
- Approval binding
- Pre-read snapshot
- Typed NETCONF / RESTCONF / gNMI operations
- Post-change verification
- Rollback and recovery workflow
- Audit evidence and provenance
- Confirmed-commit transaction handling

### PH-5 — Intent / Desired State Automation

Status: `PLANNED`

Scope:

- Desired state model
- Current vs desired comparison
- Drift detection
- Change plan generation
- Intent validation
- Approval workflow integration
- Remediation through PH-4 transaction engine

### PH-6 — Distributed Execution / HA

Status: `PLANNED`

Scope:

- Worker execution model
- Distributed queue
- Execution ownership
- Leader/fencing model
- Failover recovery
- Large-scale change orchestration
- Multi-node reliability


# NI — Network Intelligence

NI answers:

> What exists in the network and what is happening?

## NI-1 — Endpoint Location Correlation

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- IP → MAC correlation
- MAC → VLAN mapping
- VLAN → Switch port mapping
- Endpoint location discovery
- Q-BRIDGE FDB correlation
- Neighbor table correlation

Example:

```
IP
 |
MAC
 |
VLAN
 |
Switch Port
```

## NI-2 — Topology Identity

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- LLDP discovery
- CDP handling
- Device identity
- Chassis identity
- Interface identity
- Neighbor relationship
- Downstream impact traversal

## NI-3 — Network Events

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- SNMP Trap
- Syslog
- Link events
- Authentication events
- Reachability events
- Event normalization

## NI-4 — Alert Lifecycle

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- Alert promotion
- Severity handling
- Acknowledge workflow
- Resolve workflow
- Maintenance suppression
- Notification workflow

## NI-5 — Telemetry

Status: `PLANNED`

Scope:

- SNMP polling
- gNMI telemetry
- Streaming metrics
- Interface statistics
- CPU/memory/environment telemetry
- Time-series storage
- Trend analysis
- Performance baseline

## NI-6 — Discovery Analytics

Status: `PLANNED`

Scope:

### Auto Seed Discovery

- Seed device input
- Credential selection
- Discovery start workflow

### Full Network Crawl

- LLDP/CDP neighbor crawling
- Discovery queue
- Visited device tracking
- Crawl depth control
- Rate limiting
- Failure handling

### Topology Database

Nodes:

- Device
- Interface
- Link
- VLAN
- VRF
- Subnet
- Endpoint

Edges:

- CONNECTED_TO
- ATTACHED_TO
- CARRIES
- ROUTES_TO

### Unified L2/L3 Topology

- MAC path
- VLAN path
- IP path
- VRF path
- Routing relationship

### Topology Visualization

- Interactive topology graph
- Device map
- Link status
- VLAN view
- VRF view
- Path tracing
- Impact highlighting


## Release 35 PH-4 Completion Hardening

- NETCONF confirmed-commit lifecycle state model added.
- Recovery evidence schema integrated as transaction evidence boundary.
- PH-4 regression coverage added.
- Final qualification remains IMPLEMENTED_TESTING_DEFERRED until executed.


# PH-5 Intent / Desired State Automation

Status: IMPLEMENTED_TESTING_DEFERRED

Scope: DesiredState, Intent lifecycle, revisions, drift detection, Change Plan generation, PH-4 transaction integration boundary, approval and audit linkage.


# PH-5 API and Operations Surface

Status: IMPLEMENTED_TESTING_DEFERRED

Added PH-5 API helpers, intent workflow surface, and Web Console Intent Automation entry point. Device changes remain delegated to PH-4 transaction workflow.


## PH-6 Distributed Execution / HA
Status: IMPLEMENTED_TESTING_DEFERRED

## NI-6.4 Failure Risk Foundation — 2026-09-16

Status: `IMPLEMENTED_TESTING_DEFERRED`.

Implemented `opt/netconfig/netconfig/analytics/failure_risk.py` with `FailureRiskSignal`, `FailureRiskObservation`, and `FailureRiskAnalyzer`. The analyzer accepts only `INTERFACE_ERROR_SPIKE`, `LINK_FLAPPING`, `TEMPERATURE_ANOMALY`, `PACKET_DROP_INCREASE`, and `TELEMETRY_DEGRADATION`; unsupported signal types/severities fail closed. Tenant identity is authoritative caller context and is not taken from signal payloads. Output is observation/evidence plus a `FAILURE_RISK` insight mapping only; there is no execution/remediation surface.

NI-6.3 inherited regression repaired in the same delivery: the capacity threshold now matches the documented contract (`30 -> 85` remains WARNING; >=200% increase over baseline is CRITICAL). This was required because the parent NI-6.3 artifact carried a test/code mismatch.

Validation: focused NI-6.3 + NI-6.4 `9 passed`; full repository `192 passed / 7 skipped`; selftest `ALL PASS`; `compileall` PASS. An initial full-suite invocation with only `PYTHONPATH=opt/netconfig` produced four collection errors for tests importing the repository-root `opt` package; the canonical extracted-tree invocation `PYTHONPATH=.:opt/netconfig pytest -q` passed. Q-1/Ruff remains explicitly deferred/`NOT_RUN`.

Deferred: production threshold calibration, real-device failure correlation, live vendor telemetry qualification, API/UI surfacing, and all remediation. NI-6.5/NI-6.6 remain planned.



NI-6.6 Health Dashboard: IMPLEMENTED_TESTING_DEFERRED

## 2026-09-16 — NI-6 Enterprise Operations & Qualification Hardening

Implemented the product integration layer that was missing from the NI-6 foundation. Added durable `network_insights` and `analytics_jobs` tables (portable SQLite/PostgreSQL schema), `AnalyticsService`, Manager wiring, `analytics:read`/`analytics:write` token scopes, read-only GET APIs and explicit mutation POST APIs, and an Operations → Network Intelligence console. Insight lifecycle is auditable and persistent; dashboard GETs do not implicitly mutate state.

Impact simulation is now routed through NI-2 `downstream_impact()` so only resolved managed directional adjacency is traversed. The lower-level simulator is also fail-closed when managed/resolution metadata is present. Health returns `UNKNOWN` without evidence. No analytics path can execute remediation; operator actions are navigation into existing approved change workflows.

Validation before artifact freeze: 202 passed / 7 skipped / 0 failed; selftest ALL PASS; compileall/launcher/package-shell syntax PASS. First full run exposed only same-line compound-statement hygiene violations in newly added code; these were corrected, then the full suite passed.

## 2026-09-16 — NI-6 enterprise qualification hardening

NI-6 was wired into `Manager.analytics`, REST and the Operations Network Intelligence console with durable insights/jobs and approval-plane-only action routing. Frozen-source full regression passed 202/7/0. A clean-extraction candidate passed CRC/traversal/symlink/cache/CR/mode/manifests and reran 202 passed / 7 skipped / 0 failed plus selftest ALL PASS. Q-1/live gates remain deferred.

## 2026-09-16 — Release 37 RPM installation hardening

- Promoted RPM package identity from historical `2.0.0-34` to `2.0.0-37` so the distributable package identified the then-current Release 37 NI-6 source.
- Added `packaging/install-rpm.sh`, a fail-closed AlmaLinux 10 install/upgrade helper. It validates package identity, preserves runtime state/config semantics, and deliberately does not auto-create an administrator/vault or silently expose the web console.
- Reworked `opt/netconfig/INSTALL.md` and `packaging/README.md` around the supported production sequence: RPM install -> explicit first-admin bootstrap -> enable local-only web + backup timer -> smoke/qualification checks.
- RPM binary/SRPM build and installed-runtime qualification remain `NOT_RUN` in the current Debian runner; use an AlmaLinux 10 qualification host for those gates.

## 2026-09-17 — Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

Implemented durable `l3_route_observations`, `L3RouteAnalyzer`, same-VRF bounded/cycle-safe path simulation, route dependency candidate analysis, `L3_PATH`/`ROUTE_DEPENDENCY` persisted insight types, REST/API and Operations UI integration. Managed next-device identity is explicit only; no IP/topology guess is permitted. Multipath ambiguity stops path traversal instead of selecting a winner. Dependency candidates preserve distinct routes even when they share the same upstream/failed next device and report observed alternatives without claiming outage. Database schema revision advances to `ni7-l3-route-1`; PostgreSQL serial-table compatibility includes the new observation table. Q-1 live qualification remains deferred. Source regression before final packaging: **211 passed / 7 skipped / 0 failed**.

Release 40 candidate fresh-clone qualification reproduced **211 passed / 7 skipped / 0 failed**, selftest ALL PASS, compile/shell/YAML PASS, manifest checks PASS, **8/8 Git executable modes**, and a clean post-test worktree. This is offline source evidence only; it does not close Q-1 live service/vendor/AlmaLinux gates.

## 2026-09-17 — Release 41 documentation truth sync

- Synchronized all **39** maintained Markdown files with the active Release 41 / `2.0.0-41` baseline or an explicit historical-evidence notice.
- Added `DOCUMENTATION_STATUS.md` as the documentation truth map and complete file inventory.
- Corrected package wording so `netconfig-2.0.0-43.el10.noarch.rpm` is an **expected target package name**, not a claimed binary deliverable.
- Preserved historical release-specific counts in historical files while preventing them from overriding current Release 43 truth.
- Current Git evidence remains **213 passed / 7 skipped / 0 failed**; documentation-sync full-source archive evidence is **212 passed / 8 skipped / 0 failed** because the Git-index mode test is inapplicable without `.git`.
- Actual Ruff `0.16.7` and mypy execution remain `NOT_RUN`; Q-1 live gates remain deferred.
- No runtime/schema/API behavior changed in this documentation-only sync.
## 2026-09-18 — Release 43 all-Markdown roadmap/truth synchronization

- Reviewed all 40 Markdown files against the Release 43 source baseline.
- Closed the post-NI-7 roadmap review with **no new development phase assigned**; NI-7 remains the feature baseline and Q-1 remains an open qualification track.
- Reclassified `Q1_PRODUCTION_QUALIFICATION.md` as `CURRENT / MAINTAINED` because Q-1 is still open; its Release 39 origin evidence remains historical inside the file.
- Corrected stale current-state wording in `AGENTS.md`, `AI_HANDOFF.md`, `HANDOVER_PROMPT.md`, `ARCHITECTURE.md`, `DEV_BASELINE.md`, `CURRENT_PROGRESS_DELIVERY_REPORT.md`, `DELIVERY_REPORT.md`, and `packaging/README.md`.
- Marked retained PH/NI `PLANNED` architecture snapshots as historical so they cannot be mistaken for current roadmap assignments.
- Added a roadmap-disposition/current-pointer marker to every Markdown file. Historical counts and evidence remain unchanged.
- Documentation-only change: no runtime/schema/API behavior change and no RPM Release bump. Ruff `0.16.7`, mypy, canonical AlmaLinux package qualification, and other Q-1 live gates remain `NOT_RUN`/deferred unless separately executed.
- Post-sync source/archive-style regression: **217 passed / 8 skipped / 0 failed**; legacy selftest **ALL PASS**; compileall, launcher `py_compile`, packaging/tool shell syntax and operational CR scan **PASS**. The eighth skip is the Git-index executable-mode test because this working source was extracted without `.git`. Ruff `0.16.7` remains **NOT_RUN** because the executable is unavailable.
- Delivery target for this documentation-only maintenance pass: `netconfig-netconfig-2.0.0-43-sidebar-theme-refresh-v14.zip` (complete modifiable source tree; Release remains 42).
### Documentation-sync final artifact gate

Final artifact gate using mode-preserving `unzip`: ZIP CRC **PASS**; source-to-extracted byte identity **190/190 PASS**; Markdown truth markers/inventory **40/40 PASS**; required executable modes **12/12 = 0755**; path traversal **0**; symlinks **0**; cache/pyc/pytest-cache entries **0**; operational CR offenders **0**; `source-manifest.sha256` **PASS**; `SHA256SUMS` **PASS**; extracted pytest **217 passed / 8 skipped / 0 failed**; extracted legacy selftest **ALL PASS**; extracted compileall / launcher `py_compile` / shell syntax **PASS**. Ruff `0.16.7` remains **NOT_RUN** because the executable is unavailable.

Delivery artifact: `netconfig-netconfig-2.0.0-43-sidebar-theme-refresh-v14.zip`. This remains Release 43 / `2.0.0-43`; the gate does not promote project status beyond `IMPLEMENTED_TESTING_DEFERRED`.

## 2026-09-22 — Release 50 working baseline: NetFlow device-form visibility fix

- Fixed the Device edit form so the NetFlow section is visible server-side for `network` devices.
- Root cause: `netflow_section`, `portmon_section`, and `appmon_section` were rendered with inline `style="display:none"`; the JavaScript toggler only changed the `hidden` property, so the inline CSS kept the sections invisible.
- Replaced unconditional inline hiding with server-side `hidden` attributes based on the selected device type; the existing JavaScript toggler continues to update visibility when device-type checkboxes change.
- Added WebUI regressions proving a network-device edit page contains a visible NetFlow section and a non-network application device keeps it hidden.
- No NetFlow collector/parser behavior or device I/O was changed.
- RPM remains deferred until the roadmap implementation is complete.


## 2026-09-22 — UI/CSS regression review

A fresh console review found and corrected cross-cutting presentation regressions introduced by the CSS/theme consolidation: a second `hidden`/`display:none` conflict on the dashboard no-results message; stale custom properties (`--txt`, `--bad`, `--brass`, `--brass2`, `--muted`); checkbox/radio controls inheriting the global 100% input width; dynamic graph markup bypassing theme classes; narrow-screen header wrapping; narrow-screen table overflow; and long Help inline-code overflow. The strict-CSP renderer still converts server-side `style=` attributes into nonce-authorized generated classes, and representative rendered pages were checked to contain zero residual inline-style attributes after transformation. Browser rendering smoke checks at 1440px and 390px showed no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes; Network-device NetFlow remains visible while non-network NetFlow remains hidden.

Focused regression: `tests/test_css_regression_review.py`, `tests/test_ui1_web_console.py`, and `tests/test_platform_hardening_ph1.py` pass together. Full repository evidence must still preserve explicit live/integration skips and must not be promoted to `TESTED` or `RELEASED`.

Final review evidence: focused CSS/WebUI/CSP regression is **27 passed / 0 failed**. Bounded full repository regression totals **248 passed / 8 skipped / 0 failed**. The eight skips are the expected source-archive Git metadata check plus seven explicit live PostgreSQL/backup/protocol-service prerequisites. Representative rendered-page Chromium smoke at 1440px and 390px found no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes. See `CSS_UI_REVIEW_2026-09-22.md`.

## 2026-09-23 — Release 50 MC-2 Sensor History & State Transitions

Implemented the complete MC-2 source slice on top of MC-2.1. `SensorEngine` now owns a `SensorHistoryRecorder`; every canonical Sensor upsert records an observation and emits a transition only when normalized status changes. `interface.utilization` is normalized at 80% WARNING / 95% CRITICAL, so noisy same-band numeric changes do not create transitions. `UNKNOWN` remains evidence absence rather than failure; UNKNOWN→known is tagged `evidence_recovered`, and known→UNKNOWN is `evidence_lost`.

Interface/topology/Loop Protection refresh paths no longer delete active current rows before comparison, preserving previous snapshots for transition detection. Stale interface resources are pruned only after active resources are upserted. Restart duplicate protection relies on the persisted canonical `sensors` row, so recreating `SensorEngine` on the same database does not replay an unchanged transition.

History retention is bounded: raw observations are retained for 30 days and transitions for 180 days, with at-most-hourly opportunistic pruning during Sensor history writes. Added type/time and resource/time indexes in addition to existing device/key/status indexes; schema revision is `mc2-sensor-history-2`.

Read-only APIs: `GET /api/v1/sensor-history?sensor_key=...` and `GET /api/v1/sensor-transitions`, both bounded by `limit` and supporting `since`/`before` time filters. Device SNMP health view now shows a read-only “Recent sensor changes” timeline. No page/API history read triggers polling or Sensor refresh.
## 2026-09-23 — Release 50 MC-2 regression evidence

Final source-tree regression was executed in bounded groups after the MC-2 runtime/API/WebUI/retention changes: **260 passed / 8 skipped / 0 failed**. The eight skips are the expected source-archive/live-service gates: one Git-index executable-mode check (no `.git` in source ZIP), three live PostgreSQL tests, one PostgreSQL backup/restore drill, and three protocol-service integration tests. `python3 opt/netconfig/selftest.py` reports **RESULT: ALL PASS**; `compileall` passes; packaging/rpm-builder shell syntax passes. Ruff and mypy remain `NOT_RUN`.

## 2026-09-23 — Release 51 MC-3 Normalized Operational Evidence

Implemented the MC-3 event normalization boundary on top of Release 50 without changing collection frequency or adding device I/O. `operational_events` gained additive semantic columns for domain/entity/resource/status/time/evidence reference, with SQLite/PostgreSQL migration support, legacy-row backfill, and domain/entity/evidence indexes. The schema revision is now `mc3-operational-evidence-1`.

`OperationalEventStore.record()` now normalizes legacy trap/syslog/event callers at one boundary while preserving deduplication, alert-lifecycle integration, maintenance behavior, and dependency suppression. Metadata remains allow-listed and bounded; raw trap packets, SNMP communities, and arbitrary secret material remain outside the event store. `record_sensor_transition()` maps durable MC-2 transitions into normalized NETWORK evidence with `sensor-transition:<id>` provenance. Re-bridging the same durable transition is idempotent.

`Manager._refresh_sensors_and_bridge_events()` captures the Sensor transition high-water mark, runs the existing persisted-evidence Sensor refresh, and bridges only newly durable transitions for the polled device. The prior direct SNMP reachability event emission was removed so reachability changes are represented by the canonical Sensor transition path rather than duplicated by polling code. Initial Sensor observations and unchanged refreshes generate no transition event; known→UNKNOWN emits INFO evidence-unavailable semantics rather than CRITICAL.

The Event API now supports bounded normalized filters and `GET /api/v1/events/{id}` detail including the current related Sensor. The Event WebUI was moved into `web_ui.py` to keep the PH-1 `web.py` structural size gate intact and now renders the MC-3 semantic detail surface.

### Release 51 MC-3 verification evidence

Focused MC-3: **10 passed**. Bounded full repository regression: **270 passed / 8 skipped / 0 failed**. Legacy selftest: **ALL PASS**. Compileall, launcher/rpm-builder Python syntax, and packaging/rpm-builder shell syntax: **PASS**. Release 50-created SQLite database → Release 51 additive event-schema migration/backfill: **PASS**. Ruff/mypy: `NOT_RUN` (executables unavailable). Live PostgreSQL/protocol-service gates remain deferred and are not counted as passed.

## 2026-09-23 — R51-HF1 pre-MC4 SNMPv3 + Topology compatibility hotfix

Implemented a compatibility/hardening patch on top of Release 51 without advancing the roadmap release number. MC-4 / Release 52 remains `PLANNED`; this patch remains `IMPLEMENTED_TESTING_DEFERRED` until target-device/service qualification is performed.

### SNMPv3

- Split AES privacy key extension into explicit Blumenthal and Cisco/Reeder algorithms.
- Generic `aes192` / `aes256` now use Blumenthal extension, matching Net-SNMP `AES-192` / `AES-256` semantics; explicit `aes192c` / `aes256c` retain Cisco/Reeder compatibility.
- Added normalization aliases and Net-SNMP display-name mapping used by diagnostics.
- Updated offline selftest and focused regression so SHA1+AES256 checks the 32-byte `(Kul || H(Kul))` Blumenthal result while proving the explicit Reeder variant is distinct.
- No credential material is logged or persisted differently.

### Topology

- `topology --discover` now calls the in-process Vault unlock path before discovery so a prior stateless `vault unlock` invocation is no longer required.
- Added normalized MAC parsing and `infer_fdb_edges()` using already-persisted FDB/MAC plus managed device interface/chassis identities.
- FDB evidence creates only `INFERRED`, `MEDIUM`-confidence, `direct_adjacency=false` paths and never overrides a resolved LLDP/CDP `OBSERVED` edge.
- Added `build_graph()` so every managed inventory device is represented even when the agent exposes no LLDP/CDP remote table. Such nodes remain `UNKNOWN` when there is no adjacency evidence.
- Downstream impact remains bounded to observed resolved managed LLDP/CDP adjacency; inferred FDB paths are not traversed.
- Added `Manager.topology_graph()` and `GET /api/v1/topology/graph`. Both are read-only over persisted evidence and introduce no device I/O.
- Topology Web UI moved to `web_ui.py` to preserve the PH-1 `web.py` <240 KB structural gate. It provides drag/drop, pan/zoom, reset controls, evidence legend/table, and browser-local layout persistence only; dragging never changes network truth.

### Verification

- Hotfix focused: **8 passed / 0 failed**.
- Topology/Web/PH-1/legacy combined: **40 passed / 0 failed**.
- Bounded repository groups: **278 passed / 1 skipped / 0 failed**; integration inventory: **7 skipped**. Aggregate: **278 passed / 8 skipped / 0 failed**.
- Seven integration skips require live PostgreSQL/backup/protocol services; the eighth skip is the source-tree Git metadata/mode check because this delivery workspace is an extracted source baseline.
- Legacy selftest: **RESULT: ALL PASS**.
- `compileall`, launcher `py_compile`, and packaging/rpm-builder shell syntax: **PASS**.
- Ruff/mypy: **NOT_RUN** (executables unavailable).
- Live FortiGate SNMPv3 SHA1+AES256 revalidation and live vendor topology behavior: **DEFERRED/NOT_RUN**.

