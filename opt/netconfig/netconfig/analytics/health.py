"""NI-6.6 Network Health Dashboard foundation.

Aggregates operational evidence into a deterministic health view.
This module produces observations only and never performs remediation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable, Mapping


@dataclass(frozen=True)
class NetworkHealthObservation:
    tenant_id: str
    object_id: str
    availability_score: float
    stability_score: float
    capacity_score: float
    error_score: float
    overall_state: str
    confidence: float
    evidence_refs: tuple[str, ...]
    created_at: str


class HealthAnalyzer:
    """Deterministic operational health aggregation."""

    def analyze(
        self,
        tenant_id: str,
        object_id: str,
        *,
        availability: float = 100.0,
        stability: float = 100.0,
        capacity: float = 100.0,
        errors: float = 100.0,
        evidence_refs: Iterable[str] = (),
    ) -> NetworkHealthObservation:
        values = [availability, stability, capacity, errors]
        if any(v < 0 or v > 100 for v in values):
            raise ValueError("health scores must be between 0 and 100")
        refs = tuple(evidence_refs)
        average = sum(values) / len(values)
        if not refs:
            state = "UNKNOWN"
        elif average >= 85:
            state = "HEALTHY"
        elif average >= 60:
            state = "DEGRADED"
        else:
            state = "CRITICAL"
        confidence = min(1.0, max(0.0, len(refs) / 4))
        return NetworkHealthObservation(
            tenant_id=tenant_id,
            object_id=object_id,
            availability_score=availability,
            stability_score=stability,
            capacity_score=capacity,
            error_score=errors,
            overall_state=state,
            confidence=confidence,
            evidence_refs=refs,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_insight(self, observation: NetworkHealthObservation) -> dict:
        return {
            "type": "HEALTH",
            "object_id": observation.object_id,
            "severity": observation.overall_state,
            "confidence": observation.confidence,
            "summary": "Network operational health assessment",
            "evidence": [asdict(observation)],
        }
