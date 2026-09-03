# NetConfig — Credentials, Vault & SNMP

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
