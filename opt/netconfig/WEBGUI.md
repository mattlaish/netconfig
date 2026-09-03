# NetConfig — Web Console Operator Guide

This guide documents **every page and every control** in the console: what each
button, field, and option does, and what value it expects. Controls you can't see
are hidden because your role doesn't grant them (see **Users & roles**) or because
a prerequisite isn't met (e.g. monitor sections appear only for the matching device
type). Where a control's label is terse, the "what it does" description below is the
authoritative meaning.

The console renders `WEBGUI.md` (this file) on the **Help** page, so it always
matches the installed version.

---

## Navigation

The top nav exposes: **Devices**, **Groups**, **Automation**, **Change Requests**,
**Compliance**, **Alerts**, **SNMP**, **MIB**, plus (for admins) **Vault**,
**Users**, **Settings**, and always **Audit**, **Run Log**, **Help**. The top-right
shows the vault lock state, your username, your role, and **Sign out**.

---

## 1. Sign in / Sign out

- **Username / Password** → your NetConfig account (PBKDF2-hashed; not a device
  credential). **Sign in** starts a session cookie.
- **Sign out** (top-right) ends the session. It does **not** lock the vault.

## 2. Unlock the vault

The vault holds device credentials and secrets (SMTP password, O365 client secret),
encrypted with PBKDF2 + ChaCha20-Poly1305. It is **locked** after every restart.

- **Create vault** (first run only) → **Master password**: sets the master. It is
  never stored and cannot be recovered — lose it and the secrets are unreadable.
- **Unlock** → **Vault master password**: decrypts secrets for this run. Collection,
  runs, SNMP polling, and alert email all need the vault unlocked.
- To auto-unlock on start, set `NETCONFIG_MASTER` in `/etc/default/netconfig`
  (less secure — the master then lives in a file).

---

## 3. Devices (dashboard)

Lists inventory: **Name**, **Host:port**, **Type** (badges), **Platform**,
enabled/disabled. Click a name to open the device.

- **+ Add device** → opens the device form (below).
- **Collect all enabled** → SSHes to every enabled device and archives its config
  now (see Collect).

### Device form (Add / Edit)

- **Name** → unique inventory key (read-only when editing).
- **Host / IP** → address NetConfig connects to.
- **SSH port** → TCP port for SSH (default 22).
- **Device type** → **checkboxes, pick one or more**: **System**, **Network**,
  **Application**. Type controls which monitor sections appear and which compliance
  and collection logic applies. A box running an app can be both System **and**
  Application.
- **Platform** → CLI driver (cisco_ios, nxos, eos, junos, comware, mikrotik,
  generic…). Determines the commands used to fetch config.
- **Tags** → comma-separated labels for targeting bulk jobs/change requests.
- **SSH vault secret** → name of a Vault secret holding the SSH username/password/
  key for this device. This is a **reference to a Vault entry, not the password
  itself**. Leave the inline fields blank if you use this.
- **Enable vault secret (optional)** → Vault secret holding the enable password.
- Inline credential fields (under "Advanced / manual entry"): **SSH username**,
  **SSH password**, **SSH private key path**, **Enable password** — use these to set
  credentials directly on the device instead of via a Vault secret.
- **SNMP version** → none / v2c / v3. Enables the SNMP facts, interface stats, and
  (for Network devices) ARP/MAC collection.
- **SNMPv3 username** → the SNMP USM user (often differs from the SSH login).
- **SNMP vault secret** → Vault entry holding SNMP community (v2c) or v3 auth/priv
  material.
- **SNMP port** → default 161.

Monitor sections (appear by device type):

- **TCP / UDP ports** (System) — **Ports to monitor**: list like
  `tcp/22, tcp/443, udp/53` (bare numbers default to TCP). Checked live on the
  device page and by the background poller.
- **REST API / HTTPS** (Application) — **Endpoints to monitor**: one URL per line,
  optional expected status code, e.g. `https://host/api/health 200`. HTTPS URLs are
  also checked for certificate validity and days-to-expiry.
- **NetFlow** (Network) — enables matching received NetFlow records to this device by
  source IP (collector is enabled in Settings).

Other device-form controls:

- **Notes** → free text.
- **Enabled** → include in "Collect all", bulk jobs, and background polling.
- **Save changes / Add device** → writes the inventory entry.
- **Danger zone → Delete device** → removes the inventory entry. Archived configs on
  disk are **kept**.

### Device page sections

- **Collect now** → SSH in and archive the current config immediately. A new version
  is saved **only if it differs** from the last; the difference is shown under
  **Changes in last backup** (green added / red removed).
- **Run command** (operator+) → run one read-only command and show output. Audited.
- **Baselines & drift**:
  - **Set current as baseline** → saves **this device's most recently collected
    configuration** as its **drift baseline** — the known-good reference that future
    collections are compared against. (It does not fetch a new config; collect first
    if you want the latest.)
  - **Clear baseline** → removes the baseline, disabling drift detection for the
    device.
  - **Drift from baseline** → shows how the current config differs from the baseline;
    **Submit remediation request** opens a change request to push it back.
- **Compare versions** → pick **Older** and **Newer** archived snapshots, **Diff**
  shows a line-by-line colour diff.
- **Config backups** → every archived version with its SHA-256; open any one.
- **SNMP facts** → sysName, sysDescr, **Model (sysObjectID)** (always resolved
  through the MIB automap — a full vendor name if the MIB is loaded, otherwise a
  partial name with a hint, or the raw OID), uptime, location, last polled.
- **Interfaces** / **Live interface throughput** → per-interface status/speed/
  counters and a live in/out bps graph. **+ Add interface** adds another interface to
  the graph.
- **MAC address → port** (Network devices, **last section**) → the switch's layer-2
  forwarding table: which **MAC** is learned on which **port** (interface name),
  cross-referenced with the **IP** from the ARP table. Collected automatically on
  SNMP poll; empty on non-switches (no bridge forwarding table).

---

## 4. Groups

Named sets of devices for bulk targeting.

- **Group name**, **Members** (multi-select), **Save group** → create/update.
- **delete** → remove the group (devices are untouched).

## 5. Automation

- **Run now (ad-hoc)** (approver/admin) → **Target type** (device / group / tag /
  all), **Target value**, **Mode** (command = read-only, config = push), **Commands**
  → runs concurrently and shows per-device results. Config mode pushes immediately —
  the reviewed path is Change Requests.
- **Script library** → **Save a script** (**Name**, **Description**, **Commands**)
  for reuse; saved scripts are listed with **delete**.

## 6. Change Requests (approval workflow)

- **New change request** → **Title**, **Target type/value**, **Commands**,
  **Submit for approval**. Creates a `CR#` in "submitted" state.
- On a request: **Approve** / **Reject** (approver/admin), then **Execute now** to
  push to the targets. Every state change (requested / approved / executed / devices
  affected) is audited.

## 7. Compliance

- **Standard** → ISO 27001 / PCI-DSS (or all).
- **Run compliance audit** → evaluates each device by type: Network = config-policy
  checks (telnet disabled, banner, password encryption); System = live port posture
  (telnet/ftp/smb/rdp not exposed, ssh reachable); Application = TLS valid, cert not
  expiring < 30 days, TLS 1.2+, HTTPS-only, endpoints healthy. Report shows pass/fail
  per check with remediation text.

## 8. Alerts

- **Firing alerts** → currently breaching rules (severity, device, detail, age).
- **New alert rule** → build a rule from **what you can monitor**:
  - **Name** — label for the rule.
  - **Device** — a specific device or **all devices**.
  - **Monitor** — the metric: **Port state** (system), **HTTP status**,
    **Response time ms**, **TLS days to expiry**, **TLS certificate valid**
    (application).
  - **Condition** — operator; the choices auto-adjust to the metric
    (`is`/`is_not` for states; `== != > < >= <=` for HTTP status; `> <` for response
    time; `< <=` for TLS expiry).
  - **Threshold** — the value to compare against (e.g. `closed`, `200`, `14`).
  - **Target** — the specific port/URL, or blank for any target of that kind.
  - **Severity** — high / medium / low.
  - **Create rule** — saves it. The background poller opens an alert when a rule
    starts breaching (and emails it if SMTP is on), and resolves it on recovery.
- **Alert rules** list → each rule with **delete**. **Recently resolved** shows the
  last cleared alerts.

## 9. SNMP

Fleet SNMP view: every SNMP-enabled device with reachability, model, uptime,
interface count, and last-polled.

- **Poll** (one device) / **Poll all** → refresh SNMP facts + interface stats now.
  For Network devices this also collects the ARP and MAC tables.
- Background polling is enabled by **SNMP background poll interval** in Settings.

## 10. MIB

- **Upload MIB** → upload one or more `.mib`/`.txt` MIB files. On upload they are
  compiled into the **global automap index** (OID ↔ name).
- **Automap index** → shows how many OIDs/named objects are indexed and a
  **look-up box**: paste a numeric OID to get its name, or a name to get its OID.
  This index resolves names automatically across SNMP views — there is **no
  per-device MIB selection**.
- **MIB library** → uploaded files with **delete** (deleting rebuilds the index).

## 11. Vault (admin)

- **Stored secrets** → names and which fields are set (values are never shown).
  **edit** / **delete** per secret.
- **New / edit secret** → **Secret name**, then **SSH** (Username, Password, Enable
  password, Private key path, Key passphrase) and **SNMP** (v2c community, SNMP port,
  v3 auth proto/pass, v3 priv proto/pass, SNMPv3 username). On edit, blank fields
  keep their current value — you can rotate one field without re-entering the rest.

## 12. Users & roles (admin)

- **Add user** → **Username**, **Full name**, **Password**, **Role**, **Create
  user**. Roles are cumulative:
  - **viewer** — read-only.
  - **operator** — + collect, run read-only commands, submit change requests, manage
    scripts.
  - **approver** — + approve/execute changes, ad-hoc runs, unlock vault.
  - **admin** — + manage users and settings, alert rules, SMTP/O365 config.

## 13. Settings (admin)

Stored in `settings.json` in the data directory. Bind/port and collector changes
take effect on next console restart.

- **Console bind address / port** → where the console listens (127.0.0.1 recommended;
  front with the WAF for TLS).
- **Config versions to keep**, **SSH connect/command timeouts**, **Bulk concurrent
  workers**, **Host key policy** (accept-new / yes / no), **Session recording** +
  **scrub secrets**.
- **SNMP**: default port, **SNMP background poll interval (s)** (0 = off; e.g. 15
  enables live graphs), **Live-graph history window (s)**.
- **NetFlow collector**: enable, UDP port, recent flows kept per device.
- **Monitoring & alerts**: **Monitor poll interval (s)** (0 = off; runs port/HTTP/TLS
  checks in the background, records history, evaluates alert rules), **Monitor history
  retention (days)**.
- **SMTP (alert email)**: **Send alert email** (enable), **SMTP host/port**,
  **STARTTLS**, **From**, **To** (comma-separated), **SMTP username**, **SMTP
  password** (kept in the vault, never in settings.json). **Send test email** sends a
  test now.
- **Microsoft 365 OAuth (Entra ID)** → alternative to a password: **Use O365 OAuth
  for email** authenticates to `smtp.office365.com` with an OAuth token (XOAUTH2)
  using tenant/client ID and **Client secret** (secret held in the vault).
  **Test O365 sign-in** validates the token flow.
- **Save settings** → writes `settings.json`.

## 14. Audit & Run Log

- **Audit** → every action (who / what / target / when): logins, device changes,
  collects, runs, approvals, alert firing/resolution, settings changes.
- **Run Log** → history of collection/automation jobs and their per-device results.

---

## Automatic weekly backups

A systemd timer (`netconfig-backup.timer`, Sundays 02:00) exports a backup and keeps
the last few. Requires `NETCONFIG_MASTER` set so the unattended run can read the vault.

## Troubleshooting

- **"Vault locked"** → Unlock in the console, or set `NETCONFIG_MASTER`. The vault
  re-locks on every restart.
- **A monitor/section is missing** → it's gated by device type (System→ports,
  Application→REST/HTTPS, Network→NetFlow + MAC/ARP) or by your role.
- **sysObjectID shows a partial name** → upload that vendor's MIB on the MIB page to
  fully resolve it.
- **No MAC/ARP data** → the device needs SNMP configured and must be a switch
  (routers/hosts have no bridge forwarding table).
- **500 / blank after upgrade** → restart the service and re-unlock the vault; check
  for a `/etc/default/netconfig.rpmnew` after big upgrades.

---

## Console hardening additions

The console now exposes `/healthz`, `/readyz`, and Prometheus-text `/metrics`, emits structured JSON access/authentication events, throttles repeated failed logins by peer IP + username, and sends additional browser security headers. The enforced CSP is transitional while legacy inline handlers remain; a strict nonce policy is emitted in report-only mode for migration work.

Optional built-in TLS is available without a new runtime dependency:

```bash
netconfig web --bind 0.0.0.0 --port 8778 \
  --tls-cert /etc/netconfig/tls/server.crt \
  --tls-key /etc/netconfig/tls/server.key
```

Session idle/absolute expiry is a known deferred security item and is intentionally not changed in this hardening slice. See the repository `SECURITY.md` and `ROADMAP.md`.

## Topology, event-driven collection, and API

- **Topology** shows persisted LLDP/CDP neighbour edges. Managed neighbours are matched against inventory name/IP and collected SNMP sysName; unmatched neighbours are explicitly flagged **UNMANAGED**. Operators can run **Discover now** to refresh the fleet.
- **Settings → Monitoring** enables the bounded syslog receiver (default udp/5514), queue size, debounce window, and scheduled compliance/drift digest interval. A syslog config-change event from a known device triggers an immediate debounced collect.
- Read-only API tokens are created from the host CLI, not the browser: `netconfig api-token create NAME --role viewer --scope inventory:read --scope topology:read`. Save the printed token immediately; only its hash is retained. Send it as `Authorization: Bearer <token>` to `/api/v1/inventory`, `/api/v1/topology`, `/api/v1/drift`, `/api/v1/compliance/latest`, `/api/v1/digest/latest`, or `/api/v1/audit` when the corresponding scope is granted.
