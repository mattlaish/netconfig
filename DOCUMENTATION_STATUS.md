# NetConfig Documentation Status


> **2026-09-29 development update — SNMP Vendor Profile framework:** this working tree adds a data-only, hot-reloadable SNMP Vendor Profile engine on top of the refrozen R67.2 source line. This is a runtime/package payload change, so the previously frozen R67.2 exact-candidate fingerprint and candidate-bound `LIVE_RC` evidence do **not** qualify this working tree. The release identity has intentionally **not** been advanced; that remains an explicit user decision. Project state remains `IMPLEMENTED_TESTING_DEFERRED`; MC-11 remains the final Monitoring / Correlation / Change-Planning feature slice; no MC-12 and no new network-write authority are introduced. Profiles are JSON data, validated fail-closed, bounded to declared numeric OID roots, and cannot execute Python, shell, commands, URLs, or arbitrary expressions.

**Current vendor-profile source evidence:** **556 collected / 542 PASS / 14 SKIP / 0 FAIL** across 12 bounded groups; focused Vendor Profile framework coverage is **8 PASS / 0 FAIL**; `compileall`, actual launcher `py_compile`, packaging/tool/qualification shell syntax, release-metadata check, and legacy selftest are PASS. The 14 skips remain explicit live PostgreSQL/protocol-service prerequisites plus the expected source-archive Git-metadata prerequisite. These are local/source gates only and do not promote the working tree beyond `IMPLEMENTED_TESTING_DEFERRED`.

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Historical Release 53 documentation sync — 2026-09-23

Canonical docs describe MC-5 as `IMPLEMENTED_TESTING_DEFERRED`, Release `2.0.0-53`, schema revision `mc5-incident-evidence-timeline-1`, typed validated Incident references, deterministic source/receive-time timeline semantics, normalized change/external evidence stores, retention-safe unavailable markers, and read-only investigation API/CLI/Web presentation without automatic root-cause claims. R52/MC-4 remains historical predecessor evidence. The next roadmap slice is MC-6 / Release 54. Formal AlmaLinux/RPM/PostgreSQL/vendor qualification remains deferred.

## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

## Release 48 sensor documentation ownership

- `README.md`: product/release positioning and truth boundaries.
- `DEVELOPMENT.md`: implementation ledger and deferred gates.
- `AI_HANDOFF.md`: current continuation state.
- `ARCHITECTURE.md`: persisted-evidence -> Sensor Engine -> read-only consumers boundary.
- `API.md`: `/api/v1/sensors` contract and filters.
- `WEBGUI.md`: sensor-status presentation/UNKNOWN semantics.
- `TESTING.md`: focused/full regression and artifact qualification evidence.
- `ROADMAP.md`: strict `IMPLEMENTED_TESTING_DEFERRED` release state.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Historical roadmap checkpoint — 2026-09-24:** MC-10 and MC-11 were still sequenced at this point. This is chronology only; the current assigned track is R67.2 exact-candidate qualification and the fixed 12-gate `LIVE_RC` campaign. Do not create MC-12.


## 2026-09-18 documentation-only decision sync

Canonical design documentation now records the future Site Edge/Collector survivability model, read-only collector boundary, local alert persistence/replay concept, **Configuration Baselines / Templates & Drift** terminology, non-expansion of approval orchestration, and operator-oriented MIB sensor-card direction. This is documentation-only; Release 45 / `2.0.0-45` and `IMPLEMENTED_TESTING_DEFERRED` remain unchanged.

## Purpose

This file is the documentation truth map. Historical release records retain their original measured counts and decisions; they do not override the current R67.2 / `2.0.0-67.2` / `mc11-topology-change-planning-1` state declared at the top.

## Complete Markdown inventory

| File | Classification | Role |
|---|---|---|
| `ADR/ADR-004-ui1-unified-operations-console.md` | HISTORICAL EVIDENCE | historical release evidence |
| `AGENTS.md` | CURRENT / MAINTAINED | agent engineering instructions |
| `AI_HANDOFF.md` | CURRENT / MAINTAINED | new-session continuation state |
| `API.md` | CURRENT / MAINTAINED | API contract |
| `ARCHITECTURE.md` | CURRENT / MAINTAINED | architecture contract |
| `CLAUDE.md` | CURRENT / MAINTAINED | alternate-agent engineering instructions |
| `CURRENT_PROGRESS_DELIVERY_REPORT.md` | CURRENT / MAINTAINED | current progress snapshot |
| `DELIVERY_REPORT.md` | CURRENT / MAINTAINED | current delivery summary |
| `DELIVERY_REPORT_NI65.md` | HISTORICAL EVIDENCE | historical release evidence |
| `DEVELOPMENT.md` | CURRENT / MAINTAINED | canonical engineering ledger |
| `DEV_BASELINE.md` | CURRENT / MAINTAINED | source baseline contract |
| `DOCUMENTATION_STATUS.md` | CURRENT / MAINTAINED | documentation truth map (this file) |
| `GIT_REPRODUCIBILITY.md` | CURRENT / MAINTAINED | Git reproducibility contract/evidence |
| `HANDOVER_2026-09-07.md` | HISTORICAL EVIDENCE | historical release evidence |
| `HANDOVER_PROMPT.md` | CURRENT / MAINTAINED | handoff prompt / continuation rules |
| `INSTALL_RPM.md` | CURRENT / MAINTAINED | RPM installation lifecycle |
| `NI63_CAPACITY_ANALYTICS.md` | HISTORICAL EVIDENCE | historical release evidence |
| `NI64_FAILURE_RISK.md` | HISTORICAL EVIDENCE | historical release evidence |
| `NI65_IMPACT_SIMULATION.md` | HISTORICAL EVIDENCE | historical release evidence |
| `NI66_HEALTH_DASHBOARD.md` | HISTORICAL EVIDENCE | historical release evidence |
| `NI7_L3_ROUTE_INTELLIGENCE.md` | CURRENT / MAINTAINED | NI-7 current feature contract/evidence |
| `PH6_COMPLETION.md` | HISTORICAL EVIDENCE | historical release evidence |
| `Q1_PRODUCTION_QUALIFICATION.md` | CURRENT / MAINTAINED | active Q-1 qualification contract/evidence ledger |
| `README.md` | CURRENT / MAINTAINED | product entry point / current baseline |
| `ROADMAP.md` | CURRENT / MAINTAINED | roadmap and strict status truth |
| `SECURITY.md` | CURRENT / MAINTAINED | security contract |
| `TESTING.md` | CURRENT / MAINTAINED | current test ledger |
| `TESTING_RESULT_2026-09-07.md` | HISTORICAL EVIDENCE | historical release evidence |
| `TESTING_RESULT_2026-09-11.md` | HISTORICAL EVIDENCE | historical release evidence |
| `TESTING_RESULT_2026-09-12.md` | HISTORICAL EVIDENCE | historical release evidence |
| `TESTING_RESULT_2026-09-13.md` | HISTORICAL EVIDENCE | historical release evidence |
| `VALIDATION_SUMMARY.md` | CURRENT / MAINTAINED | current qualification summary |
| `WEBGUI.md` | CURRENT / MAINTAINED | top-level UI contract |
| `opt/netconfig/CREDENTIALS.md` | CURRENT / MAINTAINED | credential/vault operations guide |
| `opt/netconfig/INSTALL.md` | CURRENT / MAINTAINED | installed-source operations guide |
| `opt/netconfig/README.md` | CURRENT / MAINTAINED | installed product README |
| `opt/netconfig/WEBGUI.md` | CURRENT / MAINTAINED | web console operator guide |
| `packaging/README.md` | CURRENT / MAINTAINED | RPM packaging/operator instructions |
| `patch.md` | CURRENT / MAINTAINED | patch ledger |
| `tools/rpm-builder/README.md` | CURRENT / MAINTAINED | offline RPM builder/verifier usage and qualification boundary |

## Roadmap disposition

- Post-NI-7 roadmap review: **COMPLETE** as of 2026-09-18.
- Current product baseline: **R67.2 / `2.0.0-67.2` / `IMPLEMENTED_TESTING_DEFERRED`**; NI-7 remains included and MC-11 remains the final Monitoring/Correlation functional slice.
- Current assigned track: **R67.2 exact-candidate qualification and the fixed 12-gate `LIVE_RC` campaign**; this is qualification/release work, not a new feature phase.
- Future NI/MC feature work or any new development track requires an explicit roadmap decision; historical `NEXT`/`PLANNED` text is provenance only. **Do not create MC-12.**
- Documentation ownership after this sync: **28 CURRENT / MAINTAINED**, **12 HISTORICAL EVIDENCE**, **40 total Markdown files**.

## Historical Release 46 delivery evidence

- Historical runtime/package source identity at that checkpoint: **Release 46 / `2.0.0-46`**.
- Repository regression: **222 passed / 8 skipped / 0 failed** on the archive-derived source workspace; seven skips are live/service prerequisites and one is the expected Git-index mode skip.
- Focused Web Console/structural regression: **13 passed**.
- Legacy selftest: **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax: **PASS**.
- Offline helper RPM: `netconfig-2.0.0-46.el10.noarch.rpm`, reproduced byte-for-byte twice and independently verified; SHA-256 `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`.
- Ruff `0.16.7` and mypy `2.3.1`: **NOT_RUN** because executables are unavailable.
- Canonical AlmaLinux 10 `rpmbuild`/DNF/systemd/SELinux and remaining Q-1 live/device gates: **NOT_RUN / DEFERRED**.
- Complete-source delivery target: `netconfig-2.0.0-48-sensor-model-evidence-normalization-v25.zip`.

## Historical 2026-09-18 Release 45 all-Markdown sync evidence

- Markdown files updated: **40/40**.
- Documentation inventory: **40/40**, with **28 CURRENT / MAINTAINED** and **12 HISTORICAL EVIDENCE**.
- Release 45 source-tree regression: **221 passed / 8 skipped / 0 failed** (four bounded groups).
- Legacy selftest: **ALL PASS**. Compileall / launcher compile / shell syntax / operational CR scan: **PASS**.
- Ruff `0.16.7` actual execution: **NOT_RUN** (`ruff` executable unavailable); no substitute scan is promoted to PASS.
- Delivery target: `netconfig-2.0.0-45-operator-ux-simplification-v16.zip`; Release/RPM source identity is `2.0.0-45` because shipped Web Console/runtime source changed.

## Qualification interpretation

- **Release 43 Git checkout / Git bundle:** `218 passed / 7 skipped / 0 failed`; Git metadata exists, so the Git-index executable-mode regression executes and 12/12 required paths verify as `100755`.
- **Release 45 archive/full-source surface:** `221 passed / 8 skipped / 0 failed`; the extra archive-only skip is `test_required_git_index_executables_are_100755` because `.git` is intentionally absent.
- **Archive executable modes:** the ZIP records 12/12 required paths as `0755`; qualification extraction uses a POSIX mode-preserving extractor (`unzip`). Python `zipfile.extractall()` on this runner did not restore UNIX executable bits and is not used as mode-preservation evidence.
- **Ruff 0.16.7:** `NOT_RUN`. Pinning/configuration and source-side rule-family cleanup are not substitutes for executing Ruff.
- **mypy:** `NOT_RUN` on the isolated runner.
- **Q-1 live qualification:** PostgreSQL, backup/restore, OpenSSH/Net-SNMP, vendor/device interoperability, scale/calibration, and AlmaLinux RPM install/systemd remain deferred unless explicitly measured.
- **Release 45 offline helper RPM:** reproducibly emitted twice with SHA-256 `91cfea8b74a4c9b65472bafd59852513bf30a1adb9d87f5c6be3023e4a246efd` and independently verified offline; canonical AlmaLinux `rpmbuild`/DNF/systemd/SELinux production qualification remains `NOT_RUN`.

## Status vocabulary

Only `PLANNED`, `IMPLEMENTED_TESTING_DEFERRED`, `TESTED`, and `RELEASED` are valid current roadmap states. Documentation or source implementation alone never promotes a feature to `TESTED` or `RELEASED`.
### Release 45 final artifact gate

Mode-preserving `unzip` qualification of the Release 45 `v16` delivery surface: ZIP CRC **PASS**; source-to-extracted byte identity **190/190 PASS**; Markdown truth markers/inventory **40/40 PASS**; required executable modes **12/12 = 0755** in both ZIP metadata and extracted files; path traversal **0**; symlinks **0**; cache/pyc/pytest-cache entries **0**; operational CR offenders **0**; `source-manifest.sha256` **PASS**; `SHA256SUMS` **PASS**. Extracted repository regression executed in four bounded groups totals **221 passed / 8 skipped / 0 failed**; extracted legacy selftest is **ALL PASS**; extracted compileall and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` remains **NOT_RUN** because the executable is unavailable.

Delivery artifact: `netconfig-2.0.0-45-operator-ux-simplification-v16.zip`. Status remains `IMPLEMENTED_TESTING_DEFERRED`.


## 2026-09-22 — UI/CSS regression review

A fresh console review found and corrected cross-cutting presentation regressions introduced by the CSS/theme consolidation: a second `hidden`/`display:none` conflict on the dashboard no-results message; stale custom properties (`--txt`, `--bad`, `--brass`, `--brass2`, `--muted`); checkbox/radio controls inheriting the global 100% input width; dynamic graph markup bypassing theme classes; narrow-screen header wrapping; narrow-screen table overflow; and long Help inline-code overflow. The strict-CSP renderer still converts server-side `style=` attributes into nonce-authorized generated classes, and representative rendered pages were checked to contain zero residual inline-style attributes after transformation. Browser rendering smoke checks at 1440px and 390px showed no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes; Network-device NetFlow remains visible while non-network NetFlow remains hidden.

Focused regression: `tests/test_css_regression_review.py`, `tests/test_ui1_web_console.py`, and `tests/test_platform_hardening_ph1.py` pass together. Full repository evidence must still preserve explicit live/integration skips and must not be promoted to `TESTED` or `RELEASED`.

Final review evidence: focused CSS/WebUI/CSP regression is **27 passed / 0 failed**. Bounded full repository regression totals **248 passed / 8 skipped / 0 failed**. The eight skips are the expected source-archive Git metadata check plus seven explicit live PostgreSQL/backup/protocol-service prerequisites. Representative rendered-page Chromium smoke at 1440px and 390px found no document-level horizontal overflow on Dashboard, Protocols, Settings, Help, or network/application Device Edit pages after the fixes. See `CSS_UI_REVIEW_2026-09-22.md`.
## Release 50 MC-2 documentation truth

MC-2 runtime, API, WebUI, data-model/retention, test evidence, and continuation state are synchronized across README/DEVELOPMENT/AI_HANDOFF/ROADMAP/API/TESTING/WEBGUI and `NETCONFIG_MONITORING_CORRELATION_SLICES.md`. Historical release evidence remains historical and does not override the canonical Release 50 `IMPLEMENTED_TESTING_DEFERRED` state.

## 2026-09-23 — R51-HF1 documentation truth

Historical R51-HF1 documentation checkpoint: the baseline was Release 51 / MC-3 (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`) with a pre-MC4 compatibility hotfix overlay and MC-4 was still `PLANNED`. Release 52 now supersedes that state. The hotfix repairs SNMPv3 AES-192/AES-256 key-extension semantics, same-process Vault unlock for topology discovery, inventory-complete topology nodes, non-authoritative FDB/MAC inferred paths, and interactive browser-local topology layout. No formal RPM or live-vendor qualification is claimed.



## R67 documentation status

Canonical documentation is synchronized to Release 67. `R67_RELEASE_CANDIDATE_QUALIFICATION.md` is the release-candidate gate contract. `RELEASE_MANIFEST.json` and `SBOM.spdx.json` are generated deterministically and checked for drift.
