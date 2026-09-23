# NetConfig Production Qualification Validation Summary

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

## Release 48 current status

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

Release 48 adds the persisted read-only Sensor Engine/API over existing evidence. Historical release evidence below remains unchanged and must not be read as the current package identity.


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

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.


## Historical Release 43 — Offline RPM Builder Integration

Release 43 adds `tools/rpm-builder/`, a deterministic dependency-free RPM emitter plus an independent offline verifier. The helper reads `packaging/netconfig.spec`, packages only the canonical NetConfig runtime payload, preserves executable/config ownership semantics, encodes lifecycle scriptlets and dependencies, and verifies RPM header digests, gzip/newc payload integrity, source-byte identity, modes, `CONFIG|NOREPLACE`, requirements, and scriptlets. `SOURCE_DATE_EPOCH=1789689600` is the deterministic default for this release. The same source and epoch must produce byte-identical RPMs. This helper is **not** the production qualification authority: canonical AlmaLinux 10 `rpmbuild`, `rpm -qp`, DNF install/upgrade, systemd restart/reboot, SELinux behavior, and remaining Q-1 live gates stay deferred until actually executed.
Archive-derived qualification for Release 43 on this runner is **218 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the existing PostgreSQL backup/restore and OpenSSH/Net-SNMP integration gates plus the expected Git-index executable-mode skip because `.git` is intentionally absent from the source archive. Compileall and the focused sidebar/branding console regressions pass. The offline builder emitted `netconfig-2.0.0-43.el10.noarch.rpm` with SHA-256 `0bc3abca0b3349593f67593930e9c8e1298cfe511a42d24d38f4f2d26babc7c2`; the independent verifier passed RPM header digest, compressed payload digest, gzip/newc parsing, payload/source byte identity, modes, `CONFIG|NOREPLACE`, dependencies, and lifecycle scriptlets. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.



## Release 41 — Corrective REST + Git/Ruff Hardening

- Release/RPM identity: **2.0.0-41**.
- Correctness fix: campaign retry REST `wave` reads list-valued `form`, with route-level HTTP regression.
- Fresh-clone regression: **213 passed / 7 skipped / 0 failed**.
- Git index modes: **8/8 = 100755**; source manifest verifies; legacy selftest **ALL PASS**; compileall/launcher/package-shell checks **PASS**; post-test worktree clean.
- Identified F821/B018/B905/B007/F401/F841-style debt corrected without widening Ruff ignores. Actual Ruff `0.16.7` and mypy execution remain **NOT_RUN** because tools are unavailable in the isolated runner.
- Q-1 live PostgreSQL/backup, OpenSSH/Net-SNMP, vendor/device/scale and AlmaLinux RPM gates remain deferred/`NOT_RUN`.

### Release 41 delivery-surface evidence

- Git fresh clone / Git bundle: **213 passed / 7 skipped / 0 failed**; 8/8 required Git index modes `100755`; manifest, selftest, compile/package-shell and clean-worktree gates PASS.
- Full-source ZIP: **183/183 tracked files byte-identical**, 8/8 executable archive modes `0755`, 0 traversal/symlink/cache/CR findings; clean extraction **212 passed / 8 skipped / 0 failed**.
- RPM build-source ZIP: **183/183 tracked files byte-identical**, 8/8 executable archive modes `0755`; clean extraction **212 passed / 8 skipped / 0 failed**.
- Archive-only eighth skip is `test_required_git_index_executables_are_100755`, which deliberately skips when `.git` is absent; `test_required_raw_source_executables_are_0755` passes when the archive is extracted with the qualification extractor, and archive mode is also verified independently from ZIP metadata.
- Release 41 binary RPM remains **NOT BUILT / NOT QUALIFIED**.

## Historical Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

- Release/RPM identity: **2.0.0-40**.
- Schema revision: **ni7-l3-route-1**.
- NI-7 focused: **5 passed**.
- Full source regression before final packaging: **211 passed / 7 skipped / 0 failed**.
- Selftest: **ALL PASS**. Compileall/launcher/shell/YAML/operational-CR checks: **PASS**.
- Safety: same-VRF only, explicit managed next-device identity, bounded/cycle-safe traversal, no arbitrary ECMP winner, route-dependency candidate only, no direct configuration execution.
- Q-1 live PostgreSQL/protocol/vendor/AlmaLinux qualification remains deferred/NOT_RUN.

### Release 40 candidate fresh-clone evidence

Candidate commit fresh clone reproduced the complete test inventory in bounded groups: **211 passed / 7 skipped / 0 failed**. NI-7 focused **5 passed**; `source-manifest.sha256` and metadata checksums **PASS**; required Git index modes **8/8 = 100755**; legacy selftest **ALL PASS**; compileall, launcher compile, and packaging shell syntax **PASS**. After cache removal the clone returned to a clean Git worktree. The seven live/service tests remain intentionally skipped and Q-1 live gates remain deferred/`NOT_RUN`.

### Release 40 final delivery qualification

The frozen delivery surface is independently qualified. The full-source Git-archive ZIP contains **199 archive entries**, matches **181/181 Git-tracked files byte-for-byte**, and has **0** path-traversal entries, **0** symlinks, **0** cache/bytecode entries, **0** operational-text CR offenders, and **8/8** required executable files at mode `0755`; source and metadata manifests verify. From its clean extraction, the complete repository test inventory executes as **211 passed / 7 skipped / 0 failed**, with legacy selftest **ALL PASS** and compile/launcher/package-shell checks **PASS**. The clonable Git bundle reproduces the same commit, manifest and 8/8 Git `100755` modes and executes the same **211/7/0** regression plus selftest/compile with a clean post-test worktree. The `2.0.0-40` RPM build-source bundle has no traversal/symlink/cache entries, preserves all eight executable modes, verifies manifests/package identity, and passes **25/25** focused NI-7/repository-hygiene/Q-1 tests. Actual AlmaLinux RPM build/install and Q-1 live service/vendor gates remain `NOT_RUN`/deferred. The final archive SHA-256 is intentionally carried in external `.sha256` sidecars so the payload does not self-reference its own digest.

## Historical Release 39 — Q-1 Production Qualification Hardening

- Release/RPM identity: **2.0.0-39**.
- Release 38 installer defect fixed: the guarded installer now validates RPM Release `39`; stale comparison against `37` is prohibited by regression.
- Git index executable modes: **8/8 = 100755 PASS**.
- Source full pytest: **206 passed / 7 skipped / 0 failed**.
- Q-1 focused pytest: **12 passed / 0 failed**.
- Legacy selftest: **ALL PASS**.
- compileall / launcher `py_compile` / packaging shell syntax / workflow YAML / CR scan: **PASS**.
- Staged installed-filesystem systemd unit verification: **PASS**.
- Runtime `netconfig qualify` on this runner: **NOT READY** — required SSH client absent; Python/openssl/SQLite core storage pass; gNMI is optional while disabled.
- Ruff `0.16.7`: **NOT_RUN** — pinned but executable unavailable and package download unavailable.
- mypy `2.3.1`: **NOT_RUN** — pinned but executable unavailable and package download unavailable.
- PostgreSQL service-backed Q-1: **NOT_RUN** — `pg_dump`/server tooling unavailable.
- OpenSSH/Net-SNMP integration: **NOT_RUN** — services/tools unavailable.
- AlmaLinux 10 RPM build/install: **NOT_RUN** on this Debian runner; source CI now contains an AlmaLinux 10 build/static job, but no workflow execution is claimed here.

Release 39 remains `IMPLEMENTED_TESTING_DEFERRED`; source/offline qualification is green, while production/service-backed qualification is still open.

## Implemented boundary

- `Manager.analytics` is the single product boundary for NI-6 analyzers.
- Durable `network_insights` lifecycle: `NEW`, `ACKNOWLEDGED`, `RESOLVED`, `EXPIRED`.
- Durable `analytics_jobs` execution evidence.
- REST scopes: `analytics:read`, `analytics:write`; write requires operator-or-higher role.
- Operations → **Network Intelligence** UI with refresh, impact simulation, filters/search, insight detail/evidence/affected objects and lifecycle updates.
- Impact simulation traverses only resolved managed directional topology from the existing NI-2 truth plane.
- Analytics cannot execute remediation; action navigation leads only to existing approved Structured Changes / Desired State / Campaign workflows.

## Source validation

- focused repository-hygiene + enterprise analytics workflow: **10 passed / 0 failed**
- full repository: **202 passed / 7 skipped / 0 failed**
- legacy selftest: **ALL PASS**
- compileall: **PASS**
- launcher `py_compile`: **PASS**
- packaging shell syntax: **PASS**
- required executable modes: **7/7 = 0755**
- `web.py`: **239,648 bytes / 3,850 lines** (PH-1 boundary preserved)
- operational-text CR offenders: **0**
- symlinks: **0**
- Q-1/Ruff/mypy: **NOT_RUN** by explicit deferral

## Clean-extraction qualification staging artifact

The frozen candidate was created only after cache cleanup and manifest generation, then extracted into a new directory and independently validated:

- ZIP CRC: **PASS**
- path traversal entries: **0**
- ZIP symlink entries: **0**
- extracted symlinks: **0**
- `__pycache__`, `.pytest_cache`, `*.pyc` entries before tests: **0**
- `source-manifest.sha256`: **PASS**
- internal `SHA256SUMS`: **PASS**
- required executable modes: **7/7 = 0755**
- operational-text CR offenders: **0**
- extracted-tree full repository: **202 passed / 7 skipped / 0 failed**
- extracted-tree legacy selftest: **ALL PASS**
- extracted-tree compileall / launcher py_compile / packaging shell syntax: **PASS**

The final archive is built from the same qualified source after this evidence/documentation sync. Its archive SHA-256 is distributed as an external `.zip.sha256` sidecar to avoid circular self-checksumming.

## Deferred live gates

The seven skipped tests remain live/service-backed PostgreSQL backup/restore and protocol integration gates. Real vendor/device, production telemetry scale, production analytics threshold calibration and operational load qualification remain `NOT_RUN`/deferred. None are counted as PASS.

## Promotion boundary

Offline source and clean-extraction artifact qualification are complete. NI-6 remains `IMPLEMENTED_TESTING_DEFERRED`, not `TESTED` or `RELEASED`, until the applicable Q-1/live environment gates are executed and recorded.

## Release 37 RPM installation hardening — 2026-09-16

- RPM source identity: Version `2.0.0`, Release `37`.
- Focused repository hygiene: `5 passed`.
- Full source regression: `202 passed / 7 skipped / 0 failed` using `PYTHONPATH=.`.
- Legacy selftest: `ALL PASS`.
- Python compileall: PASS.
- All `packaging/*.sh` syntax: PASS.
- `packaging/install-rpm.sh` on the Debian artifact runner: fail-closed exit `20` because the production RPM target is AlmaLinux 10 (expected PASS of the guard behavior).
- `packaging/build-rpm.sh` on the Debian artifact runner: exit `2` because `rpmbuild` is unavailable; binary RPM build/install is therefore `NOT_RUN`, not PASS.
- Real AlmaLinux 10 RPM build, RPM payload inspection, dnf install/upgrade, systemd start/restart, and installed-runtime smoke remain deferred qualification gates.

### RPM install v3 candidate clean-extraction evidence

- Candidate ZIP CRC: PASS.
- ZIP path traversal / symlink / cache checks: PASS / 0 findings.
- Operational CR/line-ending check: PASS.
- Required executable modes: 8/8 = `0755`.
- `source-manifest.sha256` and metadata `SHA256SUMS`: PASS.
- Full regular-file byte identity against the frozen source tree: `175/175 PASS`.
- Candidate extracted-tree full regression: `202 passed / 7 skipped / 0 failed`.
- Candidate extracted-tree legacy selftest: `ALL PASS`.
- Candidate extracted-tree `packaging/*.sh` syntax: PASS.
- Candidate extracted-tree `install-rpm.sh` non-AlmaLinux fail-closed guard: PASS (exit `20` on Debian 13).
- Binary RPM build/install remains `NOT_RUN` because this artifact runner is Debian 13 without the AlmaLinux 10 `rpmbuild`/Python 3.12 target environment.

## Release 40 NI-7 current validation

Source workspace validation before final artifact freeze: NI-7 focused **5 passed**; full repository **211 passed / 7 skipped / 0 failed**. NI-7 uses explicit managed route observations only and remains decision-support/read-only. Final artifact/fresh-clone evidence must be recorded after packaging; Q-1 live service, vendor/device, AlmaLinux and scale gates remain deferred/NOT_RUN.

### Release 40 fresh-clone evidence

Clean Git clone: **211 passed / 7 skipped / 0 failed**; 8/8 required executables `100755` in the index and `0755` in the worktree; source manifest and metadata checksum verification PASS; selftest ALL PASS; compile/shell/YAML PASS; post-test worktree clean after cache removal.

## Release 41 documentation truth sync

- All **40** maintained Markdown files now carry either current Release 43 truth or an explicit historical-evidence notice; see `DOCUMENTATION_STATUS.md`.
- Documentation consistency / campaign-retry / repository-hygiene focused checks remain green.
- Runtime regression is unchanged: Git checkout/bundle **213 passed / 7 skipped / 0 failed**; documentation-sync source ZIP **212 passed / 8 skipped / 0 failed**.
- The archive-only additional skip is `test_required_git_index_executables_are_100755`; `.git` is absent by design. Raw extracted executable-mode validation passes with the qualification extractor.
- Ruff `0.16.7`, mypy, and Q-1 live gates remain `NOT_RUN`/deferred where prerequisites are unavailable.
## Release 43 Markdown truth-sync validation boundary — 2026-09-18

This documentation-only maintenance pass covers all 40 Markdown files. Required checks are: every Markdown file carries an explicit current-roadmap or historical pointer; `DOCUMENTATION_STATUS.md` inventories all 40 files; Q-1 is classified current/maintained; current docs identify Release 43 / `2.0.0-43`, NI-7 as the feature baseline, and no assigned next development phase; historical evidence remains labeled as chronology. This gate does not convert Ruff/mypy, AlmaLinux RPM/systemd/SELinux, PostgreSQL, protocol-service, vendor/device, routing/VRF, or scale gates into PASS.

Measured source-tree result after synchronization: **217 passed / 8 skipped / 0 failed**, selftest **ALL PASS**, compileall/launcher/shell/CR checks **PASS**, Markdown inventory/truth markers **40/40 PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because the executable is unavailable. Final ZIP structural/source-identity evidence is recorded only after the delivered artifact is built and independently extracted.
### Documentation-sync final artifact gate

Final artifact gate using mode-preserving `unzip`: ZIP CRC **PASS**; source-to-extracted byte identity **190/190 PASS**; Markdown truth markers/inventory **40/40 PASS**; required executable modes **12/12 = 0755**; path traversal **0**; symlinks **0**; cache/pyc/pytest-cache entries **0**; operational CR offenders **0**; `source-manifest.sha256` **PASS**; `SHA256SUMS` **PASS**; extracted pytest **217 passed / 8 skipped / 0 failed**; extracted legacy selftest **ALL PASS**; extracted compileall / launcher `py_compile` / shell syntax **PASS**. Ruff `0.16.7` remains **NOT_RUN** because the executable is unavailable.

Delivery artifact: `netconfig-netconfig-2.0.0-43-sidebar-theme-refresh-v14.zip`. This remains Release 43 / `2.0.0-43`; the gate does not promote project status beyond `IMPLEMENTED_TESTING_DEFERRED`.

## 2026-09-23 — R51-HF1 pre-MC4 hotfix

Offline source verification is green: focused hotfix **8 passed**, topology/Web/PH-1/legacy **40 passed**, bounded repository aggregate **278 passed / 8 skipped / 0 failed**, legacy selftest **ALL PASS**, compileall/launcher/shell syntax **PASS**. The eight skips remain one source-archive Git-metadata check plus seven explicit PostgreSQL/backup/protocol-service integration prerequisites. Ruff/mypy and all live FortiGate/vendor/service/RPM qualification remain `NOT_RUN`/deferred; status stays `IMPLEMENTED_TESTING_DEFERRED`.

