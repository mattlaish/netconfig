# NetConfig Offline RPM Builder

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](../../ROADMAP.md) and [AI_HANDOFF.md](../../AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current packaging and qualification disposition — 2026-10-13

The source/spec identity remains `2.0.0-67.2`, with unnumbered runtime and documentation correctives after the prior freeze. Release numbering awaits the user's decision. Building these sources does not reproduce the earlier frozen R67.2 artifact or inherit its qualification. Old release-specific filenames/commands below are historical examples; verify the actual build output and RPM metadata for the candidate being installed.

Packaged JSON SNMP profiles reside under `/usr/share/netconfig/snmp-profiles`; administrator/runtime overlays use `/etc/netconfig/snmp-profiles` and `$NETCONFIG_HOME/snmp-profiles`. October console administration manages runtime profiles while preserving built-in defaults. Ordinary RPM installation remains SQLite-first; fresh Core PostgreSQL requires the documented psycopg 3/bootstrap workflow.

Before candidate qualification, regenerate applicable release/source manifests, SPDX SBOM and checksums, then verify the new artifact. Packaged Markdown changes affect payload bytes. This documentation pass leaves generated JSON/SHA artifacts untouched so earlier frozen evidence is not silently rewritten. Canonical AlmaLinux build/install/upgrade/systemd/SELinux and all other LIVE_RC gates require the exact new candidate; offline helper verification alone does not qualify deployment. Git remains user-managed.

## Release 48 — Sensor Model & Evidence Normalization

Release 48 promotes the sensor work from UI-only health cards into a reusable persisted normalization layer. `SensorEngine` stores `sensor_type`, `device`, `resource`, `value`, `unit`, `status`, `message`, `threshold`, `source`, and `updated_at`, with the status contract limited to `OK`, `WARNING`, `CRITICAL`, and `UNKNOWN`. It reads existing NetConfig persistence only and does **not** initiate SNMP/NETCONF/RESTCONF/gNMI/SSH device I/O or change polling frequency.

The generator now derives: device reachability/polling; endpoint FDB/MAC and ARP/IP-neighbor evidence; per-interface status, utilization, error and discard-evidence state; LLDP/CDP topology neighbor/managed/unmanaged counts; and a known semantic Loop Protection summary from mapped MIB values. Unknown raw MIB/OID values remain Advanced/troubleshooting data and do not become invented sensors. Missing ARP, topology, utilization, or discard evidence is represented as `UNKNOWN` with an empty value rather than as zero, `CRITICAL`, or fabricated data.

`GET /api/v1/sensors` is read-only and accepts `device`, `type`, `status`, and bounded `limit` filters. Access requires `analytics:read` or `inventory:read`. Release 48 does not add an Alert Engine, remediation, configuration mutation path, new approval orchestration, or distributed collector runtime.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.

## Release 46 — Operator Health Cards & UX Follow-through

Release 46 implements the operator feedback gathered after Release 45 without changing the NI-7 feature baseline. The user-facing **Desired State** label is now **Configuration Baselines / Templates & Drift**; the underlying desired-state API/data model is unchanged. Operations keeps Structured Changes, Campaigns, Automation Requests, Network Intelligence, telemetry, model packs, and HA/DR, but the default workspace is outcome-oriented and the more technical surfaces are grouped under Advanced operations.

Structured collection profiles are no longer an everyday top-level navigation item. They remain available as **Collection settings** from a device and are explicitly described as network-device read/collection settings for switches, routers, and firewalls. Existing approval behavior is retained as-is; Release 46 does not expand approval orchestration.

The SNMP device page now derives operator-facing health cards from **already-collected DB/cache evidence only**: reachability, polling, interface health, FDB/MAC evidence, ARP/IP-neighbor evidence, topology-neighbor evidence, Loop Protection when mapped MIB values exist, and vendor telemetry status. Opening the page does not trigger an extra poll or vendor walk. Raw SNMP/OID and vendor MIB rows remain available under Advanced/troubleshooting views. The MIB library itself is presented as supporting metadata, not as an operator feature.

The previously documented Central Controller + read-only Site Edge/Collector concept remains a **future architecture item only**. No distributed collector, local site-alert engine, store-and-forward transport, secondary WAN/LTE/SMS path, or distributed execution node is implemented in Release 46.

**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline builder emitted `netconfig-2.0.0-46.el10.noarch.rpm` twice byte-identically; independent verification passed and SHA-256 is `5b26c9ae73ac4248171196ee3637f51bd238fed090c4ce3fa820419842f510cd`. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-24:** **R59 / MC-11 is the final Monitoring & Correlation functional slice.** Do not create MC-12. After R59 use **Q2 Production Qualification Campaign → R60 Lifecycle → R61 Scale → R62 PostgreSQL → R63 HA → R64 Security → R65 Operator Workflow → R66 Supportability → R67 RC → R68 Production Release Decision**. Simulation never counts as live PASS; qualification states are `PASS / FAIL / BLOCKED_ENVIRONMENT / NOT_RUN`.

This tool emits a deterministic unsigned RPM using only the Python standard library. It exists for isolated runners that do not have `rpm`, `rpmbuild`, Docker/Podman, or outbound package access. It packages the same NetConfig runtime paths, permissions, config-file semantics, dependencies, and systemd lifecycle scriptlets defined by `packaging/netconfig.spec`.

Use it from the repository root:

```bash
./tools/rpm-builder/build.sh
./tools/rpm-builder/verify.sh ./dist/netconfig-2.0.0-57.el10.noarch.rpm
```

`SOURCE_DATE_EPOCH` controls deterministic timestamps. If unset, Release 43 uses `1789689600` (`2026-09-18T00:00:00Z`). Rebuilding the same source with the same epoch must produce the same SHA-256.

The verifier checks RPM lead/header structure, NEVRA, gzip/newc payload parsing, source-byte identity, file type/mode, `/etc/default/netconfig` `CONFIG|NOREPLACE`, required dependencies, and lifecycle scriptlets without invoking `rpm`.

## Qualification boundary

This helper does **not** replace the canonical AlmaLinux `rpmbuild` path. A helper-emitted RPM remains offline-structurally-qualified only until `rpm -qp`, `dnf install/upgrade`, systemd start/restart, reboot persistence, SELinux behavior, and the other Q-1 live gates execute on the target platform. Do not promote a helper-emitted artifact to `TESTED` or `RELEASED` from this tool alone.

## Release 42/43 qualification evidence (historical)

The candidate fresh-clone build was reproduced byte-for-byte twice. The resulting unsigned helper RPM SHA-256 was `095b32b594b771e37e83c2cc89a27e9f87d8c5ae925d81ad94510083f0e612a1`; `verify_rpm.py` passed header/payload digest verification, gzip/newc parsing, source-byte identity, modes, config flags, requirements, and scriptlets. This is offline evidence, not target-host qualification.

The builder excludes complete `__pycache__` subtrees. CI compiles Python before building the helper RPM so empty cache directories cannot silently enter the package.

## R63 identity

The offline deterministic helper builder now emits `netconfig-2.0.0-63.el10.noarch.rpm`. This builder is artifact/reproducibility evidence only and is not a substitute for AlmaLinux/rpmbuild or live HA qualification.
