# NetConfig Testing Result — 2026-09-13 — Release 34 / UI-1

## Current state

**UI-1 — Unified Automation & Operations Console**  
Status: `IMPLEMENTED_TESTING_DEFERRED`  
RPM source metadata: `2.0.0-34`  
Parent baseline: Release 33 FULL source artifact SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`

## Executed offline source evidence

- UI-1 focused Web Console: **7 passed**
- UI-1 + automation expansion + PH-1 + PH-2 + PH-3 + Q-1 focused: **73 passed**
- Full repository: **175 passed / 7 skipped**
- Legacy selftest: **ALL PASS**
- `compileall`: **PASS**
- launcher `py_compile`: **PASS**
- packaging shell syntax: **PASS**
- source CR offenders after cleanup: **0**
- cache entries after cleanup: **0**
- symlinks: **0**
- required executable modes: **7/7 = 0755**

## Tooling truth

- Ruff: **NOT RUN** — binary unavailable in this isolated environment.
- mypy: **NOT RUN** — binary unavailable in this isolated environment.
- `rpmbuild`: **NOT RUN** — binary unavailable.
- PostgreSQL `pg_dump`/`pg_restore`: **NOT RUN** — client tools unavailable.

The seven pytest skips are the existing real PostgreSQL and service-backed protocol integration gates. They are not counted as passing.

## Live/deferred qualification

Still deferred: real PostgreSQL multi-node/HA/failover/PITR and restore drills, AlmaLinux RPM/systemd installation, real OpenSSH/Net-SNMP, NETCONF/RESTCONF/gNMI vendor/TLS/mTLS interoperability, SMTP/O365, production credential rotation, scale/load/failure testing, and representative Cisco/Juniper/Arista/Huawei qualification.

Session idle/absolute expiry remains explicitly deferred security debt.

## Artifact gate

Candidate artifact evidence: `netconfig_ui1_release34_candidate_2026-09-13.zip` (SHA-256 `760cb9d411e54b991cc1c285e09fdd276c2364d8e4a497da6bd2d6d756e70d2a`) passed clean-extraction verification: ZIP CRC **PASS**; path traversal **0**; symlinks **0**; caches **0** before testing; text CR offenders **0**; source/extracted byte identity **138/138 PASS**; payload and each of the three SHA manifests **133/133 PASS**; required executable modes **7/7 = 0755**. From that clean extraction, UI-1 focused **7 passed**, combined UI-1/automation/PH-1/PH-2/PH-3/Q-1 focused **73 passed**, full repository **175 passed / 7 skipped**, legacy selftest **ALL PASS**, and compileall/launcher `py_compile`/packaging shell syntax **PASS**. Ruff, mypy, `rpmbuild`, and PostgreSQL `pg_dump`/`pg_restore` remained **NOT_RUN** because those binaries are unavailable in this environment; none are counted as passing.

The formal FULL ZIP is built only after this candidate evidence is synchronized and all payload manifests are regenerated. The formal ZIP is then independently re-extracted and verified; its external SHA-256 is reported with delivery because embedding the archive hash inside the archive would be self-referential.
