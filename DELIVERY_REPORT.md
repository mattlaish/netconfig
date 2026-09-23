# NetConfig Release 43 — Offline RPM Builder Integration Delivery

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

## Release 48 current status

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

Release 48 adds the persisted read-only Sensor Engine/API over existing evidence. Historical release evidence below remains unchanged and must not be read as the current package identity.


**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 45 — Operator UX Simplification

Release 45 addresses operator usability rather than adding a new Network Intelligence phase. The main navigation no longer exposes a duplicate **Network Intelligence** entry because that function already exists inside **Operations**. `/operations` now opens a task-oriented **Overview** explaining which workflow to use for one-off structured changes, desired state, campaigns, telemetry, intelligence, automation requests, model packs, and HA/DR. The repaired automation ledger is renamed **Automation Requests** to make its purpose explicit.

`/protocols` remains route-compatible but is presented as **Device Collection**: current read protocols are shown first, **Collect now** is the normal action, and NETCONF/RESTCONF/gNMI profile editing is placed under an Advanced disclosure. The MIB library now explains that MIBs are dictionaries rather than product features, surfaces only useful counts and lookup by default, and hides the raw file inventory under Advanced. Per-device SNMP pages likewise hide raw OID walks and vendor MIB values under Advanced sections; normal operational interface, ARP, and MAC/FDB views remain first-class.

There is no schema or public REST contract change. Package release advances to `2.0.0-45` because shipped web/runtime source changed. Status remains `IMPLEMENTED_TESTING_DEFERRED`; NI-7 remains the feature baseline and Q-1 remains open.

**Release 45 qualification on the archive-derived workspace:** repository tests executed in four bounded groups total **221 passed / 8 skipped / 0 failed**; the eight skips are seven live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console regressions cover the Operations overview, single-surface Network Intelligence navigation, Automation Requests HTTP rendering, Device Collection guidance, and MIB purpose/advanced-library presentation. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because the executable is unavailable. The offline RPM builder emitted `netconfig-2.0.0-45.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `91cfea8b74a4c9b65472bafd59852513bf30a1adb9d87f5c6be3023e4a246efd`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.

Release 44 source-tree qualification on the archive-derived workspace is **219 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the seven live/service prerequisites plus the expected Git-index executable-mode skip because `.git` is absent. Focused HTTP regression for `/operations?tab=intents` passes. Legacy selftest is **ALL PASS**; compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` actual execution remains **NOT_RUN** because no Ruff executable is available. The Release 44 offline helper RPM was built twice byte-identically and independently verified; SHA-256 is `446b0cb5ce6d8912bc7813af46b6a05761704a7a84970ca135ff4007237ced91`. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux qualification remains `NOT_RUN`.


## Historical Release 43 — Offline RPM Builder Integration

Release 43 adds `tools/rpm-builder/`, a deterministic dependency-free RPM emitter plus an independent offline verifier. The helper reads `packaging/netconfig.spec`, packages only the canonical NetConfig runtime payload, preserves executable/config ownership semantics, encodes lifecycle scriptlets and dependencies, and verifies RPM header digests, gzip/newc payload integrity, source-byte identity, modes, `CONFIG|NOREPLACE`, requirements, and scriptlets. `SOURCE_DATE_EPOCH=1789689600` is the deterministic default for this release. The same source and epoch must produce byte-identical RPMs. This helper is **not** the production qualification authority: canonical AlmaLinux 10 `rpmbuild`, `rpm -qp`, DNF install/upgrade, systemd restart/reboot, SELinux behavior, and remaining Q-1 live gates stay deferred until actually executed.
Archive-derived qualification for Release 43 on this runner is **218 passed / 8 skipped / 0 failed** with `PYTHONPATH=.`. The eight skips are the existing PostgreSQL backup/restore and OpenSSH/Net-SNMP integration gates plus the expected Git-index executable-mode skip because `.git` is intentionally absent from the source archive. Compileall and the focused sidebar/branding console regressions pass. The offline builder emitted `netconfig-2.0.0-43.el10.noarch.rpm` with SHA-256 `0bc3abca0b3349593f67593930e9c8e1298cfe511a42d24d38f4f2d26babc7c2`; the independent verifier passed RPM header digest, compressed payload digest, gzip/newc parsing, payload/source byte identity, modes, `CONFIG|NOREPLACE`, dependencies, and lifecycle scriptlets. Canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux remains `NOT_RUN`.



Status: `IMPLEMENTED_TESTING_DEFERRED`.

Roadmap disposition after this delivery: **no new development phase is assigned**. NI-7 remains the feature baseline; Q-1 remains open qualification work.

### Release 43 documentation truth maintenance

All 40 Markdown files are synchronized to the closed post-NI-7 roadmap disposition or explicitly marked as historical chronology. `Q1_PRODUCTION_QUALIFICATION.md` is current/maintained because Q-1 remains open. Post-sync archive-style regression is **217 passed / 8 skipped / 0 failed**; selftest **ALL PASS**; compileall/launcher/shell/CR checks **PASS**. Ruff `0.16.7` remains **NOT_RUN**. Complete-source delivery target: `netconfig-netconfig-2.0.0-43-sidebar-theme-refresh-v14.zip`.

### Historical Release 41 inherited corrective evidence

Release 41 corrects the dead campaign retry REST endpoint, adds route-level retry coverage and a direct Git-index executable-mode regression, and cleans identified F821/B018/B905/B007/F401/F841-style findings without expanding the Ruff ignore set. NI-7 behavior and schema remain unchanged.

### Historical Release 41 final delivery qualification

- Git fresh clone / Git bundle: **213 passed / 7 skipped / 0 failed**, 8/8 required index modes `100755`, manifests/selftest/compile/package-shell PASS, clean post-test worktree.
- Full-source Git-archive ZIP: **183/183 tracked-file byte identity**, 8/8 executable modes `0755`, 0 traversal/symlink/cache/CR findings; clean extraction **212 passed / 8 skipped / 0 failed**.
- `2.0.0-41` RPM build-source archive: **183/183 tracked-file byte identity**, 8/8 executable modes `0755`; clean extraction **212 passed / 8 skipped / 0 failed**.
- The eighth archive skip is the Git-index mode test only; `.git` metadata is intentionally absent from source archives.
- Ruff `0.16.7` and mypy actual execution: **NOT_RUN**. Q-1 live gates: **DEFERRED / NOT_RUN**.
- Release 41 binary RPM: **not yet built or qualified**.

---

## Historical Release 40 — NI-7 L3/VRF Path & Route Dependency Intelligence Delivery

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

## Historical Release 41 documentation truth sync addendum

All maintained Markdown has been reconciled to the Release 41 baseline or explicitly marked as historical evidence. `DOCUMENTATION_STATUS.md` is the canonical document index. The documentation-only sync does not change runtime/API/schema behavior, package identity, or roadmap state. The documentation-sync full-source ZIP contains one additional tracked file (`DOCUMENTATION_STATUS.md`) relative to the original Release 41 delivery and therefore validates **184/184** tracked files byte-for-byte.
### Documentation-sync final artifact gate

Final artifact gate using mode-preserving `unzip`: ZIP CRC **PASS**; source-to-extracted byte identity **190/190 PASS**; Markdown truth markers/inventory **40/40 PASS**; required executable modes **12/12 = 0755**; path traversal **0**; symlinks **0**; cache/pyc/pytest-cache entries **0**; operational CR offenders **0**; `source-manifest.sha256` **PASS**; `SHA256SUMS` **PASS**; extracted pytest **217 passed / 8 skipped / 0 failed**; extracted legacy selftest **ALL PASS**; extracted compileall / launcher `py_compile` / shell syntax **PASS**. Ruff `0.16.7` remains **NOT_RUN** because the executable is unavailable.

Delivery artifact: `netconfig-netconfig-2.0.0-43-sidebar-theme-refresh-v14.zip`. This remains Release 43 / `2.0.0-43`; the gate does not promote project status beyond `IMPLEMENTED_TESTING_DEFERRED`.

