## Repository hygiene & hot-path performance corrective — 2026-09-29

Corrective maintenance on the R67.2 baseline; no product feature, schema, or public REST contract change, and no new network-write authority.

- **Git index executable modes:** the 40 launcher / packaging / qualification / tool entry points listed in `tests/test_repo_hygiene.py::REQUIRED_EXECUTABLES` were committed with git index mode `100644`, so a clean clone failed 13 hygiene/mode-contract tests (`test_repo_hygiene` ×2 plus the q2/r60/r61/r62.1/r64/r65/r66/r67 mode gates). Restaged all 40 to `100755` (`git update-index --chmod=+x`); filesystem and index modes now agree.
- **Topology N+1 query flaw:** `manager.topology_identities`, `manager.topology_graph`, and the neighbor-analysis path each looped `inv.get_facts()` once per device while rendering. Replaced the three identical blocks with a single `_inventory_with_sysname()` helper that does one bulk `inv.all_facts()` and joins in memory.
- **Per-packet device lookup flaw:** `manager.device_by_host()` (called once per syslog line / SNMP trap on the ingestion hot path) re-scanned and re-parsed the whole device table. Added `Inventory.get_by_host()`, a single indexed case-insensitive `WHERE LOWER(host)=LOWER(?)` lookup, and pointed `device_by_host` at it.
- **Release metadata regeneration:** regenerated `SBOM.spdx.json`, `RELEASE_MANIFEST.json`, and `RELEASE_MANIFEST_SHA256.txt` via `tools/release_metadata.py` (460 SPDX source files) so the drift check passes after the source edits.
- **Validation:** `python3.12 -m compileall` PASS; full suite **535 passed / 13 skipped / 0 failed** (13 skips are live-PostgreSQL/protocol integration gates, environment-gated as designed); `ruff check` clean on the edited modules; `release_metadata.py --check` PASS. Live RC gates remain mandatory and unaffected; status stays `IMPLEMENTED_TESTING_DEFERRED`.

## R60 Appliance Reliability & Lifecycle Hardening — 2026-09-24

Added release-60 appliance lifecycle hardening: offline-safe checksummed local-state snapshot/verify/restore, external secret/certificate preservation fingerprints, explicit PostgreSQL rollback DB switching, R59→R60 fail-closed upgrade/downgrade wrapper with runtime service masking and service-state restoration, disk-space preflight, lifecycle retention candidates, fixed-name live qualification hooks, and an R60 evidence runner. No MC-12 or new device execution authority is introduced.

## Q2 qualification harness — 2026-09-24

Added a non-product-runtime production qualification harness: `qualification/q2_runner.py`, bounded regression runner, machine-readable Q2 gate catalog, fixed-name live-hook contract, Q2 wrapper/source gates, focused tests, evidence bundle checksums/redaction, and synchronized roadmap/handover/testing/security documentation. Product RPM release remains 59 and MC-11 authority is unchanged.

# NetConfig Patch Ledger

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## PATCH-20260924-01 — Release 57 / MC-9 Operations Correlation Console

- **Status:** `IMPLEMENTED_TESTING_DEFERRED`.
- **Target release:** `2.0.0-57`; schema remains `mc8-external-evidence-connectors-1`.
- **Scope:** read-only SOC/NOC Operations Correlation Console over existing MC-4 through MC-8 durable evidence, hypotheses, dependencies, connector health, and bounded NetFlow ring.
- **Files changed:** `opt/netconfig/netconfig/operations_correlation.py`, `opt/netconfig/netconfig/web_mc9.py`, Manager/Web/Incident presentation wiring, focused tests, Release 57 packaging guards, and canonical documentation/manifests.
- **User-visible behavior:** `/dashboard`, `/traffic`, converged Alerts/Events/Incidents/Maintenance workspace navigation, and Incident supporting/contradicting evidence detail.
- **Data/schema impact:** no database migration; no persistent flow warehouse.
- **Security/authority:** rendering is DB/ring-read-only; no implicit SNMP/SSH/config collection, connector response action, root-cause promotion, arbitrary network command, or approval bypass. Untrusted hypothesis/incident content is HTML-escaped.
- **Validation completed:** source tree **357 collected / 349 passed / 8 skipped / 0 failed**; MC-9 focused **8/8 PASS**; MC-4 through MC-9 / Incident / Web / CSS compatibility **83/83 PASS**; compileall, launcher py_compile, shell syntax, and legacy selftest PASS. Release 57 helper RPM built twice byte-identically, independent verifier PASS, **96 payload files**, SHA-256 `92eb370f9d0a5b47043c526df9960e2520dee16a454ececdff0fbd0cdf53e98e`.
- **Artifact qualification:** clean-extract **357 collected / 349 passed / 8 skipped / 0 failed**; MC-9 focused **8/8 PASS**; structure **223 entries**, **0 duplicate/unsafe/symlink**, **223/223 byte+mode parity**, **209/209 source manifest**, **222/222 SHA256SUMS**, **12/12 executable modes 0755**; compile/selftest/shell PASS; clean-extract RPM rebuilds byte-identical to source-tree RPM and verifier PASS.
- **Validation outstanding:** canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux, live PostgreSQL/backup/protocol services, representative live browser/load/flow qualification, and production-scale correlation/traffic qualification remain `NOT_RUN / DEFERRED`.
- **Known limitation:** traffic analytics are bounded by the existing in-memory NetFlow ring and are not a persistent flow warehouse.
- **Recommended next step:** R58 / MC-10 Correlation Production Hardening & Qualification.

## PATCH-20260923-02 — Release 52 / MC-4 Unified Alert Plane

- **Alert authority:** new service/application monitoring writes only the normalized Sensor -> Event -> `operational_alerts` lifecycle; legacy alert rows remain readable compatibility history.
- **Lifecycle:** stable Sensor correlation prevents duplicate active alerts across escalation and auto-resolves on recovery.
- **Config collection:** Add/Edit and device detail expose effective collection command; optional override is restricted to one bounded read-only `show`/`display`/`get`/`/export` command.
- **Endpoints:** global ARP/IP-neighbor ↔ FDB/MAC join before device filtering; IP/MAC search and evidence-chain UI/API.
- **NetFlow:** operator-oriented aggregations/analysis from already-received flows; raw rows Advanced.
- **Verification:** 289 passed / 8 skipped / 0 failed source truth; selftest/compile/shell PASS; live/vendor/service gates deferred; no formal RPM built.


> **Roadmap disposition — 2026-09-24:** **R59 / MC-11 is the final Monitoring & Correlation functional slice.** Do not create MC-12. After R59, stop feature expansion and use the Release / Qualification track: **Q2 Production Qualification Campaign → R60 Appliance Reliability & Lifecycle Hardening → R61 Scale & Performance Qualification → R62 PostgreSQL / Concurrency / Recovery Hardening → R63 HA / Failure-Domain Engineering → R64 Security Hardening & Independent Abuse Testing → R65 Operator Workflow Completion → R66 Observability / Supportability → R67 Release Candidate / Full Artifact Qualification → R68 v2 Production Release Decision**. Simulation never counts as live PASS; mandatory gates use `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN`.


## PATCH-20260918-02 — Release 43 — All-Markdown Roadmap / Truth Sync

- **Scope:** documentation only; all 40 Markdown files updated. No runtime/schema/API behavior change and no RPM Release bump.
- **Roadmap:** post-NI-7 review closed with no new development phase assigned; NI-7 remains the feature baseline; Q-1 remains an open qualification track.
- **Ownership:** `Q1_PRODUCTION_QUALIFICATION.md` is current/maintained rather than historical-only.
- **Stale-pointer cleanup:** current handoff/baseline/progress/packaging language updated to Release 43; retained historical `NEXT`/`PLANNED` material explicitly marked as chronology.
- **Qualification boundary:** Ruff `0.16.7`, mypy and Q-1 live gates remain `NOT_RUN`/deferred unless actually executed.

## PATCH-20260917-01 — Release 41 — Corrective REST + Git/Ruff Hardening

- **Parent:** Release 40 NI-7 L3/VRF Path & Route Dependency Intelligence.
- **Target:** `2.0.0-41`; no schema revision.
- **Correctness:** fixed `POST /api/v1/campaigns/{id}/retry` to read `wave` from list-valued `form`; added HTTP route tests for explicit and omitted wave.
- **Reproducibility:** Git-index regression requires all eight launcher/packaging executables at `100755`; archive modes are independently checked at `0755`.
- **Lint hardening:** corrected identified F821/B018/B905/B007/F401/F841-style findings without widening ignores; actual Ruff `0.16.7` execution remains `NOT_RUN`.
- **Verification:** final Git fresh clone / bundle **213 passed / 7 skipped / 0 failed**; full-source and RPM-build-source archives **212 passed / 8 skipped / 0 failed** because archives omit `.git`.
- **Deferred:** upstream external-repository mode patch application, Release 41 binary RPM build/install, Ruff/mypy actual execution, and Q-1 live service/vendor/AlmaLinux gates.

## PATCH-20260913-01 — Release 34 — UI-1 Unified Automation & Operations Console

- **Parent:** Release 33 FULL source baseline, SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`.
- **Target release:** `2.0.0-34`; no schema migration.
- **Scope:** Web Console operations coverage for PH-4/NI-5/VM-1/NA-1/NA-2/HA-1, frozen automation CR rendering, telemetry edit service/API, focused Web/RBAC/CSRF/CSP tests, documentation/lineage/artifact evidence.
- **Security:** no new direct network-write path; structured recovery/model/HA admin controls retain backend authorization; session expiry remains deferred.
- **Source evidence:** UI-1 **7 passed**, combined focused **73 passed**, full repository **175 passed / 7 skipped**, selftest **ALL PASS**, compile/launcher/shell **PASS**, source hygiene clean after cache removal. Ruff/mypy `NOT_RUN` because binaries are unavailable.
- **Candidate artifact:** Candidate artifact evidence: `netconfig_ui1_release34_candidate_2026-09-13.zip` (SHA-256 `760cb9d411e54b991cc1c285e09fdd276c2364d8e4a497da6bd2d6d756e70d2a`) passed clean-extraction verification: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0** before testing; text CR offenders **0**; source/extracted byte identity **138/138 PASS**; payload and each of the three SHA manifests **133/133 PASS**; required executable modes **7/7 = 0755**. From that clean extraction, UI-1 focused **7 passed**, combined UI-1/automation/PH-1/PH-2/PH-3/Q-1 focused **73 passed**, full repository **175 passed / 7 skipped**, legacy selftest **ALL PASS**, and compileall/launcher `py_compile`/packaging shell syntax **PASS**. Ruff, mypy, `rpmbuild`, and PostgreSQL `pg_dump`/`pg_restore` remained **NOT_RUN** because those binaries are unavailable in this environment; none are counted as passing.


## PATCH-20260912-02 — Release 33 — Structured automation expansion

- **Status:** `IMPLEMENTED_TESTING_DEFERRED`.
- **Target release:** `2.0.0-33`; schema revision `ha1-2`.
- **PH-4:** typed structured transaction ledger, change-request-backed approval, plan/hash freeze, device/advisory serialization, idempotency, verification, rollback and recovery-required reconciliation.
- **NI-5:** durable telemetry subscriptions, bounded stream windows, scheduler/retention, scalar point normalization and summary/read APIs.
- **VM-1:** validated built-in/custom model packs, device binding and immutable model-pack hash provenance.
- **NA-1:** revisioned desired-state model, deterministic plan/evaluate/apply evidence and compensating rollback.
- **NA-2:** canary/wave campaign orchestration, stable retry identities, pause/resume/retry/abort and frozen-plan/model drift protection.
- **HA-1:** durable node drain/activate lifecycle, drain-aware leadership/admission, readiness and recovery-drill evidence; no automatic DB failover claim.
- **Security:** network writes cannot be authorized by a caller-provided boolean. Execution requires an approved durable `change_requests` record whose frozen automation snapshot still matches at approval and execute time.
- **Quality/packaging:** raw-source executable-mode checks are enforced in CI/source gates; mypy boundary expanded to Release 33 core modules; Release bumped to 33. Consolidated source evidence: automation/hygiene focused **23 passed**, PH-2 **9**, PH-3 **22**, Q-1 **11**, repository **168 passed / 7 skipped**, selftest **ALL PASS**, compile/launcher/shell **PASS**, source CR/cache/symlink offenders **0**, required executable modes **7/7 = 0755**. Ruff/mypy remain `NOT_RUN` because their binaries cannot be obtained in this isolated environment; no false PASS is recorded.
- **Artifact candidate:** Clean Release 33 candidate `netconfig_release33_candidate_2026-09-12.zip` (SHA-256 `d03720a411b796458747f7d8976a8fa01f4f40859b5e51341ef031aaa343f538`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; text CR offenders **0**; source/extracted byte identity **132/132 PASS**; payload plus each SHA/release manifest **128/128 PASS**; required executable modes **7/7 = 0755**. From the clean extraction: Release 33 focused **23 passed**, PH-2 **9 passed**, PH-3 **22 passed**, Q-1 **11 passed**, full repository **168 passed / 7 skipped** in the isolated full-suite rerun, legacy selftest **ALL PASS**, and compileall/launcher py_compile/packaging shell syntax **PASS**. A first command that chained all suites hit the execution-tool timeout after full pytest reached ~82%; that interrupted run is not counted as PASS. The same candidate full suite was then rerun alone and completed cleanly (**168 passed / 7 skipped in 22.90s**).
- **Deferred:** session idle/absolute expiry remains explicit security debt; Q-1 live service/RPM/vendor qualification remains outstanding.

> **Current continuation pointer:** use **Release 59 / MC-11 Topology-Aware Change Planning** (`2.0.0-59`) as the active full-source baseline once the final artifact gate below is frozen. Preserve `IMPLEMENTED_TESTING_DEFERRED`; do not promote to `TESTED` or `RELEASED` based on source simulation. MC-11 is the final functional slice and does not add direct execution authority. The immediate next track after artifact freeze is **Q2 Production Qualification Campaign**, not MC-12.

## PATCH-20260912-01 — Release 32 — Qualification Q-1

- **Status:** `IMPLEMENTED_TESTING_DEFERRED`.
- **Target release:** `2.0.0-32`.
- **Scope:** production runtime/service-backed qualification foundation.
- **Runtime:** added configuration-aware `netconfig qualify`; controlled PostgreSQL core backup/restore with checksum, atomic mode-0600 artifacts, short-lived mode-0600 `PGPASSFILE`, SSL-mode propagation, non-interactive execution, destructive confirmation, active-database restore refusal, and recovery-safe restore path.
- **Testing:** added Q-1 offline security/CLI/unit tests and real PostgreSQL integration tests for `SKIP LOCKED`, advisory leadership/session loss, heartbeat, migration/sequence repair and pg_dump/pg_restore recovery. CI now installs PostgreSQL client tools and enables the backup/restore integration tier.
- **Packaging:** reconciled `pyproject.toml` to Version 2.0.0, bumped RPM Release 32, separated RPM build from installed smoke, added source/PostgreSQL/AlmaLinux qualification harnesses, extended RPM inspection, and hardened the backup systemd unit.
- **Offline evidence before final artifact gate:** Q-1 focused **11 passed**; repository **147 passed / 7 skipped**. Ruff/mypy `NOT_RUN` because tools/network are unavailable; PostgreSQL qualification `NOT_RUN` because pg tools/service are unavailable; AlmaLinux qualification `NOT_RUN` because the current host is Debian 13.
- **Artifact gate:** Clean Q-1 candidate `netconfig_qualification_q1_candidate_2026-09-12.zip` (SHA-256 `185039eadf8e8e63a8dad358df35f759a7a1f099d5fa6a3456a50e023920a2b1`) passed the artifact gate: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; source/extracted byte identity **125/125 PASS**; payload plus each SHA manifest **121/121 PASS**; required executable modes **7/7 = 0755**; extracted Q-1 focused **11 passed**; extracted full regression **147 passed / 7 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**.
- **Schema/API:** no database schema revision and no new REST endpoint/scope.
- **Deferred:** all applicable real service/RPM gates must remain `NOT_RUN` until actually executed; no Q-2 is assigned.

This file is the chronological implementation ledger for AI handover and
release/version control. It records what changed in each development batch,
independently of Git history. `AI_HANDOFF.md` remains the overall architecture,
current-state, and next-task handoff; this file is the authoritative delta log.

## 2026-09-12 — Release 31 — Platform Hardening PH-3 structured adapters

- Expanded the initial read-only structured-protocol MVP into the handover-defined bounded adapter contract while preserving existing profile/collection compatibility.
- NETCONF now negotiates server hello/capabilities, provides fixed bounded `<get>` and `<get-config>` reads, understands advertised datastore/candidate/startup and confirmed-commit/rollback capability evidence, and rejects unsafe/oversized XML; no arbitrary RPC/edit-config surface is exposed.
- RESTCONF now performs HTTPS discovery, strict host/path/query/content validation, production TLS/CA and vault-resolved mTLS handling, bounded JSON/XML, and an internal approval-gated verified JSON subtree replace with best-effort pre-image rollback. Generic URL/method/body passthrough is not exposed.
- gNMI now supports Capabilities, Get and bounded ONCE Subscribe with typed paths, deadlines, response-size limits, TLS/mTLS, mode-0600 ephemeral secret configuration and secret-free argv; gNMI Set is not exposed.
- Added manager/CLI capability/state/Subscribe read surfaces and bearer API capabilities/state reads; preserved RBAC/CSRF and explicit-only CLI fallback.
- Added direct PH-3 regression coverage for capability negotiation, malformed/oversized parsing, TLS fail-closed policy, timeout/deadline handling, path allow-lists, secret redaction, unsupported capabilities, pre/post verification, rollback and Web/API/CLI RBAC.
- Source regression before final artifact packaging: **136 passed / 3 skipped**; focused PH-3 **22 passed**. The three skips remain service-backed OpenSSH, Net-SNMP and PostgreSQL integration gates.
- RPM source metadata remains `2.0.0-31`; live vendor/RPM/service-backed qualification remains deferred. No next numbered phase is assigned; perform roadmap/qualification review first.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

## Maintenance Rules

- Read `AGENTS.md`, `AI_HANDOFF.md`, and this file before modifying the project.
- Add or update a patch entry whenever code, tests, packaging, schema, service
  integration, security behavior, or user-visible documentation changes.
- Put the newest patch entry first.
- Use IDs in the form `PATCH-YYYYMMDD-NN`; never reuse an ID.
- Keep an entry `In progress` while work is incomplete, then record the actual
  validation result before changing it to `Ready for integration`.
- State explicitly when Linux/RPM/live-device validation remains outstanding.
- Never record credentials, community strings, private keys, tokens, or customer
  secrets. Use placeholders only.
- Do not infer that a patch was committed, pushed, signed, built, or installed.
  Record only actions that were actually completed.
- After a completed stage or an update to README/handover/version documents,
  the user-facing final feedback must end with the current Taiwan timestamp in
  the exact format `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)`.
- The repository owner performs Git synchronization manually. Do not run Git
  operations unless the user explicitly changes that instruction.

## Entry Template

```text
## PATCH-YYYYMMDD-NN — Short title

- Status:
- Target release:
- Scope:
- Files changed:
- User-visible behavior:
- Data/schema impact:
- Packaging/upgrade impact:
- Security impact:
- Validation completed:
- Validation outstanding:
- Known risks/limitations:
- Rollback notes:
- Recommended next step:
```

## PATCH-20260911-07 — NI-1 all-Markdown canonical-state synchronization

- **Status:** Ready for integration.
- **Target release:** Source RPM Release remains `2.0.0-25`; documentation-only synchronization, no runtime/package-spec release bump.
- **Scope:** Synchronize every Markdown file to the canonical NI-1 current state while retaining dated/changelog material as explicitly historical provenance.
- **Files changed:** All `*.md` files in the source baseline.
- **User-visible behavior:** None; documentation/handover consistency only.
- **Data/schema impact:** None.
- **Packaging/upgrade impact:** Rebuild the FULL source-baseline ZIP and manifests; runtime/RPM payload code is unchanged.
- **Security impact:** None to runtime. Documentation now consistently preserves the deferred session-lifetime and external qualification truth boundaries.
- **Validation completed:** Workspace validation: Full repository pytest **75 passed / 3 skipped**; focused `tests/test_network_intelligence.py` **8 passed**; legacy selftest **ALL PASS**; compileall/launcher/package-shell syntax **PASS**; UTF-8 CR offenders **0**. Final extracted-artifact gate is recorded in `TESTING.md` / `TESTING_RESULT_2026-09-11.md` after packaging.
- **Validation outstanding:** Ruff/mypy, service-backed integration, RPM install/runtime, and representative live-vendor qualification remain deferred unless actually run.
- **Known risks/limitations:** Historical entries intentionally retain the state/version/test counts that were true when recorded.
- **Rollback notes:** Revert Markdown-only changes and regenerate manifests/package.
- **Recommended next step:** Network Intelligence NI-2 — Topology Identity & Downstream Impact.


## PATCH-20260827-01 — Pure Application device isolation

- **Status:** Ready for integration.
- **Target release:** Planned `netconfig-2.0.0-17.el10`; the RPM spec release
  bump is intentionally not part of this focused application patch and remains
  outstanding before the next package build.
- **Scope:** Prevents Application-only inventory entries from inheriting or
  displaying network-device platform, SSH, configuration archive, and SNMP
  behavior.
- **Files changed:** `opt/netconfig/netconfig/web.py`,
  `opt/netconfig/netconfig/manager.py`, `opt/netconfig/selftest.py`,
  `AI_HANDOFF.md`, and `patch.md`.
- **User-visible behavior:** A pure Application device shows its primary
  hostname, type, and application endpoint status only. Platform, Auth, SNMP
  facts, Collect/Current raw, Run command, Current configuration, drift/diff,
  and Config backups are omitted. Dashboard rows likewise omit stale platform,
  SSH port, config, SNMP, and per-device collect controls. Mixed Application +
  System/Network entries retain the normal management UI.
- **Data/schema impact:** No schema change. Saving a pure Application device
  normalizes its inventory row to platform `generic`, internal placeholder port
  22, empty SSH/enable/SNMP references, disabled SSH/archive/NetFlow flags, and
  empty system-port monitoring while preserving application URLs, notes, tags,
  and enabled state.
- **Packaging/upgrade impact:** Application code changes require a rebuilt RPM.
  Because `-16` build material already exists and newer functionality has since
  landed, the next package should bump the embedded spec Release to `-17`
  before rebuilding; renaming an RPM file is not sufficient.
- **Security impact:** Hidden browser controls are now disabled and, critically,
  the server independently rejects forged management values for Application-only
  saves. Bulk SSH config collection skips endpoint-only devices.
- **Validation completed:** Windows Python 3.12.13 `compileall` passed and the
  full offline self-test reports `RESULT: ALL PASS`. New tests cover hostile
  hidden-field submission, detail-page isolation without config/SNMP reads,
  dashboard suppression of stale management data, and client-side disabling of
  hidden controls. Reverse-regression tests confirm a System-only device still
  preserves platform, SSH/SNMP references, port and archive options when saved;
  renders all management sections on its detail page; and retains platform,
  address/port, stored-config, SNMP, and Collect indicators on the dashboard.
- **Validation outstanding:** Browser verification and installed RPM testing on
  AlmaLinux 10.2; mixed-type and live application endpoint regression checks.
- **Known risks/limitations:** Existing inventory rows are not migrated
  destructively. Their old platform/secret/SNMP references remain stored but
  ignored and hidden until the operator edits and saves the pure Application
  entry. Existing config archives and vault secrets are deliberately retained.
- **Rollback notes:** Revert the five files listed above. No database rollback
  is required; inventory normalization occurs only when a device is saved.
- **Recommended next step:** Verify one existing and one newly created pure
  Application device in the browser, then bump the spec to release `-17`, build
  the RPM on AlmaLinux, and run the installed smoke/self-tests.

## PATCH-20260824-01 — Post-merge handoff reconciliation

- **Status:** Ready for integration.
- **Target release:** Development-process documentation for
  `netconfig-2.0.0-16.el10`; no application release change.
- **Scope:** Reconciles `AI_HANDOFF.md` after the user merged the GitHub Claude
  handoff changes with the newer local development record.
- **Files changed:** `AI_HANDOFF.md` and `patch.md`.
- **User-visible behavior:** None; this is handoff/version-ledger maintenance.
- **Data/schema impact:** None.
- **Packaging/upgrade impact:** None. The handoff now distinguishes the original
  reconstructed `-14` RPM from the current `-16.el10` packaging target.
- **Security impact:** The planned full-text-search design now requires a shared
  validated snapshot-path helper before line-by-line archive access, preserving
  the existing traversal protection without loading whole snapshots into memory.
- **Validation completed:** Confirmed that no merge-conflict markers remain;
  verified the `-16.el10` target against `packaging/netconfig.spec`; confirmed
  the documented 27 package modules; and confirmed the merged `cookie_secure`,
  `Secure` session-cookie, and `import sys` changes are present in application
  code. No Git command was run.
- **Validation outstanding:** Application tests were not rerun because this
  patch changes documentation only. AlmaLinux RPM and live-device validation
  remain outstanding as recorded below.
- **Known risks/limitations:** Repository commit/branch state is deliberately
  not asserted because Git synchronization is controlled by the user.
- **Rollback notes:** Revert this ledger entry and the three corresponding
  handoff wording corrections; there is no runtime or data rollback.
- **Recommended next step:** Let the user complete the current Git merge, then
  implement the bounded config archive full-text search described in the
  handoff or perform the pending AlmaLinux `-16` packaging validation.

## PATCH-20260820-02 — Taiwan-time completion feedback rule

- **Status:** Complete.
- **Target release:** Development-process documentation; no application release
  change.
- **Scope:** Makes a Taiwan UTC+8 timestamp mandatory at the end of user-facing
  feedback after a completed development stage or README/handover/version-file
  update.
- **Files changed:** `AGENTS.md`, `CLAUDE.md`, `AI_HANDOFF.md`, and `patch.md`.
- **User-visible behavior:** Qualifying final responses end with
  `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)` as their final line.
- **Data/schema impact:** None.
- **Packaging/upgrade impact:** None.
- **Security impact:** None; the timestamp contains no sensitive information.
- **Validation completed:** Confirmed that all four AI instruction/handover files
  contain the exact timestamp format and final-line requirement.
- **Validation outstanding:** None.
- **Known risks/limitations:** The timestamp depends on the executing
  environment clock being correct.
- **Rollback notes:** Remove the timestamp rule and this ledger entry.
- **Recommended next step:** Apply this format to every qualifying final
  feedback from this point onward.

## PATCH-20260820-01 — Consolidated 2.0.0-16 development patch

- **Status:** Ready for AlmaLinux integration testing; not built, installed,
  committed, or pushed by the AI.
- **Target release:** `netconfig-2.0.0-16.el10`
- **Scope:** Consolidates all workspace changes made after reconstruction of the
  original `netconfig-2.0.0-14.noarch.rpm` and the failed `-15` CRLF build.
- **Files changed:** Application modules under `opt/netconfig/netconfig/`,
  `opt/netconfig/selftest.py`, installation/development documentation, system
  launcher, `.gitignore`, RPM engineering under `packaging/`, `AI_HANDOFF.md`,
  and this ledger.
- **User-visible behavior:**
  - Settings uses a left-side topic menu with shorter subpages.
  - Pure Application devices use hostname/FQDN-oriented fields and hide SSH-only
    controls; mixed Network/System devices retain management controls.
  - SNMP pages expose persisted facts, interfaces, ARP, MAC/bridge information,
    raw/resolved OIDs, MIB mapping source, and per-file MIB diagnostics.
  - Uploaded MIB `OBJECT-TYPE` definitions drive bounded extended collection.
    Net-SNMP Linux devices map enterprise 8072 to Net-SNMP 8072, UCD-SNMP 2021,
    and HOST-RESOURCES `.1.3.6.1.2.1.25` collection trees.
  - System/Application compliance supports `unknown` and `not_applicable`;
    application operational health is displayed but not compliance-scored.
    Application checks include certificate validation/expiry, active TLS 1.0
    and 1.1 rejection, cipher strength, HSTS, nosniff, and CSP evidence.
  - The authenticated top bar includes a persisted Light/Dark theme toggle.
- **Data/schema impact:** Additive SQLite tables persist extended MIB values and
  poll status. Existing database initialization/migrations remain idempotent; no
  destructive migration is introduced.
- **Packaging/upgrade impact:** Reconstructed EL10 spec/build/inspection/smoke
  tooling targets release `-16`. Source and build flow normalize Windows CRLF;
  `/usr/bin/netconfig` is LF-only with a Python 3.12 shebang. The release bump is
  required so `dnf upgrade` replaces the broken `-15` launcher installation.
- **Security impact:** SNMPv3 engine discovery and RFC 3414 localized keys are
  cached per poll, removing repeated CPU-intensive derivation. Compliance probe
  errors no longer produce false passes. No credentials or secrets were added.
  `.gitignore` excludes local databases, vaults, MIB indexes, environment files,
  keys, certificates, logs, caches, and RPM build outputs.
- **Validation completed:** Windows Python 3.12 `compileall` passed; bundled
  offline self-test completed with `RESULT: ALL PASS`; packaging/version/payload
  static checks passed; 50-file artifact, private-key/certificate, high-confidence
  secret, and large-file scans passed. Launcher and packaging scripts were
  checked for Linux LF endings.
- **Validation outstanding:** AlmaLinux Bash syntax check; actual RPM/SRPM build;
  RPM inspection; `-15` to `-16` upgrade; installed smoke test; systemd/SELinux;
  live SSH, SNMP/MIB, TLS/HTTP, compliance, NetFlow, and device integration.
- **Known risks/limitations:** Windows cannot validate RPM macros, executable
  modes, systemd sandbox behavior, or Unix-only `pty` transport. Extended MIB
  collection remains deliberately bounded. Current ARP collection does not yet
  provide modern cross-device IP-to-MAC-to-switch-port correlation.
- **Rollback notes:** Retain a known-good RPM and database/config backup before
  upgrading. Application schema changes are additive, but package downgrade and
  restored application code should be tested on a copy of production data.
- **Recommended next step:** Build and inspect `-16` on AlmaLinux 10.2, perform
  the installed smoke test and live regression checks, then begin Slice 1:
  modern `ipNetToPhysicalTable` neighbor collection.

## Planned Delivery Slices

The current canonical development sequence is maintained in `ROADMAP.md`. The 2026-09-07 handover
reconciled the old list after LLDP/CDP topology, syslog-triggered collection, read-only API and scheduled
digest were implemented. Do not use an older numbered list from historical patch entries as current truth.

## PATCH-20260902-01 — Topology, event-driven collection, API and digest

- **Status:** Implemented; live device/event integration testing deferred.
- **Scope:** LLDP/CDP fleet topology and unmanaged-neighbour detection, bounded syslog-triggered immediate config collection, scoped read-only bearer API, and scheduled compliance/drift email digest.
- **Data/schema impact:** Additive SQLite tables `l2_neighbors`, `syslog_events`, `api_tokens`, and `digest_runs`; no destructive migration.
- **Security impact:** API tokens are random and hash-only at rest with explicit read scopes; syslog receiver is disabled by default and bounded, and source correlation fails closed to exact inventory peer IP. No write API was added. Session expiry remains deferred unchanged.
- **Validation completed:** pytest 19 passed / 3 existing service-gated integration skips; legacy selftest `RESULT: ALL PASS`; compileall passed.
- **Validation outstanding:** representative real-device LLDP/CDP, production syslog forwarding/relay model, and full GitHub CI (Ruff/mypy/protocol services).
- **Recommended next step:** add SNMP traps and richer topology identity/VLAN correlation after live validation of this slice.


## PATCH-20260907-01 — New-chat handover and roadmap reconciliation

- **Status:** Complete documentation/packaging-hygiene handover; no runtime feature change intended.
- **Target release:** Source handover only. Current RPM spec remains `2.0.0-17`; decide/bump the next
  Release before building a new distributable RPM because significant development landed after the
  historical `-17` changelog entry.
- **Scope:** Prepare a self-contained next-chat handover, current testing evidence, prioritized roadmap
  and reusable handover prompt; reconcile stale Git and packaging references.
- **Files changed:** `HANDOVER_2026-09-07.md`, `TESTING_RESULT_2026-09-07.md`, `HANDOVER_PROMPT.md`,
  `ROADMAP.md`, `DEVELOPMENT.md`, `AI_HANDOFF.md`, `AGENTS.md`, `patch.md`, packaging/install docs and
  the release-agnostic artifact listing in `packaging/build-rpm.sh`.
- **User-visible behavior:** None.
- **Data/schema impact:** None.
- **Packaging/upgrade impact:** Documentation examples now match spec Release 17; `build-rpm.sh` no
  longer hardcodes Release 16 when listing generated RPMs. No RPM was built or installed.
- **Security impact:** No runtime security behavior changed. Session lifetime remains deliberately deferred.
- **Validation completed:** pytest 19 passed / 3 skipped; legacy selftest `RESULT: ALL PASS`; compileall
  passed; repository text CR scan found 0 offenders; packaging shell syntax is checked in the final
  handover packaging pass.
- **Validation outstanding:** Ruff/mypy in Python 3.12 CI, service-backed protocol integration, AlmaLinux
  RPM build/install, real-device remediation/LLDP/CDP, and production syslog relay qualification.
- **Known risks/limitations:** Historical sections still describe older releases for chronology; use
  `HANDOVER_2026-09-07.md`, `TESTING_RESULT_2026-09-07.md`, and the current `ROADMAP.md` as present truth.
- **Rollback notes:** Documentation/packaging-reference changes only; no database/runtime rollback required.
- **Recommended next step:** Begin Roadmap Slice A — qualification and release gate closure.


## 2026-09-11 — D.5 Phase 4A

- Added incident lifecycle source/model/schema/CLI/API foundation and bundle linkage.
- Added `incident:read` / role-gated `incident:write`.
- Repaired missing Phase 3D `debug:download` / `debug:admin` token scope registration.
- Added incident and additive-schema regression tests.
- No console session lifetime change.


## 2026-09-11 — D.5 Phase 4B

- Added `incident_evidence_links` additive schema and reference-only incident evidence model.
- Added audit/syslog/collection/compliance evidence linking plus immutable archived drift references.
- Added unified incident timeline, missing-source markers, CLI operations and scoped REST endpoints.
- Updated complete source baseline documentation and packaging spec source Release to 19.
- Repository verification before packaging: 33 passed / 3 skipped; incident tests 14 passed; selftest ALL PASS; compileall PASS.


## PATCH-20260911-03 — Roadmap track normalization

- **Status:** Complete documentation-only reconciliation; no runtime/API/schema change.
- **Scope:** Promote `ROADMAP.md` Current/Next and track-based planning as canonical. Demote the 2026-09-07 Slice A-G sequence to historical provenance only.
- **Current/next:** CURRENT is D.5 Phase 4B Incident Timeline; NEXT is D.5 Phase 4C Support Case Export.
- **Tracks:** Diagnostics; Network Intelligence; Platform Hardening. Historical A-G work is mapped into those tracks rather than deleted.
- **Handoff impact:** New chats must follow the current `ROADMAP.md` NEXT item, not older patch/handover text that says Slice A is next.
- **Runtime impact:** None. Session idle/absolute expiry remains deliberately deferred and unchanged.
- **Artifact gate:** Roadmap-refresh candidate passed 101/101 source/extracted identity, 97/97 manifest payload, ZIP CRC, traversal/symlink/CR checks, extracted 67/3 pytest, closeout-focused 3/3, selftest and compileall/package syntax.
- **Recommended next step:** D.5 Phase 4C — Support Case Export.


## 2026-09-11 — D.5 Phase 4C Support Case Export

- Added managed support-case export source (`caseexport.py`) and additive `incident_case_exports` metadata.
- Added bounded reference-only case archives with selected linked diagnostic bundles, SHA-256 file/archive integrity metadata and credential-assignment redaction for free-text case metadata.
- Added role-gated `incident:export`, CLI `incident export-case|exports`, and REST create/list/download with audit evidence.
- Case download now verifies durable size/SHA-256 and fails closed/audits on tampering; case/debug HTTP downloads stream files in bounded chunks instead of whole-file memory buffering.
- Preserved authoritative evidence boundaries: external syslog/audit/compliance/config bodies are not copied into Incident case indexes; linked bundles are embedded byte-for-byte.
- Advanced RPM source spec Release to 20; RPM build/install remains unclaimed.
- Repository verification before final packaging: 39 passed / 3 skipped; incident/case tests 20 passed; selftest ALL PASS; compileall PASS.
- Current/next: CURRENT is D.5 Phase 4C Support Case Export; NEXT is D.5 Phase 4D Evidence / Manifest Signing.


## 2026-09-11 — D.5 Phase 4D Evidence / Manifest Signing

- Added `evidence_signing.py`: fixed OpenSSL/Ed25519 signer and extraction-free verifier.
- External private-key boundary: systemd credential first, protected file fallback; no private key in source/state/export.
- Added signed diagnostic/support-case manifests, embedded public key/signature metadata, independent fingerprint trust pins and signing-required policy.
- Added additive case-export signature metadata, CLI/API verification, signing-status and verification audit.
- RPM source Release bumped to `2.0.0-21` and `/usr/bin/openssl` added as runtime requirement.
- Current/next: CURRENT is D.5 Phase 4D; NEXT is D.5 Phase 4E Protocol Trace Capture.


## 2026-09-11 — D.5 Phase 4E Protocol Trace Capture

- Added bounded metadata-only `ProtocolTraceStore` and additive trace session/event tables.
- Added CLI/OpenSSH command metadata and context-local SNMP UDP-exchange metadata capture with strict redaction/no raw payloads.
- Added Incident `protocol_trace` evidence, case/debug export inclusion, `trace:read`/`trace:capture`, CLI and REST lifecycle.
- NETCONF/RESTCONF use the future-ready schema but fail closed until providers exist.
- Current/next: CURRENT is D.5 Phase 4E; NEXT is D.5 Phase 4F Incident Web Console.


## 2026-09-11 — D.5 Phase 4F Incident Web Console

- Added `/incidents` register/filter and `/incident` detail console surfaces.
- Unified lifecycle, timeline, evidence, bounded trace, diagnostic-bundle and signed support-case workflows.
- Preserved viewer read-only, operator+ mutation, CSRF, evidence-reference, trace redaction/bounds and case verification boundaries.
- Added focused web security/regression tests; repository result is 64 passed / 3 skipped before packaging.
- Current/next: CURRENT is D.5 Phase 4F; NEXT is D.5 Closeout / Diagnostic Qualification Review.


## D.5 Closeout / Diagnostic Qualification Review — 2026-09-11

- Added opt-in bounded diagnostic retention scheduler and one-shot CLI maintenance.
- Added support-bundle count retention, case-export archive age retention with durable metadata preservation, and unlinked inactive protocol-trace age retention.
- Added Monitoring settings for the closeout maintenance policy.
- Kept automatic maintenance disabled by default and protected Incident-linked trace evidence from generic pruning.
- Offline regression: 67 passed / 3 skipped; focused closeout 3 passed; selftest ALL PASS.
- D.5 remains IMPLEMENTED_TESTING_DEFERRED pending external CI/service/RPM/live-device qualification.

## PATCH-20260911-04 — Post-closeout roadmap naming clarification

- **Status:** Complete documentation-only reconciliation; no runtime/API/schema change.
- **Clarification:** D.5 is a standalone Diagnostics track inserted historically between Slice D and Slice E; it is **not Slice E**.
- **Current/next:** CURRENT is D.5 Closeout / Diagnostic Qualification Review (`IMPLEMENTED_TESTING_DEFERRED`); NEXT is Network Intelligence Track -> VLAN-aware endpoint and topology correlation.
- **Historical mapping:** The NEXT Network Intelligence item maps to old Slice B. Old Slice E remains Platform Hardening -> Web-console structural hardening.
- **Metadata repair:** Updated stale Phase 4F/D.5-closeout handoff wording and stale RPM source-release references to the current `2.0.0-24` source spec.
- **Runtime impact:** None. Session idle/absolute expiry remains deliberately deferred and unchanged.

## PATCH-20260911-05 — Source baseline executable-mode / RPM-doc repair

- **Scope:** Packaging/documentation only; no runtime/API/schema behavior change.
- **Executable mode:** Preserve `0755` in the FULL source ZIP for `usr/bin/netconfig` and the three RPM helper shell scripts.
- **Documentation:** Active RPM build/install examples now reference source Release `2.0.0-24`; historical changelog/patch provenance is retained.
- **Gate:** Re-run complete regression plus extracted-artifact CRC/path/symlink/checksum/mode/direct-execution checks before publication.


## 2026-09-11 — Network Intelligence NI-1

Implemented VLAN-aware endpoint attachment correlation: IP-MIB `ipNetToPhysicalTable`, Q-BRIDGE FDB/VLAN evidence, additive neighbour/FDB tables, LLDP/CDP transit suppression, explicit ambiguity/staleness, `endpoint:read` API, CLI `endpoints`, Web Endpoints page, metrics and tests. Source RPM Release: `2.0.0-25`. Live vendor/RPM qualification remains deferred.

## 2026-09-11 — Network Intelligence NI-2

Implemented normalized LLDP/ENTITY-MIB chassis and IF-MIB interface identity, unique-evidence managed-neighbour resolution with explicit ambiguity, bounded cycle-safe downstream impact, CLI/API/Web exposure, additive persistence and focused tests. Full source-workspace regression: **83 passed / 3 skipped**; NI-2 focused **8 passed**. RPM source Release: `2.0.0-26`. Live vendor/RPM qualification remains deferred.

NI-2 candidate artifact integrity passed: 104/104 stage/extracted files, 100/100 payload/manifests, exact hidden paths, 0755 executable modes, archive-security checks and extracted regression 83 passed / 3 skipped with focused NI-2 8 passed.

## 2026-09-11 — Network Intelligence NI-3

Implemented bounded SNMP v1/v2c Trap ingestion, normalized/durable operational events, event deduplication, targeted SNMP re-poll, NI-2 dependency-aware suppression, unified syslog/SNMP reachability events, CLI/API/Web exposure and settings. Full source-workspace regression: **91 passed / 3 skipped**; NI-3 focused **8 passed**. RPM source Release: `2.0.0-27`. SNMPv3 trap authentication, INFORM acknowledgement, live Net-SNMP/vendor and RPM qualification remain deferred.

NI-3 candidate source-baseline gate passed: 107/107 identity, 103/103 manifests, 0755 preserved, extracted 91/3 + focused 8 + selftest/compile/shell PASS. Final FULL source baseline rebuilt afterward.


## 2026-09-11 — Network Intelligence NI-4

Implemented operational event-to-alert promotion, audited acknowledge/resolve lifecycle, maintenance windows, bounded durable SMTP retry/backoff, scheduled operational reports, `alerts:read/write` and `reports:read/write`, CLI/API/Web surfaces, and opt-in lifecycle scheduling. Full source-workspace regression: **99 passed / 3 skipped**; focused NI-4 **8 passed**; legacy selftest **ALL PASS**. RPM source Release: `2.0.0-28`. Live SMTP/service/RPM/vendor qualification remains deferred.


### NI-4 candidate artifact evidence

Candidate `netconfig_network_intelligence_ni4_candidate_2026-09-11.zip` SHA-256 `17ed1297a863eaca2eeb4a92f5bddcf3ab120804d2526c63339bda79ae1569e3` passed clean system-unzip validation: **109/109** artifact files present, **105/105** Release payload entries and each of the three SHA manifests verified, exact hidden paths retained, four executable files preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and all **19/19** Markdown files carried the NI-4/PH-1/Release-28 current-state pointer. Extracted regression: **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## 2026-09-11 — Platform Hardening PH-1

Implemented Web-console structural/CSP hardening: extracted `web_api.py` and `web_ui.py`, reduced `web.py` below 4,000 lines / 240 KB, enforced per-response script/style nonces with script/style attribute denial, removed inline HTML event handlers, normalized server-rendered style attributes to generated nonce-authorized classes, and added script-context/XSS regression coverage. Source regression **105 passed / 3 skipped**; focused PH-1 **6 passed**; selftest **ALL PASS**. RPM source Release: `2.0.0-29`.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## PATCH-20260911-30 — Platform Hardening PH-2 PostgreSQL Core / Distributed Operation

Status: Ready for integration (source implementation; live PostgreSQL/RPM qualification deferred).

- Added opt-in PostgreSQL core storage with cross-dialect schema bootstrap and fail-closed startup.
- Added storage schema revision/readiness, protected pre-vault DB credential sourcing, and systemd credential guidance.
- Added cluster heartbeat, PostgreSQL advisory-lock scheduler leadership, and `FOR UPDATE SKIP LOCKED` distributed task claiming.
- Added local storage CLI and fail-closed SQLite→PostgreSQL migration with serial-sequence repair.
- Offline verification: PH-2 focused 9 passed; full repository 114 passed / 3 skipped.

PH-2 candidate packaging integrity: `6dfd6e554b08883c51a6f268bbe604bf95cc7819dad8f4bda6f023d688807d21`; 114/114 files, 110/110 manifests, hidden paths/modes/security gates PASS, extracted repository 114/3 and PH-2 9/9 PASS. Final artifact rebuilt afterward.

## PATCH-20260916-RPM37 — Release 37 RPM installation hardening

- **Target package:** `2.0.0-37`.
- Bump `packaging/netconfig.spec` Release from 34 to 37 for the current NI-6 source baseline.
- Add guarded AlmaLinux 10 `packaging/install-rpm.sh` with explicit fresh-install administrator bootstrap and safe upgrade preservation.
- Rewrite current RPM installation/build documentation and add root `INSTALL_RPM.md`.
- Preserve `IMPLEMENTED_TESTING_DEFERRED`: source/offline checks pass; real AlmaLinux RPM build/install gate remains `NOT_RUN` on the Debian artifact runner.

## PATCH-20260917-NI7 — Release 40 — L3/VRF Path & Route Dependency Intelligence

- **Parent:** Release 39 Q-1 Production Qualification Hardening v5.
- **Target RPM release:** `2.0.0-40`; schema revision `ni7-l3-route-1`.
- **Scope:** durable route observations; same-VRF bounded path simulation; route dependency candidates; `L3_PATH`/`ROUTE_DEPENDENCY` insights; API/UI integration.
- **Safety:** no next-hop identity inference, no VRF crossing, no arbitrary ECMP selection, no direct remediation/configuration execution.
- **Verification before packaging:** NI-7 focused **5 passed**; full repository **211 passed / 7 skipped / 0 failed**. Q-1 live gates remain deferred.

## 2026-09-23 — Release 50 MC-2 completion patch

- fixed missing `SensorEngine.history` initialization in the MC-2.2 working source;
- completed durable observation/transition recording and threshold-aware severity normalization;
- preserved previous active Sensor rows through generator refresh so transitions are detectable;
- added restart-safe unchanged-state suppression and UNKNOWN evidence semantics;
- added bounded 30d/180d history retention and supporting indexes;
- added read-only history/transition APIs and device transition timeline;
- added MC-2 focused/API/WebUI/retention/index tests.

## PATCH-20260923-R51-HF1 — Pre-MC4 SNMPv3 + Topology compatibility hotfix

- **Parent:** Release 51 / MC-3 Normalized Operational Evidence (`2.0.0-51`).
- **Historical status at patch time:** `IMPLEMENTED_TESTING_DEFERRED`; MC-4 / Release 52 was then `PLANNED` and is now superseded by the implemented Release 52 baseline.
- **SNMPv3:** generic AES-192/AES-256 uses Blumenthal key extension compatible with Net-SNMP; Cisco/Reeder is explicit `aes192c` / `aes256c`.
- **Topology CLI:** `--discover` unlocks the Vault in-process before credentialed discovery.
- **Topology truth:** every managed inventory device appears as a node; LLDP/CDP is `OBSERVED`; unique persisted FDB/MAC correlation may add non-direct `INFERRED` paths; inferred paths are excluded from downstream-impact traversal.
- **Web/API:** interactive dependency-free drag/pan/zoom topology canvas with browser-local layout only; added read-only `GET /api/v1/topology/graph`.
- **Device I/O:** none added; graph/UI/API consume already-persisted evidence.
- **Verification:** hotfix focused 8 passed; combined topology/Web/PH-1/legacy 40 passed; bounded repository aggregate 278 passed / 8 skipped / 0 failed; legacy selftest ALL PASS; compileall/launcher/shell syntax PASS; Ruff/mypy NOT_RUN.
- **Deferred:** live FortiGate SHA1+AES256 confirmation, real vendor topology/FDB behavior, live PostgreSQL/backup/protocol services, formal RPM qualification.


## R61 changes

Added scale/performance qualification runner, isolated synthetic benchmark, fixed live hooks/templates, capacity/load profiles, percentile/resource measurement, MC-10 bounded overload probe, Release 61 packaging identity, tests and synchronized documentation. No persisted schema change and no network/configuration authority expansion.

## Release 62

Added PostgreSQL fail-closed connection recovery, bounded retry-safe DB-only transactions, transaction concurrency budget, same-identity MC-11 planning and external-evidence concurrency serialization, R62 qualification runner/hooks, tests, packaging identity `2.0.0-62`, and synchronized release documentation.


## R62.1 security/package patch

Closed RESTCONF redirect SSRF/TLS-downgrade exposure, hardened SSH argv target parsing, removed reviewed dead code, expanded the upstream Git mode repair patch to all current required executables, and assigned distinct package Release `62.1`.

## R63 patch summary

Release 63 adds session-generation-aware PostgreSQL advisory fencing, node identity/failure-domain metadata, scheduler revalidation/takeover, fenced distributed-task ownership and explicit partial-job recovery, plus fixed-hook HA qualification tooling. Package release advances to 63; persisted schema identity remains MC-11.

## R63 verified clean-extract truth — 2026-09-24

The provisional source archive was extracted with system `unzip` and reproduced **477 collected / 463 passed / 14 skipped / 0 failed**. R63 focused coverage is **16/16 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, launcher/qualification `py_compile`, packaging/qualification/tool shell syntax, and legacy selftest are PASS. The provisional structural gate is **348 entries / 0 duplicates / 0 unsafe paths / 0 symlinks / CRC PASS / 348/348 byte+mode parity / 346/346 R63 source manifest / 347/347 whole-tree SHA256SUMS / 26/26 executable modes**. Two clean-extract helper RPM rebuilds are byte-identical to each other and to the source-tree RPM; independent verification passes. RPM SHA-256 is `1e2a40476c212d2ffe410d51ef1cd9b2fac3051fc96bf30789539be5bca4b60d`. This is local/offline artifact evidence only; live HA remains deferred.


## R65 change summary

Release 65 (`2.0.0-65`) implements Operator Workflow Completion on top of R64. The persisted-data-first journey binds Incident → MC-11 plan → exact persisted proposal → existing Automation Request/approval → Structured Change → verification/recovery/rollback → Incident-linked post-change evidence. It adds no MC-12, no parallel write authority, no page-triggered polling, and no schema migration. Status remains `IMPLEMENTED_TESTING_DEFERRED`; `LIVE_OPERATOR` evidence is still required for production operator-workflow claims. Next approved track is R66 Observability / Supportability and is not started.
