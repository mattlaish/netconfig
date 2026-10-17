# Q-1 Production Qualification — Active Track (originated Release 39)

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current candidate applicability — 2026-10-13

The current working tree includes corrective runtime and documentation changes after the R67.2 freeze. The earlier exact-candidate fingerprint and its live evidence do not qualify these bytes. Current source/spec release remains `2.0.0-67.2`; selecting a new release identity is pending explicit user decision.

The next campaign requires a newly frozen artifact, regenerated/verified metadata and all twelve mandatory LIVE_RC gates against that fingerprint, followed by R68 review. Q1/Q2 and R60–R66 tools/contracts remain reusable within their declared release-specific boundaries; older gate outcomes do not transfer automatically. Fresh SQLite login and PostgreSQL bootstrap, supported upgrade preservation, real exporter/vendor behavior, browser device-type/profile administration and R64 managed-session behavior belong in applicable candidate acceptance.

Documentation synchronization establishes no new runtime/live PASS and does not promote `IMPLEMENTED_TESTING_DEFERRED`.

> **Canonical qualification state — 2026-09-18:** Q-1 remains the active, open production/runtime qualification track for Release 44. Its historical Release 39 evidence is preserved below, but that origin does not make Q-1 historical or closed. Missing prerequisites remain `NOT_RUN`; deferred live gates are not PASS.

> **Roadmap disposition — 2026-09-24:** The monitoring/correlation roadmap is active. MC-1 through MC-10 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`. **MC-11 / Release 59 — Topology-Aware Change Planning** is the next and final defined slice; keep the existing MC-4→MC-10 order historical and do not pull MC-11 execution authority into MC-10. NI-7 remains implemented and Q-1/live production qualification remains open. Do not invent NI-8/Q-2 or skip the defined roadmap without an explicit decision.

Status: `IMPLEMENTED_TESTING_DEFERRED`

## Qualification truth boundary

Q-1 separates source/offline reproducibility from production/service-backed evidence. A missing prerequisite is `NOT_RUN`; a target-host mismatch is `NOT_RUN`; an actual test or validation failure is `FAIL`. No skipped or simulated service test is promoted to PASS.

## Defect found while qualifying Release 38

Release 38 `packaging/install-rpm.sh` reported an expected RPM Release 38 but compared `${RELEASE%%.*}` against `37`. That would reject the correct `2.0.0-38` RPM. Release 39 fixes the guard and advances the package identity to `2.0.0-39`; the regression test forbids the stale `37` comparison.

## Release 39 qualification infrastructure

- Git executable index modes remain an explicit `100755` gate.
- Ruff is pinned to `0.16.7`; mypy is pinned to `2.3.1`; the source gate verifies the actual tool versions before use.
- GitHub Actions checkout is pinned to commit `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1).
- GitHub Actions setup-python is pinned to commit `5fda3b95a4ea91299a34e894583c3862153e4b97` (v7.0.0).
- CI retains PostgreSQL/OpenSSH/Net-SNMP integration and adds an AlmaLinux 10 RPM build/static qualification job.
- Installed AlmaLinux systemd restart/smoke remains a separate explicit disposable-host gate (`--install` + `NETCONFIG_Q1_ALLOW_INSTALL=1`).

## Recorded Q1 runner evidence

The current runner is Debian 13 / Python 3.13. It does not provide Ruff, mypy, PostgreSQL client/server, OpenSSH client/server, Net-SNMP, RPM/rpmbuild, Docker or Podman, and DNS/package download is unavailable. Therefore those production gates remain `NOT_RUN` here. The runner can still execute the clean-checkout offline gates and staged unit verification.

### Pre-final-package measured results

| Gate | Result | Evidence |
| --- | --- | --- |
| Q-1 focused pytest | PASS | 12 passed |
| Full repository pytest | PASS | 206 passed / 7 skipped / 0 failed |
| Legacy selftest | PASS | ALL PASS |
| compileall / launcher compile / packaging shell syntax | PASS | completed with exit 0 |
| Workflow YAML parse | PASS | jobs: `python-312`, `almalinux-10-rpm-build` |
| Git executable index modes | PASS | 8/8 = `100755` |
| Staged systemd unit verify | PASS | `systemd-analyze verify --root=...` exit 0 |
| Runtime preflight on artifact runner | NOT READY | required `ssh` absent |
| Ruff 0.16.7 | NOT_RUN | tool unavailable; external download unavailable |
| mypy 2.3.1 | NOT_RUN | tool unavailable; external download unavailable |
| PostgreSQL live/backup-restore | NOT_RUN | `pg_dump` / PostgreSQL tooling unavailable |
| OpenSSH / Net-SNMP integration | NOT_RUN | service binaries unavailable |
| AlmaLinux 10 RPM build/static | NOT_RUN | current host Debian 13; harness exit 20 |
| AlmaLinux installed RPM/systemd restart | NOT_RUN | requires disposable AlmaLinux 10 host and explicit allow flag |

The seven pytest skips are exactly the four PostgreSQL live/backup-restore tests and three protocol-service integration tests. Final fresh-clone and final artifact gates are appended only after the source is committed and frozen.
