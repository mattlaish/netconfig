# NetConfig

A self-hosted, **zero-dependency** network configuration and security-operations
console. NetConfig logs into network devices over SSH, archives versioned copies
of their configurations, pushes changes through an approval workflow, audits them
against security standards, and enriches inventory over SNMP — a compact,
air-gapped alternative to RANCID/Oxidized plus a slice of change-management and
compliance tooling.

**Pure Python standard library.** No pip packages are required to run it. The
only external runtime dependency is the system `ssh` binary (the stdlib has no
SSH client, so NetConfig drives OpenSSH through a pty). SNMP, AES,
ChaCha20-Poly1305, and the web console are all implemented in stdlib. One
**optional** feature — long-term interface-throughput history — can use
PostgreSQL via `psycopg`; everything else needs nothing beyond Python and `ssh`.

- **Runtime:** Python 3.12+ (aligned with AlmaLinux 10 and the installed
  `/usr/bin/python3.12` launcher)
- **Version:** 2.0.0 (RPM release `-16`)

## About this repository

This repo is a **source reconstruction of the RPM payload**, not a conventional
build tree:

- `opt/netconfig/` — the application (Python package under
  `opt/netconfig/netconfig/`, plus `selftest.py` and the operator docs)
- `etc/`, `usr/` — packaged config and systemd service/timer units
- `packaging/` — reconstructed EL10 RPM spec, build/inspect/smoke scripts

Make application changes under `opt/netconfig/`; keep packaging and service
changes in their payload paths.

## Features

### Collect & archive
- **SSH via system OpenSSH**, driven expect-style over a stdlib pty. Password,
  SSH-key, and key-passphrase auth; a `--legacy` mode for old gear.
- **Per-platform drivers** — Cisco IOS/NX-OS/ASA, Arista EOS, Juniper JunOS,
  HP Comware, MikroTik, and a generic fallback.
- **Encrypted credential vault** — PBKDF2 + a pure-Python ChaCha20-Poly1305 AEAD
  (validated against RFC 8439). The inventory database holds no secrets.
- **Versioned archive** — text snapshots written only when the config changes,
  with unified diffs, per-device retention, optional secret scrubbing, and full
  session transcripts.

### Manage & control
- **Bulk automation** — run a CLI script across a device/group/tag/all over many
  concurrent SSH sessions, with per-device dynamic variables resolved at review.
- **Baseline & drift** — designate a golden version, flag drift, and submit a
  gated remediation request.
- **Change-approval workflow** — submit → review the *resolved* per-device
  commands → approve → execute, with an append-only audit trail.
- **Compliance auditing** — ISO 27001 / PCI-DSS starter rule packs with
  pass/fail reports and remediation notes.
- **Users & RBAC** — viewer / operator / approver / admin, PBKDF2 passwords;
  authentication is separate from the vault.

### Monitor & observe
- **SNMP** — pure-stdlib v2c and full v3 (USM): engine discovery, RFC 3414 key
  localization, HMAC-MD5/SHA auth, and AES-128 privacy (authPriv) using a
  from-scratch AES validated against FIPS-197.
- **MIB library** — upload vendor MIBs to name OIDs in walks and drive bounded
  vendor collection, with per-file resolved/unresolved/conflict diagnostics.
- **Live + 24h interface throughput** — per-interface in/out rate graphs on the
  SNMP page; an optional PostgreSQL store adds a 24-hour history view.
- **Monitoring & alerts** — background TCP/UDP port, HTTP, and TLS checks with
  history and alert rules; optional email (SMTP or Microsoft 365 OAuth).
- **NetFlow** — a bounded stdlib v5/v9 collector.

### Web console
Everything the CLI does, in the browser — add/edit devices, manage vault
credentials, run and save scripts, review/approve changes, audit, and edit
settings — all role-gated, CSRF-protected, with a persisted light/dark theme.
The dashboard groups devices by type (collapsible) with a name/IP/tag search.

> The console speaks plain HTTP by design — bind it to `127.0.0.1` and front it
> with your reverse proxy/WAF for TLS.

## Quick start

Install on AlmaLinux 10 from the RPM (see `opt/netconfig/INSTALL.md` for the
full procedure), then:

```bash
netconfig init
netconfig user add admin --role admin      # first console user
netconfig vault create
netconfig vault set core --username admin --ask-password --ask-enable
netconfig device add sw1 --host 10.0.0.11 --platform cisco_ios --secret core
netconfig collect sw1
netconfig diff sw1
netconfig compliance --verbose
netconfig web                               # http://127.0.0.1:8778
```

## Documentation

| Doc | Covers |
|-----|--------|
| [`opt/netconfig/INSTALL.md`](opt/netconfig/INSTALL.md) | Install & operations, platforms, backups, SNMP, and the optional PostgreSQL interface-history setup |
| [`opt/netconfig/README.md`](opt/netconfig/README.md) | Detailed feature overview and module layout |
| [`opt/netconfig/CREDENTIALS.md`](opt/netconfig/CREDENTIALS.md) | Vault model, adding SSH/SNMP credentials, troubleshooting |
| [`opt/netconfig/WEBGUI.md`](opt/netconfig/WEBGUI.md) | Web console walkthrough |
| [`packaging/README.md`](packaging/README.md) | Building the RPM/SRPM on AlmaLinux 10 |

## Build & test

```bash
# Offline self-test (no network or devices required)
cd opt/netconfig && python3 selftest.py

# Build the RPM/SRPM on an AlmaLinux 10 build host
./packaging/build-rpm.sh
```

The self-test runs offline vectors and round-trips: ChaCha20-Poly1305 (RFC 8439),
AES (FIPS-197), the SNMP BER codec and SNMPv3 key localization (RFC 3414), vault,
store/diff, RBAC, automation, compliance, baseline/drift, and target resolution.

## Honest limits

- Config push/remediation write to live devices; they were tested against a fake
  device and a local sshd, **not** real production gear — verify per platform.
- Remediation replays the baseline (additive re-assert), it does not compute a
  full replace, so it will not by itself remove lines that were *added*.
- Compliance packs are Cisco-IOS-shaped starters, not a certification.
- The pure-Python SNMP AES is slow but fine for small polls; real vendor v3
  agents vary.
- The web console is plain HTTP — terminate TLS at a proxy in front of it.

## License

Proprietary. See the RPM spec (`packaging/netconfig.spec`) for packaging
metadata.
