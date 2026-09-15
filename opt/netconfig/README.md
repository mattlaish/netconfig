# NetConfig

> **Canonical project state — 2026-09-13:** **CURRENT IMPLEMENTATION BASELINE** = **UI-1 — Unified Automation & Operations Console** (`IMPLEMENTED_TESTING_DEFERRED`). Parent baseline is Release `2.0.0-33` (SHA-256 `ca0a8b9dc525118d7b542f03c715f6d20139e3584ada56bdca148e3d9ff0dccb`); UI-1 is implemented on top of PH-4/NI-5/VM-1/NA-1/NA-2/HA-1 and preserves the durable request/approve/execute safety plane. Qualification **Q-1** remains `IMPLEMENTED_TESTING_DEFERRED`; live PostgreSQL/AlmaLinux/systemd/real-device gates remain deferred. RPM source Release is `2.0.0-34`.

> **Current continuation pointer:** use the Release 34 FULL source baseline as the active implementation source. UI-1 remains `IMPLEMENTED_TESTING_DEFERRED`; execute the applicable Q-1/live qualification gates before any promotion to `TESTED`/`RELEASED`. No next development phase is auto-assigned; perform a fresh roadmap review after qualification.

A self-hosted network configuration manager. The default SQLite deployment is zero-dependency; optional PH-2 PostgreSQL core mode adds a psycopg runtime dependency. It logs into your
network devices over SSH, runs CLI commands, archives versioned text copies of
their configurations, pushes changes through an approval workflow, audits them
against security standards, and enriches inventory over SNMP — a compact,
air-gapped alternative to RANCID/Oxidized plus a slice of a change-management
and compliance tool.

**Default SQLite mode uses only the Python standard library.** No pip packages are required unless PostgreSQL core/history is selected. The baseline non-Python dependency is the system `ssh` binary (stdlib has no SSH client — NetConfig
drives OpenSSH through a pty rather than reimplementing SSH or taking a
third-party library). SNMP, AES, and everything else are implemented in stdlib.


## Qualification Q-1 runtime preflight

`netconfig qualify` emits a secret-free production-runtime readiness report. PostgreSQL core deployments fail readiness when psycopg, `pg_dump` or `pg_restore` is unavailable; gNMI requires `gnmic` only when an enabled gNMI profile exists. Q-1 also adds checksum-verified PostgreSQL core backup and recovery-to-separate-database operations. These mechanisms do not by themselves constitute live AlmaLinux/PostgreSQL/vendor qualification.

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
  drifts and can submit a guarded semantic remediation request that computes vendor-aware additions/removals and verifies fresh live state.

- **LLDP/CDP topology** — LLDP-MIB discovery with read-only CDP fallback, persisted fleet edges, and managed/unmanaged-neighbour detection. The console Topology page renders an offline SVG map and flags unmanaged devices on managed switch ports.
- **VLAN-aware endpoint intelligence (NI-1)** — modern IP-MIB IPv4/IPv6 neighbour evidence plus Q-BRIDGE VLAN-aware forwarding data is correlated into conservative `IP → MAC → VLAN → switch/port` attachments. LLDP/CDP-facing ports are treated as transit, stale evidence is marked, and ambiguous mappings remain explicit. Available via Endpoints Web UI, `netconfig endpoints`, and scoped `endpoint:read` API.
- **Event-driven collection** — optional bounded UDP syslog receiver recognizes common configuration-change events and triggers a debounced immediate archive for the source device.
- **Scoped JSON API** — bearer tokens are hashed at rest and expose read-only fleet data plus narrowly-scoped diagnostic/incident operations under `/api/v1/`. Incident writes require both `incident:write` and an operator-or-higher token role.
- **Scheduled compliance & drift digest** — periodic sweep reuses the compliance engine, baselines and SMTP/O365 delivery to email drift/failure summaries without an operator login.
- **Incident timeline (D.5/4B)** — durable `INC-YYYY-NNNNNN` incidents now correlate existing audit, syslog, configuration-collection, compliance, drift-snapshot, and diagnostic-bundle evidence through reference-only links. Timeline reads dereference authoritative stores instead of copying evidence; case export/signing, bounded protocol trace and the Incident Web Console are now implemented D.5 layers.
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

Support-case export (D.5/4C) packages Incident-owned metadata, reference-only timeline/evidence indexes and selected already-linked diagnostic bundles into a bounded managed archive with SHA-256 manifests. Raw authoritative event/config bodies are not copied into case indexes; Phase 4D signing and Phase 4E sanitized protocol-trace evidence are layered on top.

Example:

```bash
netconfig incident export-case INC-2026-000001 --reason "vendor escalation"
netconfig incident exports INC-2026-000001
```

Incident timeline example:

```bash
netconfig incident create --title "Core switch investigation" --severity HIGH
netconfig incident link-evidence INC-2026-000001 syslog 42 --note "config change"
netconfig incident link-drift INC-2026-000001 sw1
netconfig incident timeline INC-2026-000001
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
- **Remediation is semantic and guarded.** Execution fetches fresh live state, computes vendor-aware additions/removals, arms an automatic rollback guard on supported platforms, applies the plan, re-fetches and verifies before confirming the change. Unsupported rollback platforms fail closed.
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


### Evidence manifest signing (D.5 Phase 4D)

Diagnostic bundles and Incident support-case exports can be signed with an external Ed25519 private key. NetConfig does not generate or store that private key. Under systemd, deliver it as `$CREDENTIALS_DIRECTORY/evidence-signing-key.pem`; for manual/non-systemd execution, set `NETCONFIG_EVIDENCE_SIGNING_KEY_FILE` to a mode-0600 (or stricter) regular PEM key. A configured invalid/insecure key causes signing to fail rather than silently downgrading.

Create a key outside NetConfig state, for example with `umask 077` and `openssl genpkey -algorithm ED25519 -out <protected-path>`. Use `netconfig debug signing-status` to see the public fingerprint. To require signing for a specific operation, use `netconfig debug collect --require-signature` or `netconfig incident export-case <INC-ID> --require-signature`. Verify with `netconfig debug verify <bundle> --trusted-fingerprint SHA256:<hex>` or `netconfig incident verify-export <INC-ID> <CEX-ID> --trusted-fingerprint SHA256:<hex>`.

The public key embedded in an archive proves only that the signature matches that key. Authenticity requires an independently obtained SHA-256 SPKI fingerprint. `NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS` may contain comma-separated pins; overlap old/new pins during key rotation. Set `NETCONFIG_EVIDENCE_SIGNING_REQUIRED=1` when unsigned creation must fail closed globally.


### Protocol trace capture (D.5 Phase 4E)

Use `netconfig trace start <device> --protocol cli_ssh|snmp [--incident INC-...]` to enable explicit bounded metadata-only capture. Inspect with `netconfig trace list`, `trace show`, `trace events`, and end early with `trace stop`. TTL/event/metadata-byte limits stop capture automatically. SSH traces record operation/status/duration/byte counts without terminal output; secret-bearing commands are replaced with a fixed redaction marker. SNMP traces record UDP exchange target/status/latency/byte counts without packet bodies or community/v3 secrets. Linked trace evidence can be included in signed diagnostic/support-case archives.


### Incident Web Console (D.5 Phase 4F)

The authenticated console now includes **Incidents**. Viewer accounts may inspect Incident metadata, the unified timeline, evidence references, sanitized protocol traces, linked diagnostic bundles and support-case export metadata. Operator/approver/admin accounts may also create/update Incidents, perform valid lifecycle transitions, link evidence/bundles, start/stop bounded traces, and create/verify/download support-case exports. Browser mutations remain CSRF-protected and support-case downloads reuse integrity/signature verification before streaming.


### Diagnostic retention maintenance

D.5 closeout adds opt-in retention maintenance. It is disabled by default (`diagnostic_maintenance_interval=0`). Configure support-bundle count retention and optional case-export/unlinked-trace age retention under Settings -> Monitoring, or run one pass with `netconfig debug maintenance`. Case-export metadata is preserved after archive expiry and Incident-linked protocol traces are never auto-pruned by this generic worker.


---

Historical NI-1 documentation snapshot: `netconfig_network_intelligence_ni1_markdown_refresh_FULL_source_baseline_2026-09-11.zip`. The current baseline is the Q-1 FULL source artifact described by the canonical header.

### Network Intelligence NI-2

Topology now includes normalized managed-device identity (LLDP local chassis/system identity, ENTITY-MIB chassis serial/model, and IF-MIB interface identity), explicit managed-neighbour resolution evidence, and bounded downstream impact over resolved observed L2 adjacency. Use `netconfig topology --identities`, `netconfig topology --impact DEVICE [--port PORT]`, or the Topology Web/API views. Ambiguous identity is never guessed or traversed.

### Network Intelligence NI-3

NI-3 adds an opt-in bounded SNMP Trap receiver and a unified operational event stream. Enable `snmp_trap_enabled` and use the default non-privileged UDP/5162 listener (forward UDP/162 externally if required). View events with `netconfig events`, `/events`, or `GET /api/v1/events` using `events:read`. v1/v2c Trap is supported; SNMPv3 Trap and INFORM fail closed until authenticated/acknowledged receive paths are implemented. Raw packets and community strings are never persisted.


### Network Intelligence NI-4

NI-4 promotes unsuppressed NI-3 events into a durable operational-alert lifecycle with acknowledge/resolve, maintenance windows, bounded notification retry/backoff and scheduled aggregate reports. Use `netconfig alerts ...`, the `/op-alerts` console, or the scoped `/api/v1/operational-alerts`, `/maintenance-windows` and `/operational-reports` APIs. Automatic report/delivery processing is opt-in with `operational_lifecycle_interval`; SMTP notifications are separately opt-in.

### Platform Hardening PH-1

The built-in console now uses strict nonce-authorized script/style blocks, rejects inline HTML event/style attributes after render normalization, and separates API routing (`web_api.py`) from presentation helpers (`web_ui.py`). Existing routes, RBAC, CSRF and session behavior are unchanged.

## PH-2 core database modes

The default SQLite mode remains stdlib-only and is intended for single-node deployment/development. PH-2 adds an explicit PostgreSQL core mode for distributed-capable deployments. PostgreSQL mode requires the optional `psycopg` driver and a reachable PostgreSQL server; selecting it is fail-closed and never silently falls back to SQLite.

Configure `core_db_backend=postgres` plus the existing `pg_host`, `pg_port`, `pg_dbname`, `pg_user`, and `pg_sslmode` settings. Supply the core database password before process startup through a systemd `postgres-core-password` credential or a protected `NETCONFIG_DB_PASSWORD_FILE`. Use `netconfig storage status` to inspect non-secret readiness and cluster-node state.


## PH-3 structured protocol adapters

Per-device protocol profiles can select `cli_ssh`, `netconf`, `restconf`, or `gnmi`. NETCONF performs server hello/capability negotiation and fixed bounded `<get>` / `<get-config>` reads; RESTCONF performs HTTPS discovery plus bounded configuration/operational reads; gNMI supports Capabilities, Get and bounded ONCE Subscribe with typed paths. Credentials remain vault-backed and production HTTPS/gRPC certificate verification is fail-closed by default.

Use `netconfig protocol set DEVICE PROTOCOL ...`, `netconfig protocol list`, `netconfig protocol collect DEVICE`, `netconfig protocol capabilities DEVICE`, and `netconfig protocol state DEVICE`; gNMI also supports `netconfig protocol subscribe-once DEVICE`. Structured failures do not silently fall back to CLI unless `--allow-cli-fallback` is explicitly configured. gNMI requires an external `gnmic` executable discoverable on PATH or through `NETCONFIG_GNMIC`; that optional binary is not bundled by the current RPM source.

PH-3 does **not** expose arbitrary NETCONF RPC, arbitrary RESTCONF URL/method/body forwarding, shell tunnelling, or gNMI Set. An internal approval-gated RESTCONF JSON subtree replacement primitive exists for controlled change integration and performs pre-read, post-read verification and best-effort pre-image rollback, but no generic structured-write Web/API/CLI endpoint is exposed.
