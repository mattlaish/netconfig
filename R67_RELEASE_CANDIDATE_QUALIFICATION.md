# R67 — Release Candidate / Full Artifact Qualification

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

Status: `IMPLEMENTED_TESTING_DEFERRED`  
Package: `2.0.0-67`  
Persisted schema: `mc11-topology-change-planning-1` (unchanged)

## Feature freeze and authority boundary

R67 adds qualification and release-engineering evidence only. It does not add a new product feature, network execution path, device command, approval bypass, polling path, workflow engine, HA authority, security exception, or Monitoring/Correlation slice. MC-11 remains final and MC-12 is not defined.

Any source, package, manifest, SBOM, executable-mode contract, or release-metadata change after an R67 qualification run invalidates that run for RC purposes. A new candidate fingerprint and complete required-gate rerun are required; results from an earlier candidate are not transferable.

## Local artifact gates

R67 locally verifies release/schema/freeze identity, focused R67 tests, the complete bounded repository regression, retained MC-11 authority, release-manifest/SPDX consistency, deterministic offline RPM rebuilding, independent RPM verification, repository/package hygiene, source executable modes, compile/syntax/selftest, clean extraction, source-to-extract byte/mode parity, archive CRC/path/symlink safety, source manifest and whole-tree checksums.

These are `LOCAL_REGRESSION` or `LOCAL_ARTIFACT` evidence. They do not satisfy `LIVE_RC`.

## Required LIVE_RC matrix

A release-candidate qualification claim requires all twelve fixed live gates against the same candidate fingerprint: independent clean checkout/CI; AlmaLinux 10 RPM/systemd/SELinux fresh install; R66→R67 upgrade and state preservation; backup/restore/rollback; PostgreSQL migration/concurrency/outage/recovery; multi-node HA/failure-domain fencing; real protocol/vendor devices; production scale/performance; independent security/abuse assessment; independent browser/operator acceptance; supportability drill; and MC-11 approved change/verification/rollback end-to-end.

Gate states are only `PASS`, `FAIL`, `BLOCKED_ENVIRONMENT`, or `NOT_RUN`. A local simulation, fake driver, SQLite test, offline RPM, or previous-release result is never a `LIVE_RC` PASS.

## Release decision boundary

Even a complete R67 `release_candidate_qualified=true` result does not set `RELEASED` and does not make the production decision. R68 owns the explicit v2 production release decision after reviewing the exact R67 candidate evidence and any remaining operational/legal/deployment conditions.
