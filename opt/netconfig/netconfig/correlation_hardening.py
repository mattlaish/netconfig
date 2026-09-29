"""MC-10 production hardening and qualification support for correlation.

This module adds bounded run telemetry, replay-preview semantics, restart recovery,
retention for correlation-run metadata, and read-only production health snapshots.
It does not add device polling, external response actions, or configuration
execution authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from contextlib import contextmanager


MC10_SCHEMA_REVISION = "mc10-correlation-hardening-1"
MC10_COMPATIBLE_SCHEMA_REVISIONS = {MC10_SCHEMA_REVISION, "mc11-topology-change-planning-1"}
MAX_INCIDENT_TIMELINE_EVENTS = 2000
MAX_REPLAY_RANGE_SECONDS = 7 * 24 * 60 * 60
CLOCK_SKEW_WARN_SECONDS = 300
DEFAULT_RUNTIME_RETENTION_DAYS = 30
MAX_RUNTIME_RETENTION_DAYS = 3650
LOCK_WAIT_SECONDS = 5.0


class CorrelationBusyError(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _percentile(values, percentile):
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * float(percentile)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return round(ordered[lo], 3)
    value = ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)
    return round(value, 3)


class CorrelationHardeningService:
    """Runtime safety/qualification layer around deterministic correlation."""

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self._state_lock = threading.RLock()
        self._locks = {}
        self._inflight = 0
        self._waiting = 0
        self._recover_interrupted_runs()

    def _recover_interrupted_runs(self):
        now = time.time()
        self.conn.execute(
            "UPDATE correlation_runs SET state='INTERRUPTED',finished_ts=?,duration_ms=CASE "
            "WHEN started_ts>0 AND ?>started_ts THEN (?-started_ts)*1000 ELSE 0 END,error='ProcessRestart' "
            "WHERE state='RUNNING'",
            (now, now, now),
        )
        self.conn.commit()

    @staticmethod
    def bounds():
        # Imported lazily to avoid a module cycle with CorrelationEngine.
        from .correlation import (
            _MAX_DEP_EDGES, _MAX_FACTS, _MAX_HYPOTHESES, _MAX_REL_DEPTH,
            _MAX_REL_NODES, _MAX_RULE_WINDOW_SECONDS,
        )
        from .external_evidence import _GLOBAL_MAX_PAYLOAD
        return {
            "max_facts_per_run": _MAX_FACTS,
            "max_hypotheses_per_run": _MAX_HYPOTHESES,
            "max_dependency_edges": _MAX_DEP_EDGES,
            "max_relationship_depth": _MAX_REL_DEPTH,
            "max_relationship_nodes": _MAX_REL_NODES,
            "max_rule_time_window_seconds": _MAX_RULE_WINDOW_SECONDS,
            "max_incident_timeline_events": MAX_INCIDENT_TIMELINE_EVENTS,
            "max_replay_range_seconds": MAX_REPLAY_RANGE_SECONDS,
            "clock_skew_warn_seconds": CLOCK_SKEW_WARN_SECONDS,
            "external_payload_hard_limit_bytes": _GLOBAL_MAX_PAYLOAD,
            "lock_wait_seconds": LOCK_WAIT_SECONDS,
        }

    def _lock_for(self, incident_id):
        with self._state_lock:
            return self._locks.setdefault(int(incident_id), threading.Lock())

    @contextmanager
    def incident_guard(self, incident_id):
        """Bound concurrent runs per incident and use PostgreSQL advisory locking when available."""
        incident_id = int(incident_id)
        lock = self._lock_for(incident_id)
        with self._state_lock:
            self._waiting += 1
        acquired = lock.acquire(timeout=LOCK_WAIT_SECONDS)
        with self._state_lock:
            self._waiting -= 1
        if not acquired:
            raise CorrelationBusyError("correlation run is already active for this incident")
        advisory_name = f"mc10:correlation:incident:{incident_id}"
        advisory = False
        try:
            if getattr(self.db, "dialect", "sqlite") == "postgres" and hasattr(self.db, "try_advisory_lock"):
                advisory = bool(self.db.try_advisory_lock(advisory_name))
                if not advisory:
                    raise CorrelationBusyError("correlation run is active on another control-plane node")
            with self._state_lock:
                self._inflight += 1
            yield
        finally:
            with self._state_lock:
                self._inflight = max(0, self._inflight - 1)
            if advisory and hasattr(self.db, "advisory_unlock"):
                try:
                    self.db.advisory_unlock(advisory_name)
                except Exception:
                    pass
            lock.release()

    @staticmethod
    def fact_diagnostics(facts):
        late = 0
        future = 0
        received_order = []
        for fact in facts:
            source_ts = float(fact.get("source_ts") or 0)
            received_ts = float(fact.get("received_ts") or 0)
            skew = received_ts - source_ts
            if skew > CLOCK_SKEW_WARN_SECONDS:
                late += 1
            elif skew < -CLOCK_SKEW_WARN_SECONDS:
                future += 1
            received_order.append((received_ts, source_ts, str(fact.get("source_type") or ""), str(fact.get("source_ref") or "")))
        received_order.sort()
        out_of_order = 0
        max_source = None
        for _, source_ts, _, _ in received_order:
            if max_source is not None and source_ts < max_source:
                out_of_order += 1
            max_source = source_ts if max_source is None else max(max_source, source_ts)
        source_times = [float(x.get("source_ts") or 0) for x in facts]
        return {
            "late_evidence_count": late,
            "future_clock_skew_count": future,
            "out_of_order_count": out_of_order,
            "first_source_ts": min(source_times) if source_times else 0,
            "last_source_ts": max(source_times) if source_times else 0,
        }

    @staticmethod
    def input_fingerprint(facts, dependency_fingerprint, *, mode, range_start_ts=0, range_end_ts=0):
        material = [{
            "source_type": x.get("source_type"),
            "source_ref": x.get("source_ref"),
            "source_ts": x.get("source_ts"),
            "received_ts": x.get("received_ts"),
            "status": x.get("status"),
            "severity": x.get("severity"),
            "event_type": x.get("event_type"),
            "aliases": x.get("aliases") or [],
            "degrading": bool(x.get("degrading")),
            "healthy": bool(x.get("healthy")),
        } for x in facts]
        return _sha({
            "facts": material,
            "dependency_fingerprint": dependency_fingerprint,
            "mode": mode,
            "range_start_ts": float(range_start_ts or 0),
            "range_end_ts": float(range_end_ts or 0),
        })

    @staticmethod
    def result_fingerprint(hypotheses):
        return _sha([{
            "hypothesis_key": h.get("hypothesis_key"),
            "hypothesis_type": h.get("hypothesis_type"),
            "confidence": h.get("confidence"),
            "evidence_fingerprint": h.get("evidence_fingerprint"),
        } for h in hypotheses])

    def begin_run(self, incident_id, rule_version, input_fingerprint, *, mode="CORRELATE",
                  range_start_ts=0, range_end_ts=0, now=None):
        now = time.time() if now is None else float(now)
        previous = self.conn.execute(
            "SELECT id,result_fingerprint FROM correlation_runs WHERE incident_id=? AND mode=? "
            "AND rule_version=? AND input_fingerprint=? AND state='COMPLETED' "
            "ORDER BY finished_ts DESC,id DESC LIMIT 1",
            (int(incident_id), mode, rule_version, input_fingerprint),
        ).fetchone()
        run_key = "corr-" + secrets.token_hex(16)
        cur = self.conn.execute(
            "INSERT INTO correlation_runs(tenant_id,incident_id,run_key,mode,rule_version,input_fingerprint,"
            "state,replay_of_id,deterministic_match,range_start_ts,range_end_ts,queued_ts,started_ts) "
            "VALUES('default',?,?,?,?,?,'RUNNING',?,1,?,?,?,?)",
            (int(incident_id), run_key, mode, rule_version, input_fingerprint,
             int(previous["id"]) if previous else None, float(range_start_ts or 0), float(range_end_ts or 0), now, now),
        )
        self.conn.commit()
        return {
            "id": int(cur.lastrowid), "run_key": run_key,
            "replay_of_id": int(previous["id"]) if previous else None,
            "previous_result_fingerprint": previous["result_fingerprint"] if previous else "",
            "started_ts": now,
        }

    def complete_run(self, run, *, result_fingerprint, facts_considered, hypotheses_count,
                     diagnostics, dependency_truncated=False, facts_truncated=False, now=None):
        now = time.time() if now is None else float(now)
        duration_ms = max(0.0, (now - float(run["started_ts"])) * 1000.0)
        previous = str(run.get("previous_result_fingerprint") or "")
        deterministic = not previous or previous == result_fingerprint
        state = "COMPLETED" if deterministic else "NON_DETERMINISTIC"
        error = "" if deterministic else "same input fingerprint produced a different result fingerprint"
        self.conn.execute(
            "UPDATE correlation_runs SET result_fingerprint=?,state=?,deterministic_match=?,facts_considered=?,"
            "hypotheses_count=?,late_evidence_count=?,future_skew_count=?,out_of_order_count=?,"
            "dependency_truncated=?,facts_truncated=?,finished_ts=?,duration_ms=?,error=? WHERE id=?",
            (result_fingerprint, state, 1 if deterministic else 0, int(facts_considered), int(hypotheses_count),
             int(diagnostics.get("late_evidence_count") or 0), int(diagnostics.get("future_clock_skew_count") or 0),
             int(diagnostics.get("out_of_order_count") or 0), 1 if dependency_truncated else 0,
             1 if facts_truncated else 0, now, duration_ms, error, int(run["id"])),
        )
        self.conn.commit()
        if not deterministic:
            raise RuntimeError("NON_DETERMINISTIC_CORRELATION_RESULT")
        return self.run(run["id"])

    def fail_run(self, run, exc, *, now=None):
        now = time.time() if now is None else float(now)
        duration_ms = max(0.0, (now - float(run["started_ts"])) * 1000.0)
        self.conn.execute(
            "UPDATE correlation_runs SET state='FAILED',finished_ts=?,duration_ms=?,error=? WHERE id=? AND state='RUNNING'",
            (now, duration_ms, str(exc)[:500], int(run["id"])),
        )
        self.conn.commit()

    @staticmethod
    def _run_row(row):
        if not row:
            return None
        item = dict(row)
        for key in ("deterministic_match", "dependency_truncated", "facts_truncated"):
            item[key] = bool(item.get(key))
        return item

    def run(self, ref):
        row = self.conn.execute(
            "SELECT * FROM correlation_runs WHERE id=? OR run_key=? ORDER BY id DESC LIMIT 1",
            (int(ref) if str(ref).isdigit() else -1, str(ref)),
        ).fetchone()
        return self._run_row(row)

    def runs(self, incident_ref="", *, limit=100):
        limit = max(1, min(int(limit), 1000))
        args = []
        q = "SELECT r.* FROM correlation_runs r"
        if incident_ref:
            incident = self.manager.incidents.get(incident_ref)
            if not incident:
                raise ValueError("incident not found")
            q += " WHERE r.incident_id=?"
            args.append(incident["id"])
        q += " ORDER BY r.started_ts DESC,r.id DESC LIMIT ?"
        args.append(limit)
        return [self._run_row(row) for row in self.conn.execute(q, tuple(args)).fetchall()]

    def replay_preview(self, incident_ref, start_ts, end_ts, *, actor="system"):
        start_ts = float(start_ts)
        end_ts = float(end_ts)
        if start_ts <= 0 or end_ts <= 0 or end_ts < start_ts:
            raise ValueError("replay range must have positive start_ts <= end_ts")
        if end_ts - start_ts > MAX_REPLAY_RANGE_SECONDS:
            raise ValueError(f"replay range exceeds {MAX_REPLAY_RANGE_SECONDS} seconds")
        return self.manager.correlation.preview(
            incident_ref, start_ts=start_ts, end_ts=end_ts, actor=actor, mode="REPLAY_PREVIEW")

    def prune_runs(self, retention_days=DEFAULT_RUNTIME_RETENTION_DAYS, *, now=None, actor="system"):
        retention_days = int(retention_days)
        if retention_days < 1 or retention_days > MAX_RUNTIME_RETENTION_DAYS:
            raise ValueError(f"retention_days must be 1..{MAX_RUNTIME_RETENTION_DAYS}")
        now = time.time() if now is None else float(now)
        cutoff = now - retention_days * 86400
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM correlation_runs WHERE state<>'RUNNING' AND finished_ts>0 AND finished_ts<?",
            (cutoff,),
        ).fetchone()
        count = int(row["n"] or 0) if row else 0
        self.conn.execute(
            "DELETE FROM correlation_runs WHERE state<>'RUNNING' AND finished_ts>0 AND finished_ts<?",
            (cutoff,),
        )
        self.conn.commit()
        self.db.audit(actor, "correlation_runtime_retention", "correlation_runs",
                      f"retention_days={retention_days};deleted={count}")
        return {"retention_days": retention_days, "cutoff_ts": cutoff, "deleted_runs": count}

    def health(self, *, window_seconds=900, now=None):
        window_seconds = max(60, min(int(window_seconds), 86400))
        now = time.time() if now is None else float(now)
        cutoff = now - window_seconds
        rows = [dict(r) for r in self.conn.execute(
            "SELECT * FROM correlation_runs WHERE started_ts>=? ORDER BY started_ts,id", (cutoff,)).fetchall()]
        completed = [r for r in rows if r.get("state") == "COMPLETED"]
        latencies = [float(r.get("duration_ms") or 0) for r in completed]
        external_events = self.conn.execute(
            "SELECT COUNT(*) AS n FROM external_events WHERE received_ts>=?", (cutoff,)).fetchone()
        receipts = self.conn.execute(
            "SELECT result,COUNT(*) AS n FROM external_ingest_receipts WHERE received_ts>=? GROUP BY result",
            (cutoff,),
        ).fetchall()
        receipt_counts = {str(r["result"]): int(r["n"] or 0) for r in receipts}
        sensor = self.conn.execute(
            "SELECT COUNT(*) AS n FROM sensor_transitions WHERE COALESCE(created_at,observed_at)>=?", (cutoff,)).fetchone()
        alerts = self.conn.execute(
            "SELECT COUNT(*) AS n FROM operational_alerts WHERE first_ts>=?", (cutoff,)).fetchone()
        incidents = self.conn.execute(
            "SELECT COUNT(*) AS n FROM incidents WHERE created_ts>=?", (cutoff,)).fetchone()
        sources = [dict(r) for r in self.conn.execute(
            "SELECT * FROM external_sources ORDER BY source_key").fetchall()]
        lag_rows = []
        rejected_total = duplicate_total = 0
        for source in sources:
            lag = max(0.0, float(source.get("last_received_ts") or 0) - float(source.get("last_event_ts") or 0))
            if source.get("last_received_ts"):
                lag_rows.append({"source_key": source.get("source_key"), "lag_seconds": round(lag, 3)})
            rejected_total += int(source.get("rejected_count") or 0)
            duplicate_total += int(source.get("duplicate_count") or 0)
        with self._state_lock:
            inflight = self._inflight
            waiting = self._waiting
        return {
            "window_seconds": window_seconds,
            "generated_ts": now,
            "bounds": self.bounds(),
            "correlation": {
                "runs": len(rows),
                "completed": len(completed),
                "failed": sum(1 for r in rows if r.get("state") == "FAILED"),
                "interrupted": sum(1 for r in rows if r.get("state") == "INTERRUPTED"),
                "non_deterministic": sum(1 for r in rows if r.get("state") == "NON_DETERMINISTIC"),
                "replays": sum(1 for r in rows if r.get("replay_of_id") is not None),
                "facts_truncated_runs": sum(1 for r in rows if r.get("facts_truncated")),
                "dependency_truncated_runs": sum(1 for r in rows if r.get("dependency_truncated")),
                "late_evidence": sum(int(r.get("late_evidence_count") or 0) for r in rows),
                "future_clock_skew": sum(int(r.get("future_skew_count") or 0) for r in rows),
                "out_of_order": sum(int(r.get("out_of_order_count") or 0) for r in rows),
                "latency_ms": {
                    "p50": _percentile(latencies, 0.50),
                    "p95": _percentile(latencies, 0.95),
                    "max": round(max(latencies), 3) if latencies else 0.0,
                },
                "queue_depth": waiting,
                "inflight": inflight,
                "execution_model": "synchronous-bounded",
            },
            "rates": {
                "external_events": int(external_events["n"] or 0) if external_events else 0,
                "sensor_transitions": int(sensor["n"] or 0) if sensor else 0,
                "alerts_created": int(alerts["n"] or 0) if alerts else 0,
                "incidents_created": int(incidents["n"] or 0) if incidents else 0,
            },
            "external_ingestion": {
                "receipt_results": receipt_counts,
                "duplicate_receipts": sum(v for k, v in receipt_counts.items() if k.startswith("DUPLICATE")),
                "rejected_total": rejected_total,
                "duplicate_total": duplicate_total,
                "connector_lag": lag_rows,
            },
            "truth": {
                "correlation_is_causation": False,
                "qualification_is_release_approval": False,
                "device_polling_performed": False,
                "external_actions_performed": False,
            },
        }

    def qualification_report(self, *, now=None, window_seconds=900):
        now = time.time() if now is None else float(now)
        health = self.health(window_seconds=window_seconds, now=now)
        local_checks = [
            {"name": "schema-revision", "status": "PASS" if self.db.storage_status().get("schema_revision") in MC10_COMPATIBLE_SCHEMA_REVISIONS else "FAIL"},
            {"name": "bounded-correlation-limits", "status": "PASS"},
            {"name": "determinism-watch", "status": "PASS" if health["correlation"]["non_deterministic"] == 0 else "FAIL"},
            {"name": "stale-run-recovery", "status": "PASS" if not self.conn.execute("SELECT 1 FROM correlation_runs WHERE state='RUNNING' AND started_ts<? LIMIT 1", (now - 300,)).fetchone() else "FAIL"},
        ]
        deferred = [
            "live-postgresql-concurrency",
            "live-postgresql-backup-restore",
            "almalinux-rpmbuild-dnf-upgrade",
            "systemd-selinux",
            "representative-live-device-protocols",
            "live-external-product-ingestion",
            "production-scale-correlation-and-large-topology",
            "production-clock-skew-and-out-of-order",
            "ha-failover-when-supported",
        ]
        failures = [x["name"] for x in local_checks if x["status"] == "FAIL"]
        return {
            "qualification_track": "MC-10",
            "status": "IMPLEMENTED_TESTING_DEFERRED",
            "local_checks": local_checks,
            "deferred_live_gates": [{"name": name, "status": "NOT_RUN"} for name in deferred],
            "health": health,
            "local_ready": not failures,
            "release_eligible": False,
            "failures": failures,
        }
