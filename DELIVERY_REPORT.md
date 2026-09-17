# NetConfig Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence Delivery

Status: `IMPLEMENTED_TESTING_DEFERRED`.

Release 40 / RPM identity `2.0.0-40` resumes feature development from Release 39 while leaving Q-1 live qualification deferred. NI-7 adds durable explicit `l3_route_observations`, deterministic same-VRF bounded path simulation, persisted `L3_PATH` and `ROUTE_DEPENDENCY` insights, scoped REST APIs, and Operations → Network Intelligence route-evidence/path/dependency workflows. Managed next-device identity is explicit only; next-hop IP is never promoted to device identity by inference. Missing/unmanaged/multipath/mixed-terminal/loop evidence fails closed. Route-dependency output is a candidate rather than an outage verdict, and analytics cannot execute configuration.

Source qualification executed in bounded groups: **211 passed / 7 skipped / 0 failed**; NI-7 focused **5 passed**; legacy selftest **ALL PASS**; compileall, launcher compile, packaging shell syntax and operational-CR checks **PASS**. The seven existing service-backed skips and Q-1 live PostgreSQL/protocol/vendor/AlmaLinux gates remain deferred/`NOT_RUN`.

---

# NetConfig Release 39 — Q-1 Production Qualification Hardening Delivery

Candidate fresh-clone gate: **211 passed / 7 skipped / 0 failed**, NI-7 focused **5 passed**, selftest **ALL PASS**, manifest/checksum and compile/shell gates **PASS**, 8/8 required Git executable modes `100755`, clean post-test worktree after cache removal.

### Release 40 final delivery qualification

The frozen delivery surface is independently qualified. The full-source Git-archive ZIP contains **199 archive entries**, matches **181/181 Git-tracked files byte-for-byte**, and has **0** path-traversal entries, **0** symlinks, **0** cache/bytecode entries, **0** operational-text CR offenders, and **8/8** required executable files at mode `0755`; source and metadata manifests verify. From its clean extraction, the complete repository test inventory executes as **211 passed / 7 skipped / 0 failed**, with legacy selftest **ALL PASS** and compile/launcher/package-shell checks **PASS**. The clonable Git bundle reproduces the same commit, manifest and 8/8 Git `100755` modes and executes the same **211/7/0** regression plus selftest/compile with a clean post-test worktree. The `2.0.0-40` RPM build-source bundle has no traversal/symlink/cache entries, preserves all eight executable modes, verifies manifests/package identity, and passes **25/25** focused NI-7/repository-hygiene/Q-1 tests. Actual AlmaLinux RPM build/install and Q-1 live service/vendor gates remain `NOT_RUN`/deferred. The final archive SHA-256 is intentionally carried in external `.sha256` sidecars so the payload does not self-reference its own digest.

## Release 39 qualification result

Local source qualification after the Q-1 fixes: **206 passed / 7 skipped / 0 failed**; Q-1 focused **12 passed**; selftest **ALL PASS**; compile/shell/YAML/CR/Git-mode/staged-systemd gates PASS. The runner lacks Ruff, mypy, PostgreSQL, SSH/SNMP and RPM target tooling, so those gates remain `NOT_RUN`; runtime preflight correctly marks this host not ready because `ssh` is absent. The release therefore remains `IMPLEMENTED_TESTING_DEFERRED`.

Status: `IMPLEMENTED_TESTING_DEFERRED`.

Release 39 / RPM identity `2.0.0-39` continues the clean-Git-checkout baseline and hardens Q-1 production qualification. Release 38 Q-1 execution exposed a guarded-installer release mismatch, now fixed. Historical Release 38 evidence: all eight required launcher/packaging paths are committed as Git `100755`; CI validates the index with `git ls-files --stage`; Ruff is pinned to `0.16.7`; known reported Ruff debt was modernized without broadening ignores. A fresh clone from the local Git object database passed **204 passed / 7 skipped / 0 failed**, legacy selftest `ALL PASS`, compileall, launcher compile and packaging shell syntax, then returned to a clean worktree. Ruff and mypy remain `NOT_RUN` in this isolated runner because their executables are unavailable; no PASS is claimed for those gates.

The final delivery includes a full source ZIP, a clonable Git bundle preserving index modes, and an RPM `2.0.0-38` build-source transfer bundle. Real AlmaLinux 10 RPM build/install/restart and live PostgreSQL/protocol/vendor/device/scale qualification remain deferred.

---

# NetConfig Release 37 — NI-6 Enterprise Operations Delivery

Status: `IMPLEMENTED_TESTING_DEFERRED`.

This delivery productizes NI-6 Capacity, Failure Risk, Impact Simulation and Health analytics through `Manager.analytics`, scoped REST APIs and the Operations **Network Intelligence** console. It adds durable insight/job evidence, lifecycle state, filter/search, affected-object/evidence drill-down and explicit impact simulation. Analytics remains non-remediating; operators are routed only into the existing approval-gated Structured Changes, Desired State and Campaign workflows for action.

Qualification evidence is canonical in `VALIDATION_SUMMARY.md`. Source and clean-extraction full regression are **202 passed / 7 skipped / 0 failed**; selftest is **ALL PASS**; manifest/hygiene/artifact structure gates pass. Q-1 Ruff/mypy and live PostgreSQL/protocol/vendor/device/scale qualification remain deferred and are not PASS.

## Release 37 RPM install delivery

This delivery adds the canonical production installation path and package identity `2.0.0-37`. Use the AlmaLinux 10 RPM lifecycle documented in `INSTALL_RPM.md`, `opt/netconfig/INSTALL.md`, and `packaging/README.md`. The source bundle includes `packaging/install-rpm.sh`; a separate `netconfig-2.0.0-37-rpm-build-source.zip` is provided for transfer to an AlmaLinux 10 build host. No binary RPM is claimed from the Debian artifact runner because the target `rpmbuild`/Python 3.12 environment is absent.

Candidate artifact qualification for the RPM-install delivery: clean extraction and manifests PASS; full byte identity 175/175; extracted-tree regression 202 passed / 7 skipped / 0 failed; selftest ALL PASS. The binary `.rpm` is intentionally not fabricated on the Debian runner. Use the included RPM build-transfer bundle on AlmaLinux 10.
