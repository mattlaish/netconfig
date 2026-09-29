"""MC-9 read-only operations correlation console aggregation.

This service is deliberately presentation-oriented.  It consumes persisted
NetConfig evidence plus the bounded in-memory NetFlow collector ring and never
initiates device I/O, external connector actions, or configuration changes.
"""

from collections import defaultdict
import time

from .netflow import summarize_flows


_ACTIVE_INCIDENT_STATES = {"OPEN", "INVESTIGATING"}
_CRITICAL_SEVERITIES = {"CRITICAL", "MAJOR", "ERROR", "HIGH"}


class OperationsCorrelationConsole:
    """Bounded DB/ring-read-only aggregation for the MC-9 console."""

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn

    def incident(self, incident_ref, *, timeline_limit=500):
        investigation = self.manager.incidents.investigation_view(
            incident_ref, max(1, min(int(timeline_limit), 2000)))
        hypotheses = self.manager.correlation.list(
            incident_ref, active_only=True, limit=100)
        current = hypotheses[0] if hypotheses else None
        investigation["hypotheses"] = hypotheses
        investigation["current_hypothesis"] = current
        investigation["root_cause"] = None
        investigation["root_cause_state"] = "NOT_CONFIRMED" if current else "NOT_EVALUATED"
        investigation["correlation_runs"] = self.manager.correlation_hardening.runs(
            incident_ref, limit=20)
        return investigation

    def dashboard(self, *, incident_limit=50, alert_limit=100, dependency_limit=500,
                  connector_limit=500):
        incident_limit = max(1, min(int(incident_limit), 200))
        incidents = [i for i in self.manager.incidents.list(limit=incident_limit * 4)
                     if i.get("status") in _ACTIVE_INCIDENT_STATES][:incident_limit]

        incident_rows = []
        impacted_services = {}
        correlated_changes = {}
        for incident in incidents:
            hypotheses = self.manager.correlation.list(
                incident["incident_key"], active_only=True, limit=100)
            current = hypotheses[0] if hypotheses else None
            incident_rows.append({
                "incident": incident,
                "current_hypothesis": current,
                "hypothesis_count": len(hypotheses),
            })
            for hypothesis in hypotheses:
                for entity in hypothesis.get("affected_entities") or []:
                    key = str(entity.get("entity_key") if isinstance(entity, dict) else entity or "").strip()
                    if not key:
                        continue
                    svc = self.manager.dependencies.get_entity(key)
                    if svc:
                        impacted_services[key] = svc
                for evidence in hypothesis.get("supporting_evidence") or []:
                    if not isinstance(evidence, dict):
                        continue
                    st = str(evidence.get("source_type") or evidence.get("type") or "").lower()
                    if st != "change_event":
                        continue
                    ref = str(evidence.get("source_ref") or evidence.get("source_id") or evidence.get("ref") or "")
                    if ref:
                        correlated_changes[ref] = {
                            "source_ref": ref,
                            "incident": incident["incident_key"],
                            "hypothesis_type": hypothesis.get("hypothesis_type") or "",
                            "summary": evidence.get("summary") or "",
                        }

        alerts = self.manager.alert_lifecycle.list(limit=max(1, min(int(alert_limit), 500)))
        critical_alerts = [a for a in alerts
                           if a.get("state") in {"OPEN", "ACKNOWLEDGED"}
                           and str(a.get("severity") or "").upper() in _CRITICAL_SEVERITIES]

        dependencies = self.manager.dependencies.dependencies(
            include_inactive=True, limit=max(1, min(int(dependency_limit), 2000)))
        unhealthy_dependencies = []
        for edge in dependencies:
            reason = ""
            if not edge.get("active"):
                reason = "INACTIVE"
            elif edge.get("evidence_state") == "UNKNOWN":
                reason = "UNKNOWN"
            elif edge.get("freshness") == "STALE":
                reason = "STALE"
            if reason:
                unhealthy_dependencies.append({**edge, "console_state": reason})

        connectors = self.manager.external_evidence.sources(
            limit=max(1, min(int(connector_limit), 1000)))
        degraded_connectors = [c for c in connectors
                               if c.get("status") not in {"CONNECTED", "CONFIGURED"}
                               or c.get("auth_state") == "FAILED"]

        correlation_health = self.manager.correlation_hardening.health(window_seconds=900)
        return {
            "generated_ts": time.time(),
            "correlation_health": correlation_health,
            "active_incidents": incident_rows,
            "active_incident_count": len(incident_rows),
            "impacted_services": sorted(impacted_services.values(), key=lambda x: (x.get("entity_type", ""), x.get("name", ""), x.get("entity_key", ""))),
            "correlated_changes": sorted(correlated_changes.values(), key=lambda x: (x["incident"], x["source_ref"])),
            "critical_alerts": critical_alerts,
            "unhealthy_dependencies": unhealthy_dependencies,
            "connectors": connectors,
            "degraded_connectors": degraded_connectors,
            "truth": {
                "correlation_is_causation": False,
                "device_polling_performed": False,
                "external_actions_performed": False,
            },
        }

    @staticmethod
    def _endpoint_index(rows):
        index = {}
        for row in rows or []:
            ips = list(row.get("ipv4") or []) + list(row.get("ipv6") or [])
            for ip in ips:
                index[str(ip)] = {
                    "mac": row.get("mac") or "",
                    "status": row.get("status") or "",
                    "confidence": row.get("confidence") or "",
                    "attachment": row.get("attachment"),
                }
        return index

    def traffic(self, collector, *, window_seconds=3600, bucket_seconds=300, limit=12, now=None):
        window_seconds = max(60, min(int(window_seconds), 86400))
        bucket_seconds = max(60, min(int(bucket_seconds), 3600))
        limit = max(1, min(int(limit), 20))
        now = time.time() if now is None else float(now)
        cutoff = now - window_seconds

        flows = []
        exporter_counts = collector.exporters() if collector is not None else {}
        if collector is not None:
            max_flows = max(1, int(getattr(collector, "max_flows", 500)))
            for exporter in sorted(exporter_counts):
                for flow in collector.flows_for(exporter, limit=max_flows):
                    ts = float(flow.get("ts") or 0)
                    if cutoff <= ts <= now:
                        flows.append(dict(flow))
        flows.sort(key=lambda f: (float(f.get("ts") or 0), str(f.get("exporter") or ""), str(f.get("src") or ""), str(f.get("dst") or "")))

        summary = summarize_flows(flows, limit=limit)
        endpoints = self._endpoint_index(self.manager.endpoint_inventory())
        for key in ("top_sources", "top_destinations"):
            for row in summary.get(key) or []:
                row["endpoint"] = endpoints.get(str(row.get("label") or ""))

        exporter_buckets = defaultdict(lambda: {"bytes": 0, "packets": 0, "flows": 0})
        trend = defaultdict(lambda: {"bytes": 0, "packets": 0, "flows": 0})
        for flow in flows:
            b = max(0, int(flow.get("bytes") or 0))
            p = max(0, int(flow.get("packets") or 0))
            exp = str(flow.get("exporter") or "unknown")
            exporter_buckets[exp]["bytes"] += b
            exporter_buckets[exp]["packets"] += p
            exporter_buckets[exp]["flows"] += 1
            bucket = int(float(flow.get("ts") or 0) // bucket_seconds) * bucket_seconds
            trend[bucket]["bytes"] += b
            trend[bucket]["packets"] += p
            trend[bucket]["flows"] += 1

        exporters = [{"exporter": key, **value, "packet_datagrams": int(exporter_counts.get(key, 0))}
                     for key, value in exporter_buckets.items()]
        exporters.sort(key=lambda x: (x["bytes"], x["packets"], x["flows"], x["exporter"]), reverse=True)
        trend_rows = [{"bucket_ts": ts, **trend[ts]} for ts in sorted(trend)]

        return {
            "window_seconds": window_seconds,
            "bucket_seconds": bucket_seconds,
            "cutoff_ts": cutoff,
            "generated_ts": now,
            "ring_bounded": True,
            "summary": summary,
            "exporters": exporters[:limit],
            "trend": trend_rows,
            "raw_flows": list(reversed(flows))[:200],
            "collector_status": collector.status() if collector is not None else {"running": False, "exporters": 0},
        }
