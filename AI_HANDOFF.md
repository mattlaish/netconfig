# NetConfig AI Handover

## Six workflow repairs + operator presentation — 2026-10-24

User authorized all six findings from the preceding workflow audit, plus the
engineering-oriented incident/change page. Implemented in the canonical root
`C:\Users\mattlai\Projects\netconfig`; no Git operations, version change or build.

- `web_forms.py`: device form validates required fields, numeric ports, name
  collisions and collection override before rename/credential writes. Manual
  credentials fork unique SSH/SNMP vault entries from their separate old sources;
  blank passwords retain previous values. Saved mode ignores forged manual fields.
  Application-only isolation and System management remain covered. Error forms
  retain safe fields/original edit identity, never submitted passwords/community.
- Numeric Settings validation rejects malformed/out-of-range/non-finite values
  before publishing changes. Candidate settings do not mutate the live dict until
  storage succeeds. Mail/OAuth/History credential saves require a created/unlocked
  vault; errors are explicit/sanitized, with prior-secret compensation on failure.
  Database settings retain existing Core connection/setup checks.
- Cross-file vault/archive/inventory/settings changes are NOT one ACID operation.
  Device storage failures inspect actual rename/reference state, retain attached
  credentials and report uncertain/partial saves rather than promising rollback.
  Failed secret compensation explicitly requires administrator review.
- Collect/Poll SNMP return via 303 to the same device Configuration/SNMP tab (or
  fleet SNMP detail) with short-lived per-session result feedback; device facts
  show Last error. Unlock validates same-site `next`, preserves workflow IDs and
  reports success/wrong password. Header unlock link also carries safe context.
- Traffic uses separate complete `exporter_choices`, not the top-12 list. Choices
  merge current senders, saved DISTINCT exporters in the period, pending rows and
  selected zero-record sender. Independent lookup survives raw-query truncation;
  failure is visible/sanitized. Existing 200,000-row analysis bound is unchanged.
- `web_workflow_ux.py` + `web_ops.py`: role-aware next step/status/change-target
  summary, readable path/proposal/reviewed-intent tables, closed technical details,
  device suggestions, safer stale controls and inline unlock/return. Targets are
  NOT a complete impact assessment. Existing frozen proposal, approval, execution,
  verification/recovery authority and no-I/O rendering are unchanged.
- Validation: 204 related tests PASS (10 modules; 5 deliberately deselected:
  Windows POSIX-mode first-admin assertion and separate qualification-runner gates).
  Legacy selftest ALL PASS. Initial new-test failures were corrected harness
  assumptions (session replacement and header-vs-inline next links); final run green.
  Browser fake-data light/dark, summaries/details and real unlock/return verified.
  Final wording/anchor source follow-up rechecked: 204 PASS / 5 deselected in
  150.81 s. 98 runtime/selftest Python files plus new regressions compile in
  memory. Ruff: 0 new findings, 9 retained baseline findings in this checked set.
  No accidental private-key/access-token signatures or temporary source files
  found in the checked changes. Temporary browser preview is closed/stopped.
  Real PostgreSQL, live devices, AlmaLinux RPM upgrade/service and LIVE_RC NOT_RUN.
- Source metadata regenerated; package remains `2.0.0-67.2`, status
  `IMPLEMENTED_TESTING_DEFERRED`. Existing root RPM is stale and excludes both
  this work and the Oct 22 flow-history changes. No new artifact is claimed.
- Backups/proof: `C:\Users\mattlai\AppData\Local\Temp\netconfig-workflow-fix-00d7577cc87046118ad5398cc6ac1f65`.
- Next: user-selected RPM build/release identity and isolated AlmaLinux/PostgreSQL
  verification. Do not redo baseline analysis or create MC-12.

## NetFlow 24-hour PostgreSQL history — 2026-10-22

User explicitly requested database-backed NetFlow retention. This supersedes
earlier descriptions of NetFlow as memory-only; it does not merge the separate
October 7 sensor-history lineage or add MC-12. Package identity is unchanged.

- `netflow_history.py`: dedicated `netconfig_flow_history` PostgreSQL table;
  receive timestamp, exporter, IPv4/IPv6 endpoints, ports, protocol, packet/byte
  counters and retry-stable UUID. Indexes on time and exporter/time. Numeric
  counters preserve unsigned 64-bit values. Core DB/schema identity unchanged.
- `netflow_history_enabled` defaults true. Uses existing History PostgreSQL
  connection keys/legacy DSN and `__pg_history__` vault password independently
  of `if_history_enabled` and `if_history_hours`. No duplicated credentials.
  Settings → NetFlow exposes enable/status; restart to activate changes.
- UDP receive stays DB-free. One worker batches 500 rows with a 20,000-record
  volatile queue; timeout/retry and UUID conflict handling avoid double writes.
  Queue rejects, expired pending rows, pending/saved counts and sanitized
  read/write/maintenance errors appear in Traffic and device views. Recovery
  refreshes vault credentials; missing schema can be retried after a write error.
- Logical reads always exclude records older than 24 h. Worker cleanup runs even
  without incoming flows, normally every 60 s, deleting 10,000 expired rows per
  transaction and speeding retries during backlog. Physical deletion can lag;
  disk space is not a fixed quota or guaranteed immediate reclamation.
- Global Traffic and device Traffic prefer committed history plus pending rows
  deduplicated by UUID; they never add the memory ring to DB totals. DB read
  failure explicitly falls back to the ring. Restarted collectors can read old
  saved exporters even before new datagrams arrive. The displayed period is a
  query range, not a claim of uninterrupted collection.
- One analysis reads at most 200,000 newest saved rows, plus bounded pending;
  results are explicitly marked incomplete at that limit. Filter to a shorter
  period/exporter; older records remain stored until expiry. IP/service filtering
  runs after this bound. Raw display remains latest 100. No new rollup warehouse.
- Receive-time rate estimates, port-based service guesses, UDP/template loss and
  cross-exporter duplicate observations are unchanged. A hard stop/prolonged DB
  outage can lose queued flows; no disk spool or historical backfill is claimed.
  Graceful shutdown drains multiple batches within a short budget.
- Validation: **136 PASS / 1 SKIP** focused/related regressions, selftest ALL
  PASS, 93 Python files compile in memory. Ruff: 0 new findings; 8 pre-existing
  findings remain in the checked set. Real PostgreSQL/AlmaLinux qualification
  remains NOT_RUN; isolated SQLite SQL-bridge tests are not PostgreSQL evidence.
  An opt-in `tests/integration/test_netflow_history_postgres.py` gate uses
  `NETCONFIG_TEST_FLOW_PG_DSN` and an isolated temporary schema.
- Existing project-root RPM predates this change and does NOT include it. No
  new RPM/version/Git synchronization or production deployment is performed.
  Status remains `IMPLEMENTED_TESTING_DEFERRED`; source metadata regenerated.
  Proof/backups: `C:\Users\mattlai\AppData\Local\Temp\netconfig-flow24-21ca8b20d4aa41f99b7db186fdf6ee0d`.

## RPM installation build — 2026-10-22

At the user's explicit request, built the current canonical source into
`netconfig-2.0.0-67.2.el10.noarch.rpm` **without increasing the version**.
The user reports their installed version is older and explicitly wants
`dnf upgrade`; use that command for the delivered local package. If a future
host already has the same EVR installed, upgrade will not replace it and an
explicit reinstall would be required; no Epoch/version trick was introduced.

- Source: `C:\Users\mattlai\Projects\netconfig`, including the current Web UX,
  security-policy, NetFlow and operator-wording work. The separate October 7
  sensor-history-rollup ZIP was **not merged**; its missing-from-current-tree
  history changes remain unresolved and are not claimed to be in this RPM.
- Builder: existing dependency-free offline RPM tool, not Linux rpmbuild.
  Package identity remains `2.0.0-67.2.el10.noarch`; the source spec is unchanged.
- Output: project-root RPM, 519551 bytes, 113 payload entries.
  SHA-256: `ebe868756cf78b9ebecb6fd883849daf0ee27e21b31ff18cb9c720ce4dcded56`.
- Independent verifier PASS: package headers/digests, payload/source bytes,
  permissions, scriptlets, dependencies and config noreplace flags. Two builds
  with the same epoch `1792660193` are byte-identical. Launcher is LF-normalized
  and executable; existing data/vault contents are not shipped in the payload.
- Focused local regression: **109 PASS / 1 Windows-host-limited failure**.
  `test_first_admin_setup_with_one_time_code` stops at its POSIX 0600 assertion
  because Windows reports 0666; production code still creates/chmods 0600.
  No assertion was weakened, and this is not reported as a full-suite PASS.
  Legacy selftest: **ALL PASS**.
- RPM is unsigned. AlmaLinux RPM/DNF install-upgrade, systemd/SELinux, live
  PostgreSQL/devices and LIVE_RC gates are **NOT_RUN**, not inferred from offline
  verification. Status stays `IMPLEMENTED_TESTING_DEFERRED`.
- Source release metadata/SBOM is regenerated for the handover change; this is
  not candidate freeze or production-release promotion. No Git operations.
- External build/rebuild proof:
  `C:\Users\mattlai\AppData\Local\Temp\netconfig-rpm-install-20261022-92f9e3e97e404cbd875a8727aa21777b\build-result.json`.

## Console usability round — 2026-10-18

Source-only UX work; no schema or network-write authority change. Status stays
`IMPLEMENTED_TESTING_DEFERRED`.

- `web_ux.py` (`WebUxMixin`, first in `Console` bases) now owns `_page`, `_nav`,
  `_topright`, `_login_page`, `_dashboard` (Devices home), `_device_form`,
  `_audit_page`, `_runs_page`, plus `/search`, `/device-import`, `/device-test`
  and `/setup-admin`. Keep web.py under the PH-1 gate by adding new screens there.
- Shared client behavior is in `UX_JS` (sortable/filterable tables, tabs, phone
  menu, device-form credential modes, connection test); everything is nonce'd,
  with no inline handlers or style attributes added.
- Dashboard (`web_mc9._network_glance`) is network-first; correlation sections
  render only when non-empty; engine health sits in a closed `<details>`.
- `Manager.test_device_connection()` is the only new device I/O and runs only on
  an explicit approver/admin request; it stores nothing besides normal SSH
  host-key pinning.
- First-admin setup code: `web_ux.ensure_setup_code()` (log + 0600 file, 24 h).
- Next: unchanged — choose release identity, freeze a candidate, run the twelve
  LIVE_RC gates.

## Security policy fixes and NetFlow traffic analytics — 2026-10-17

Source-only corrective on top of the operator-wording refresh; no schema, route
removal or network-write authority change. Status stays `IMPLEMENTED_TESTING_DEFERRED`.

- API protocol-profile writes need approver/admin; `debug:create`/`debug:admin`
  scopes need admin and over-role scopes are dropped at token verification;
  console/CLI passwords need 12+ characters (`users.validate_password`).
- NetFlow: v9 IPv6 decoding; `netflow.analyze_traffic()` (direction-aware,
  port-based services, 5-tuple sessions, interval-aligned avg/peak);
  `netflow_max_flows` default 10000; optional `netflow_resolve_names`
  background reverse-DNS cache (`netflow.REVERSE_DNS`).
- UI: `/traffic` and the device NetFlow section render through
  `web_traffic.py` (Sources/Destinations/Services/Conversations/Exporters,
  drill-down, throughput chart). Keep bars as SVG geometry (CSP forbids style
  attributes) and keep host names escaped.
- Next: unchanged — choose release identity, freeze a candidate, run the twelve
  LIVE_RC gates. IPFIX decoding remains unassigned future scope.

## Operator-facing wording refresh — 2026-10-17

The English console now uses task-oriented labels and instructions rather than
internal release/slice codes and implementation wording. Coverage includes
Dashboard, alerts/events, SNMP/MIB, service dependencies, integrations, database
and monitoring settings, diagnostics/traces, and Operations/change workflows.
Only display strings and generated human-readable workflow summaries change;
routes, form names/values, settings keys, DB schema, machine-readable API fields,
role/CSRF checks, approval and device-I/O behavior are unchanged. Raw diagnostic
records, protocol identifiers and developer/historical documents retain their
precise technical terms. This is not a global replacement of stored/user data.

Validation: **119 PASS** (including **18 new console-copy page checks**); legacy
selftest **ALL PASS**; **14 changed/new Python files compile**; **10 runtime
modules retain identical non-text AST and machine-facing fields**. Ruff adds
**0 new findings**; 10 existing findings remain. Three qualification/platform
cases were deliberately deselected, not counted as PASS. No Git operations,
RPM build/install, browser visual acceptance or LIVE_RC execution were performed.

Release identity stays `2.0.0-67.2`, state `IMPLEMENTED_TESTING_DEFERRED`. The
current source bytes changed: earlier candidate hashes/manifests/SBOM do not
qualify this update. Regenerate them at the next user-approved candidate freeze
and run the required LIVE_RC gates; no new feature phase or release is declared.

Work only in `C:\Users\mattlai\Projects\netconfig`. Current continuation
is candidate identity/freeze and qualification, not another feature slice.
Preserve the prior Web-control and workspace corrections below. One existing
documentation regression assumed the R67.2 heading was the second line; it
now checks the maintained canonical declaration instead of document order,
retaining release, deferred-status and session-security assertions.
Original affected files and generated patch/validation evidence are under
`C:\Users\mattlai\AppData\Local\Temp\netconfig-ui-wording-20261017-2d3h11po`.

## Workspace reconciliation — 2026-10-16 (current entry point)

Work only in `C:\Users\mattlai\Projects\netconfig`. The old chat/App launch cwd
`C:\Users\mattlai\Documents\ChatGPT\dev project` was never switched when the user
selected this root on 2026-08-18. Do not confuse launch cwd with the explicit source
workdir, or create another full source tree when approval is needed.

The first verified post-selection alternate-tree product edits occurred on
2026-10-15 in `netconfig-web-controls-20261015`. They were promoted to this root
on 2026-10-16. Before this reconciliation, all **468/468 non-cache staged files**
matched the canonical source; no missing staged changes were found. The redundant
tree is retired recoverably, not merged over current files. Earlier August edits
after the root selection targeted this canonical tree. Full chronology and
recovery locations: [workspace audit](WORKSPACE_AUDIT_2026-10-16.md).

Windows tests now use `tools/run_windows_source_tests.py`, anchored to its owning
tree even when invoked from another cwd. Optional pytest dependencies are supplied
with `NETCONFIG_TEST_DEPENDENCIES`, not a hardcoded old workspace import path.
The POSIX PTY guard fails closed; Windows results do not qualify real SSH/Linux.

Preserve the five Web UI corrective features and their recorded validation below.
Next product action remains release identity, candidate freeze/metadata regeneration,
then the twelve mandatory LIVE_RC gates, not a new feature slice or a rollback to
historical baseline ZIPs. This reconciliation changes developer tooling/docs only;
it does not declare a new release, rebuild an RPM or run live qualification.
No Git operations. The App's shared-project binding is still old; current tools
cannot change that source-folder association, and other chats must not be repointed.

Reconciliation validation: **51 PASS** (3 new runner + 45 Web controls + 3 existing
source/structure checks); legacy selftest **ALL PASS**; runner/test compile **2/2**
and focused Ruff **PASS**. Rechecked 468 original file hashes: **0 unexpected
changes**; product runtime unchanged. Initial shared-Temp setup errors were
resolved using a new unique test directory, not a product fix. Recovery paths and
limitations are recorded in the audit. Evidence: 2026-10-16 09:43:43 UTC+8 (Taiwan).

## Web UI control coverage corrective — 2026-10-16

The R67.2-based working tree now closes five console coverage gaps. Status remains `IMPLEMENTED_TESTING_DEFERRED`; package identity remains `2.0.0-67.2` pending the user's release decision.

- **Users:** admins can enable, disable and delete accounts from `/users`. Console changes protect the current account and the last enabled admin; SQLite transactions and a PostgreSQL transaction advisory lock serialize access changes. Existing managed sessions reject deleted/disabled accounts on their next request. Password-reset inputs are masked.
- **Device Collection:** approvers/admins can remove a saved protocol profile; inventory and vault secrets are retained and default collection is restored. Operators and above can explicitly run Capabilities, Read state and bounded gNMI Subscribe once. Collection now checks the existing `collect` capability. Page loads do not initiate protocol I/O.
- **Diagnostics:** admins can create full or per-device captures, request a signature, verify archive signature/trust, view effective signing status and clean up older managed bundles with a minimum keep count of one. Signature validity and trusted-signer status are displayed separately. Device captures create their missing security subdirectory; cleanup uses file modification time across full/device archive prefixes.
- **Settings → Evidence signing:** admin-only policy controls for `evidence_signing_required` and `evidence_trusted_fingerprints`; validated/normalized SHA-256 pins are saved only after all inputs pass. Environment policy overrides remain visible and environment-added pins are not copied into settings. Private keys remain outside the Web UI.
- **Protocol Traces:** standalone `/traces` navigation, device/status filters, session detail and bounded event view. Operators and above can start/stop captures with TTL/event/byte budgets and optional Incident linkage. Viewers can read but cannot capture.

All new console POST routes use session authentication, existing role checks and CSRF protection. Network configuration writes remain behind the existing approval chain; no schema or public bearer-REST contract changes are introduced. `web_feature_controls.py` holds the additional controls and preserves the PH-1 `web.py` structural limits.

Console routes added: `POST /user-access`, `/protocol-delete`, `/protocol-inspect`, `/debug-verify`, `/debug-cleanup`, `/trace-start`, `/trace-stop`; `GET /traces` lists/details existing trace sessions. Existing `POST /debug-create` now accepts `mode=full|device`, `device` and optional `require_signature=1`. Existing `POST /settings-save` accepts `section=evidence`. These remain browser-session routes, not new bearer-token API endpoints.

Validation on the Windows development host: **131 PASS** across **45 new HTTP/role/CSRF/access-lifecycle cases** and **86 related existing regressions**. Three pre-existing POSIX/qualification-runner cases were reproduced against the unmodified working folder and excluded from this compatible run; they require the appropriate runtime. Ten existing OpenSSL signing cases were skipped in the earlier expanded run because OpenSSL was not exposed to that runner. The Windows test harness supplies only a fail-closed `pty` import shim; any real POSIX SSH attempt raises rather than simulating success. This is source/local HTTP evidence, not live AlmaLinux, PostgreSQL concurrency, device interoperability, browser acceptance or cryptographic-signing qualification.

Generated manifests, SBOM and artifact hashes remain pending regeneration for the next frozen candidate. Earlier candidate fingerprints do not qualify these changed bytes. No new version, MC slice or production release is declared. Git remains user-managed.

Additional completed local checks: legacy selftest **ALL PASS** (including Application-only isolation and System-only regression), six changed runtime modules compile, and the existing canonical-state, compound-statement and PH-1 structure checks **3/3 PASS**. Selftest uses the same fail-closed Windows PTY import harness; this is not live SSH evidence.

Active continuation: finish candidate identity/freeze and execute required LIVE_RC gates. The 2026-10-13 documentation-only pass below is historical; this corrective includes runtime and regression-test changes. Do not infer that the entire CLI/settings surface has been re-audited from closure of these five reported gaps.

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Active continuation — 2026-10-13

Continue from the current working tree on R67.2 plus the 2026-09-29 Vendor Profile framework and 2026-10-09 Web UI/NetFlow corrective. No new version has been selected. Do not reuse the old candidate fingerprint or manufacture a live PASS. Resolve release identity, freeze the candidate and execute the twelve LIVE_RC gates before R68 review. No new feature-development phase is assigned; MC-11 is final.

Current source has `/snmp` profile administration, indexed host lookup, bulk topology facts joins, exporter/template diagnostics and Application-only isolation. Preserve System/Network/mixed-type management behavior. Session idle/absolute expiry is already implemented in `web_security_runtime.py` (30 minutes / 12 hours); older deferred-expiry notes are historical. IPFIX decoding, SNMPv3 traps/INFORM, NETCONF base:1.1-only framing and Site Edge/Collector are unassigned future scope.

This handover pass changes Markdown only. It does not rerun full product tests or live gates. Historical 556/542/14 source-test counts belong to the September Vendor Profile checkpoint; the October ledger records nine new focused tests and reports a green suite without an exact new aggregate. Do not combine or invent totals. Any changed packaged Markdown also changes artifact bytes and requires metadata/artifact regeneration before qualification.

Git synchronization and history remain user-managed. Do not run Git commands without explicit current-chat authorization. Completion feedback after a documentation-stage update must end with Taiwan time (UTC+8).

## Web UI feature-coverage & NetFlow usability corrective — 2026-10-09

Corrective maintenance on top of the SNMP Vendor Profile working tree; no schema or public REST contract change, no new network-write authority, release/package identity intentionally not advanced. Status stays `IMPLEMENTED_TESTING_DEFERRED`.

- Re-applied two hot-path performance fixes a prior ZIP rebuild had reverted: `Inventory.get_by_host()` backs `Manager.device_by_host()` (no per-packet full scan on syslog/trap ingestion), and `Manager._inventory_with_sysname()` replaces the topology N+1 with a single bulk `all_facts()` join.
- Closed the SNMP vendor-profile **web** gap: the `/snmp` page now lists loaded profiles and lets `manage_devices` operators upload/validate, reload, and remove operator-installed profiles (built-in profiles read-only), mirroring the MIB library. Renderer lives in `web_ui.py` so web.py stays under the PH-1 structural-split gate.
- Made received NetFlow meaningful on the device page: `render_netflow_section` now distinguishes exporter-IP mismatch (lists real exporters, points to `/traffic`), datagrams-without-decoded-flows (awaiting v9 template / IPFIX not decoded), and nothing-received, instead of a blanket "no flows" note. The global `/traffic` page already aggregated across exporters.
- Added `tests/test_vendor_profile_web_admin.py` and `tests/test_netflow_device_diagnostics.py`; regenerated SBOM/RELEASE_MANIFEST; full suite green; no new ruff findings.

## Recorded engineering checkpoint — 2026-09-29

The active working tree is an **unnumbered corrective development update on top of the refrozen R67.2 source line**, implementing the data-driven SNMP Vendor Profile framework. Project roadmap state remains `IMPLEMENTED_TESTING_DEFERRED`. The release/package identity has intentionally not been advanced; do not invent R67.3/R67.2.x or promote R68 without the user's explicit decision.

**Recorded 2026-09-29 vendor-profile source evidence:** **556 collected / 542 PASS / 14 SKIP / 0 FAIL** across 12 bounded groups; focused Vendor Profile framework coverage is **8 PASS / 0 FAIL**; `compileall`, actual launcher `py_compile`, packaging/tool/qualification shell syntax, release-metadata check, and legacy selftest are PASS. The 14 skips remain explicit live PostgreSQL/protocol-service prerequisites plus the expected source-archive Git-metadata prerequisite. These are local/source gates only and do not promote the working tree beyond `IMPLEMENTED_TESTING_DEFERRED`.

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

## 2026-10-13 documentation validation result

Markdown inventory/applicability: **67/67 PASS** (54 maintained, 13 historical). Canonical-state consistency: **PASS**, executing the existing `test_release_67_rc_canonical_truth_is_consistent` assertion function directly. The pytest runner was **NOT_RUN** because the installed Python has no pytest module; direct assertion execution is not reported as a pytest-suite result. Local Markdown links and fenced-code balance pass the documentation audit. All **399 non-Markdown files** checked before/after synchronization are byte-unchanged. No Git operations, full product regression, RPM build or LIVE_RC gates were executed. Original Markdown is recoverable from the external temporary backup created for this sync.
