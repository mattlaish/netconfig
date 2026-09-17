# Q-1 Production Qualification — Release 39

Status: `IMPLEMENTED_TESTING_DEFERRED`

## Qualification truth boundary

Q-1 separates source/offline reproducibility from production/service-backed evidence. A missing prerequisite is `NOT_RUN`; a target-host mismatch is `NOT_RUN`; an actual test or validation failure is `FAIL`. No skipped or simulated service test is promoted to PASS.

## Defect found while qualifying Release 38

Release 38 `packaging/install-rpm.sh` reported an expected RPM Release 38 but compared `${RELEASE%%.*}` against `37`. That would reject the correct `2.0.0-38` RPM. Release 39 fixes the guard and advances the package identity to `2.0.0-39`; the regression test forbids the stale `37` comparison.

## Release 39 qualification infrastructure

- Git executable index modes remain an explicit `100755` gate.
- Ruff is pinned to `0.16.7`; mypy is pinned to `2.3.1`; the source gate verifies the actual tool versions before use.
- GitHub Actions checkout is pinned to commit `3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1).
- GitHub Actions setup-python is pinned to commit `5fda3b95a4ea91299a34e894583c3862153e4b97` (v7.0.0).
- CI retains PostgreSQL/OpenSSH/Net-SNMP integration and adds an AlmaLinux 10 RPM build/static qualification job.
- Installed AlmaLinux systemd restart/smoke remains a separate explicit disposable-host gate (`--install` + `NETCONFIG_Q1_ALLOW_INSTALL=1`).

## Current runner evidence

The current runner is Debian 13 / Python 3.13. It does not provide Ruff, mypy, PostgreSQL client/server, OpenSSH client/server, Net-SNMP, RPM/rpmbuild, Docker or Podman, and DNS/package download is unavailable. Therefore those production gates remain `NOT_RUN` here. The runner can still execute the clean-checkout offline gates and staged unit verification.

### Pre-final-package measured results

| Gate | Result | Evidence |
| --- | --- | --- |
| Q-1 focused pytest | PASS | 12 passed |
| Full repository pytest | PASS | 206 passed / 7 skipped / 0 failed |
| Legacy selftest | PASS | ALL PASS |
| compileall / launcher compile / packaging shell syntax | PASS | completed with exit 0 |
| Workflow YAML parse | PASS | jobs: `python-312`, `almalinux-10-rpm-build` |
| Git executable index modes | PASS | 8/8 = `100755` |
| Staged systemd unit verify | PASS | `systemd-analyze verify --root=...` exit 0 |
| Runtime preflight on artifact runner | NOT READY | required `ssh` absent |
| Ruff 0.16.7 | NOT_RUN | tool unavailable; external download unavailable |
| mypy 2.3.1 | NOT_RUN | tool unavailable; external download unavailable |
| PostgreSQL live/backup-restore | NOT_RUN | `pg_dump` / PostgreSQL tooling unavailable |
| OpenSSH / Net-SNMP integration | NOT_RUN | service binaries unavailable |
| AlmaLinux 10 RPM build/static | NOT_RUN | current host Debian 13; harness exit 20 |
| AlmaLinux installed RPM/systemd restart | NOT_RUN | requires disposable AlmaLinux 10 host and explicit allow flag |

The seven pytest skips are exactly the four PostgreSQL live/backup-restore tests and three protocol-service integration tests. Final fresh-clone and final artifact gates are appended only after the source is committed and frozen.
