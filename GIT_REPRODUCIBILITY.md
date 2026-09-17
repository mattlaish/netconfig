# Git Reproducibility Hardening — Release 38

> **Canonical project state — 2026-09-16:** **CURRENT IMPLEMENTATION BASELINE** = **Release 38 / Git Reproducibility Hardening** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-38`; NI-6.1 through NI-6.6 and Enterprise Operations are complete in source. The Git baseline now requires committed executable modes (`100755`) and fresh-clone reproducibility; Ruff/mypy and live PostgreSQL/protocol/vendor/device/scale gates may be marked PASS only when actually executed.

Release 38 closes the gap between ZIP/file-system mode evidence and Git checkout truth.

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
git clone netconfig-release38.gitbundle fresh-clone
cd fresh-clone
git ls-files --stage usr/bin/netconfig packaging/*.sh
PYTHONPATH=. pytest -q
python3 -m compileall -q opt/netconfig/netconfig
PYTHONPATH=opt/netconfig python3 opt/netconfig/selftest.py
```

Run `ruff check opt/netconfig/netconfig tests` and the configured mypy boundary in an environment where the actual tools are installed. Until those tools execute successfully, their status remains `NOT_RUN`.
