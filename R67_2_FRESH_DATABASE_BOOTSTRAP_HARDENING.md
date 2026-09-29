# R67.2 — Fresh Database Bootstrap Hardening Corrective RC

**Package:** `2.0.0-67.2`  
**Schema:** `mc11-topology-change-planning-1` (unchanged)  
**State:** `IMPLEMENTED_TESTING_DEFERRED`  
**Feature authority:** unchanged. MC-11 remains the final Monitoring / Correlation / Change-Planning slice. Do not create MC-12.

R67.2 is a corrective release-candidate baseline created after live appliance rescue and a fresh-install source audit exposed database/bootstrap and login defects in R67.1. It does not add network-write authority and does not promote the product to TESTED or RELEASED. All twelve mandatory `LIVE_RC` gates remain release-blocking.

## Corrective scope

1. **Fresh login regression** — restore the process-wide `LoginThrottle` instance used by `/login` and cover a true fresh Manager → first admin → HTTP `GET /login` → HTTP `POST /login` flow. This closes the R64-through-R67.1 `NameError` regression that was missed by tests which injected authenticated sessions directly.
2. **Additive migration ordering** — bootstrap base tables first, apply additive migrations second, and create indexes last for both SQLite and PostgreSQL. Existing databases can therefore acquire newly required columns before an index references them. Fresh schema semantics and schema revision are unchanged.
3. **Fail-closed Core PostgreSQL preflight** — saving `Core Database = PostgreSQL` first validates required connection fields, protected pre-vault credential availability, psycopg 3 driver availability, connectivity, schema bootstrap/migration, and the expected schema revision. A failure leaves the persisted backend unchanged. Runtime backend activation still occurs only after process restart.
4. **Core/History database separation** — Core PostgreSQL retains the existing `pg_*` settings for upgrade compatibility. Interface History gains dedicated `if_history_pg_*` connection settings and a distinct UI panel/test action. Existing installations without dedicated History settings temporarily fall back to legacy `pg_*`; once History settings are saved, they no longer share the Core database connection fields. The History password remains in the encrypted vault and is never used as the pre-vault Core credential.
5. **Fresh PostgreSQL Core bootstrap workflow** — package `/usr/libexec/netconfig/bootstrap-postgres-core` for fresh installations. It requires psycopg 3, refuses existing operational SQLite/settings state, checkpoints phases for exact-argument `--resume`, provisions a local role/database when requested, installs the protected Core credential, wires the credential to both Web and backup services, refuses a non-empty PostgreSQL target, bootstraps the Core schema, persists PostgreSQL settings only after successful preflight, creates the first admin interactively, starts services, and validates first-start storage status. It is not a migration or force-install command.

## Additional PostgreSQL bootstrap hardening

The source audit also found that the old PostgreSQL schema conversion split `_SCHEMA` with a naive `split(";")`. A semicolon inside a SQL line comment could therefore be interpreted as a statement boundary. R67.2 uses a bounded SQL-script splitter that ignores semicolons inside quoted strings and `--` comments before classifying base DDL versus indexes. This is locally regression-tested but is **not** claimed as live PostgreSQL qualification.

## Database settings truth boundary

The Console now presents two independent concepts:

- **Core Database** — SQLite or PostgreSQL, Core host/port/database/user/SSL, protected Core credential status, cluster settings, `Test & bootstrap Core PostgreSQL`, and fail-closed Save.
- **Interface History Store** — optional long-term interface-rate persistence with dedicated History host/port/database/user/SSL, vault-backed History password, retention/downsample settings, and `Test History PostgreSQL`.

`/db-test` remains a compatibility alias for the History test. It does not validate the Core database.

## Fresh-install boundaries

The ordinary RPM install remains SQLite-first and dependency-light. A fresh SQLite appliance does not require psycopg. A fresh PostgreSQL Core deployment must first make a **psycopg 3** runtime available to `/usr/bin/python3.12`, then run the packaged bootstrap helper before creating any SQLite Core state. The bootstrap helper defaults to a distinct Core database name, `netconfig_core`.

For remote PostgreSQL, database and role provisioning are external; the helper still performs credential, emptiness, connectivity, schema, first-admin, service, and storage validation. For local PostgreSQL, the helper can create the role/database. The supplied password is never placed on the process argv.

Interrupted-install recovery is deliberately narrow: `--resume` is accepted only when the same fresh bootstrap state exists and its argument fingerprint matches. Existing settings, an existing SQLite Core, a completed bootstrap, or a different/non-fresh user set fail closed.

## Qualification truth

Local source/unit/integration, clean-extract, packaging, and helper-RPM evidence can establish implementation and artifact integrity only. They do not substitute for:

- real PostgreSQL fresh bootstrap and upgrade/recovery qualification;
- AlmaLinux 10 RPM/systemd/SELinux qualification;
- browser/operator acceptance;
- HA, scale, independent security, protocol/vendor, supportability, or MC-11 live end-to-end gates.

The R67.2 qualification runner therefore retains the same twelve mandatory `LIVE_RC` gates. R68 may be rerun only against the exact frozen R67.2 candidate after those live requirements are satisfied.
