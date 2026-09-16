"""NI-6.3 Capacity Analytics foundation.

Deterministic, evidence-backed capacity analysis. This module creates
observations and insights only; it never performs device actions.
"""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class CapacityObservation:
    object_id: str
    metric: str
    current_value: float
    baseline_value: float
    difference: float
    trend: str
    state: str
    confidence: float
    observed_at: str


class CapacityAnalyzer:
    """Compare current telemetry values against baseline evidence."""

    def analyze(self, object_id: str, metric: str, current_value: float,
                baseline_value: float, trend: str = "stable") -> CapacityObservation:
        difference = current_value - baseline_value
        ratio = 0.0 if baseline_value == 0 else difference / baseline_value

        # NI-6.3 contract: a sustained increase of at least 50% over baseline
        # is WARNING; reserve CRITICAL for a >=200% increase over baseline.
        # This keeps the documented 30% -> 85% example at WARNING while a
        # 30% -> 120% observation is CRITICAL.
        if ratio >= 2.0:
            state = "CRITICAL"
        elif ratio >= 0.5:
            state = "WARNING"
        else:
            state = "NORMAL"

        confidence = min(0.99, max(0.1, abs(ratio)))
        return CapacityObservation(
            object_id=object_id,
            metric=metric,
            current_value=current_value,
            baseline_value=baseline_value,
            difference=difference,
            trend=trend,
            state=state,
            confidence=confidence,
            observed_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_insight(self, observation: CapacityObservation) -> dict:
        return {
            "type": "CAPACITY",
            "object_id": observation.object_id,
            "severity": observation.state,
            "confidence": observation.confidence,
            "summary": f"{observation.metric} capacity state is {observation.state}",
            "evidence": asdict(observation),
        }
