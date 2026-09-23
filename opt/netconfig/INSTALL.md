# NetConfig — Install & Operations

> **Canonical project state — 2026-09-23:** **CURRENT IMPLEMENTATION BASELINE** = **Release 51 / MC-3 Normalized Operational Evidence** (`2.0.0-51`, `IMPLEMENTED_TESTING_DEFERRED`). MC-1 Sensor Integration Unification and MC-2 Sensor History & State Transitions remain implemented. Release 51 adds a normalized cross-domain operational-evidence envelope, durable Sensor-transition → Event bridging, recovery/`UNKNOWN` semantics, additive event-schema migration/backfill/indexes, filtered/detail Event API reads, and an Event detail UI with current related Sensor state. NI-1 through **NI-7 L3/VRF Path & Route Dependency Intelligence** remain implemented. Formal RPM qualification remains deferred until the monitoring/correlation roadmap is complete; any ad-hoc RPM remains development evidence only.

## Release 48 package identity

Current RPM identity is `netconfig-2.0.0-48.el10.noarch`. The offline helper RPM is built only after the final source-artifact integrity gate; canonical AlmaLinux 10 `rpmbuild`/DNF/systemd/SELinux qualification remains separate and deferred until actually run.

**Release 48 source qualification (2026-09-20):** focused Sensor Model/API coverage is **14 passed / 0 failed**. The full repository regression was executed in four bounded mutually exclusive groups and totals **236 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent from this archive-derived workspace. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because their executables are unavailable. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux, PostgreSQL live/backup-restore, protocol-service and vendor/device live gates remain **NOT_RUN / DEFERRED**. Final source-artifact integrity qualification and offline RPM build occur after this source/documentation sync and do not promote the project beyond `IMPLEMENTED_TESTING_DEFERRED`.


**Release 46 source qualification:** repository regression executed in bounded groups totals **222 passed / 8 skipped / 0 failed**; the eight skips are seven explicit live/service prerequisites plus the expected Git-index mode skip because `.git` is absent. Focused Web Console/structural coverage is **13 passed**. Legacy selftest is **ALL PASS**; compileall, launcher `py_compile`, and packaging/tool shell syntax are **PASS**. Ruff `0.16.7` and mypy `2.3.1` remain **NOT_RUN** because the executables are unavailable. The dependency-free offline RPM builder is covered by Release 46 reproducibility and independent-verifier gates; the exact delivered RPM SHA-256 is recorded in the top-level release evidence rather than in packaged runtime documentation. Canonical AlmaLinux 10 `rpmbuild`/DNF install-upgrade/systemd/SELinux and other Q-1 live/device gates remain **NOT_RUN / DEFERRED**.


> **Roadmap disposition — 2026-09-23:** The monitoring/correlation roadmap is active. MC-1 through MC-3 are implemented in source as `IMPLEMENTED_TESTING_DEFERRED`; the next planned slice is **MC-4 / Release 52 — Unified Alert Plane**. NI-7 remains implemented and Q-1 remains an open production/service qualification track. Do not invent NI-8/Q-2 or skip the defined MC sequence without an explicit roadmap decision.

## Release 44 — Intent Automation Operations Repair

Release 44 fixes a real Web Console defect in `Operations -> Intent Automation`: `_TABS` accepted `tab=intents`, but `_operations_page()` had no `intents` renderer entry, so `GET /operations?tab=intents` raised `KeyError: 'intents'` and returned a server-error page. The renderer map now routes to `_ops_intents()`, which provides a read-only durable automation-request ledger plus links into the typed Structured Change / Desired State / Campaign creation paths. It does not create a direct network-write path; execution remains behind frozen snapshots, separate approval, current-snapshot revalidation, verification, and audit.

HTTP-level regression coverage now requests `/operations?tab=intents` and requires a `200` response with the Intent Automation content instead of a server error. Release 43's left sidebar, supplied green theme, and neutral NetConfig branding are preserved. There is no schema or public REST contract change. Package release advances to `2.0.0-44` because shipped runtime source changed.


> **Release 48 RPM status:** the final helper-emitted `netconfig-2.0.0-48.el10.noarch.rpm` is built only after the final source artifact gate. Production qualification still requires the canonical AlmaLinux package path.

## Production installation — AlmaLinux 10 RPM

The supported production package target is **AlmaLinux 10**. Use RPM Release `2.0.0-48` for the current Release 48 source baseline. Do not install an older package and assume it contains the current Sensor Engine/API runtime.

### A. Install or upgrade the RPM

On a clean or existing AlmaLinux 10 host:

```bash
sudo dnf install ./netconfig-2.0.0-48.el10.noarch.rpm
# For an existing installation, dnf install is also upgrade-safe; alternatively:
# sudo dnf upgrade ./netconfig-2.0.0-48.el10.noarch.rpm
sudo systemctl daemon-reload
```

From the source bundle you can use the guarded helper instead:

```bash
sudo ./packaging/install-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
```

The RPM:

- installs application code under `/opt/netconfig`;
- installs `/usr/bin/netconfig` with a Python 3.12 shebang;
- creates the non-login `netconfig` service account;
- owns `/var/lib/netconfig` but does not package runtime database/vault content;
- installs `netconfig-web.service`, `netconfig-backup.service`, and
  `netconfig-backup.timer`;
- installs `/etc/default/netconfig` as `%config(noreplace)`, so local settings are
  preserved across upgrades;
- requires the system OpenSSH client and OpenSSL; optional PostgreSQL mode still
  requires its separately qualified psycopg/PostgreSQL runtime.

### B. Fresh install: create the first admin explicitly

Do this **before starting the web console**. The package does not manufacture a
password or administrator account:

```bash
sudo -u netconfig /usr/bin/netconfig user add admin \
  --role admin --fullname "NetConfig Administrator"
```

The command prompts twice for the console password. On an **upgrade**, skip this
step if users already exist; `/var/lib/netconfig` is retained.

### C. Start the service and backup timer

```bash
sudo systemctl enable --now netconfig-web.service netconfig-backup.timer
systemctl is-active netconfig-web.service
systemctl is-active netconfig-backup.timer
```

The web console binds to `127.0.0.1:8778` by default. For remote administration,
use an SSH tunnel or a TLS reverse proxy/WAF. Do not expose the default plain HTTP
listener directly to an untrusted network.

Example SSH tunnel from an administrator workstation:

```bash
ssh -L 8778:127.0.0.1:8778 admin@netconfig-server
```

Then open `http://127.0.0.1:8778/` locally.

### D. Verify the installed runtime

From the source/qualification bundle:

```bash
./packaging/inspect-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
./packaging/smoke-installed.sh
```

Useful service checks:

```bash
sudo systemctl status --no-pager netconfig-web.service
sudo journalctl -u netconfig-web.service -n 100 --no-pager
sudo -u netconfig /usr/bin/netconfig --home /var/lib/netconfig qualify
```

`qualify` is configuration-aware. Optional PostgreSQL/gNMI paths are required
only when enabled. A `NOT_RUN` Q-1/live gate is not a production qualification
pass.

## Building the RPM

Build on an **AlmaLinux 10** build host/VM, not on the production host:

```bash
sudo dnf install -y rpm-build python3.12 systemd-rpm-macros
chmod 0755 packaging/*.sh
./packaging/build-rpm.sh
./packaging/inspect-rpm.sh ./netconfig-2.0.0-48.el10.noarch.rpm
```

Expected outputs:

```text
netconfig-2.0.0-48.el10.noarch.rpm
netconfig-2.0.0-48.el10.src.rpm
```

The provided source delivery can be transferred to AlmaLinux as-is; the separate
`netconfig-netconfig-2.0.0-48-rpm-build-source.zip` is a minimized build-transfer bundle.

## Manual source install

Manual copying into `/opt/netconfig` is **development/recovery only**. Production
installations should use the RPM so service account ownership, systemd units,
`%config(noreplace)`, and upgrade semantics remain deterministic.

## 1. Why it shells out to `ssh`

Python's standard library has no SSH client. The two alternatives to using the
system `ssh` binary are (a) a third-party library like paramiko, which breaks the
zero-dependency rule, or (b) reimplementing the SSH transport protocol in Python,
which is a large, security-critical undertaking you do not want a config tool to
own. So NetConfig drives the system OpenSSH client through a stdlib pty and talks
to it expect-style. OpenSSH does the crypto; NetConfig does the orchestration.

Practical consequence: OpenSSH's config, host-key handling, and algorithm support
are what actually govern the connection. That's a feature (battle-tested crypto),
but it means old gear may need the `--legacy` flag (below).

## 2. Manual source install (development only)

```bash
sudo mkdir -p /opt/netconfig
sudo cp -r opt/netconfig/. /opt/netconfig/
sudo install -m 0755 usr/bin/netconfig /usr/bin/netconfig

# pick a data directory (holds inventory DB, vault, configs, sessions)
export NETCONFIG_HOME=/var/lib/netconfig
sudo mkdir -p "$NETCONFIG_HOME"
sudo chown "$USER" "$NETCONFIG_HOME"

netconfig init
```

`NETCONFIG_HOME` defaults to `./netconfig-data` if unset. Everything the tool
stores lives under it, so back that one directory up.

## 3. First run

```bash
# 1) create the encrypted credential vault (prompts for a master password)
netconfig vault create

# 2) store a credential set. --ask-password / --ask-enable prompt so secrets
#    never land in your shell history.
netconfig vault set core-switches --username admin --ask-password --ask-enable

# 3) add a device that references that credential
netconfig device add dist-sw1 --host 10.10.0.11 --platform cisco_ios --secret core-switches

# 4) collect its config (prompts for the vault master password)
netconfig collect dist-sw1

# 5) see it
netconfig config dist-sw1 | less
netconfig versions dist-sw1
netconfig diff dist-sw1            # diff of the two most recent snapshots
```

### SSH key auth (preferred — no stored password, no vault unlock needed)

```bash
netconfig vault set core-switches --username admin --key-path ~/.ssh/netops_ed25519
netconfig device add dist-sw1 --host 10.10.0.11 --platform cisco_ios \
    --secret core-switches --use-key
```

Key auth means scheduled runs don't need the master password at all (see §6).

## 4. Platforms

`netconfig platforms` lists them. Currently:
`cisco_ios`, `cisco_nxos`, `cisco_asa`, `arista_eos`, `juniper_junos`,
`hp_comware`, `mikrotik_routeros`, `generic`.

Each driver knows how to disable paging, enter enable/privileged mode where
needed, and which command dumps the config. A platform not listed can often run
as `generic` (assumes `terminal length 0` + `show running-config`); if it needs
different commands, add a driver in `netconfig/drivers.py` — they're ~6 lines each.

## 5. Legacy devices

Modern OpenSSH disables old key-exchange, host-key, and cipher algorithms by
default, so a 2011-vintage IOS box may refuse to connect with
`no matching key exchange method found`. Add `--legacy`:

```bash
netconfig device add old-sw --host 10.10.0.50 --platform cisco_ios \
    --secret core-switches --legacy
```

`--legacy` re-enables `diffie-hellman-group14-sha1`, `ssh-rsa` host keys, and CBC
ciphers for that device. This is a knowing security downgrade, scoped per device.

## 6. Scheduled backups (systemd timer)

Runs `collect --all` on a schedule. For unattended runs, prefer **key auth** so no
vault master password is needed. If some devices require stored passwords, you can
supply the master password via `NETCONFIG_MASTER` in a root-only env file — but
understand that puts the master password in a file readable by that unit's user.
Key auth avoids this entirely.

`/etc/netconfig.env` (only if you must use password-auth devices unattended):
```
NETCONFIG_HOME=/var/lib/netconfig
NETCONFIG_MASTER=your-vault-master-password
```
```bash
sudo chmod 600 /etc/netconfig.env
```

`/etc/systemd/system/netconfig-collect.service`:
```ini
[Unit]
Description=NetConfig — collect all device configs
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=netconfig
EnvironmentFile=/etc/netconfig.env
ExecStart=/usr/local/bin/netconfig collect --all
```

`/etc/systemd/system/netconfig-collect.timer`:
```ini
[Unit]
Description=Run NetConfig collection hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netconfig-collect.timer
sudo systemctl start netconfig-collect.service   # test once
```

A snapshot is only written when a config's content actually changes, so hourly
polling won't fill the disk with identical files; retention keeps the last 30
distinct versions per device (tunable in `settings.json`).

## 7. Web console

```bash
netconfig web            # http://127.0.0.1:8778
```

Dark "Security Operations" console: device inventory, per-device collect, config
view, latest-change diff, version history, and the run log. **Login is the vault
master password**, which unlocks the vault for the process.

Security: `http.server` speaks **plain HTTP** and the console binds to
`127.0.0.1` by default. Do **not** bind it to `0.0.0.0` and log in across a
network — that sends the master password in cleartext. For remote access, put it
behind your WAF (TLS termination) and point the WAF at `127.0.0.1:8778`. Sessions
are httponly/SameSite=Strict cookies with per-session CSRF tokens on every POST.

Run it under systemd the same way if you want it always-on (bind 127.0.0.1).

## 8. Secret scrubbing

Configs contain secrets (SNMP communities, password hashes, PSKs, VTY passwords).
Add `--scrub` to a device to store a masked copy instead of the raw config
(`<scrubbed:snmp>` etc.). **A scrubbed config is not restorable** — use it when the
archive's job is change-tracking/audit, not disaster recovery. Off by default.

Session transcripts (`sessions/`) also contain secrets; they're written `0600`.
Set `"scrub_sessions": true` in `settings.json` to mask those too.

## 9. What this is not

- Not a config *push* tool. It reads; it does not modify device configs. (`run`
  will execute whatever command you give it, so it *can* push if you tell it to —
  but there's no guard-railed change workflow. That's deliberate for v1.)
- Not multi-user. Single-operator console gated by the vault password. No RBAC.
- The drivers are pragmatic, not exhaustive. Prompts, pagers, and enable flows
  vary; test against your actual gear and check `sessions/` if a driver misbehaves.

## 10. Files under NETCONFIG_HOME

```
inventory.db        SQLite device inventory + run log (no secrets)
credentials.vault   encrypted credential store (ChaCha20-Poly1305)
settings.json       instance settings
known_hosts         per-tool SSH known_hosts
configs/<device>/   current.cfg, <timestamp>.cfg snapshots, meta.json
sessions/<device>/  connection transcripts (0600, sensitive)
```

---

# NetConfig v2 — Users, Automation, Compliance, SNMP

v2 adds multi-user operation with roles, bulk automation through a change-approval
workflow, baseline/drift, compliance auditing, and SNMP. Existing v1 data
directories upgrade in place automatically (additive schema migrations run on
first launch — devices and history are preserved).

## A. Users, roles, and the vault-vs-login model

There are now **two separate secrets**:

1. **Console login** — per-user accounts (PBKDF2). This is *who you are*.
2. **The credential vault** — device SSH/SNMP secrets. This is *what the tool
   uses to reach devices*, unlocked once per process by an admin.

They are deliberately distinct: a junior can log in and submit work without ever
holding the device credentials, and unlocking the vault is a separate privileged
step. Create the first admin before starting the console:

```bash
netconfig user add alice --role admin --fullname "Alice Admin"
netconfig user add bob   --role operator
netconfig user add carol --role approver
netconfig user list
```

Roles (least → most privilege):

| role     | can |
|----------|-----|
| viewer   | view devices, configs, diffs, reports, audit |
| operator | + collect, author scripts, **submit** change requests |
| approver | + **approve/reject** requests, **execute** approved changes, manage devices, unlock vault |
| admin    | everything, including user management |

In the **web console** these roles are enforced end to end (a junior sees no
approve button; only approvers/admins can execute). The **CLI** acts with admin
authority for whoever holds a shell — use `--actor NAME` so the audit trail still
records who ran it.

Unlock the vault for a running console as an admin from the dashboard, or start
the server with `NETCONFIG_MASTER` set for unattended use.

## B. Groups and targeting

Bulk work, compliance, and requests all target devices the same way —
`kind:value`, where kind is `device`, `group`, `tag`, or `all`:

```bash
netconfig group add all-h3c --description "H3C access switches" \
    --member acc-sw1 --member acc-sw2
netconfig group list
```

## C. Bulk automation

Write commands (one per line, `${VAR}` allowed) and run them concurrently:

```bash
# ad-hoc read across a group (safe, no config change)
netconfig bulk --target group:all-h3c --mode command --command "display version"

# a config change from a script file, saved to startup, 8 workers
netconfig bulk --target tag:core --mode config --script add-ntp.txt --save --workers 8
```

Variables filled per device: `${NodeName}`/`${Name}`, `${IP_Address}`/`${Host}`,
`${Port}`, `${Platform}`, `${Tag:x}`, `${Var:KEY}`. An unresolved variable stops
that device with an error rather than sending a half-formed command.

> Note: direct `netconfig bulk --mode config` pushes immediately (CLI = admin).
> For the reviewed path where a junior can't push without sign-off, use the
> change-request workflow below (and the web console).

## D. Change-approval workflow

```bash
# junior submits (status: pending) — nothing runs yet
netconfig --actor bob request submit --title "Add NTP to core" \
    --target group:core --mode config --command "ntp server 10.0.0.254"

# senior reviews the RESOLVED per-device plan, then approves
netconfig --actor carol request show 1
netconfig --actor carol request approve 1        # or: request reject 1 --note "wrong VLAN"

# execute the approved change (records a job + per-device results)
netconfig --actor carol request execute 1 --save
```

Every transition is in the audit trail:

```bash
netconfig audit --limit 50
```

The web console (`/requests`) is the intended home for this: submit, preview,
approve/reject, and execute all have role-gated buttons, and the executed job's
per-device output is shown inline.

## E. Baseline & drift

```bash
netconfig collect dist-sw1
netconfig baseline set dist-sw1          # designate current as golden
# ... later ...
netconfig baseline drift dist-sw1        # colorized diff if it drifted
```

In the console, a drifted device offers a **Submit remediation request** button
(mode `remediate`), which — once approved and executed — fetches fresh live state, computes a semantic vendor-aware plan, arms an automatic rollback guard where supported, applies it, then re-fetches and verifies before confirming the change.
Remediation is best-effort (it re-asserts baseline lines; it does not compute
vendor negations for added rogue lines on supported grammars. Treat drift **detection** as the universally safe
control and remediation as a gated convenience.

## F. Compliance auditing

```bash
netconfig compliance                       # all standards, summary
netconfig compliance --standard PCI-DSS --verbose
```

Audits stored configs (collect first). The console `/compliance` page runs it
with one click and renders per-device pass/fail with remediation text. Rule packs
are Cisco-IOS-shaped starters covering Telnet, banners, password encryption,
SSHv2, logging, NTP, default communities, and session timeout — extend
`compliance.py` for your estate.

## G. SNMP (v2c and v3)

SNMP enriches inventory (sysName/Descr/uptime/contact/location + reachability).
Credentials live in the vault.

**v2c (cleartext community — fallback only):**

```bash
netconfig vault set sw1-snmp --username x --snmp-community public
netconfig device add sw1 --host 10.0.0.11 --platform cisco_ios \
    --secret core --snmp-version v2c --snmp-secret sw1-snmp
```

**v3 authPriv (recommended on a production network — SHA auth + AES privacy):**

```bash
netconfig vault set sw1-snmp --username netops \
    --snmp-auth-pass --snmp-auth-proto sha \
    --snmp-priv-pass --snmp-priv-proto aes
netconfig device add sw1 --host 10.0.0.11 --platform cisco_ios \
    --secret core --snmp-version v3 --snmp-secret sw1-snmp

netconfig snmp poll sw1        # or: netconfig snmp poll   (all SNMP-enabled)
```

Non-standard SNMP port: add `--snmp-port N` to `vault set`, or set `snmp_port` in
`settings.json`. The whole SNMP stack — BER codec, v3 USM, RFC 3414 key
localization, and AES-128 — is pure stdlib and was validated against net-snmp and
the RFC 3414 test vector.

**Live interface stats.** Set an SNMP version on a device and NetConfig can walk its interface table (status, speed, in/out octets, errors) and compute in/out bit-rates between polls. The console's SNMP page shows a per-interface **live graph**. For continuous updates without clicking, set `snmp_poll_interval` (Settings, or settings.json) to e.g. 15 seconds — a background poller then samples every SNMP-enabled device while the console runs and the vault is unlocked, and the graph redraws itself. `snmp_history_seconds` controls how much history the graph keeps. This is a lightweight middle ground between on-demand polling and a full always-on NMS; for long-term time-series, feed the samples to the SIEM.

## H. Self-test

```bash
python3 selftest.py
```

Runs offline vectors and round-trips: ChaCha20-Poly1305 (RFC 8439), AES
(FIPS-197), SNMP BER codec + SNMPv3 SHA key localization (RFC 3414), vault,
store/diff, RBAC, variable substitution, compliance, baseline/drift, and group
resolution. No network or devices required.

## I. Honest limits (recap)

- Config push/remediation write to live devices; tested against a fake device +
  local sshd, not real production gear. Verify per platform.
- Remediation = baseline replay (additive re-assert, not full replace).
- Compliance packs are starters, not a certification.
- SNMP pure-Python AES is slow but fine for small polls; real v3 agents vary.
- Console is plain HTTP — bind 127.0.0.1, front with the WAF for TLS.
- Not yet included: signed self-update (`sigupdate`/PAIRING.md), mini-SIEM event
  emission, and a WAF host-routing entry for the console — natural next steps.


## Optional D.5 evidence signing

Phase 4D can Ed25519-sign diagnostic and Incident support-case manifests. `/usr/bin/openssl` is a runtime dependency, but no private signing key is included in the package. Create/provision the key outside `/var/lib/netconfig` and source control. For a systemd-managed service, the preferred pattern is a service drop-in containing `LoadCredential=evidence-signing-key.pem:/secure/path/evidence-signing-key.pem`; NetConfig then reads `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem`. For manual/non-systemd runs, `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE` may point at a protected regular PEM file.

Only Ed25519 is accepted and the private-key file must have no group/world permission bits. `netconfig debug signing-status` reports the public SHA-256 SPKI fingerprint without exposing private material. Distribute that fingerprint through an independent trusted channel. `NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS` accepts comma-separated trusted fingerprints; overlap old and new pins during a planned key rotation. `NETCONFIG_EVIDENCE_SIGNING_REQUIRED=1` makes new evidence creation fail closed when a signer is unavailable or invalid.


---

Historical NI-1 documentation snapshot: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. The current baseline is the Q-1 FULL source artifact described by the canonical header.

## PH-2 PostgreSQL core deployment

SQLite remains the default. For PostgreSQL core mode, install a psycopg 3 driver appropriate to the Python 3.12 runtime and configure the PostgreSQL connection under **Settings → Database** (or `settings.json`) with `core_db_backend=postgres`. The password must not be placed in `settings.json`.

Recommended systemd drop-in:

```ini
[Service]
LoadCredential=postgres-core-password:/secure/path/netconfig-postgres-password
```

NetConfig reads `$CREDENTIALS_DIRECTORY/postgres-core-password` before opening the core database. For manual/non-systemd startup, use a root-protected `NETCONFIG_DB_PASSWORD_FILE`. `NETCONFIG_DB_PASSWORD` is legacy fallback only.

Before switching an existing SQLite deployment, configure PostgreSQL, keep `core_db_backend=sqlite`, then run `netconfig storage migrate-sqlite`. The destination application tables must be empty by default. After validating the migration, switch `core_db_backend` to `postgres` and restart. Perform a real backup/restore test before production cutover; PH-2 source tests do not constitute that live qualification.


PH-3 optional dependency: install a trusted `gnmic` binary only when gNMI profiles are required. NETCONF uses the existing OpenSSH dependency; RESTCONF uses Python TLS/HTTP. Live vendor interoperability remains a qualification gate.


## Q-1 runtime qualification

After installation, run the secret-free preflight as the service account:

```bash
sudo -u netconfig /usr/bin/netconfig --home /var/lib/netconfig qualify
```

When PostgreSQL core mode is selected, qualification requires a working psycopg 3 runtime, `pg_dump`, `pg_restore`, the configured PostgreSQL endpoint and the protected pre-vault database credential. Q-1 also provides `netconfig storage backup-postgres` and recovery-safe `netconfig storage restore-postgres`; restore requires SHA-256 verification, the literal confirmation `RESTORE_DATABASE`, and a target database different from the active core database. The restore path is intended for an isolated drill/standby/recovery database, not an in-place hot overwrite.
