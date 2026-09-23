"""Normalized operational evidence stream.

MC-3 keeps the existing durable NI-3 event/dependency-suppression behavior, but
adds a stable cross-domain semantic envelope used by later correlation slices.
Collectors remain responsible only for collection; normalization happens at this
boundary.  Sensor transitions are bridged from durable MC-2 transition rows, so
ordinary Sensor refreshes never create events.
"""
from __future__ import annotations

import hashlib
import json
import time


DOMAINS = {
    "NETWORK", "SECURITY", "APPLICATION", "DATABASE", "STORAGE",
    "SYSTEM", "CONFIGURATION", "IDENTITY", "EXTERNAL",
}

_SEVERITY_FOR_SENSOR_STATUS = {
    "OK": "INFO",
    "WARNING": "WARNING",
    "CRITICAL": "CRITICAL",
    # UNKNOWN means missing/insufficient evidence, not a failure verdict.
    "UNKNOWN": "INFO",
}


def _safe_text(value, limit=1024):
    text = str(value or "").replace("\x00", "")
    return text[:limit]


def _json_dict(value):
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _infer_domain(source_type, event_type, metadata):
    source_type = str(source_type or "").lower()
    event_type_u = str(event_type or "").upper()
    if event_type_u in {"CONFIG_CHANGE", "CONFIGURATION_CHANGE"}:
        return "CONFIGURATION"
    if "AUTH" in event_type_u or "LOGIN" in event_type_u or "SECURITY" in event_type_u:
        return "SECURITY"
    if source_type in {"snmp_trap", "snmp_poll", "sensor_transition", "netflow"}:
        return "NETWORK"
    if source_type == "syslog":
        if str((metadata or {}).get("protocol") or "").lower() == "syslog":
            return "SYSTEM"
    return "SYSTEM"


def _infer_entity(device, interface, ifindex, source, entity_type, entity_id):
    if entity_type:
        return _safe_text(entity_type, 64).lower(), _safe_text(entity_id, 255)
    if interface or ifindex:
        return "interface", _safe_text(interface or ifindex, 255)
    if device:
        return "device", _safe_text(device, 255)
    if source:
        return "source", _safe_text(source, 255)
    return "unknown", ""


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
               allow_suppression=True, domain="", entity_type="", entity_id="",
               resource="", status="OBSERVED", evidence_ref=""):
        """Normalize and persist one operational evidence record.

        Legacy callers may continue to provide the NI-3 fields only.  MC-3
        semantic fields are inferred at the event boundary and are persisted on
        every row.  A non-empty evidence_ref is treated as a durable idempotency
        reference, which is especially important for Sensor-transition bridging.
        """
        now = time.time() if now is None else float(now)
        dedup_seconds = int(self.manager.settings.get("operational_event_dedup_seconds", 30)
                            if dedup_seconds is None else dedup_seconds)
        meta = dict(metadata or {})
        # Explicit allow-list/bounds. Raw packets, community strings and arbitrary
        # secret material are never accepted by this storage boundary.
        clean_meta = {}
        for key in (
            "protocol", "version", "generic_trap", "specific_trap",
            "uptime_ticks", "if_admin_status", "if_oper_status",
            "source_port", "poll_ok", "reason",
            "transition_id", "sensor_key", "sensor_type",
            "previous_status", "new_status", "previous_value", "new_value",
            "transition_reason",
        ):
            if key in meta and meta[key] is not None:
                clean_meta[key] = _safe_text(meta[key], 512)

        device = _safe_text(device, 255)
        interface = _safe_text(interface, 255)
        ifindex = _safe_text(ifindex, 64)
        event_type = _safe_text(event_type, 128) or "EVENT"
        source_type = _safe_text(source_type, 32).lower() or "unknown"
        trap_oid = _safe_text(trap_oid, 255)
        source = _safe_text(source, 255)
        severity = _safe_text(severity, 16).upper() or "INFO"
        message = _safe_text(message, 2048)
        status = _safe_text(status, 32).upper() or "OBSERVED"
        evidence_ref = _safe_text(evidence_ref, 255)
        resource = _safe_text(resource or interface, 255)

        domain = _safe_text(domain, 32).upper()
        if domain not in DOMAINS:
            domain = _infer_domain(source_type, event_type, clean_meta)
        entity_type, entity_id = _infer_entity(
            device, interface, ifindex, source, entity_type, entity_id)

        if evidence_ref:
            existing = self.db.operational_event_by_evidence_ref(evidence_ref)
            if existing:
                existing["deduplicated"] = True
                return existing

        dedup_basis = "\x1f".join([
            source_type, source, device, event_type, domain, entity_type,
            entity_id, resource, interface, ifindex, trap_oid, message,
            evidence_ref,
        ])
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
            json.dumps(clean_meta, sort_keys=True, separators=(",", ":")),
            domain=domain, entity_type=entity_type, entity_id=entity_id,
            resource=resource, status=status, observed_at=now,
            evidence_ref=evidence_ref)
        row["deduplicated"] = False
        lifecycle = getattr(self.manager, "alert_lifecycle", None)
        if lifecycle is not None:
            lifecycle.observe_event(row, now=now)
            refreshed = self.db.conn.execute(
                "SELECT * FROM operational_events WHERE id=?", (int(row["id"]),)).fetchone()
            if refreshed:
                row = dict(refreshed)
                row["deduplicated"] = False
        return row

    @staticmethod
    def _sensor_event_semantics(transition):
        sensor_type = str(transition.get("sensor_type") or "")
        previous = str(transition.get("previous_status") or "UNKNOWN").upper()
        current = str(transition.get("new_status") or "UNKNOWN").upper()
        resource = str(transition.get("resource") or "")
        device = str(transition.get("device") or "")

        if sensor_type.startswith("interface."):
            entity_type = "interface"
            entity_id = resource
        elif sensor_type.startswith("endpoint."):
            entity_type = "device" if device else "network"
            entity_id = device or "global"
        else:
            entity_type = "device" if device else "network"
            entity_id = device or "global"

        if current == "UNKNOWN":
            event_type = f"{sensor_type}.evidence_unavailable" if sensor_type else "sensor.evidence_unavailable"
        elif sensor_type == "device.reachability":
            event_type = "device.reachable" if current == "OK" else "device.unreachable"
        elif sensor_type == "interface.status":
            event_type = "interface.up" if current == "OK" else "interface.down"
        elif previous in {"WARNING", "CRITICAL"} and current == "OK":
            event_type = f"{sensor_type}.recovered" if sensor_type else "sensor.recovered"
        else:
            suffix = current.lower()
            event_type = f"{sensor_type}.{suffix}" if sensor_type else f"sensor.{suffix}"

        return {
            "domain": "NETWORK",
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "resource": resource,
            "severity": _SEVERITY_FOR_SENSOR_STATUS.get(current, "INFO"),
            "status": current,
            "previous_status": previous,
            "new_status": current,
        }

    def record_sensor_transition(self, transition):
        """Bridge one durable MC-2 transition into normalized MC-3 evidence."""
        if not transition or not transition.get("id"):
            return None
        semantics = self._sensor_event_semantics(transition)
        metadata = _json_dict(transition.get("metadata_json"))
        sensor_type = str(transition.get("sensor_type") or "")
        previous = semantics["previous_status"]
        current = semantics["new_status"]
        resource = str(transition.get("resource") or "")
        device = str(transition.get("device") or "")
        transition_id = int(transition["id"])
        evidence_ref = f"sensor-transition:{transition_id}"
        message = f"{sensor_type or 'sensor'} {previous}→{current}"
        if resource:
            message += f" on {resource}"
        metadata.update({
            "transition_id": transition_id,
            "sensor_key": transition.get("sensor_key") or "",
            "sensor_type": sensor_type,
            "previous_status": previous,
            "new_status": current,
            "previous_value": transition.get("previous_value") or "",
            "new_value": transition.get("new_value") or "",
            "transition_reason": metadata.get("reason") or "status_change",
        })
        return self.record(
            source_type="sensor_transition",
            source=transition.get("source") or "SensorEngine",
            device=device,
            event_type=semantics["event_type"],
            severity=semantics["severity"],
            message=message,
            metadata=metadata,
            now=float(transition.get("observed_at") or time.time()),
            allow_suppression=True,
            domain=semantics["domain"],
            entity_type=semantics["entity_type"],
            entity_id=semantics["entity_id"],
            resource=semantics["resource"],
            status=semantics["status"],
            evidence_ref=evidence_ref,
        )

    def get(self, event_id):
        return self.db.operational_event(int(event_id))

    def list(self, limit=200, device=None, include_suppressed=True, domain=None,
             source_type=None, entity_type=None, status=None):
        self.db.expire_operational_suppressions(time.time())
        return self.db.operational_events(
            limit=limit, device=device, include_suppressed=include_suppressed,
            domain=domain, source_type=source_type, entity_type=entity_type,
            status=status)

    def related_sensor(self, event):
        """Return the current Sensor most closely related to an event, if any."""
        if not event:
            return None
        metadata = _json_dict(event.get("metadata"))
        sensor_type = str(metadata.get("sensor_type") or "")
        device = str(event.get("device") or "")
        resource = str(event.get("resource") or event.get("interface") or "")
        if not sensor_type and str(event.get("entity_type") or "") == "interface":
            sensor_type = "interface.status"
        if not sensor_type and str(event.get("event_type") or "").startswith("device."):
            sensor_type = "device.reachability"
        if not sensor_type:
            return None
        try:
            rows = self.manager.sensors.list(device=device or None, sensor_type=sensor_type, limit=500)
        except Exception:
            return None
        for row in rows:
            if str(row.get("resource") or "") == resource:
                return row
        if not resource and rows:
            return rows[0]
        return None

    def suppress_downstream(self, root_device, root_port, parent_event_id, ttl=None, now=None):
        now = time.time() if now is None else float(now)
        ttl = int(self.manager.settings.get("operational_suppression_ttl_seconds", 300)
                  if ttl is None else ttl)
        if ttl <= 0:
            return []
        try:
            impact = self.manager.downstream_impact(
                root_device, root_port or None,
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
