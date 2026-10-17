# Git Reproducibility Hardening

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current packaging and qualification disposition — 2026-10-13

The source/spec identity remains `2.0.0-67.2`, with unnumbered runtime and documentation correctives after the prior freeze. Release numbering awaits the user's decision. Building these sources does not reproduce the earlier frozen R67.2 artifact or inherit its qualification. Old release-specific filenames/commands below are historical examples; verify the actual build output and RPM metadata for the candidate being installed.

Packaged JSON SNMP profiles reside under `/usr/share/netconfig/snmp-profiles`; administrator/runtime overlays use `/etc/netconfig/snmp-profiles` and `$NETCONFIG_HOME/snmp-profiles`. October console administration manages runtime profiles while preserving built-in defaults. Ordinary RPM installation remains SQLite-first; fresh Core PostgreSQL requires the documented psycopg 3/bootstrap workflow.

Before candidate qualification, regenerate applicable release/source manifests, SPDX SBOM and checksums, then verify the new artifact. Packaged Markdown changes affect payload bytes. This documentation pass leaves generated JSON/SHA artifacts untouched so earlier frozen evidence is not silently rewritten. Canonical AlmaLinux build/install/upgrade/systemd/SELinux and all other LIVE_RC gates require the exact new candidate; offline helper verification alone does not qualify deployment. Git remains user-managed.

> **Roadmap disposition — 2026-09-24:** The monitoring/correlation roadmap is active. MC-1 through MC-9 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next formal slice is **MC-10 / Release 58 — Correlation Production Hardening & Qualification**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. MC-11 / Release 59 remains the final Topology-Aware Change Planning slice. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Recorded R62.1 Git-index evidence

The R62.1 security review found that an external clean Git clone can still record required launcher/qualification/packaging entry points as `100644`. A source ZIP with POSIX mode `0755` is **not** evidence that the external Git index is correct. This delivery therefore does not claim a clean-clone Git-mode PASS.

`UPSTREAM_GIT_MODE_FIX.patch` now contains mode-only `100644 -> 100755` entries for all 24 paths enforced by `tests/test_repo_hygiene.py` and `.github/workflows/ci.yml`. Applying and committing that patch in the upstream Git repository, then verifying a fresh clone with `git ls-files --stage`, is required before current Git-index qualification can be marked PASS.


## Release 41 fresh-clone proof

The frozen Release 41 Git baseline reproduces all eight required executable paths as Git mode `100755`; final fresh-clone regression is **213 passed / 7 skipped / 0 failed**, source manifest verification and legacy selftest/compile/package-shell checks PASS, and test-cache cleanup returns the clone to a clean worktree. `UPSTREAM_GIT_MODE_FIX.patch` is provided for external repositories that still track these paths as `100644`. Ruff `0.16.7` remains `NOT_RUN` on this isolated runner because its executable cannot be installed/downloaded.


## External upstream repository status

The Release 41 delivery Git bundle itself is verified at 8/8 `100755`. A separate `netconfig_release41_UPSTREAM_GIT_MODE_FIX.patch` exists for an external/upstream repository that still records the paths as `100644`. Applying/committing that patch to the external repository is a separate future action and is **not** claimed complete by this document.

## Historical Release 38 hardening

Release 38 originally closed the gap between ZIP/file-system mode evidence and Git checkout truth.

## Required Git executable modes

The following paths must be committed with Git mode `100755`:

- `usr/bin/netconfig`
- `packaging/build-rpm.sh`
- `packaging/install-rpm.sh`
- `packaging/inspect-rpm.sh`
- `packaging/q1-qualify-almalinux.sh`
- `packaging/q1-qualify-postgres.sh`
- `packaging/q1-source-gates.sh`
- `packaging/q2-qualify.sh`
- `packaging/q2-source-gates.sh`
- `packaging/r60-qualify.sh`
- `packaging/r60-lifecycle-upgrade.sh`
- `packaging/r61-qualify.sh`
- `packaging/r62-qualify.sh`
- `qualification/q2_runner.py`
- `qualification/r60_runner.py`
- `qualification/r61_runner.py`
- `qualification/r61_benchmark.py`
- `qualification/r62_runner.py`
- `qualification/run_bounded_regression.py`
- `packaging/smoke-installed.sh`
- `tools/rpm-builder/build.sh`
- `tools/rpm-builder/verify.sh`
- `tools/rpm-builder/rpm_builder.py`
- `tools/rpm-builder/verify_rpm.py`

A local `chmod 0755`, RPM payload mode, or ZIP external attribute is not sufficient Git-index evidence. A fresh Git clone must reproduce `100755` in the index and executable files in the worktree.

## CI order

The canonical CI order is Git-index mode verification, Ruff, mypy boundary checks, compileall, pytest, legacy selftest, then service-backed integration tiers. Tool absence is `NOT_RUN`, never PASS.

## Fresh-clone qualification

A release qualification clone must be created from the committed Git object database or delivery Git bundle, not copied from the source worktree. Run at minimum:

```bash
git clone netconfig_release41_Corrective_REST_Git_Ruff_Hardening_v7.gitbundle fresh-clone
cd fresh-clone
git ls-files --stage usr/bin/netconfig packaging/*.sh
PYTHONPATH=. pytest -q
python3 -m compileall -q opt/netconfig/netconfig
PYTHONPATH=opt/netconfig python3 opt/netconfig/selftest.py
```

Run `ruff check opt/netconfig/netconfig tests` and the configured mypy boundary in an environment where the actual tools are installed. Until those tools execute successfully, their status remains `NOT_RUN`.


## R67 executable-mode boundary

R67 source artifacts require 35 operational entry points at `0755`. This remains distinct from upstream Git-index `100755`; the source archive cannot prove the latter. The mode-only patch must be committed and verified from a fresh clone before that live RC gate can PASS.
