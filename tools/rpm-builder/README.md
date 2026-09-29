# NetConfig Offline RPM Builder

> **Canonical project state — 2026-09-24:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67 / R67 Release Candidate / Full Artifact Qualification** (`2.0.0-67`, `IMPLEMENTED_TESTING_DEFERRED`) on top of **R66 Observability / Supportability**. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67 is a **feature freeze** and adds release-candidate/full-artifact qualification, exact-candidate evidence binding, synchronized release metadata, and an SPDX 2.3 source SBOM; it adds no device-write, polling, approval-bypass, workflow, HA, security, or MC authority. **Local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. R67 cannot mark the product `RELEASED`. Do not create MC-12.** The next approved track is **R68 v2 Production Release Decision**, but R67 does not start or decide R68.
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
