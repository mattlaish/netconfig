# Development Ledger

## 2026-08-31 — engineering/security/remediation hardening slice

### Implemented

- Added `pyproject.toml` with Python 3.12+ contract, pytest, Ruff, and mypy configuration.
- Added GitHub Actions CI for lint, incremental typing, compileall, pytest, legacy self-test, PostgreSQL, scripted real-OpenSSH integration, and Net-SNMP integration.
- Added focused pytest modules for config remediation modeling, login throttling/security headers, service credentials, SNMP worker concurrency, protocol capabilities, and legacy-regression execution.
- Added `security.py` with process-local bounded login throttling and console security headers.
- Added `observability.py` with structured JSON events and Prometheus text metrics.
- Added `/healthz`, `/readyz`, and `/metrics`; restored HTTP access observability instead of suppressing `log_message`.
- Added failed-login and throttled-login audit events. Successful login/logout now include peer-source audit context.
- Added optional built-in TLS through stdlib `ssl.SSLContext`; CLI accepts `--tls-cert` and `--tls-key`.
- Added service vault bootstrap from systemd credential directory or root-only master file; legacy `NETCONFIG_MASTER` remains fallback compatibility only.
- Replaced service-start recursive root `chown` with systemd `StateDirectory=netconfig`; enabled `MemoryDenyWriteExecute=true` in the packaged web unit.
- Added `configmodel.py` and changed remediation from baseline text replay to fresh-live semantic planning, vendor negation, guarded execution, post-change re-fetch, and semantic verification.
- Remediation now refuses scrubbed baselines and platforms without an implemented automatic rollback guard.
- Added bounded concurrent SNMP polling with metrics.
- Added a thin storage boundary and explicit protocol capability registry for future PostgreSQL-core / NETCONF / RESTCONF / gNMI work.
- Updated remediation approval preview to show the semantic plan from the latest stored current config; execution still re-plans from fresh live state.
- Fixed a duplicate username field in the login page.

### Intentional non-change

Console session expiry was **not** implemented in this slice. The current in-memory session remains valid until logout or process restart. This is explicitly documented as deferred security debt in `SECURITY.md` and `ROADMAP.md` for a later dedicated lifecycle change.

### Validation still required

- Run CI on Python 3.12 with Ruff and mypy installed.
- Run the OpenSSH/Net-SNMP/PostgreSQL integration tier in Linux CI.
- Validate Cisco IOS/ASA and Arista timed-reload interactions on real vendor/lab images.
- Validate JunOS `commit confirmed` behavior and prompt transitions on a real JunOS lab image.
- Validate `MemoryDenyWriteExecute=true` on the exact target distribution/package build.
- Confirm built-in TLS certificate/key permissions and reverse-proxy coexistence in deployment environments.

### Known limitations

- Enforced CSP still permits legacy inline script/style because `web.py` has inline event handlers. Strict nonce CSP is report-only until those are removed.
- The old `selftest.py` remains as a compatibility runner while cases are progressively migrated to pytest.
- The storage abstraction is intentionally thin; the core database is still SQLite/WAL.
- NETCONF/RESTCONF/gNMI are architecture capabilities, not implemented transports yet.

## 2026-09-01 — CI lint and line-ending hygiene follow-up

### Implemented

- Reconciled Ruff with the existing code style so the CI lint gate is actionable: `E702` (multiple statements separated by semicolons) is now an explicit temporary house-style exception instead of an always-failing gate.
- Removed confirmed unused imports and cleaned the identified `F541`, `B904`, and `E741` violations rather than suppressing those rule families.
- Added `.gitattributes` with LF enforcement for Python, shell, systemd units/timers, RPM specs, TOML/YAML, Markdown, and common repository text artifacts.
- Renormalized repository text files to LF. Local verification found zero CRLF/bare-CR UTF-8 text files after normalization.
- Added repository-hygiene pytest coverage and a CI index-EOL check so future CRLF regressions are visible.

### Validation

- `python -m compileall -q opt/netconfig/netconfig tests`: PASS.
- `pytest -q`: PASS (11 passed, 3 integration tests skipped because protocol services are not running locally before this follow-up's new hygiene tests were added; rerun after final packaging records the final count).
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: `RESULT: ALL PASS`.
- Local Ruff execution remains **NOT RUN** because Ruff is not installed in this sandbox and outbound PyPI access is unavailable. The GitHub Actions Ruff step remains the authoritative validation for the exact configured ruleset.

### Deferred security debt unchanged

- Console idle timeout / absolute session expiry remains deliberately deferred. No session-lifetime behavior was changed in this follow-up; see `SECURITY.md` and `ROADMAP.md`.

## 2026-09-02 — topology, event-driven collection, read-only API, scheduled digest slice

### Implemented

- Added `topology.py` with pure LLDP-MIB and CDP-detail parsers, inventory/SNMP-sysName correlation and explicit unmanaged-neighbour classification.
- SNMP network polling now persists LLDP topology; when LLDP returns no neighbours and SSH credentials are available, a read-only `show cdp neighbors detail` fallback is attempted.
- Added a dependency-free `/topology` SVG fleet map and neighbour table plus a manual fleet discovery action.
- Added `syslog_receiver.py`: bounded UDP queue, 8 KiB message cap, source-IP device correlation, common config-change event matching, per-device debounce, immediate archive trigger, persistent recent events and audit evidence. Default listener is non-privileged udp/5514.
- Added `apitokens.py` and additive `api_tokens` schema. Tokens are random bearer credentials, stored only as SHA-256 hashes, have an existing NetConfig role plus explicit read scopes, support CLI create/list/revoke, and are audited on API use.
- Added read-only API endpoints for inventory, topology, drift, latest compliance, latest digest and audit.
- Added `digest.py`: periodic compliance/drift sweep with persisted digest evidence and SMTP/O365 delivery through the existing mailer. Monitoring settings now expose syslog and digest scheduling.
- Added additive topology/syslog/digest database tables and focused pytest coverage.

### Validation

- `PYTHONPATH=opt/netconfig pytest -q`: **19 passed, 3 skipped** (the 3 existing protocol-service integration tests remain environment-gated).
- `PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py`: **RESULT: ALL PASS**.
- `python -m compileall`: PASS for changed modules and final tree.

### Deferred / not claimed

- No real-device LLDP/CDP lab run was performed in this environment.
- No production syslog relay/NAT design is claimed; source-IP matching assumes the UDP peer is the managed device. Trusted-relay parsing must be explicit before supporting relayed syslog.
- SNMP traps are not implemented in this slice.
- Session idle/absolute expiry remains deliberately deferred security debt and was not changed.
