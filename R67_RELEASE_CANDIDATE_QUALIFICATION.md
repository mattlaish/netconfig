# R67.2 — Release Candidate / Full Artifact Qualification

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current candidate applicability — 2026-10-13

The current working tree includes corrective runtime and documentation changes after the R67.2 freeze. The earlier exact-candidate fingerprint and its live evidence do not qualify these bytes. Current source/spec release remains `2.0.0-67.2`; selecting a new release identity is pending explicit user decision.

The next campaign requires a newly frozen artifact, regenerated/verified metadata and all twelve mandatory LIVE_RC gates against that fingerprint, followed by R68 review. Q1/Q2 and R60–R66 tools/contracts remain reusable within their declared release-specific boundaries; older gate outcomes do not transfer automatically. Fresh SQLite login and PostgreSQL bootstrap, supported upgrade preservation, real exporter/vendor behavior, browser device-type/profile administration and R64 managed-session behavior belong in applicable candidate acceptance.

Documentation synchronization establishes no new runtime/live PASS and does not promote `IMPLEMENTED_TESTING_DEFERRED`.

Status: `IMPLEMENTED_TESTING_DEFERRED`  
Package: `2.0.0-67.2`  
Persisted schema: `mc11-topology-change-planning-1` (unchanged)

## Feature freeze and authority boundary

The original R67.2 corrective R67 candidate added qualification/release-engineering plus the documented fresh database/bootstrap hardening only. It does not add a new product feature, network execution path, device command, approval bypass, polling path, workflow engine, HA authority, security exception, or Monitoring/Correlation slice. MC-11 remains final and MC-12 is not defined.

Any source, package, manifest, SBOM, executable-mode contract, or release-metadata change after an R67.2 qualification run invalidates that run for RC purposes. A new candidate fingerprint and complete required-gate rerun are required; results from an earlier candidate are not transferable.

## Local artifact gates

R67.2 locally verifies release/schema/freeze identity, focused R67.2 tests, the complete bounded repository regression, retained MC-11 authority, release-manifest/SPDX consistency, deterministic offline RPM rebuilding, independent RPM verification, repository/package hygiene, source executable modes, compile/syntax/selftest, clean extraction, source-to-extract byte/mode parity, archive CRC/path/symlink safety, source manifest and whole-tree checksums.

These are `LOCAL_REGRESSION` or `LOCAL_ARTIFACT` evidence. They do not satisfy `LIVE_RC`.

## Required LIVE_RC matrix

A release-candidate qualification claim requires all twelve fixed live gates against the same candidate fingerprint: independent clean checkout/CI; AlmaLinux 10 RPM/systemd/SELinux fresh install; supported R66/R67/R67.1 installed state → R67.2 upgrade and state preservation; backup/restore/rollback; PostgreSQL migration/concurrency/outage/recovery; multi-node HA/failure-domain fencing; real protocol/vendor devices; production scale/performance; independent security/abuse assessment; independent browser/operator acceptance; supportability drill; and MC-11 approved change/verification/rollback end-to-end.

Gate states are only `PASS`, `FAIL`, `BLOCKED_ENVIRONMENT`, or `NOT_RUN`. A local simulation, fake driver, SQLite test, offline RPM, or previous-release result is never a `LIVE_RC` PASS.

## Release decision boundary

Even a complete R67.2 `release_candidate_qualified=true` result does not set `RELEASED` and does not make the production decision. R68 owns the explicit v2 production release decision after reviewing the exact R67.2 candidate evidence and any remaining operational/legal/deployment conditions.
