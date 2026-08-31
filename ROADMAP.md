# Roadmap

Status vocabulary: `IMPLEMENTED`, `IMPLEMENTED_TESTING_DEFERRED`, `PLANNED`.

## Engineering foundation

- **IMPLEMENTED** Python project metadata in `pyproject.toml`, Python >=3.12 contract, Ruff configuration, incremental mypy gate, compileall gate, pytest suite, legacy self-test compatibility, and GitHub Actions CI.
- **IMPLEMENTED_TESTING_DEFERRED** protocol integration tier using a real OpenSSH daemon with a scripted fake network CLI, a real Net-SNMP agent, and PostgreSQL. The workflow is defined; local container/CI execution is environment-dependent.
- **PLANNED** continue migrating procedural `selftest.py` cases into focused pytest modules until the legacy runner can be retired.

## Console hardening

- **IMPLEMENTED** failed-login throttling and authentication audit events.
- **IMPLEMENTED** security headers and transitional CSP with strict nonce policy in report-only mode.
- **IMPLEMENTED** optional built-in TLS using `ssl.SSLContext`.
- **IMPLEMENTED** `/healthz`, `/readyz`, `/metrics`, and structured JSON event/access logging.
- **PLANNED / SECURITY DEBT** session idle timeout and absolute expiry. Explicitly deferred by current project direction; see `SECURITY.md`.
- **PLANNED** complete removal of inline event handlers/styles, then switch the enforced CSP to nonce-only scripts and no `unsafe-inline`.
- **PLANNED** finish decomposing the remaining `web.py` route/rendering monolith into route, response, template/static, and security packages. Cross-cutting security/observability code has already been extracted.

## Unattended operation

- **IMPLEMENTED** systemd credential-directory and root-only credential-file bootstrap for vault master material.
- **IMPLEMENTED** legacy environment bootstrap retained only for compatibility.
- **PLANNED** external KMS/HSM/secret-manager provider adapters if deployments require centralized rotation or attestation.

## Safe remediation

- **IMPLEMENTED** indentation-scoped semantic config model and JunOS `set` model.
- **IMPLEMENTED** add/change/remove planning with vendor negation (`no`, `undo`, `delete`).
- **IMPLEMENTED** fresh-state planning at execution time and post-change semantic verification.
- **IMPLEMENTED** automatic rollback guards for Cisco IOS/ASA, Arista EOS, and JunOS; unsupported platforms fail closed.
- **IMPLEMENTED** scrubbed-baseline remediation refusal.
- **IMPLEMENTED_TESTING_DEFERRED** real device validation of reload/commit-confirmed prompts and rollback behavior.
- **PLANNED** deeper vendor grammars for nested policy constructs where indentation alone is insufficient.

## Fleet scale and storage

- **IMPLEMENTED** bounded concurrent SNMP polling via `snmp_workers`.
- **IMPLEMENTED** SQLite WAL was already present and remains the local default.
- **IMPLEMENTED** thin storage capability boundary for future backend migration.
- **PLANNED** migrate core state, not only interface history, to PostgreSQL when multi-process/HA operation is required.
- **PLANNED** shared distributed job coordination before claiming active-active pollers.

## Protocol modernization

- **IMPLEMENTED** explicit protocol capability registry; CLI/OpenSSH is the current implemented fallback.
- **PLANNED** NETCONF adapter.
- **PLANNED** RESTCONF adapter.
- **PLANNED** gNMI adapter.
- **PLANNED** capability-based protocol selection per device, preserving CLI for legacy systems.
