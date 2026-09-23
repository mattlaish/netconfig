# Roadmap

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence + R51-HF1 pre-MC4 compatibility hotfix** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

### Release 48 status

- **Status:** `IMPLEMENTED_TESTING_DEFERRED`
- **Implemented:** normalized Sensor Engine, persisted sensor rows, existing-evidence generators, read-only sensor API and filters, UNKNOWN semantics regression.
- **Not implemented:** Alert Engine, sensor-driven remediation, distributed Site Edge/Collector runtime, additional polling solely for visualization.
- **Qualification boundary:** local/source regression and offline RPM structural verification may pass without promoting the project to `TESTED` or `RELEASED`; live Q-1 gates remain authoritative.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.
## Recorded future architecture / UX candidates — NOT ASSIGNED

The following decisions are recorded for a future roadmap selection but are **not** an assigned implementation phase:

- distributed **Site Edge / Collector** architecture for site survivability and alert-path resilience, with local read-only polling, cache/spool, local health/alerts/UI, store-and-forward telemetry, and heartbeat to the Central Controller;
- collectors remain read-only by default (SNMP GET/WALK, NETCONF/RESTCONF read, gNMI subscribe); configuration push and arbitrary SSH are not collector capabilities by default; future distributed writes require a separate **Execution Node** or explicitly authorized execution role;
- local alert persistence/replay during central/WAN isolation, with possible future out-of-band fallback notification channels;
- user-facing terminology **Configuration Baselines / Templates & Drift**;
- keep the current approval capability but do not expand approval orchestration now;
- operator-oriented MIB sensor summaries from already-collected evidence, while keeping raw OIDs in Advanced and avoiding extra device I/O solely for visualization.

These candidates do not create NI-8/Q-2 or any other phase until explicitly selected.


## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.


## Historical Release 43 — Offline RPM Builder Integration

Release 43 adds `tools/rpm-builder/`, a deterministic dependency-free RPM emitter plus an independent offline verifier. The helper reads `packaging/netconfig.spec`, packages only the canonical NetConfig runtime payload, preserves executable/config ownership semantics, encodes lifecycle scriptlets and dependencies, and verifies RPM header digests, gzip/newc payload integrity, source-byte identity, modes, `CONFIG|NOREPLACE`, requirements, and scriptlets. `SOURCE_DATE_EPOCH=1789689600` is the deterministic default for this release. The same source and epoch must produce byte-identical RPMs. This helper is **not** the production qualification authority: canonical AlmaLinux 10 `rpmbuild`, `rpm -qp`, DNF install/upgrade, systemd restart/reboot, SELinux behavior, and remaining Q-1 live gates stay deferred until actually executed.
Release 43 candidate qualification from a real Git fresh clone is **218 passed / 7 skipped / 0 failed**; the seven skips are the existing PostgreSQL/backup and OpenSSH/Net-SNMP live-service gates. The same clone verifies **12/12 required executable paths at Git mode `100755`**, source-manifest integrity, legacy selftest **ALL PASS**, compile/launcher/package-shell checks, and a clean post-test worktree. An archive-derived source tree without `.git` is **217 passed / 8 skipped / 0 failed** because the Git-index mode test correctly skips. The offline builder produced `netconfig-2.0.0-43.el10.noarch.rpm` twice with identical SHA-256 `095b32b594b771e37e83c2cc89a27e9f87d8c5ae925d81ad94510083f0e612a1`; the independent verifier passed RPM header digest, compressed payload digest, gzip/newc parsing, payload/source byte identity, modes, `CONFIG|NOREPLACE`, dependencies, and lifecycle scriptlets. This remains offline evidence only; canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux is `NOT_RUN`.



## Release 41 documentation truth

Release 45 is `IMPLEMENTED_TESTING_DEFERRED`. It simplifies operator UX while preserving NI-7 as the feature baseline; the Release 42 offline RPM builder remains available. Production AlmaLinux `rpmbuild`/DNF/systemd/SELinux, Ruff/mypy, and other Q-1 live gates remain incomplete. No NI-8 or Q-2 phase is automatically assigned.

## Post-NI-7 roadmap review — COMPLETE (2026-09-18)

The roadmap review concluded with **no new implementation phase assigned**. NI-7 remains the feature baseline and Release 45 remains operator-UX hardening on top of that feature baseline. Q-1 remains open for real production/service qualification and may proceed without creating a new feature phase. Historical `NEXT`, `PLANNED`, Slice, PH, and NI ordering later in this file is preserved as chronology only. Any future NI-8, Q-2, security-debt implementation, or other new phase must be explicitly selected and entered into the roadmap before implementation starts.

## Release 41 — Corrective REST + Git/Ruff Hardening

**Status:** `IMPLEMENTED_TESTING_DEFERRED`.

Release 41 closes a dead campaign-retry REST route and hardens Git/CI reproducibility. It does not introduce NI-8 or a new mutation plane. Release 40 NI-7 remains the implemented feature baseline underneath this corrective release. Offline repository regression is **213 passed / 7 skipped / 0 failed**; Ruff/mypy actual execution and Q-1 live infrastructure gates remain deferred/`NOT_RUN` where prerequisites are unavailable.



## Historical Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

State: **IMPLEMENTED_TESTING_DEFERRED**. NI-7 resumes feature development after Release 39 while leaving Q-1 live gates explicitly deferred. Implemented scope: durable explicit L3 route observations; VRF-scoped bounded/cycle-safe path simulation; no next-hop-IP-to-device inference; fail-closed handling for missing/unmanaged/multipath/loop evidence; route dependency candidates with alternate-observation evidence; `L3_PATH` and `ROUTE_DEPENDENCY` insights; analytics REST/API and Network Intelligence UI integration. NI-7 remains read-only decision support and cannot bypass existing change approval.

Offline source evidence before final packaging: **211 passed / 7 skipped / 0 failed**. Live PostgreSQL/protocol/vendor/scale/AlmaLinux Q-1 gates remain deferred and must not be counted as NI-7 qualification PASS.

## Release 39 — Q-1 Production Qualification Hardening

State: **IMPLEMENTED_TESTING_DEFERRED**. Q-1 execution found and repaired the Release 38 RPM installer release-number mismatch and hardened CI/tool reproducibility. This release does not promote Q-1 to `TESTED`: Ruff/mypy and service-backed PostgreSQL/protocol/AlmaLinux installed-runtime/vendor/device/scale gates require actual execution. Release 38 Git mode/fresh-clone work remains inherited and must continue to pass.


## Release 38 — Git Reproducibility Hardening

State: **IMPLEMENTED_TESTING_DEFERRED**. Git index/worktree executable-mode reproducibility and fresh-clone pytest/selftest/compile/shell gates are implemented and locally verified. Ruff/mypy and live infrastructure/vendor/AlmaLinux qualification remain NOT_RUN/deferred, so Release 38 is not `TESTED` or `RELEASED`.

## UI-1 — Unified Automation & Operations Console — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source:

- unified `/operations` navigation with Structured Changes, Telemetry, Model Packs, Desired State, Campaigns, and HA / DR panels;
- PH-4 transaction ledger/detail, pre/post evidence, rollback approval submission, admin-only interrupted-transaction intake and reconciliation;
- NI-5 subscription create/edit/enable/disable/delete/capture/window, due-run maintenance, retention prune, bounded sample view and scalar time-series summary/trend;
- VM-1 built-in/custom pack inspection, admin lifecycle, explicit device binding/unbinding, effective resource browser and protocol filtering;
- NA-1 DRAFT edit/clone, approver publish, plan/drift evaluation, approval-gated apply request, run/evidence inspection;
- NA-2 campaign create/start/pause/resume/retry/abort, frozen-plan/target progress, and approval-gated next-wave request;
- HA-1 readiness, node heartbeat history, admin ACTIVE/DRAINING/DRAINED lifecycle, recovery-drill record/detail/complete evidence;
- automation Change Request review renders frozen/current snapshots and SHA-256 drift status instead of presenting automation JSON as CLI commands;
- all existing CSRF, RBAC, CSP nonce, vault, frozen-snapshot, audit and recovery invariants are retained.

**CURRENT:** Release 46 / Operator Health Cards & UX Follow-through — `IMPLEMENTED_TESTING_DEFERRED`.

### Future — Distributed Site Edge / Collector Survivability — `PLANNED`

Documented design only; **not implemented in Release 46**. Future Site Edge/Collectors remain read-only by default and are intended for local polling/cache/health/alert survivability and store-and-forward operation during WAN isolation. Configuration push and arbitrary SSH are prohibited by default; future distributed writes require a separate Execution Node or an explicitly authorized execution role.


**NEXT DEVELOPMENT PHASE:** **none assigned.** The post-NI-7 roadmap review is complete. Q-1 live qualification remains open and can be resumed independently; it is qualification work, not a new development phase. NI-8/Q-2 require an explicit future roadmap decision. Session idle/absolute expiry remains explicitly deferred security debt.


## Release 33 implementation expansion — source complete, qualification pending

The following development phases are now implemented in source. All remain `IMPLEMENTED_TESTING_DEFERRED`; implementation evidence must not be confused with real-device/service qualification.

- **PH-4 — Structured Configuration Transactions:** durable typed structured-change transactions; mandatory existing change-request approval references; frozen automation snapshots/hashes; per-device serialization; pre-read/change/post-read verification; idempotency; rollback and `RECOVERY_REQUIRED` reconciliation; NETCONF candidate/lock/validate/confirmed-commit-aware writes, bounded RESTCONF replace with pre-image rollback, and typed gNMI Set. No caller-supplied arbitrary XML/URL/protobuf passthrough is exposed.
- **NI-5 — Streaming Telemetry & Time-Series Intelligence Foundation:** durable gNMI telemetry subscriptions, bounded ON_CHANGE/SAMPLE stream windows, scheduled collection, raw bounded samples, normalized scalar time-series points, retention, summary/point APIs and CLI, and explicit error/due state. Long-running unbounded stream workers are not claimed.
- **VM-1 — Vendor Model Packs:** built-in Generic/OpenConfig plus Cisco IOS-XE, Juniper Junos, Arista EOS and Huawei VRP model packs; validated custom pack lifecycle; strict selector/path/resource allow-lists; device bindings; effective pack/hash/resource inspection. Model-pack hash is part of frozen automation/campaign evidence.
- **NA-1 — Intent / Desired-State Management:** durable DRAFT/PUBLISHED desired states, device/tag targeting, deterministic compilation through VM-1, plan/evaluate/run evidence, immutable published revisions via clone, approval-gated apply through PH-4, and reverse-order compensating rollback for earlier successful operations when a later operation fails.
- **NA-2 — Fleet Change Campaigns:** frozen fleet plan, canary/wave rollout, deterministic ordering, failure thresholds, explicit pause/resume/retry/abort, stable retry attempt identity, optional rollback-on-failure, campaign/device/model-pack drift fail-closed behavior, and approval-gated wave execution through the existing change-request workflow.
- **HA-1 — Control-plane HA & Recovery Foundation:** durable ACTIVE/DRAINING/DRAINED node lifecycle on top of PH-2 cluster heartbeats, drain-aware scheduler leadership, explicit automation admission blocking while draining, active-node readiness, recovery/DR drill evidence, and safe leadership handoff primitives. Automatic database failover is not claimed.

**Qualification Q-1 remains open** as `IMPLEMENTED_TESTING_DEFERRED`. Its real PostgreSQL, AlmaLinux RPM/systemd, OpenSSH/Net-SNMP, Ruff/mypy, and other service-backed gates still require actual execution. Session idle/absolute expiry remains explicitly deferred security debt.

**Release 33 consolidated source verification:** automation/repository hygiene focused **23 passed**; PH-2 **9 passed**; PH-3 **22 passed**; Q-1 **11 passed**; full repository **168 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher/shell syntax **PASS**; source CR/cache/symlink offenders **0**; required executable modes **7/7 = 0755**. Ruff and mypy remain `NOT_RUN` because neither binary is available in this isolated environment and package/binary retrieval is unavailable; no lint/type-check PASS is claimed.

**Release 33 candidate artifact:** Clean Release 33 candidate `netconfig_release33_candidate_2026-09-12.zip` (SHA-256 `d03720a411b796458747f7d8976a8fa01f4f40859b5e51341ef031aaa343f538`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; text CR offenders **0**; source/extracted byte identity **132/132 PASS**; payload plus each SHA/release manifest **128/128 PASS**; required executable modes **7/7 = 0755**. From the clean extraction: Release 33 focused **23 passed**, PH-2 **9 passed**, PH-3 **22 passed**, Q-1 **11 passed**, full repository **168 passed / 7 skipped** in the isolated full-suite rerun, legacy selftest **ALL PASS**, and compileall/launcher py_compile/packaging shell syntax **PASS**. A first command that chained all suites hit the execution-tool timeout after full pytest reached ~82%; that interrupted run is not counted as PASS. The same candidate full suite was then rerun alone and completed cleanly (**168 passed / 7 skipped in 22.90s**).

**Historical NEXT (Release 33):** rebuild and independently verify the formal Release 33 FULL ZIP, then execute the available Q-1 live gates and perform another roadmap/qualification review.

> **Current continuation pointer:** use **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`) as the active full-source baseline. Preserve `IMPLEMENTED_TESTING_DEFERRED`. MC-1 through MC-3 are implemented in source; the next roadmap slice is **MC-4 / Release 52 — Unified Alert Plane**. Sensor generation/history and Sensor→Event normalization must not add device I/O; unchanged Sensor refreshes create no event, and missing evidence remains `UNKNOWN` rather than an automatic critical verdict. Formal RPM qualification remains deferred until the roadmap is complete.

Status vocabulary for new work: `PLANNED`, `IMPLEMENTED_TESTING_DEFERRED`, `TESTED`, `RELEASED`. Older `IMPLEMENTED` labels predate this vocabulary and should not be interpreted as live-environment qualification.

## Current execution roadmap summary

Only the status vocabulary `PLANNED`, `IMPLEMENTED_TESTING_DEFERRED`, `TESTED`, and `RELEASED` is authoritative for current work. Historical prose later in this file is retained only for provenance.

- **Monitoring Correlation MC-1 / Release 49 — Sensor Integration Unification:** `IMPLEMENTED_TESTING_DEFERRED` — canonical Sensor snapshot drives API/WebUI health without request-time device I/O.
- **Monitoring Correlation MC-2 / Release 50 — Sensor History & State Transitions:** `IMPLEMENTED_TESTING_DEFERRED` — durable observations/transitions, threshold-aware state changes, UNKNOWN evidence semantics, restart-safe transition suppression, 30-day observation/180-day transition retention, read-only history APIs, and device transition timeline implemented in source.
- **Monitoring Correlation MC-3 / Release 51 — Normalized Operational Evidence:** `IMPLEMENTED_TESTING_DEFERRED` — normalized cross-domain event envelope, additive event-schema migration/backfill, durable Sensor-transition → Event bridge, recovery/UNKNOWN semantics, filtered/detail Event APIs, and Event detail UI with related Sensor state implemented in source.
- **Monitoring Correlation MC-4 / Release 52 — Unified Alert Plane:** `PLANNED`.
- **Diagnostics D.5:** `IMPLEMENTED_TESTING_DEFERRED` — feature-complete in source.
- **Network Intelligence NI-1 through NI-4:** `IMPLEMENTED_TESTING_DEFERRED` — complete in source; representative live-device/service qualification remains outstanding.
- **Platform Hardening PH-1:** `IMPLEMENTED_TESTING_DEFERRED` — Web-console structural hardening complete in source.
- **Platform Hardening PH-2:** `IMPLEMENTED_TESTING_DEFERRED` — PostgreSQL core/distributed operation complete in source, with real service-backed qualification debt.
- **Platform Hardening PH-3:** `IMPLEMENTED_TESTING_DEFERRED` — bounded NETCONF/RESTCONF/gNMI structured adapters complete in source, with real vendor/TLS interoperability debt.
- **Platform Hardening PH-4:** `IMPLEMENTED_TESTING_DEFERRED` — structured configuration transactions complete in source.
- **Network Intelligence NI-5:** `IMPLEMENTED_TESTING_DEFERRED` — bounded streaming telemetry/time-series foundation complete in source.
- **Network Intelligence NI-6:** `IMPLEMENTED_TESTING_DEFERRED` — analytics, durable insights/jobs, Capacity/Failure Risk/Impact/Health and Network Intelligence operator workflow complete in source; live calibration/device/scale qualification remains deferred.
- **Vendor Models VM-1:** `IMPLEMENTED_TESTING_DEFERRED` — validated vendor/model packs and device bindings complete in source.
- **Network Automation NA-1:** `IMPLEMENTED_TESTING_DEFERRED` — desired-state lifecycle and compensating rollback complete in source.
- **Network Automation NA-2:** `IMPLEMENTED_TESTING_DEFERRED` — fleet campaign/canary/wave orchestration complete in source.
- **HA-1:** `IMPLEMENTED_TESTING_DEFERRED` — control-plane drain/readiness/recovery foundation complete in source.
- **Qualification Q-1:** `IMPLEMENTED_TESTING_DEFERRED` — production/runtime qualification track remains open; real PostgreSQL, AlmaLinux RPM/systemd, Ruff/mypy and other service-backed gates are not yet all executed in this environment.

Session idle/absolute expiry remains explicitly deferred security debt and is not part of Q-1. No Q-2 is assigned.

### Q-1 — Production Runtime & Service-backed Qualification — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source:

- release/version truth reconciled: Python package/project Version `2.0.0`, active RPM source Release `39`;
- configuration-aware `netconfig qualify` runtime preflight for active storage and required external executables;
- controlled PostgreSQL core backup using atomic custom-format `pg_dump`, SHA-256 sidecar, mode-0600 output and non-interactive authentication;
- controlled PostgreSQL restore drill requiring SHA-256 verification, explicit `RESTORE_DATABASE` confirmation, and a target database different from the active core database;
- PostgreSQL client passwords are delivered only through a short-lived mode-0600 `PGPASSFILE`, never argv; configured libpq SSL mode is preserved;
- recovery-safe restore CLI path does not require opening the active core database before restoring a separate drill/standby target;
- real PostgreSQL service-backed tests for two-node `FOR UPDATE SKIP LOCKED` claim exclusivity, advisory-lock leadership/release on session loss, node heartbeat visibility, SQLite-to-PostgreSQL migration/sequence repair, and pg_dump/pg_restore recovery drill;
- GitHub Actions integration tier now provisions PostgreSQL client tools and executes the Q-1 PostgreSQL live gates when CI runs;
- AlmaLinux 10 qualification harness separates non-mutating RPM build/inspection from explicit disposable-host `--install`; install requires `NETCONFIG_Q1_ALLOW_INSTALL=1`;
- RPM build no longer incorrectly invokes installed-RPM smoke before installation; installed smoke now runs the Q-1 runtime preflight and checks systemd hardening;
- backup systemd unit hardened to the same filesystem/process baseline as the Web service and documents the pre-vault PostgreSQL systemd credential;
- source qualification harness fails closed when Ruff/mypy are absent instead of reporting skipped tooling as success.

Historical Release 39 environment evidence:

- Q-1 focused offline tests: **12 passed**;
- full offline repository: **206 passed / 7 skipped / 0 failed** before final Release 39 packaging;
- the seven skips are four PostgreSQL live/backup-restore gates plus three OpenSSH/Net-SNMP protocol-service gates;
- Git index executable modes: **8/8 = 100755 PASS**;
- staged installed-filesystem systemd unit verification: **PASS**;
- runtime preflight on this Debian artifact runner: **NOT READY** because required `ssh` is absent; SQLite storage/openssl/Python checks pass and gNMI is not required when disabled;
- Ruff/mypy source gate: `NOT_RUN` / exit `2` because the pinned tools are absent and this isolated environment cannot resolve/download packages;
- PostgreSQL service-backed Q-1 gate: `NOT_RUN` / exit `2` because `pg_dump`/PostgreSQL service tooling is absent;
- AlmaLinux RPM qualification harness: `NOT_RUN` / exit `20` because the current host is Debian 13, not AlmaLinux 10. CI now contains an AlmaLinux 10 build/static qualification job, but it is not PASS until that workflow actually runs.

Q-1 remains `IMPLEMENTED_TESTING_DEFERRED`. It must not be promoted until the applicable live gates are actually executed and recorded. After Q-1 qualification, perform a new roadmap review; do not invent Q-2 automatically.

## Current execution roadmap

The lettered Slice A-G sequence below was created for the 2026-09-07 handover as a prioritization aid. It is no longer the primary execution numbering. Current development follows named tracks and numbered track phases; the historical mapping is retained later for provenance.

**Numbering clarification:** D.5 is the standalone Diagnostics Track, not Slice E. Network Intelligence is the active product-development track. The historical Slice B work is being implemented as explicit Network Intelligence phases so completed scope is not overstated.

### Historical current — Network Intelligence Phase NI-1: VLAN-aware Endpoint Attachment Correlation — IMPLEMENTED_TESTING_DEFERRED

- Added IP-MIB `ipNetToPhysicalTable` IPv4/IPv6 neighbour collection with explicit legacy `ipNetToMediaTable` fallback provenance.
- Added Q-BRIDGE-MIB FDB collection with `dot1qVlanFdbId` mapping and bridge-port -> ifIndex resolution. VLAN is reported only when FDB-ID -> VLAN mapping is unique; shared-learning ambiguity is never guessed.
- Added additive `ip_neighbors` and `vlan_fdb` evidence tables while preserving legacy ARP/MAC views for compatibility.
- Added fleet correlation for `IP -> MAC -> VLAN -> switch/port` with evidence freshness, explicit `ATTACHED`/`AMBIGUOUS`/`TRANSIT_ONLY`/`STALE`/`UNRESOLVED` states, and confidence labels.
- LLDP/CDP-facing ports are classified as transit observations, so MACs learned on uplinks are not silently promoted to direct endpoint attachments.
- Added `endpoint:read`, `GET /api/v1/endpoints`, `netconfig endpoints`, and an authenticated Endpoints Web page.
- Offline regression: **75 passed / 3 skipped**; NI-1 focused tests: **8 passed** before final packaging; final artifact-level evidence is recorded in `TESTING.md`.
- RPM source metadata is `2.0.0-25`; no RPM build/install or representative vendor qualification is claimed.

### Historical next at that point — Network Intelligence Phase NI-2: Topology Identity & Downstream Impact — PLANNED

- Enrich topology identity with chassis-ID subtype normalization, chassis MAC, serial/system identity and LLDP system capabilities where evidence exists.
- Resolve interface identity more robustly across LLDP local-port descriptions, ifIndex/ifName/ifDescr and vendor naming variants.
- Build deterministic downstream attachment/impact traversal over managed topology edges without treating inferred identity as authoritative fact.
- Preserve explicit ambiguity and source provenance; do not collapse conflicting observations.


### Markdown-state synchronization note — 2026-09-11

Historical synchronization note: at that checkpoint the project had moved to NI-3/NI-4 planning. The current canonical header and NI-4 section below supersede it; D.5 entries remain implementation history. Current source RPM Release is `2.0.0-28`.

## Diagnostics Track

This feature track is complete in source; external qualification remains outstanding.

- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4B — Incident Timeline.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4C — Support Case Export.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4D — Evidence / manifest signing and verification trust model.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4E — bounded, secret-safe protocol trace capture for CLI/OpenSSH and SNMP, with future structured-provider schema.
- **IMPLEMENTED_TESTING_DEFERRED:** D.5 Phase 4F — Incident Web Console unifying lifecycle, timeline, evidence, traces, bundles and signed support-case workflow.
- **COMPLETED-IN-SOURCE — IMPLEMENTED_TESTING_DEFERRED:** D.5 closeout — opt-in bounded retention/scheduler controls implemented; offline qualification is green, while external CI/service/RPM/live-device gates remain deferred. D.5 is not the active feature track.
- **FEATURE TRACK COMPLETE:** No additional D.5 feature phase is planned before external qualification evidence. The next product-development track is VLAN-aware endpoint/topology correlation.

## Network Intelligence Track

The Network Intelligence track is complete in source through NI-4. All phases remain `IMPLEMENTED_TESTING_DEFERRED` until representative live-device/service qualification is executed.

### NI-1 — VLAN-aware Endpoint Attachment Correlation — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: IP-MIB IPv4/IPv6 neighbour collection, Q-BRIDGE VLAN-aware FDB/FDB-ID resolution, bridge-port→ifIndex mapping, conservative IP→MAC→VLAN→switch→port correlation, transit suppression, staleness/ambiguity handling, and CLI/API/Web visibility.

### NI-2 — Topology Identity & Downstream Impact — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: normalized LLDP/ENTITY-MIB/IF-MIB/chassis identity, managed-neighbour resolution with ambiguity fail-closed behavior, and bounded cycle-safe managed L2 downstream traversal.

### NI-3 — SNMP Traps & Dependency-aware Events — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: bounded SNMP v1/v2c Trap ingestion, normalized operational events, deduplication, targeted re-poll debounce, unified syslog/SNMP event stream, and NI-2 topology-aware temporary suppression. SNMPv3 Trap authentication/privacy and INFORM acknowledgement remain fail-closed/deferred.

### NI-4 — Operational Alert & Reporting Lifecycle — `IMPLEMENTED_TESTING_DEFERRED`

Implemented: OPEN/ACKNOWLEDGED/RESOLVED operational alerts, maintenance windows, suppression provenance, durable notification queue with bounded retry/backoff, scheduled operational reports, and role-gated CLI/API/Web workflows. Notifications/lifecycle schedulers remain disabled by default unless explicitly configured.

## Platform Hardening Track

Historical A-G labels are provenance only. The canonical execution line is PH-1 → PH-2 → PH-3.

### PH-1 — Web-console Structural Hardening — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source: API/UI helper extraction, reduced `web.py`, per-response CSP nonces, `script-src-attr 'none'`, `style-src-attr 'none'`, inline-handler removal, style normalization, and script-context escaping regression coverage. Session idle/absolute expiry remains explicitly deferred.

### PH-2 — PostgreSQL Core & Distributed Operation — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source: explicit fail-closed PostgreSQL core backend, schema bootstrap/translation, sequence repair, cluster heartbeat, durable distributed tasks, PostgreSQL `FOR UPDATE SKIP LOCKED`, scheduler advisory locks, readiness/status, protected pre-vault database credentials, and SQLite→PostgreSQL migration tooling. SQLite remains single-node.

### PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters — `IMPLEMENTED_TESTING_DEFERRED`

Implemented in source:

- NETCONF server hello/capability negotiation, fixed bounded `<get>` and `<get-config>` reads, advertised datastore awareness, confirmed-commit/rollback capability reporting, timeout/size limits, and DTD/entity-rejecting XML parsing. Base-1.1-only chunked framing remains deferred.
- RESTCONF HTTPS discovery, strict host/path/query validation, mandatory TLS verification unless an explicit lab-only environment override is set, CA-bundle support, vault-resolved mTLS material, bounded JSON/XML reads, and an internal approval-gated JSON subtree replace primitive with pre-read, post-read verification, and best-effort pre-image rollback. No generic URL/method/body passthrough is exposed through Web/API/CLI.
- gNMI Capabilities, Get, bounded ONCE Subscribe, typed paths, TLS/mTLS-capable runtime configuration, deadline/size enforcement, mode-0600 ephemeral credential config, and secret-free argv. gNMI Set remains deliberately unexposed.
- common fail-closed structured collection, explicit CLI fallback only, runtime vault credential resolution, durable audit/provenance, and metadata-only protocol trace evidence.

Offline evidence before final artifact packaging: **136 passed / 3 skipped**, focused PH-3 **22 passed**. The three skips are the existing service-backed OpenSSH, Net-SNMP, and PostgreSQL tests.

### After PH-3 — Qualification Track Q-1

The required roadmap review selected **Q-1 — Production Runtime & Service-backed Qualification**. Q-1 is implemented in source and currently `IMPLEMENTED_TESTING_DEFERRED`; its remaining live gates are listed in the canonical Q-1 section above. No Q-2 is assigned.

## Historical 2026-09-07 lettered handover mapping

The old A-G labels are retained only to interpret historical handover notes and patch entries; they are not the current execution sequence.
D.5 and Slice E are distinct historical entries: D.5 maps to Diagnostics; Slice E maps only to Platform Hardening / Web-console structural hardening.

| Historical label | Current track/location |
| --- | --- |
| Slice A — Qualification/release gates | Platform Hardening Track -> Qualification and release gate closure |
| Slice B — VLAN-aware endpoint/topology | Network Intelligence Track -> VLAN-aware endpoint and topology correlation |
| Slice C — SNMP traps/events | Network Intelligence Track -> SNMP traps and dependency-aware events |
| Slice D — Alert/reporting lifecycle | Network Intelligence Track -> Alert and reporting lifecycle |
| Slice D.5 — Diagnostics | Diagnostics Track |
| Slice E — Web-console hardening | Platform Hardening Track -> Web-console structural hardening |
| Slice F — PostgreSQL/distributed operation | Platform Hardening Track -> PostgreSQL core and distributed operation |
| Slice G — NETCONF/RESTCONF/gNMI | Platform Hardening Track -> Structured network protocols |

## Slice D.5 — Diagnostic & Support Bundle Framework
Status: IMPLEMENTED_TESTING_DEFERRED

Implemented initial diagnostic bundle foundation: redacted support bundle generation, manifest/checksum metadata, security redaction report, and CLI entry point (`netconfig debug collect`). Deferred: production archive retention policy, Web UI workflow, device-specific captures, and full incident bundle integration.


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


## Slice D.5 Phase 3C — Diagnostics Web Console + Secure Download (2026-09-10)

Status: IMPLEMENTED_TESTING_DEFERRED

- Added the authenticated Diagnostics console for support-bundle list/create/download workflow.
- Added CSRF-protected browser bundle creation and traversal-safe managed-bundle download with audit evidence.
- API download authorization, incident correlation, signing and protocol traces remained later work at this point.


## D.5 Phase 3D — Enterprise Diagnostic Operations

Status: IMPLEMENTED_TESTING_DEFERRED

Added secure debug bundle download API foundation, debug:download scope, RBAC/audit integration. Deferred: incident workflow, signed manifests, retention scheduler UI.


## Slice D.5 Phase 4A — Incident Model Foundation (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added durable `incidents` and `incident_bundles` state with additive SQLite schema creation.
- Added human-readable `INC-YYYY-NNNNNN` IDs, LOW/MEDIUM/HIGH/CRITICAL severity, OPEN/INVESTIGATING/RESOLVED/CLOSED lifecycle, bounded title/description/tags, update metadata, closure metadata, and explicit reopen semantics.
- Added audited CLI create/list/show/update/status/link-bundle/unlink-bundle operations.
- Added scoped JSON API foundation: `incident:read` and operator-or-higher `incident:write`, including create, read, status transition, and diagnostic-bundle link operations.
- Repaired the Phase 3D scope registry so `debug:download` and `debug:admin` are actually creatable by the API-token CLI.
- Kept incident timeline/event correlation, case export, signed manifests, protocol traces, and Incident Web UI out of 4A; those remain Phase 4B+ work.
- Console session idle/absolute expiry remains deliberately deferred and unchanged.

At Phase 4A completion, the next phase was **D.5 Phase 4B — Incident Timeline**; it is now implemented below.


## Slice D.5 Phase 4B — Incident Timeline (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added additive `incident_evidence_links` reference table; it stores only incident/source pointers and bounded link metadata, never copied syslog/audit/compliance/config payloads.
- Added evidence sources: `audit`, `syslog`, `collection`, `compliance`, and immutable `drift` references. Existing incident-bundle links and incident-native audit events are rendered into the same timeline.
- Drift evidence pins the baseline/current archived configuration stamps at link time so later collection cannot rewrite the historical comparison.
- Timeline dereferences authoritative records at read time. Retained links whose source has later been pruned/deleted remain visible as unavailable references instead of silently disappearing.
- Added CLI evidence/timeline operations and scoped REST timeline/evidence endpoints under the existing `incident:read` / operator-or-higher `incident:write` boundary.
- Case export, evidence signing, protocol trace capture, and Incident Web UI remain separate Phase 4C+ work. Console session idle/absolute expiry remains deliberately deferred.

At Phase 4B completion, the next phase was **D.5 Phase 4C — Support Case Export**; it is now implemented below.


## Slice D.5 Phase 4C — Support Case Export (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added managed `case-exports/` storage and additive `incident_case_exports` metadata with export key, filename, creator/time, reason, included/missing bundle indexes, archive size and SHA-256.
- Added bounded case-package generation containing `case.json`, `evidence-links.json`, `timeline-references.json`, selected linked diagnostic bundles, `README.txt`, `manifest.json`, and `manifest.sha256`.
- External audit/syslog/compliance/config bodies are not exported into case indexes. Timeline output is reduced to provenance/reference fields; diagnostic bundles are embedded as opaque byte-for-byte files rather than extracted or rewritten.
- Added dedicated `incident:export` bearer scope requiring operator-or-higher role, plus CLI `incident export-case|exports` and REST create/list/download workflow.
- Export creation/download is audited against the Incident. Explicitly requested unlinked/missing bundles fail closed; default exports preserve missing linked bundles as metadata instead of fabricating replacement evidence.
- Case export limits are 32 bundles / 512 MiB aggregate diagnostic-bundle input. Free-text case metadata applies credential-assignment redaction before export.
- At Phase 4C completion, SHA-256 integrity was implemented while cryptographic authenticity remained for Phase 4D; Phase 4D is now implemented below. Protocol trace capture remains Phase 4E and Incident Web Console remains Phase 4F.
- Console session idle/absolute expiry remains deliberately deferred and unchanged.

Historical Phase 4C next step was **D.5 Phase 4D — Evidence / Manifest Signing**; that phase is now implemented below.


## Slice D.5 Phase 4D — Evidence / Manifest Signing (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added fixed-function Ed25519 signing through the system OpenSSL binary without adding a Python crypto dependency or exposing a generic shell/signer command surface.
- Private signing keys remain external to NetConfig state. Resolution prefers systemd `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem`, then `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE`; key files must be regular non-symlink files with no group/world permission bits.
- Diagnostic bundles and support-case exports auto-sign when a valid signer is configured. `--require-signature`, `NETCONFIG_EVIDENCE_SIGNING_REQUIRED=1`, or the corresponding setting makes creation fail closed if signing is unavailable.
- Signed archives include the public key and signature metadata, while the private key is never embedded. Verification recomputes the manifest SHA-256 and every payload size/hash before validating the Ed25519 signature.
- Authentication trust is independent of the embedded key: SHA-256 SPKI fingerprint pins may be supplied by CLI, settings, or `NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS`; multiple pins support planned key rotation.
- Support-case export records persist signature state/algorithm/fingerprint via additive SQLite columns. Existing Phase 4C unsigned records remain compatible.
- Added CLI `incident verify-export`, `debug verify`, `debug signing-status`, API case-export verify and debug signing/verify surfaces, plus audit evidence for verification and signature failures.
- Signed case download still enforces the durable outer archive size/SHA-256 and additionally verifies the inner signature; configured trust pins fail closed on signer mismatch.
- Phase 4E protocol trace capture and Phase 4F Incident Web Console remain separate. Session idle/absolute expiry remains deliberately deferred.

Next: **D.5 Phase 4E — Protocol Trace Capture**.


## Slice D.5 Phase 4E — Protocol Trace Capture (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added additive `protocol_trace_sessions` and `protocol_trace_events` tables with explicit TTL, status, event budget and metadata-byte budget.
- Implemented `ProtocolTraceStore` with explicit start/stop/list/events lifecycle, audit evidence and optional automatic Incident evidence linkage.
- CLI/OpenSSH capture records connect/command metadata, result, duration and byte counts only. Sensitive commands are replaced by a constant marker before persistence; raw command secrets and terminal output are not trace evidence.
- SNMP capture is context-local and records target/port/attempt, duration and request/response byte counts at the UDP exchange boundary without recording BER packet bodies, community strings or v3 secrets.
- Incident timeline can resolve `protocol_trace` evidence; case exports include sanitized `protocol-traces.json`; diagnostic support bundles include bounded recent trace metadata.
- Added CLI `trace start|list|show|events|stop` and REST `/api/v1/traces` read/capture lifecycle using `trace:read` and role-gated `trace:capture`.
- Historical Phase 4E trace schema anticipated NETCONF/RESTCONF. PH-3 now implements NETCONF/RESTCONF/gNMI metadata trace providers while retaining the same evidence budgets.
- Offline regression: **59 passed / 3 skipped**; Phase 4E focused tests: **10 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**. Ruff/mypy remain NOT RUN in this environment.

Next: **D.5 Phase 4F — Incident Web Console**.


## Slice D.5 Phase 4F — Incident Web Console (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added `/incidents` register/filter UI and `/incident?ref=...` detail UI to the authenticated console.
- Viewer is read-only. Operator/approver/admin can create/edit Incidents, execute server-validated lifecycle transitions, link/unlink diagnostic bundles and reference-only evidence, and start/stop bounded CLI/SNMP traces.
- The detail view unifies Incident metadata, Phase 4B timeline/evidence, Phase 4E trace session/events, diagnostic bundles, and Phase 4C/4D support-case create/verify/download operations.
- All browser mutations retain CSRF checks. Case downloads call the existing integrity/signature verification path before chunked streaming.
- Rendering escapes Incident-controlled title/description/tags/evidence text. Cross-Incident trace stop is rejected.
- No new database schema or parallel Incident data model was introduced. Existing Incident/trace/export services remain authoritative.
- Offline regression after implementation: **64 passed / 3 skipped**; Phase 4F focused Web Console tests: **5 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell checks **PASS**.

Next: **D.5 Closeout / Diagnostic Qualification Review**.


## D.5 Closeout / Diagnostic Qualification Review (2026-09-11)

Status: **IMPLEMENTED_TESTING_DEFERRED**

- Added `diagnostic_maintenance.py` and opt-in background scheduling (`diagnostic_maintenance_interval`, default `0`).
- Added `debug_bundle_keep` (default `10`), `case_export_retention_days` (default `0`), and `protocol_trace_retention_days` (default `0`).
- Case-export cleanup preserves durable export metadata so Incident history shows an unavailable historical export instead of erasing the record.
- Protocol-trace cleanup is intentionally limited to inactive traces with no Incident linkage; Incident evidence is not automatically destroyed by generic retention.
- Added `netconfig debug maintenance` for explicit one-shot maintenance and Monitoring settings for the scheduler/policies.
- Offline closeout result: **67 passed / 3 skipped**, focused closeout **3 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**, CR offenders **0**.
- Ruff/mypy, service-backed OpenSSH/Net-SNMP/PostgreSQL integration, AlmaLinux RPM build/install/systemd runtime, and representative live-device qualification remain **NOT RUN / DEFERRED** in this environment. Therefore D.5 remains `IMPLEMENTED_TESTING_DEFERRED`; feature completion is not equivalent to release qualification.
- Next product-development track: **VLAN-aware endpoint and topology correlation**.

## Network Intelligence progression update — 2026-09-11

### Historical current — NI-2: Topology Identity & Downstream Impact — IMPLEMENTED_TESTING_DEFERRED
- Normalize local LLDP chassis identity, ENTITY-MIB chassis serial/model/name and IF-MIB ifName/ifDescr/ifAlias/physical-address evidence.
- Resolve managed neighbours only when normalized identity evidence uniquely identifies one inventory device; contradictory/non-unique evidence remains `AMBIGUOUS`.
- Provide bounded, cycle-safe downstream traversal over resolved managed L2 adjacency, with optional first-hop root-port scoping in CLI/Web.
- Expose normalized identity and impact through CLI, `topology:read` REST endpoints, and the Topology Web console.
- Offline regression: **83 passed / 3 skipped**; focused NI-2 **8 passed** before final packaging. RPM source metadata: `2.0.0-26`.

### Historical next at that point — NI-3: SNMP Traps & Dependency-aware Events — PLANNED
- Bounded trap receiver for linkDown/linkUp, coldStart/warmStart and authenticationFailure.
- Strict source/device correlation, deduplication and debounce.
- Trigger targeted re-polls rather than fleet-wide polling.
- Merge trap, syslog and poll evidence into one operational event timeline.
- Use resolved topology identity/adjacency for dependency-aware downstream suppression while preserving ambiguity/fail-closed behavior.

## Network Intelligence NI-3 — SNMP Traps & Dependency-aware Events

### Historical current — NI-3 — IMPLEMENTED_TESTING_DEFERRED
- bounded UDP SNMP v1/v2c Trap receiver; default non-privileged port 5162 with external udp/162 forwarding when required
- SNMPv3 traps fail closed until an authenticated USM receiver is implemented; INFORM fails closed because acknowledgements are not implemented
- normalized coldStart/warmStart/linkDown/linkUp/authFailure plus enterprise trap OID preservation
- durable unified operational event stream for traps, syslog and SNMP reachability transitions
- bounded deduplication, targeted SNMP re-poll debounce, dependency suppression TTL
- suppression follows only NI-2 resolved managed-L2 adjacency and never ambiguous/unmanaged edges
- CLI `netconfig events`, Web Events page, and `GET /api/v1/events` with `events:read`
- offline evidence: **91 passed / 3 skipped**; focused NI-3 **8 passed** before packaging
- RPM source metadata: `2.0.0-27`; live Net-SNMP/vendor/RPM qualification remains deferred

### Historical next at that point — NI-4: Operational Alert & Reporting Lifecycle — PLANNED
- acknowledgement/resolution lifecycle, maintenance windows, notification retry/backoff, scheduled reporting, and bounded archive/search workflows


## Network Intelligence NI-4 — Operational Alert & Reporting Lifecycle

### Historical current — NI-4 — IMPLEMENTED_TESTING_DEFERRED
- Promote unsuppressed NI-3 events at/above a configurable severity threshold into a durable operational alert lifecycle.
- Lifecycle states: `OPEN`, `ACKNOWLEDGED`, `RESOLVED`; acknowledge/resolve are role-gated and audited.
- Device-scoped or fleet-wide maintenance windows suppress alert promotion while retaining the authoritative operational event and a durable maintenance-window reference.
- Optional SMTP alert/report delivery uses a durable queue with bounded attempts and exponential backoff; notification worker is opt-in (`operational_lifecycle_interval=0` by default).
- Scheduled operational reports persist run metadata and bounded aggregate summaries over events/alerts/suppressions; no raw trap/community/secret material is copied.
- CLI `netconfig alerts`, scoped REST (`alerts:read/write`, `reports:read/write`) and authenticated `/op-alerts` Web UI are implemented.
- Existing monitor-rule alerts remain a separate compatibility subsystem; NI-4 does not silently migrate or reinterpret them.
- Offline evidence: **99 passed / 3 skipped**; focused NI-4 **8 passed**; legacy selftest **ALL PASS**.
- RPM source metadata: `2.0.0-28`; live SMTP, service-backed integration, representative vendor trap and RPM/systemd qualification remain deferred.

### Historical next at that point — Platform Hardening PH-1: Web-console Structural Hardening — PLANNED
This is the modern continuation of historical Slice E. Decompose the monolithic Web console/server routing, reduce inline UI coupling, tighten CSP-compatible rendering and preserve all existing RBAC/CSRF/API/session truth boundaries. Session idle/absolute expiry remains separately deferred unless explicitly selected.

**Network Intelligence feature track status:** NI-1 through NI-4 are complete in source. External/live qualification remains outstanding and prevents promotion to `TESTED`/`RELEASED`.

## Platform Hardening PH-1 — Web-console Structural Hardening (2026-09-11)

### Historical PH-1 completion — IMPLEMENTED_TESTING_DEFERRED

- Extracted Bearer API routing from `web.py` into `web_api.py` and UI assets/render helpers into `web_ui.py`; `web.py` is now below the PH-1 structural gate of 4,000 lines / 240 KB.
- Enforced per-response CSP nonces for first-party script/style blocks. `script-src-attr 'none'` and `style-src-attr 'none'` are enforced; rendered `style=` attributes are normalized to deterministic nonce-authorized utility classes.
- Removed HTML inline event handlers and replaced destructive-action confirmations with delegated `data-confirm` handling.
- Hardened script-context rendering for dynamic device names and removed secret-name `innerHTML` rendering.
- Existing URL paths, API contract, RBAC, CSRF, session semantics and session-expiry deferral are preserved.
- Verification: source regression **105 passed / 3 skipped**; PH-1 focused **6 passed**; legacy selftest **ALL PASS**; compileall/launcher/package shell syntax **PASS**. Live browser matrix/RPM/service-backed qualification remains deferred.

### Historical next at PH-1 completion — PH-2 PostgreSQL Core & Distributed Operation

Move additional core state behind the storage boundary only with explicit multi-process semantics; add distributed job ownership/leases, duplicate-work prevention and failover tests before any HA claim.

## Platform Hardening PH-2 — PostgreSQL Core & Distributed Operation — HISTORICAL COMPLETION

State: `IMPLEMENTED_TESTING_DEFERRED`.

Implemented in source: optional fail-closed PostgreSQL core database, cross-dialect schema bootstrap/compatibility, schema-revision readiness, protected pre-vault DB credentials, cluster node heartbeat, PostgreSQL advisory-lock singleton schedulers, durable distributed task queue with `FOR UPDATE SKIP LOCKED`, and fail-closed SQLite→PostgreSQL migration tooling. SQLite remains the default single-node development backend.

External qualification still required before `TESTED`/`RELEASED`: real PostgreSQL service and migration drill, concurrent multi-node claims, advisory-lock leader failover, HA/connection-loss behavior, backup/restore/PITR, packaged psycopg and AlmaLinux RPM/systemd deployment, and measured scale.

## Platform Hardening PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters — HISTORICAL COMPLETION

State: `IMPLEMENTED_TESTING_DEFERRED`. Historical mapping: Slice G.

PH-3 now implements the full offline structured-adapter contract described above rather than the earlier read-only MVP. Network configuration mutation remains constrained: generic NETCONF RPC, generic RESTCONF URL/method/body forwarding, and gNMI Set are not exposed. The only structured write primitive currently present is an internal approval-gated RESTCONF JSON subtree replacement with mandatory pre-read, caller-supplied post-read verification, and best-effort pre-image rollback.

Current offline evidence before final packaging: **136 passed / 3 skipped**; focused PH-3 **22 passed**. Live structured-protocol vendor validation, TLS/mTLS interoperability, service-backed PostgreSQL/OpenSSH/Net-SNMP, packaged `gnmic`, AlmaLinux RPM/systemd, Ruff/mypy, scale/failure, and backup/restore/PITR remain deferred.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

### Historical next action after PH-3 — Roadmap / Qualification Review

That review was completed on 2026-09-12 and selected **Qualification Track Q-1 — Production Runtime & Service-backed Qualification**. Q-1 is now the current track; this PH-3 next-action text is chronology only.


# Canonical Architecture Split — PH vs NI

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

Status: `IMPLEMENTED_TESTING_DEFERRED` — delivered through NA-1 / NA-2 and retained here as historical architecture naming

Scope:

- Desired state model
- Current vs desired comparison
- Drift detection
- Change plan generation
- Intent validation
- Approval workflow integration
- Remediation through PH-4 transaction engine

### PH-6 — Distributed Execution / HA

Status: `IMPLEMENTED_TESTING_DEFERRED` — delivered through HA-1 / distributed task foundations and retained here as historical architecture naming

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

Status: `IMPLEMENTED_TESTING_DEFERRED`

Scope:

- SNMP polling
- gNMI telemetry
- Streaming metrics
- Interface statistics
- CPU/memory/environment telemetry
- Time-series storage
- Trend analysis
- Performance baseline

## NI-6 — Network Analytics / Operational Intelligence

Status: `IMPLEMENTED_TESTING_DEFERRED`

Implemented milestones:

- NI-6.1 Analytics Engine Foundation — `IMPLEMENTED_TESTING_DEFERRED`
- NI-6.2 Insight Model — `IMPLEMENTED_TESTING_DEFERRED`
- NI-6.3 Capacity Analytics — `IMPLEMENTED_TESTING_DEFERRED`
- NI-6.4 Failure Risk Foundation — `IMPLEMENTED_TESTING_DEFERRED`
- NI-6.5 Impact Simulation — `IMPLEMENTED_TESTING_DEFERRED`
- NI-6.6 Health Dashboard — `IMPLEMENTED_TESTING_DEFERRED`
- NI-6 Enterprise Operations & Qualification Hardening — `IMPLEMENTED_TESTING_DEFERRED`

Enterprise operations hardening adds durable `network_insights` / `analytics_jobs`, Manager → API → UI integration, `analytics:read` / `analytics:write` RBAC scopes, insight acknowledgement/resolution/expiry, filter/search, affected-object/evidence drill-down, managed directional impact simulation, and the Operations → Network Intelligence dashboard. Analytics remains evidence-only and does not execute remediation; configuration action must use the existing approved Structured Changes / Desired State / Campaign plane.

Offline source evidence after hardening: **204 passed / 7 skipped / 0 failed**, selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Q-1/Ruff and live PostgreSQL/protocol/vendor/scale gates remain `NOT_RUN`/deferred.

Scope retained for future expansion after Release 40: production threshold calibration, richer routing-table/FIB ingestion, and live scale/vendor qualification. L3/VRF path analytics and route-dependency simulation are implemented by NI-7.

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


## Release 37 — RPM Installation Hardening — `IMPLEMENTED_TESTING_DEFERRED`

At the historical Release 37 checkpoint, the package identity was `2.0.0-37`, aligned with that NI-6 source baseline. Canonical production installation targets AlmaLinux 10 and uses the RPM lifecycle (`build-rpm.sh` -> `inspect-rpm.sh` -> `install-rpm.sh` -> explicit first-admin bootstrap -> systemd enable/start -> installed smoke). Source-side regression and packaging-script checks pass; the real AlmaLinux 10 RPM build/install/restart gate remains `NOT_RUN` until executed on suitable infrastructure.

## 2026-09-23 — R51-HF1 pre-MC4 compatibility overlay

Status remains `IMPLEMENTED_TESTING_DEFERRED`. This overlay does not advance the roadmap release: MC-4 / Release 52 remains `PLANNED`.

Implemented before MC-4: Net-SNMP-compatible standard SNMPv3 AES-192/AES-256 key extension with explicit Cisco/Reeder compatibility modes; same-process Vault unlock for topology discovery; topology graph nodes for every managed inventory device even without LLDP/CDP; persisted FDB/MAC evidence as non-authoritative `INFERRED` paths; and an interactive drag/pan/zoom Topology Web canvas whose layout is browser-local presentation state only. Graph/API/UI reuse persisted evidence and add no device I/O. Live FortiGate/vendor qualification remains deferred.
