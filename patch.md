# NetConfig Patch Ledger

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.

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

> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

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
