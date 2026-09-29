# Git Reproducibility Hardening

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

> **Roadmap disposition — 2026-09-24:** The monitoring/correlation roadmap is active. MC-1 through MC-9 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next formal slice is **MC-10 / Release 58 — Correlation Production Hardening & Qualification**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. MC-11 / Release 59 remains the final Topology-Aware Change Planning slice. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## R62.1 current Git-index truth

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
