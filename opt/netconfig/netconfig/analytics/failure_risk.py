"""NI-6.4 Failure Risk Foundation.

Deterministic, evidence-backed operational failure-risk analysis.  The module
produces observations and insights only.  It has no device execution,
configuration, remediation, or approval-bypass capability.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping


_ALLOWED_SIGNAL_TYPES = frozenset({
    "INTERFACE_ERROR_SPIKE",
    "LINK_FLAPPING",
    "TEMPERATURE_ANOMALY",
    "PACKET_DROP_INCREASE",
    "TELEMETRY_DEGRADATION",
})
_ALLOWED_SEVERITIES = frozenset({"INFO", "WARNING", "CRITICAL"})

# Base contribution from one WARNING-level signal.  Severity multipliers and
# source-diversity bonuses are applied by ``FailureRiskAnalyzer``.
_SIGNAL_WEIGHTS = {
    "INTERFACE_ERROR_SPIKE": 0.30,
    "LINK_FLAPPING": 0.30,
    "TEMPERATURE_ANOMALY": 0.25,
    "PACKET_DROP_INCREASE": 0.25,
    "TELEMETRY_DEGRADATION": 0.20,
}
_SEVERITY_MULTIPLIERS = {
    "INFO": 0.25,
    "WARNING": 1.0,
    "CRITICAL": 1.5,
}


def _bounded_text(value: object, limit: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


@dataclass(frozen=True)
class FailureRiskSignal:
    signal_type: str
    source_id: str
    severity: str
    observed_at: str
    metric: str = ""
    value: str = ""


@dataclass(frozen=True)
class FailureRiskObservation:
    tenant_id: str
    object_id: str
    risk_type: str
    signals: tuple[FailureRiskSignal, ...]
    severity: str
    confidence: float
    state: str
    evidence_refs: tuple[str, ...]
    observed_at: str


class FailureRiskAnalyzer:
    """Aggregate normalized operational signals into a failure-risk insight.

    Inputs are deliberately constrained to a small normalized schema.  Unknown
    signal types or severities are rejected rather than treated as arbitrary
    payloads.  This keeps the analytics boundary deterministic and fail-closed.
    """

    allowed_signal_types = _ALLOWED_SIGNAL_TYPES

    def _normalize_signal(self, raw: FailureRiskSignal | Mapping[str, object]) -> FailureRiskSignal:
        if isinstance(raw, FailureRiskSignal):
            signal = raw
        elif isinstance(raw, Mapping):
            signal = FailureRiskSignal(
                signal_type=_bounded_text(raw.get("signal_type"), 64).upper(),
                source_id=_bounded_text(raw.get("source_id"), 160),
                severity=_bounded_text(raw.get("severity", "WARNING"), 16).upper(),
                observed_at=_bounded_text(raw.get("observed_at"), 64)
                or datetime.now(timezone.utc).isoformat(),
                metric=_bounded_text(raw.get("metric"), 128),
                value=_bounded_text(raw.get("value"), 128),
            )
        else:
            raise TypeError("signal must be FailureRiskSignal or mapping")

        signal_type = signal.signal_type.upper()
        severity = signal.severity.upper()
        if signal_type not in _ALLOWED_SIGNAL_TYPES:
            raise ValueError(f"unsupported failure-risk signal type: {signal_type}")
        if severity not in _ALLOWED_SEVERITIES:
            raise ValueError(f"unsupported failure-risk severity: {severity}")
        if not signal.source_id:
            raise ValueError("failure-risk signal source_id is required")

        return FailureRiskSignal(
            signal_type=signal_type,
            source_id=_bounded_text(signal.source_id, 160),
            severity=severity,
            observed_at=_bounded_text(signal.observed_at, 64)
            or datetime.now(timezone.utc).isoformat(),
            metric=_bounded_text(signal.metric, 128),
            value=_bounded_text(signal.value, 128),
        )

    def analyze(
        self,
        *,
        tenant_id: str,
        object_id: str,
        signals: Iterable[FailureRiskSignal | Mapping[str, object]],
        observed_at: str | None = None,
    ) -> FailureRiskObservation:
        tenant_id = _bounded_text(tenant_id, 128)
        object_id = _bounded_text(object_id, 255)
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not object_id:
            raise ValueError("object_id is required")

        normalized = tuple(self._normalize_signal(item) for item in signals)
        now = _bounded_text(observed_at, 64) or datetime.now(timezone.utc).isoformat()

        if not normalized:
            return FailureRiskObservation(
                tenant_id=tenant_id,
                object_id=object_id,
                risk_type="FAILURE_RISK",
                signals=(),
                severity="INFO",
                confidence=0.10,
                state="NORMAL",
                evidence_refs=(),
                observed_at=now,
            )

        score = 0.0
        critical_count = 0
        unique_types: set[str] = set()
        evidence_refs: list[str] = []
        for signal in normalized:
            score += _SIGNAL_WEIGHTS[signal.signal_type] * _SEVERITY_MULTIPLIERS[signal.severity]
            unique_types.add(signal.signal_type)
            if signal.severity == "CRITICAL":
                critical_count += 1
            if signal.source_id not in evidence_refs:
                evidence_refs.append(signal.source_id)

        # Multiple independent signal classes increase confidence in a correlated
        # operational risk without making a causal claim.
        diversity_bonus = min(0.15, max(0, len(unique_types) - 1) * 0.05)
        score = min(1.0, score + diversity_bonus)

        if score >= 0.75 or critical_count >= 2:
            state = "CRITICAL"
        elif score >= 0.30:
            state = "WARNING"
        else:
            state = "NORMAL"

        if state == "NORMAL":
            severity = "INFO"
        else:
            severity = state

        # Confidence is intentionally bounded below 1.0: this foundation emits
        # operational evidence, not certainty or an autonomous remediation order.
        confidence = round(min(0.99, max(0.10, score)), 2)
        return FailureRiskObservation(
            tenant_id=tenant_id,
            object_id=object_id,
            risk_type="FAILURE_RISK",
            signals=normalized,
            severity=severity,
            confidence=confidence,
            state=state,
            evidence_refs=tuple(evidence_refs),
            observed_at=now,
        )

    def to_insight(self, observation: FailureRiskObservation) -> dict[str, object]:
        """Return an evidence-only NetworkInsight-compatible mapping."""
        return {
            "tenant_id": observation.tenant_id,
            "type": "FAILURE_RISK",
            "object_id": observation.object_id,
            "severity": observation.severity,
            "confidence": observation.confidence,
            "summary": f"{observation.object_id} failure-risk state is {observation.state}",
            "evidence": {
                "risk_type": observation.risk_type,
                "state": observation.state,
                "signals": [asdict(signal) for signal in observation.signals],
                "evidence_refs": list(observation.evidence_refs),
                "observed_at": observation.observed_at,
            },
        }
