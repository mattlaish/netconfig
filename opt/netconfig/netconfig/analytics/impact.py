"""NI-6.5 Impact Simulation foundation.

Deterministic topology impact simulation. This module only produces simulation
observations and insights; it never executes network actions.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable, Mapping


@dataclass(frozen=True)
class ImpactObservation:
    tenant_id: str
    source_object: str
    affected_object: str
    object_type: str
    relationship: str
    depth: int
    confidence: float
    evidence_refs: tuple[str, ...]
    observed_at: str


class ImpactSimulator:
    """Bounded dependency traversal for operational what-if analysis."""

    def simulate(self, tenant_id: str, source_object: str,
                 links: Iterable[Mapping[str, object]],
                 endpoints: Iterable[Mapping[str, object]] = (),
                 max_depth: int = 5) -> list[ImpactObservation]:
        if max_depth < 0:
            raise ValueError("max_depth must be non-negative")
        graph: dict[str, set[str]] = {}
        for link in links:
            # Direction is intentional: operational impact is downstream traversal,
            # not generic physical connectivity. When topology-resolution metadata
            # is present, fail closed unless the edge is a resolved managed neighbor.
            if "managed_neighbor" in link and not bool(link.get("managed_neighbor")):
                continue
            if "resolution_state" in link and str(link.get("resolution_state") or "").upper() not in {"", "RESOLVED"}:
                continue
            src = str(link.get("source", link.get("device", "")))
            dst = str(link.get("target", link.get("neighbor_device", "")))
            if src and dst:
                graph.setdefault(src, set()).add(dst)

        now = datetime.now(timezone.utc).isoformat()
        seen = {source_object}
        queue = [(source_object, 0)]
        result: list[ImpactObservation] = []
        while queue:
            node, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for child in sorted(graph.get(node, ())):
                if child in seen:
                    continue
                seen.add(child)
                queue.append((child, depth + 1))
                result.append(ImpactObservation(
                    tenant_id=tenant_id,
                    source_object=source_object,
                    affected_object=child,
                    object_type="DEVICE",
                    relationship="TOPOLOGY_DOWNSTREAM",
                    depth=depth + 1,
                    confidence=0.9,
                    evidence_refs=(f"topology:{node}->{child}",),
                    observed_at=now,
                ))

        known = {str(e.get("device_id", "")): e for e in endpoints}
        for device_id, endpoint in known.items():
            if device_id in seen:
                result.append(ImpactObservation(
                    tenant_id=tenant_id,
                    source_object=source_object,
                    affected_object=str(endpoint.get("id", device_id)),
                    object_type="ENDPOINT",
                    relationship="ATTACHED_ENDPOINT",
                    depth=1,
                    confidence=0.85,
                    evidence_refs=(f"endpoint:{device_id}",),
                    observed_at=now,
                ))
        return result

    def to_insight(self, source_object: str, observations: Iterable[ImpactObservation]) -> dict:
        items = list(observations)
        return {
            "type": "DEPENDENCY_IMPACT",
            "object_id": source_object,
            "severity": "WARNING" if items else "INFO",
            "confidence": min(0.99, max((x.confidence for x in items), default=0.0)),
            "affected_objects": len(items),
            "summary": "Dependency impact simulation result",
            "evidence": [asdict(x) for x in items],
        }
