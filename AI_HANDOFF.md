# NetConfig AI Handover

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.


## Current engineering state — 2026-09-29

The active working tree is an **unnumbered corrective development update on top of the refrozen R67.2 source line**, implementing the data-driven SNMP Vendor Profile framework. Project roadmap state remains `IMPLEMENTED_TESTING_DEFERRED`. The release/package identity has intentionally not been advanced; do not invent R67.3/R67.2.x or promote R68 without the user's explicit decision.

**Current vendor-profile source evidence:** **556 collected / 542 PASS / 14 SKIP / 0 FAIL** across 12 bounded groups; focused Vendor Profile framework coverage is **8 PASS / 0 FAIL**; `compileall`, actual launcher `py_compile`, packaging/tool/qualification shell syntax, release-metadata check, and legacy selftest are PASS. The 14 skips remain explicit live PostgreSQL/protocol-service prerequisites plus the expected source-archive Git-metadata prerequisite. These are local/source gates only and do not promote the working tree beyond `IMPLEMENTED_TESTING_DEFERRED`.

The prior refrozen exact R67.2 source ZIP had SHA-256 `b93084d7e2af9be4de234ceb6e21f147332a4e696970a0d829812de22a841559`. This working tree changes runtime/package bytes, so prior exact-candidate fingerprint `dd8524faf97f889992b5f84cfdb4eb47e2d6a8e4aa5be842f3f4b29022ccafda` and candidate-bound LIVE_RC evidence do not qualify the new bytes.

## SNMP Vendor Profile architecture

- `opt/netconfig/netconfig/vendor_profiles.py`: JSON-only profile validation, registry, matching, reload, bounded table/scalar normalization. No executable profile content is permitted.
- Search precedence: `/usr/share/netconfig/snmp-profiles` -> `/etc/netconfig/snmp-profiles` -> `$NETCONFIG_HOME/snmp-profiles` -> optional `NETCONFIG_SNMP_PROFILE_PATH` directories.
- `usr/share/netconfig/snmp-profiles/fortinet.fortigate.json`: first packaged profile. It collects bounded FortiGate system, security DB, hardware, processors, VDOM, interface extension and VPN branches. Firewall policy and HA branches are intentionally excluded.
- `manager.py::_poll_vendor_mibs()`: matching declarative profile wins; otherwise legacy bounded MIB-root behavior remains.
- Profile normalization writes canonical Sensors with source `vendor-profile:<id>/<mapping>` and prunes stale profile-owned resources.
- `web.py`: generic read-only Vendor profile telemetry panel from persisted Sensors; raw OIDs remain Advanced.
- `cli.py`: `snmp profiles`, `snmp profile-reload`, `snmp profile-validate`, `snmp profile-install`, `snmp profile-remove`.
- RPM spec/offline builder package default profiles under `/usr/share/netconfig/snmp-profiles`.

No DB schema change. No REST mutation surface. Existing `GET /api/v1/sensors` automatically exposes normalized vendor Sensors under existing auth/filter semantics. No change to the request -> approval -> frozen snapshot -> execution-time revalidation -> execute -> verify -> audit network-write chain.

## Roadmap truth

MC-11 remains the final Monitoring / Correlation / Change-Planning functional slice. Do not create MC-12. R68 remains a release-decision step only after a new exact candidate is frozen and all mandatory LIVE_RC gates are executed against those exact bytes.

## Qualification rules

Count only completed tests. Timeouts/partial output are not PASS. Local/offline fake/simulation evidence never substitutes for live device/PostgreSQL/AlmaLinux/HA gates. Keep `DEVELOPMENT.md`, `ROADMAP.md`, `TESTING.md`, `SECURITY.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`, `WEBGUI.md`, `README.md`, `DOCUMENTATION_STATUS.md`, this file, and the focused SNMP profile document synchronized whenever this work changes.
