# NetConfig Monitoring / SOC + NOC Correlation Implementation Slices

**Baseline:** NetConfig Release 48 (`2.0.0-48`)\
**Baseline status:** `IMPLEMENTED_TESTING_DEFERRED`\
**Baseline source:**
`netconfig-2.0.0-48-sensor-model-evidence-normalization-v25.zip`\
**Purpose:** Evolve the current Sensor / Operational Event / Alert /
Incident / Network Intelligence foundation into an Infrastructure
Monitoring + Configuration Assurance + SOC/NOC Correlation platform
without replacing the existing architecture or introducing uncontrolled
device writes.

> Product direction: **Monitor what is running. Detect what changed.
> Correlate what happened. Understand why.**

## 1. Current code baseline

The Release 48 source already contains the principal foundations that
this roadmap must reuse rather than replace:

-   `opt/netconfig/netconfig/sensor.py` --- normalized current-state
    Sensor model and generator.
-   `opt/netconfig/netconfig/manager.py` --- SNMP/device collection
    orchestration; `snmp_poll()` is the main evidence persistence path.
-   `opt/netconfig/netconfig/web_api.py` --- `/api/v1/sensors` and other
    REST endpoints.
-   `opt/netconfig/netconfig/web_ui.py` --- device/SNMP health
    rendering, including `render_snmp_health_summary()`.
-   `opt/netconfig/netconfig/monitor.py` --- existing
    service/HTTP/port/TLS monitoring and legacy alert path.
-   `opt/netconfig/netconfig/operational_events.py` --- normalized
    operational events.
-   `opt/netconfig/netconfig/operational_alerts.py` --- operational
    alert lifecycle.
-   `opt/netconfig/netconfig/incidents.py` --- incidents, evidence
    linking, timeline and diagnostics.
-   `opt/netconfig/netconfig/analytics/impact.py` --- bounded managed
    dependency/impact analysis.
-   `opt/netconfig/netconfig/analytics/l3.py` --- VRF/L3 path and route
    dependency intelligence.
-   `opt/netconfig/netconfig/db.py` --- persistent schema.
-   `opt/netconfig/netconfig/web.py` --- current navigation and Alerts /
    Events / Ops Alerts / Incidents UI.

Current architectural inconsistency to correct first:

``` text
Raw evidence ──→ SensorEngine ──→ Sensor API
      │
      └────────────────────────→ WebUI recalculates health independently
```

Target:

``` text
Raw evidence
    ↓
Sensor Engine
    ↓
Canonical Sensor Snapshot
    ├── WebUI
    ├── API
    ├── Alert/Event pipeline
    └── Correlation pipeline
```

No slice may increase device polling frequency merely to support UI or
correlation. Existing evidence must be reused wherever possible.

------------------------------------------------------------------------

# MC-1 / Release 49 --- Sensor Integration Unification

**Goal:** Make SensorEngine the canonical health truth source for API
and WebUI.

**Expected status after implementation:** `IMPLEMENTED_TESTING_DEFERRED`
until live qualification is complete.

## Runtime changes

### `manager.py`

Modify `snmp_poll()` so that after existing evidence has been persisted
successfully, SensorEngine refreshes the affected device.

Required flow:

``` text
SNMP collection
→ persist facts/interfaces/FDB/ARP/IP-neighbor/topology/MIB evidence
→ refresh canonical sensors
→ return poll result
```

Failure flow must also refresh sensors after reachability/poll failure
state is persisted:

``` text
poll failure
→ persist failure/reachability evidence
→ refresh sensors
→ return/raise existing failure semantics
```

Requirements:

-   No additional SNMP GET/WALK solely for Sensor generation.
-   Sensor generation reads persisted evidence/cache.
-   Sensor refresh failure must not silently turn a successful
    collection into fabricated healthy state.
-   Existing collection evidence remains authoritative input.

### `web_api.py`

Change `GET /api/v1/sensors` into a read-only endpoint.

Remove request-time behavior equivalent to:

``` python
manager.sensors.refresh_inventory_health(...)
```

GET must only read the current canonical Sensor snapshot.

Requirements:

-   GET must not mutate `sensors`.
-   GET must not change `updated_at`.
-   Preserve existing supported filters and response compatibility.
-   Add explicit filters only if runtime implementation and tests agree;
    do not document unimplemented filters.

### `web_ui.py`

Refactor `render_snmp_health_summary()`.

Stop independently deriving health from raw:

-   interfaces
-   MAC/FDB
-   ARP/IP-neighbor
-   topology neighbors
-   MIB values/poll state

Use SensorEngine output for semantic health cards.

Expected mappings:

  -----------------------------------------------------------------------
  UI card                             Sensor input
  ----------------------------------- -----------------------------------
  Reachability                        `device.reachability`

  Polling                             `device.polling`

  Interface health                    `interface.status`,
                                      `interface.utilization`,
                                      `interface.errors`,
                                      `interface.discards`

  FDB/MAC evidence                    `endpoint.fdb_evidence`

  L3 evidence                         `endpoint.arp_evidence`

  Topology                            `topology.neighbor`,
                                      managed/unmanaged counts

  Loop Protection                     `loop_protection.health`
  -----------------------------------------------------------------------

Raw MIB/OID remains available under Advanced/Troubleshooting and is not
removed.

### `sensor.py`

Keep the current normalized status vocabulary:

``` text
OK
WARNING
CRITICAL
UNKNOWN
```

Do not add historical persistence in this slice.

Add helper/query methods only if needed to make UI consumption
deterministic and avoid duplicating interpretation logic.

## WebUI changes

Keep the existing Health Card concept but make cards Sensor-backed.

Example:

``` text
Interface Health
46 OK · 2 Warning · 0 Unknown
Peak utilization: 71%
Interfaces with errors: 2
```

For absent L3 evidence:

``` text
L3 Evidence — UNKNOWN
No local ARP/IP-neighbor evidence.
This may be normal for a pure L2 switch.
```

Do not render missing evidence as a fault.

## Tests

Add/extend:

-   `tests/test_sensor_model.py`
-   `tests/test_sensor_api.py`
-   focused WebUI tests
-   manager/poll tests where existing fixtures allow

Mandatory assertions:

1.  Poll persistence causes Sensor snapshot refresh.
2.  Poll failure updates relevant sensor state.
3.  Sensor API GET does not mutate DB state/timestamps.
4.  UI card status agrees with Sensor status.
5.  `ip_neighbors=0` remains `UNKNOWN`, never `CRITICAL`.
6.  Missing topology remains `UNKNOWN`.
7.  Missing interface counters do not create fake numeric values.
8.  No new collection/device I/O is introduced by WebUI/API reads.

## Documentation

Update at minimum:

-   `DEVELOPMENT.md`
-   `AI_HANDOFF.md`
-   `ARCHITECTURE.md`
-   `ROADMAP.md`
-   `API.md`
-   `WEBGUI.md`
-   `TESTING.md`
-   `DOCUMENTATION_STATUS.md`

## Exit gate

``` text
Poll → persisted evidence → Sensor → API     PASS
Poll → persisted evidence → Sensor → WebUI   PASS
Sensor API read-only                         PASS
UI/API semantic agreement                    PASS
UNKNOWN semantics                            PASS
Full regression                              PASS
Artifact integrity gate                      PASS
RPM deterministic rebuild                    PASS
```

------------------------------------------------------------------------

# MC-2 / Release 50 --- Sensor History & State Transitions

**Goal:** Preserve when a Sensor changed, not only its latest state.

## Schema changes

Add migration-backed entities, preferably:

### `sensor_observations`

Purpose: bounded historical observation/evidence storage where useful.

Suggested fields:

``` text
id
sensor_key / sensor_id
sensor_type
device
resource
value
unit
status
message
source
observed_at
metadata_json
```

### `sensor_transitions`

Purpose: durable state/value transition evidence.

Suggested fields:

``` text
id
sensor_key / sensor_id
sensor_type
device
resource
previous_status
new_status
previous_value
new_value
source
observed_at
metadata_json
```

Indexes must support:

-   device + time
-   sensor_type + time
-   status + time
-   resource + time

Define retention policy rather than allowing unlimited growth.

## `sensor.py`

Refactor upsert logic:

``` text
new observation
→ compare with canonical current sensor
→ update snapshot
→ if meaningful transition, persist transition
```

Do not emit a transition for:

``` text
OK → OK
same value → same value
```

unless a sensor type explicitly defines a meaningful value-change
threshold.

Transitions must distinguish:

-   status change
-   value change
-   evidence freshness/expiry change

## API

Add read-only endpoints such as:

``` text
GET /api/v1/sensors/{...}/history
GET /api/v1/sensor-transitions
```

Exact route design must follow existing API conventions and tenant/auth
model.

Support bounded pagination/time filters.

## WebUI

Add an Advanced/History view from a health card or device page.

Example:

``` text
13:02:17  Gi1/0/48  OK → WARNING  UP → DOWN
13:18:42  Gi1/0/48  WARNING → OK  DOWN → UP
```

Do not overload the default Device page with raw history.

## Tests

Cover:

-   no duplicate transition for unchanged state
-   `OK → WARNING`
-   `WARNING → OK`
-   `UNKNOWN → OK`
-   missing evidence/freshness transition semantics
-   restart/replay idempotency
-   retention behavior
-   API pagination/time filtering
-   migration upgrade/downgrade where project policy requires it

## Exit gate

Transition history must be deterministic, bounded, restart-safe and
incapable of generating a transition storm from unchanged polling data.

------------------------------------------------------------------------

# MC-3 / Release 51 --- Normalized Operational Evidence

**Goal:** Establish one cross-domain evidence language before
correlation.

## `operational_events.py`

Extend/normalize the event schema so events can represent domains such
as:

``` text
NETWORK
SECURITY
APPLICATION
DATABASE
STORAGE
SYSTEM
CONFIGURATION
IDENTITY
EXTERNAL
```

Required semantic fields:

``` text
event_type
domain
source
entity_type
entity_id
device
resource
severity
status
observed_at
evidence_ref
message
metadata
```

Preserve current deduplication and bounded/cycle-safe dependency
behavior.

## Sensor → Event bridge

Create events from meaningful Sensor transitions, not every Sensor
refresh.

Examples:

``` text
interface.status OK→WARNING
→ NETWORK / interface.down

device.reachability OK→CRITICAL
→ NETWORK / device.unreachable
```

`UNKNOWN` must not automatically become a critical event.

## `manager.py`

After Sensor refresh, pass only durable meaningful transitions into the
event pipeline.

## Syslog / trap compatibility

Existing operational event ingestion remains supported.

Do not rewrite existing SNMP trap/syslog collectors if normalization can
occur at the event boundary.

## WebUI

Event detail should display:

-   domain
-   source
-   affected entity/resource
-   evidence reference
-   event time
-   current related Sensor status where available

## Tests

Cover:

-   Sensor transition → one normalized event
-   unchanged Sensor → no event
-   recovery transition
-   UNKNOWN handling
-   deduplication
-   existing syslog/trap regression
-   dependency suppression regression

------------------------------------------------------------------------

# MC-4 / Release 52 --- Unified Alert Plane

**Goal:** Converge legacy monitoring alerts and operational alerts
without abruptly breaking compatibility.

## Current issue

Two paths exist:

``` text
monitor.py → alert_rules / alerts
```

and:

``` text
operational_events.py → operational_alerts.py → operational_alerts
```

## Runtime changes

### `monitor.py`

Do not remove HTTP/port/TLS/service monitoring.

Normalize its observations into Sensor/Event semantics, for example:

``` text
service.port_state
application.http_status
application.response_time
application.tls_expiry
```

Meaningful transitions become Operational Events.

### `operational_alerts.py`

Make this the target lifecycle for new normalized alerting.

Preserve:

-   acknowledgement
-   suppression/maintenance behavior
-   auditability
-   severity
-   state transitions

### Compatibility

Existing legacy API/routes/data must remain readable during migration.

If legacy writes remain temporarily, document exactly which path is
authoritative.

No destructive migration until equivalence is proven.

## WebUI

Consolidate top-level operator navigation.

Target:

``` text
Alerts
  Overview
  Active Alerts
  Events
  Maintenance
```

Keep old URLs such as `/events` and `/op-alerts` as compatibility
routes/redirects where practical.

## Tests

Cover:

-   HTTP/port/TLS monitor → normalized event
-   event → operational alert
-   alert lifecycle
-   recovery
-   deduplication
-   legacy route compatibility
-   no double alert for one underlying transition

------------------------------------------------------------------------

# MC-5 / Release 53 --- Incident Evidence & Unified Timeline

**Goal:** Make Incident the durable cross-domain investigation object.

## `incidents.py`

Expand current evidence types beyond:

``` text
audit
syslog
collection
compliance
drift
protocol_trace
```

Add supported references such as:

``` text
sensor_transition
operational_event
operational_alert
change_event
analytics_insight
external_event
```

Evidence references must remain typed and validated.

Do not copy large raw payloads into Incident rows when a durable
evidence reference is sufficient.

## Incident timeline

Create one ordered timeline across evidence types:

``` text
13:02 NDR traffic anomaly
13:04 WAF request anomaly
13:05 DB connection pressure
13:07 host CPU saturation
13:08 API latency breach
```

Handle:

-   late-arriving evidence
-   equal timestamps
-   source clock metadata where available
-   evidence removal/retention safely

## WebUI

Upgrade Incident detail into:

``` text
Incident summary
Impact
Timeline
Related alerts
Related changes
Network evidence
Security evidence
Infrastructure evidence
Raw/advanced evidence
```

At this slice there is still no automatic root-cause verdict.

## Tests

Cover:

-   each evidence type
-   invalid evidence refs fail closed
-   timeline deterministic ordering
-   cross-domain evidence
-   authorization
-   deletion/retention behavior
-   existing diagnostic bundle/protocol trace regression

------------------------------------------------------------------------

# MC-6 / Release 54 --- Service & Dependency Graph

**Goal:** Extend network topology knowledge into explicit service
dependency knowledge.

## New domain model

Add explicit entities/relationships for at least:

``` text
Service
Application
Database
Storage
LoadBalancer
DNS
VM
Hypervisor
```

and typed relationships:

``` text
DEPENDS_ON
RUNS_ON
ROUTES_THROUGH
USES_DNS
USES_DATABASE
USES_STORAGE
PROTECTED_BY
```

Every dependency must have provenance/source and freshness.

Do not infer critical production dependencies solely from temporal
correlation.

## Reuse existing analytics

Integrate, do not replace:

-   `analytics/impact.py`
-   `analytics/l3.py`

Network dependencies remain VRF/path scoped and fail closed under
ambiguity.

Never invent a managed next device from next-hop IP.

## API

Add bounded graph/dependency query APIs.

Must enforce traversal depth/size limits.

## WebUI

Add Service/Dependency view capable of showing:

``` text
Payment API
  ↓
APP01
  ↓
DB01
  ↓
STORAGE01
```

Overlay relevant network path when known.

Clearly distinguish:

-   configured dependency
-   discovered evidence
-   inferred candidate
-   unknown

## Tests

Cover:

-   bounded traversal
-   cycle safety
-   ambiguous paths
-   stale dependency evidence
-   cross-tenant/object authorization if applicable
-   L3/VRF regression
-   impact analytics regression

------------------------------------------------------------------------

# MC-7 / Release 55 --- Deterministic Correlation & Hypothesis Engine

**Goal:** Produce evidence-backed hypotheses without making an LLM or
heuristic engine the blocking authority.

## New module

Add:

``` text
opt/netconfig/netconfig/correlation.py
```

Potential supporting modules may be split if the implementation becomes
large.

## Correlation inputs

Use:

``` text
time proximity
entity identity
dependency relationship
event ordering
configuration-change proximity
Sensor transitions
network/path health
supporting evidence
contradicting evidence
```

## New model: Hypothesis

Suggested fields:

``` text
id
incident_id
hypothesis_type
summary
confidence
initiating_event_ref
first_evidence_at
last_evidence_at
supporting_evidence[]
contradicting_evidence[]
affected_entities[]
rule/version
created_at
updated_at
```

Confidence must be explainable and deterministic for the same evidence
set/rule version.

Do not equate correlation with confirmed causation.

Preferred language:

``` text
Likely
Consistent with
Evidence supports
Possible cause
```

Avoid unsupported:

``` text
Attack confirmed
Root cause proven
```

## Example

``` text
Hypothesis:
Application/API traffic saturation

Supporting:
+ NDR traffic spike occurred first
+ WAF anomaly followed
+ DB connections increased
+ application CPU saturated afterwards

Contradicting:
- no interface congestion
- no packet loss
- no route change
- no recent configuration change
```

## Tests

Cover:

-   deterministic result ordering
-   same evidence → same hypothesis/confidence
-   contradictory evidence lowers/changes confidence
-   unrelated simultaneous events do not correlate merely by time
-   dependency-aware correlation
-   cycle/bounds
-   replay idempotency
-   no unsupported attack verdict

------------------------------------------------------------------------

# MC-8 / Release 56 --- External Evidence Ingestion & Connectors

**Goal:** Accept SOC/NOC evidence from external systems without turning
NetConfig into every source product.

## Initial source categories

Support normalized ingestion for:

``` text
NDR
WAF
SIEM
EDR
APM
Database monitoring
Storage monitoring
Virtualization
Cloud monitoring
```

Implement source adapters incrementally.

## Security boundary

External integrations are read-only evidence ingestion by default.

They do not grant NetConfig authority to:

-   reconfigure WAF
-   modify SIEM
-   execute EDR response
-   change database configuration
-   run arbitrary commands

Any future action plane remains separately permissioned and audited.

## Ingestion API

Add authenticated, rate-limited normalized event ingestion.

Required considerations:

-   source identity
-   idempotency key
-   source event ID
-   timestamp
-   received-at timestamp
-   payload size limits
-   schema validation
-   replay/duplicate handling
-   tenant/source scoping
-   secret redaction

## Connector health

Expose:

``` text
connected
degraded
last evidence received
authentication failure
rate-limited
schema rejection count
```

as operational state, not silent failures.

## WebUI

Settings/Integrations page:

``` text
Source
Status
Last event
Events received
Rejected
Authentication state
```

Raw external payloads belong in Advanced evidence views.

## Tests

Cover malformed payloads, duplicates, replay, auth failure, oversized
payloads, clock skew metadata, unknown source types and secret
redaction.

------------------------------------------------------------------------

# MC-9 / Release 57 --- Operations Correlation Console

**Goal:** Deliver the operator-facing SOC/NOC correlation experience.

## Navigation

Move toward:

``` text
Dashboard
Devices
Topology
Endpoints
Changes
Alerts
Diagnostics
Settings
```

Do not delete compatibility routes merely to simplify navigation.

## Alerts workspace

Tabs:

``` text
Overview
Active Alerts
Events
Incidents
Maintenance
```

## Incident correlation UI

Primary view:

``` text
INCIDENT #2481
Payment API Degradation

Severity        HIGH
Started         13:02
Affected        Payment API

Probable Cause
Application/API traffic saturation

Confidence
82%

Supporting Evidence
✓ NDR traffic spike
✓ WAF abnormal requests
✓ DB connections increased
✓ APP CPU saturation

Contradicting Evidence
✓ No interface congestion
✓ No packet loss
✓ No route change
✓ No recent configuration change

Timeline
13:02 NDR
13:04 WAF
13:05 Database
13:07 Host
13:08 Application
```

Use wording such as `Probable cause` or `Current hypothesis`, not
`Confirmed root cause`, unless the underlying evidence explicitly
confirms it.

## Dashboard

Add operator-level cards such as:

``` text
Active incidents
Services impacted
Critical alerts
Recent changes correlated with incidents
Unhealthy dependencies
External evidence source health
```

Do not turn the Dashboard into raw OID/event tables.

## Tests

Cover:

-   rendering with no correlation
-   one hypothesis
-   multiple hypotheses
-   contradictory evidence
-   UNKNOWN states
-   large timeline
-   escaping/untrusted external evidence
-   permissions
-   old route compatibility

------------------------------------------------------------------------

# MC-10 / Release 58 --- Correlation Production Hardening & Qualification

**Goal:** Make the correlation plane operationally safe at production
scale.

## Runtime hardening

Validate:

``` text
event retention
Sensor history retention
Incident retention
correlation replay
late-arriving events
out-of-order events
clock skew
duplicate external events
worker restart recovery
PostgreSQL concurrency
large topology
large incident timeline
large evidence fan-in
API latency
WebUI latency
```

## Correlation bounds

Hard limits must exist for:

-   time window
-   graph depth
-   graph node count
-   events per correlation run
-   evidence per incident
-   external payload size
-   replay range

Correlation must fail boundedly rather than consume unlimited
CPU/memory.

## Observability

Measure the platform itself:

``` text
event ingest rate
Sensor transition rate
alert creation rate
correlation queue depth
correlation execution latency
dedup count
dropped/rejected event count
connector lag
incident generation rate
```

## Qualification

Run feasible automated/local tests and explicitly leave
real-infrastructure gates as `NOT_RUN` / `DEFERRED` when unavailable.

Production qualification should include real or production-like:

-   AlmaLinux package install/upgrade
-   PostgreSQL
-   systemd
-   SELinux
-   SNMP/device polling
-   syslog/trap
-   external event ingestion
-   restart/recovery
-   retention
-   scale
-   clock skew/out-of-order delivery
-   HA/failover where architecture supports it

No deferred live gate may be reported as passed.

------------------------------------------------------------------------

# Cross-slice engineering rules

These apply to MC-1 through MC-10.

## 1. Evidence semantics

`UNKNOWN` means insufficient/missing evidence, not failure.

Examples:

``` text
L2 switch has no ARP table → UNKNOWN
No topology evidence → UNKNOWN
Missing interface utilization counter → UNKNOWN
```

Never manufacture zero values to replace missing evidence.

## 2. No extra device load for presentation

WebUI, API, Sensor rendering, Incident rendering and correlation must
not initiate extra SNMP polling/walking merely to populate a page.

Collection is separated from consumption.

## 3. Configuration safety

Monitoring/correlation does not gain configuration authority.

Existing Structured Changes / Desired State / Campaign mechanisms remain
the controlled write path.

## 4. Explainability

Correlation output must retain:

``` text
supporting evidence
contradicting evidence
source references
rule/version
confidence
```

An AI/LLM may later summarize or explain evidence, but must not become
the sole blocking incident verdict authority.

## 5. Compatibility

Prefer compatibility routes/migrations over abrupt removal of existing
APIs or UI URLs.

Deprecation must be documented before removal.

## 6. Documentation truth

For every implementation slice update:

-   `DEVELOPMENT.md`
-   `AI_HANDOFF.md`
-   `ARCHITECTURE.md`
-   `ROADMAP.md`
-   `SECURITY.md` when security boundaries change
-   `API.md` when contracts change
-   `TESTING.md`
-   `WEBGUI.md` when operator UX changes
-   `DOCUMENTATION_STATUS.md`

Documentation existence does not count as implementation.

## 7. Slice status

Use only the project's established status vocabulary.

An implemented slice with deferred real-infrastructure gates remains:

``` text
IMPLEMENTED_TESTING_DEFERRED
```

Do not promote it merely because unit tests pass.

## 8. Delivery sequence

Every code-changing slice follows:

``` text
Implementation
→ focused tests
→ full regression
→ documentation sync
→ complete source package
→ Artifact Packaging Integrity Gate
→ deterministic RPM build/verification
```

The delivery must contain the complete modifiable source baseline, tests
and relevant build/deployment files.

## 9. Artifact Packaging Integrity Gate

Before delivery verify the extracted artifact, not only the workspace:

-   clean extraction
-   no path traversal
-   no unsafe symlinks
-   required files exist
-   executable modes are correct
-   syntax checks
-   source ↔ extracted SHA-256 comparison
-   manifest/checksum validation
-   archive CRC
-   extracted-tree regression where feasible
-   RPM/package verifier
-   deterministic rebuild where supported

## 10. Distributed architecture remains separate

The future Site Edge/Collector design for WAN/site survivability remains
a separate roadmap track.

Do not combine distributed consistency, correlation semantics and
Sensor/Event migration into the same slice.

Future site collectors should remain read-only by default and preserve
local alert/store-and-forward behavior without gaining arbitrary
configuration authority.

------------------------------------------------------------------------

# Recommended release sequence

``` text
R48  Sensor Model / Evidence Normalization
R49  MC-1 Sensor Integration Unification
R50  MC-2 Sensor History & State Transitions
R51  MC-3 Normalized Operational Evidence                CURRENT BASELINE
R52  MC-4 Unified Alert Plane
R53  MC-5 Incident Evidence & Unified Timeline
R54  MC-6 Service & Dependency Graph
R55  MC-7 Deterministic Correlation Engine
R56  MC-8 External Evidence Ingestion & Connectors
R57  MC-9 Operations Correlation Console
R58  MC-10 Production Hardening & Qualification
```

The order is intentional: **normalize truth first, preserve history
second, normalize events third, unify alerts fourth, build
incidents/dependencies fifth, and only then perform cross-domain
correlation.**

## Implementation status — 2026-09-23

- MC-1 / Release 49 — `IMPLEMENTED_TESTING_DEFERRED`
- MC-2 / Release 50 — `IMPLEMENTED_TESTING_DEFERRED`
- MC-3 / Release 51 — `IMPLEMENTED_TESTING_DEFERRED`
- MC-4 / Release 52 and later — `PLANNED`

Release 51 implements the MC-3 normalized operational-evidence schema, Sensor-transition bridge, additive migration/backfill, read-only Event filters/detail API, and Event detail UI described below. Release 50 remains the completed MC-2 history/state-transition baseline underneath it.

## Release 51 pre-MC4 compatibility overlay — 2026-09-23

Before entering MC-4, Release 51 receives an implementation-preserving hotfix overlay: standard SNMPv3 AES-192/AES-256 privacy uses the Net-SNMP-compatible Blumenthal extension, topology discovery unlocks Vault credentials in-process, every managed inventory device is represented in the topology graph even without LLDP/CDP, and persisted FDB/MAC correlation may contribute only clearly-labelled non-authoritative `INFERRED` topology evidence. The `/topology` UI is now an interactive drag/pan/zoom canvas with browser-local layout state only. These changes do not advance MC-4, do not add device I/O, and keep MC-4 / Release 52 `PLANNED`.

