# NetConfig AI Handover

## 67.8 Enable credential precedence corrective — 2026-11-05

Live 67.7 testing passed SSH authentication and the legacy SHA-1 host-signature
stage, then failed at Cisco privileged mode despite the user having saved the
correct Enable secret. The defect was local: Web-managed device secrets can be
both `secret_ref` and `enable_ref`; `_creds_for()` loaded `enable_password`
correctly, then overwrote it with the same record's SSH login `password`.

- Enable resolution is now `enable_password` first, then the `password` field
  used by a separate password-only Enable vault secret, then the previously
  resolved value. No credential value is migrated, exposed or guessed.
- Same-record Web credentials, a separate secret with explicit
  `enable_password`, and the legacy separate password-only secret are covered.
- Failed base configuration collection now says route learning was not attempted;
  it no longer appends the misleading generic route-learning failure.
- Focused Enable/route/retained legacy SSH regression: 67 PASS; Python compile
  PASS. Package advances to 2.0.0-67.8 for upgrade from the live 67.7 test.
  Live privileged-mode success remains NOT_RUN for the new bytes; no Git or R68
  promotion.

## 67.7 legacy RSA SHA-1 verification corrective — 2026-11-05

The live AlmaLinux/Cisco test reached the isolated Paramiko backend but failed
during key exchange with `sha1 is not supported by this backend for RSA
signing`. This is the RHEL-family crypto-backend rejection of an otherwise
valid legacy `ssh-rsa` host signature, before password authentication.

- Only devices explicitly using Older-device SSH compatibility receive the
  fallback. Normal devices remain on system OpenSSH; no system crypto-policy,
  OpenSSL configuration or inventory default is changed.
- The fallback catches only `UnsupportedAlgorithm` from Paramiko verification
  and handles only the `ssh-rsa` signature identifier. Other RSA algorithms
  retain the backend result. PKCS#1 v1.5 decoding requires exact SHA-1
  DigestInfo, at least eight FF padding bytes and an exact full encoded block.
- Paramiko completes the host signature check before NetConfig checks or pins
  the managed known_hosts entry and before any password/private key is sent.
  Changed keys, malformed/tampered signatures and RSA below 512 bits fail.
- Focused compatibility regression is 23 PASS, including the exact restricted-
  backend exception, valid/tampered data, non-SHA-1 isolation, RSA 512/1024/2048
  loopback login, changed known_hosts and below-minimum rejection. Python compile
  PASS. The preceding merged baseline remains 868 PASS / 15 skipped; no new full
  suite or live success is claimed.
- Package identity advances to 2.0.0-67.7 for upgrade from 67.6. Status remains
  IMPLEMENTED_TESTING_DEFERRED until the exact RPM passes live Cisco/AlmaLinux
  installation, systemd, SELinux and device tests. No Git operation or R68
  promotion is part of this corrective.

## 67.6 RSA 512+ SSH compatibility — 2026-11-04

User requires one reusable older-device mode that supports RSA host keys from
512 bits upward, rather than adding one device/key length at a time. OpenSSH's
`RequiredRSASize` cannot lower its built-in 1024-bit floor, so opted-in devices
now use an isolated Paramiko 3.5 SSHv2 backend. Normal devices still use system
OpenSSH. No IP-specific rule or global crypto-policy change was added.

- Compatibility backend supports Paramiko 3.5's legacy KEX/cipher/MAC families
  and forces `ssh-rsa` signatures for the old RSA path. Live RSA key size is
  checked before credentials; 512+ proceeds and below 512 fails clearly.
- Managed known_hosts is loaded before authentication. Matching keys proceed;
  changed same-type keys always fail; `yes` rejects unknown keys; `accept-new`
  and explicit `no` pin unknown keys. Nonstandard ports use `[host]:port`.
- Password/keyboard-interactive and private-key authentication, CLI PTY and
  NETCONF subsystem channels share the existing command/trace/timeout interface.
  OpenSSH-only extra options fail clearly in this isolated backend.
- Actual loopback SSHv2 handshakes pass with RSA 512, 1024 and 2048 host keys,
  password auth, prompt and command execution. Changed keys and RSA below 512
  are rejected before password. Related regression retains normal OpenSSH mode.
  Final related suite: 99 PASS / 2 explicit Windows POSIX-mode exclusions in
  38.47 s. Exclusions are first-admin 0600 and release-tool 0755 assertions;
  RPM mode verification remains independent. Legacy selftest ALL PASS.
- RPM identity advances to 2.0.0-67.6 and requires `python3-paramiko >= 3.5`
  and `< 5`; Paramiko 5 removes the required SHA-1 KEX/signature algorithms.
  Fedora EPEL 10 currently supplies 3.5.x. Live Cisco/AlmaLinux qualification
  remains NOT_RUN; status stays IMPLEMENTED_TESTING_DEFERRED.
- Offline builder produced two byte-identical RPMs from epoch 1793750400;
  independent structure/source/mode/scriptlet/versioned-dependency verification
  passes. Final SHA-256 is `1b9727d7761ce03ebd7e80eead5fcfe682db49eacd86c857bce8dccb8a41c0c4`.
  Delivery: `C:\Users\mattlai\Downloads\netconfig-20261104-67.6\netconfig-2.0.0-67.6.el10.noarch.rpm`
  with SHA256SUMS and RPM_BUILD_REPORT.json. Unsigned helper RPM; no SRPM.
- Preserve prior SNMPv3, Endpoint CSV, evidence/routing/vendor, Sensor cleanup
  and operator-workflow repairs. No Git operations, deployment or R68 promotion.

## 67.5 SSH/SNMPv3 RPM delivery — 2026-11-04

User confirmed the legacy-mode error on Cisco 192.168.0.205 is exactly
Bad key types '+ssh-rsa,ssh-dss'. The unsupported ssh-dss list is the existing
legacy-mode bug fixed by compiled-capability filtering. Package both today's
SSH and SNMPv3 fixes as real Release 67.5 for upgrade from 67.4.
User also reported Cisco show snmp: 26 Unknown community name. This is a
cumulative unknown-community packet counter, not error code 26; it can remain
after a fix. Compare before/after an explicit poll, accounting for other pollers.
User confirmed Cisco uses SNMP v2c; the community value itself was not supplied.
Added explicit v2c manual community override regression; do not promise the RPM corrects a mismatched
Cisco/server setting or erases historical counters. Community values stay private.

- Runtime hashes match the immediately preceding 150 PASS / 6 Windows-excluded
  source checkpoint, selftest ALL PASS. New packaging/identity/SSH/SNMPv3 focused
  checks and final artifact verification are recorded in the external report.
  Final packaging regression: 51 PASS / 3 deliberate exclusions, 14.36 s,
  including the new v2c community case. Exclusions are two qualification-runner
  environment cases and the POSIX CI mode assertion; no Git-index test executed.
- Keep this device's Older-device SSH compatibility enabled after upgrade.
  No inventory edit/default downgrade/global crypto-policy change is made here.
  This removes the reported unsupported-list error; it does not prove that the
  Cisco will pass every subsequent SSH negotiation/authentication stage.
- Build uses the existing Python offline builder, epoch 1793750400. Two final
  builds compared; independent RPM/source/mode/launcher/config/scriptlet verifier
  and packaged-Python compilation precede delivery. Unsigned; canonical AlmaLinux
  rpmbuild/install/upgrade/systemd/SELinux and live Cisco/FortiGate/PG NOT_RUN.
- Delivery: C:\Users\mattlai\Downloads\netconfig-20261104-67.5\netconfig-2.0.0-67.5.el10.noarch.rpm
  with SHA256SUMS and RPM_BUILD_REPORT.json. Prior 67.4 artifact remains unchanged.
  No SRPM. Actual artifact hashes live outside source to avoid a hash cycle.
- Spec, installer example, canonical banners, identity tests and source metadata
  synchronized to 67.5. Earlier source-only notes below are historical; both
  repairs are included in 67.5. Status IMPLEMENTED_TESTING_DEFERRED, no Git/live
  deployment/R68 promotion or inherited frozen-candidate evidence.
- Earlier 104 GB startup cause remains unverified; later user reports include
  Web NetFlow and connection-test responses. Do not assert old no-8778 status
  remains current, or claim this SSH package diagnosed that historical delay.

## Per-device SSH compatibility repair — 2026-11-04

User reported Cisco 192.168.0.205 offering only diffie-hellman-group-exchange-sha1,
group14-sha1 and group1-sha1, then clarified it supports SSH version 2. SSHv2 is
already the intended protocol; the reported failure is KEX algorithm agreement,
before password authentication. Do not tell the user to find SSHv3 or blame SSHv2.
SNMPv3 missing-credential fixes from the preceding section are preserved.

- Existing per-device legacy flag is now labelled Older-device SSH compatibility.
  It stays opt-in. No automatic weaker retry, inventory migration or global
  ssh_config/crypto-policy changes. The previously delivered 67.4 label is
  legacy algorithms; enable it on this device to request its existing mode.
- transport queries the resolved local SSH binary with ssh -Q kex/key/cipher
  only when default legacy additions are needed. Each subprocess has 2 s timeout,
  no shell, input or device connection. Cache is bounded and keyed by binary
  path/category/mtime/size. Append only compiled-supported legacy candidates;
  removed ssh-dss/3des/etc are omitted rather than invalidating the whole command.
  Empty subsets add no invalid empty options. Explicit algorithm overrides keep
  their previous behavior. Prefer group14, then group-exchange, then group1.
- Modern/default mode makes no capability probes/additions. Host-key checking,
  known_hosts, target-after-- and password/key selection remain. Compiled support
  is not system-policy approval; FIPS/crypto policy may still reject old methods.
- Detect standard KEX/host-key/cipher/MAC mismatch output during negotiation or
  EOF and produce an actionable TransportError instead of misleading auth/bytes
  repr. When mode is off, direct user to this per-device checkbox; when already
  enabled, explain local support/policy limitation and device SSH update. No
  password send, fallback connection or authentication retry is introduced.
- Validation: 150 PASS / 6 deliberate Windows exclusions,
  100.42 s / 7 modules. Includes 17 new SSH cases and the prior SNMPv3 cases;
  one initial checkbox assertion wrongly depended on inline style stripped by
  CSP, corrected to inspect the actual checked attribute. First broad run hit
  five pre-existing gNMI fchmod-dependent cases unavailable on Windows; excluded
  without changing their security code, alongside first-admin POSIX mode case.
  Legacy selftest ALL PASS; 100 runtime + new SSH test compile; Ruff 0 findings
  in changed Python. Local Windows OpenSSH -G parsing PASS (no device connection).
  SNMP module hash and _do_device_test AST match the prior credential repair.
- No live Cisco/FortiGate/AlmaLinux/PG test or browser visual acceptance claimed.
  Source-only, identity 2.0.0-67.4 / IMPLEMENTED_TESTING_DEFERRED, no Git/build/
  deployment. Delivered 67.4 remains unchanged and excludes BOTH today's SNMPv3
  and SSH fixes. A future upgrade RPM needs a higher Release. Source docs/metadata
  synchronized; do not overwrite old artifact or claim a production resolution.
- Reference: https://www.openssh.org/legacy.html (per-host appends and ssh -Q).
- Proof: C:\Users\mattlai\AppData\Local\Temp\netconfig-ssh-compat-cbfefbdb31b74131b8c1ac51e6c3dd3a.

## SNMPv3 missing-credential and connection-test repair — 2026-11-04

User reported Failed SNMP v3: 'NoneType' object has no attribute 'encode'.
Reproduced locally with missing authentication password; V3Params also allowed
None usernames. Manager's connection-test path normalizes missing usernames to
empty strings, so its reported None.encode path points to password localization.
Do not claim the actual user's vault contents were inspected.

- snmp.V3Params validates nonempty text username, selected auth password and
  compatible auth/privacy configuration before discovery/network I/O. Direct
  password_to_key rejects None/empty/non-text input before encode/modulo. Errors
  identify the field, never echo secret values. Explicit noAuthNoPriv remains
  supported; missing passwords do not silently downgrade security. Existing
  privacy-password reuse of auth password is preserved; whitespace is retained.
  This adds presence/type validation, not a new passphrase-length policy.
- Test connection now honors cred_mode. Manual mode merges nonempty edits over
  the original device's separate SSH/SNMP entries; blank passwords retain saved
  values even when hidden reference selects are disabled/not posted. Saved mode
  ignores manual fields and requires a selected SNMP secret. No credential or
  inventory writes; existing audit/host-key behavior remains. Password/community
  whitespace is no longer stripped. Never substitute SSH password for SNMP auth.
- Manual SNMP form explains required auth fields and password reuse. On existing
  67.4, user can enter SNMPv3 username/passwords in device Edit, Save changes, then
  Poll now to use persisted credentials; Test connection could otherwise use an
  old selected secret or lose blank saved fields in the unfixed version.
- Validation: 123 related PASS / 2 Windows POSIX-mode exclusions
  (100.50 s, 7 modules), including 24 new credential tests. Legacy selftest
  ALL PASS, including RFC key vectors; 100 runtime + new test compile; Ruff 0 new /
  3 baseline. Tests cover missing fields/no network, noAuth/auth/privacy reuse,
  normal polling, manual edits with disabled references, blank/whitespace values,
  saved-mode injection, separate secret preservation and response redaction.
- Source-only; identity remains 2.0.0-67.4 / IMPLEMENTED_TESTING_DEFERRED. No Git,
  RPM build, version bump, deployment or live FortiGate/AlmaLinux/PG verification.
  Delivered 67.4 SHA remains 00e30d4f77f27afa7880fae64b68142e4c66d06b8e51b3b66936e0f726b62e4b
  and excludes this fix. Next delivery needs a higher Release for dnf upgrade.
- Source docs/metadata synchronized. Corrected two broken 67.4 delivery paths
  caused by a prior escaped newline in generated Markdown. Later user reports
  include Web NetFlow/Test connection output; do not keep asserting the earlier
  missing-8778 snapshot is current. Exact 104 GB startup SQL/cause is unconfirmed.
- Proof: C:\Users\mattlai\AppData\Local\Temp\netconfig-snmpv3-credentials-7a61b39cda664d6b84b6d83fcb2c6064.

## 67.4 RPM delivery — 2026-11-03

User requested the RPM after Endpoint CSV source work. Actual package Release is
67.4 for upgrade from installed 67.3. Includes filtered Export CSV with IP/MAC,
likely switch/port and explicit uncertainty; preserves 67.3 runtime repairs.
Runtime export hashes match the immediately preceding 96 PASS / 1 Windows-mode
exclusion checkpoint, selftest ALL PASS. Packaging-only identity/manifest/CSV/
cleanup checks and final reproducibility results are in the external build report.
Final packaging checks: 37 PASS / 3 deliberate exclusions in 9.10 s (the two
qualification-runner environment cases and the POSIX CI mode assertion). Both
offline RPM builds were byte-identical; independent verifier passed; 101 packaged
Python/launcher files compiled; Ruff 0 findings in the packaging Python changes.

- Source root unchanged. No Git or live deployment; status remains
  IMPLEMENTED_TESTING_DEFERRED, no R68 promotion or inherited LIVE_RC PASS.
- Existing Python offline builder, epoch 1793664000. Two final builds compared;
  independent RPM/payload/source verification and in-memory Python compilation
  precede delivery. Unsigned; canonical AlmaLinux rpmbuild/install/upgrade/
  systemd/SELinux/PG/device/latency qualification is NOT_RUN. No SRPM is generated.
- Delivery: `C:\Users\mattlai\Downloads\netconfig-20261103-67.4\netconfig-2.0.0-67.4.el10.noarch.rpm`,
  adjacent SHA256SUMS and RPM_BUILD_REPORT.json. Earlier 67.3 output is preserved.
- IMPORTANT: this adds CSV, not a new startup repair. The user's 104 GB SQLite
  startup still had no 8778 and advancing I/O at the last report. Exact SQL/stage
  is unconfirmed. Do not interrupt ongoing initialization to install this export;
  wait for completion or separately diagnose the startup blocker. Do not close it.
- Canonical banners, spec, metadata, installer example and identity tests synced
  to 67.4. Source history notes below describe earlier checkpoints/artifacts.

## Endpoint CSV source update and live startup investigation — 2026-11-03

User requested /endpoints export of IP, MAC and likely switch/port. Implemented
in the canonical source root; existing delivered 67.3 RPM is unchanged and does
NOT contain this source update. No Git, build, version bump or deployment here.

- Existing authenticated /endpoints supports format=csv. Export CSV button keeps
  only the current q/device filters and downloads netconfig-endpoints.csv, UTF-8
  BOM for spreadsheet use, no-store. It uses the same endpoint_inventory result
  as the page, without a second correlation pass or new device/network I/O.
- One row per distinct IPv4/IPv6 address; MAC-only evidence gets a blank IP.
  Columns: IP, MAC, Likely switch/port, VLAN, Result, Confidence, Direct connection
  proven, IP mapping fresh, Candidate locations, Transit observations, Outdated
  observations. Unresolved/ambiguous/transit/stale rows have no guessed primary
  location; their observation lists remain. No direct-attachment proof is added.
- web_evidence.endpoints_csv uses csv.writer for quotes/newlines/Unicode and
  escapes spreadsheet formula-leading cells. Empty results keep CSV headers.
  Existing sign-in/user-disabled handling applies; viewers can read/export.
- Validation: 96 PASS / 1 Windows first-admin POSIX-mode assertion excluded,
  45.72 s across export/evidence/network-intelligence/Web UX modules. Selftest
  ALL PASS; 100 runtime Python files + new test compile; Ruff 0 new / 6 baseline.
  HTTP tests cover filters, button URL, response headers, viewer/anonymous/disabled
  access, no I/O/no writes; pure tests cover uncertainty, all IPs, MAC-only,
  formula prefixes, Chinese/CSV quoting/newlines. A first disabled-user test used
  a legacy fixture session; corrected to the real managed-session constructor.
  No new browser visual or live-device/AlmaLinux/PG qualification is claimed.
- Source docs/metadata updated. Prior 67.3 artifact hash remains
  e7dafff523ba609a9a3124369d29cf0626988cc9c166805ffdb8925cd2e7f6a3.
  A future deliverable needs a new package Release for upgrade; never overwrite
  or call this feature present in the already-installed 67.3 artifact.
- LIVE ISSUE STILL OPEN: user installed 67.3; service PID 370869 running one
  thread, 8778 absent. inventory.db is 104 GB, MIB cache 1.2 MB; SQLite etilqs
  temporary file open. Python RSS was 35400 KiB (~35 MB); systemd service Memory
  13.1 GB is a different/cgroup measure and must not be called Python RSS.
  Over the user's 10-second sample, read_bytes rose 314036224 (~299.5 MiB),
  write_bytes rose 26882048 (~25.6 MiB): startup I/O progressing, not proof of
  which SQL/index/migration is active or a completion-time guarantee. Do not
  falsely close the startup issue or repeatedly restart ongoing index work.
  py-spy was unavailable; no fresh Python startup stack has been captured.
- Next: user reports whether 8778 appears / startup completes; if still blocked,
  identify the exact startup stage before another corrective RPM. Source CSV
  feature is ready for later packaging, not a reason to interrupt current startup.
- Proof: C:\Users\mattlai\AppData\Local\Temp\netconfig-endpoint-export-d9d4804c147e452188e19792d082214a.

## RPM delivery — 2026-11-03

User confirmed the host already has netconfig-2.0.0-67.2.el10.noarch.
The deliverable therefore advances the actual RPM Release to 67.3 so
`dnf upgrade` installs the repair. This is a packaging revision, not a new
feature phase or R68 release decision. Preliminary same-version 67.2 test
builds remain only in external Temp proof and are not the delivered RPM.

- Active source stays C:\Users\mattlai\Projects\netconfig. Includes Nov 2 Sensor
  cleanup/login responsiveness, Nov 1 evidence/routing/MIB repairs and Oct 25
  Account/credential/unconfigured-NetFlow corrections. Runtime repair hashes
  match the Nov 2 validation; its 211 PASS / 2 Windows exclusions and selftest
  ALL PASS remain prior source evidence, not a new full-suite run today.
- Build uses the existing Python offline RPM builder, since this Windows host
  has no available canonical AlmaLinux rpmbuild environment. Source timestamp
  is fixed at 1793664000 (2026-11-03 00:00:00 UTC). Two final builds and independent
  structure/header/digest/payload/source/mode/config/scriptlet verification are
  recorded in the external delivery proof. All packaged Python compiles in memory.
  It is unsigned and offline-verified only; no live install/upgrade, systemd,
  SELinux, PostgreSQL, latency or LIVE_RC PASS is implied. Status remains
  IMPLEMENTED_TESTING_DEFERRED; no R68 release promotion or Git operations. Spec, source metadata, installer
  example, canonical documentation banners and identity regressions use 67.3.
  Historical R67.2 qualification evidence is not reused as current PASS.
- Delivery: C:\Users\mattlai\Downloads\netconfig-20261103\netconfig-2.0.0-67.3.el10.noarch.rpm
  with adjacent SHA256SUMS and RPM_BUILD_REPORT.json. These contain final hashes
  outside packaged docs, avoiding an artifact/source hash cycle. Old project-root
  RPM remains unchanged and stale; do not accidentally send it. This helper does
  not generate an SRPM. Existing configuration/state preservation is retained.
- Source metadata regenerated after documentation sync. A large existing DB may
  take extra time on first updated startup to create the new retention indexes.
  No manual SQL is needed. Real-host installation remains the next user action.
- Final 67.3 packaging/source regression: 18 PASS / 3 deliberately deselected
  (4.19 s). Selected release identity/manifest/SBOM/installer/canonical truth and
  all cleanup regressions; excluded two qualification-runner environment cases
  and a POSIX executable-mode CI assertion. No Git-index test was executed.
- Proof: C:\Users\mattlai\AppData\Local\Temp\netconfig-rpm-20261103-d4be8843b00646d7a44ceb53f77d8de9.

## Sign-in blocked by Sensor cleanup — 2026-11-02

User supplied a live Python stack: /login Users.count and the SNMP scheduler
were waiting at the SQLite shared connection lock while the monitor thread was
inside DELETE in SensorHistoryRecorder._prune_history. This identifies the
blocking path; the snapshot alone does not distinguish disk cost from another
process's write lock. Previous November 1 "login unresolved" notes are historical
for this specific path; no claim that every possible login delay is solved.

- db.py adds (observed_at,id) indexes for sensor_observations/transitions through
  existing additive startup schema/index initialization (SQLite and PG schema).
  Existing large databases may need extra time for this one-time index build.
- File-backed SQLite retention uses an independent, short-lived connection to
  the resolved already-open DB filename, mode=rw, with 50 ms busy timeout. It
  never creates a replacement DB, uses no web/shared-connection lock, commits
  each table's batch separately, and closes/rolls back its own handle on failure.
  The normal connection's 5000 ms busy timeout and locking stay unchanged.
- Each attempt deletes at most 500 expired rows per table via an indexed ID
  subquery; no unbounded DELETE or drain loop. Backlog/contended in-memory handle
  retries after at least 1 second; completed sweep waits an hour. Failure backs
  off 60 seconds and logs only exception class. Deadlines are monotonic and a
  recorder guard prevents concurrent duplicate sweeps. These are triggered by
  subsequent Sensor records, not a new background timer or idle-cleanup promise.
- New observations/transitions are committed before optional cleanup. Failed
  cleanup cannot discard their evidence. In-memory SQLite uses a nonblocking
  lock and skips an existing transaction, never committing someone else's work.
  Other adapters retain their connection contract with portable bounded SQL;
  PostgreSQL does not gain the separate SQLite maintenance connection.
- Sensor retention stays 30 days observations / 180 days transitions. Physical
  cleanup may lag during backlog, no new observations, DB outage or contention.
  NetFlow's separate 24-hour PostgreSQL history is unchanged. No login caching,
  password/session/RBAC changes or manual operator SQL is required.
- Validation: 211 related PASS / 2 Windows POSIX-mode assertions
  deselected (108.01 s, 13 modules). New tests cover indexed in-place
  upgrade, bounded/retried expiry with exact-cutoff preservation, cleanup failure
  retaining observations/transitions, transaction ownership, real external
  SQLite writer contention/recovery, and real HTTP healthz/login responses while
  cleanup SQL is deliberately paused. PG adapter SQL compatibility is offline.
  Legacy selftest ALL PASS; 100 runtime Python files + new regression compile;
  Ruff 0 findings in changed Python. First broad run found an additional Windows
  secure-file POSIX-mode incompatibility; excluded without weakening security.
  First new-test run corrected a fixture's mistaken salt column name.
- No private-key/token signatures or temporary source files in checked changes.
  November 1's three restored files match their completion hashes unchanged.
  READMEs, patch.md and source metadata synchronized; package remains 2.0.0-67.2 /
  IMPLEMENTED_TESTING_DEFERRED. No Git, RPM build/version bump/deployment; existing
  RPM is stale and unchanged. Live AlmaLinux latency, real PG/devices and LIVE_RC
  NOT_RUN. Rebuild/install and reproduce on the user's host before claiming a
  verified production resolution. Other October 31 audit issues remain open.
- Backups, patch ledger and final proof:
  `C:\Users\mattlai\AppData\Local\Temp\netconfig-history-cleanup-2b0e5b8cf3074daaadf293c3a403a685`.

## Review of the November 1 restore + October 31 audit items — 2026-11-01

Source-only; status stays `IMPLEMENTED_TESTING_DEFERRED`. See PATCH-20261101-03.

- List/summary pages must use `ConfigStore.drift_state()` / `has_current()`; never
  `drift()` (builds a full diff) in loops. This was the probable login delay.
- Device-page Monitoring panels read `monitor_results`; live checks only via
  `/device-monitor-check` or the background monitor.
- `/compliance-run` requires the `collect` permission.
- Dashboard reachability ignores polls older than 3× interval (min 1 h) or 24 h.
- `Manager.collect` isolates route-learning failures; never let L3 bookkeeping
  discard a config snapshot.
- Next: unchanged — choose release identity, freeze a candidate, run the twelve
  LIVE_RC gates.

## Restored evidence repairs, merged with October 25 changes — 2026-11-01

User requested restoring the three missing files and their required integration.
`web_evidence.py` (the requested `eb_evidence.py`), `vendor_measurements.py`
and `test_evidence_repairs.py` match their earlier completed SHA-256 checkpoint.
Existing October 25 Account, credential cleanup, unconfigured History DB and
cross-OS metadata ordering changes are preserved. See PATCH-20261101-02.
This restores the previously completed repairs described below. Canonical
source remains `C:\Users\mattlai\Projects\netconfig`. No Git operations, RPM build,
version increase or live deployment; status remains `IMPLEMENTED_TESTING_DEFERRED`.

- Endpoint correlation: a single fresh non-transit FDB record is now CANDIDATE /
  LOW, not ATTACHED / HIGH. `attachment` is null; `observed_location` retains the
  useful switch/port/VLAN observation, with `direct_connection_proven=false`.
  The old `summary.attached` key is retained; `summary.candidate` is additive.
  API/CLI consumers must not treat a candidate as a physical attachment. Search,
  Endpoints and device MAC tables retain candidate locations and explicitly show
  known-neighbor transit, multiple candidates, outdated and unclassified data.
  FDB alone does not distinguish a directly plugged-in host from an unseen
  bridge. Invalid/future timestamps are not fresh. No direct-proof engine added.
- Safety consequence: MC-11 endpoint-IP planning no longer auto-selects a device
  from FDB-only candidates. Explicit managed-device source/destination planning
  still works. Existing approval, frozen snapshot and mutation controls unchanged.
- Routing topology: independent Inventory → Routing topology entry, prominent
  Physical / Layer 3 / Combined links, collection status for all Network devices
  (including unsupported/not collected), visible stale/error hints and device
  Overview route panel. Old route data remains hidden from current graphs after
  one hour, with an explicit explanation and Show outdated link, not deletion.
  Collect config + routes reuses authenticated, CSRF/RBAC-protected `/collect`,
  configured CLI method/credentials, then returns to routing view with results.
  This is explicit device I/O and also saves a config snapshot. GET does not
  collect. Structured protocol profiles are not silently bypassed; unsupported
  method/platform is explained. No new automatic polling or forced fallback.
- `vendor_measurements.py`: optional declarative `numeric` conversion/range/
  upper/lower warning/critical thresholds on profile metrics and table sensors.
  Finite bounded rule validation, positive scale, range/order checks; no scripts,
  expressions, unbounded walks or relaxed enterprise-root restrictions. Values
  outside range, invalid/NaN/Inf readings are UNKNOWN. Numeric zero is preserved.
- Bundled FortiGate CPU/processor/VDOM CPU defaults warn >=80%, critical >=95%;
  memory/VDOM memory warn >=80%, critical >=90%, valid range 0..100. These are
  adjustable NetConfig policies, not asserted manufacturer recommendations.
  Numeric CPU/memory profiles without policy now return UNKNOWN, including old
  runtime overrides, rather than blindly OK. Other explicit enumeration mappings
  remain. Threshold text is saved with Sensors. Existing Sensor observations,
  transitions, operational events and alert open/recovery paths are reused.
- SNMP Vendor profile telemetry now shows readable measurement names, units,
  health rules, last evaluation and a scoped latest-50 history view. Old CPU/
  memory snapshots without thresholds show Unknown until polled under the new
  policy. An unmatched profile explicitly explains that uploaded MIB names/raw
  values are not automatic semantic monitoring. No claim of all-vendor MIB
  coverage, arbitrary-MIB auto-interpretation or new AlmaLinux metric mappings.
- Validation: 335 related tests PASS / 2 Windows POSIX-mode assertions deselected
  (23 modules, 161.84 s); legacy selftest ALL PASS; 100 runtime Python
  files and changed regressions compile. Ruff: 0 new / 23 baseline findings.
  Six protected files are byte-identical and four Account/form functions are
  AST-identical to the current pre-merge tree. Checked changes have no secret
  signatures or temporary source files. Source metadata regenerated/checked
  at closeout. No new browser/live PostgreSQL, real-device, AlmaLinux service
  or LIVE_RC verification is claimed.
- Out of scope: intermittent login delay (root cause still unproven), viewer
  compliance execution, stale global overview status and hidden live checks on
  other device tabs from the October 31 audit are NOT repaired by this change.
- Existing project RPM is stale; rebuilding/real-host verification is a separate
  user-selected step. Backups/proof:
  `C:\Users\mattlai\AppData\Local\Temp\netconfig-restore-merge-5846c8b23b8c48be884419f485a5fc10`.

## Review fixes after the 2026-10-24 workflow repairs — 2026-10-25

Source-only; status stays `IMPLEMENTED_TESTING_DEFERRED`. See PATCH-20261025-01.

- `web_forms.device_owned_ref()` identifies form-created per-device vault entries;
  `_release_replaced_refs()` deletes replaced ones only when unreferenced by devices
  and protocol profiles. Never extend it to user-named secrets.
- `FlowHistory` has a `configured` state: provider `None` (no History DB host/name)
  means memory mode with no buffering and no error notices; exceptions still mean an
  outage. Tests that simulate an outage must use a failing backend, not `None`.
- `/account` + `/account-password` in `web_ux.py` (self-service password change).
- Release metadata sorts by POSIX relative path; regenerate on any OS.
- Next: unchanged — choose release identity, freeze a candidate, run the twelve
  LIVE_RC gates.

## Six workflow repairs + operator presentation — 2026-10-24

User authorized all six findings from the preceding workflow audit, plus the
engineering-oriented incident/change page. Implemented in the canonical root
`C:\Users\mattlai\Projects\netconfig`; no Git operations, version change or build.

- `web_forms.py`: device form validates required fields, numeric ports, name
  collisions and collection override before rename/credential writes. Manual
  credentials fork unique SSH/SNMP vault entries from their separate old sources;
  blank passwords retain previous values. Saved mode ignores forged manual fields.
  Application-only isolation and System management remain covered. Error forms
  retain safe fields/original edit identity, never submitted passwords/community.
- Numeric Settings validation rejects malformed/out-of-range/non-finite values
  before publishing changes. Candidate settings do not mutate the live dict until
  storage succeeds. Mail/OAuth/History credential saves require a created/unlocked
  vault; errors are explicit/sanitized, with prior-secret compensation on failure.
  Database settings retain existing Core connection/setup checks.
- Cross-file vault/archive/inventory/settings changes are NOT one ACID operation.
  Device storage failures inspect actual rename/reference state, retain attached
  credentials and report uncertain/partial saves rather than promising rollback.
  Failed secret compensation explicitly requires administrator review.
- Collect/Poll SNMP return via 303 to the same device Configuration/SNMP tab (or
  fleet SNMP detail) with short-lived per-session result feedback; device facts
  show Last error. Unlock validates same-site `next`, preserves workflow IDs and
  reports success/wrong password. Header unlock link also carries safe context.
- Traffic uses separate complete `exporter_choices`, not the top-12 list. Choices
  merge current senders, saved DISTINCT exporters in the period, pending rows and
  selected zero-record sender. Independent lookup survives raw-query truncation;
  failure is visible/sanitized. Existing 200,000-row analysis bound is unchanged.
- `web_workflow_ux.py` + `web_ops.py`: role-aware next step/status/change-target
  summary, readable path/proposal/reviewed-intent tables, closed technical details,
  device suggestions, safer stale controls and inline unlock/return. Targets are
  NOT a complete impact assessment. Existing frozen proposal, approval, execution,
  verification/recovery authority and no-I/O rendering are unchanged.
- Validation: 204 related tests PASS (10 modules; 5 deliberately deselected:
  Windows POSIX-mode first-admin assertion and separate qualification-runner gates).
  Legacy selftest ALL PASS. Initial new-test failures were corrected harness
  assumptions (session replacement and header-vs-inline next links); final run green.
  Browser fake-data light/dark, summaries/details and real unlock/return verified.
  Final wording/anchor source follow-up rechecked: 204 PASS / 5 deselected in
  150.81 s. 98 runtime/selftest Python files plus new regressions compile in
  memory. Ruff: 0 new findings, 9 retained baseline findings in this checked set.
  No accidental private-key/access-token signatures or temporary source files
  found in the checked changes. Temporary browser preview is closed/stopped.
  Real PostgreSQL, live devices, AlmaLinux RPM upgrade/service and LIVE_RC NOT_RUN.
- Source metadata regenerated; package remains `2.0.0-67.2`, status
  `IMPLEMENTED_TESTING_DEFERRED`. Existing root RPM is stale and excludes both
  this work and the Oct 22 flow-history changes. No new artifact is claimed.
- Backups/proof: `C:\Users\mattlai\AppData\Local\Temp\netconfig-workflow-fix-00d7577cc87046118ad5398cc6ac1f65`.
- Next: user-selected RPM build/release identity and isolated AlmaLinux/PostgreSQL
  verification. Do not redo baseline analysis or create MC-12.

## NetFlow 24-hour PostgreSQL history — 2026-10-22

User explicitly requested database-backed NetFlow retention. This supersedes
earlier descriptions of NetFlow as memory-only; it does not merge the separate
October 7 sensor-history lineage or add MC-12. Package identity is unchanged.

- `netflow_history.py`: dedicated `netconfig_flow_history` PostgreSQL table;
  receive timestamp, exporter, IPv4/IPv6 endpoints, ports, protocol, packet/byte
  counters and retry-stable UUID. Indexes on time and exporter/time. Numeric
  counters preserve unsigned 64-bit values. Core DB/schema identity unchanged.
- `netflow_history_enabled` defaults true. Uses existing History PostgreSQL
  connection keys/legacy DSN and `__pg_history__` vault password independently
  of `if_history_enabled` and `if_history_hours`. No duplicated credentials.
  Settings → NetFlow exposes enable/status; restart to activate changes.
- UDP receive stays DB-free. One worker batches 500 rows with a 20,000-record
  volatile queue; timeout/retry and UUID conflict handling avoid double writes.
  Queue rejects, expired pending rows, pending/saved counts and sanitized
  read/write/maintenance errors appear in Traffic and device views. Recovery
  refreshes vault credentials; missing schema can be retried after a write error.
- Logical reads always exclude records older than 24 h. Worker cleanup runs even
  without incoming flows, normally every 60 s, deleting 10,000 expired rows per
  transaction and speeding retries during backlog. Physical deletion can lag;
  disk space is not a fixed quota or guaranteed immediate reclamation.
- Global Traffic and device Traffic prefer committed history plus pending rows
  deduplicated by UUID; they never add the memory ring to DB totals. DB read
  failure explicitly falls back to the ring. Restarted collectors can read old
  saved exporters even before new datagrams arrive. The displayed period is a
  query range, not a claim of uninterrupted collection.
- One analysis reads at most 200,000 newest saved rows, plus bounded pending;
  results are explicitly marked incomplete at that limit. Filter to a shorter
  period/exporter; older records remain stored until expiry. IP/service filtering
  runs after this bound. Raw display remains latest 100. No new rollup warehouse.
- Receive-time rate estimates, port-based service guesses, UDP/template loss and
  cross-exporter duplicate observations are unchanged. A hard stop/prolonged DB
  outage can lose queued flows; no disk spool or historical backfill is claimed.
  Graceful shutdown drains multiple batches within a short budget.
- Validation: **136 PASS / 1 SKIP** focused/related regressions, selftest ALL
  PASS, 93 Python files compile in memory. Ruff: 0 new findings; 8 pre-existing
  findings remain in the checked set. Real PostgreSQL/AlmaLinux qualification
  remains NOT_RUN; isolated SQLite SQL-bridge tests are not PostgreSQL evidence.
  An opt-in `tests/integration/test_netflow_history_postgres.py` gate uses
  `NETCONFIG_TEST_FLOW_PG_DSN` and an isolated temporary schema.
- Existing project-root RPM predates this change and does NOT include it. No
  new RPM/version/Git synchronization or production deployment is performed.
  Status remains `IMPLEMENTED_TESTING_DEFERRED`; source metadata regenerated.
  Proof/backups: `C:\Users\mattlai\AppData\Local\Temp\netconfig-flow24-21ca8b20d4aa41f99b7db186fdf6ee0d`.

## RPM installation build — 2026-10-22

At the user's explicit request, built the current canonical source into
`netconfig-2.0.0-67.2.el10.noarch.rpm` **without increasing the version**.
The user reports their installed version is older and explicitly wants
`dnf upgrade`; use that command for the delivered local package. If a future
host already has the same EVR installed, upgrade will not replace it and an
explicit reinstall would be required; no Epoch/version trick was introduced.

- Source: `C:\Users\mattlai\Projects\netconfig`, including the current Web UX,
  security-policy, NetFlow and operator-wording work. The separate October 7
  sensor-history-rollup ZIP was **not merged**; its missing-from-current-tree
  history changes remain unresolved and are not claimed to be in this RPM.
- Builder: existing dependency-free offline RPM tool, not Linux rpmbuild.
  Package identity remains `2.0.0-67.2.el10.noarch`; the source spec is unchanged.
- Output: project-root RPM, 519551 bytes, 113 payload entries.
  SHA-256: `ebe868756cf78b9ebecb6fd883849daf0ee27e21b31ff18cb9c720ce4dcded56`.
- Independent verifier PASS: package headers/digests, payload/source bytes,
  permissions, scriptlets, dependencies and config noreplace flags. Two builds
  with the same epoch `1792660193` are byte-identical. Launcher is LF-normalized
  and executable; existing data/vault contents are not shipped in the payload.
- Focused local regression: **109 PASS / 1 Windows-host-limited failure**.
  `test_first_admin_setup_with_one_time_code` stops at its POSIX 0600 assertion
  because Windows reports 0666; production code still creates/chmods 0600.
  No assertion was weakened, and this is not reported as a full-suite PASS.
  Legacy selftest: **ALL PASS**.
- RPM is unsigned. AlmaLinux RPM/DNF install-upgrade, systemd/SELinux, live
  PostgreSQL/devices and LIVE_RC gates are **NOT_RUN**, not inferred from offline
  verification. Status stays `IMPLEMENTED_TESTING_DEFERRED`.
- Source release metadata/SBOM is regenerated for the handover change; this is
  not candidate freeze or production-release promotion. No Git operations.
- External build/rebuild proof:
  `C:\Users\mattlai\AppData\Local\Temp\netconfig-rpm-install-20261022-92f9e3e97e404cbd875a8727aa21777b\build-result.json`.

## Console usability round — 2026-10-18

Source-only UX work; no schema or network-write authority change. Status stays
`IMPLEMENTED_TESTING_DEFERRED`.

- `web_ux.py` (`WebUxMixin`, first in `Console` bases) now owns `_page`, `_nav`,
  `_topright`, `_login_page`, `_dashboard` (Devices home), `_device_form`,
  `_audit_page`, `_runs_page`, plus `/search`, `/device-import`, `/device-test`
  and `/setup-admin`. Keep web.py under the PH-1 gate by adding new screens there.
- Shared client behavior is in `UX_JS` (sortable/filterable tables, tabs, phone
  menu, device-form credential modes, connection test); everything is nonce'd,
  with no inline handlers or style attributes added.
- Dashboard (`web_mc9._network_glance`) is network-first; correlation sections
  render only when non-empty; engine health sits in a closed `<details>`.
- `Manager.test_device_connection()` is the only new device I/O and runs only on
  an explicit approver/admin request; it stores nothing besides normal SSH
  host-key pinning.
- First-admin setup code: `web_ux.ensure_setup_code()` (log + 0600 file, 24 h).
- Next: unchanged — choose release identity, freeze a candidate, run the twelve
  LIVE_RC gates.

## Security policy fixes and NetFlow traffic analytics — 2026-10-17

Source-only corrective on top of the operator-wording refresh; no schema, route
removal or network-write authority change. Status stays `IMPLEMENTED_TESTING_DEFERRED`.

- API protocol-profile writes need approver/admin; `debug:create`/`debug:admin`
  scopes need admin and over-role scopes are dropped at token verification;
  console/CLI passwords need 12+ characters (`users.validate_password`).
- NetFlow: v9 IPv6 decoding; `netflow.analyze_traffic()` (direction-aware,
  port-based services, 5-tuple sessions, interval-aligned avg/peak);
  `netflow_max_flows` default 10000; optional `netflow_resolve_names`
  background reverse-DNS cache (`netflow.REVERSE_DNS`).
- UI: `/traffic` and the device NetFlow section render through
  `web_traffic.py` (Sources/Destinations/Services/Conversations/Exporters,
  drill-down, throughput chart). Keep bars as SVG geometry (CSP forbids style
  attributes) and keep host names escaped.
- Next: unchanged — choose release identity, freeze a candidate, run the twelve
  LIVE_RC gates. IPFIX decoding remains unassigned future scope.

## Operator-facing wording refresh — 2026-10-17

The English console now uses task-oriented labels and instructions rather than
internal release/slice codes and implementation wording. Coverage includes
Dashboard, alerts/events, SNMP/MIB, service dependencies, integrations, database
and monitoring settings, diagnostics/traces, and Operations/change workflows.
Only display strings and generated human-readable workflow summaries change;
routes, form names/values, settings keys, DB schema, machine-readable API fields,
role/CSRF checks, approval and device-I/O behavior are unchanged. Raw diagnostic
records, protocol identifiers and developer/historical documents retain their
precise technical terms. This is not a global replacement of stored/user data.

Validation: **119 PASS** (including **18 new console-copy page checks**); legacy
selftest **ALL PASS**; **14 changed/new Python files compile**; **10 runtime
modules retain identical non-text AST and machine-facing fields**. Ruff adds
**0 new findings**; 10 existing findings remain. Three qualification/platform
cases were deliberately deselected, not counted as PASS. No Git operations,
RPM build/install, browser visual acceptance or LIVE_RC execution were performed.

Release identity stays `2.0.0-67.2`, state `IMPLEMENTED_TESTING_DEFERRED`. The
current source bytes changed: earlier candidate hashes/manifests/SBOM do not
qualify this update. Regenerate them at the next user-approved candidate freeze
and run the required LIVE_RC gates; no new feature phase or release is declared.

Work only in `C:\Users\mattlai\Projects\netconfig`. Current continuation
is candidate identity/freeze and qualification, not another feature slice.
Preserve the prior Web-control and workspace corrections below. One existing
documentation regression assumed the R67.2 heading was the second line; it
now checks the maintained canonical declaration instead of document order,
retaining release, deferred-status and session-security assertions.
Original affected files and generated patch/validation evidence are under
`C:\Users\mattlai\AppData\Local\Temp\netconfig-ui-wording-20261017-2d3h11po`.

## Workspace reconciliation — 2026-10-16 (current entry point)

Work only in `C:\Users\mattlai\Projects\netconfig`. The old chat/App launch cwd
`C:\Users\mattlai\Documents\ChatGPT\dev project` was never switched when the user
selected this root on 2026-08-18. Do not confuse launch cwd with the explicit source
workdir, or create another full source tree when approval is needed.

The first verified post-selection alternate-tree product edits occurred on
2026-10-15 in `netconfig-web-controls-20261015`. They were promoted to this root
on 2026-10-16. Before this reconciliation, all **468/468 non-cache staged files**
matched the canonical source; no missing staged changes were found. The redundant
tree is retired recoverably, not merged over current files. Earlier August edits
after the root selection targeted this canonical tree. Full chronology and
recovery locations: [workspace audit](WORKSPACE_AUDIT_2026-10-16.md).

Windows tests now use `tools/run_windows_source_tests.py`, anchored to its owning
tree even when invoked from another cwd. Optional pytest dependencies are supplied
with `NETCONFIG_TEST_DEPENDENCIES`, not a hardcoded old workspace import path.
The POSIX PTY guard fails closed; Windows results do not qualify real SSH/Linux.

Preserve the five Web UI corrective features and their recorded validation below.
Next product action remains release identity, candidate freeze/metadata regeneration,
then the twelve mandatory LIVE_RC gates, not a new feature slice or a rollback to
historical baseline ZIPs. This reconciliation changes developer tooling/docs only;
it does not declare a new release, rebuild an RPM or run live qualification.
No Git operations. The App's shared-project binding is still old; current tools
cannot change that source-folder association, and other chats must not be repointed.

Reconciliation validation: **51 PASS** (3 new runner + 45 Web controls + 3 existing
source/structure checks); legacy selftest **ALL PASS**; runner/test compile **2/2**
and focused Ruff **PASS**. Rechecked 468 original file hashes: **0 unexpected
changes**; product runtime unchanged. Initial shared-Temp setup errors were
resolved using a new unique test directory, not a product fix. Recovery paths and
limitations are recorded in the audit. Evidence: 2026-10-16 09:43:43 UTC+8 (Taiwan).

## Web UI control coverage corrective — 2026-10-16

The R67.2-based working tree now closes five console coverage gaps. Status remains `IMPLEMENTED_TESTING_DEFERRED`; package identity remains `2.0.0-67.2` pending the user's release decision.

- **Users:** admins can enable, disable and delete accounts from `/users`. Console changes protect the current account and the last enabled admin; SQLite transactions and a PostgreSQL transaction advisory lock serialize access changes. Existing managed sessions reject deleted/disabled accounts on their next request. Password-reset inputs are masked.
- **Device Collection:** approvers/admins can remove a saved protocol profile; inventory and vault secrets are retained and default collection is restored. Operators and above can explicitly run Capabilities, Read state and bounded gNMI Subscribe once. Collection now checks the existing `collect` capability. Page loads do not initiate protocol I/O.
- **Diagnostics:** admins can create full or per-device captures, request a signature, verify archive signature/trust, view effective signing status and clean up older managed bundles with a minimum keep count of one. Signature validity and trusted-signer status are displayed separately. Device captures create their missing security subdirectory; cleanup uses file modification time across full/device archive prefixes.
- **Settings → Evidence signing:** admin-only policy controls for `evidence_signing_required` and `evidence_trusted_fingerprints`; validated/normalized SHA-256 pins are saved only after all inputs pass. Environment policy overrides remain visible and environment-added pins are not copied into settings. Private keys remain outside the Web UI.
- **Protocol Traces:** standalone `/traces` navigation, device/status filters, session detail and bounded event view. Operators and above can start/stop captures with TTL/event/byte budgets and optional Incident linkage. Viewers can read but cannot capture.

All new console POST routes use session authentication, existing role checks and CSRF protection. Network configuration writes remain behind the existing approval chain; no schema or public bearer-REST contract changes are introduced. `web_feature_controls.py` holds the additional controls and preserves the PH-1 `web.py` structural limits.

Console routes added: `POST /user-access`, `/protocol-delete`, `/protocol-inspect`, `/debug-verify`, `/debug-cleanup`, `/trace-start`, `/trace-stop`; `GET /traces` lists/details existing trace sessions. Existing `POST /debug-create` now accepts `mode=full|device`, `device` and optional `require_signature=1`. Existing `POST /settings-save` accepts `section=evidence`. These remain browser-session routes, not new bearer-token API endpoints.

Validation on the Windows development host: **131 PASS** across **45 new HTTP/role/CSRF/access-lifecycle cases** and **86 related existing regressions**. Three pre-existing POSIX/qualification-runner cases were reproduced against the unmodified working folder and excluded from this compatible run; they require the appropriate runtime. Ten existing OpenSSL signing cases were skipped in the earlier expanded run because OpenSSL was not exposed to that runner. The Windows test harness supplies only a fail-closed `pty` import shim; any real POSIX SSH attempt raises rather than simulating success. This is source/local HTTP evidence, not live AlmaLinux, PostgreSQL concurrency, device interoperability, browser acceptance or cryptographic-signing qualification.

Generated manifests, SBOM and artifact hashes remain pending regeneration for the next frozen candidate. Earlier candidate fingerprints do not qualify these changed bytes. No new version, MC slice or production release is declared. Git remains user-managed.

Additional completed local checks: legacy selftest **ALL PASS** (including Application-only isolation and System-only regression), six changed runtime modules compile, and the existing canonical-state, compound-statement and PH-1 structure checks **3/3 PASS**. Selftest uses the same fail-closed Windows PTY import harness; this is not live SSH evidence.

Active continuation: finish candidate identity/freeze and execute required LIVE_RC gates. The 2026-10-13 documentation-only pass below is historical; this corrective includes runtime and regression-test changes. Do not infer that the entire CLI/settings surface has been re-audited from closure of these five reported gaps.

<!-- documentation-sync: 2026-11-05 -->
> **Canonical project state — 2026-11-05:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.8 / Enable Credential Precedence Corrective RPM** (`2.0.0-67.8`, `IMPLEMENTED_TESTING_DEFERRED`). When a Web-managed vault secret is both the SSH and enable reference, NetConfig now sends its explicit `enable_password` instead of incorrectly overwriting it with the SSH login password; separate Enable secrets remain supported. Release 67.7 legacy `ssh-rsa`/SHA-1 verification, managed known_hosts, the RSA 512-bit floor and normal-device OpenSSH isolation remain. Prior SNMPv3, Endpoint CSV, history/evidence/workflow corrections are preserved. **MC-11 Topology-Aware Change Planning** remains the final feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** and schema `mc11-topology-change-planning-1` remain. **Do not create MC-12.** Local regression does not replace live Cisco/AlmaLinux qualification. All twelve LIVE_RC gates and an explicit R68 decision remain required. Git stays user-managed.

> **Document applicability:** this document is maintained against [ROADMAP.md](ROADMAP.md) and [AI_HANDOFF.md](AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Active continuation — 2026-10-13

Continue from the current working tree on R67.2 plus the 2026-09-29 Vendor Profile framework and 2026-10-09 Web UI/NetFlow corrective. No new version has been selected. Do not reuse the old candidate fingerprint or manufacture a live PASS. Resolve release identity, freeze the candidate and execute the twelve LIVE_RC gates before R68 review. No new feature-development phase is assigned; MC-11 is final.

Current source has `/snmp` profile administration, indexed host lookup, bulk topology facts joins, exporter/template diagnostics and Application-only isolation. Preserve System/Network/mixed-type management behavior. Session idle/absolute expiry is already implemented in `web_security_runtime.py` (30 minutes / 12 hours); older deferred-expiry notes are historical. IPFIX decoding, SNMPv3 traps/INFORM, NETCONF base:1.1-only framing and Site Edge/Collector are unassigned future scope.

This handover pass changes Markdown only. It does not rerun full product tests or live gates. Historical 556/542/14 source-test counts belong to the September Vendor Profile checkpoint; the October ledger records nine new focused tests and reports a green suite without an exact new aggregate. Do not combine or invent totals. Any changed packaged Markdown also changes artifact bytes and requires metadata/artifact regeneration before qualification.

Git synchronization and history remain user-managed. Do not run Git commands without explicit current-chat authorization. Completion feedback after a documentation-stage update must end with Taiwan time (UTC+8).

## Web UI feature-coverage & NetFlow usability corrective — 2026-10-09

Corrective maintenance on top of the SNMP Vendor Profile working tree; no schema or public REST contract change, no new network-write authority, release/package identity intentionally not advanced. Status stays `IMPLEMENTED_TESTING_DEFERRED`.

- Re-applied two hot-path performance fixes a prior ZIP rebuild had reverted: `Inventory.get_by_host()` backs `Manager.device_by_host()` (no per-packet full scan on syslog/trap ingestion), and `Manager._inventory_with_sysname()` replaces the topology N+1 with a single bulk `all_facts()` join.
- Closed the SNMP vendor-profile **web** gap: the `/snmp` page now lists loaded profiles and lets `manage_devices` operators upload/validate, reload, and remove operator-installed profiles (built-in profiles read-only), mirroring the MIB library. Renderer lives in `web_ui.py` so web.py stays under the PH-1 structural-split gate.
- Made received NetFlow meaningful on the device page: `render_netflow_section` now distinguishes exporter-IP mismatch (lists real exporters, points to `/traffic`), datagrams-without-decoded-flows (awaiting v9 template / IPFIX not decoded), and nothing-received, instead of a blanket "no flows" note. The global `/traffic` page already aggregated across exporters.
- Added `tests/test_vendor_profile_web_admin.py` and `tests/test_netflow_device_diagnostics.py`; regenerated SBOM/RELEASE_MANIFEST; full suite green; no new ruff findings.

## Recorded engineering checkpoint — 2026-09-29

The active working tree is an **unnumbered corrective development update on top of the refrozen R67.2 source line**, implementing the data-driven SNMP Vendor Profile framework. Project roadmap state remains `IMPLEMENTED_TESTING_DEFERRED`. The release/package identity has intentionally not been advanced; do not invent R67.3/R67.2.x or promote R68 without the user's explicit decision.

**Recorded 2026-09-29 vendor-profile source evidence:** **556 collected / 542 PASS / 14 SKIP / 0 FAIL** across 12 bounded groups; focused Vendor Profile framework coverage is **8 PASS / 0 FAIL**; `compileall`, actual launcher `py_compile`, packaging/tool/qualification shell syntax, release-metadata check, and legacy selftest are PASS. The 14 skips remain explicit live PostgreSQL/protocol-service prerequisites plus the expected source-archive Git-metadata prerequisite. These are local/source gates only and do not promote the working tree beyond `IMPLEMENTED_TESTING_DEFERRED`.

The prior refrozen exact R67.2 source ZIP had SHA-256 `b93084d7e2af9be4de234ceb6e21f147332a4e696970a0d829812de22a841559`. This working tree changes runtime/package bytes, so prior exact-candidate fingerprint `dd8524faf97f889992b5f84cfdb4eb47e2d6a8e4aa5be842f3f4b29022ccafda` and candidate-bound LIVE_RC evidence do not qualify the new bytes.

## SNMP Vendor Profile architecture

- `opt/netconfig/netconfig/vendor_profiles.py`: JSON-only profile validation, registry, matching, reload, bounded table/scalar normalization. No executable profile content is permitted.
- Search precedence: `/usr/share/netconfig/snmp-profiles` -> `/etc/netconfig/snmp-profiles` -> `$NETCONFIG_HOME/snmp-profiles` -> optional `NETCONFIG_SNMP_PROFILE_PATH` directories.
- `usr/share/netconfig/snmp-profiles/fortinet.fortigate.json`: first packaged profile. It collects bounded FortiGate system, security DB, hardware, processors, VDOM, interface extension and VPN branches. Firewall policy and HA branches are intentionally excluded.
- `manager.py::_poll_vendor_mibs()`: matching declarative profile wins; otherwise legacy bounded MIB-root behavior remains.
- Profile normalization writes canonical Sensors with source `vendor-profile:<id>/<mapping>` and prunes stale profile-owned resources.
- `web.py`: generic read-only Vendor profile telemetry panel from persisted Sensors; raw OIDs remain Advanced.
- `cli.py`: `snmp profiles`, `snmp profile-reload`, `snmp profile-validate`, `snmp profile-install`, `snmp profile-remove`.
- RPM spec/offline builder package default profiles under `/usr/share/netconfig/snmp-profiles`.

No DB schema change. No REST mutation surface. Existing `GET /api/v1/sensors` automatically exposes normalized vendor Sensors under existing auth/filter semantics. No change to the request -> approval -> frozen snapshot -> execution-time revalidation -> execute -> verify -> audit network-write chain.

## Roadmap truth

MC-11 remains the final Monitoring / Correlation / Change-Planning functional slice. Do not create MC-12. R68 remains a release-decision step only after a new exact candidate is frozen and all mandatory LIVE_RC gates are executed against those exact bytes.

## Qualification rules

Count only completed tests. Timeouts/partial output are not PASS. Local/offline fake/simulation evidence never substitutes for live device/PostgreSQL/AlmaLinux/HA gates. Keep `DEVELOPMENT.md`, `ROADMAP.md`, `TESTING.md`, `SECURITY.md`, `ARCHITECTURE.md`, `DEPLOYMENT.md`, `WEBGUI.md`, `README.md`, `DOCUMENTATION_STATUS.md`, this file, and the focused SNMP profile document synchronized whenever this work changes.

## 2026-10-13 documentation validation result

Markdown inventory/applicability: **67/67 PASS** (54 maintained, 13 historical). Canonical-state consistency: **PASS**, executing the existing `test_release_67_rc_canonical_truth_is_consistent` assertion function directly. The pytest runner was **NOT_RUN** because the installed Python has no pytest module; direct assertion execution is not reported as a pytest-suite result. Local Markdown links and fenced-code balance pass the documentation audit. All **399 non-Markdown files** checked before/after synchronization are byte-unchanged. No Git operations, full product regression, RPM build or LIVE_RC gates were executed. Original Markdown is recoverable from the external temporary backup created for this sync.
