# NetConfig development baseline

> **Canonical project state — 2026-09-16:** **CURRENT IMPLEMENTATION BASELINE** = **Release 37 / NI-6 Enterprise Operations & Qualification Hardening** (`IMPLEMENTED_TESTING_DEFERRED`). RPM/package version identity is `2.0.0-37`; NI-6.1 through NI-6.6 are complete in source, and NI-6 is now wired through `Manager.analytics` to scoped REST API and the Operations Network Intelligence console. Q-1 Ruff/mypy and live PostgreSQL/protocol/vendor/device/scale gates remain deferred and are not PASS.

## Release 34 baseline identity

- Parent artifact: `netconfig_release33_FULL_source_baseline_2026-09-12.zip`
- Parent SHA-256: `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`
- Current application version: `2.0.0`
- Current RPM source Release: `34`
- Current phase: UI-1 — Unified Automation & Operations Console
- Status: `IMPLEMENTED_TESTING_DEFERRED`
- Schema revision: unchanged from Release 33 (`ha1-2`)
- Primary new source: `opt/netconfig/netconfig/web_ops.py`, telemetry edit contract, Web/API route wiring, UI-1 tests and synchronized documentation.


## Release 33 baseline

Application/project Version: `2.0.0`. RPM source Release: `33`. Database schema revision: `ha1-2`.

Source includes PH-4 structured transactions, NI-5 telemetry/time-series foundation, VM-1 vendor model packs, NA-1 desired state, NA-2 fleet campaigns and HA-1 control-plane recovery/drain foundation. All are `IMPLEMENTED_TESTING_DEFERRED`; Q-1 real-service/RPM qualification remains outstanding. The source tree is the authoritative modifiable baseline; no claim is made that Release 33 RPM or real network devices have been qualified until corresponding evidence exists.

> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

## Historical Q-1 baseline note

At the Q-1 baseline checkpoint, **Qualification Q-1 — Production Runtime & Service-backed Qualification** was the active track, status `IMPLEMENTED_TESTING_DEFERRED`; PH-3 was then the latest feature baseline. That historical baseline used RPM source Release `32` and schema revision `ph3-1`. Release 33 supersedes it as the active implementation source.

Q-1 source adds runtime preflight, controlled PostgreSQL backup/restore, real PostgreSQL qualification tests, AlmaLinux/RPM qualification harnesses, hardened backup systemd service, and CI coverage for PostgreSQL client recovery tooling. Current local evidence before final packaging is **147 passed / 7 skipped**, Q-1 focused **11 passed**. Ruff/mypy, real PostgreSQL, and AlmaLinux install gates are explicitly `NOT_RUN` in this environment. No Q-2 is assigned.

Historical PH-3 closeout immediately preceded Q-1. Release 33 subsequently implemented PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 while leaving Q-1 qualification open. Historical Slice labels are provenance only; D.5 remains the separate completed-in-source Diagnostics Track.

- Application version remains NetConfig 2.0.0; packaging spec source Release is 33 for the active Release 33 baseline.
- Application source: `opt/netconfig/netconfig/`.
- Tests: `tests/` plus legacy `opt/netconfig/selftest.py`.
- RPM/build integration: `packaging/`, `etc/`, and `usr/`.
- Canonical current engineering state: `DEVELOPMENT.md`, `ROADMAP.md`, `SECURITY.md`, `API.md`, `TESTING.md`, `AI_HANDOFF.md`.

This source tree is a complete modifiable development baseline, not an installed-RPM image. RPM Release 33 has **not** been built or installed in this environment because the current host is not AlmaLinux and lacks `rpmbuild`; that gate remains `NOT_RUN`. Historical RPM/handover material is provenance only and must not override current source truth.

Phase 4C adds bounded managed Support Case Export on top of the Phase 4B reference-only Incident Timeline. It packages Incident-owned metadata, reference indexes and selected linked diagnostic bundles without copying authoritative event/report/config payloads into Incident state. Phase 4A lifecycle and Phase 3D debug download/admin scope repair remain intact. Session idle/absolute expiry remains deliberately deferred.

Before any new implementation phase, complete consolidated Release 33 verification and execute the available deferred Q-1 service/RPM qualification gates. Then perform a new roadmap review before naming another phase.


## Phase 4C baseline note

Support-case export is implemented through `SupportCaseExporter`: durable `incident_case_exports`, managed `case-exports/`, reference-only Incident/timeline indexes, selected linked diagnostic bundles, SHA-256 manifests, CLI/API create/list/download, dedicated role-gated `incident:export`, and audit evidence. This describes the Phase 4C foundation; Phase 4D signing is now layered on top as documented below.


## Phase 4D baseline note

Evidence signing is now implemented for diagnostic bundles and support-case exports. Use external Ed25519 private-key delivery only; never add private key material to source, SQLite, settings JSON, bundles or case archives. Verification must preserve the distinction between `signature_valid` and independently `trusted`. The embedded public key alone is not an authenticity anchor.

Final Phase 4D handoff package: `netconfig_d55_phase4d_FULL_source_baseline_2026-09-11.zip`. Source-baseline/artifact gate must remain clean before using it for Phase 4E.


## Phase 4E baseline note

Protocol trace capture is implemented as bounded metadata-only evidence. `protocoltrace.py` provides durable sessions/events, Incident linkage, CLI/REST lifecycle, SSH command metadata and SNMP UDP-exchange metadata capture. Sensitive CLI commands use a constant redaction marker; raw SSH output/SNMP packets and protocol credentials are never trace payload. Historical Phase 4E note: NETCONF/RESTCONF were provider-not-implemented at that time; PH-3 supersedes that limitation with bounded metadata trace providers.

Final Phase 4E handoff package: `netconfig_d55_phase4e_FULL_source_baseline_2026-09-11.zip`.

Phase 4F adds only Web Console orchestration over existing Incident/timeline/trace/export services; no new schema was required. Viewer is read-only and browser mutations remain CSRF-protected.


## Phase 4F baseline note

Incident Web Console is implemented as a human-operator layer over the existing Incident, timeline/evidence, protocol trace, diagnostic-bundle and support-case services. Viewer remains read-only; operator/approver/admin mutations remain CSRF-protected and service-validated. Case downloads reuse integrity/signature/trust verification before chunked streaming. No Phase 4F schema migration was required.

Final Phase 4F handoff package: `netconfig_d55_phase4f_FULL_source_baseline_2026-09-11.zip`.


## D.5 closeout baseline — 2026-09-11

Current feature position: D.5 planned feature phases complete through closeout; status remains **IMPLEMENTED_TESTING_DEFERRED** because external qualification is incomplete. Offline regression is **67 passed / 3 skipped**, focused closeout **3 passed**, selftest **ALL PASS**. RPM source metadata is `2.0.0-24`; no RPM build/install qualification is claimed. Next product-development track is VLAN-aware endpoint/topology correlation.


Current closeout delivery package: `netconfig_d55_closeout_FULL_source_baseline_2026-09-11.zip` (checksum recorded in final delivery response and release manifest).

Current refreshed handoff package: `netconfig_d55_closeout_roadmap_refresh_repacked_FULL_source_baseline_2026-09-11.zip`.

## Network Intelligence NI-1 baseline — 2026-09-11

NI-1 establishes the source-of-truth evidence and conservative correlation layer for `IP -> MAC -> VLAN -> switch/port`. Modern IP-MIB and Q-BRIDGE observations are persisted separately from legacy compatibility views. VLAN, direct attachment and confidence are never guessed across ambiguous mappings/candidates. Pre-package regression: **75 passed / 3 skipped**, NI-1 focused **8 passed**. RPM source metadata is `2.0.0-25`; no RPM/live-vendor qualification is claimed.

Current NI-1 handoff artifact name: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. Use this as the sole baseline for NI-2 after its final artifact gate passes.

Current synchronized Markdown baseline artifact: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. Markdown synchronization does not change runtime/API/schema or source RPM Release 25. Workspace regression remains **75 passed / 3 skipped**, NI-1 focused **8 passed**, selftest **ALL PASS**.

## Network Intelligence NI-2 baseline — 2026-09-11

NI-2 adds normalized chassis/interface identity, fail-closed managed-neighbour resolution, and bounded observed-L2 downstream impact. Current source-workspace evidence is **83 passed / 3 skipped** with NI-2 focused **8 passed**. Source RPM metadata is `2.0.0-26`; live vendor/RPM qualification is not claimed. Intended handoff artifact: `netconfig_network_intelligence_ni2_FULL_source_baseline_2026-09-11.zip` after artifact-gate completion.

NI-2 candidate package independently passed clean-extraction artifact integrity: **104/104** complete file identity, **100/100** payload/manifest validation, exact hidden paths, executable-mode preservation and extracted regression **83 passed / 3 skipped** with NI-2 focused **8 passed**. Final handoff ZIP is rebuilt after recording this evidence.

## Network Intelligence NI-3 baseline — 2026-09-11

NI-3 adds bounded SNMP trap ingestion and a durable unified operational event stream with deduplication, targeted re-poll and NI-2 managed-L2 dependency suppression. Current source-workspace evidence is **91 passed / 3 skipped** with focused NI-3 **8 passed**. Source RPM metadata is `2.0.0-27`; live Net-SNMP/vendor/RPM qualification is not claimed. Intended handoff artifact: `netconfig_network_intelligence_ni3_FULL_source_baseline_2026-09-11.zip` after artifact-gate completion.


## Network Intelligence NI-4 baseline — 2026-09-11

NI-4 adds a durable lifecycle on top of NI-3 normalized operational events: severity-threshold promotion, `OPEN -> ACKNOWLEDGED/RESOLVED`, device/global maintenance windows that suppress alert creation without deleting event evidence, bounded SMTP delivery retry/backoff, and durable scheduled operational report runs. The legacy monitor-rule `alerts` table remains separate and compatible. Source-workspace evidence is **99 passed / 3 skipped**, focused NI-4 **8 passed**, legacy selftest **ALL PASS**. Source RPM metadata is `2.0.0-28`; live SMTP/service/RPM qualification is not claimed.

Intended complete handoff artifact: `netconfig_network_intelligence_ni4_FULL_source_baseline_2026-09-11.zip` after final artifact-gate completion.


NI-4 candidate artifact gate passed with 109/109 files, 105/105 payload manifests, exact hidden paths, preserved 0755 modes, and extracted 99/3 + focused 8 + selftest/compile/shell PASS. Final continuation must use `netconfig_network_intelligence_ni4_FULL_source_baseline_2026-09-11.zip` only after its own clean-extraction gate.

## 2026-09-11 — Historical baseline: Platform Hardening PH-1

Historical PH-1 snapshot: PH-1 decomposes the Web console without changing routes/API semantics: `web.py` delegates bearer API handling to `web_api.py` and presentation/assets to `web_ui.py`; strict per-response CSP nonces are enforced for script/style elements; HTML event/style attributes are denied after render normalization. Current source regression is **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**. Source RPM metadata is `2.0.0-29`. Intended complete artifact: `netconfig_platform_hardening_ph1_FULL_source_baseline_2026-09-11.zip` after final artifact gate. Next recommended phase at that historical point: **PH-2 — PostgreSQL Core & Distributed Operation**.

### PH-1 candidate artifact evidence

Candidate `netconfig_platform_hardening_ph1_candidate_2026-09-11.zip` SHA-256 `d8590fe771cbea6ff1a521880b07d8562bde06b2de560b77cafa5e202dac2f34` passed clean system-unzip validation: **112/112** artifact files identity, **108/108** Release payload and all three SHA manifests, exact hidden paths, four executables preserved as `0755`, ZIP CRC/path-traversal/symlink/cache/CR gates passed, and **57/57** Markdown current-state checks passed. Extracted regression: **105 passed / 3 skipped**, focused PH-1 **6 passed**, legacy selftest **ALL PASS**, compileall/launcher/package-shell syntax **PASS**. Direct `build-rpm.sh` executes and exits `2` only because `rpmbuild` is unavailable.

## Historical PH-2 baseline update — 2026-09-11

- Historical state at PH-2 completion: Platform Hardening PH-2 (`IMPLEMENTED_TESTING_DEFERRED`), next PH-3.
- RPM source metadata at that point: `2.0.0-30`.
- Offline regression at that point: 114 passed / 3 skipped; PH-2 focused 9 passed.
- Production truth boundary: PostgreSQL/live multi-node/HA/RPM qualification remains deferred.

PH-2 candidate artifact independently passed clean extraction: 114/114 source identity, 110/110 manifest payload, exact hidden paths, four 0755 executables, 19/19 Markdown current-state alignment, extracted pytest 114 passed / 3 skipped, PH-2 focused 9 passed, selftest ALL PASS and compile/shell PASS. Final baseline is rebuilt after recording this evidence.


## PH-3 baseline update — 2026-09-12

PH-3 is implemented in source and remains `IMPLEMENTED_TESTING_DEFERRED`.

The structured adapter contract now includes NETCONF hello/capability negotiation plus fixed bounded `<get>` / `<get-config>` reads; RESTCONF HTTPS discovery, strict path/content/TLS validation and an internal approval-gated verified/rollbackable JSON subtree replace; and gNMI Capabilities/Get/typed-path ONCE Subscribe with TLS/mTLS/deadline/size controls. Runtime secrets remain vault-resolved. Generic RPC/URL/body/protobuf passthrough, NETCONF edit-config, gNMI Set and shell tunnelling are not exposed.

Manager/CLI read surfaces expose capabilities, operational state and gNMI ONCE Subscribe; bearer API adds protocol capabilities/state reads. Existing profile/collect compatibility remains. Protocol traces remain metadata-only, and structured failures remain fail-closed unless explicit CLI fallback is configured.

Offline regression before final packaging: **136 passed / 3 skipped**; PH-3 focused **22 passed**. The three skips are service-backed OpenSSH, Net-SNMP and PostgreSQL integrations and remain deferred. Final selftest/compile/shell/manifest/clean-extraction evidence is recorded in `TESTING_RESULT_2026-09-12.md`.

Clean candidate `netconfig_platform_hardening_ph3_candidate_completed_2026-09-12.zip` (SHA-256 `ea4c2f56f277e76ab85f49b0647269799002d00d5ee79fedd5f6f0fa84450136`) passed system-unzip validation: **118/118** source byte identity; **114/114** entries in `RELEASE_MANIFEST.json` and each of the three SHA manifests; ZIP CRC **PASS**; traversal **0**; symlinks **0**; caches **0**; CR offenders **0**; hidden control paths **3/3 exact**; required executable modes **4/4 = 0755**; extracted focused PH-3 **22 passed**; extracted full regression **136 passed / 3 skipped**; legacy selftest **ALL PASS**; compileall/launcher py_compile/packaging shell syntax **PASS**. The direct RPM helper exits `2` only because `rpmbuild` is unavailable.

Live NETCONF/RESTCONF/gNMI devices, vendor behavior, TLS/mTLS interoperability, production credential rotation, packaged `gnmic`, real PostgreSQL multi-node/HA/PITR/backup-restore, AlmaLinux RPM/systemd, Ruff/mypy, SMTP/O365 and scale/failure qualification are not run and remain release/qualification debt.

No next numbered implementation phase is assigned. Perform the roadmap / qualification review before opening another phase.
