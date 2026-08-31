# NetConfig

A self-hosted, zero-dependency network configuration manager. It logs into your
network devices over SSH, runs CLI commands, archives versioned text copies of
their configurations, pushes changes through an approval workflow, audits them
against security standards, and enriches inventory over SNMP — a compact,
air-gapped alternative to RANCID/Oxidized plus a slice of a change-management
and compliance tool.

**Pure Python standard library.** No pip packages. The only non-Python
dependency is the system `ssh` binary (stdlib has no SSH client — NetConfig
drives OpenSSH through a pty rather than reimplementing SSH or taking a
third-party library). SNMP, AES, and everything else are implemented in stdlib.

## Highlights

### Collect & archive (v1)
- **SSH via system OpenSSH**, driven expect-style over a stdlib pty. Password,
  SSH-key, and key-passphrase auth. `--legacy` for old gear that needs
  group14-sha1 / ssh-rsa / CBC.
- **Per-platform drivers** (Cisco IOS/NX-OS/ASA, Arista EOS, Juniper JunOS,
  HP Comware, MikroTik, generic): paging disable, enable-mode entry, config dump.
- **Encrypted credential vault** — PBKDF2 + a pure-Python ChaCha20-Poly1305 AEAD
  (validated against RFC 8439). The inventory DB holds no secrets.
- **Versioned archive** — text snapshots written only when content changes, with
  unified diffs and per-device retention. Optional secret scrubbing and full
  session transcript recording.

### Manage & control (v2)
- **Bulk automation** — write a CLI script, target a device/group/tag/all, and
  NetConfig runs it over many concurrent SSH sessions with per-device results.
  Dynamic variables (`${NodeName}`, `${IP_Address}`, `${Platform}`, …) let each
  device fill its own parameters; an unresolved variable fails at review, not on
  the switch.
- **Line-by-line color diff** between *any* two saved versions (green added / red
  deleted), in the console and CLI.
- **Baseline & drift** — designate a golden version; NetConfig flags when a device
  drifts and can submit a remediation request that replays the baseline.
- **Compliance auditing** — ISO 27001 / PCI-DSS starter rule packs check configs
  (Telnet disabled, login banner, password encryption, SSHv2, logging, NTP, no
  default communities, session timeout) and produce one-click pass/fail reports
  with remediation steps.
- **Change-approval workflow** — a junior submits a change request; a senior
  reviews the *resolved* per-device commands and approves or rejects; only then
  can it execute. Every step (who requested / approved / executed / which devices
  affected) lands in an append-only audit trail.
- **Full web console** — everything the CLI does, in the browser: add/edit/delete
  devices, manage vault credentials, run ad-hoc commands and save scripts, review and
  approve changes, audit, and edit settings — all role-gated, CSRF-protected, dark theme.
- **Users & RBAC** — viewer / operator / approver / admin, PBKDF2 passwords.
  Authentication (who you are) is separate from the vault (device secrets).
- **SNMP** — pure-stdlib v2c and full **v3 (USM)**: engine discovery, RFC 3414
  key localization, HMAC-MD5/SHA auth, and **AES-128 privacy (authPriv)** using a
  from-scratch AES validated against FIPS-197. Enriches inventory with
  sysName/Descr/uptime/contact/location and reachability. Prefer v3 authPriv on a
  hospital network; v2c (cleartext community) remains as a fallback.

## Quick start

```bash
netconfig init
netconfig user add admin --role admin          # first console user
netconfig vault create
netconfig vault set core --username admin --ask-password --ask-enable
netconfig device add sw1 --host 10.0.0.11 --platform cisco_ios --secret core
netconfig collect sw1
netconfig diff sw1
netconfig baseline set sw1
netconfig compliance --verbose
netconfig web        # http://127.0.0.1:8778
```

Bulk + approval, from the CLI:

```bash
netconfig group add core --member sw1 --member sw2
netconfig request submit --title "Add NTP" --target group:core \
    --mode config --command "ntp server 10.0.0.254"    # junior submits
netconfig request approve 1                              # senior approves
netconfig request execute 1 --save                       # runs, records job
```

SNMP v3 (authPriv):

```bash
netconfig vault set sw1-snmp --username netops \
    --snmp-auth-pass --snmp-auth-proto sha \
    --snmp-priv-pass --snmp-priv-proto aes
netconfig device add sw1 --host 10.0.0.11 --platform cisco_ios \
    --secret core --snmp-version v3 --snmp-secret sw1-snmp
netconfig snmp poll sw1
```

See `INSTALL.md` for full setup, roles, the vault-vs-login model, scheduling,
and honest limits.

## Layout

```
netconfig/
  aead.py        pure-Python ChaCha20-Poly1305 (RFC 8439)
  aes.py         pure-Python AES-128/192/256 (FIPS-197) for SNMPv3 privacy
  snmp.py        SNMP v2c + v3 USM (BER codec, key localization, auth+priv)
  vault.py       encrypted credential store
  transport.py   SSH-over-pty expect engine
  drivers.py     per-platform CLI behaviour incl. config push
  db.py          shared SQLite schema + migrations
  inventory.py   devices, groups, target resolution, SNMP facts
  users.py       user accounts + RBAC
  automation.py  variable substitution + script parsing
  workflow.py    change requests, approvals, jobs, audit
  compliance.py  ISO 27001 / PCI-DSS rule engine
  store.py       versioned config archive, diffs, baseline/drift
  scrub.py       secret masking
  session.py     transcript recording
  config.py      paths & settings
  manager.py     orchestration (collect, bulk, remediate, SNMP)
  cli.py         command-line interface
  web.py         web console (RBAC, all v2 features)
bin/netconfig    entry point
selftest.py      offline vectors + round-trips (run: python3 selftest.py)
```

## Status / limits (honest)

- **Config push & remediation write to live devices.** They were tested against a
  fake Cisco device and a local sshd, **not** against real hospital gear — verify
  on your platforms first and watch `sessions/`.
- **Remediation replays the baseline** as config lines. That cleanly re-asserts
  additive drift but does not compute negations, so it will not by itself remove
  lines that were *added*. Drift *detection + alert* is the always-safe feature;
  remediation is gated behind approval + explicit opt-in.
- **Compliance packs are Cisco-IOS-shaped starters**, meant to be extended for
  your estate — passing them is necessary hygiene, not a signed certification.
- **SNMP** was validated against net-snmp 5.9 (v2c + v3 authPriv/authNoPriv/
  noAuthNoPriv) and the RFC 3414 key-localization vector; real vendor v3 agents
  vary. Pure-Python AES is slow but fine for small SNMP PDUs.
- The console speaks plain HTTP — bind 127.0.0.1 and front with the WAF for TLS.

## Credentials, vault & SNMP

See **CREDENTIALS.md** for the vault model, adding SSH/SNMP devices (with the Aruba SNMPv3 mapping), `sudo`/`NETCONFIG_HOME` notes, and troubleshooting.

## Operating the web console

See **WEBGUI.md** for the full browser walkthrough (sign in, unlock, add devices, collect, diffs/baseline, SNMP live graph, change-approval workflow, compliance, users, settings).

### 2026-08 hardening notes

- Bulk SNMP polling now uses a bounded worker pool (`snmp_workers`, default 8).
- Remediation computes a fresh semantic plan and vendor negations instead of blindly replaying baseline text; guarded rollback and post-change verification are required.
- Scrubbed baselines are evidence-only and cannot be used for remediation.
- The web console supports optional built-in TLS, login throttling/auditing, JSON logs, and health/readiness/metrics endpoints.
- Unattended vault unlock should use systemd credentials or a protected credential file rather than a plaintext environment variable.
- Console session expiry remains explicitly deferred; see `SECURITY.md`.
