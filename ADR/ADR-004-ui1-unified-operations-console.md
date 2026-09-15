# ADR-004 — UI-1 Unified Automation & Operations Console

**Date:** 2026-09-13  
**Status:** Accepted / implemented in Release 34

## Context

Release 33 implemented PH-4 structured transactions, NI-5 telemetry, VM-1 model packs, NA-1 desired state, NA-2 campaigns and HA-1 recovery controls. Their CLI/API/service capabilities were not represented by one complete Web operator workflow.

## Decision

Add a dedicated `WebOpsMixin` in `web_ops.py` and expose `/operations` with six panels. Keep `web.py` as the routing/session shell so the PH-1 `<4000 lines / <240 KB` structural gate remains enforceable.

Network-changing UI operations do not call southbound adapters directly. They submit the existing durable automation change-request intents; approval and execution continue to freeze and revalidate resolved snapshots/hashes. Recovery/model/cluster lifecycle operations retain the same role restrictions as service/API paths.

Telemetry edit is added as a service/API contract, but device rebinding is prohibited in-place.

## Rejected alternatives

- Direct browser execution of structured changes — rejected because it bypasses separation of duties and frozen approval evidence.
- Re-expanding `web.py` with all UI-1 rendering/actions — rejected because it reverses PH-1 structural hardening.
- UI-only authorization/hiding controls — rejected; backend/service authorization remains authoritative.
- In-place telemetry device reassignment — rejected because historical samples/audit evidence would become ambiguous.

## Consequences

UI-1 can evolve independently of the legacy Web monolith, but it must preserve CSRF/CSP/RBAC and approval invariants. Live device/service qualification remains a separate Q-1 concern; offline UI tests cannot promote the phase to `TESTED` or `RELEASED`.
