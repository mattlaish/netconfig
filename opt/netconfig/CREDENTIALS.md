# NetConfig — Credentials, Vault & SNMP

> **Canonical project state — 2026-09-12:** **CURRENT IMPLEMENTATION BASELINE** = **HA-1 — Control-plane HA & Recovery Foundation** (`IMPLEMENTED_TESTING_DEFERRED`). **PH-4, NI-5, VM-1, NA-1, NA-2, and HA-1** are implemented in source and awaiting consolidated qualification. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; its live PostgreSQL/AlmaLinux/systemd/service-backed gates remain deferred. No further development phase is assigned until the post-implementation qualification/roadmap review. RPM source Release is `2.0.0-33`.

> **Current continuation pointer:** use the Release 33 full source baseline as the active implementation source. Historical CURRENT/NEXT statements below are chronology only. Run consolidated Release 33 verification and the applicable Q-1 live gates before any promotion to `TESTED`/`RELEASED`; then perform a fresh roadmap review before assigning another development phase.

This guide covers how NetConfig stores device credentials, how to add devices
(SSH and SNMP), and how to get out of the common snags. If you only read one
section, read **The model** and **Quick start**.

---

## The model (read this first)

NetConfig never keeps passwords in the inventory database. Credentials live in an
encrypted **vault** (PBKDF2 + ChaCha20‑Poly1305). A device only stores the *name*
of a vault entry — a label — not the secret itself.

You have two ways to put credentials in:

1. **Enter them on the device** (recommended). On the CLI use `--username`,
   `--ask-password`, `--snmp-user`, `--snmp-auth-pass`, etc. In the web console
   type them straight into the device form. NetConfig creates the vault entry for
   you (named `<device>-cred`) and links it to the device. You never deal with
   labels by hand.
2. **Reference an existing vault entry** by name with `--secret-name <label>`
   (CLI) or the advanced field in the console. Use this to share one credential
   across many devices.

> `--secret` / `--secret-name` takes a **vault label, not a password**. Passing a
> real password there will not work — NetConfig will look for a vault entry with
> that name and fail. As of 2.0.0‑3 the CLI warns you when a value looks like a
> password.

---

## The data directory and `sudo`

All state lives under `NETCONFIG_HOME` (default `/var/lib/netconfig` when installed
from the RPM). The vault, inventory, config archive and session recordings are all
there.

**`sudo` strips your environment.** If you run `sudo netconfig ...` in a plain
shell, `NETCONFIG_HOME` from your login profile is *not* passed through, and a
non‑packaged build would fall back to `./netconfig-data` in the current directory —
a different, empty dataset. Two ways to stay consistent:

* The **RPM launcher defaults `NETCONFIG_HOME` to `/var/lib/netconfig`**, so
  `sudo netconfig ...` already points at the right place.
* Otherwise pass the env through: `sudo -E netconfig ...`, or set it inline:
  `sudo NETCONFIG_HOME=/var/lib/netconfig netconfig ...`.

Run CLI admin tasks as the service account so files stay owned correctly:

```bash
sudo -u netconfig NETCONFIG_HOME=/var/lib/netconfig netconfig <cmd>
```

---

## Unlocking the vault (CLI)

The CLI runs **one command per process**, so there is no long‑lived "unlocked"
session. Every command that touches secrets unlocks on its own, in this order:

1. `$NETCONFIG_MASTER` if set (handy for the systemd service — see
   `/etc/default/netconfig`), else
2. an interactive prompt (only when you're on a terminal).

Under `sudo`, use `sudo -E` so `NETCONFIG_MASTER` survives, or just let it prompt.
`netconfig vault unlock` verifies your master password is correct (it does **not**
create a persistent session).

If a command can't get the master and isn't on a terminal, it now exits with a
clear message instead of a raw `vault locked` traceback.

---

## Quick start (CLI)

```bash
# one-time
netconfig init
netconfig vault create                      # sets the master password

# an SSH-managed switch (credentials entered inline -> auto vault entry)
netconfig device add core-sw1 \
    --host 10.20.0.11 --platform cisco_ios \
    --username netadmin --ask-password
netconfig collect core-sw1                  # pulls + archives the running config

# a key-authenticated device
netconfig device add edge-rtr1 \
    --host 10.20.0.1 --platform cisco_ios \
    --username netadmin --key-path /var/lib/netconfig/keys/id_ed25519 --use-key
```

Set the master once for a batch so you're not prompted per command:

```bash
export NETCONFIG_MASTER='your-master'       # or use sudo -E
netconfig collect --all
```

---

## SNMP

### v2c

```bash
netconfig device add sw2 --host 10.20.0.12 --platform cisco_ios \
    --snmp-version v2c --snmp-community 'ro-community'
netconfig snmp poll sw2
netconfig snmp stats sw2                     # interface table
```

> v2c community strings cross the wire in clear text. Prefer v3 on a hospital
> network wherever the gear supports it.

### v3 (authPriv) — mapping from the switch CLI

If your Aruba config is:

```
snmpv3 user snmp-admin auth sha auth-pass plaintext MyAuthPass123 \
    priv aes priv-pass plaintext MyPrivPass123 access-level rw
```

then in NetConfig:

```bash
netconfig device add gf-sw1 --host 192.168.3.57 --platform generic \
    --snmp-version v3 \
    --snmp-user snmp-admin \
    --snmp-auth-proto sha --snmp-auth-pass \
    --snmp-priv-proto aes --snmp-priv-pass
# you'll be prompted for MyAuthPass123 and MyPrivPass123
netconfig snmp poll gf-sw1
```

Field mapping:

| Switch CLI            | NetConfig            |
|-----------------------|----------------------|
| `user snmp-admin`     | `--snmp-user`        |
| `auth sha`            | `--snmp-auth-proto`  |
| `auth-pass ...`       | `--snmp-auth-pass`   |
| `priv aes`            | `--snmp-priv-proto`  |
| `priv-pass ...`       | `--snmp-priv-pass`   |
| `access-level rw`     | not needed — NetConfig only reads (GET/GETNEXT); read‑only is enough |

The SNMPv3 username can differ from the SSH username; it's stored separately
(`snmp_user`) and takes precedence for SNMP.

### Updating credentials later

```bash
netconfig device set-cred gf-sw1 --snmp-auth-pass          # re-prompt just the auth pass
netconfig device set-cred core-sw1 --username newadmin --ask-password
```

---

## Web console

1. Sign in, then **unlock the vault** (Devices page shows the unlock box; the
   Vault page only shows credential forms once unlocked — after a service restart
   the vault is locked again).
2. **Add device** → fill the **SNMP authentication** section right on the form
   (username, auth/priv protocol + password, community, port). It's saved to the
   vault automatically; you don't visit the Vault page.
3. **SNMP** page shows the fleet, per‑interface stats, and a live throughput graph.

The separate **Vault** page still exists for managing shared credentials directly,
but you no longer need it for normal per‑device setup.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `KeyError: 'P@ssw0rd123'` / "points at vault secret 'X' which does not exist" | A password was passed to `--secret` (a label field) | Use `--username/--ask-password` to store creds inline, or `--secret-name <label>` to reference a real entry |
| `no username available` / "vault secret 'X' has no username" | Vault locked during the command, or the entry has no `username` | Provide the master (`NETCONFIG_MASTER`/`sudo -E`/prompt); set a username with `netconfig vault set X --username U` |
| `RuntimeError: vault locked` on `vault set/rm` | No master available, non‑interactive | `sudo -E`, set `NETCONFIG_MASTER`, or run on a terminal |
| Commands act on an empty/blank dataset | `NETCONFIG_HOME` not set under `sudo` | RPM launcher defaults it; otherwise `sudo -E` or set it inline |
| `collect` fails but you only want SNMP | `collect` uses SSH | Use `netconfig snmp poll <device>` for SNMP‑only devices |

## SNMP debugging

If `snmpwalk` works but NetConfig doesn't, get a full trace and a side-by-side comparison:

```bash
sudo -u netconfig NETCONFIG_HOME=/var/lib/netconfig NETCONFIG_MASTER='<master>' \
    netconfig snmp debug <device> > /tmp/snmp-debug.txt 2>&1
# add --hex for raw packet dumps
```

It prints the resolved parameters, the equivalent `snmpwalk` command to compare, the v3 engine discovery, and every request/response. It also tests the interface table two ways -- multi-varbind GETNEXT (the default) and one OID at a time (like `snmpwalk`) -- and tells you if your agent rejects multi-varbind requests (NetConfig auto-falls back to single-OID walking in that case).

For the web console's background poller, set `NETCONFIG_SNMP_DEBUG=1` in `/etc/default/netconfig`, restart, and read the trace with `journalctl -u netconfig-web -f`.
---

## Production unattended vault unlock

For long-running polling/backup services, prefer a systemd credential instead of keeping the vault master in `/etc/default/netconfig`:

```ini
# systemctl edit netconfig-web
[Service]
LoadCredential=vault-master:/root/secure/netconfig-vault-master
```

NetConfig automatically reads `$CREDENTIALS_DIRECTORY/vault-master`. For non-systemd deployments, `NETCONFIG_MASTER_FILE=/root/secure/netconfig-vault-master` is supported; the file is rejected when group/world writable. `NETCONFIG_MASTER` remains a legacy compatibility fallback and is not the recommended production path.


## Evidence-signing key (separate from the device vault)

D.5 Phase 4D evidence signing does **not** use the device credential vault and does not make NetConfig a CA. The evidence signer accepts only an external Ed25519 PEM private key. Prefer systemd `LoadCredential=evidence-signing-key.pem:/secure/path/key.pem`, which exposes the key to the service under `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem`. Manual/non-systemd runs may use `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE`. The key file must be a regular non-symlink file with no group/world permission bits.

Never place this private key under `NETCONFIG_HOME`, source control, a support bundle, or a case export. Use `netconfig debug signing-status` to obtain the public SHA-256 SPKI fingerprint and distribute that fingerprint independently to parties that need to authenticate exported evidence. Multiple trust fingerprints may be configured during key rotation.


---

Historical NI-1 documentation snapshot: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. The current baseline is the Q-1 FULL source artifact described by the canonical header.

## PH-2 core PostgreSQL credential

The core PostgreSQL password is different from device credentials and from the optional interface-history password. Core storage is opened before the encrypted device vault, so its startup credential cannot depend on that vault. Preferred source: systemd `LoadCredential=postgres-core-password:/secure/path/password`. Manual fallback: a non-group/world-writable file referenced by `NETCONFIG_DB_PASSWORD_FILE`. `NETCONFIG_DB_PASSWORD` is retained only for legacy automation and should not be stored in `/etc/default/netconfig` when a credential file is available.


## PH-3 NETCONF / RESTCONF / gNMI credentials

Structured protocol profiles store only a `secret_ref` label (or reuse the device's existing `secret_ref`). Credential material remains in the encrypted vault and is resolved only when the protocol operation runs. NETCONF can use a vault SSH key or username/password. RESTCONF and gNMI accept vault username/password or an mTLS client certificate/key pair referenced by `client_cert_file` and `client_key_file` (RESTCONF also supports `client_key_password`). Password authentication requires a username. gNMI writes runtime secret fields only to a short-lived mode-0600 config file; they are never included in process arguments. RESTCONF authorization headers and structured request/response bodies are not persisted in protocol traces.


## Q-1 PostgreSQL backup/restore credential boundary

`netconfig storage backup-postgres` and recovery-safe `restore-postgres` reuse the pre-vault core PostgreSQL credential source. The password is written only to a short-lived mode-0600 `PGPASSFILE`; it is not placed in process arguments, settings, audit detail or returned JSON. `PGSSLMODE` is propagated from the configured core database policy. Restore additionally requires SHA-256 verification, the literal destructive confirmation, and a database name different from the active core database.
