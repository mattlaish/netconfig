"""NI-7 L3/VRF path and route-dependency intelligence.

Only explicit route observations are accepted.  The analyzer never maps a
next-hop IP to a managed device, never crosses VRFs, never chooses among
ambiguous multipath observations, and never performs a device mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass(frozen=True)
class L3PathObservation:
    source_device: str
    vrf: str
    destination_prefix: str
    status: str
    hops: tuple[dict, ...]
    route_ids: tuple[int, ...]
    stop_reason: str
    confidence: float


class L3RouteAnalyzer:
    """Deterministic, fail-closed traversal over explicit route evidence."""

    TERMINAL = "REACHED_TERMINAL"
    INCOMPLETE = "INCOMPLETE"
    AMBIGUOUS = "AMBIGUOUS"
    LOOP = "LOOP_DETECTED"
    UNMANAGED = "UNMANAGED_NEXT_DEVICE"
    MAX_HOPS = "MAX_HOPS_REACHED"

    @staticmethod
    def _same_route_key(row):
        return (
            str(row.get("next_hop") or ""),
            str(row.get("outgoing_interface") or ""),
            str(row.get("next_device") or ""),
            int(row.get("metric") or 0),
            bool(row.get("terminal")),
        )

    def simulate(
        self,
        source_device: str,
        vrf: str,
        destination_prefix: str,
        observations: Iterable[dict],
        managed_devices: Iterable[str],
        *,
        max_hops: int = 16,
    ) -> L3PathObservation:
        source_device = str(source_device or "").strip()
        vrf = str(vrf or "default").strip() or "default"
        destination_prefix = str(destination_prefix or "").strip()
        max_hops = max(1, min(int(max_hops), 64))
        managed = {str(x) for x in managed_devices}
        if not source_device or source_device not in managed:
            raise ValueError("source_device must be a managed device")
        if not destination_prefix:
            raise ValueError("destination_prefix is required")

        by_device: dict[str, list[dict]] = {}
        for raw in observations:
            row = dict(raw)
            if str(row.get("vrf") or "default") != vrf:
                continue
            if str(row.get("destination_prefix") or "") != destination_prefix:
                continue
            by_device.setdefault(str(row.get("device") or ""), []).append(row)

        hops: list[dict] = []
        route_ids: list[int] = []
        visited: set[str] = set()
        current = source_device

        for depth in range(max_hops):
            if current in visited:
                return self._result(source_device, vrf, destination_prefix, self.LOOP,
                                    hops, route_ids, f"loop at managed device {current}", 0.45)
            visited.add(current)
            routes = by_device.get(current, [])
            if not routes:
                return self._result(source_device, vrf, destination_prefix, self.INCOMPLETE,
                                    hops, route_ids, f"no explicit route observation for {current}", 0.35)

            # Identical duplicate observations do not create a forwarding choice;
            # any distinct forwarding signature is multipath ambiguity and stops.
            unique = {}
            for row in routes:
                unique.setdefault(self._same_route_key(row), row)
            candidates = list(unique.values())
            terminals = [r for r in candidates if bool(r.get("terminal"))]
            nonterminals = [r for r in candidates if not bool(r.get("terminal"))]
            if terminals and nonterminals:
                return self._result(source_device, vrf, destination_prefix, self.AMBIGUOUS,
                                    hops, route_ids,
                                    f"mixed terminal/non-terminal route evidence at {current}", 0.5)
            if len(candidates) > 1 and nonterminals:
                return self._result(source_device, vrf, destination_prefix, self.AMBIGUOUS,
                                    hops, route_ids,
                                    f"multipath route evidence at {current}; no path selected", 0.5)

            row = candidates[0]
            rid = int(row.get("id") or 0)
            if rid:
                route_ids.append(rid)
            hop = {
                "depth": depth,
                "device": current,
                "route_id": rid,
                "vrf": vrf,
                "destination_prefix": destination_prefix,
                "protocol": str(row.get("protocol") or ""),
                "next_hop": str(row.get("next_hop") or ""),
                "outgoing_interface": str(row.get("outgoing_interface") or ""),
                "next_device": str(row.get("next_device") or ""),
                "metric": int(row.get("metric") or 0),
                "terminal": bool(row.get("terminal")),
            }
            hops.append(hop)
            if bool(row.get("terminal")):
                return self._result(source_device, vrf, destination_prefix, self.TERMINAL,
                                    hops, route_ids, f"explicit terminal route at {current}", 0.95)

            next_device = str(row.get("next_device") or "").strip()
            if not next_device:
                return self._result(source_device, vrf, destination_prefix, self.INCOMPLETE,
                                    hops, route_ids,
                                    f"route at {current} has no explicit managed next_device", 0.4)
            if next_device not in managed:
                return self._result(source_device, vrf, destination_prefix, self.UNMANAGED,
                                    hops, route_ids,
                                    f"explicit next_device {next_device} is not managed", 0.4)
            current = next_device

        return self._result(source_device, vrf, destination_prefix, self.MAX_HOPS,
                            hops, route_ids, f"max_hops={max_hops} reached", 0.45)

    @staticmethod
    def _result(source_device, vrf, destination_prefix, status, hops, route_ids,
                stop_reason, confidence):
        return L3PathObservation(
            source_device=source_device,
            vrf=vrf,
            destination_prefix=destination_prefix,
            status=status,
            hops=tuple(hops),
            route_ids=tuple(route_ids),
            stop_reason=stop_reason,
            confidence=max(0.0, min(1.0, float(confidence))),
        )

    @staticmethod
    def to_insight(observation: L3PathObservation) -> dict:
        ok = observation.status == L3RouteAnalyzer.TERMINAL
        return {
            "type": "L3_PATH",
            "object_id": observation.source_device,
            "severity": "INFO" if ok else "WARNING",
            "confidence": observation.confidence,
            "summary": (
                f"L3 path {observation.status}: {observation.vrf} "
                f"{observation.destination_prefix}; {observation.stop_reason}"
            ),
            "evidence": {"path": asdict(observation)},
        }
