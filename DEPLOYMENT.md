# Deployment

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## R61 qualification deployment

Production scale claims require a controlled AlmaLinux 10/PostgreSQL qualification environment with representative collectors, protocol inputs and operator/API traffic. Run R61 live gates through `packaging/r61-qualify.sh` with fixed hooks and retain the resulting evidence directory and checksums.

Do not use `LOCAL_SYNTHETIC` benchmark numbers as sizing guidance. R60 lifecycle rollback/recovery controls remain required when installing/upgrading the R61 RPM. R61 itself does not weaken systemd, SELinux, secret handling, approval, rollback or MC-11 execution boundaries.

## R63 HA deployment requirements

Production HA qualification requires PostgreSQL plus at least two fresh ACTIVE NetConfig nodes placed in at least two distinct explicitly configured `cluster_failure_domain` values. Each running process has a unique runtime `instance_id`; duplicated configured `cluster_node_id` is fenced through PostgreSQL. NetConfig does not run PostgreSQL consensus, replication, primary promotion, VIP movement, or PITR; deploy a supported external PostgreSQL HA layer and validate failover with the R63 live hooks.

## R64 deployment security note

Production security qualification requires the designated target deployment and independent `LIVE_ABUSE` hooks. Public-cloud O365 authority is pinned; deployments requiring a sovereign Microsoft cloud must remain unsupported until an explicit reviewed allow-list is implemented. Source-archive executable modes are validated separately from upstream Git-index modes.

## R65 deployment note

R65 adds no new daemon, listener, database migration, or external service. The Operator Journey runs inside the existing web/control-plane process and reads existing persisted state. Production acceptance still requires the designated `LIVE_OPERATOR` qualification environment.

## R66 observability deployment notes

`/metrics`, `/healthz`, and `/readyz` remain local/reverse-proxy-oriented operational endpoints. R66 metrics are aggregate and bounded-cardinality. Production monitoring should scrape through the approved management path and must not treat a successful scrape as proof that deferred live PostgreSQL, HA, protocol, or support-drill gates passed.

## R67 deployment qualification

The package identity is `2.0.0-67`. R67 requires live AlmaLinux 10 RPM/systemd/SELinux fresh-install and R66→R67 upgrade/state-preservation gates before RC qualification. Offline RPM reproducibility is artifact evidence only and does not replace those live deployment gates.
