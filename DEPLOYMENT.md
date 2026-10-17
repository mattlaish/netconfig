# Deployment

## Operator-facing wording refresh — 2026-10-17

This is a source-only console wording update. No RPM was built or installed.
Deploy the rebuilt, validated package to see it on an installed console;
editing this Windows source does not update the running AlmaLinux service.

Release identity stays `2.0.0-67.2`, state `IMPLEMENTED_TESTING_DEFERRED`. The
current source bytes changed: earlier candidate hashes/manifests/SBOM do not
qualify this update. Regenerate them at the next user-approved candidate freeze
and run the required LIVE_RC gates; no new feature phase or release is declared.

## Web UI control coverage corrective — 2026-10-16

The R67.2-based working tree now closes five console coverage gaps. Status remains `IMPLEMENTED_TESTING_DEFERRED`; package identity remains `2.0.0-67.2` pending the user's release decision.

- **Users:** admins can enable, disable and delete accounts from `/users`. Console changes protect the current account and the last enabled admin; SQLite transactions and a PostgreSQL transaction advisory lock serialize access changes. Existing managed sessions reject deleted/disabled accounts on their next request. Password-reset inputs are masked.
- **Device Collection:** approvers/admins can remove a saved protocol profile; inventory and vault secrets are retained and default collection is restored. Operators and above can explicitly run Capabilities, Read state and bounded gNMI Subscribe once. Collection now checks the existing `collect` capability. Page loads do not initiate protocol I/O.
- **Diagnostics:** admins can create full or per-device captures, request a signature, verify archive signature/trust, view effective signing status and clean up older managed bundles with a minimum keep count of one. Signature validity and trusted-signer status are displayed separately. Device captures create their missing security subdirectory; cleanup uses file modification time across full/device archive prefixes.
- **Settings → Evidence signing:** admin-only policy controls for `evidence_signing_required` and `evidence_trusted_fingerprints`; validated/normalized SHA-256 pins are saved only after all inputs pass. Environment policy overrides remain visible and environment-added pins are not copied into settings. Private keys remain outside the Web UI.
- **Protocol Traces:** standalone `/traces` navigation, device/status filters, session detail and bounded event view. Operators and above can start/stop captures with TTL/event/byte budgets and optional Incident linkage. Viewers can read but cannot capture.

All new console POST routes use session authentication, existing role checks and CSRF protection. Network configuration writes remain behind the existing approval chain; no schema or public bearer-REST contract changes are introduced. `web_feature_controls.py` holds the additional controls and preserves the PH-1 `web.py` structural limits.

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current packaging and qualification disposition — 2026-10-13

The source/spec identity remains `2.0.0-67.2`, with unnumbered runtime and documentation correctives after the prior freeze. Release numbering awaits the user's decision. Building these sources does not reproduce the earlier frozen R67.2 artifact or inherit its qualification. Old release-specific filenames/commands below are historical examples; verify the actual build output and RPM metadata for the candidate being installed.

Packaged JSON SNMP profiles reside under `/usr/share/netconfig/snmp-profiles`; administrator/runtime overlays use `/etc/netconfig/snmp-profiles` and `$NETCONFIG_HOME/snmp-profiles`. October console administration manages runtime profiles while preserving built-in defaults. Ordinary RPM installation remains SQLite-first; fresh Core PostgreSQL requires the documented psycopg 3/bootstrap workflow.

Before candidate qualification, regenerate applicable release/source manifests, SPDX SBOM and checksums, then verify the new artifact. Packaged Markdown changes affect payload bytes. This documentation pass leaves generated JSON/SHA artifacts untouched so earlier frozen evidence is not silently rewritten. Canonical AlmaLinux build/install/upgrade/systemd/SELinux and all other LIVE_RC gates require the exact new candidate; offline helper verification alone does not qualify deployment. Git remains user-managed.

> **2026-09-29 development update — SNMP Vendor Profile framework:** this working tree adds a data-only, hot-reloadable SNMP Vendor Profile engine on top of the refrozen R67.2 source line. This is a runtime/package payload change, so the previously frozen R67.2 exact-candidate fingerprint and candidate-bound `LIVE_RC` evidence do **not** qualify this working tree. The release identity has intentionally **not** been advanced; that remains an explicit user decision. Project state remains `IMPLEMENTED_TESTING_DEFERRED`; MC-11 remains the final Monitoring / Correlation / Change-Planning feature slice; no MC-12 and no new network-write authority are introduced. Profiles are JSON data, validated fail-closed, bounded to declared numeric OID roots, and cannot execute Python, shell, commands, URLs, or arbitrary expressions.

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

The package identity is `2.0.0-67.2`. R67.2 requires live AlmaLinux 10 RPM/systemd/SELinux fresh-install plus the supported prior-installed-state → R67.2 upgrade/state-preservation gates before RC qualification. Offline RPM reproducibility is artifact evidence only and does not replace those live deployment gates.
