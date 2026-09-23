# NetConfig Offline RPM Builder

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.
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


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

This tool emits a deterministic unsigned RPM using only the Python standard library. It exists for isolated runners that do not have `rpm`, `rpmbuild`, Docker/Podman, or outbound package access. It packages the same NetConfig runtime paths, permissions, config-file semantics, dependencies, and systemd lifecycle scriptlets defined by `packaging/netconfig.spec`.

Use it from the repository root:

```bash
./tools/rpm-builder/build.sh
./tools/rpm-builder/verify.sh ./dist/netconfig-2.0.0-48.el10.noarch.rpm
```

`SOURCE_DATE_EPOCH` controls deterministic timestamps. If unset, Release 43 uses `1789689600` (`2026-09-18T00:00:00Z`). Rebuilding the same source with the same epoch must produce the same SHA-256.

The verifier checks RPM lead/header structure, NEVRA, gzip/newc payload parsing, source-byte identity, file type/mode, `/etc/default/netconfig` `CONFIG|NOREPLACE`, required dependencies, and lifecycle scriptlets without invoking `rpm`.

## Qualification boundary

This helper does **not** replace the canonical AlmaLinux `rpmbuild` path. A helper-emitted RPM remains offline-structurally-qualified only until `rpm -qp`, `dnf install/upgrade`, systemd start/restart, reboot persistence, SELinux behavior, and the other Q-1 live gates execute on the target platform. Do not promote a helper-emitted artifact to `TESTED` or `RELEASED` from this tool alone.

## Release 42/43 qualification evidence (historical)

The candidate fresh-clone build was reproduced byte-for-byte twice. The resulting unsigned helper RPM SHA-256 was `095b32b594b771e37e83c2cc89a27e9f87d8c5ae925d81ad94510083f0e612a1`; `verify_rpm.py` passed header/payload digest verification, gzip/newc parsing, source-byte identity, modes, config flags, requirements, and scriptlets. This is offline evidence, not target-host qualification.

The builder excludes complete `__pycache__` subtrees. CI compiles Python before building the helper RPM so empty cache directories cannot silently enter the package.
