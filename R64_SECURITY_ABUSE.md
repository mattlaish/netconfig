# R64 — Security Hardening & Independent Abuse Testing

Status: **IMPLEMENTED_TESTING_DEFERRED**.

R64 hardens existing NetConfig boundaries without adding device-write authority or a new Monitoring / Correlation / Change-Planning slice. MC-11 remains final and its candidate what-if path remains read-only.

Implemented local hardening includes bounded login-throttle identity cardinality; bounded/expiring web sessions with authoritative per-request user-role, disable, and password-reset revalidation; strict request framing and body limits; bounded multipart MIB uploads; generic external 500 responses; public-Microsoft-cloud OAuth authority pinning, tenant validation, redirect refusal and response limits; and streaming signed-archive verification that rejects non-file/non-directory members before dangerous archive materialization.

The fixed-hook R64 campaign separates `LOCAL_REGRESSION`, `LOCAL_ABUSE`, and `LIVE_ABUSE`. Local evidence is not an independent production security assessment. `production_security_claim` can become true only when every required `LIVE_ABUSE` gate passes on the designated target environment. The runner never promotes the release to TESTED or RELEASED.

## R64 current verification truth

Source-tree regression: **498 collected / 484 PASS / 14 SKIP / 0 FAIL**. R64 focused: **21/21 PASS**. MC-11 focused: **12/12 PASS**. Security/compatibility focused set: **102 PASS / 1 expected no-.git SKIP / 0 FAIL**. Initial selected R64 campaign: **6 local PASS / 0 FAIL / 12 BLOCKED_ENVIRONMENT / 0 NOT_RUN / 0 LIVE_ABUSE PASS**; `production_security_claim=false`. The runner all-local nested full-regression invocation exceeded the surrounding execution envelope, so the full regression was executed separately with the same deterministic five-group partition and recorded in the evidence bundle; this does not change its `LOCAL_REGRESSION` class.
