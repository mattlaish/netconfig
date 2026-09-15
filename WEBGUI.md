# NetConfig Web Console — Release 34 UI-1

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.
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
