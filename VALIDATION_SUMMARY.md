# NI-6 Enterprise Operations & Qualification Validation Summary

Status: `IMPLEMENTED_TESTING_DEFERRED`.

## Implemented boundary

- `Manager.analytics` is the single product boundary for NI-6 analyzers.
- Durable `network_insights` lifecycle: `NEW`, `ACKNOWLEDGED`, `RESOLVED`, `EXPIRED`.
- Durable `analytics_jobs` execution evidence.
- REST scopes: `analytics:read`, `analytics:write`; write requires operator-or-higher role.
- Operations → **Network Intelligence** UI with refresh, impact simulation, filters/search, insight detail/evidence/affected objects and lifecycle updates.
- Impact simulation traverses only resolved managed directional topology from the existing NI-2 truth plane.
- Analytics cannot execute remediation; action navigation leads only to existing approved Structured Changes / Desired State / Campaign workflows.

## Source validation

- focused repository-hygiene + enterprise analytics workflow: **10 passed / 0 failed**
- full repository: **202 passed / 7 skipped / 0 failed**
- legacy selftest: **ALL PASS**
- compileall: **PASS**
- launcher `py_compile`: **PASS**
- packaging shell syntax: **PASS**
- required executable modes: **7/7 = 0755**
- `web.py`: **239,648 bytes / 3,850 lines** (PH-1 boundary preserved)
- operational-text CR offenders: **0**
- symlinks: **0**
- Q-1/Ruff/mypy: **NOT_RUN** by explicit deferral

## Clean-extraction qualification staging artifact

The frozen candidate was created only after cache cleanup and manifest generation, then extracted into a new directory and independently validated:

- ZIP CRC: **PASS**
- path traversal entries: **0**
- ZIP symlink entries: **0**
- extracted symlinks: **0**
- `__pycache__`, `.pytest_cache`, `*.pyc` entries before tests: **0**
- `source-manifest.sha256`: **PASS**
- internal `SHA256SUMS`: **PASS**
- required executable modes: **7/7 = 0755**
- operational-text CR offenders: **0**
- extracted-tree full repository: **202 passed / 7 skipped / 0 failed**
- extracted-tree legacy selftest: **ALL PASS**
- extracted-tree compileall / launcher py_compile / packaging shell syntax: **PASS**

The final archive is built from the same qualified source after this evidence/documentation sync. Its archive SHA-256 is distributed as an external `.zip.sha256` sidecar to avoid circular self-checksumming.

## Deferred live gates

The seven skipped tests remain live/service-backed PostgreSQL backup/restore and protocol integration gates. Real vendor/device, production telemetry scale, production analytics threshold calibration and operational load qualification remain `NOT_RUN`/deferred. None are counted as PASS.

## Promotion boundary

Offline source and clean-extraction artifact qualification are complete. NI-6 remains `IMPLEMENTED_TESTING_DEFERRED`, not `TESTED` or `RELEASED`, until the applicable Q-1/live environment gates are executed and recorded.

## Release 37 RPM installation hardening — 2026-09-16

- RPM source identity: Version `2.0.0`, Release `37`.
- Focused repository hygiene: `5 passed`.
- Full source regression: `202 passed / 7 skipped / 0 failed` using `PYTHONPATH=.`.
- Legacy selftest: `ALL PASS`.
- Python compileall: PASS.
- All `packaging/*.sh` syntax: PASS.
- `packaging/install-rpm.sh` on the Debian artifact runner: fail-closed exit `20` because the production RPM target is AlmaLinux 10 (expected PASS of the guard behavior).
- `packaging/build-rpm.sh` on the Debian artifact runner: exit `2` because `rpmbuild` is unavailable; binary RPM build/install is therefore `NOT_RUN`, not PASS.
- Real AlmaLinux 10 RPM build, RPM payload inspection, dnf install/upgrade, systemd start/restart, and installed-runtime smoke remain deferred qualification gates.

### RPM install v3 candidate clean-extraction evidence

- Candidate ZIP CRC: PASS.
- ZIP path traversal / symlink / cache checks: PASS / 0 findings.
- Operational CR/line-ending check: PASS.
- Required executable modes: 8/8 = `0755`.
- `source-manifest.sha256` and metadata `SHA256SUMS`: PASS.
- Full regular-file byte identity against the frozen source tree: `175/175 PASS`.
- Candidate extracted-tree full regression: `202 passed / 7 skipped / 0 failed`.
- Candidate extracted-tree legacy selftest: `ALL PASS`.
- Candidate extracted-tree `packaging/*.sh` syntax: PASS.
- Candidate extracted-tree `install-rpm.sh` non-AlmaLinux fail-closed guard: PASS (exit `20` on Debian 13).
- Binary RPM build/install remains `NOT_RUN` because this artifact runner is Debian 13 without the AlmaLinux 10 `rpmbuild`/Python 3.12 target environment.
