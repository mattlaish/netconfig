# R67.2 development update — Data-Driven SNMP Vendor Profiles

## Operator-facing wording refresh — 2026-10-17

SNMP pages now describe profiles as device matching plus collected monitoring
measurements, rather than canonical Sensors or bounded branches. MIB object
names, sysObjectID/OIDs, JSON profile format, limits and collection behavior
are unchanged. Profile absence or missing data still does not imply health.

Validation: **119 PASS** (including **18 new console-copy page checks**); legacy
selftest **ALL PASS**; **14 changed/new Python files compile**; **10 runtime
modules retain identical non-text AST and machine-facing fields**. Ruff adds
**0 new findings**; 10 existing findings remain. Three qualification/platform
cases were deliberately deselected, not counted as PASS. No Git operations,
RPM build/install, browser visual acceptance or LIVE_RC execution were performed.

## Web UI control coverage corrective — 2026-10-16

The R67.2-based working tree now closes five console coverage gaps. Status remains `IMPLEMENTED_TESTING_DEFERRED`; package identity remains `2.0.0-67.2` pending the user's release decision.

- **Users:** admins can enable, disable and delete accounts from `/users`. Console changes protect the current account and the last enabled admin; SQLite transactions and a PostgreSQL transaction advisory lock serialize access changes. Existing managed sessions reject deleted/disabled accounts on their next request. Password-reset inputs are masked.
- **Device Collection:** approvers/admins can remove a saved protocol profile; inventory and vault secrets are retained and default collection is restored. Operators and above can explicitly run Capabilities, Read state and bounded gNMI Subscribe once. Collection now checks the existing `collect` capability. Page loads do not initiate protocol I/O.
- **Diagnostics:** admins can create full or per-device captures, request a signature, verify archive signature/trust, view effective signing status and clean up older managed bundles with a minimum keep count of one. Signature validity and trusted-signer status are displayed separately. Device captures create their missing security subdirectory; cleanup uses file modification time across full/device archive prefixes.
- **Settings → Evidence signing:** admin-only policy controls for `evidence_signing_required` and `evidence_trusted_fingerprints`; validated/normalized SHA-256 pins are saved only after all inputs pass. Environment policy overrides remain visible and environment-added pins are not copied into settings. Private keys remain outside the Web UI.
- **Protocol Traces:** standalone `/traces` navigation, device/status filters, session detail and bounded event view. Operators and above can start/stop captures with TTL/event/byte budgets and optional Incident linkage. Viewers can read but cannot capture.

All new console POST routes use session authentication, existing role checks and CSRF protection. Network configuration writes remain behind the existing approval chain; no schema or public bearer-REST contract changes are introduced. `web_feature_controls.py` holds the additional controls and preserves the PH-1 `web.py` structural limits.

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## October Web administration follow-through — 2026-10-13 sync

The 2026-10-09 corrective closes the CLI-only management gap: `/snmp` lists loaded profiles and errors and supports JSON upload/validate, registry reload and runtime-profile removal for `manage_devices` operators. Routes `/vendor-profile-upload`, `/vendor-profile-reload` and `/vendor-profile-delete` require CSRF. Built-in profiles remain read-only. The renderer is in `web_ui.py`; telemetry still consumes persisted canonical Sensors.

Focused test files are `tests/test_vendor_profile_web_admin.py` (five tests) and `tests/test_netflow_device_diagnostics.py` (four tests). The October ledger's full-suite/ruff report is historical recorded evidence, not a rerun in this documentation pass. Live vendor and browser qualification remains required against a new frozen candidate. FortiGate firewall-policy and HA branches remain outside this profile's declared scope.

**State:** `IMPLEMENTED_TESTING_DEFERRED`  
**Release identity:** intentionally pending an explicit user decision  
**Schema revision:** `mc11-topology-change-planning-1` (unchanged)  
**Network-write authority:** unchanged; profiles are read-only SNMP collection metadata

## Why this corrective engineering exists

The refrozen R67.2 generic vendor collector chose uploaded-MIB roots and then applied a fixed per-root value cap. Live FortiGate observation showed that the device exposes substantially more useful operational telemetry than the generic first-root quota makes visible: system CPU/memory/sessions, security database versions, hardware sensors, processor rows, VDOM rows, interface/VLAN extensions, and VPN tunnel state/counters. Increasing one generic global limit would make vendor walks less predictable and would not provide semantic normalization.

This update replaces that behavior **only when a validated matching vendor profile exists**. Devices without a matching profile keep the previous bounded generic-MIB collector.

## Profile loading and precedence

Profiles are JSON and are loaded in low-to-high precedence order:

1. `/usr/share/netconfig/snmp-profiles` — packaged defaults.
2. `/etc/netconfig/snmp-profiles` — administrator overrides.
3. `$NETCONFIG_HOME/snmp-profiles` — locally imported/runtime profiles.
4. Optional colon-separated directories from `NETCONFIG_SNMP_PROFILE_PATH`.

A later valid profile with the same profile id replaces an earlier one. `netconfig snmp profile-reload` refreshes the registry without rebuilding the RPM.

## Fail-closed profile boundary

The profile schema permits only declarative identity, bounded collection roots, scalar metric mappings, table-column mappings, unit/enum/status mappings, messages, and limits. Validation rejects executable/action-shaped fields including Python, shell, commands, scripts, URLs, expressions, eval/exec, and subprocess fields. Numeric OID roots must stay within the declared `sysObjectID` identity prefix, collection counts and per-root values are bounded, and invalid files are reported but not activated.

A MIB file and a Vendor Profile have separate roles:

- **MIB:** OID dictionary/reference metadata.
- **Vendor Profile:** which bounded read-only OID branches NetConfig should collect and how persisted values map to canonical operational Sensors.

Uploading a MIB does not authorize polling every `OBJECT-TYPE` in that MIB.

## First packaged profile: Fortinet FortiGate

`fortinet.fortigate` matches `1.3.6.1.4.1.12356.101*` and currently collects only these bounded branches:

- system: `1.3.6.1.4.1.12356.101.4.1`
- security database versions: `...101.4.2`
- hardware sensors: `...101.4.3`
- processor telemetry: `...101.4.4`
- VDOM telemetry: `...101.3`
- interface/VLAN extensions: `...101.7.2`
- VPN telemetry: `...101.12`

The profile intentionally does **not** collect firewall policy statistics (`...101.5`) or HA (`...101.13`) for the current deployment scope.

Current semantic normalization includes firmware, aggregate CPU, memory, active sessions/session rate, AV/IPS database versions, hardware sensor reading/alarm state, per-processor CPU, VDOM CPU/memory/session counts, VPN up-count, and individual IPsec tunnel status/details. Interface/VLAN extension rows are collected and retained as profile-owned raw evidence; they can be promoted through the same declarative table mapper when an operator-facing canonical Sensor contract is selected.

No ad-hoc threshold is invented for CPU, memory, temperature, or session values. Hardware alarm state uses the device-provided alarm field; VPN status uses the documented FortiGate up/down enum.

## Runtime flow

```text
SNMP system poll -> sysObjectID
                  |
                  v
          Vendor Profile registry
             /             \
      matching profile      no profile
          |                    |
  bounded profile roots   legacy bounded MIB roots
          |                    |
          +--------> current mib_values snapshot
                           |
                           v
               declarative normalization
                           |
                           v
                   canonical Sensors
                           |
                           v
                Web/API read-only views
```

The existing `mib_values` storage remains a current snapshot, not an append-only history. No database migration is required.

## Operator / CLI surfaces

- `netconfig snmp profiles` lists loaded profiles and validation errors.
- `netconfig snmp profile-validate FILE.json` validates a profile without installing it.
- `netconfig snmp profile-reload` reloads configured profile directories.
- `netconfig snmp profile-install FILE.json` validates and atomically installs a runtime override under `$NETCONFIG_HOME/snmp-profiles/<profile-id>.json` without rebuilding the RPM.
- `netconfig snmp profile-remove PROFILE_ID` removes only the runtime override and reloads the registry so packaged/admin lower layers can take effect again.
- Device SNMP pages render a generic **Vendor profile telemetry** section from canonical Sensors and keep raw vendor OIDs under the existing Advanced vendor-MIB panel.
- Rendering profile telemetry does not initiate SNMP/device I/O.

## Packaging

The RPM installs packaged JSON profiles under `/usr/share/netconfig/snmp-profiles`. `/etc/netconfig/snmp-profiles` and `$NETCONFIG_HOME/snmp-profiles` are runtime override locations and are not populated with executable content.

## Qualification truth

**Recorded 2026-09-29 vendor-profile source evidence:** **556 collected / 542 PASS / 14 SKIP / 0 FAIL** across 12 bounded groups; focused Vendor Profile framework coverage is **8 PASS / 0 FAIL**; `compileall`, actual launcher `py_compile`, packaging/tool/qualification shell syntax, release-metadata check, and legacy selftest are PASS. The 14 skips remain explicit live PostgreSQL/protocol-service prerequisites plus the expected source-archive Git-metadata prerequisite. These are local/source gates only and do not promote the working tree beyond `IMPLEMENTED_TESTING_DEFERRED`.

Source qualification for this development update uses bounded pytest groups, focused profile/security/UI/package tests, `compileall`, shell syntax checks, deterministic helper-RPM rebuilds, clean-extract verification, and artifact-integrity checks. Live FortiGate evidence supplied by the operator established the collection need, but the current automated qualification environment does not itself perform the live FortiGate poll; that remains live-device evidence, not a simulated PASS.

Because runtime/package bytes changed after the refrozen R67.2 candidate, the old exact-candidate fingerprint and its candidate-bound `LIVE_RC` results cannot be reused for this working tree.
