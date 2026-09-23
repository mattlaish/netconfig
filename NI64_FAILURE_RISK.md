# NI-6.4 Failure Risk Foundation

> **Historical evidence notice — 2026-09-20:** This file preserves evidence and decisions from its named historical release/date. The active implementation baseline is **Release 49 / MC-1 Sensor Integration Unification** (`2.0.0-49`, `IMPLEMENTED_TESTING_DEFERRED`). NI-7 remains the current feature baseline; historical counts and release-specific statements below are intentionally unchanged. Production AlmaLinux `rpmbuild`/DNF/systemd/SELinux and other deferred Q-1 live gates remain authoritative.

> **Current roadmap pointer — 2026-09-18:** This file is retained as historical evidence. The post-NI-7 roadmap review is complete and **no new development phase is currently assigned**. NI-7 remains the current feature baseline and Q-1 remains the open qualification track. Historical “next”, “planned”, or package-baseline statements below are chronology only and do not override current Release 44 truth.

Status: `IMPLEMENTED_TESTING_DEFERRED`

NI-6.4 adds a deterministic, evidence-backed failure-risk analyzer on top of normalized operational evidence. It is intentionally an analytics-only foundation and does not execute remediation.

## Implemented

- `FailureRiskAnalyzer`
- `FailureRiskSignal`
- `FailureRiskObservation`
- allow-listed normalized signal types:
  - `INTERFACE_ERROR_SPIKE`
  - `LINK_FLAPPING`
  - `TEMPERATURE_ANOMALY`
  - `PACKET_DROP_INCREASE`
  - `TELEMETRY_DEGRADATION`
- deterministic `NORMAL` / `WARNING` / `CRITICAL` state calculation
- bounded confidence output
- evidence reference preservation
- `FAILURE_RISK` NetworkInsight-compatible mapping
- tenant context is supplied by the caller and is not accepted from signal payloads

## Security boundary

The analyzer produces only observations and evidence-backed insight. It has no interface for device commands, shutdown, configuration changes, automated replacement, remediation, or approval bypass. Unknown signal types and unsupported severities fail closed.

## Deferred

- production-scale calibration of thresholds and confidence
- live vendor telemetry validation
- real-device failure correlation
- automatic API/UI surfacing of NI-6.4 insight
- any remediation workflow, which must remain behind existing operator/change/SOAR controls
