# Git Reproducibility Hardening

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 41 fresh-clone proof

The frozen Release 41 Git baseline reproduces all eight required executable paths as Git mode `100755`; final fresh-clone regression is **213 passed / 7 skipped / 0 failed**, source manifest verification and legacy selftest/compile/package-shell checks PASS, and test-cache cleanup returns the clone to a clean worktree. `UPSTREAM_GIT_MODE_FIX.patch` is provided for external repositories that still track these paths as `100644`. Ruff `0.16.7` remains `NOT_RUN` on this isolated runner because its executable cannot be installed/downloaded.


## External upstream repository status

The Release 41 delivery Git bundle itself is verified at 8/8 `100755`. A separate `netconfig_release41_UPSTREAM_GIT_MODE_FIX.patch` exists for an external/upstream repository that still records the paths as `100644`. Applying/committing that patch to the external repository is a separate future action and is **not** claimed complete by this document.

## Historical Release 38 hardening

Release 38 originally closed the gap between ZIP/file-system mode evidence and Git checkout truth.

## Required Git executable modes


Ruff is pinned to `0.16.7` in `requirements-quality.txt` and CI; this runner still records Ruff as **NOT_RUN** because the executable cannot be installed/downloaded here.
The following paths must be committed with Git mode `100755`:

- `usr/bin/netconfig`
- `packaging/build-rpm.sh`
- `packaging/install-rpm.sh`
- `packaging/inspect-rpm.sh`
- `packaging/q1-qualify-almalinux.sh`
- `packaging/q1-qualify-postgres.sh`
- `packaging/q1-source-gates.sh`
- `packaging/smoke-installed.sh`

Verify with:

```bash
git ls-files --stage usr/bin/netconfig packaging/*.sh
```

A local `chmod 0755` or ZIP external attributes are not sufficient evidence. A fresh Git clone must reproduce `100755` in the index and executable files in the worktree.

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
