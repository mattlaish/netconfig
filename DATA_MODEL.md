# Data Model

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current corrective architecture — 2026-10-13

JSON Vendor Profiles declare validated numeric collection roots and scalar/table mappings. Matching profiles use bounded SNMP collection, normalize to existing canonical Sensors and retain legacy bounded MIB collection when no profile matches. Profiles cannot execute code, commands or URLs. The October Web UI adds registry management, using the same role/CSRF and JSON validation boundaries.

`Inventory.get_by_host()` backs ingestion-source lookup; `_inventory_with_sysname()` joins one bulk facts snapshot to inventory for topology identity/graph analysis. NetFlow diagnostics expose existing exporter/decoder evidence and add no parser support for IPFIX. Application-only save handling removes management settings and stores a neutral platform; managed System/Network behavior remains.

No database schema or public REST contract is changed by these correctives. Schema remains `mc11-topology-change-planning-1`; network writes remain behind existing approval, execution-time validation, verification and audit. Site Edge/Collector runtime is future scope.

> **2026-09-29 development update — SNMP Vendor Profile framework:** this working tree adds a data-only, hot-reloadable SNMP Vendor Profile engine on top of the refrozen R67.2 source line. This is a runtime/package payload change, so the previously frozen R67.2 exact-candidate fingerprint and candidate-bound `LIVE_RC` evidence do **not** qualify this working tree. The release identity has intentionally **not** been advanced; that remains an explicit user decision. Project state remains `IMPLEMENTED_TESTING_DEFERRED`; MC-11 remains the final Monitoring / Correlation / Change-Planning feature slice; no MC-12 and no new network-write authority are introduced. Profiles are JSON data, validated fail-closed, bounded to declared numeric OID roots, and cannot execute Python, shell, commands, URLs, or arbitrary expressions.

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
