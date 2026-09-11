# NetConfig Testing Result — 2026-09-07 Handover

> **Historical snapshot:** this document preserves 2026-09-07 evidence/provenance. Historical statements below must not override the current project state.

> **Canonical project state — 2026-09-12:** **CURRENT** = Qualification Track **Q-1 — Production Runtime & Service-backed Qualification** (`IMPLEMENTED_TESTING_DEFERRED`). **LATEST FEATURE BASELINE** = Platform Hardening **PH-3 — NETCONF / RESTCONF / gNMI Structured Adapters** (`IMPLEMENTED_TESTING_DEFERRED`). Q-1 implementation is complete in source, but live PostgreSQL/AlmaLinux/systemd/service-backed gates remain explicitly deferred in this environment. No Q-2 is assigned. RPM source Release is `2.0.0-32`.

> **Current continuation pointer:** use the Q-1 full source baseline from 2026-09-12 as the active source. Historical CURRENT/NEXT statements below are chronology only. Execute the remaining Q-1 live gates before any promotion to `TESTED`/`RELEASED`; after Q-1 qualification, perform a fresh roadmap review before assigning Q-2.

## Test environment

- Handover execution environment Python: **3.13.5**.
- Project contract: `>=3.12,<3.14`.
- This environment had `pytest` available.
- `ruff` and `mypy` executables were not available locally during this handover.
- No GitHub Actions runner, AlmaLinux RPM host, real network devices, dedicated Net-SNMP/OpenSSH fake
  services, or production syslog relay were available for this handover run.

## Executed validation

### Pytest

Command:

```bash
PYTHONPATH=opt/netconfig pytest -q
```

Result:

```text
19 passed, 3 skipped
```

The three skipped tests are all in `tests/integration/test_protocol_fakes.py`. They intentionally
require `NETCONFIG_INTEGRATION=1` plus the CI-style OpenSSH, Net-SNMP and PostgreSQL services.

### Legacy regression suite

Command:

```bash
PYTHONPATH=opt/netconfig python opt/netconfig/selftest.py
```

Result:

```text
RESULT: ALL PASS
```

### Python bytecode compilation

Command:

```bash
python -m compileall -q opt/netconfig/netconfig tests
```

Result: **PASS**.

### Packaging shell syntax

Command:

```bash
bash -n packaging/build-rpm.sh packaging/inspect-rpm.sh packaging/smoke-installed.sh
```

Result: **PASS**. PowerShell syntax/execution of `prepare-transfer.ps1` was not run because `pwsh` was
not available in this handover environment.

### Line-ending hygiene

The handover tree was scanned for carriage returns in repository text types covered by the LF policy
(Python, shell, service/timer, spec, TOML/YAML, Markdown and related repository-control text).

Result:

```text
CR-containing text files: 0
```

## Defined but not locally executed in this handover

### Ruff

CI command:

```bash
ruff check opt/netconfig/netconfig tests
```

Status: **NOT RUN in this handover environment** (`ruff` binary unavailable). Do not report Ruff green
until this command or the GitHub Actions job actually succeeds.

Current policy intentionally ignores `E702` as the existing semicolon house-style exception while
keeping the other selected Ruff rule families active.

### Mypy

CI command covers these boundary modules:

- `security.py`
- `credentials.py`
- `configmodel.py`
- `observability.py`
- `protocols.py`
- `storage_backend.py`

Status: **NOT RUN in this handover environment** (`mypy` binary unavailable).

### Protocol integration tier

CI provisions:

- OpenSSH server with `tests/integration/fake_device_shell.py`;
- Net-SNMP agent;
- PostgreSQL 16 + psycopg.

Command:

```bash
NETCONFIG_INTEGRATION=1 pytest -q tests/integration
```

Status: **DEFERRED / not executed locally for this handover**.

## Live / target-platform qualification still required

The following are not claimed as passed:

- Python 3.12 CI job end-to-end including Ruff and mypy;
- AlmaLinux 10 RPM source/binary build;
- RPM inspection, install/upgrade and installed smoke test;
- exact systemd sandbox behavior including `MemoryDenyWriteExecute=true`;
- systemd `LoadCredential=` unattended vault bootstrap on target Linux;
- built-in TLS certificate/key permission and reverse-proxy coexistence tests;
- Cisco IOS/ASA and Arista timed-reload remediation/rollback behavior;
- JunOS `commit confirmed` remediation/rollback behavior;
- representative real-device LLDP/CDP discovery/correlation;
- production syslog direct forwarding and trusted-relay/NAT identity model;
- multi-process PostgreSQL-core/HA behavior (not implemented yet);
- NETCONF/RESTCONF/gNMI behavior (not implemented yet).

## Security-debt test note

Console idle timeout / absolute session expiry remains intentionally unimplemented. There are therefore
no expiry behavior tests in this baseline. Do not interpret that as a passing security gate; it is a
known deferred item documented in `SECURITY.md` and `ROADMAP.md`.

## Baseline acceptance for next chat

A new development chat should first reproduce at least:

```text
pytest: 19 passed / 3 environment-gated skips
legacy selftest: RESULT: ALL PASS
compileall: PASS
```

If those results change before the next feature slice, investigate the baseline regression first.


## 2026-09-10 Slice D.5 Verification

Additional verification after D.5 foundation:
- pytest: 19 passed, 3 skipped
- compile validation: passed
- Debug bundle implementation added and included in handover baseline.

> **Historical continuation pointer (superseded):** after the final artifact gate, use `netconfig_network_intelligence_ni4_FULL_source_baseline_2026-09-11.zip` as the only active source baseline. Historical CURRENT/NEXT statements below are chronology only; continuation is **PH-1 Web-console Structural Hardening**.
