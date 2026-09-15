# Security

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.

## Release 34 / UI-1 security boundaries

UI-1 adds no direct network-write primitive. Structured changes, desired-state application, rollback, and fleet waves are submitted as durable automation change requests. Approval reviews a frozen resolved snapshot and SHA-256; approval/execution revalidates the current resolved snapshot and fails closed on drift.

Web role boundaries mirror the service/API plane: viewers are read-only; operators may create operational objects and submit approvals; approvers may publish desired-state revisions and approve/execute CRs; only admins may mark/reconcile interrupted structured transactions, manage model packs/bindings, or change cluster-node lifecycle state. CSRF is required for every UI mutation. Strict CSP nonce processing and `script-src-attr/style-src-attr 'none'` remain unchanged.

Telemetry edits cannot change the bound device and cannot modify a RUNNING subscription. This prevents retained sample/audit history from being silently reassigned. Session idle/absolute expiry remains explicitly deferred security debt and was not implemented by UI-1.


## Release 33 security invariants

Release 33 preserves the existing fail-closed boundaries and adds the following mandatory controls:

- a network mutation must reference an approved durable `change_requests` record; a CLI/API boolean cannot self-authorize a write;
- the exact automation snapshot is hashed at submission and checked again at approval/execution; device target, desired-state revision, campaign target set or model-pack changes after submission fail closed;
- PH-4 accepts only model-resolved typed resources/selectors/values and protocol-specific generated payloads; arbitrary NETCONF RPC XML, RESTCONF URL/body forwarding and arbitrary gNMI protobuf/Set passthrough are not exposed;
- structured transactions persist pre/post hashes/values, verification state, rollback state, idempotency identity and recovery state without storing credentials;
- `RECOVERY_REQUIRED` prevents blind replay when remote state is uncertain; explicit reconciliation/recovery is required;
- desired-state compensating rollback occurs in reverse order and campaign retry identities are stable across crash/re-entry;
- HA DRAINING/DRAINED nodes reject new automation work and relinquish singleton scheduler leadership; this is control-plane coordination, not database HA/failover;
- telemetry persists bounded sanitized JSON/scalar observations and does not persist credential material or unbounded stream buffers;
- custom model packs are validated against path/selector/resource allow-lists and cannot introduce arbitrary URLs, traversal, shell content or generic protocol payloads.

Session idle/absolute expiry remains deliberately deferred security debt and is unchanged.

> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

## Q-1 production qualification security boundaries

- PostgreSQL core backups use only fixed `pg_dump` arguments derived from validated settings; restore uses fixed `pg_restore` arguments. No generic command/option passthrough exists.
- PostgreSQL passwords never appear in argv, returned JSON, logs, or audit detail. When a password is required, Q-1 creates a private temporary directory and mode-0600 `PGPASSFILE`, then removes it after the subprocess exits.
- `PGSSLMODE` follows the configured core `pg_sslmode`; backup/restore is non-interactive (`--no-password`) and fails closed when credentials/tools/TLS policy are insufficient.
- Backup output is atomic, mode 0600, and accompanied by a mode-0600 SHA-256 sidecar. Restore requires an explicit SHA-256 or valid sidecar and fails on mismatch.
- Destructive restore requires the literal confirmation `RESTORE_DATABASE` and refuses the configured active core database as a target. Q-1 intentionally restores only to a separate drill/standby database; promotion is an external controlled database operation.
- The recovery-safe restore branch does not initialize the active core database first, so a failed production core cannot block restoration into a separate recovery target. Because that path cannot rely on the failed DB audit trail, operators must preserve shell/change-ticket evidence for the recovery action.
- AlmaLinux install qualification is deliberately double-gated (`--install` and `NETCONFIG_Q1_ALLOW_INSTALL=1`) to prevent accidental mutation of a non-disposable host.
- Q-1 does not change the explicitly deferred console session idle/absolute expiry policy.

## Current hardening baseline

The built-in console remains stdlib-only. It now supports optional built-in TLS, failed-login throttling keyed by peer IP + normalized username, failed/successful authentication auditing, JSON security/access logs, secure-response headers, health/readiness endpoints, and Prometheus-text metrics. HSTS is emitted only when the built-in server is actually serving TLS.

The enforced CSP is intentionally transitional because the legacy UI still contains inline style attributes and inline event handlers. It enforces restrictive default/base/object/frame/form/connect boundaries while temporarily allowing inline script/style. A stricter nonce-based CSP is emitted in report-only mode so route/template extraction can remove those inline constructs without breaking the console.

## Service credential bootstrap

Preferred unattended vault unlock is systemd `LoadCredential=`. NetConfig reads `$CREDENTIALS_DIRECTORY/vault-master` automatically. A root-controlled `NETCONFIG_MASTER_FILE` is the migration/non-systemd alternative. `NETCONFIG_MASTER` remains supported only as a legacy compatibility path and should not be the production recommendation.

Never put device passwords, SNMP secrets, SMTP credentials, vault plaintext, or private keys in logs, metrics, settings JSON, command-line arguments, or repository files.

## Remediation safety

Remediation now fetches the live configuration immediately before execution, computes a semantic plan against the baseline, emits vendor negations where supported, arms an automatic rollback guard, applies the plan, re-fetches configuration, verifies semantic convergence, and only then cancels/confirms the rollback guard. Platforms without an implemented automatic rollback primitive fail closed for remediation.

Remediation is also fail-closed when the stored baseline was scrubbed. A sanitized baseline is evidence, not an executable desired-state source, and must never be pushed back to a device.

Current automatic rollback support:

- Cisco IOS / ASA / Arista EOS: timed `reload in 5`, cancelled only after verification.
- JunOS: `commit confirmed 5`, confirmed only after verification.
- Cisco NX-OS, Comware, MikroTik, Generic: remediation is blocked until a tested automatic rollback strategy exists.

Real-vendor lab validation remains required before calling these guards production-validated.

## Known security debt — session lifetime (DEFERRED)

**Explicitly deferred:** console sessions currently have no idle timeout or absolute expiry. Session tokens persist in process memory until logout or process restart. This is a known security weakness for an administrative console.

Do not silently change this behavior in the current hardening slice. A future dedicated session-lifecycle change must add, at minimum:

- idle expiration;
- absolute lifetime;
- expired-session cleanup;
- session rotation on authentication / privilege transition where applicable;
- logout/expiry audit evidence;
- tests for expiry, concurrent requests, CSRF behavior, and clock-boundary cases.

Until that work lands, deployments should treat console token theft as valid for the lifetime of the server process and rely on TLS, host access control, short administrative exposure windows, and explicit logout as compensating controls.

## Scoped API tokens

API bearer tokens are separate from console session cookies. Tokens are generated randomly, stored only as SHA-256 hashes, mapped to an existing NetConfig role, constrained by explicit read scopes, and auditable by token name. The plaintext token is returned only once at creation. The fleet inventory/topology/drift/compliance/audit surfaces remain read-only. Diagnostic bundle creation/download and D.5 incident lifecycle operations are narrow operational endpoints, not arbitrary device-configuration APIs. Revoke unused tokens promptly. The server refuses bearer-token authentication over cleartext non-loopback HTTP; use built-in TLS or a loopback reverse-proxy backend.

## Syslog-triggered collection boundary

The UDP syslog receiver is disabled by default, bounded by queue size/message size, and defaults to non-privileged udp/5514. A configuration-change event triggers collection only when the UDP peer source IP exactly matches an inventory device. Deployments using relays/NAT must not assume embedded syslog host fields are trusted; trusted-relay identity validation is future work.


## Diagnostic Bundle Security Boundary

Support bundles must be treated as sensitive operational artifacts. The D.5 foundation applies redaction before export and records a redaction report. Future bundle extensions must preserve exclusion of passwords, tokens, SNMP communities, vault secrets, OAuth secrets, and private keys.


## Slice D.5 Phase 3B — Diagnostic API Foundation (2026-09-10)
- Added read-only debug bundle API foundation.
- Added debug:create and debug:read API token scopes.
- Bundle creation remains secret-redacted and audited.
- Status: IMPLEMENTED_TESTING_DEFERRED.
- Deferred: Diagnostics UI, download workflow, incident correlation, protocol trace capture.


## D.5 Phase 3D — Enterprise Diagnostic Operations

Status: IMPLEMENTED_TESTING_DEFERRED

Added secure debug bundle download API foundation, debug:download scope, RBAC/audit integration. Deferred: incident workflow, signed manifests, retention scheduler UI.


## D.5 Phase 4A incident security boundary

Incident records are operational metadata and may themselves be sensitive. The Phase 4A API therefore separates `incident:read` from `incident:write`; write scope requires an operator-or-higher token role both when a token is created and again at HTTP request time. Incident writes are constrained to validated model operations rather than arbitrary SQL or filesystem access.

Diagnostic bundle association is name-based only. A linked bundle must be a single basename ending in `.tar.gz` and must exist beneath the managed NetConfig `debug-bundles` directory when used through the production Manager. Paths such as `../bundle.tar.gz` are rejected. Linking does not copy, decrypt, or inspect bundle payloads.

All incident create/update/status/link/unlink actions append audit evidence containing actor, incident ID and bounded metadata; they must not contain credentials or bearer tokens. Timeline aggregation, support-case export and evidence signing are deliberately deferred so Phase 4A does not create an unreviewed evidence trust model. Console session expiry remains unchanged/deferred.


## D.5 Phase 4B incident timeline security boundary

Incident evidence correlation is reference-only. `incident_evidence_links` stores source type/reference plus bounded link metadata; it does not persist copied syslog messages, audit detail, compliance reports, device configuration text, credentials, or bearer tokens. Supported source types are a fixed allow-list (`audit`, `syslog`, `collection`, `compliance`, `drift`) and are resolved with fixed queries rather than caller-provided table/SQL names.

Evidence is existence-validated at link time. Drift references additionally require bare archived configuration filenames and are resolved through `ConfigStore.read_version()` traversal controls. A drift link pins immutable baseline/current archive stamps so later collections cannot silently rewrite the historical comparison. If retention or an administrator later removes an authoritative source, the incident timeline retains the reference and marks it unavailable rather than manufacturing replacement evidence.

Timeline/evidence reads require `incident:read`. Evidence link/unlink requires `incident:write` plus operator/approver/admin role through the same double-check used for other incident mutation. Every link/unlink operation emits incident-targeted audit evidence. Phase 4B does not add automatic correlation, case export, signatures, protocol payload capture, or broader filesystem access. Console session expiry remains unchanged/deferred.


## D.5 Phase 4C support-case export security boundary

Support-case export is a distinct sensitive operation. API creation/download requires the dedicated `incident:export` scope and an operator/approver/admin token role; `incident:read` alone may list export metadata but cannot create or download an archive. The CLI remains host-operator authority and all create/download operations append Incident-targeted audit evidence.

The exporter accepts only diagnostic bundle basenames already linked to the target Incident. Explicitly selected unlinked, traversal-style, or missing bundle names fail closed. Default all-linked export may record a linked-but-retained-away bundle under `missing_linked_bundles`, but it never invents replacement evidence. Case exports are bounded to 32 embedded diagnostic bundles and 512 MiB aggregate diagnostic-bundle input. Download revalidates the managed archive against the durable recorded size and SHA-256; an integrity mismatch fails closed and emits `incident_case_export_integrity_failure` audit evidence.

Case indexes preserve the Phase 4B provenance model: `timeline-references.json` contains only source type/id/link/timestamp/availability fields and `evidence-links.json` contains Incident-owned link metadata/reference pointers. Raw authoritative syslog messages, external audit details, compliance report bodies and device configuration contents are not copied into these indexes. Linked diagnostic bundles are copied byte-for-byte as opaque `.tar.gz` files and are not extracted or rewritten.

Phase 4C originally provided SHA-256 integrity only. Phase 4D now adds optional Ed25519 manifest signatures and independent signer-fingerprint trust pins; private signing material remains outside exported evidence and NetConfig state. Free-text Incident/case metadata applies bounded credential-assignment redaction before export, but operators must still treat case exports as sensitive restricted data. Console session idle/absolute expiry remains deliberately deferred and unchanged.


## D.5 Phase 4D evidence-signing security boundary

Phase 4D uses the system OpenSSL binary through fixed argument vectors and never executes a configured shell command. Only Ed25519 private keys are accepted. The private key is resolved from `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem` first or `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE` second, must be a regular non-symlink file, is size-bounded, and must have no group/world permission bits. NetConfig never copies the private key into SQLite, `settings.json`, audit details, support bundles, case exports, or release artifacts.

A signed evidence archive contains `manifest.json`, `manifest.sha256`, `manifest.signature.json`, and `manifest.public.pem`. Verification is extraction-free: archive paths are validated, links/devices are rejected, the archive must have one top-level root, unexpected regular files are rejected, every manifest payload is streamed through SHA-256 and size validation, the manifest digest is checked, and then the Ed25519 signature is verified.

The embedded public key is convenience material, not a trust anchor. A cryptographically valid signature returns `trusted=false` unless its SHA-256 SubjectPublicKeyInfo fingerprint matches an independently supplied/configured trust pin. Support-case records also retain the signer fingerprint captured at creation and signed downloads require the archive signer to match that durable record. When configured trust pins exist, signed case download fails closed if none match. Multiple trust pins may overlap during planned key rotation.

Signing is backward-compatible by default: legacy unsigned archives remain usable. Operators may require signed creation per command (`--require-signature`), globally with `NETCONFIG_EVIDENCE_SIGNING_REQUIRED=1`, or via `evidence_signing_required` in settings. A configured but malformed/insecure/wrong-type signing key always fails closed rather than silently producing unsigned output.

Phase 4D does not create certificates, manage a CA, store CA keys, expose arbitrary OpenSSL operations, or claim HSM/KMS attestation. External HSM/KMS signer adapters remain future work if required. Protocol traces are still Phase 4E. Console session idle/absolute expiry remains deliberately deferred.


## D.5 Phase 4E protocol-trace security boundary

Protocol trace capture is opt-in and bounded, not a packet-capture or terminal-recording feature. Sessions require an inventory device and currently support only implemented `cli_ssh` or `snmp` capture providers. TTL is capped at 3600 seconds, event count at 5000 and serialized trace metadata at 8 MiB per session; reaching a budget stops further capture while preserving evidence.

CLI/OpenSSH traces persist command metadata, status, duration and byte counts but never terminal output. Commands matching password/secret/community/key/token patterns are replaced with a fixed `<redacted-sensitive-command>` marker before persistence. No hash derived from the original secret-bearing command is retained. SNMP traces persist target/port/attempt, status, latency and byte counts only; request/response packet bodies, v2c communities and v3 auth/priv material are excluded. General metadata also passes an allow-by-structure redactor for credential-like keys and assignments.

`trace:capture` requires operator-or-higher role; `trace:read` may be delegated independently. Start/stop/expiry/budget events are audited. Trace sessions linked to Incidents are reference-only evidence; case/debug exports include only the sanitized trace records. Historical Phase 4E behavior was provider-not-implemented. PH-3 enables NETCONF/RESTCONF/gNMI metadata trace providers while retaining bounded, secret-safe capture. Console session idle/absolute expiry remains deliberately deferred.


## D.5 Phase 4F Incident Web Console security boundary

The Incident Web Console is a presentation/orchestration layer over the existing Incident, evidence, protocol-trace, diagnostic-bundle and support-case services. It does not add a parallel state store or bypass their validation. All authenticated roles may read the Incident register/detail views; mutation controls are shown and accepted only for operator/approver/admin sessions.

Every browser mutation uses the existing per-session CSRF token. Lifecycle updates are still validated by the Incident state machine. Evidence and bundle links still pass their authoritative existence/path checks. Trace stop additionally verifies the target trace belongs to the Incident named by the form, preventing cross-Incident stop requests. Support-case download calls the existing `record_download()` integrity/signature/trust path before chunked streaming.

Incident-controlled title, description, tags, evidence notes and trace summaries are HTML-escaped before rendering. Regression coverage includes stored markup/XSS payloads and viewer download denial. Phase 4F does not change the explicitly deferred console idle/absolute session-expiry policy.


## D.5 closeout retention safety

Diagnostic maintenance is opt-in and disabled by default. Count-based support-bundle cleanup only operates inside the managed `debug-bundles/` directory. Case-export age cleanup removes only the managed archive file and preserves the durable database record/provenance. Protocol-trace age cleanup excludes ACTIVE traces and every trace linked to an Incident, preventing the generic retention worker from silently destroying Incident evidence. Every maintenance pass writes an audit summary. Session idle/absolute expiry remains separately deferred by project direction.


## Network Intelligence NI-1 correlation security boundary

Endpoint correlation uses read-only SNMP-derived evidence. `ip_neighbors` and `vlan_fdb` contain addresses, interface identifiers, VLAN/FDB identifiers, state/status and timestamps; they do not contain SNMP communities, SNMPv3 authentication/privacy material or raw BER packets. Existing protocol-trace protections remain unchanged.

Correlation is intentionally conservative. Q-BRIDGE FDB IDs are not assumed to equal VLAN IDs; VLAN is emitted only when `dot1qVlanFdbId` supplies a unique mapping. LLDP/CDP-facing ports are marked transit, multiple direct candidates remain `AMBIGUOUS`, and evidence outside the configured freshness budget becomes `STALE`. This avoids turning uncertain forwarding observations into authoritative access-port identity.

The read API uses the separate `endpoint:read` scope. NI-1 adds no remote write/enforcement endpoint. Representative vendor behaviour remains qualification debt.


---

Historical NI-1 documentation snapshot: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. The current baseline is the Q-1 FULL source artifact described by the canonical header.

## Network Intelligence NI-2 identity / impact security boundary

NI-2 treats topology identity as evidence, not authority. Managed-neighbour resolution requires unique normalized identity tokens; token collisions and contradictory observations fail closed to `AMBIGUOUS`. Fuzzy name matching is intentionally not used. LLDP localPortNum is retained as LLDP provenance and is never reinterpreted as IF-MIB ifIndex.

Downstream impact follows only stored `RESOLVED` managed adjacency and uses bounded, cycle-safe traversal. `AMBIGUOUS` and unmanaged observations are excluded. The result is labeled `observed_managed_l2_adjacency`; it must not be represented as routing reachability, STP forwarding state, service dependency, or physical/power dependency. NI-2 is read-only from the API perspective and reuses `topology:read`.

## Network Intelligence NI-3 trap/event security boundary

The NI-3 receiver accepts bounded SNMP v1/v2c Trap datagrams only. Community strings are parsed only to identify the message envelope and are never persisted, logged or exposed through APIs. SNMPv3 traps fail closed until USM authentication/privacy verification exists, and INFORM requests fail closed because no acknowledgement path is implemented. Unknown enterprise traps preserve only the trap OID and allow-listed metadata. Dependency suppression is advisory and follows only NI-2 `RESOLVED` managed-L2 adjacency with bounded depth and TTL; ambiguous or unmanaged edges are excluded. Targeted re-poll is read-only, rate-limited per managed device, and cannot execute configuration changes.


## Network Intelligence NI-4 alert/report security boundary

NI-4 consumes only normalized NI-3 events. Dependency-suppressed events and events below the configured severity floor are not promoted to operational alerts. Maintenance windows suppress promotion only; they do not erase or rewrite the underlying event evidence. `alerts:write` and `reports:write` require operator/approver/admin, while browser writes also require CSRF. SMTP credentials continue to come from the existing vault/OAuth paths and are never persisted in delivery rows. Notification delivery is durable but bounded by a configured maximum-attempt count and exponential-backoff cap. Scheduled reports persist aggregate counts/state summaries only; they do not copy raw SNMP packets, communities, configuration bodies or credential material. The old monitor-rule alert engine remains separate to avoid silent semantic migration. Session idle/absolute expiry remains intentionally deferred.

## PH-1 Web-console CSP and rendering hardening

Every HTML response generates a fresh CSP nonce. Enforced CSP authorizes first-party script/style elements only with that nonce, rejects `script-src-attr` and `style-src-attr`, and retains `default-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`, `form-action 'self'`, no-referrer and no-store boundaries. Server-rendered inline styles are normalized into deterministic generated classes inside one nonce-authorized style element. HTML inline event attributes were removed. PH-1 does not implement idle/absolute session expiry; that debt remains explicitly deferred.

## Platform Hardening PH-2 — PostgreSQL core security boundary

- SQLite remains the default and is explicitly single-node; it must not be represented as HA/distributed storage.
- PostgreSQL core mode is explicit and fail-closed. Driver import, connection, schema bootstrap, or schema-revision failures prevent normal Manager startup rather than silently falling back to SQLite.
- The core PostgreSQL password is needed before the encrypted NetConfig vault can be opened. It therefore comes from a protected file/systemd credential (`postgres-core-password`), with `NETCONFIG_DB_PASSWORD` retained only as a legacy environment fallback. It is never persisted in `settings.json`, audit records, diagnostic bundles, or API responses.
- Operators should use `sslmode=require`, `verify-ca`, or preferably `verify-full` according to their PKI. PH-2 does not disable TLS verification automatically.
- PostgreSQL advisory locks coordinate singleton schedulers only; they are not an authorization boundary.
- Distributed task payloads are application data, not a secret transport. Credentials/tokens/private keys must not be placed in task payload JSON.
- SQLite→PostgreSQL migration refuses a non-empty target by default to prevent accidental live-database merges.
- `/readyz` reports backend/revision/node metadata but never database passwords or connection secrets.


## PH-3 structured southbound security boundary

- Protocol profiles persist only non-secret configuration and vault secret labels. Usernames, passwords, SSH keys/passphrases, client-certificate paths/passwords, and other device credentials are resolved from the encrypted vault at execution time.
- Device hosts are validated as host/IP values; URL-like, userinfo-bearing, path-bearing, multicast, unspecified, and otherwise invalid targets fail closed before structured transport setup.
- NETCONF uses the SSH `netconf` subsystem, bounded server-hello and RPC reads, and safe XML parsing that rejects DTD/entity declarations and excessive depth/node counts. Only fixed internal `<get>` and `<get-config>` requests are emitted; caller-supplied RPC XML, shell/CLI tunnelling, `edit-config`, and generic RPC passthrough are not exposed. Requested datastores must be advertised. Candidate, startup, writable-running, confirmed-commit, rollback-on-error, validate, and xpath are capability evidence, not permission to issue arbitrary writes. Base-1.1-only chunk framing remains explicitly deferred and fails closed.
- RESTCONF is HTTPS-only. TLS verification is mandatory by default; disabling verification requires the explicit lab-only `NETCONFIG_ALLOW_INSECURE_STRUCTURED_TLS=1` environment gate. Optional CA bundles and vault-resolved client certificate/key material are supported. Discovery and data paths are validated against an allow-list; arbitrary URL, host, method, path, query, and body forwarding is not exposed. Content types and JSON/XML body sizes are bounded and validated.
- The only PH-3 structured write primitive is an internal RESTCONF JSON subtree replacement. It is not exposed as generic Web/API/CLI mutation, requires a named actor plus `approved=True` and a post-read verifier, performs pre-read, conditional PUT when an ETag is available, post-read verification, and best-effort pre-image rollback on failure. Unsupported rollback or verification semantics are explicit rather than silently treated as safe.
- gNMI uses an allow-resolved absolute `gnmic` binary for Capabilities, Get, and bounded ONCE Subscribe. Paths use a typed parser; deadlines and response-size limits are enforced. TLS verification is fail-closed by default, CA/mTLS material is resolved at runtime, secret fields exist only in a mode-0600 ephemeral config, and credentials never appear in argv. gNMI Set and arbitrary protobuf/request passthrough are not exposed.
- Structured collection failure is fail-closed by default. CLI fallback requires explicit per-device `allow_cli_fallback`; no automatic downgrade is performed.
- Protocol trace integration remains metadata-only. Request/response bodies, RPC XML, protobuf material, authorization headers, usernames, passwords, tokens, and private-key material are excluded from trace payloads and error strings are secret-redacted.
- `protocol:write` remains operator-or-higher; browser profile changes/collection retain authenticated session RBAC and CSRF. New read endpoints require `protocol:read`.
- Session idle timeout / absolute session expiry remains deliberately deferred and was not changed by PH-3.

PH-3 remains `IMPLEMENTED_TESTING_DEFERRED`: offline/fake-driver evidence does not qualify real NETCONF/RESTCONF/gNMI devices, TLS/mTLS interoperability, packaged `gnmic`, vendor-specific behavior, live PostgreSQL/OpenSSH/Net-SNMP services, or AlmaLinux RPM/systemd deployment.


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
