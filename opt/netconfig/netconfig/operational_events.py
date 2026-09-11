"""NI-3 durable operational event correlation and dependency suppression."""
import hashlib
import json
import time


def _safe_text(value, limit=1024):
    text = str(value or "").replace("\x00", "")
    return text[:limit]


class OperationalEventStore:
    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db

    def _active_suppression(self, device, now=None):
        now = time.time() if now is None else float(now)
        self.db.expire_operational_suppressions(now)
        rows = self.db.active_operational_suppressions(device, now)
        return rows[0] if rows else None

    def record(self, *, source_type, source="", device="", event_type="EVENT",
               severity="INFO", interface="", ifindex="", trap_oid="",
               message="", metadata=None, dedup_seconds=None, now=None,
               allow_suppression=True):
        now = time.time() if now is None else float(now)
        dedup_seconds = int(self.manager.settings.get("operational_event_dedup_seconds", 30)
                            if dedup_seconds is None else dedup_seconds)
        meta = dict(metadata or {})
        # Explicit allow-list/bounds.  Raw packets, community strings and arbitrary
        # secret material are never accepted by this storage boundary.
        clean_meta = {}
        for key in ("protocol", "version", "generic_trap", "specific_trap",
                    "uptime_ticks", "if_admin_status", "if_oper_status",
                    "source_port", "poll_ok", "reason"):
            if key in meta and meta[key] is not None:
                clean_meta[key] = _safe_text(meta[key], 256)
        device = _safe_text(device, 255)
        interface = _safe_text(interface, 255)
        ifindex = _safe_text(ifindex, 64)
        event_type = _safe_text(event_type, 96).upper() or "EVENT"
        source_type = _safe_text(source_type, 32).lower() or "unknown"
        trap_oid = _safe_text(trap_oid, 255)
        source = _safe_text(source, 255)
        severity = _safe_text(severity, 16).upper() or "INFO"
        message = _safe_text(message, 2048)
        dedup_basis = "\x1f".join([source_type, device, event_type, interface, ifindex, trap_oid, message])
        dedup_key = hashlib.sha256(dedup_basis.encode("utf-8", "replace")).hexdigest()
        if dedup_seconds > 0:
            existing = self.db.find_recent_operational_event(dedup_key, now - dedup_seconds)
            if existing:
                row = self.db.touch_operational_event(existing["id"], now)
                row["deduplicated"] = True
                lifecycle = getattr(self.manager, "alert_lifecycle", None)
                if lifecycle is not None:
                    lifecycle.observe_event(row, now=now)
                return row
        suppression = self._active_suppression(device, now) if allow_suppression and device else None
        row = self.db.insert_operational_event(
            now, source_type, source, device, event_type, severity, interface, ifindex,
            trap_oid, message, dedup_key, 1 if suppression else 0,
            suppression["id"] if suppression else None,
            json.dumps(clean_meta, sort_keys=True, separators=(",", ":")))
        row["deduplicated"] = False
        lifecycle = getattr(self.manager, "alert_lifecycle", None)
        if lifecycle is not None:
            lifecycle.observe_event(row, now=now)
            refreshed = self.db.conn.execute("SELECT * FROM operational_events WHERE id=?", (int(row["id"]),)).fetchone()
            if refreshed:
                row = dict(refreshed); row["deduplicated"] = False
        return row

    def list(self, limit=200, device=None, include_suppressed=True):
        self.db.expire_operational_suppressions(time.time())
        return self.db.operational_events(limit=limit, device=device,
                                          include_suppressed=include_suppressed)

    def suppress_downstream(self, root_device, root_port, parent_event_id, ttl=None, now=None):
        now = time.time() if now is None else float(now)
        ttl = int(self.manager.settings.get("operational_suppression_ttl_seconds", 300)
                  if ttl is None else ttl)
        if ttl <= 0:
            return []
        try:
            impact = self.manager.downstream_impact(root_device, root_port or None,
                                                    max_depth=int(self.manager.settings.get("operational_impact_max_depth", 16)))
        except Exception:
            return []
        out = []
        for item in impact.get("devices") or []:
            target = item.get("device") or ""
            if not target or target == root_device:
                continue
            row = self.db.add_operational_suppression(
                now, now + ttl, root_device, root_port or "", target,
                int(parent_event_id), "upstream_link_down")
            out.append(row)
        return out

    def clear_upstream(self, root_device, root_port, now=None):
        return self.db.clear_operational_suppressions(
            root_device, root_port or "", time.time() if now is None else float(now))

    def suppressions(self, active_only=True):
        now = time.time()
        self.db.expire_operational_suppressions(now)
        return self.db.operational_suppressions(active_only=active_only, now=now)
