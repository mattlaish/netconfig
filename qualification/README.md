# Q2 Production Qualification Campaign

<!-- documentation-sync: 2026-10-13 -->
> **Canonical project state — 2026-10-13:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) with unnumbered SNMP Vendor Profile and October Web UI / NetFlow corrective updates. **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included; schema `mc11-topology-change-planning-1` is unchanged. The working tree is not the previously frozen R67.2 candidate. Release numbering awaits an explicit user decision. Next: choose release identity, freeze a new candidate, execute all twelve mandatory `LIVE_RC` gates against its exact bytes, then perform R68 production release review. No new feature phase is assigned. All network mutation remains approval-gated. Local/source evidence does not establish production readiness. **Do not create MC-12.**

> **Document applicability:** this document is maintained against [ROADMAP.md](../ROADMAP.md) and [AI_HANDOFF.md](../AI_HANDOFF.md). Older release-numbered sections, test counts, fingerprints and Current/Next pointers below are historical unless explicitly restated in this 2026-10-13 update.

## Current candidate applicability — 2026-10-13

The current working tree includes corrective runtime and documentation changes after the R67.2 freeze. The earlier exact-candidate fingerprint and its live evidence do not qualify these bytes. Current source/spec release remains `2.0.0-67.2`; selecting a new release identity is pending explicit user decision.

The next campaign requires a newly frozen artifact, regenerated/verified metadata and all twelve mandatory LIVE_RC gates against that fingerprint, followed by R68 review. Q1/Q2 and R60–R66 tools/contracts remain reusable within their declared release-specific boundaries; older gate outcomes do not transfer automatically. Fresh SQLite login and PostgreSQL bootstrap, supported upgrade preservation, real exporter/vendor behavior, browser device-type/profile administration and R64 managed-session behavior belong in applicable candidate acceptance.

Documentation synchronization establishes no new runtime/live PASS and does not promote `IMPLEMENTED_TESTING_DEFERRED`.

This directory contains the repeatable qualification harness for the frozen NetConfig R59 / MC-11 product baseline (`2.0.0-59`, schema `mc11-topology-aware-change-planning-1`). It is **qualification tooling**, not a new MC feature slice and not a product execution path.

## Truth model

Every gate ends in exactly one of:

- `PASS` — the selected gate executed against the declared evidence class and passed.
- `FAIL` — the selected gate executed and failed.
- `BLOCKED_ENVIRONMENT` — the gate was selected, but required OS/tool/credential/target/hook infrastructure was unavailable.
- `NOT_RUN` — the gate was not selected for execution or a destructive gate was not explicitly authorized.

`LOCAL_REGRESSION` evidence never substitutes for `LIVE_PRODUCTION` evidence. The runner never changes project state to `TESTED` or `RELEASED`.

## Run

List the catalog:

```bash
python3 qualification/q2_runner.py --output-dir /tmp/unused --list
```

Run local baseline/regression gates only:

```bash
python3 qualification/q2_runner.py \
  --output-dir /var/tmp/netconfig-q2-local \
  --area baseline --include-local
```

Inventory the entire campaign in a non-destructive live attempt. Gates whose real target infrastructure or hook is unavailable become `BLOCKED_ENVIRONMENT`; destructive gates remain `NOT_RUN`:

```bash
python3 qualification/q2_runner.py \
  --output-dir /var/tmp/netconfig-q2-campaign \
  --include-local --live
```

On a disposable qualification appliance, add `--allow-destructive` only when install/upgrade/rollback/restart/reboot tests are intentionally authorized.

## Live hooks

Environment-specific live gates are implemented by exact executable files in `--hook-dir` (or `NETCONFIG_Q2_HOOK_DIR`). The runner executes only the predefined filename for each gate; it does not execute a caller-supplied shell command string.

Hook exit protocol:

- `0` = `PASS`
- `20` = `BLOCKED_ENVIRONMENT`
- `21` = `NOT_RUN`
- any other non-zero code = `FAIL`

The runner sets `NETCONFIG_Q2_GATE_ID`, `NETCONFIG_Q2_REPO_ROOT`, and `NETCONFIG_Q2_RESULT_PATH`. A hook may write a bounded JSON object to `NETCONFIG_Q2_RESULT_PATH` for metrics. Secrets must not be written there. Logs are redacted and bounded before being added to the evidence bundle.

Example hook contracts are under `qualification/hooks.example/`. They intentionally fail closed until the operator replaces the example logic with environment-specific qualification steps.

## Evidence bundle

Each run emits `campaign.json`, `SUMMARY.md`, per-gate JSON, bounded redacted stdout/stderr, and `SHA256SUMS`. Hostname, interface addresses, and the process environment are intentionally excluded from automatic host inventory. Credentials/tokens are never intentionally recorded.
## R67.2 corrective-RC campaign

`qualification/r67_2_runner.py` / `packaging/r67_2-qualify.sh` bind local and `LIVE_RC` evidence to the R67.2 fresh database/bootstrap corrective candidate. The fixed twelve live gates are unchanged in authority. R67.2 adds focused evidence for fresh HTTP login, SQLite/PostgreSQL migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History database separation, and the packaged fresh PostgreSQL bootstrap workflow. Live PostgreSQL/AlmaLinux/browser/device evidence remains mandatory and local regression cannot promote the candidate. Set `NETCONFIG_R67_2_LIVE_RC=1` only in the approved independent live qualification environment.
