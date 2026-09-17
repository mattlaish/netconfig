# NetConfig Web Console — Release 34 UI-1

> **Canonical project state — 2026-09-17:** **CURRENT IMPLEMENTATION BASELINE** = **Release 40 / NI-7 L3/VRF Path & Route Dependency Intelligence** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-40`; NI-1 through NI-7 and Enterprise Operations are implemented in source. Q-1 live PostgreSQL/protocol/vendor/device/AlmaLinux gates remain deferred/`NOT_RUN`; Release 40 does not promote them to PASS.
> UI-1 is an operator presentation layer over existing services. It does not create a direct device-write path.

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
