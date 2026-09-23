# NetConfig Web Console — Operations and UI

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

## Release 48 normalized health semantics

Operator health cards may consume normalized sensors instead of reinterpreting raw rows independently. Green/yellow/red/gray presentation maps to `OK` / `WARNING` / `CRITICAL` / `UNKNOWN`. In particular, missing ARP/IP-neighbor evidence on an L2 switch, missing LLDP/CDP evidence, or missing interface rate counters must render as unknown/no data rather than as an outage. Raw MIB/OID rows remain under Advanced/troubleshooting; only known semantic mappers such as Loop Protection become first-class sensors.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.

> UI-1 is an operator presentation layer over existing services. It does not create a direct device-write path.

> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.
## Recorded UX direction — baselines, MIB sensor summaries, and collection

Future user-facing wording should describe `Configuration Baselines` as **Configuration Baselines / Templates & Drift**. The intent is to make clear that a baseline can act as a reusable configuration template and that the system can compare observed/current state against that baseline for drift before any remediation is considered.

Keep Structured Changes, Campaigns, Automation Requests, Device Collection/Protocols, and the MIB Library available for now. The existing approval capability also remains, but this documentation decision does **not** expand approval orchestration.

For MIB/SNMP data, normal operator views should emphasize feature-oriented sensor cards and health indicators derived from existing collected evidence—for example `Loop Protection: enabled ports / loop detected / last event`—rather than presenting raw OID rows as the primary experience. Raw MIB/OID detail remains in Advanced/troubleshooting views. UI visualization should reuse DB/cache evidence by default and must not create higher-frequency polling or broader device walks merely to draw cards or status lights.


## Release 45 — Operator UX Simplification

Release 45 addresses operator usability rather than adding a new Network Intelligence phase. The main navigation no longer exposes a duplicate **Network Intelligence** entry because that function already exists inside **Operations**. `/operations` now opens a task-oriented **Overview** explaining which workflow to use for one-off structured changes, desired state, campaigns, telemetry, intelligence, automation requests, model packs, and HA/DR. The repaired automation ledger is renamed **Automation Requests** to make its purpose explicit.

`/protocols` remains route-compatible but is presented as **Device Collection**: current read protocols are shown first, **Collect now** is the normal action, and NETCONF/RESTCONF/gNMI profile editing is placed under an Advanced disclosure. The MIB library now explains that MIBs are dictionaries rather than product features, surfaces only useful counts and lookup by default, and hides the raw file inventory under Advanced. Per-device SNMP pages likewise hide raw OID walks and vendor MIB values under Advanced sections; normal operational interface, ARP, and MAC/FDB views remain first-class.

There is no schema or public REST contract change. Package release advances to `2.0.0-45` because shipped web/runtime source changed. Status remains `IMPLEMENTED_TESTING_DEFERRED`; NI-7 remains the feature baseline and Q-1 remains open.

**Release 45 qualification on the archive-derived workspace:** repository tests executed in four bounded groups total **221 passed / 8 skipped / 0 failed**; the eight skips are seven live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console regressions cover the Operations overview, single-surface Network Intelligence navigation, Automation Requests HTTP rendering, Device Collection guidance, and MIB purpose/advanced-library presentation. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because the executable is unavailable. The offline RPM builder emitted `netconfig-2.0.0-45.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `91cfea8b74a4c9b65472bafd59852513bf30a1adb9d87f5c6be3023e4a246efd`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.



## Historical Release 43 console refresh

Release 43 restructures the shared console shell so the primary navigation is rendered as a left sidebar instead of a multi-row top bar. The shared `_CSS` theme is refreshed around the supplied green palette and related focus/selection affordances, and the user-visible organization-specific branding in the header/footer is removed in favor of neutral NetConfig branding. No device-write, approval, schema, or REST semantics change.

## Operations navigation

Open **Operations** from the main console navigation. Six panels are available:

- **Structured Changes** — submit typed resource changes for approval, inspect durable TX pre/post evidence, request rollback, and (admin only) reconcile interrupted transactions.
- **Telemetry** — create/edit/enable/disable/delete gNMI subscriptions, capture bounded samples/windows, run due work, prune retention, and inspect scalar time-series summaries/trends.
- **Model Packs** — inspect built-in/custom packs, effective device bindings and allow-listed resources; admins may create/enable/disable/delete custom packs and bind/unbind devices.
- **Desired State** — create/edit DRAFT revisions, clone, publish (approver/admin), inspect plan/drift, submit PUBLISHED apply requests for approval, and inspect run evidence.
- **Campaigns** — create canary/wave rollouts, start/pause/resume/retry/abort, inspect frozen plan/targets, and submit the next wave through change approval.
- **HA / DR** — inspect readiness and heartbeat history; admins manage ACTIVE/DRAINING/DRAINED node lifecycle; operators record/complete recovery-drill evidence.

## Approval invariant

Structured device changes, desired-state apply, structured rollback, and campaign waves always follow:

`submit intent -> frozen snapshot/hash -> separate approval -> snapshot revalidation -> execute -> verify/audit`

The Web UI cannot mark its own request approved and cannot send arbitrary RPC XML, REST bodies, protobuf requests, or shell commands through these structured operations.

## Roles

- `viewer`: read-only Operations views.
- `operator`: create operational objects and submit change approvals.
- `approver`: operator privileges plus desired-state publish and change request approve/execute.
- `admin`: approver privileges plus structured recovery intake/reconciliation, model-pack lifecycle/bindings, and cluster-node state changes.

Every POST requires the existing session CSRF token. Existing CSP nonce processing remains enforced.

## Telemetry edit boundary

A subscription can be edited only when it is not RUNNING. Its bound device cannot be changed in-place; delete/recreate is required so retained samples and audit history cannot be silently reassigned.


NI-6.6 Health Dashboard: IMPLEMENTED_TESTING_DEFERRED

## Network Intelligence / Health dashboard

The main navigation now links directly to Operations → **Network Intelligence**. The dashboard shows active/new/acknowledged/health counts, explicit Capacity/Failure Risk/Health refresh, managed impact simulation, insight filters/search, durable lifecycle controls, analytics job history, evidence JSON and affected-object drill-down. Insight details link to Topology, Endpoints, Events and Telemetry evidence. Viewer sessions remain read-only. The UI never executes a recommendation; action buttons route operators to Structured Changes, Desired State or Campaigns where normal approval applies.

## NI-7 Network Intelligence operations

`/operations?tab=intelligence` now includes explicit L3 route-evidence entry, VRF/path simulation, route-dependency candidate analysis, recent L3 route evidence, and the existing persisted-insight lifecycle. Viewer sessions remain read-only. Operator forms do not perform configuration changes; the page keeps the approved change-workflow boundary visible.

### NetFlow device-form visibility (Release 50 working baseline)

For devices whose type includes `Network`, the edit form shows the **NetFlow** section immediately and offers **collect NetFlow from this device**. The section is hidden for non-network-only devices and updates dynamically when the device-type checkboxes change. This is a UI visibility fix only; it does not add extra device polling or change NetFlow collector behavior.


## 2026-09-22 — UI/CSS regression review

A fresh console review found and corrected cross-cutting presentation regressions introduced by the CSS/theme consolidation: a second `hidden`/`display:none` conflict on the dashboard no-results message; stale custom properties (`--txt`, `--bad`, `--brass`, `--brass2`, `--muted`); checkbox/radio controls inheriting the global 100% input width; dynamic graph markup bypassing theme classes; narrow-screen header wrapping; narrow-screen table overflow; and long Help inline-code overflow. The strict-CSP renderer still converts server-side `style=` attributes into nonce-authorized generated classes, and representative rendered pages were checked to contain zero residual inline-style attributes after transformation. Browser rendering smoke checks at 1440px and 390px showed no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes; Network-device NetFlow remains visible while non-network NetFlow remains hidden.

Focused regression: `tests/test_css_regression_review.py`, `tests/test_ui1_web_console.py`, and `tests/test_platform_hardening_ph1.py` pass together. Full repository evidence must still preserve explicit live/integration skips and must not be promoted to `TESTED` or `RELEASED`.

Final review evidence: focused CSS/WebUI/CSP regression is **27 passed / 0 failed**. Bounded full repository regression totals **248 passed / 8 skipped / 0 failed**. The eight skips are the expected source-archive Git metadata check plus seven explicit live PostgreSQL/backup/protocol-service prerequisites. Representative rendered-page Chromium smoke at 1440px and 390px found no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes. See `CSS_UI_REVIEW_2026-09-22.md`.

## Release 50 MC-2 Sensor transition timeline

The device SNMP health surface now includes **Recent sensor changes** below canonical health cards. It reads durable `sensor_transitions` only and displays time, Sensor type/resource, previous status, and new status. `UNKNOWN` is explicitly described as unavailable evidence, not a failure verdict. Rendering the timeline does not trigger SNMP collection, Sensor refresh, or any other device I/O.

## Release 51 MC-3 Event evidence detail

The Events page now presents normalized domain, severity, event type, affected entity, resource, status, occurrence count, and suppression state. Operators can filter by device and domain. Selecting an event opens a read-only evidence detail panel showing domain, collector/source provenance, entity/resource, status/severity, event time, durable evidence reference, message, and the current related Sensor when available. Rendering this page performs no device collection and does not mutate Sensor state.

## R51-HF1 interactive Topology console

`/topology` now uses an inline dependency-free SVG graph rather than requiring managed devices to appear only through LLDP/CDP rows. Every managed inventory device receives a node. Node state distinguishes `OBSERVED`, `INFERRED`, and `UNKNOWN`; observed LLDP/CDP edges and inferred FDB/MAC paths use separate line styles and evidence labels.

Operators can drag nodes, pan the background, zoom with the mouse wheel, reset the viewport, and clear the saved layout. Layout coordinates are stored only in browser `localStorage` under `netconfig-topology-layout-v1`; moving a node never asserts or modifies a network relationship. The page also retains evidence and identity tables and keeps downstream impact limited to observed direct topology evidence.

