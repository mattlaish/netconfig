## R60 lifecycle management surface

R60 adds no public REST mutation API. Appliance lifecycle authority remains local/operator controlled through the CLI and packaging runbook: `netconfig lifecycle snapshot`, `verify`, `verify-live`, `restore-local`, `retention-candidates`, and `switch-postgres-rollback`. These commands do not add network-device configuration authority and do not bypass Automation Request / Structured Change approval.

## Q2 qualification API impact

None. Q2 adds offline/qualification-host tooling and evidence files only. There is no new REST endpoint, no new device/configuration authority, and no public API contract change. MC-11 proposed changes continue to enter the existing Automation Request / Structured Change workflow.

# NetConfig API Contract


## MC-11 Topology-Aware Change Planning API

- `POST /api/v1/change-planning/evidence` — operator + `analytics:write`; persists normalized ACL/firewall/NAT/PBR/routing-policy evidence and optional validated Structured Change proposal metadata.
- `GET /api/v1/change-planning/evidence` — `analytics:read`; bounded persisted evidence query.
- `POST /api/v1/change-planning/plans` — operator + `analytics:write`; persists deterministic Source→Destination planning result from already-collected evidence.
- `GET /api/v1/change-planning/plans` and `GET /api/v1/change-planning/plans/{id}` — `analytics:read`.
- `POST /api/v1/change-planning/plans/{id}/what-if` — operator + `analytics:write`; evaluates candidate proposal state without network mutation.

The API accepts no arbitrary command payload. Proposed changes use the existing Structured Change schema and remain non-executing until the separate approval/execution workflow is used.

## Release 58 / MC-10 correlation hardening API

MC-10 adds read/qualification and bounded maintenance surfaces without adding device or external-product action authority:

- `GET /api/v1/operations/correlation/health` — `analytics:read`; optional bounded `window_seconds` (60..86400). Returns run counts/states, latency percentiles, queue/inflight state, truncation/skew counters, evidence/event rates, duplicate/reject counters, connector lag and hard limits.
- `GET /api/v1/operations/qualification/correlation` — `analytics:read`. Returns local checks plus explicit deferred live gates and always preserves `IMPLEMENTED_TESTING_DEFERRED` / `release_eligible=false` until a separate release process has real evidence.
- `GET /api/v1/incidents/{incident_ref}/correlation-runs` — `incident:read`. Returns bounded durable run/replay evidence; Incident investigation also includes the latest run history.
- `POST /api/v1/incidents/{incident_ref}/correlation-replay` — `incident:write` plus operator/approver/admin. Requires a bounded start/end range no larger than seven days. It evaluates the same deterministic engine in preview mode and does **not** persist/deactivate hypotheses.
- `POST /api/v1/operations/correlation/retention` — `analytics:write` plus operator/approver/admin. Prunes only old finished `correlation_runs`; it does not delete Incident evidence or hypotheses.

Same-incident contention returns a bounded/fail-closed busy result; detected non-deterministic replay integrity failure is surfaced as conflict rather than silently accepted.

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Release 55 / MC-7 Incident correlation API

MC-7 adds deterministic Incident correlation without adding any device-write or connector-action authority.

- `POST /api/v1/incidents/{incident_ref}/correlate` — requires `incident:write` and operator/approver/admin role. Runs the bounded deterministic rule set against already-persisted Incident evidence and trusted MC-6 dependency context. The response contains generated/active hypotheses and execution bounds. It does not poll devices, execute remediation, or confirm root cause.
- `GET /api/v1/incidents/{incident_ref}/hypotheses` — requires `incident:read`. Returns persisted hypotheses including rule/version, confidence, supporting evidence, contradicting evidence, affected entities, evidence time range, and score breakdown.
- `GET /api/v1/incidents/{incident_ref}/investigation` — existing endpoint now includes `hypotheses` and `current_hypothesis`. `root_cause` remains unset; `root_cause_state` may be `NOT_CONFIRMED` when hypotheses exist and otherwise remains `NOT_EVALUATED`.

Correlation is replay-idempotent for the same incident/evidence/rule version and does not use time proximity alone to connect unrelated entities.


## Release 54 / MC-6 Service & Dependency Graph API

MC-6 reuses the existing analytics authorization boundary. Read endpoints require `analytics:read`. Mutation of NetConfig's dependency inventory requires `analytics:write` plus an `operator`, `approver`, or `admin` token role. These writes only update dependency metadata; they cannot execute device/application configuration. The API currently accepts only the deployment's `default` tenant scope.

- `POST /api/v1/dependencies/entities` — create/update a typed service entity. Fields: `entity_key`, `entity_type`, `name`, optional `description`, optional JSON `metadata`.
- `GET /api/v1/dependencies/entities` — query entities by optional `type`, `q`, and bounded `limit`.
- `POST /api/v1/dependencies/edges` — create/refresh typed dependency evidence. Fields: `source_key`, `target_key`, `relationship`, `evidence_state`, `provenance`, optional `evidence_ref`, `observed_ts`, `max_age_seconds`, `vrf`, `destination_prefix`, and JSON `metadata`. `DISCOVERED` / `INFERRED` require an evidence reference. VRF/destination scope is accepted only for `ROUTES_THROUGH`.
- `GET /api/v1/dependencies/edges` — query dependency evidence with source/target/relationship/state filters.
- `POST /api/v1/dependencies/edges/{id}/state` — activate/deactivate one dependency evidence row.
- `GET /api/v1/dependencies/graph/{root}` — bounded directed traversal. Query options: `max_depth` (0–8), `max_nodes` (1–250), `include_inferred`, and `include_stale`. Default traversal does not follow INFERRED, stale, inactive, or UNKNOWN evidence.
- `GET /api/v1/dependencies/impact/{root}` — dependency impact projection through the existing `ImpactSimulator`; stale evidence is excluded and inferred evidence requires explicit opt-in.
- `GET /api/v1/dependencies/network-overlay/{root}` — read-only NI-7 L3/VRF overlay using `source_device`, `vrf`, `destination_prefix`, optional `max_hops`. It reads persisted route observations only, performs no device I/O, and fails closed on unresolved/ambiguous paths.

Graph responses expose nodes, evidence edges, traversal/exclusion decisions, evidence-state/freshness counts, cycle count, configured hard bounds, and explicit truncation state. `UNKNOWN` is not returned as a failure condition.

## Release 53 / MC-5 Incident API additions

Incident evidence linking accepts the existing types plus `sensor_transition`, `operational_event`, `operational_alert`, `change_event`, `analytics_insight`, and `external_event`. References are type-validated and must resolve at link time. The link records source/receive timestamps and bounded source-clock metadata while the source object remains authoritative.

`GET /api/v1/incidents/{ref}/investigation` requires the existing `incident:read` scope and returns Incident summary/impact, deterministic Unified Timeline, Related Alerts, Related Changes, Network Evidence, Security Evidence, Infrastructure Evidence, and Raw/Advanced Evidence. It returns no automatic root-cause verdict. The normalized `external_events` table is internal MC-5 evidence storage; R53 does **not** publish the MC-8 external connector/ingestion contract. Existing Incident write/RBAC semantics are unchanged.


## Release 52 alert and endpoint API additions

`GET /api/v1/alerts` is the canonical MC-4 read alias for the `operational_alerts` lifecycle and accepts `state`, `device`, and bounded `limit`; it requires `alerts:read`. Existing `GET /api/v1/operational-alerts` remains compatible and returns the same authoritative lifecycle. Existing alert write operations are also accepted under `/api/v1/alerts/{id}/...` with the same `alerts:write` and role requirements; old operational-alert write URLs remain valid.

`GET /api/v1/endpoints` now accepts optional `q` and `device`. `q` searches IP, MAC, resolved switch/port and candidate evidence. Correlation is global before the optional device filter so ARP/IP-neighbor evidence on an L3 gateway can join FDB/MAC evidence on a different managed switch. Responses include `evidence_chain.ip_neighbors` and `evidence_chain.fdb_candidates`; ambiguous/transit/stale states remain explicit. When IP evidence exists, `ip_mapping_fresh` reports whether at least one current IP-neighbor mapping supports the combined conclusion; stale-only IP evidence downgrades combined confidence instead of being reported as `HIGH`.

## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

> **Roadmap disposition — 2026-09-24:** **R59 / MC-11 is the final Monitoring & Correlation functional slice.** Do not create MC-12. After R59, stop feature expansion and use the Release / Qualification track: **Q2 Production Qualification Campaign → R60 Appliance Reliability & Lifecycle Hardening → R61 Scale & Performance Qualification → R62 PostgreSQL / Concurrency / Recovery Hardening → R63 HA / Failure-Domain Engineering → R64 Security Hardening & Independent Abuse Testing → R65 Operator Workflow Completion → R66 Observability / Supportability → R67 Release Candidate / Full Artifact Qualification → R68 v2 Production Release Decision**. Simulation never counts as live PASS; mandatory gates use `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN`.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


## Historical Release 34 / UI-1 API alignment

UI-1 consumes the existing PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 service contracts and does not create a privileged browser-only execution API. The existing `/api/v1/automation-requests` request/approve/execute path remains the canonical network-mutation contract.

Release 34 adds parity for telemetry edit: `POST /api/v1/telemetry/subscriptions/{id}/update` accepts the same bounded fields as creation except `device`; device rebinding is deliberately unsupported. Existing telemetry create/capture/window/enable/disable/delete/run-due and read/points/summary contracts remain unchanged.

The Web `/operations` routes are HTML operator workflows, not a replacement REST contract. All mutations still enforce the underlying role/service rules and CSRF.


## Release 33 automation API contract

New bearer scopes are `automation:read|write`, `telemetry:read|write`, `desired:read|write`, `campaign:read|write`, `model:read|write`, and `ha:read|write`. Existing role checks continue to apply in addition to scopes.

Primary read/write surfaces include:

- `/api/v1/automation-requests` for durable submit/approve/execute workflow; structured change, desired-state apply, campaign wave and rollback intents execute only through this approval path;
- `/api/v1/structured-changes` plus transaction detail/interrupted/recovery operations; direct generic mutation is not exposed;
- `/api/v1/telemetry/subscriptions`, `/samples`, `/points`, `/summary`, bounded capture/stream-window, enable/disable/delete and `/api/v1/telemetry/run-due`;
- `/api/v1/desired-states`, per-state plan/evaluate/runs, clone/update/publish, plus `/api/v1/desired-state-runs` evidence;
- `/api/v1/campaigns` with create/start/pause/resume/retry/abort and read surfaces; direct wave mutation returns approval-required and must use an automation request;
- `/api/v1/vendor-model-packs` plus device binding/effective resource inspection; model writes require `model:write` and validated specs;
- `/api/v1/ha/nodes`, `/api/v1/ha/readiness`, node-state drain/activate and recovery-drill evidence.

All structured resource selection is server-side/model-pack resolved. API clients cannot supply arbitrary southbound XML, arbitrary RESTCONF URLs/bodies, arbitrary gNMI proto requests, or secrets in protocol traces/audit responses.

> **Current continuation pointer:** use **Release 59 / MC-11 Topology-Aware Change Planning** (`2.0.0-59`) as the active full-source baseline once the final artifact gate below is frozen. Preserve `IMPLEMENTED_TESTING_DEFERRED`; do not promote to `TESTED` or `RELEASED` based on source simulation. MC-11 is the final functional slice and does not add direct execution authority. The immediate next track after artifact freeze is **Q2 Production Qualification Campaign**, not MC-12.

## Q-1 API impact

Q-1 adds **no new REST API endpoints or bearer scopes**. Production qualification controls are local operator/packaging surfaces: `netconfig qualify`, `netconfig storage backup-postgres`, `netconfig storage restore-postgres`, and the `packaging/q1-*` qualification harnesses. Existing API authentication, RBAC, CSRF, TLS and secret-redaction semantics are unchanged.

Current source baseline: Qualification Q-1 on top of Platform Hardening PH-3 (2026-09-12). Q-1 changes local runtime/qualification surfaces only; PH-3 remains the latest feature baseline.

## Authentication

API clients use `Authorization: Bearer <token>`. Token plaintext is returned once at creation; only its SHA-256 hash is persisted. The server rejects bearer authentication over cleartext non-loopback HTTP. Use built-in TLS or a TLS reverse proxy whose backend connection is loopback.

Scopes are explicit. Phase 4A adds `incident:read` and `incident:write`; Phase 4C adds `incident:export`. Both `incident:write` and `incident:export` require an `operator`, `approver`, or `admin` token role. Phase 4D reuses those existing scopes for verification. Phase 4E adds `trace:read` and `trace:capture`; `trace:capture` requires an `operator`, `approver`, or `admin` token role. Phase 3D scopes `debug:download` and `debug:admin` remain present in the token registry.

## Existing read surfaces

- `GET /api/v1/inventory` — `inventory:read`
- `GET /api/v1/topology` — `topology:read`
- `GET /api/v1/drift` — `drift:read`
- `GET /api/v1/compliance/latest` — `compliance:read`
- `GET /api/v1/digest/latest` — `compliance:read`
- `GET /api/v1/audit` — `audit:read`
- `GET /api/v1/debug/bundles` — `debug:read`
- `GET /api/v1/debug/bundles/{bundle}` — `debug:download`
- `POST /api/v1/debug/bundles` — `debug:create`

## D.5 Phase 4A incident endpoints

### Create incident

`POST /api/v1/incidents` — `incident:write`, operator-or-higher role.

JSON or URL-encoded fields:

- `title` — required, 1–200 characters.
- `description` — optional, at most 10,000 characters.
- `severity` — LOW, MEDIUM, HIGH, CRITICAL; default MEDIUM.
- `tags` — optional JSON array; URL-encoded clients may repeat `tag`.

New incidents start in `OPEN` and receive an ID such as `INC-2026-000001`.

### List/read

- `GET /api/v1/incidents` — `incident:read`.
- `GET /api/v1/incidents/{incident_key_or_numeric_id}` — `incident:read`.

The detail object includes linked diagnostic bundle metadata.

### Change status

`POST /api/v1/incidents/{id}/status` — `incident:write`, operator-or-higher role.

Fields: `status`, optional `note`.

Allowed transitions:

- OPEN → INVESTIGATING, RESOLVED, CLOSED
- INVESTIGATING → RESOLVED, CLOSED
- RESOLVED → INVESTIGATING, CLOSED
- CLOSED → INVESTIGATING

Closing records `closed_by` and `closed_ts`; reopening clears closure metadata.

### Link diagnostic bundle

`POST /api/v1/incidents/{id}/bundles` — `incident:write`, operator-or-higher role.

Field: `bundle` containing a managed `.tar.gz` basename. Traversal/nested paths are rejected and the bundle must exist in NetConfig's managed debug-bundle directory.

## Error semantics

Authentication failures return 401; insufficient scope/role returns 403; missing incident/bundle/export returns 404; invalid model input or transition returns 400. A support-case archive whose durable size/SHA-256 no longer matches returns 409 and is not downloaded. Internal failures remain 500 and are handled by the console's existing error logging path.

## D.5 Phase 4B incident timeline endpoints

### List evidence links

`GET /api/v1/incidents/{id}/evidence` — `incident:read`.

Returns reference/link metadata and an `available` flag. The response does not copy the authoritative evidence body into the link record. Drift source references are returned as `{device, baseline_stamp, current_stamp}`.

### Read unified timeline

`GET /api/v1/incidents/{id}/timeline` — `incident:read`.

Returns an ordered view of incident creation, incident-targeted audit events, currently linked diagnostic bundles, and linked `audit`, `syslog`, `collection`, `compliance`, or `drift` evidence. Resolver output is derived from authoritative stores at read time. A source removed by retention is returned with `available=false`.

### Link evidence

`POST /api/v1/incidents/{id}/evidence` — `incident:write`, operator-or-higher role.

For audit/syslog/collection/compliance, fields are `source_type`, `source_id`, and optional `note`. For drift, use `source_type=drift`, `device=<inventory/config-store device>`, optional `note`; NetConfig captures the current baseline/current archive stamps server-side. Unsupported types and nonexistent sources are rejected.

### Unlink evidence

`POST /api/v1/incidents/{id}/evidence/{link_id}/unlink` — `incident:write`, operator-or-higher role.

Removes only the incident association. It never deletes the authoritative audit/syslog/run/compliance/config evidence.

## D.5 Phase 4C support-case export endpoints

### Create support-case export

`POST /api/v1/incidents/{id}/exports` — `incident:export`, operator-or-higher role.

JSON or URL-encoded fields:

- `bundles` / repeated `bundle` — optional linked diagnostic bundle basenames. When omitted, all currently available linked bundles are included.
- `reason` — optional bounded export reason. Common credential-assignment patterns are redacted before persistence/export.

Explicitly requested bundles must already be linked to the Incident and still exist in the managed diagnostic-bundle directory. The exporter is bounded to 32 bundles and 512 MiB aggregate diagnostic-bundle input.

### List support-case exports

`GET /api/v1/incidents/{id}/exports` — `incident:read`.

Returns durable export metadata and current `available` state without exposing server filesystem paths.

### Download support-case export

`GET /api/v1/incidents/{id}/exports/{export_key}` — `incident:export`, operator-or-higher role.

Only a durable export record under the managed case-export directory can be downloaded. Before streaming, NetConfig recomputes archive size/SHA-256 and fails closed on mismatch. The download is audited against the Incident and returns `application/gzip` with an attachment filename without loading the complete archive into memory.

## Deferred

Phase 4D implements evidence/manifest signing and verification. Protocol trace APIs, automatic event-correlation rules, and Incident Web UI endpoints remain deferred.


## D.5 Phase 4D signing / verification endpoints

### Create diagnostic bundle with required signature

`POST /api/v1/debug/bundles` — `debug:create`. Optional field `require_signature=true` makes the request fail closed unless the external Ed25519 signer is ready. A configured signer is used automatically even when the field is omitted.

### Signing status

`GET /api/v1/debug/signing` — `debug:read`. Returns signer readiness, algorithm, current key fingerprint when available, signing-required policy, and configured trust fingerprints. It never returns private-key paths or material.

### Verify diagnostic bundle

`GET /api/v1/debug/bundles/{name}/verify` — `debug:read`. Performs extraction-free archive/manifest/payload/signature verification and reports `signature_valid`, `key_fingerprint`, and `trusted`. Verification is audited.

### Create support-case export with required signature

`POST /api/v1/incidents/{id}/exports` — `incident:export`, operator-or-higher role. Optional field `require_signature=true` requires signing. Existing `bundles` and `reason` semantics are unchanged.

### Verify support-case export

`GET /api/v1/incidents/{id}/exports/{export_key}/verify` — `incident:export`, operator-or-higher role. Verifies outer durable archive identity plus the signed inner manifest/payload. The result distinguishes cryptographic validity from trust-pin match and the operation is audited.

Signed support-case downloads continue through `GET /api/v1/incidents/{id}/exports/{export_key}`. When the durable record says the export is signed, download verifies the signature and recorded signer fingerprint before streaming. If independent trust pins are configured, a valid but untrusted signer is rejected.


## D.5 Phase 4E protocol trace endpoints

Trace capture is metadata-only, explicit and bounded. It does not expose raw SSH terminal output, SNMP packets or protocol credentials.

- `POST /api/v1/traces` — `trace:capture`, operator-or-higher. Fields: `device`, `protocol` (`cli_ssh` or `snmp`), optional `incident`, `ttl` (30..3600 seconds), `max_events` (1..5000), `max_bytes` (4096..8388608), and bounded `reason`.
- `GET /api/v1/traces` — `trace:read`. Lists durable trace-session metadata.
- `GET /api/v1/traces/{trace_key}` — `trace:read`. Reads one session.
- `GET /api/v1/traces/{trace_key}/events` — `trace:read`. Reads sanitized trace events.
- `POST /api/v1/traces/{trace_key}/stop` — `trace:capture`, operator-or-higher. Explicitly ends an active session.

Starting with an Incident automatically creates a reference-only `protocol_trace` Incident evidence link. TTL/budget exhaustion preserves the durable trace and changes its state to `EXPIRED` or `LIMIT_REACHED`. PH-3 enables NETCONF/RESTCONF/gNMI metadata trace providers. Trace capture remains bounded and never stores raw structured-protocol payloads or credentials.


## D.5 Phase 4F Web Console note

Phase 4F adds no new `/api/v1` contract. It introduces authenticated human-operator routes (`/incidents`, `/incident`, and CSRF-protected Incident action routes) that orchestrate the existing Incident, evidence, trace and support-case service methods. Existing Phase 4A-4E REST scopes and semantics remain unchanged.


## D.5 closeout maintenance

D.5 closeout does not add a new REST mutation surface. Retention maintenance is configured through the authenticated admin Monitoring settings and can be executed explicitly with `netconfig debug maintenance`. Existing Incident, trace, diagnostic-bundle and support-case APIs remain unchanged.


## Network Intelligence NI-1 endpoint correlation

Bearer scope: `endpoint:read` (viewer role is sufficient).

### `GET /api/v1/endpoints`

Returns `{summary, endpoints}`. Each endpoint record includes normalized MAC, IPv4/IPv6 observations, correlation status/confidence, an optional direct attachment `{device,vlan_id,fdb_id,ifindex,ifdescr,bridge_port,source,ts}`, direct candidates, transit observations and source neighbour observations.

Correlation is deliberately fail-closed: VLAN is blank when Q-BRIDGE FDB-ID mapping is not unique; multiple fresh non-neighbour-facing attachment candidates return `AMBIGUOUS`; observations found only on LLDP/CDP-facing ports return `TRANSIT_ONLY`; old evidence returns `STALE`. The API never converts those states into a guessed direct attachment.


---

Historical PH-3 closeout artifact: `netconfig_platform_hardening_ph3_FULL_source_baseline_2026-09-12_completed.zip`. The current deliverable is the Q-1 FULL source baseline.

## Network Intelligence NI-2 topology identity / impact

All endpoints below require bearer scope `topology:read` and are read-only.

- `GET /api/v1/topology/identities` — normalized managed-device identity and interface-identity evidence.
- `GET /api/v1/topology/impact/{device}` — bounded downstream traversal over resolved managed L2 observations for the named root device.

The impact response includes `scope=observed_managed_l2_adjacency`, `devices`, `edges`, `device_count`, and `edge_count`. Ambiguous/unmanaged edges are not traversed. The REST endpoint intentionally uses the whole-device root; optional first-hop port scoping is available in CLI/Web workflow.

## Network Intelligence NI-3 operational events

`GET /api/v1/events` requires `events:read` and returns the latest normalized operational events plus active dependency suppressions. Event rows expose source type, device/source, normalized event type, severity, interface/ifIndex, trap OID, dedup count, suppression state and bounded normalized metadata. Raw SNMP packets and v2c community strings are never returned or persisted.


## Network Intelligence NI-4 operational alerts and reports

Bearer scopes: `alerts:read`, `alerts:write`, `reports:read`, `reports:write`. Write scopes require operator-or-higher role.

Read endpoints:
- `GET /api/v1/operational-alerts` -> operational alerts, active maintenance and recent delivery state.
- `GET /api/v1/maintenance-windows` -> durable maintenance windows.
- `GET /api/v1/operational-reports` -> report schedules and recent runs.

Write endpoints:
- `POST /api/v1/operational-alerts/{id}/ack` (`alerts:write`)
- `POST /api/v1/operational-alerts/{id}/resolve` (`alerts:write`)
- `POST /api/v1/maintenance-windows` and `/api/v1/maintenance-windows/{id}/cancel` (`alerts:write`)
- `POST /api/v1/report-schedules`, `/api/v1/report-schedules/{id}/run|enable|disable` (`reports:write`)

NI-4 APIs never expose SMTP credentials or raw trap packets/community strings. Operational reports contain bounded aggregate summaries, not raw authoritative evidence payloads.

## Platform Hardening PH-1 API compatibility

PH-1 is a structural Web-console hardening slice. No `/api/v1` route, method, request/response schema or bearer-scope contract is intentionally changed. API routing is physically separated into `web_api.py`, while the same bearer-token transport restriction and scope checks remain enforced.

## Platform Hardening PH-2 storage/readiness additions

PH-2 does not add a new bearer-token REST mutation surface for storage administration. Core database migration and task-queue administration are local CLI/operator operations.

Existing `GET /readyz` is extended additively with a `storage` object containing non-secret backend readiness data: backend (`sqlite` or `postgres`), whether the backend is distributed-capable, configured/observed schema revision, reachability/overall readiness, cluster node ID, and the *type* of password source (for example `systemd-credential`), never the password itself.

The CLI adds `netconfig storage status|tasks|enqueue|claim|finish|migrate-sqlite`. PostgreSQL task claims are transactional and use `FOR UPDATE SKIP LOCKED`; SQLite claims are single-node/process-local compatibility only.


## PH-3 structured protocol profiles

Scopes: `protocol:read` may be granted to viewer tokens. `protocol:write` requires token role `operator`, `approver`, or `admin`.

- `GET /api/v1/protocol-profiles` — `protocol:read`; returns non-secret per-device profile/status information.
- `POST /api/v1/protocol-profiles` — `protocol:write`; create/update one bounded protocol profile. Fields include `device`, `protocol`, optional `port`, validated RESTCONF/gNMI read `path`, vault `secret_ref`, `tls_verify`, `ca_file`, and `allow_cli_fallback`. TLS verification cannot be disabled unless the explicit lab-only environment gate is active.
- `POST /api/v1/protocol-collect/{device}` — `protocol:write`; trigger one configuration collection using the selected profile and return collection/version metadata. Structured failure is fail-closed unless that profile explicitly enables CLI fallback.
- `GET /api/v1/protocol-capabilities/{device}` — `protocol:read`; perform protocol-specific capability/discovery negotiation and return normalized non-secret capability evidence.
- `GET /api/v1/protocol-state/{device}` — `protocol:read`; perform a bounded operational-state read using the device profile's validated path/default.

CLI-only bounded read helpers additionally expose `netconfig protocol capabilities`, `netconfig protocol state`, and `netconfig protocol subscribe-once` (gNMI ONCE only).

No public PH-3 API/CLI surface accepts arbitrary NETCONF RPC XML, arbitrary RESTCONF URL/method/body, arbitrary protobuf, NETCONF `edit-config`, RESTCONF generic mutation, or gNMI Set. The internal RESTCONF JSON subtree replacement primitive is approval-gated and intentionally not exposed as a generic remote-execution endpoint.


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

## NI-6.4 Failure Risk API boundary

NI-6.4 in this delivery is an internal analytics foundation and does **not** add a new public HTTP route. `FailureRiskAnalyzer` emits a NetworkInsight-compatible `FAILURE_RISK` mapping containing tenant/object identity, severity, confidence, summary, and bounded evidence. Public API/UI surfacing is deferred to a later slice. No API accepts device commands, remediation actions, arbitrary analytics payloads, or caller-supplied approval state through this feature.



NI-6.6 Health Dashboard: IMPLEMENTED_TESTING_DEFERRED

## NI-6 Enterprise Analytics API

Bearer scopes: `analytics:read` for reads; `analytics:write` plus role `operator|approver|admin` for analytics execution/lifecycle mutation. Bearer transport protections remain unchanged.

Read-only endpoints:

- `GET /api/v1/analytics/dashboard`
- `GET /api/v1/analytics/jobs?limit=N`
- `GET /api/v1/analytics/insights?state=&type=&severity=&object_id=&search=&limit=`
- `GET /api/v1/analytics/insights/{id}`

Explicit mutation endpoints:

- `POST /api/v1/analytics/refresh` with `object_id` — runs Capacity, Failure Risk and Health and persists evidence.
- `POST /api/v1/analytics/impact/simulate` with `object_id`, optional `max_depth` — managed directional what-if simulation only.
- `POST /api/v1/analytics/insights/{id}/state` with `state=ACKNOWLEDGED|RESOLVED|EXPIRED`, optional `note`.
- `POST /api/v1/analytics/expire` with optional `max_age_seconds`.

Analytics responses include workflow navigation references but never contain an executable remediation primitive.

## NI-7 L3/VRF Path & Route Dependency API

Uses the existing `analytics:read` / `analytics:write` scopes. Write endpoints additionally require operator-or-higher role. NI-7 is evidence capture and simulation only; these endpoints do not expose arbitrary route commands, device configuration, or approval bypass.

Read:

- `GET /api/v1/analytics/l3/routes?device=&vrf=&destination_prefix=&limit=` — list durable explicit route observations.

Operator writes:

- `POST /api/v1/analytics/l3/routes` — persist one explicit route observation (`device`, `vrf`, `destination_prefix`, optional `protocol`, `next_hop`, `outgoing_interface`, explicit managed `next_device`, `metric`, `terminal`).
- `POST /api/v1/analytics/l3/path/simulate` — simulate a bounded same-VRF path using only explicit managed route evidence (`source_device`, `vrf`, `destination_prefix`, optional `max_hops`).
- `POST /api/v1/analytics/l3/dependencies/analyze` — persist route-dependency candidate insights for observations explicitly referencing `failed_device`.

Simulation is fail-closed: no next-device inference from next-hop IP, no VRF crossing, no arbitrary ECMP selection, and bounded loop detection. Dependency results are candidates rather than outage assertions.

## Release 48 sensor API contract

`GET /api/v1/sensors` returns normalized persisted sensor rows. Query parameters are `device=<name>`, `type=<sensor_type>`, `status=OK|WARNING|CRITICAL|UNKNOWN`, and `limit=<1..2000>`. Invalid status values fail closed with HTTP 400. The endpoint refreshes sensors from already-persisted inventory/evidence before reading them; this refresh performs no network/device I/O. Required bearer scope: `analytics:read` **or** `inventory:read`.

Representative response fields: `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, `updated_at`. Missing evidence uses `status=UNKNOWN` and an empty `value`; clients must not reinterpret that as a numeric zero or outage.

## Release 50 MC-2 Sensor history API

### `GET /api/v1/sensor-history`
Requires `analytics:read` or `inventory:read`. Query parameters: `sensor_key` (required), `limit` (1–2000), optional UNIX timestamps `since` and `before`. Returns `{sensor_key, observations, transitions}`. This endpoint is read-only and does not refresh Sensors or contact devices.

### `GET /api/v1/sensor-transitions`
Requires `analytics:read` or `inventory:read`. Optional filters: `device`, `type`, `from_status`/`from`, `to_status`/`to`, `since`, `before`, and bounded `limit` (1–2000). Status values are `OK`, `WARNING`, `CRITICAL`, `UNKNOWN`; invalid status filters fail with HTTP 400.

## Release 51 MC-3 Operational Evidence API

`GET /api/v1/events` remains protected by `events:read` and now returns normalized operational-evidence fields. Optional query parameters are `device`, `domain`, `source_type` (legacy alias `source` selects the source type), `entity_type`, `status`, `limit`, and `include_suppressed`. Reads are bounded and do not refresh Sensors or contact devices.

`GET /api/v1/events/{id}` returns:

```json
{
  "event": {"id": 1, "domain": "NETWORK", "event_type": "interface.down", "evidence_ref": "sensor-transition:42"},
  "related_sensor": {"sensor_type": "interface.status", "status": "WARNING"}
}
```

The related Sensor is a read-only lookup of the current canonical Sensor snapshot and may be `null` for events that do not map to a Sensor. Sensor-derived operational evidence uses `sensor-transition:<transition-id>` as its durable evidence reference.

## R51-HF1 topology graph API

### `GET /api/v1/topology/graph`

Read-only; requires `topology:read`. Returns the current graph derived from persisted inventory, topology identity/interface rows, resolved LLDP/CDP observations, and FDB/MAC evidence. It does **not** trigger discovery or device polling.

The response contains `nodes`, `edges`, and `summary`. Every managed inventory device is represented as a node. LLDP/CDP resolved direct adjacency is returned with `evidence_kind="OBSERVED"` and `direct_adjacency=true`; FDB/MAC correlation is returned only as `evidence_kind="INFERRED"`, `direct_adjacency=false`, and must not be interpreted as proof of a direct physical link. Nodes without adjacency evidence remain `UNKNOWN` rather than disappearing from the graph.


## R54.1 L3 topology read APIs

All endpoints below require `topology:read` and are read-only:

- `GET /api/v1/topology/l3` — current fresh L3 graph; optional `include_stale=true` exposes stale evidence without treating it as fresh truth.
- `GET /api/v1/topology/combined` — L2 physical/FDB evidence overlaid with the L3 graph.
- `GET /api/v1/topology/l3/status?device=<name>` — L3 collection generation/status.
- `GET /api/v1/topology/l3/interfaces?device=<name>` — normalized interface-address observations.

Existing `GET /api/v1/analytics/l3/routes` remains the route-evidence query surface. No L3 topology endpoint performs device I/O or configuration execution.

## Release 56 / MC-8 external evidence API

MC-8 exposes an inbound, evidence-only normalized ingestion plane. API-token scopes are `external:manage` (admin source lifecycle), `external:ingest` (operator-or-higher source-bound connector ingestion), and `external:read` (viewer-or-higher health/evidence reads). One enabled ingest token may bind to only one external source. Token hashes remain in the existing API-token store; connector plaintext secrets are not stored in the source registry.

Management/read routes:

- `POST /api/v1/external-sources` — create/update a normalized source (`external:manage`, admin).
- `POST /api/v1/external-sources/{source_key}/state` — enable/disable source (`external:manage`, admin).
- `GET /api/v1/external-sources` and `/api/v1/external-sources/{source_key}` — health/state (`external:read`).
- `GET /api/v1/external-sources/{source_key}/events` — bounded normalized events (`external:read`).
- `GET /api/v1/external-evidence/{event_id}` — sanitized Advanced evidence (`external:read`).
- `POST /api/v1/external-evidence/{source_key}/events` — source-bound normalized ingest (`external:ingest`).

Normalized schema v1 example:

```json
{
  "schema_version": "1",
  "source_event_id": "ndr-evt-123",
  "idempotency_key": "delivery-123",
  "event_type": "traffic.spike",
  "source_ts": 1770000000.0,
  "severity": "MAJOR",
  "domain": "SECURITY",
  "entity_type": "ip",
  "entity_id": "10.0.0.10",
  "summary": "Traffic volume spike",
  "metadata": {},
  "payload": {},
  "source_clock": {}
}
```

A new event returns `201`; an identical idempotent/source-event replay returns `200` without creating another event. Reusing an idempotency key or source-event ID with different normalized evidence returns `409`. Disabled source is `409`; authentication/source-binding failure is `403`; source-specific/global oversized payload is `413`; source rate limit is `429`; malformed or unsupported schema is a bounded 4xx rejection and increments visible schema/rejection health. Secret-like fields are recursively redacted before persistence. MC-8 routes never reconfigure the external source or invoke response actions.

## R61 API qualification note

R61 adds no public REST contract. The qualification benchmark measures existing read-only API and WebUI paths. Reported local percentiles are `LOCAL_SYNTHETIC`; production API/WebUI latency claims require the corresponding `LIVE_PRODUCTION` gates.

## R62 API impact

R62 adds no public REST mutation authority. Existing APIs retain their contracts; the change is PostgreSQL concurrency/recovery hardening underneath persisted-data operations. Qualification hooks are operational tooling, not public API endpoints.

## R63 API/contract impact

R63 does not add a parallel device-execution REST authority. Existing readiness/storage representations may expose additive non-secret HA readiness information derived from cluster membership and failure domains. The operational task contract now relies on fenced claim token/generation/lease semantics internally; stale or expired ownership is rejected. PostgreSQL primary promotion remains outside the NetConfig API.

## R65 operator-workflow API

- `POST /api/v1/change-planning/plans` accepts optional `incident_ref`; when supplied, the incident must exist and the reference is persisted with the MC-11 input.
- `POST /api/v1/automation-requests` accepts optional bounded `context` containing only `incident_ref`, `plan_id`, and `proposal_index`. The submitted Structured Change intent must exactly match the persisted proposal selected by the context.
- `GET /api/v1/operator-workflows/{incident}` is read-only and requires `incident:read`, `analytics:read`, and `automation:read`; optional `plan_id`, `request_id`, and `transaction_id` selectors constrain the persisted read model.

These endpoints do not grant direct device-write authority; approval/execution still use existing Workflow and Structured Change controls.

## R66 supportability API

`GET /api/v1/supportability` requires bearer scope `debug:read`. It returns schema `r66-supportability-1` with aggregate storage, HA, restart, queue, telemetry, external-ingest, collector, correlation, retention, disk and last-success state plus explicit read-only truth. The route performs no device polling or network mutation. HTTP responses include a server-generated `X-Request-ID` for log/error correlation.

## R67 API status

R67 adds no REST endpoint, request/response schema, permission, or mutation authority. Existing API behavior remains frozen from R66; API/operator acceptance is exercised only through qualification gates.
