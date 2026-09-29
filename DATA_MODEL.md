# Data Model

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

R61 introduces **no persisted production schema changes**. Existing durable entities remain authoritative, including devices, endpoint/L2 evidence, NI-7 route/interface observations, service/dependency context, incidents/evidence links, MC-7 hypotheses, MC-8 external evidence, MC-10 correlation runs, and MC-11 change-planning evidence/plans.

R61 qualification evidence is external artifact data (`campaign.json`, metrics JSON, logs and SHA256SUMS) and is not written into product operational tables. Synthetic benchmark records use an isolated temporary database and are never imported into production state.

## R63 additive HA fields

`cluster_nodes` adds `failure_domain` and `instance_id`. `distributed_tasks` adds `claim_generation`, `claim_token`, `claimed_instance`, `replay_safe`, and `recovery_reason`. These are additive migrations under the existing `mc11-topology-change-planning-1` schema-revision contract; no MC-12 schema identity is introduced. `RECOVERY_REQUIRED` is the fail-closed state for an expired partial claim.

## R65 persisted workflow context

No new table or schema revision is introduced. Existing MC-11 plan input may persist `incident_ref`; existing Automation Request payloads may contain a bounded/hash-protected `context` with `incident_ref`, `plan_id`, and `proposal_index`. Existing Incident evidence links and change-event records close the post-change chain. Schema revision remains `mc11-topology-change-planning-1`.

## R66 data-model note

R66 adds no persisted schema revision. `r66-supportability-1` is a transient read model derived from existing tables/runtime state; the canonical persisted schema remains `mc11-topology-change-planning-1`.

## R67 data-model status

No persisted entity, column, index, migration, or schema revision is added. The persisted schema remains `mc11-topology-change-planning-1`. R67 release manifests, SPDX SBOM and qualification evidence are release artifacts, not product database entities.
