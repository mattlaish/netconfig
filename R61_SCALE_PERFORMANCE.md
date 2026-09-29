# R61 — Scale & Performance Qualification

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Purpose

R61 freezes feature growth and measures whether the existing NetConfig control plane remains bounded and operational as inventory, evidence, topology, incidents, correlation and operator load increase. It does not add device-write authority, a new MC slice, or a new correlation model.

## Capacity dimensions

The qualification matrix records measured workload and resulting latency/throughput/resource evidence for:

- managed device count and endpoint rows;
- L2 topology nodes/edges and NI-7 route observations;
- syslog events/second and SNMP traps/second;
- external evidence events/second;
- NetFlow v5/v9 records/second and a separate IPFIX v10 live gate;
- active incidents, incident evidence/timeline fan-in and correlation runs/minute;
- concurrent operators;
- CPU, RSS/RAM, database growth and ingest lag;
- correlation p50/p95/p99, API p50/p95/p99 and key WebUI render p50/p95/p99.

## Evidence classes

`LOCAL_REGRESSION` proves source invariants. `LOCAL_SYNTHETIC` exercises actual NetConfig SQLite persistence/services/HTTP paths in an isolated temporary home and is useful for regression comparison, but it is not production sizing. `LIVE_PRODUCTION` requires fixed-name hooks running on the declared AlmaLinux/PostgreSQL target and is the only evidence class that can support production capacity claims.

The runner uses only `PASS`, `FAIL`, `BLOCKED_ENVIRONMENT`, and `NOT_RUN`. It never promotes `TESTED` or `RELEASED`.

## MC-10 overload contract

MC-10 hard bounds remain authoritative: maximum facts per run, incident timeline scan, dependency edge/node/depth bounds, replay range and external payload limits are not relaxed for scale tests. R61 deliberately runs a local overload probe beyond the incident timeline bound and requires truncation/bounded processing. A production overload hook must likewise demonstrate bounded degradation rather than unbounded queue/memory growth.

## Local synthetic benchmark

`qualification/r61_benchmark.py` uses an isolated NetConfig home and actual product paths to seed devices, endpoint tables, L2 topology, NI-7 routes, syslog, normalized operational events, MC-8 external evidence, incidents, evidence fan-in, deterministic correlation, HTTP API requests and dashboard rendering. It also parses real NetFlow v5 records through `NetflowParser` and records process RSS and database-tree growth.

The benchmark explicitly sets `production_capacity_claim=false`. Its NetFlow result also sets `ipfix_v10_measured=false`; an IPFIX result must come from the dedicated live gate rather than being inferred from NetFlow v5/v9 behavior.

## Live hook contract

Run:

```bash
./packaging/r61-qualify.sh /path/to/evidence --include-local --live --hook-dir /path/to/r61-hooks
```

Hooks are fixed executable names from `R61_GATE_CATALOG.json`. The runner does not accept arbitrary shell commands. Each hook may write a bounded JSON result to `$NETCONFIG_R61_RESULT_PATH`, and receives `$NETCONFIG_R61_GATE_ID` and `$NETCONFIG_R61_REPO_ROOT`.

Exit codes are: `0` PASS, `20` BLOCKED_ENVIRONMENT, `21` NOT_RUN, anything else FAIL. Evidence must include actual workload counts, elapsed duration, percentile metrics where applicable, CPU/RAM/database observations and target identity. Secrets/tokens/communities/authorization values must not be written into hook output.

## Current truth

R61 implementation and local/offline regression can be completed on the development runner. AlmaLinux/PostgreSQL/live ingest/real operator-scale results remain separate until actually executed. The project remains `IMPLEMENTED_TESTING_DEFERRED` until required live evidence exists.

## Clean-extract qualification

**R61 clean-extract qualification (2026-09-24):** the provisional source artifact was extracted with system `unzip` and reproduced **435 collected / 427 passed / 8 skipped / 0 failed** across the deterministic five-way bounded partition; R61 focused coverage is **17/17 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, launcher/R61 `py_compile`, packaging/tool shell syntax, and legacy selftest are PASS. The clean extract rebuilt the offline helper RPM twice byte-identically; both builds are byte-identical to the source-tree RPM and pass the independent verifier. RPM SHA-256 remains `c1458d97a19ce0390f0c6f42384c652eed1704c47f57f41e11f0c95a11d2ed5b`. This is local/offline artifact evidence only and does not establish production capacity.
