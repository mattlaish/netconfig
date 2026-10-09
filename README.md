# NetConfig

## Current baseline — R67.2 corrective RC

> **2026-09-29 development update — SNMP Vendor Profile framework:** this working tree adds a data-only, hot-reloadable SNMP Vendor Profile engine on top of the refrozen R67.2 source line. This is a runtime/package payload change, so the previously frozen R67.2 exact-candidate fingerprint and candidate-bound `LIVE_RC` evidence do **not** qualify this working tree. The release identity has intentionally **not** been advanced; that remains an explicit user decision. Project state remains `IMPLEMENTED_TESTING_DEFERRED`; MC-11 remains the final Monitoring / Correlation / Change-Planning feature slice; no MC-12 and no new network-write authority are introduced. Profiles are JSON data, validated fail-closed, bounded to declared numeric OID roots, and cannot execute Python, shell, commands, URLs, or arbitrary expressions.

**Current vendor-profile source evidence:** **556 collected / 542 PASS / 14 SKIP / 0 FAIL** across 12 bounded groups; focused Vendor Profile framework coverage is **8 PASS / 0 FAIL**; `compileall`, actual launcher `py_compile`, packaging/tool/qualification shell syntax, release-metadata check, and legacy selftest are PASS. The 14 skips remain explicit live PostgreSQL/protocol-service prerequisites plus the expected source-archive Git-metadata prerequisite. These are local/source gates only and do not promote the working tree beyond `IMPLEMENTED_TESTING_DEFERRED`.

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

R67.2 supersedes R67.1 as the active corrective candidate after fresh-install and live-rescue findings. It restores fresh login, fixes additive migration/index ordering, fails closed before persisting a Core PostgreSQL switch, separates Core and Interface History PostgreSQL configuration, and adds a resumable fresh PostgreSQL Core bootstrap. See `R67_2_FRESH_DATABASE_BOOTSTRAP_HARDENING.md`.

Historical release sections below preserve implementation/evidence lineage; they are not current-state declarations.

## Release 59 — MC-11 Topology-Aware Change Planning

Release 59 closes the Monitoring & Correlation functional roadmap with a persisted, fail-closed planning layer. Operators can resolve source/destination devices or uniquely attached endpoints, evaluate forward and return NI-7 L3/VRF paths, combine MC-6 service/dependency context with ACL/firewall/NAT/PBR/routing-policy evidence, identify explicit configuration gaps and exact evidence-backed change points, inspect `Why here?`, run candidate-state what-if, and produce schema-bounded Structured Change proposals. Planning does **not** call device collection or execution paths; `what-if` never executes; every proposed change remains subject to the existing Structured Change validation/approval authority.

**Target release truth:** `2.0.0-59` / `mc11-topology-change-planning-1` / `IMPLEMENTED_TESTING_DEFERRED`. The final source/clean-extract/package evidence is recorded after the frozen artifact gate. No MC-12 is planned; the next mainline is Q2 Production Qualification Campaign.

**Release 59 source-tree qualification:** **372 passed / 8 skipped / 0 failed** across **380 collected tests**. MC-11 focused is **12/12 PASS**. Selected compatibility coverage across MC-3→MC-11 plus NI-7 and ImpactSimulator is **112/112 PASS**. The eight skips are three live PostgreSQL tests, one PostgreSQL backup/restore test, three protocol-service integration tests, and the expected archive Git-index executable-mode gate. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The dependency-free helper RPM rebuild is deterministic and independently verified; canonical AlmaLinux 10 `rpmbuild`/DNF/systemd/SELinux qualification is `BLOCKED_ENVIRONMENT` on the current Debian 13 runner (qualification script exit 20), not PASS. Final clean-extract and frozen-artifact evidence is recorded in `ARTIFACT_MANIFEST.json` and the external artifact-gate evidence.


## Release 58 — MC-10 Correlation Production Hardening & Qualification

Release 58 hardens the MC-7 correlation engine and MC-9 operations console without changing their authority boundary. Each correlation/replay execution now has durable `correlation_runs` telemetry with deterministic input/result fingerprints, replay lineage, latency, truncation and late/out-of-order/future-clock-skew evidence. Abandoned `RUNNING` executions are recovered as `INTERRUPTED / ProcessRestart`; same-incident execution is serialized locally and the PostgreSQL path additionally uses a bounded advisory lock. Read-only replay preview is bounded to seven days and never mutates active hypotheses. Runtime retention prunes only completed run metadata, never incident evidence or hypotheses.

The self-monitoring surface reports correlation throughput/state, p50/p95/max latency, queue/inflight depth, truncation/skew counters, incident/alert/sensor/external-event rates, duplicate/reject counters and connector lag. `netconfig qualify --correlation` and the qualification API expose local checks plus explicit deferred live gates; they cannot self-promote the release. Hard bounds include 500 correlation facts, 2,000 timeline scan entries, 25 hypotheses, dependency depth 4 / 250 nodes / 1,000 edges, a 30-minute rule window, and a seven-day replay ceiling. Correlation remains non-causal and DB/evidence-only.

## Release 57 — MC-9 Operations Correlation Console

Release 57 turns the MC-4 through MC-8 evidence/correlation foundations into the primary operator-facing SOC/NOC workflow. `/dashboard` summarizes active incidents, impacted services, critical alerts, changes used by active hypotheses, unhealthy dependency evidence, and external-source health without polling devices. Incident pages surface the current hypothesis with explicit supporting and contradicting evidence and preserve the non-causal wording. `/traffic` provides global time-windowed FortiView-style top sources/destinations/protocols/ports/conversations/exporters and bucketed traffic trend over the existing bounded NetFlow ring, with endpoint attachment enrichment where available. Raw flow/evidence records remain drill-down surfaces. No database schema change is required; `mc8-external-evidence-connectors-1` remains the schema revision.

**Release 57 source-tree qualification:** **349 passed / 8 skipped / 0 failed** across **357 collected tests**, including **8/8 MC-9 focused PASS** and **83/83 MC-4 through MC-9 / Incident / Web / CSS compatibility PASS**. The eight skips are seven explicit PostgreSQL/backup/protocol-service live prerequisites plus the expected archive Git-index executable-mode gate. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The unsigned offline helper RPM is `netconfig-2.0.0-57.el10.noarch.rpm`, SHA-256 `92eb370f9d0a5b47043c526df9960e2520dee16a454ececdff0fbd0cdf53e98e`, with **96 payload files**; two independent source-tree builds are byte-identical and the independent offline verifier passes. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux, live PostgreSQL/protocol services, representative browser/load qualification, and production-scale correlation/traffic qualification remain `NOT_RUN / DEFERRED`.

**Release 57 clean-extract artifact qualification:** **349 passed / 8 skipped / 0 failed** across **357 collected tests**, with MC-9 focused **8/8 PASS**. ZIP structural verification is **223 entries**, **0 duplicates**, **0 unsafe paths**, **0 symlinks**, **223/223 source↔ZIP↔system-unzip extract byte+mode parity**, **209/209 source payload manifest**, **222/222 SHA256SUMS**, and **12/12 required executable modes = 0755**. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest pass from the extracted artifact. Two helper-RPM rebuilds from the clean extract are byte-identical to each other and to the source-tree RPM and pass the independent RPM verifier.

**Release 58 source-tree qualification:** **360 passed / 8 skipped / 0 failed** across **368 collected tests**, executed as five mutually exclusive non-live groups plus the explicit live-integration inventory. MC-10 focused is **11/11 PASS**; the earlier selected MC-3→MC-10 compatibility run is **83/83 PASS**. The eight skips are three live PostgreSQL tests, one PostgreSQL backup/restore test, three protocol-service integration tests, and the expected archive Git-index executable-mode gate. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. A real R57→R58 SQLite additive upgrade preserved the seeded Incident, External Event, and two MC-7 hypotheses while advancing the schema to `mc10-correlation-hardening-1` and creating `correlation_runs`. This is SQLite migration evidence only, not live PostgreSQL qualification. The unsigned offline helper RPM is `netconfig-2.0.0-58.el10.noarch.rpm`, SHA-256 `29ba4491d19cfe48aaf9601d6eb196f29e29b3daed3aa47f3421116f0e81a9ae`, with **97 payload files**; two independent source-tree builds are byte-identical and the independent verifier passes. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux and the MC-10 live PostgreSQL/external-product/production-scale/clock-skew/HA gates remain `NOT_RUN / DEFERRED`.

**Release 58 clean-extract artifact qualification:** provisional clean-extract verification completed with **360 passed / 8 skipped / 0 failed** across **368 collected tests**, MC-10 focused included in the full run, **226 ZIP entries**, **0 duplicates**, **0 unsafe paths**, **0 symlinks**, **226/226 source↔ZIP↔system-unzip extract byte+mode parity**, **211/211 source payload manifest**, **225/225 SHA256SUMS**, and **12/12 required executable modes = 0755**. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest pass from the extracted artifact. Two helper-RPM rebuilds from that clean extract are byte-identical to each other and to the source-tree helper RPM and pass the independent verifier. These results are re-run once more against the frozen final ZIP before delivery; the ZIP is not promoted to `TESTED` or `RELEASED`.

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Release 56 — MC-8 External Evidence Ingestion & Connectors

Release 56 adds a source-bound normalized inbound evidence plane for NDR, WAF, SIEM, EDR, APM, database, storage, virtualization and cloud monitoring evidence. External sources are registered with a unique hashed bearer token carrying `external:ingest`; source management is admin-only via `external:manage`, while `external:read` exposes health and sanitized evidence. Schema v1 is bounded and validates source-event/idempotency identity, source time, severity/domain/entity context, metadata/payload objects and clock metadata. Duplicate replay is deterministic; conflicting replay fails closed. Connector health exposes authentication failures, rate limits, schema rejections, rejected/received/duplicate counts and last-event state. Secret-looking fields are recursively redacted before persistence.

The Settings/Integrations view is evidence-only and stores no plaintext connector credential. Sanitized external payloads appear only as Advanced Incident evidence. MC-8 does not grant authority to reconfigure WAF/SIEM/EDR/APM/database/storage/cloud/network systems, execute response actions, run arbitrary commands, or bypass Structured Changes. Vendor-specific live adapters/products and production-scale ingestion qualification remain deferred.

**Release 56 source-tree qualification:** **341 passed / 8 skipped / 0 failed** across **349 collected tests**, including **12/12 MC-8 focused PASS**. The eight skips are seven explicit PostgreSQL/backup/protocol-service live prerequisites plus the expected archive Git-index mode gate. R55→R56 additive SQLite upgrade preservation, `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The unsigned offline helper RPM is `netconfig-2.0.0-56.el10.noarch.rpm`, SHA-256 `0fa3f4e877d5a6c69d56d1138341c32834f977e741ab492b63b76750611d3242`, with **94 payload files**; two independent builds are byte-identical and the independent offline verifier passes. These are local/offline qualifications only; live PostgreSQL, canonical AlmaLinux DNF/systemd/SELinux, real external products/connectors, and production-scale ingest/concurrency/restart qualification remain `NOT_RUN / DEFERRED`.

**Release 56 clean-extract artifact qualification:** **341 passed / 8 skipped / 0 failed** across **349 collected tests**, with MC-8 focused **12/12 PASS**. The clean-extract ZIP structure gate is **219 entries**, **0 duplicates**, **0 unsafe paths**, **0 symlinks**, **219/219 source↔ZIP↔extract byte+mode parity**, **206/206 source payload manifest**, **218/218 SHA256SUMS**, and **12/12 required executable modes = 0755**. `compileall`, launcher `py_compile`, packaging/tool shell syntax and legacy selftest pass from the extracted artifact. Rebuilding the helper RPM from the clean extract is byte-identical to the source-tree RPM and passes the independent verifier.

## Release 55 — MC-7 Deterministic Correlation & Hypothesis Engine

Release 55 adds a bounded, deterministic correlation layer over the durable Incident evidence introduced by MC-5 and the trusted dependency context introduced by MC-6. `netconfig/correlation.py` evaluates incident-linked `sensor_transition`, `operational_event`, `operational_alert`, `change_event`, `analytics_insight`, and `external_event` references using versioned rules. Time proximity alone never establishes a relationship: evidence must share an entity or be connected through active `CONFIGURED` or fresh `DISCOVERED` MC-6 dependency evidence. `INFERRED`, `UNKNOWN`, stale, ambiguous, or untrusted dependency evidence is excluded from normal correlation.

The first deterministic rule families are `RECENT_CONFIGURATION_CHANGE`, `NETWORK_PATH_DEGRADATION`, and `RELATED_ENTITY_DEGRADATION`. Every persisted hypothesis records its rule/version, deterministic evidence fingerprint, initiating evidence, affected entities, supporting evidence, contradicting evidence, score breakdown, confidence, and evidence time range. Healthy/recovery evidence is preserved as contradiction and lowers confidence instead of being discarded. Replaying the same evidence set with the same rule version is idempotent and does not create or rewrite a hypothesis merely because correlation was run again.

Correlation remains decision support rather than configuration or root-cause authority. Hypothesis wording is deliberately non-causal (`consistent with`, `evidence supports`, `causation is not established`); the Incident investigation surface keeps `root_cause` unset and reports `NOT_CONFIRMED` when hypotheses exist. Correlation performs no SNMP/SSH/device polling, connector action, remediation, Structured Change execution, or arbitrary infrastructure write.

The Incident API adds `POST /api/v1/incidents/{ref}/correlate` for operator-or-higher users with `incident:write` and `GET /api/v1/incidents/{ref}/hypotheses` under `incident:read`. `GET /api/v1/incidents/{ref}/investigation` includes active hypotheses and a current hypothesis without converting either into a confirmed root cause. The Incident Web view shows the same evidence-backed hypothesis state and exposes **Run correlation** only to authorized writers.

**Release 55 source-tree qualification:** **329 passed / 8 skipped / 0 failed** across **337 collected tests**, including **8/8 MC-7 focused PASS**. The eight skips remain seven explicit PostgreSQL/backup/protocol-service live prerequisites plus the expected archive Git-index mode gate. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The unsigned offline helper RPM is `netconfig-2.0.0-55.el10.noarch.rpm`, SHA-256 `f52b87b73c41051a5db60cf9f0efa3b524de27490afae048efc6b0ed55fdff0e`, with **92 payload files**; two independent builds are byte-identical and the independent offline verifier passes. These are local/offline qualifications only; live PostgreSQL/service, canonical AlmaLinux DNF/systemd/SELinux, representative vendor/device, and production-scale correlation qualification remain `NOT_RUN / DEFERRED`.

**Release 55 clean-extract artifact qualification:** **329 passed / 8 skipped / 0 failed** across **337 collected tests**, with MC-7 focused **8/8 PASS**. ZIP structural verification is **215 entries**, **0 duplicates**, **0 unsafe paths**, **0 symlinks**, **215/215 source↔ZIP↔extract byte+mode parity**, **203/203 source payload manifest**, **214/214 SHA256SUMS**, and **12/12 required executable modes = 0755**. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest pass from the extracted artifact. Rebuilding the helper RPM from the clean extract is byte-identical to the source-tree build and passes the independent RPM verifier.


## Release 54.1 — MC-6 L3 Routing Topology follow-up

Release 54.1 is an additive MC-6 follow-up on the complete Release 54 service/dependency baseline. Normal CLI configuration collection reuses the authenticated session to collect driver-declared read-only interface and route evidence, publishes successful evidence generations atomically, and keeps the previous successful generation when the L3 refresh fails. Layer-3 next-hop resolution is same-VRF, freshness-aware, and fail-closed: only one fresh managed-interface match may become a managed-device edge; stale, ambiguous, cross-VRF, unresolved, and unmanaged next hops remain evidence rather than invented topology. The Topology workspace adds Physical, Layer 3, and Combined views, all rendered from persisted evidence without page-triggered polling. MC-7 correlation and R59/MC-11 topology-aware change planning remain outside this follow-up.

**Release 54.1 source-tree qualification:** **321 passed / 8 skipped / 0 failed** across **329 collected tests**. The L3 Routing Topology follow-up focused coverage is **9/9 PASS**. The eight skips are seven explicit PostgreSQL/backup/protocol-service integration prerequisites and the expected Git-index executable-mode gate because archive-derived source has no `.git`. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The unsigned offline helper RPM is `netconfig-2.0.0-54.1.el10.noarch.rpm`, SHA-256 `8e8b5acc38335026906f797a4163ff40e0679d0b8143448bdbdd39ef11cd2134`, with **91 payload files**; two independent builds are byte-identical and the independent offline verifier passes. Live AlmaLinux RPM/systemd/SELinux, PostgreSQL service-backed, protocol-service, representative vendor/device route-output, and production-scale topology qualification remain `NOT_RUN / DEFERRED`.

**Release 54.1 clean-extract artifact qualification:** **321 passed / 8 skipped / 0 failed** across **329 collected tests**, with L3 follow-up focused **9/9 PASS**. ZIP structural verification is **212 entries**, **0 duplicates**, **0 unsafe paths**, **0 symlinks**, **212/212 source↔ZIP↔extract byte+mode parity**, **201/201 source payload manifest**, **211/211 SHA256SUMS**, and **12/12 required executable modes = 0755**. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest pass from the extracted artifact. Rebuilding the helper RPM from the clean extract is byte-identical to the source-tree build and passes the independent RPM verifier.

## Release 54 — MC-6 Service & Dependency Graph

Release 54 extends NetConfig from physical/network evidence into an explicit service dependency model without treating temporal proximity as proof of production dependency. The durable model adds `service_entities` for `SERVICE`, `APPLICATION`, `DATABASE`, `STORAGE`, `LOAD_BALANCER`, `DNS`, `VM`, and `HYPERVISOR`, plus typed `service_dependencies` for `DEPENDS_ON`, `RUNS_ON`, `ROUTES_THROUGH`, `USES_DNS`, `USES_DATABASE`, `USES_STORAGE`, and `PROTECTED_BY`. Every stored dependency carries provenance, evidence state, evidence reference where applicable, observation time, freshness policy, and active state.

Dependency evidence is explicitly classified as `CONFIGURED`, `DISCOVERED`, `INFERRED`, or `UNKNOWN`. Default traversal follows configured and fresh discovered evidence only. Inferred candidates require explicit opt-in; stale discovered evidence and unknown evidence remain visible but are not traversed by default. `UNKNOWN` means insufficient evidence, not failure. Graph traversal is deterministic, cycle-safe, and bounded to hard limits of depth 8, 250 nodes, and 1,000 evidence edges.

MC-6 reuses rather than replaces existing analytics. Service dependency impact is evaluated through the existing `ImpactSimulator` while preserving service entity types/relationship names. Read-only network overlays reuse the NI-7 L3 analyzer over persisted route observations, retain VRF/destination scope, fail closed on ECMP/ambiguous/incomplete paths, and never promote next-hop IP addresses into managed devices. Rendering `/dependencies` or querying graph APIs performs no SNMP/SSH/device polling.

The REST surface uses existing `analytics:read` / role-gated `analytics:write` boundaries. The Web Console adds **Dependencies** with operator configuration forms, evidence/freshness labels, bounded traversal, and optional read-only network-path overlay. MC-6 adds no MC-7 causal hypothesis engine, no connector/action authority, and no direct infrastructure configuration path; network/application changes remain in the existing Structured Changes / Desired State / Campaign workflows.

**Release 54 source-tree qualification:** **312 passed / 8 skipped / 0 failed** across **320 collected tests**. MC-6 focused coverage is **9/9 PASS**. The eight skips are seven explicit PostgreSQL/backup/protocol-service integration prerequisites and the expected Git-index executable-mode gate because archive-derived source has no `.git`. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. Live AlmaLinux RPM/systemd/SELinux, PostgreSQL service-backed, protocol-service, representative vendor/device, and production-scale graph qualification remain `NOT_RUN / DEFERRED`.

## Release 53 — MC-5 Incident Evidence & Unified Timeline

Release 53 evolves the existing Incident object into the durable cross-domain investigation container required by the monitoring/correlation roadmap. Incidents can now link typed, validated references to `sensor_transition`, `operational_event`, `operational_alert`, `change_event`, `analytics_insight`, and `external_event` evidence in addition to the existing audit/syslog/collection/compliance/drift/protocol-trace evidence. Links snapshot source time, receive time, and bounded source-clock metadata so late-arriving evidence can be placed deterministically without copying the underlying raw payload.

A normalized durable `change_events` stream records request/approval/execution lifecycle summaries without copying configuration command bodies. A bounded `external_events` store establishes normalized MC-5 evidence semantics and source-event idempotency, but does **not** expose the MC-8 connector/ingestion plane or grant external systems configuration authority. `GET /api/v1/incidents/{ref}/investigation` and the Incident Web view group Impact, Unified Timeline, Related Alerts, Related Changes, Network Evidence, Security Evidence, Infrastructure Evidence, and Raw/Advanced Evidence. Missing retained source rows remain visible as unavailable evidence at their original timeline position. MC-5 intentionally returns no automatic root-cause verdict; service dependency reasoning remains MC-6 and deterministic hypotheses remain MC-7.

**Release 53 source-tree qualification:** **303 passed / 8 skipped / 0 failed** across 311 collected tests. The eight skips are seven explicit PostgreSQL/backup/protocol-service integration prerequisites and the expected Git-index executable-mode gate because archive-derived source has no `.git`. MC-5 focused coverage is **8/8 PASS**. `compileall`, launcher `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. Live AlmaLinux RPM/systemd/SELinux, PostgreSQL service-backed, protocol-service, and representative vendor/device qualification remain `NOT_RUN / DEFERRED`.


## Release 52 — MC-4 Unified Alert Plane

Release 52 makes the normalized operational alert lifecycle the source of truth for new monitoring alerts. HTTP/port/TLS checks now normalize into Sensors, meaningful changes become Operational Events, and one correlated `operational_alerts` lifecycle follows escalation and recovery. Existing legacy alert rows and compatibility URLs remain readable; legacy monitor rules continue to define thresholds, but the monitor poller no longer creates a second legacy alert row for the same condition.

Operator feedback is included in the same source baseline. Device Add/Edit shows the platform's effective config collection command and accepts one optional bounded read-only alternative command for devices such as firewalls whose config command differs from the generic driver. `/endpoints` now supports direct IP/MAC search and joins L3 ARP/IP-neighbor evidence to switch FDB/MAC evidence across devices before filtering, with an explicit evidence chain and no guessed port when multiple candidates remain. NetFlow is presented as traffic summaries/top talkers/destinations/protocols/ports/conversations plus deterministic observations, while raw flow records remain an Advanced drill-down. These views reuse existing evidence and do not add device I/O.

MC-4 correctness repair: R51/early-R52 alert rows with an empty `correlation_key` are backfilled from their durable Operational Event before new alert correlation runs; manually resolved alerts reopen on the next DB-only Sensor refresh if the condition is still `WARNING`/`CRITICAL`; maintenance-covered persistent Sensor evidence is re-evaluated after the window expires without fabricating a Sensor transition. Config collection now fails closed on empty/known CLI-error output instead of archiving it as configuration. `fortigate_fortios` is a native driver (aliases `fortigate`, `fortios`, `fortinet_fortigate`) using `show full-configuration` without mutating FortiGate console paging configuration. RouterOS override safety permits exact `/export` only. Endpoint combined confidence is downgraded to `PARTIAL` when matching ARP/IP-neighbor evidence exists but is stale.

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


> **Roadmap disposition — 2026-09-24:** **R59 / MC-11 is the final Monitoring & Correlation functional slice.** Do not create MC-12. After R59, stop feature expansion and use the Release / Qualification track: **Q2 Production Qualification Campaign → R60 Appliance Reliability & Lifecycle Hardening → R61 Scale & Performance Qualification → R62 PostgreSQL / Concurrency / Recovery Hardening → R63 HA / Failure-Domain Engineering → R64 Security Hardening & Independent Abuse Testing → R65 Operator Workflow Completion → R66 Observability / Supportability → R67 Release Candidate / Full Artifact Qualification → R68 v2 Production Release Decision**. Simulation never counts as live PASS; mandatory gates use `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN`.

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

Historical Release 39 evidence recorded **206 passed / 7 skipped / 0 failed**, Q-1 focused **12 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell/YAML checks **PASS**, Git index executable modes **8/8 = 100755**, and staged systemd unit verification **PASS**. This is historical evidence only: the R62.1 review found the current external/upstream Git index had regressed required entry points to `100644`, so Release 39 evidence must not be used as proof of current clone modes. The current isolated runner does not contain Ruff/mypy/PostgreSQL/OpenSSH/Net-SNMP/RPM tooling and cannot download packages. `netconfig qualify` therefore correctly fails this host's runtime readiness on the required SSH client. Ruff/mypy, PostgreSQL, protocol-service and AlmaLinux target gates remain `NOT_RUN` here; GitHub CI and disposable target environments must provide actual service-backed evidence before promotion. See `Q1_PRODUCTION_QUALIFICATION.md`.

## Historical Release 38 Git reproducibility baseline

Release 38 historically recorded a closure of the difference between ZIP/file-system executable bits and Git checkout truth. That historical baseline reported eight launcher/packaging entry points as Git mode `100755`, with CI verifying the index mode before Ruff or tests. The R62.1 review later found the current external/upstream Git index had regressed executable modes, so this paragraph is provenance rather than current-state proof. The historical fresh-clone run reproduced all eight executable bits and passed `204 passed / 7 skipped / 0 failed`, legacy selftest `ALL PASS`, compileall, launcher `py_compile`, and packaging shell syntax. Ruff is pinned to `0.16.7` in `requirements-quality.txt` and CI; this runner still records Ruff as **NOT_RUN** because the executable cannot be installed/downloaded here. Ruff and mypy are **NOT_RUN** in the current isolated runner because those tools are unavailable; this is not a PASS claim. See `GIT_REPRODUCIBILITY.md`.

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


## Release 61 — Scale & Performance Qualification

R61 adds a repeatable qualification framework rather than a new product feature slice. `qualification/r61_benchmark.py` provides isolated local synthetic comparison across inventory, endpoint/L2 data, NI-7 routes, syslog, traps, external evidence, incidents, correlation, HTTP API/dashboard and NetFlow v5 parsing. `qualification/r61_runner.py` separates `LOCAL_REGRESSION`, `LOCAL_SYNTHETIC`, and `LIVE_PRODUCTION` evidence and requires fixed hooks for production claims. MC-10 bounds remain unchanged and are explicitly probed beyond the incident timeline scan limit. Local results are not sizing guidance.

**R61 clean-extract qualification (2026-09-24):** the provisional source artifact was extracted with system `unzip` and reproduced **435 collected / 427 passed / 8 skipped / 0 failed** across the deterministic five-way bounded partition; R61 focused coverage is **17/17 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, launcher/R61 `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The clean extract rebuilt the offline helper RPM twice byte-identically; both builds are byte-identical to the source-tree RPM and pass the independent verifier. RPM SHA-256 remains `c1458d97a19ce0390f0c6f42384c652eed1704c47f57f41e11f0c95a11d2ed5b`. This is local/offline artifact evidence only and does not establish production capacity.


## Release 62.1 security and packaging hotfix

R62.1 closes the reviewed RESTCONF redirect SSRF/TLS-downgrade path by refusing all redirects before a second request, adds `--` before the OpenSSH `user@host` target, removes the reviewed dead code, and expands the upstream Git-mode repair patch to all 24 executable paths in the current CI contract. Full source regression is **458 collected / 447 passed / 11 skipped / 0 failed**; focused security/compatibility is **82 passed / 1 skipped / 0 failed**. The offline helper RPM is `2.0.0-62.1`, SHA-256 `84caef15419b339e10f3b22a8c22c9ae80b25da910bbeceea4389b566043d042`. Clean-clone Git-index `100755` is intentionally **not** claimed from an archive-only workspace; the upstream mode patch must be committed and verified from Git metadata.

## Release 62 PostgreSQL hardening

R62 adds bounded PostgreSQL concurrency/recovery controls and a live qualification matrix. Unknown-outcome writes are never replayed after connection loss; only database-only deadlock/serialization transactions are eligible for bounded retry. Production PostgreSQL claims require `LIVE_POSTGRESQL` evidence.

### R62 source/offline qualification truth — 2026-09-24

- Repository: **453 collected / 442 PASS / 11 SKIP / 0 FAIL**.
- R62 focused: **15/15 PASS**. MC-11 authority regression: **12/12 PASS**.
- Compileall, launcher/R62 py_compile, packaging/hook shell syntax, and legacy selftest: **PASS**.
- Initial R62 campaign on this runner: **3 LOCAL_REGRESSION PASS / 0 FAIL / 12 BLOCKED_ENVIRONMENT / 0 NOT_RUN / 0 LIVE_POSTGRESQL PASS**. Production PostgreSQL claim remains false.
- Offline helper RPM: **99 payload files**, two source-tree rebuilds byte-identical, independent verifier PASS, SHA-256 `c47c4a7a1a8e2c26e86d7f5135965df3beced8fa38e593c7de8df457721edc1b`. This is not canonical live PostgreSQL/AlmaLinux evidence.
- Initial evidence bundle SHA-256: `b723e441bc309bdee8a142071f5e13271ce39c50cfd739728b7e2dccd2e60f4a`.

### R62 verified clean-extract truth

Provisional system-unzip clean extraction reproduced **453 collected / 442 PASS / 11 SKIP / 0 FAIL**; R62 focused **15/15 PASS**, MC-11 focused **12/12 PASS**, compileall/py_compile/shell/selftest PASS. Two clean-extract helper RPM rebuilds were byte-identical to the source-tree helper RPM and independently verified. Final frozen-artifact revalidation is performed after this documentation sync.

## Release 63 HA / failure-domain hardening

R63 makes control-plane coordination fail closed across PostgreSQL session loss and worker/node turnover. Advisory ownership is tied to PostgreSQL session generation, node identity is fenced, singleton schedulers revalidate leadership each pass so standbys can take over, and distributed work uses token/generation/lease fencing. Expired partial jobs move to `RECOVERY_REQUIRED`; only work explicitly marked `replay_safe` can be requeued. PostgreSQL primary election/promotion is not implemented by NetConfig and remains an external platform responsibility. Production HA is not claimed until the fixed live R63 qualification hooks pass on a real multi-node deployment spanning at least two declared failure domains.

## R63 verified clean-extract truth — 2026-09-24

The provisional source archive was extracted with system `unzip` and reproduced **477 collected / 463 passed / 14 skipped / 0 failed**. R63 focused coverage is **16/16 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, launcher/qualification `py_compile`, packaging/qualification/tool shell syntax, and legacy selftest are PASS. The provisional structural gate is **348 entries / 0 duplicates / 0 unsafe paths / 0 symlinks / CRC PASS / 348/348 byte+mode parity / 346/346 R63 source manifest / 347/347 whole-tree SHA256SUMS / 26/26 executable modes**. Two clean-extract helper RPM rebuilds are byte-identical to each other and to the source-tree RPM; independent verification passes. RPM SHA-256 is `1e2a40476c212d2ffe410d51ef1cd9b2fac3051fc96bf30789539be5bca4b60d`. This is local/offline artifact evidence only; live HA remains deferred.

## Release 65 — Operator Workflow Completion

R65 composes the existing persisted authorities into one operator journey: Incident → investigation/evidence → NI-7/MC-11 path plan → exact persisted proposal → existing Automation Request approval → Structured Change execution/verification/recovery/rollback → Incident-linked post-change evidence. It adds no parallel execution engine, no page-triggered polling, no arbitrary command authority, and no MC-12. Source regression is **508 collected / 494 PASS / 14 SKIP / 0 FAIL**; R65 focused **10/10 PASS**; MC-11 **12/12 PASS**. Initial campaign is **4 local PASS / 0 FAIL / 10 BLOCKED_ENVIRONMENT / 0 LIVE_OPERATOR PASS**, so production operator acceptance remains unclaimed.

## R67 release-candidate qualification

Release 67 freezes product authority and performs full artifact/release-candidate qualification. The source tree includes a deterministic SPDX 2.3 source SBOM and synchronized release manifest. Local/offline PASS establishes artifact consistency only; all fixed `LIVE_RC` gates remain required before the exact candidate can be described as RC-qualified. R67 itself never promotes the product to `RELEASED`.
