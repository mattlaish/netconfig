# R62.1 Security & Packaging Hardening

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

R62.1 is a corrective hotfix on Release 62 and does not start R63 or create MC-12. Persisted schema remains `mc11-topology-change-planning-1`.

## Security fixes

- RESTCONF now uses a per-request urllib opener with a redirect handler that refuses all 3xx redirects before a second network request. This closes redirect-target SSRF and HTTPS-to-HTTP downgrade paths from a managed RESTCONF device. The existing 16 MiB response cap and TLS policy remain unchanged.
- OpenSSH argv now inserts `--` before the managed `user@host` target for both CLI and subsystem transports, preventing a target beginning with `-` from being parsed as an ssh option.
- The reviewed unused SNMP `previous_facts` fetch, unused `_TOPOLOGY_JS` import, and empty CLI f-string were removed.

## Git executable-mode truth

The source artifact records all required operational entry points as POSIX `0755`, and artifact gates verify those modes. That does not prove an external Git repository index. `UPSTREAM_GIT_MODE_FIX.patch` contains mode-only `100644 -> 100755` entries for every path enforced by the current CI/repository hygiene contract. Upstream Git-mode qualification remains incomplete until that patch is applied/committed and a fresh clone proves `100755` from Git metadata.

## Authority boundaries

No API, data-model, MC-11 authority, Structured Change execution, PostgreSQL retry, or R60/R61/R62 qualification authority changes are introduced by this hotfix.

### R62.1 validation closeout

- Security/compatibility focused: **82 passed / 1 skipped / 0 failed**; the skip is the expected Git-index check because the source archive contains no `.git`.
- Full bounded repository regression: **458 collected / 447 passed / 11 skipped / 0 failed**. The 11 skips remain 4 existing PostgreSQL/backup live prerequisites, 3 protocol-service prerequisites, 3 R62 live-PostgreSQL prerequisites, and 1 source-archive Git-index check.
- Redirect regression uses a real local HTTP redirect server and proves the redirect target receives **0 requests**.
- compileall / launcher+qualification py_compile / packaging shell syntax / legacy selftest: **PASS**.
- Offline helper RPM `2.0.0-62.1`: two source-tree builds byte-identical; independent verifier **PASS**; SHA-256 `84caef15419b339e10f3b22a8c22c9ae80b25da910bbeceea4389b566043d042`; payload files **99**. This is offline artifact evidence, not canonical AlmaLinux/rpmbuild qualification.
- External/upstream Git-index mode repair is **not claimed complete** by the source archive. `UPSTREAM_GIT_MODE_FIX.patch` covers all **24** required operational entry points; a real upstream commit plus fresh clone is still required for Git-index `100755` PASS.

### R62.1 clean-extract qualification

The provisional clean extraction reproduced **458 collected / 447 passed / 11 skipped / 0 failed**. compileall, py_compile, packaging/tool shell syntax, and legacy selftest passed. The provisional archive structural gate recorded **329 entries / 0 duplicates / 0 unsafe paths / 0 symlinks / CRC PASS / 329/329 source-to-extract byte+mode parity / 327/327 R62.1 source manifest / 328/328 whole-tree SHA256SUMS / 24/24 required executable modes at 0755**. Two clean-extract helper RPM rebuilds were byte-identical to each other and to the source-tree `2.0.0-62.1` RPM; independent verification passed with SHA-256 `84caef15419b339e10f3b22a8c22c9ae80b25da910bbeceea4389b566043d042`. This still does not establish external Git-index `100755`.
