# R67.1 — Release UI / Authority Consolidation Corrective RC

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

Status: `IMPLEMENTED_TESTING_DEFERRED`.

R67.1 is a corrective release-candidate rebuild after the full-file/operator-surface audit of the frozen R67 candidate. Because R67 evidence was bound to exact candidate bytes, these fixes intentionally invalidate the old R67 candidate fingerprint and require a new RC qualification campaign. R67.1 does not create MC-12 and does not add network-write authority.

## Authority consolidation

Legacy immediate execution is now read-only. `Manager.run`, Device **Run command**, Web **Run now**, `Workflow.run_adhoc`, and CLI `bulk` accept only bounded, non-chained `show`, `display`, `get`, or exact `/export` commands. Ad-hoc `config`, `remediate`, and `save` fail closed. Configuration mutation remains available through the durable Change Request / Automation Request / Structured Change approval, frozen-snapshot revalidation, execution, verification and recovery paths.

## Console consolidation

- `/alerts?view=reports` is the canonical operational-report schedule surface; legacy `/op-alerts` is a compatibility redirect instead of a second alert console.
- Settings → Integrations includes admin API-token create/list/revoke. Raw tokens are displayed once in the create response and never placed in URLs or persisted in plaintext.
- Diagnostics exposes the read-only R66 Supportability snapshot to authenticated viewer/operator roles. Support-bundle create/download remains admin-only.
- Operations → HA / DR exposes distributed-task recovery state. Only admin can requeue a task, and the database authority still permits requeue only from `RECOVERY_REQUIRED` when `replay_safe=true`; claim generation remains monotonic.

## Documentation truth

At the R67.1 checkpoint, README/ROADMAP/SECURITY/handoff headers identified R67.1 as the active corrective RC. Historical release sections remain historical evidence and are explicitly subordinate to the current-state header. R64 session idle/absolute expiry is current truth (30-minute idle, 12-hour absolute, with authoritative user-state revalidation); older statements saying it remains deferred are historical only.

## Qualification boundary

R67.1 has its own candidate fingerprint and fixed `LIVE_RC` matrix. Local regression, deterministic packaging and artifact integrity cannot substitute for live AlmaLinux/systemd/SELinux, upgrade, PostgreSQL, HA, real protocol/vendor device, scale, independent security/browser/supportability, Git fresh-clone executable-mode, or MC-11 end-to-end evidence. R68 must be rerun against the exact R67.1 candidate after all mandatory live gates pass.
