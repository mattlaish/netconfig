# NetConfig Patch Ledger

This file is the chronological implementation ledger for AI handover and
release/version control. It records what changed in each development batch,
independently of Git history. `AI_HANDOFF.md` remains the overall architecture,
current-state, and next-task handoff; this file is the authoritative delta log.

## Maintenance Rules

- Read `AGENTS.md`, `AI_HANDOFF.md`, and this file before modifying the project.
- Add or update a patch entry whenever code, tests, packaging, schema, service
  integration, security behavior, or user-visible documentation changes.
- Put the newest patch entry first.
- Use IDs in the form `PATCH-YYYYMMDD-NN`; never reuse an ID.
- Keep an entry `In progress` while work is incomplete, then record the actual
  validation result before changing it to `Ready for integration`.
- State explicitly when Linux/RPM/live-device validation remains outstanding.
- Never record credentials, community strings, private keys, tokens, or customer
  secrets. Use placeholders only.
- Do not infer that a patch was committed, pushed, signed, built, or installed.
  Record only actions that were actually completed.
- After a completed stage or an update to README/handover/version documents,
  the user-facing final feedback must end with the current Taiwan timestamp in
  the exact format `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)`.
- The repository owner performs Git synchronization manually. Do not run Git
  operations unless the user explicitly changes that instruction.

## Entry Template

```text
## PATCH-YYYYMMDD-NN — Short title

- Status:
- Target release:
- Scope:
- Files changed:
- User-visible behavior:
- Data/schema impact:
- Packaging/upgrade impact:
- Security impact:
- Validation completed:
- Validation outstanding:
- Known risks/limitations:
- Rollback notes:
- Recommended next step:
```

## PATCH-20260820-02 — Taiwan-time completion feedback rule

- **Status:** Complete.
- **Target release:** Development-process documentation; no application release
  change.
- **Scope:** Makes a Taiwan UTC+8 timestamp mandatory at the end of user-facing
  feedback after a completed development stage or README/handover/version-file
  update.
- **Files changed:** `AGENTS.md`, `CLAUDE.md`, `AI_HANDOFF.md`, and `patch.md`.
- **User-visible behavior:** Qualifying final responses end with
  `YYYY-MM-DD HH:MM:SS UTC+8 (Taiwan)` as their final line.
- **Data/schema impact:** None.
- **Packaging/upgrade impact:** None.
- **Security impact:** None; the timestamp contains no sensitive information.
- **Validation completed:** Confirmed that all four AI instruction/handover files
  contain the exact timestamp format and final-line requirement.
- **Validation outstanding:** None.
- **Known risks/limitations:** The timestamp depends on the executing
  environment clock being correct.
- **Rollback notes:** Remove the timestamp rule and this ledger entry.
- **Recommended next step:** Apply this format to every qualifying final
  feedback from this point onward.

## PATCH-20260820-01 — Consolidated 2.0.0-16 development patch

- **Status:** Ready for AlmaLinux integration testing; not built, installed,
  committed, or pushed by the AI.
- **Target release:** `netconfig-2.0.0-16.el10`
- **Scope:** Consolidates all workspace changes made after reconstruction of the
  original `netconfig-2.0.0-14.noarch.rpm` and the failed `-15` CRLF build.
- **Files changed:** Application modules under `opt/netconfig/netconfig/`,
  `opt/netconfig/selftest.py`, installation/development documentation, system
  launcher, `.gitignore`, RPM engineering under `packaging/`, `AI_HANDOFF.md`,
  and this ledger.
- **User-visible behavior:**
  - Settings uses a left-side topic menu with shorter subpages.
  - Pure Application devices use hostname/FQDN-oriented fields and hide SSH-only
    controls; mixed Network/System devices retain management controls.
  - SNMP pages expose persisted facts, interfaces, ARP, MAC/bridge information,
    raw/resolved OIDs, MIB mapping source, and per-file MIB diagnostics.
  - Uploaded MIB `OBJECT-TYPE` definitions drive bounded extended collection.
    Net-SNMP Linux devices map enterprise 8072 to Net-SNMP 8072, UCD-SNMP 2021,
    and HOST-RESOURCES `.1.3.6.1.2.1.25` collection trees.
  - System/Application compliance supports `unknown` and `not_applicable`;
    application operational health is displayed but not compliance-scored.
    Application checks include certificate validation/expiry, active TLS 1.0
    and 1.1 rejection, cipher strength, HSTS, nosniff, and CSP evidence.
  - The authenticated top bar includes a persisted Light/Dark theme toggle.
- **Data/schema impact:** Additive SQLite tables persist extended MIB values and
  poll status. Existing database initialization/migrations remain idempotent; no
  destructive migration is introduced.
- **Packaging/upgrade impact:** Reconstructed EL10 spec/build/inspection/smoke
  tooling targets release `-16`. Source and build flow normalize Windows CRLF;
  `/usr/bin/netconfig` is LF-only with a Python 3.12 shebang. The release bump is
  required so `dnf upgrade` replaces the broken `-15` launcher installation.
- **Security impact:** SNMPv3 engine discovery and RFC 3414 localized keys are
  cached per poll, removing repeated CPU-intensive derivation. Compliance probe
  errors no longer produce false passes. No credentials or secrets were added.
  `.gitignore` excludes local databases, vaults, MIB indexes, environment files,
  keys, certificates, logs, caches, and RPM build outputs.
- **Validation completed:** Windows Python 3.12 `compileall` passed; bundled
  offline self-test completed with `RESULT: ALL PASS`; packaging/version/payload
  static checks passed; 50-file artifact, private-key/certificate, high-confidence
  secret, and large-file scans passed. Launcher and packaging scripts were
  checked for Linux LF endings.
- **Validation outstanding:** AlmaLinux Bash syntax check; actual RPM/SRPM build;
  RPM inspection; `-15` to `-16` upgrade; installed smoke test; systemd/SELinux;
  live SSH, SNMP/MIB, TLS/HTTP, compliance, NetFlow, and device integration.
- **Known risks/limitations:** Windows cannot validate RPM macros, executable
  modes, systemd sandbox behavior, or Unix-only `pty` transport. Extended MIB
  collection remains deliberately bounded. Current ARP collection does not yet
  provide modern cross-device IP-to-MAC-to-switch-port correlation.
- **Rollback notes:** Retain a known-good RPM and database/config backup before
  upgrading. Application schema changes are additive, but package downgrade and
  restored application code should be tested on a copy of production data.
- **Recommended next step:** Build and inspect `-16` on AlmaLinux 10.2, perform
  the installed smoke test and live regression checks, then begin Slice 1:
  modern `ipNetToPhysicalTable` neighbor collection.

## Planned Delivery Slices

These are roadmap items, not completed patches. Create a new patch entry when a
slice begins; do not mark it complete here without implementation and validation.

1. Modern ARP/IPv4/IPv6 neighbor collection.
2. VLAN-aware Q-BRIDGE MAC forwarding table.
3. Global IP -> MAC -> VLAN -> switch port correlation.
4. LLDP/CDP topology and discovered-device matching.
5. Alert lifecycle, maintenance windows, and notification retry.
6. Dependency-aware downstream alert suppression.
7. Authenticated Linux system compliance audit.
8. Expanded application security posture and response-policy checks.
9. Polling worker reliability, scheduling, backoff, and health telemetry.
10. Retention, aggregation, and database maintenance.
11. Reports, exports, and scheduled delivery.
12. Backup/restore and disaster-recovery verification.
13. PostgreSQL, distributed pollers, HA, signing, and enterprise deployment.
