# NetConfig Production Qualification Validation Summary

## Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence

- Release/RPM identity: **2.0.0-40**.
- Schema revision: **ni7-l3-route-1**.
- NI-7 focused: **5 passed**.
- Full source regression before final packaging: **211 passed / 7 skipped / 0 failed**.
- Selftest: **ALL PASS**. Compileall/launcher/shell/YAML/operational-CR checks: **PASS**.
- Safety: same-VRF only, explicit managed next-device identity, bounded/cycle-safe traversal, no arbitrary ECMP winner, route-dependency candidate only, no direct configuration execution.
- Q-1 live PostgreSQL/protocol/vendor/AlmaLinux qualification remains deferred/NOT_RUN.

### Release 40 candidate fresh-clone evidence

Candidate commit fresh clone reproduced the complete test inventory in bounded groups: **211 passed / 7 skipped / 0 failed**. NI-7 focused **5 passed**; `source-manifest.sha256` and metadata checksums **PASS**; required Git index modes **8/8 = 100755**; legacy selftest **ALL PASS**; compileall, launcher compile, and packaging shell syntax **PASS**. After cache removal the clone returned to a clean Git worktree. The seven live/service tests remain intentionally skipped and Q-1 live gates remain deferred/`NOT_RUN`.

### Release 40 final delivery qualification

The frozen delivery surface is independently qualified. The full-source Git-archive ZIP contains **199 archive entries**, matches **181/181 Git-tracked files byte-for-byte**, and has **0** path-traversal entries, **0** symlinks, **0** cache/bytecode entries, **0** operational-text CR offenders, and **8/8** required executable files at mode `0755`; source and metadata manifests verify. From its clean extraction, the complete repository test inventory executes as **211 passed / 7 skipped / 0 failed**, with legacy selftest **ALL PASS** and compile/launcher/package-shell checks **PASS**. The clonable Git bundle reproduces the same commit, manifest and 8/8 Git `100755` modes and executes the same **211/7/0** regression plus selftest/compile with a clean post-test worktree. The `2.0.0-40` RPM build-source bundle has no traversal/symlink/cache entries, preserves all eight executable modes, verifies manifests/package identity, and passes **25/25** focused NI-7/repository-hygiene/Q-1 tests. Actual AlmaLinux RPM build/install and Q-1 live service/vendor gates remain `NOT_RUN`/deferred. The final archive SHA-256 is intentionally carried in external `.sha256` sidecars so the payload does not self-reference its own digest.

## Historical Release 39 — Q-1 Production Qualification Hardening

- Release/RPM identity: **2.0.0-39**.
- Release 38 installer defect fixed: the guarded installer now validates RPM Release `39`; stale comparison against `37` is prohibited by regression.
- Git index executable modes: **8/8 = 100755 PASS**.
- Source full pytest: **206 passed / 7 skipped / 0 failed**.
- Q-1 focused pytest: **12 passed / 0 failed**.
- Legacy selftest: **ALL PASS**.
- compileall / launcher `py_compile` / packaging shell syntax / workflow YAML / CR scan: **PASS**.
- Staged installed-filesystem systemd unit verification: **PASS**.
- Runtime `netconfig qualify` on this runner: **NOT READY** — required SSH client absent; Python/openssl/SQLite core storage pass; gNMI is optional while disabled.
- Ruff `0.16.7`: **NOT_RUN** — pinned but executable unavailable and package download unavailable.
- mypy `2.3.1`: **NOT_RUN** — pinned but executable unavailable and package download unavailable.
- PostgreSQL service-backed Q-1: **NOT_RUN** — `pg_dump`/server tooling unavailable.
- OpenSSH/Net-SNMP integration: **NOT_RUN** — services/tools unavailable.
- AlmaLinux 10 RPM build/install: **NOT_RUN** on this Debian runner; source CI now contains an AlmaLinux 10 build/static job, but no workflow execution is claimed here.

Release 39 remains `IMPLEMENTED_TESTING_DEFERRED`; source/offline qualification is green, while production/service-backed qualification is still open.

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

## Release 40 NI-7 current validation

Source workspace validation before final artifact freeze: NI-7 focused **5 passed**; full repository **211 passed / 7 skipped / 0 failed**. NI-7 uses explicit managed route observations only and remains decision-support/read-only. Final artifact/fresh-clone evidence must be recorded after packaging; Q-1 live service, vendor/device, AlmaLinux and scale gates remain deferred/NOT_RUN.

### Release 40 fresh-clone evidence

Clean Git clone: **211 passed / 7 skipped / 0 failed**; 8/8 required executables `100755` in the index and `0755` in the worktree; source manifest and metadata checksum verification PASS; selftest ALL PASS; compile/shell/YAML PASS; post-test worktree clean after cache removal.
