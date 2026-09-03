# NetConfig — Install & Operations

## Quick install (AlmaLinux 10 RPM)

```bash
sudo dnf install ./netconfig-2.0.0-16.el10.noarch.rpm
sudo systemctl enable --now netconfig-web.service netconfig-backup.timer
```

The RPM installs code under `/opt/netconfig`, the launcher at
`/usr/bin/netconfig`, creates the `netconfig` service account and the protected
`/var/lib/netconfig` data directory, and installs the web and backup systemd
units. Upgrades retain runtime data and preserve a locally edited
`/etc/default/netconfig`. See `packaging/README.md` in the source tree for the
reproducible RPM/SRPM build and test procedure.

Zero-dependency network configuration manager. Logs into your devices over SSH,
runs commands, and archives text copies of their configs with versioned diffs.

- **Runtime:** Python 3.12+. No pip packages. Python stdlib only.
- **System requirement:** the OpenSSH client (`ssh`) must be on `PATH`. On Debian:
  `sudo apt-get install openssh-client`. That's the *only* non-Python dependency,
  and it's there because stdlib has no SSH client — see the note below.

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

**v3 authPriv (recommended on a hospital network — SHA auth + AES privacy):**

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
  local sshd, not real hospital gear. Verify per platform.
- Remediation = baseline replay (additive re-assert, not full replace).
- Compliance packs are starters, not a certification.
- SNMP pure-Python AES is slow but fine for small polls; real v3 agents vary.
- Console is plain HTTP — bind 127.0.0.1, front with the WAF for TLS.
- Not yet included: signed self-update (`sigupdate`/PAIRING.md), mini-SIEM event
  emission, and a WAF host-routing entry for the console — natural next steps.
