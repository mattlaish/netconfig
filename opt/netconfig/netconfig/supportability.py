"""R66 bounded, read-only runtime observability and supportability view.

The service aggregates already-persisted/runtime state.  It never polls devices,
executes changes, exposes credentials, or turns local health into qualification.
"""
from __future__ import annotations

import re
import shutil
import time
from collections import Counter

from . import __version__

SCHEMA = "r66-supportability-1"
_SECRET = re.compile(
    r"(?i)(bearer\s+[^\s,;]+|(?:password|passwd|secret|token|community|api[_-]?key|authorization)\s*[=:]\s*[^\s,;]+)"
)


def _safe_text(value, limit=300):
    text = str(value or "").replace("\x00", " ")[:limit]
    return _SECRET.sub("[REDACTED]", text)


def _age(now, ts):
    try:
        ts = float(ts or 0)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, now - ts), 3) if ts > 0 else None


def _counts(rows, key):
    return dict(sorted(Counter(str(row.get(key) or "UNKNOWN") for row in rows).items()))


class SupportabilityService:
    """Aggregate bounded secret-free runtime diagnostics without side effects."""

    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn

    def _tasks(self, now):
        rows = [dict(row) for row in self.conn.execute(
            "SELECT state,available_ts,lease_until,updated_ts FROM distributed_tasks"
        ).fetchall()]
        pending = [row for row in rows if row.get("state") == "PENDING"]
        claimed = [row for row in rows if row.get("state") == "CLAIMED"]
        oldest = min((float(row.get("available_ts") or now) for row in pending), default=0)
        expired = sum(
            1 for row in claimed
            if row.get("lease_until") is not None and float(row.get("lease_until") or 0) < now
        )
        return {
            "total": len(rows),
            "states": _counts(rows, "state"),
            "pending": len(pending),
            "claimed": len(claimed),
            "expired_claims_visible": expired,
            "recovery_required": sum(1 for row in rows if row.get("state") == "RECOVERY_REQUIRED"),
            "oldest_pending_age_seconds": _age(now, oldest),
        }

    def _telemetry(self, now):
        rows = self.manager.telemetry.list()
        enabled = [row for row in rows if bool(row.get("enabled"))]
        due = [row for row in enabled if float(row.get("next_run_ts") or 0) <= now]
        successful = [
            row for row in rows
            if float(row.get("last_run_ts") or 0) > 0 and not str(row.get("last_error") or "")
        ]
        last_success = max((float(row.get("last_run_ts") or 0) for row in successful), default=0)
        max_lag = max((max(0.0, now - float(row.get("next_run_ts") or now)) for row in due), default=0.0)
        return {
            "subscriptions": len(rows),
            "enabled": len(enabled),
            "states": _counts(rows, "state"),
            "due": len(due),
            "error": sum(1 for row in rows if str(row.get("state") or "").upper() == "ERROR"),
            "max_schedule_lag_seconds": round(max_lag, 3),
            "last_success_age_seconds": _age(now, last_success),
        }

    def _external_ingest(self, now):
        rows = self.manager.external_evidence.sources(limit=1000)
        enabled = [row for row in rows if bool(row.get("enabled"))]
        last_received = max((float(row.get("last_received_ts") or 0) for row in rows), default=0)
        return {
            "sources": len(rows),
            "enabled": len(enabled),
            "statuses": _counts(rows, "status"),
            "auth_states": _counts(rows, "auth_state"),
            "received": sum(int(row.get("received_count") or 0) for row in rows),
            "rejected": sum(int(row.get("rejected_count") or 0) for row in rows),
            "duplicates": sum(int(row.get("duplicate_count") or 0) for row in rows),
            "rate_limited": sum(int(row.get("rate_limited_count") or 0) for row in rows),
            "schema_rejections": sum(int(row.get("schema_rejection_count") or 0) for row in rows),
            "last_success_age_seconds": _age(now, last_received),
            "last_error_classes": dict(sorted(Counter(
                str(row.get("last_error_class") or "") for row in rows if row.get("last_error_class")
            ).items())),
        }

    def _collectors(self):
        configured = {
            "netflow": bool(self.manager.settings.get("netflow_enabled")),
            "syslog": bool(self.manager.settings.get("syslog_enabled")),
            "snmp_trap": bool(self.manager.settings.get("snmp_trap_enabled")),
        }
        attached = getattr(self.manager, "runtime_collectors", {}) or {}
        out = {}
        for name, enabled in configured.items():
            collector = attached.get(name)
            status = {}
            if collector is not None and hasattr(collector, "status"):
                try:
                    status = dict(collector.status() or {})
                except Exception as exc:
                    status = {"running": False, "last_error": _safe_text(exc)}
            out[name] = {
                "configured": enabled,
                "attached": collector is not None,
                "running": bool(status.get("running")),
                "queue_depth": int(status.get("queue_depth") or 0),
                "dropped": int(status.get("dropped") or 0),
                "received": int(status.get("total_packets") or 0),
                "accepted": int(status.get("accepted") or status.get("total_flows") or 0),
                "rejected": int(status.get("rejected") or 0),
                "last_error": _safe_text(status.get("last_error")),
            }
        return out

    def _retention(self, now):
        row = self.conn.execute(
            "SELECT ts,action FROM audit WHERE action IN ('diagnostic_retention','diagnostic_retention_failed') "
            "ORDER BY ts DESC,id DESC LIMIT 1"
        ).fetchone()
        return {
            "maintenance_interval_seconds": int(self.manager.settings.get("diagnostic_maintenance_interval", 0) or 0),
            "debug_bundle_keep": int(self.manager.settings.get("debug_bundle_keep", 10) or 10),
            "case_export_retention_days": int(self.manager.settings.get("case_export_retention_days", 0) or 0),
            "protocol_trace_retention_days": int(self.manager.settings.get("protocol_trace_retention_days", 0) or 0),
            "last_run_status": ("FAILED" if row and row["action"] == "diagnostic_retention_failed" else "OK") if row else "NEVER",
            "last_run_age_seconds": _age(now, row["ts"] if row else 0),
        }

    def _last_success(self, now):
        facts = list(self.manager.inv.all_facts().values())
        snmp_success = max((float(row.get("last_polled") or 0) for row in facts if row.get("reachable")), default=0)
        run = self.conn.execute("SELECT MAX(ts) AS ts FROM runs WHERE ok=1").fetchone()
        change_success = self.conn.execute(
            "SELECT MAX(finished_ts) AS ts FROM structured_change_transactions WHERE state='SUCCEEDED'"
        ).fetchone()
        return {
            "snmp_poll_age_seconds": _age(now, snmp_success),
            "config_collection_age_seconds": _age(now, run["ts"] if run else 0),
            "structured_change_age_seconds": _age(now, change_success["ts"] if change_success else 0),
        }

    def _disk(self):
        try:
            usage = shutil.disk_usage(self.manager.paths.home)
            free_percent = (usage.free / usage.total * 100.0) if usage.total else 0.0
            return {
                "total_bytes": int(usage.total), "used_bytes": int(usage.used), "free_bytes": int(usage.free),
                "free_percent": round(free_percent, 3),
            }
        except OSError as exc:
            return {"error": _safe_text(exc), "total_bytes": 0, "used_bytes": 0, "free_bytes": 0, "free_percent": 0.0}

    def snapshot(self, now=None):
        now = float(time.time() if now is None else now)
        storage = dict(self.manager.db.readiness())
        storage.pop("error", None)
        tasks = self._tasks(now)
        telemetry = self._telemetry(now)
        ingest = self._external_ingest(now)
        collectors = self._collectors()
        retention = self._retention(now)
        disk = self._disk()
        correlation = self.manager.correlation_hardening.health(window_seconds=900, now=now)
        nodes = self.manager.ha.nodes(90)
        node = self.manager.ha.node() or {}
        active_nodes = [item for item in nodes if str(item.get("state") or "ACTIVE").upper() == "ACTIVE"]
        failure_domains = {str(item.get("failure_domain") or "").strip() for item in active_nodes if str(item.get("failure_domain") or "").strip()}
        backend = storage.get("backend") or getattr(self.manager.db, "dialect", "sqlite")
        ha_ready_observed = bool(
            backend == "postgres" and getattr(self.manager.db, "distributed_capable", False)
            and len(active_nodes) >= 2 and len(failure_domains) >= 2
            and str(node.get("state") or "ACTIVE").upper() == "ACTIVE"
        )
        issues = []
        if not bool(storage.get("ok") and storage.get("reachable", True)):
            issues.append("core storage is not ready")
        if tasks["recovery_required"] or tasks["expired_claims_visible"]:
            issues.append("distributed work requires recovery attention")
        if telemetry["error"]:
            issues.append("telemetry subscriptions report errors")
        if any(item["dropped"] for item in collectors.values()):
            issues.append("collector packet drops observed")
        if any(item["configured"] and not item["running"] for item in collectors.values()):
            issues.append("configured runtime collector is not running")
        if ingest["rejected"]:
            issues.append("external evidence rejections observed")
        if retention["last_run_status"] == "FAILED":
            issues.append("diagnostic retention last run failed")
        if disk.get("free_bytes", 0) < 512 * 1024 * 1024 or disk.get("free_percent", 0) < 5.0:
            issues.append("runtime filesystem free space is low")
        return {
            "schema": SCHEMA,
            "generated_ts": now,
            "version": __version__,
            "state": "READY" if not issues else "DEGRADED",
            "issues": issues,
            "storage": storage,
            "ha": {
                "backend": backend,
                "ready_observed": ha_ready_observed,
                "fresh_node_count": len(nodes),
                "active_node_count": len(active_nodes),
                "failure_domain_count": len(failure_domains),
                "identity_fence_probed": False,
            },
            "restart": {
                "node_state": str(node.get("state") or "UNKNOWN"),
                "process_age_seconds": _age(now, node.get("started_ts")),
                "heartbeat_age_seconds": _age(now, node.get("last_heartbeat_ts")),
            },
            "queues": {"distributed_tasks": tasks, "correlation": correlation.get("correlation", {})},
            "telemetry": telemetry,
            "external_ingest": ingest,
            "collectors": collectors,
            "retention": retention,
            "disk": disk,
            "last_success": self._last_success(now),
            "truth": {
                "read_only": True,
                "device_polling_performed": False,
                "network_write_authority": False,
                "qualification_claim": False,
                "secrets_included": False,
            },
        }

    def publish_metrics(self, metrics, now=None):
        snap = self.snapshot(now=now)
        tasks = snap["queues"]["distributed_tasks"]
        metrics.set("netconfig_supportability_ready", 1 if snap["state"] == "READY" else 0)
        metrics.set("netconfig_storage_ready", 1 if snap["storage"].get("ok") else 0)
        metrics.set("netconfig_disk_free_bytes", snap["disk"].get("free_bytes", 0))
        metrics.set("netconfig_distributed_tasks_pending", tasks["pending"])
        metrics.set("netconfig_distributed_tasks_recovery_required", tasks["recovery_required"])
        metrics.set("netconfig_telemetry_due", snap["telemetry"]["due"])
        metrics.set("netconfig_telemetry_errors", snap["telemetry"]["error"])
        metrics.set("netconfig_external_ingest_rejected_total", snap["external_ingest"]["rejected"])
        metrics.set("netconfig_correlation_queue_depth", snap["queues"]["correlation"].get("queue_depth", 0))
        metrics.set("netconfig_correlation_inflight", snap["queues"]["correlation"].get("inflight", 0))
        metrics.set("netconfig_collector_dropped_total", sum(v["dropped"] for v in snap["collectors"].values()))
        return snap
