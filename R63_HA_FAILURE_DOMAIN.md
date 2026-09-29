# R63 — HA / Failure-Domain Engineering

> **Canonical project state — 2026-09-25:** **CURRENT IMPLEMENTATION BASELINE** = **Release 67.2 / R67.2 Fresh Database Bootstrap Hardening Corrective RC** (`2.0.0-67.2`, `IMPLEMENTED_TESTING_DEFERRED`) on top of the frozen R67 candidate. MC-1 through MC-11 remain implemented; **MC-11 Topology-Aware Change Planning** remains the final Monitoring / Correlation / Change-Planning feature slice and schema revision remains `mc11-topology-change-planning-1`; **NI-7 L3/VRF Path & Route Dependency Intelligence** remains included. R67.2 repairs fresh login, additive migration/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL configuration separation, and fresh PostgreSQL Core bootstrap without adding network-write authority. **All network mutation remains approval-gated; local/offline qualification does not establish RC or production release readiness; all required `LIVE_RC` gates remain mandatory. Do not create MC-12.** R68 must be rerun against the exact R67.2 candidate after mandatory live qualification.

## Implemented HA safety boundaries

R63 hardens coordination rather than inventing a second execution authority. PostgreSQL advisory locks remain the ownership primitive, but cached ownership is now bound to the live PostgreSQL session generation. A reconnect invalidates old in-memory ownership and requires a real lock reacquisition before work continues. A configured cluster node identity is additionally fenced with a dedicated PostgreSQL advisory lock so two live sessions cannot safely operate as the same node identity.

Each enabled control-plane process starts the singleton scheduler loops, but each pass must reacquire or revalidate its scheduler leadership lock. This allows a standby to take over after the prior leader disappears while preventing a process that lost its database session from continuing on stale leadership state. Database or network partition therefore fails closed for automation work.

Distributed work claims now carry a random `claim_token`, monotonic `claim_generation`, worker/node identity, and bounded lease. Completion and renewal require the exact live claim tuple. An expired `CLAIMED` row is moved to `RECOVERY_REQUIRED`; it is never silently reclaimed. Only work explicitly classified `replay_safe` can be manually requeued, and the next claim advances generation so a stale worker cannot complete an older attempt.

## Failure-domain readiness truth

HA readiness requires PostgreSQL, a valid local identity fence, at least two fresh ACTIVE nodes, and at least two distinct non-empty operator-declared failure domains. Merely running two processes on one host/rack/site does not establish HA readiness. R63 does not manage PostgreSQL leader election, replication, primary promotion, PITR, virtual-IP movement, or consensus; those remain responsibilities of the external PostgreSQL HA/platform layer.

## Qualification model

`qualification/r63_runner.py` uses only `PASS`, `FAIL`, `BLOCKED_ENVIRONMENT`, and `NOT_RUN`. Local regression is evidence of implementation behavior only. Live HA qualification uses fixed hooks and requires explicit `NETCONFIG_R63_LIVE_HA=1`; it covers multi-failure-domain membership, scheduler takeover, node failover, worker lease fencing, partial-job recovery, explicit safe replay, database failover, database network partition, stale advisory-lock handling, split-brain fencing, restart/rejoin, and drain/failover. No arbitrary shell command argument exists.

Until those live gates execute successfully on a real multi-node PostgreSQL-backed deployment, the supported release truth remains `IMPLEMENTED_TESTING_DEFERRED` and `production_ha_claim=false`.

## R63 verified clean-extract truth — 2026-09-24

The provisional source archive was extracted with system `unzip` and reproduced **477 collected / 463 passed / 14 skipped / 0 failed**. R63 focused coverage is **16/16 PASS** and retained MC-11 authority coverage is **12/12 PASS**. `compileall`, launcher/qualification `py_compile`, packaging/qualification/tool shell syntax, and legacy selftest are PASS. The provisional structural gate is **348 entries / 0 duplicates / 0 unsafe paths / 0 symlinks / CRC PASS / 348/348 byte+mode parity / 346/346 R63 source manifest / 347/347 whole-tree SHA256SUMS / 26/26 executable modes**. Two clean-extract helper RPM rebuilds are byte-identical to each other and to the source-tree RPM; independent verification passes. RPM SHA-256 is `1e2a40476c212d2ffe410d51ef1cd9b2fac3051fc96bf30789539be5bca4b60d`. This is local/offline artifact evidence only; live HA remains deferred.
