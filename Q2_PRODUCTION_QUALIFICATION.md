## Progression note — R60 selected

The operator confirmed that Q2 live execution had been performed and was usable, and explicitly selected R60 as the next roadmap stage. This source tree preserves that decision without inventing missing per-gate Q2 live results. Q2 remains historical qualification evidence for R59; new lifecycle evidence belongs to R60.

## Q2 qualification-harness artifact closeout

The complete Q2 qualification-tooling source tree and clean system-unzip extract both pass **394 collected / 386 passed / 8 skipped / 0 failed**. Q2 focused harness coverage is **14/14 PASS**; MC-11 focused authority coverage is **12/12 PASS**. `compileall`, launcher/Q2 `py_compile`, shell syntax and legacy selftest are PASS. Clean-extract helper RPM rebuilds are byte-identical to each other and to the frozen R59 helper RPM, and the independent RPM verifier passes. Product runtime payload remains byte-identical to the frozen R59 runtime.

The Q2 harness source artifact remains qualification tooling over R59, not a new product release. Live production gates remain deferred according to the initial campaign matrix; project state remains `IMPLEMENTED_TESTING_DEFERRED`.

## Q2 local qualification closeout for this environment

The implemented Q2 harness was exercised on the current non-AlmaLinux runner. Repository regression after the Q2 tooling changes is **394 collected / 386 passed / 8 skipped / 0 failed**. Q2 focused harness tests are **14/14 PASS** and MC-11 focused authority tests are **12/12 PASS**. `compileall`, launcher/Q2 `py_compile`, packaging/tool shell syntax and legacy selftest are PASS. Product runtime payload is byte-identical to frozen R59, and two helper-RPM rebuilds remain byte-identical to the frozen R59 RPM (`af001a110e0d1eb6f3013f1608e1cf9159fecc2b590fccc2516738dc32a2d2a9`).

The first formal Q2 matrix selected 25 gates (the full-repository gate was recorded separately to avoid duplicating the bounded regression run): **3 LOCAL_REGRESSION PASS / 0 FAIL / 16 BLOCKED_ENVIRONMENT / 6 NOT_RUN / 0 LIVE_PRODUCTION PASS**. This is correct deferred truth for the current environment and does not promote the product. The evidence bundle is `netconfig-2.0.0-59-Q2-initial-qualification-evidence.zip`, SHA-256 `8feb30d7c57112321b21c0f6ad7ce712454a6a079712c11ebbedbd5cfc30181e`.

# Q2 Production Qualification Campaign

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current candidate applicability — 2026-10-13

The current working tree includes corrective runtime and documentation changes after the R67.2 freeze. The earlier exact-candidate fingerprint and its live evidence do not qualify these bytes. Current source/spec release remains `2.0.0-67.2`; selecting a new release identity is pending explicit user decision.

The next campaign requires a newly frozen artifact, regenerated/verified metadata and all twelve mandatory LIVE_RC gates against that fingerprint, followed by R68 review. Q1/Q2 and R60–R66 tools/contracts remain reusable within their declared release-specific boundaries; older gate outcomes do not transfer automatically. Fresh SQLite login and PostgreSQL bootstrap, supported upgrade preservation, real exporter/vendor behavior, browser device-type/profile administration and R64 managed-session behavior belong in applicable candidate acceptance.

Documentation synchronization establishes no new runtime/live PASS and does not promote `IMPLEMENTED_TESTING_DEFERRED`.

Status: **ACTIVE / HARNESS IMPLEMENTED / LIVE QUALIFICATION IN PROGRESS**  
Product baseline: **Release 59 / MC-11 (`2.0.0-59`)**  
Schema: **`mc11-topology-aware-change-planning-1`**  
Product state: **`IMPLEMENTED_TESTING_DEFERRED`**

Q2 is a production-qualification track over the frozen R59 product, not MC-12 and not a new product feature release. Product runtime/version identity remains `2.0.0-59` while qualification tooling and evidence evolve around it.

## Implemented campaign harness

`qualification/q2_runner.py` provides a repeatable, standard-library qualification runner and immutable-per-run evidence bundle. The gate catalog is machine-readable in `Q2_GATE_CATALOG.json`. `packaging/q2-qualify.sh` is the shell entry point and `packaging/q2-source-gates.sh` validates the qualification harness itself.

Every gate records exactly one of `PASS`, `FAIL`, `BLOCKED_ENVIRONMENT`, or `NOT_RUN`. Evidence is explicitly classified as `LOCAL_REGRESSION` or `LIVE_PRODUCTION`; local tests, SQLite, simulation, fake protocol services, or offline package inspection can never satisfy a live-production gate.

The runner automatically records only allow-listed host facts (OS ID/version, kernel, architecture, Python version, root boolean, selected tool availability, SELinux mode, systemd state). It intentionally excludes hostname, interface addresses, and the process environment. Gate stdout/stderr is bounded and redacted before inclusion. Environment-specific live hooks are selected by fixed filename from a hook directory; the runner exposes no arbitrary `--command`/shell-string execution parameter.

## Gate coverage

The initial Q2 catalog covers:

- R59 release/schema/authority baseline and full local regression.
- AlmaLinux 10 clean install, supported upgrade, rollback, systemd restart/reboot and SELinux enforcing operation.
- Real PostgreSQL migration, backup/restore, concurrency and advisory-lock behavior.
- Real SNMP, SSH, syslog, SNMP trap and NetFlow/IPFIX collection/ingestion.
- Real external-evidence connector behavior.
- Worker restart/recovery, clock skew, late/out-of-order evidence, duplicate/replay and retention.
- Representative API and WebUI latency.

PostgreSQL gates are directly wired to the existing service-backed integration tests and require explicit test-database credentials/environment. Environment-specific device/protocol/platform/performance gates use exact executable hook contracts so production evidence can be adapted to the qualification lab without adding arbitrary execution authority to NetConfig itself.

## Safety and authority boundary

Q2 never changes the MC-11 authority model. Path planning and candidate what-if remain analysis-only. The qualification runner does not submit or execute device configuration. Any Structured Change used by an end-to-end qualification scenario must still enter the existing Automation Request / Structured Change approval, snapshot revalidation, execution, verification, rollback and audit workflow.

Destructive qualification gates (install, upgrade, rollback, restart, reboot, worker restart) require both `--live` and `--allow-destructive`. Without explicit destructive authorization, they are `NOT_RUN`. Missing target OS, required tools/modules/credentials or gate hook is `BLOCKED_ENVIRONMENT`, not PASS.

## Evidence bundle

Each campaign run contains:

- `campaign.json` — complete machine-readable campaign summary and gate matrix.
- `SUMMARY.md` — human-readable summary.
- `gates/<gate-id>.json` — per-gate truth.
- `logs/<gate-id>.stdout.log` and `.stderr.log` — bounded/redacted command evidence where a gate executed.
- `SHA256SUMS` — integrity coverage for the bundle.

The runner never promotes the project to `TESTED` or `RELEASED`. Q2 evidence feeds later R60–R67 work and the separate R68 release decision.

## Recorded qualification environment

The current build runner is not an AlmaLinux 10 production-qualification appliance and does not provide the required live PostgreSQL/device/protocol/external-product targets. Therefore those gates must remain `BLOCKED_ENVIRONMENT` or `NOT_RUN` until executed on suitable infrastructure. Q2 harness/unit/local-regression PASS is not production qualification PASS.

## Historical execution target

Run the Q2 campaign on a designated disposable AlmaLinux 10 qualification appliance with the frozen R59 RPM/source artifact, a real PostgreSQL qualification database, controlled network devices/protocol emitters, external evidence test systems, and explicit restart/reboot recovery access. Preserve every raw evidence bundle and its SHA-256 sidecar; do not overwrite prior campaign evidence after a product or harness change.
