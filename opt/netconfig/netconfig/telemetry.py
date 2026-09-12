"""NI-5 gNMI telemetry lifecycle, scheduler, and bounded time-series evidence.

Long-lived unbounded streams are deliberately not embedded in HTTP request
threads.  Each subscription is collected in bounded windows, scheduled by the
existing singleton scheduler-leader model, and flattened into typed scalar
points for trend queries while preserving the bounded raw JSON evidence.
"""
from __future__ import annotations

import json
import math
import threading
import time
from contextlib import contextmanager

from .structured_protocols import GnmiPath, StructuredProtocolError

_ALLOWED_MODES = {"ON_CHANGE", "SAMPLE", "TARGET_DEFINED"}
_MAX_WINDOW_SECONDS = 300
_MAX_RECORDS_PER_WINDOW = 10_000
_MAX_POINTS_PER_RECORD = 2_000


class TelemetryError(RuntimeError):
    pass


class TelemetryService:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn
        self._guard = threading.Lock()
        self._locks = {}

    @contextmanager
    def _subscription_lock(self, sid):
        key = str(int(sid))
        with self._guard:
            local = self._locks.setdefault(key, threading.RLock())
        if not local.acquire(timeout=10):
            raise TelemetryError("timed out waiting for local telemetry subscription lock")
        lock_name = f"netconfig:telemetry:{key}"
        advisory = False
        try:
            advisory = bool(self.manager.db.try_advisory_lock(lock_name))
            if not advisory:
                raise TelemetryError("telemetry subscription is already being collected by another node")
            yield
        finally:
            if advisory:
                try:
                    self.manager.db.advisory_unlock(lock_name)
                except Exception:
                    pass
            local.release()

    def create(
        self,
        *,
        name,
        device,
        path,
        mode="ON_CHANGE",
        sample_interval_ms=10_000,
        heartbeat_interval_ms=0,
        window_seconds=30,
        collection_interval_seconds=60,
        retention_days=30,
        actor="system",
    ):
        dev, profile = self.manager._structured_profile_for(device)
        if profile["protocol"] != "gnmi":
            raise TelemetryError("NI-5 telemetry requires a gNMI protocol profile")
        typed = GnmiPath.parse(path)
        mode = str(mode or "ON_CHANGE").upper()
        if mode not in _ALLOWED_MODES:
            raise TelemetryError("unsupported telemetry subscription mode")
        sample = int(sample_interval_ms)
        heartbeat = int(heartbeat_interval_ms)
        window = int(window_seconds)
        collection = int(collection_interval_seconds)
        retention = int(retention_days)
        if sample < 1000 or sample > 3_600_000 or heartbeat < 0 or heartbeat > 3_600_000:
            raise TelemetryError("telemetry interval outside safe bounds")
        if window < 1 or window > _MAX_WINDOW_SECONDS:
            raise TelemetryError("telemetry collection window must be 1..300 seconds")
        if collection < max(5, window) or collection > 86_400:
            raise TelemetryError("telemetry collection interval must be >= window and <= 86400 seconds")
        if retention < 1 or retention > 3650:
            raise TelemetryError("telemetry retention must be 1..3650 days")
        name = str(name or "").strip()
        if not name or len(name) > 128:
            raise TelemetryError("telemetry subscription name is required and must be <=128 characters")
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO telemetry_subscriptions "
            "(name,device,path,mode,encoding,sample_interval_ms,heartbeat_interval_ms,window_seconds,"
            "collection_interval_seconds,retention_days,next_run_ts,enabled,state,created_ts,updated_ts) "
            "VALUES (?,?,?,?, 'json_ietf', ?,?,?,?,?,?,1,'IDLE',?,?)",
            (
                name,
                dev["name"],
                typed.render(),
                mode,
                sample,
                heartbeat,
                window,
                collection,
                retention,
                now,
                now,
                now,
            ),
        )
        self.conn.commit()
        self.manager.db.audit(
            actor,
            "telemetry_subscription_create",
            device,
            f"id={cur.lastrowid};mode={mode};path={typed.render()};window={window};interval={collection}",
        )
        return self.get(cur.lastrowid)

    def get(self, sid):
        row = self.conn.execute(
            "SELECT * FROM telemetry_subscriptions WHERE id=?", (int(sid),)
        ).fetchone()
        return dict(row) if row else None

    def list(self):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM telemetry_subscriptions ORDER BY name"
            ).fetchall()
        ]

    def set_enabled(self, sid, enabled, actor="system"):
        with self._subscription_lock(sid):
            item = self.get(sid)
            if not item:
                raise TelemetryError("unknown telemetry subscription")
            now = time.time()
            self.conn.execute(
                "UPDATE telemetry_subscriptions SET enabled=?,state=?,next_run_ts=?,updated_ts=? WHERE id=?",
                (
                    int(bool(enabled)),
                    "IDLE" if enabled else "DISABLED",
                    now if enabled else 0,
                    now,
                    int(sid),
                ),
            )
            self.conn.commit()
            self.manager.db.audit(
                actor,
                "telemetry_subscription_enable",
                item["device"],
                f"id={sid};enabled={int(bool(enabled))}",
            )
            return self.get(sid)

    def delete(self, sid, actor="system"):
        with self._subscription_lock(sid):
            item = self.get(sid)
            if not item:
                raise TelemetryError("unknown telemetry subscription")
            if item.get("state") == "RUNNING":
                raise TelemetryError("running telemetry subscription cannot be deleted")
            self.conn.execute("DELETE FROM telemetry_points WHERE subscription_id=?", (int(sid),))
            self.conn.execute("DELETE FROM telemetry_samples WHERE subscription_id=?", (int(sid),))
            self.conn.execute("DELETE FROM telemetry_subscriptions WHERE id=?", (int(sid),))
            self.conn.commit()
            self.manager.db.audit(
                actor, "telemetry_subscription_delete", item["device"], f"id={int(sid)};name={item['name']}"
            )
            return {"deleted": int(sid), "name": item["name"], "device": item["device"]}

    @staticmethod
    def _source_timestamp(value):
        candidates = value if isinstance(value, list) else [value]
        for item in candidates:
            if isinstance(item, dict):
                for key in ("timestamp", "ts", "time"):
                    raw = item.get(key)
                    if isinstance(raw, (int, float)):
                        number = float(raw)
                        if number > 1e15:
                            number /= 1e9
                        elif number > 1e12:
                            number /= 1e3
                        return number
        return 0.0

    @staticmethod
    def _flatten_scalars(value, prefix="$", *, limit=_MAX_POINTS_PER_RECORD):
        points = []

        def walk(node, path):
            if len(points) >= limit:
                return
            if isinstance(node, dict):
                for key in sorted(node, key=str):
                    clean = str(key).replace("\x00", "")[:128]
                    walk(node[key], f"{path}.{clean}")
                return
            if isinstance(node, list):
                for index, item in enumerate(node[:256]):
                    walk(item, f"{path}[{index}]")
                return
            if isinstance(node, bool):
                points.append((path, "boolean", float(int(node)), "true" if node else "false"))
                return
            if isinstance(node, (int, float)) and not isinstance(node, bool):
                number = float(node)
                if math.isfinite(number):
                    points.append((path, "number", number, ""))
                return
            if node is None:
                points.append((path, "null", None, ""))
                return
            if isinstance(node, str):
                points.append((path, "string", None, node.replace("\x00", "")[:4096]))

        walk(value, prefix)
        return points

    def _store_record(self, sub, item, observed):
        source_ts = self._source_timestamp(item)
        payload = json.dumps(item, separators=(",", ":"), sort_keys=True)
        self.conn.execute(
            "INSERT INTO telemetry_samples (subscription_id,device,path,observed_ts,value_json,source_ts) "
            "VALUES (?,?,?,?,?,?)",
            (int(sub["id"]), sub["device"], sub["path"], observed, payload, source_ts),
        )
        point_count = 0
        for value_path, value_type, numeric_value, text_value in self._flatten_scalars(item):
            self.conn.execute(
                "INSERT INTO telemetry_points "
                "(subscription_id,device,path,value_path,observed_ts,source_ts,value_type,numeric_value,text_value) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    int(sub["id"]),
                    sub["device"],
                    sub["path"],
                    value_path,
                    observed,
                    source_ts,
                    value_type,
                    numeric_value,
                    text_value,
                ),
            )
            point_count += 1
        return point_count

    def capture_once(self, sid, actor="system"):
        with self._subscription_lock(sid):
            return self._capture_once_locked(sid, actor=actor)

    def _capture_once_locked(self, sid, actor="system"):
        sub = self.get(sid)
        if not sub or not sub.get("enabled"):
            raise TelemetryError("telemetry subscription is missing or disabled")
        self.manager.ha.require_active_node()
        dev, profile = self.manager._structured_profile_for(sub["device"])
        try:
            text, meta = self.manager.structured_collector.subscribe_once(
                dev, profile, path=sub["path"]
            )
            value = json.loads(text)
            observed = time.time()
            points = self._store_record(sub, value, observed)
            next_run = observed + int(sub.get("collection_interval_seconds") or 60)
            self.conn.execute(
                "UPDATE telemetry_subscriptions "
                "SET state='IDLE',last_error='',last_run_ts=?,next_run_ts=?,updated_ts=? WHERE id=?",
                (observed, next_run, observed, int(sid)),
            )
            self.conn.commit()
            self.manager.db.audit(
                actor,
                "telemetry_capture",
                sub["device"],
                f"id={sid};status=ok;points={points}",
            )
            return {
                "subscription": self.get(sid),
                "metadata": meta,
                "observed_ts": observed,
                "points": points,
                "value": value,
            }
        except Exception as exc:
            self._record_error(sub, sid, exc, actor, "telemetry_capture")
            if isinstance(exc, StructuredProtocolError):
                raise TelemetryError(str(exc)) from exc
            raise

    def capture_window(self, sid, *, duration_seconds=None, actor="system"):
        with self._subscription_lock(sid):
            return self._capture_window_locked(
                sid, duration_seconds=duration_seconds, actor=actor
            )

    def _capture_window_locked(self, sid, *, duration_seconds=None, actor="system"):
        sub = self.get(sid)
        if not sub or not sub.get("enabled"):
            raise TelemetryError("telemetry subscription is missing or disabled")
        self.manager.ha.require_active_node()
        dev, profile = self.manager._structured_profile_for(sub["device"])
        duration = int(duration_seconds or sub.get("window_seconds") or 30)
        if duration < 1 or duration > _MAX_WINDOW_SECONDS:
            raise TelemetryError("telemetry collection window must be 1..300 seconds")
        started = time.time()
        self.conn.execute(
            "UPDATE telemetry_subscriptions SET state='RUNNING',updated_ts=? WHERE id=?",
            (started, int(sid)),
        )
        self.conn.commit()
        try:
            text, meta = self.manager.structured_collector.subscribe_window(
                dev,
                profile,
                path=sub["path"],
                mode=sub["mode"],
                duration_seconds=duration,
                sample_interval_ms=sub["sample_interval_ms"],
                heartbeat_interval_ms=sub["heartbeat_interval_ms"],
            )
            value = json.loads(text)
            records = value if isinstance(value, list) else [value]
            records = records[:_MAX_RECORDS_PER_WINDOW]
            observed = time.time()
            points = sum(self._store_record(sub, item, observed) for item in records)
            next_run = observed + int(sub.get("collection_interval_seconds") or 60)
            self.conn.execute(
                "UPDATE telemetry_subscriptions "
                "SET state='IDLE',last_error='',last_run_ts=?,next_run_ts=?,updated_ts=? WHERE id=?",
                (observed, next_run, observed, int(sid)),
            )
            self.conn.commit()
            self.manager.db.audit(
                actor,
                "telemetry_stream_window",
                sub["device"],
                f"id={sid};records={len(records)};points={points};duration={duration}",
            )
            return {
                "subscription": self.get(sid),
                "metadata": meta,
                "records": len(records),
                "points": points,
                "observed_ts": observed,
            }
        except Exception as exc:
            self._record_error(sub, sid, exc, actor, "telemetry_stream_window")
            if isinstance(exc, StructuredProtocolError):
                raise TelemetryError(str(exc)) from exc
            raise

    def _record_error(self, sub, sid, exc, actor, action):
        now = time.time()
        retry = now + max(30, int(sub.get("collection_interval_seconds") or 60))
        self.conn.execute(
            "UPDATE telemetry_subscriptions "
            "SET state='ERROR',last_error=?,last_run_ts=?,next_run_ts=?,updated_ts=? WHERE id=?",
            (type(exc).__name__, now, retry, now, int(sid)),
        )
        self.conn.commit()
        self.manager.db.audit(
            actor,
            action,
            sub["device"],
            f"id={sid};status=error;type={type(exc).__name__}",
        )

    def due(self, now=None, limit=32):
        now = float(time.time() if now is None else now)
        limit = min(256, max(1, int(limit)))
        rows = self.conn.execute(
            "SELECT * FROM telemetry_subscriptions "
            "WHERE enabled=1 AND next_run_ts<=? ORDER BY next_run_ts,id LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def run_due(self, *, actor="scheduler", now=None, limit=32):
        self.manager.ha.require_active_node()
        started = float(time.time() if now is None else now)
        results = []
        for sub in self.due(started, limit=limit):
            try:
                result = self.capture_window(
                    sub["id"],
                    duration_seconds=int(sub.get("window_seconds") or 30),
                    actor=actor,
                )
                results.append(
                    {
                        "subscription_id": sub["id"],
                        "ok": True,
                        "records": result["records"],
                        "points": result["points"],
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "subscription_id": sub["id"],
                        "ok": False,
                        "error": type(exc).__name__,
                    }
                )
        pruned = self.prune_expired(now=started)
        return {"processed": len(results), "results": results, "pruned": pruned}

    def samples(self, sid, limit=500):
        return [
            dict(row)
            for row in self.conn.execute(
                "SELECT * FROM telemetry_samples "
                "WHERE subscription_id=? ORDER BY observed_ts DESC LIMIT ?",
                (int(sid), min(5000, max(1, int(limit)))),
            ).fetchall()
        ]

    def points(self, sid, *, value_path=None, since_ts=0, limit=2000):
        limit = min(20_000, max(1, int(limit)))
        if value_path:
            rows = self.conn.execute(
                "SELECT * FROM telemetry_points WHERE subscription_id=? AND value_path=? "
                "AND observed_ts>=? ORDER BY observed_ts DESC LIMIT ?",
                (int(sid), str(value_path), float(since_ts), limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM telemetry_points WHERE subscription_id=? AND observed_ts>=? "
                "ORDER BY observed_ts DESC,id DESC LIMIT ?",
                (int(sid), float(since_ts), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, sid, *, value_path, since_ts=0, limit=20_000):
        sub = self.get(sid)
        if not sub:
            raise TelemetryError("unknown telemetry subscription")
        value_path = str(value_path or "").strip()
        if not value_path or len(value_path) > 1024 or "\x00" in value_path:
            raise TelemetryError("telemetry summary requires a bounded value path")
        rows = self.points(
            sid, value_path=value_path, since_ts=float(since_ts or 0),
            limit=min(20_000, max(1, int(limit))),
        )
        ordered = list(reversed(rows))
        numeric = [row for row in ordered if row.get("numeric_value") is not None]
        latest = ordered[-1] if ordered else None
        result = {
            "subscription_id": int(sid),
            "device": sub["device"],
            "path": sub["path"],
            "value_path": value_path,
            "count": len(ordered),
            "numeric_count": len(numeric),
            "first_observed_ts": float(ordered[0]["observed_ts"]) if ordered else 0,
            "last_observed_ts": float(ordered[-1]["observed_ts"]) if ordered else 0,
            "latest": latest,
        }
        if numeric:
            values = [float(row["numeric_value"]) for row in numeric]
            first = numeric[0]
            last = numeric[-1]
            elapsed = float(last["observed_ts"]) - float(first["observed_ts"])
            delta = values[-1] - values[0]
            result.update(
                {
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "first_numeric": values[0],
                    "last_numeric": values[-1],
                    "delta": delta,
                    "rate_per_second": (delta / elapsed) if elapsed > 0 else None,
                }
            )
        return result

    def prune_expired(self, now=None):
        now = float(time.time() if now is None else now)
        deleted_samples = 0
        deleted_points = 0
        for sub in self.list():
            cutoff = now - max(1, int(sub.get("retention_days") or 30)) * 86_400
            cur = self.conn.execute(
                "DELETE FROM telemetry_samples WHERE subscription_id=? AND observed_ts<?",
                (int(sub["id"]), cutoff),
            )
            deleted_samples += max(0, int(cur.rowcount or 0))
            cur = self.conn.execute(
                "DELETE FROM telemetry_points WHERE subscription_id=? AND observed_ts<?",
                (int(sub["id"]), cutoff),
            )
            deleted_points += max(0, int(cur.rowcount or 0))
        self.conn.commit()
        return {"samples": deleted_samples, "points": deleted_points}

    def prune(self, older_than_ts):
        cutoff = float(older_than_ts)
        samples = self.conn.execute(
            "DELETE FROM telemetry_samples WHERE observed_ts < ?", (cutoff,)
        )
        points = self.conn.execute(
            "DELETE FROM telemetry_points WHERE observed_ts < ?", (cutoff,)
        )
        self.conn.commit()
        return {
            "samples": max(0, int(samples.rowcount or 0)),
            "points": max(0, int(points.rowcount or 0)),
        }


def poller(manager, interval, stop_event):
    """Singleton NI-5 scheduler loop; node drain is honored on every iteration."""
    interval = max(5, int(interval))
    while not stop_event.wait(interval):
        if not manager.ha.accepts_automation_work():
            continue
        try:
            manager.telemetry.run_due(actor="scheduler")
        except Exception as exc:
            manager.db.audit(
                "scheduler",
                "telemetry_scheduler_failed",
                "ni5",
                type(exc).__name__,
            )
