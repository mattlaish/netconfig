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
