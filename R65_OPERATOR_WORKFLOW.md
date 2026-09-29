# R65 — Operator Workflow Completion

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Purpose

R65 closes the operator continuity gap without introducing a second workflow or execution authority. It composes existing persisted Incident, MC-9 investigation, evidence, NI-7/MC-11 path analysis, MC-11 Structured Change proposal, Automation Request, approval, Structured Change, verification/recovery/rollback, audit, and change-event evidence into one bounded journey. Opening or refreshing the journey does not poll a device.

## Persisted journey

`Dashboard → Incident → Hypothesis → Evidence → Topology Path → Proposed Change → Approval → Structured Change → Validation → Post-change Evidence`

- An optional `incident_ref` binds an MC-11 plan to an existing Incident and becomes part of the persisted planning input/key.
- A workflow submission references `incident_ref + plan_id + proposal_index`; the automation intent must normalize exactly to that persisted proposal or submission fails.
- Approval and execution reuse the existing Automation Request and frozen-snapshot revalidation path.
- Structured Change success still requires exact post-write verification. Recovery and rollback retain their existing authority and controls.
- Final change-event evidence is linked back to the originating Incident only after the execution event is persisted. Evidence-link failure is audited and never rewrites an already committed network transaction result.

## Read model and UI

The read-only `OperatorWorkflowService` returns schema `r65-operator-workflow-1`. `GET /api/v1/operator-workflows/{incident}` requires `incident:read`, `analytics:read`, and `automation:read`. The Operations Console adds **Operator Journey** with role-aware controls; viewers are read-only, operators can create an incident-linked plan and submit the exact persisted proposal, approver/admin roles retain approval/execution authority, and admin retains recovery reconciliation authority.

## Authority and safety invariants

- No arbitrary CLI, command, RPC, URL, or generic write is introduced.
- Candidate what-if remains read-only and is not verification.
- Root cause is never auto-confirmed.
- Page rendering and read APIs perform no network collection.
- Workflow context cannot substitute a different Structured Change intent.
- R64 security, R63 HA fencing, R62 PostgreSQL concurrency/recovery, and MC-10 bounded-correlation controls remain authoritative.

## Qualification

`qualification/r65_runner.py` uses `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN` and separates `LOCAL_REGRESSION`, `LOCAL_WORKFLOW`, and `LIVE_OPERATOR`. Live hooks are fixed-name scripts; there is no arbitrary command option. `production_operator_workflow_claim` may be true only when all selected required `LIVE_OPERATOR` gates pass. The runner never promotes the release to TESTED or RELEASED.

The persisted schema revision remains `mc11-topology-change-planning-1`; R65 adds no database table migration.

## Source qualification closeout — 2026-09-24

Source-tree regression is **508 collected / 494 PASS / 14 SKIP / 0 FAIL** using the deterministic five-way bounded partition. R65 focused coverage is **10/10 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, R65 runner `py_compile`, packaging/hook shell syntax, and legacy selftest are PASS. The initial R65 campaign is **4 local PASS / 0 FAIL / 10 BLOCKED_ENVIRONMENT / 0 NOT_RUN / 0 LIVE_OPERATOR PASS**; `production_operator_workflow_claim=false`. The nested full-regression gate is intentionally represented by the separately executed deterministic five-group evidence in `FULL_REGRESSION.md`, not by a timeout-derived result.

The final source artifact structural gate is **385 entries / 0 duplicates / 0 unsafe paths / 0 symlinks / CRC PASS / 385/385 source-to-clean-extract byte+mode parity / 383/383 R65 source manifest / 384/384 whole-tree SHA256SUMS / 30/30 required executable modes at 0755**. External/upstream Git-index `100755` remains unclaimed until the mode-only patch is committed in the actual repository and verified from a fresh clone.
