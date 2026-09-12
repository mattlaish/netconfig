# NetConfig API Contract

> **Canonical project state — 2026-09-12:** **CURRENT IMPLEMENTATION BASELINE** = **HA-1 — Control-plane HA & Recovery Foundation** (`IMPLEMENTED_TESTING_DEFERRED`). **PH-4, NI-5, VM-1, NA-1, NA-2, and HA-1** are implemented in source; consolidated Release 33 offline regression is green, while live/service-backed qualification remains deferred. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; its live PostgreSQL/AlmaLinux/systemd/service-backed gates remain deferred. No further development phase is assigned until the post-implementation qualification/roadmap review. RPM source Release is `2.0.0-33`.

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

> **Current continuation pointer:** use the Release 33 full source baseline as the active implementation source. Historical CURRENT/NEXT statements below are chronology only. Use the recorded Release 33 offline/artifact evidence and run the applicable Q-1 live gates before any promotion to `TESTED`/`RELEASED`; then perform a fresh roadmap review before assigning another development phase.

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
