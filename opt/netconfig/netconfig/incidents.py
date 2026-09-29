"""Incident model, evidence links, and unified incident timeline.

Phase D.5/4A established durable incident lifecycle state and diagnostic-bundle
association. Phase D.5/4B added reference-only links to authoritative evidence.
MC-5 extends those links across monitoring, alert, change, analytics, and external
evidence and renders one deterministic cross-domain investigation timeline.

The link table never copies large authoritative payloads. It stores only typed
references plus bounded timestamp/clock metadata so late-arriving evidence keeps
its original ordering even when the referenced payload is later retained away.
Drift evidence remains pinned to immutable archived baseline/current stamps.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, UTC
from pathlib import Path

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
STATUSES = ("OPEN", "INVESTIGATING", "RESOLVED", "CLOSED")
EVIDENCE_TYPES = (
    "audit", "syslog", "collection", "compliance", "drift", "protocol_trace",
    "sensor_transition", "operational_event", "operational_alert", "change_event",
    "analytics_insight", "external_event",
)

_ALLOWED_TRANSITIONS = {
    "OPEN": {"INVESTIGATING", "RESOLVED", "CLOSED"},
    "INVESTIGATING": {"RESOLVED", "CLOSED"},
    "RESOLVED": {"INVESTIGATING", "CLOSED"},
    "CLOSED": {"INVESTIGATING"},
}


def _tags(value):
    if value is None:
        return []
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",")]
    out = []
    for item in value:
        item = str(item).strip()
        if item and item not in out:
            if len(item) > 64:
                raise ValueError("incident tag exceeds 64 characters")
            out.append(item)
    if len(out) > 32:
        raise ValueError("too many incident tags")
    return out


def _severity(value):
    value = str(value or "MEDIUM").upper()
    if value not in SEVERITIES:
        raise ValueError("invalid incident severity")
    return value


def _status(value):
    value = str(value or "").upper()
    if value not in STATUSES:
        raise ValueError("invalid incident status")
    return value


def _note(value):
    value = str(value or "").strip()
    if len(value) > 1000:
        raise ValueError("evidence note exceeds 1000 characters")
    return value


def _numeric_ref(value, label):
    text = str(value or "").strip()
    if not text.isdigit() or int(text) < 1:
        raise ValueError(f"invalid {label} evidence id")
    return str(int(text))


class Incidents:
    """Durable incident lifecycle service with reference-only evidence links."""

    def __init__(self, database, bundle_root=None, config_store=None):
        self.db = database
        self.conn = database.conn
        self.bundle_root = Path(bundle_root) if bundle_root else None
        self.config_store = config_store

    @staticmethod
    def _row(row):
        if not row:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except (TypeError, json.JSONDecodeError):
            d["tags"] = []
        return d

    def create(self, title, description="", severity="MEDIUM", created_by="", tags=None):
        title = str(title or "").strip()
        description = str(description or "").strip()
        if not title:
            raise ValueError("incident title is required")
        if len(title) > 200:
            raise ValueError("incident title exceeds 200 characters")
        if len(description) > 10000:
            raise ValueError("incident description exceeds 10000 characters")
        sev = _severity(severity)
        tag_list = _tags(tags)
        now = time.time()
        placeholder = "pending-" + secrets.token_hex(12)
        # The shared SQLite wrapper exposes its RLock so the generated human ID
        # and insert/update sequence cannot interleave inside this process.
        with self.conn.lock:
            cur = self.conn.execute(
                "INSERT INTO incidents(incident_key,title,description,severity,status,tags,"
                "created_by,created_ts,updated_by,updated_ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (placeholder, title, description, sev, "OPEN", json.dumps(tag_list),
                 created_by or "", now, created_by or "", now))
            incident_key = f"INC-{datetime.fromtimestamp(now, UTC).year}-{cur.lastrowid:06d}"
            self.conn.execute("UPDATE incidents SET incident_key=? WHERE id=?",
                              (incident_key, cur.lastrowid))
            self.conn.commit()
        self.db.audit(created_by, "incident_create", incident_key,
                      f"severity={sev};status=OPEN")
        return self.get(incident_key)

    def get(self, ref):
        text = str(ref or "").strip()
        if not text:
            return None
        if text.isdigit():
            row = self.conn.execute("SELECT * FROM incidents WHERE id=?", (int(text),)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM incidents WHERE incident_key=?", (text.upper(),)).fetchone()
        item = self._row(row)
        if item:
            item["bundles"] = self.bundles(item["id"])
            item["evidence_count"] = self.conn.execute(
                "SELECT COUNT(*) AS n FROM incident_evidence_links WHERE incident_id=?",
                (item["id"],)).fetchone()["n"]
        return item

    def list(self, status=None, severity=None, limit=100):
        limit = max(1, min(int(limit), 1000))
        q = "SELECT * FROM incidents WHERE 1=1"
        args = []
        if status:
            q += " AND status=?"
            args.append(_status(status))
        if severity:
            q += " AND severity=?"
            args.append(_severity(severity))
        q += " ORDER BY created_ts DESC, id DESC LIMIT ?"
        args.append(limit)
        return [self._row(r) for r in self.conn.execute(q, args).fetchall()]

    def update(self, ref, actor, *, title=None, description=None, severity=None, tags=None):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        fields = []
        values = []
        changed = []
        if title is not None:
            title = str(title).strip()
            if not title or len(title) > 200:
                raise ValueError("invalid incident title")
            fields.append("title=?")
            values.append(title)
            changed.append("title")
        if description is not None:
            description = str(description).strip()
            if len(description) > 10000:
                raise ValueError("incident description exceeds 10000 characters")
            fields.append("description=?")
            values.append(description)
            changed.append("description")
        if severity is not None:
            sev = _severity(severity)
            fields.append("severity=?")
            values.append(sev)
            changed.append("severity=" + sev)
        if tags is not None:
            tag_list = _tags(tags)
            fields.append("tags=?")
            values.append(json.dumps(tag_list))
            changed.append("tags")
        if not fields:
            return incident
        now = time.time()
        fields.extend(["updated_by=?", "updated_ts=?"])
        values.extend([actor or "", now, incident["id"]])
        self.conn.execute(f"UPDATE incidents SET {','.join(fields)} WHERE id=?", values)
        self.conn.commit()
        self.db.audit(actor, "incident_update", incident["incident_key"], ",".join(changed))
        return self.get(incident["id"])

    def set_status(self, ref, new_status, actor, note=""):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        new = _status(new_status)
        old = incident["status"]
        if new == old:
            return incident
        if new not in _ALLOWED_TRANSITIONS.get(old, set()):
            raise ValueError(f"invalid incident transition {old}->{new}")
        now = time.time()
        closed_by = actor or "" if new == "CLOSED" else None
        closed_ts = now if new == "CLOSED" else None
        self.conn.execute(
            "UPDATE incidents SET status=?,updated_by=?,updated_ts=?,closed_by=?,closed_ts=? WHERE id=?",
            (new, actor or "", now, closed_by, closed_ts, incident["id"]))
        self.conn.commit()
        detail = f"{old}->{new}"
        if note:
            detail += ";note=" + str(note).replace("\n", " ")[:500]
        self.db.audit(actor, "incident_status", incident["incident_key"], detail)
        return self.get(incident["id"])

    def _validated_bundle(self, bundle_name):
        name = Path(str(bundle_name or "")).name
        if not name or name != str(bundle_name) or not name.endswith(".tar.gz"):
            raise ValueError("invalid diagnostic bundle name")
        if self.bundle_root is not None:
            target = self.bundle_root / name
            if not target.is_file():
                raise ValueError("diagnostic bundle not found")
        return name

    def link_bundle(self, ref, bundle_name, actor):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        name = self._validated_bundle(bundle_name)
        now = time.time()
        self.conn.execute(
            "INSERT OR IGNORE INTO incident_bundles(incident_id,bundle_name,linked_by,linked_ts) "
            "VALUES(?,?,?,?)", (incident["id"], name, actor or "", now))
        self.conn.commit()
        self.db.audit(actor, "incident_bundle_link", incident["incident_key"], name)
        return self.get(incident["id"])

    def unlink_bundle(self, ref, bundle_name, actor):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        name = Path(str(bundle_name or "")).name
        self.conn.execute("DELETE FROM incident_bundles WHERE incident_id=? AND bundle_name=?",
                          (incident["id"], name))
        self.conn.commit()
        self.db.audit(actor, "incident_bundle_unlink", incident["incident_key"], name)
        return self.get(incident["id"])

    def bundles(self, incident_id):
        rows = self.conn.execute(
            "SELECT bundle_name,linked_by,linked_ts FROM incident_bundles "
            "WHERE incident_id=? ORDER BY linked_ts DESC,bundle_name", (int(incident_id),)).fetchall()
        return [dict(r) for r in rows]

    # ---- MC-5 typed evidence references + deterministic timeline ----------
    @staticmethod
    def _decode_json(raw):
        if isinstance(raw, dict):
            return dict(raw)
        try:
            value = json.loads(raw or "{}")
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _evidence_category(source_type, *, domain=""):
        source_type = str(source_type or "").lower()
        domain = str(domain or "").upper()
        if source_type in {"operational_alert"}:
            return "alerts"
        if source_type in {"change_event", "drift"} or domain == "CONFIGURATION":
            return "changes"
        if domain == "SECURITY":
            return "security"
        if domain == "NETWORK" or source_type in {"syslog", "protocol_trace"}:
            return "network"
        if domain in {"APPLICATION", "SYSTEM", "INFRASTRUCTURE"} or source_type in {
                "sensor_transition", "operational_event", "analytics_insight", "collection",
                "compliance"}:
            return "infrastructure"
        return "advanced"

    def _source_exists(self, source_type, source_ref):
        table = {
            "audit": "audit",
            "syslog": "syslog_events",
            "collection": "runs",
            "compliance": "compliance_runs",
            "protocol_trace": "protocol_trace_sessions",
            "sensor_transition": "sensor_transitions",
            "operational_event": "operational_events",
            "operational_alert": "operational_alerts",
            "change_event": "change_events",
            "analytics_insight": "network_insights",
            "external_event": "external_events",
        }.get(source_type)
        if table:
            row = self.conn.execute(
                f"SELECT id FROM {table} WHERE id=?", (int(source_ref),)).fetchone()
            return row is not None
        if source_type == "drift":
            if self.config_store is None:
                return False
            try:
                data = json.loads(source_ref)
                self.config_store.read_version(data["device"], data["baseline_stamp"])
                self.config_store.read_version(data["device"], data["current_stamp"])
                return True
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, FileNotFoundError):
                return False
        return False

    def _canonical_source_ref(self, source_type, source_ref):
        source_type = str(source_type or "").strip().lower()
        if source_type not in EVIDENCE_TYPES:
            raise ValueError("invalid incident evidence type")
        if source_type == "drift":
            if isinstance(source_ref, dict):
                data = source_ref
            else:
                try:
                    data = json.loads(str(source_ref or ""))
                except json.JSONDecodeError as exc:
                    raise ValueError("invalid drift evidence reference") from exc
            device = str(data.get("device") or "").strip()
            raw_baseline = str(data.get("baseline_stamp") or "")
            raw_current = str(data.get("current_stamp") or "")
            baseline = Path(raw_baseline).name
            current = Path(raw_current).name
            if (not device or not baseline or not current or baseline != raw_baseline
                    or current != raw_current or "/" in raw_baseline or "\\" in raw_baseline
                    or "/" in raw_current or "\\" in raw_current):
                raise ValueError("invalid drift evidence reference")
            source_ref = json.dumps({
                "baseline_stamp": baseline,
                "current_stamp": current,
                "device": device,
            }, sort_keys=True, separators=(",", ":"))
        else:
            source_ref = _numeric_ref(source_ref, source_type)
        if not self._source_exists(source_type, source_ref):
            raise ValueError(f"{source_type} evidence not found")
        return source_type, source_ref

    def _evidence_timing(self, source_type, source_ref, linked_ts):
        """Return bounded source/receive clock metadata without copying payloads."""
        source_ts = float(linked_ts)
        received_ts = float(linked_ts)
        clock = {"ordering": "link_time", "source_clock": "unknown"}
        if source_type == "drift":
            return source_ts, received_ts, clock
        table = {
            "audit": ("audit", "ts", None),
            "syslog": ("syslog_events", "ts", None),
            "collection": ("runs", "ts", None),
            "compliance": ("compliance_runs", "ts", None),
            "protocol_trace": ("protocol_trace_sessions", "created_ts", None),
            "sensor_transition": ("sensor_transitions", "observed_at", "created_at"),
            "operational_event": ("operational_events", "observed_at", "last_ts"),
            "operational_alert": ("operational_alerts", "first_ts", "last_ts"),
            "change_event": ("change_events", "source_ts", "received_ts"),
            "analytics_insight": ("network_insights", "first_seen_ts", "last_seen_ts"),
            "external_event": ("external_events", "source_ts", "received_ts"),
        }.get(source_type)
        if not table:
            return source_ts, received_ts, clock
        table_name, source_col, receive_col = table
        cols = f"{source_col} AS source_ts"
        if receive_col:
            cols += f",{receive_col} AS received_ts"
        if source_type == "external_event":
            cols += ",source_clock_json"
        row = self.conn.execute(
            f"SELECT {cols} FROM {table_name} WHERE id=?", (int(source_ref),)).fetchone()
        if not row:
            return source_ts, received_ts, clock
        row = dict(row)
        source_ts = float(row.get("source_ts") or linked_ts)
        received_ts = float(row.get("received_ts") or linked_ts)
        clock = {"ordering": "source_time", "source_clock": "managed"}
        if source_type == "external_event":
            clock = self._decode_json(row.get("source_clock_json"))
            clock.setdefault("ordering", "source_time")
            clock.setdefault("source_clock", "external")
        return source_ts, received_ts, clock

    def link_evidence(self, ref, source_type, source_ref, actor, note=""):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        source_type, source_ref = self._canonical_source_ref(source_type, source_ref)
        note = _note(note)
        now = time.time()
        source_ts, received_ts, source_clock = self._evidence_timing(source_type, source_ref, now)
        clock_json = json.dumps(source_clock, sort_keys=True, separators=(",", ":"))
        self.conn.execute(
            "INSERT OR IGNORE INTO incident_evidence_links"
            "(incident_id,source_type,source_ref,linked_by,linked_ts,source_ts,received_ts,"
            "source_clock_json,note) VALUES(?,?,?,?,?,?,?,?,?)",
            (incident["id"], source_type, source_ref, actor or "", now, source_ts, received_ts,
             clock_json, note))
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id FROM incident_evidence_links WHERE incident_id=? AND source_type=? AND source_ref=?",
            (incident["id"], source_type, source_ref)).fetchone()
        self.db.audit(actor, "incident_evidence_link", incident["incident_key"],
                      f"{source_type}:{source_ref[:300]}")
        return dict(self.conn.execute(
            "SELECT * FROM incident_evidence_links WHERE id=?", (row["id"],)).fetchone())

    def link_drift(self, ref, device, actor, note=""):
        if self.config_store is None:
            raise ValueError("drift evidence store unavailable")
        device = str(device or "").strip()
        baseline = self.config_store.get_baseline(device)
        versions = self.config_store.versions(device)
        if not baseline:
            raise ValueError("device has no baseline")
        if not versions:
            raise ValueError("device has no archived current configuration")
        source_ref = {
            "device": device,
            "baseline_stamp": baseline.get("stamp"),
            "current_stamp": versions[-1].get("stamp"),
        }
        return self.link_evidence(ref, "drift", source_ref, actor, note)

    def unlink_evidence(self, ref, link_id, actor):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        row = self.conn.execute(
            "SELECT * FROM incident_evidence_links WHERE id=? AND incident_id=?",
            (int(link_id), incident["id"])).fetchone()
        if not row:
            raise ValueError("incident evidence link not found")
        self.conn.execute("DELETE FROM incident_evidence_links WHERE id=?", (int(link_id),))
        self.conn.commit()
        self.db.audit(actor, "incident_evidence_unlink", incident["incident_key"],
                      f"{row['source_type']}:{row['source_ref'][:300]}")
        return self.evidence_links(incident["id"])

    def evidence_links(self, incident_ref):
        incident = self.get(incident_ref) if not isinstance(incident_ref, int) else None
        incident_id = incident["id"] if incident else int(incident_ref)
        rows = self.conn.execute(
            "SELECT id,source_type,source_ref,linked_by,linked_ts,source_ts,received_ts,"
            "source_clock_json,note FROM incident_evidence_links WHERE incident_id=? "
            "ORDER BY source_ts,received_ts,id",
            (incident_id,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["available"] = self._source_exists(item["source_type"], item["source_ref"])
            item["source_clock"] = self._decode_json(item.pop("source_clock_json", "{}"))
            if item["source_type"] == "drift":
                try:
                    item["source_ref"] = json.loads(item["source_ref"])
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out

    def _base_evidence(self, link, *, domain="", category=""):
        source_type = link["source_type"]
        clock = self._decode_json(link.get("source_clock_json"))
        return {
            "kind": source_type,
            "source_type": source_type,
            "source_id": link["source_ref"],
            "link_id": link["id"],
            "linked_by": link["linked_by"],
            "linked_ts": link["linked_ts"],
            "source_ts": float(link.get("source_ts") or link["linked_ts"]),
            "received_ts": float(link.get("received_ts") or link["linked_ts"]),
            "source_clock": clock,
            "note": link["note"],
            "domain": domain or "",
            "category": category or self._evidence_category(source_type, domain=domain),
            "available": True,
        }

    def _resolve_evidence(self, link):
        source_type = link["source_type"]
        source_ref = link["source_ref"]
        base = self._base_evidence(link)
        if source_type == "audit":
            row = self.conn.execute("SELECT * FROM audit WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                domain = "CONFIGURATION" if "change" in str(row["action"]).lower() else "SYSTEM"
                return dict(base, ts=row["ts"], source_ts=row["ts"], actor=row["actor"],
                            action=row["action"], target=row["target"], domain=domain,
                            category=self._evidence_category(source_type, domain=domain),
                            summary=f"audit {row['action']} target={row['target']}".strip())
        elif source_type == "syslog":
            row = self.conn.execute(
                "SELECT * FROM syslog_events WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["ts"], source_ts=row["ts"], source=row["source"],
                            domain="NETWORK", category="network",
                            summary=f"syslog event from {row['source']}")
        elif source_type == "collection":
            row = self.conn.execute("SELECT * FROM runs WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                state = "OK" if row["ok"] else "FAILED"
                change = " changed" if row["changed"] else ""
                return dict(base, ts=row["ts"], source_ts=row["ts"], device=row["device"],
                            ok=bool(row["ok"]), changed=bool(row["changed"]), domain="SYSTEM",
                            category="infrastructure",
                            summary=f"collection {row['device']} {state}{change}")
        elif source_type == "compliance":
            row = self.conn.execute(
                "SELECT id,ts,standard,run_by,total,passed,failed FROM compliance_runs WHERE id=?",
                (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["ts"], source_ts=row["ts"], standard=row["standard"],
                            actor=row["run_by"], total=row["total"], passed=row["passed"],
                            failed=row["failed"], domain="SYSTEM", category="infrastructure",
                            summary=(f"compliance {row['standard'] or 'all'}: "
                                     f"{row['passed']} passed / {row['failed']} failed"))
        elif source_type == "protocol_trace":
            row = self.conn.execute(
                "SELECT id,trace_key,device,protocol,status,created_by,created_ts,expires_ts,"
                "event_count,bytes_count FROM protocol_trace_sessions WHERE id=?",
                (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["created_ts"], source_ts=row["created_ts"],
                            actor=row["created_by"], trace_key=row["trace_key"], device=row["device"],
                            protocol=row["protocol"], status=row["status"], domain="NETWORK",
                            category="network", event_count=row["event_count"],
                            bytes_count=row["bytes_count"],
                            summary=(f"protocol trace {row['trace_key']} "
                                     f"{row['protocol']} {row['device']} {row['status']}"))
        elif source_type == "sensor_transition":
            row = self.conn.execute(
                "SELECT * FROM sensor_transitions WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                sensor_type = row.get("sensor_type") or "sensor"
                domain = "APPLICATION" if sensor_type.startswith("application.") else "NETWORK"
                if sensor_type.startswith("service."):
                    domain = "SYSTEM"
                return dict(base, ts=row["observed_at"], source_ts=row["observed_at"],
                            device=row.get("device") or "", resource=row.get("resource") or "",
                            sensor_type=sensor_type, previous_status=row.get("previous_status") or "",
                            status=row.get("new_status") or "", domain=domain,
                            category=self._evidence_category(source_type, domain=domain),
                            summary=(f"{sensor_type} {row.get('previous_status') or 'UNKNOWN'} → "
                                     f"{row.get('new_status') or 'UNKNOWN'} "
                                     f"{row.get('device') or row.get('resource') or ''}").strip())
        elif source_type == "operational_event":
            row = self.conn.execute(
                "SELECT * FROM operational_events WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                domain = str(row.get("domain") or "SYSTEM").upper()
                return dict(base, ts=row.get("observed_at") or row["last_ts"],
                            source_ts=row.get("observed_at") or row["last_ts"],
                            received_ts=max(float(base["received_ts"]), float(row["last_ts"] or 0)),
                            device=row.get("device") or "", entity_type=row.get("entity_type") or "",
                            entity_id=row.get("entity_id") or "", resource=row.get("resource") or "",
                            event_type=row.get("event_type") or "", severity=row.get("severity") or "",
                            status=row.get("status") or "", domain=domain,
                            category=self._evidence_category(source_type, domain=domain),
                            summary=(row.get("message") or row.get("event_type") or "operational event")[:1000])
        elif source_type == "operational_alert":
            row = self.conn.execute(
                "SELECT * FROM operational_alerts WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["first_ts"], source_ts=row["first_ts"],
                            received_ts=max(float(base["received_ts"]), float(row["last_ts"] or 0)),
                            device=row.get("device") or "", event_type=row.get("event_type") or "",
                            severity=row.get("severity") or "", status=row.get("state") or "",
                            domain="ALERT", category="alerts",
                            summary=(f"alert {row.get('state') or ''} {row.get('severity') or ''} "
                                     f"{row.get('device') or ''} {row.get('event_type') or ''}").strip())
        elif source_type == "change_event":
            row = self.conn.execute(
                "SELECT * FROM change_events WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["source_ts"], source_ts=row["source_ts"],
                            received_ts=row["received_ts"], actor=row.get("actor") or "",
                            request_id=row.get("request_id"), event_type=row.get("event_type") or "",
                            status=row.get("status") or "", domain="CONFIGURATION", category="changes",
                            summary=row.get("summary") or f"change {row.get('event_type') or ''}")
        elif source_type == "analytics_insight":
            row = self.conn.execute(
                "SELECT * FROM network_insights WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["first_seen_ts"], source_ts=row["first_seen_ts"],
                            received_ts=max(float(base["received_ts"]), float(row["last_seen_ts"] or 0)),
                            insight_type=row.get("insight_type") or "", object_type=row.get("object_type") or "",
                            entity_id=row.get("object_id") or "", severity=row.get("severity") or "",
                            status=row.get("state") or "", confidence=float(row.get("confidence") or 0),
                            domain="NETWORK", category="network",
                            summary=row.get("summary") or row.get("insight_type") or "analytics insight")
        elif source_type == "external_event":
            row = self.conn.execute(
                "SELECT * FROM external_events WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                domain = str(row.get("domain") or "EXTERNAL").upper()
                clock = self._decode_json(row.get("source_clock_json"))
                metadata = self._decode_json(row.get("metadata_json"))
                payload = self._decode_json(row.get("payload_json"))
                return dict(base, ts=row["source_ts"], source_ts=row["source_ts"],
                            received_ts=row["received_ts"], source_clock=clock,
                            source_system=row.get("source_system") or "",
                            source_key=row.get("source_key") or row.get("source_system") or "",
                            source_event_id=row.get("source_event_id") or "",
                            event_type=row.get("event_type") or "", severity=row.get("severity") or "",
                            entity_type=row.get("entity_type") or "", entity_id=row.get("entity_id") or "",
                            domain=domain, category=self._evidence_category(source_type, domain=domain),
                            advanced={"metadata": metadata, "payload": payload,
                                      "payload_sha256": row.get("payload_sha256") or "",
                                      "schema_version": row.get("schema_version") or "1"},
                            summary=row.get("summary") or row.get("event_type") or "external event")
        elif source_type == "drift" and self.config_store is not None:
            try:
                ref = json.loads(source_ref)
                baseline = self.config_store.read_version(ref["device"], ref["baseline_stamp"])
                current = self.config_store.read_version(ref["device"], ref["current_stamp"])
                drifted = baseline != current
                return dict(base, source_id=ref, ts=base["source_ts"], device=ref["device"],
                            baseline_stamp=ref["baseline_stamp"], current_stamp=ref["current_stamp"],
                            drifted=drifted, domain="CONFIGURATION", category="changes",
                            summary=(f"drift {ref['device']}: "
                                     f"{'DRIFTED' if drifted else 'in sync'} "
                                     f"{ref['baseline_stamp']} -> {ref['current_stamp']}"))
            except (KeyError, TypeError, json.JSONDecodeError, FileNotFoundError):
                pass
        return dict(base, available=False, ts=base["source_ts"],
                    summary=f"{source_type} evidence no longer available")

    @staticmethod
    def _sort_source_id(value):
        text = str(value or "")
        return (0, int(text)) if text.isdigit() else (1, text)

    def timeline(self, ref, limit=500):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        limit = max(1, min(int(limit), 2000))
        events = [{
            "kind": "incident",
            "source_type": "incident",
            "source_id": incident["incident_key"],
            "ts": incident["created_ts"],
            "source_ts": incident["created_ts"],
            "received_ts": incident["created_ts"],
            "source_clock": {"ordering": "local_time", "source_clock": "managed"},
            "category": "advanced",
            "actor": incident["created_by"],
            "summary": f"incident created: {incident['title']}",
            "available": True,
        }]
        # Incident-native audit events are authoritative and automatically part
        # of its timeline; operators do not need self-referential evidence links.
        audits = self.conn.execute(
            "SELECT * FROM audit WHERE target=? ORDER BY ts,id", (incident["incident_key"],)).fetchall()
        native_audit_ids = set()
        for row in audits:
            row = dict(row)
            native_audit_ids.add(str(row["id"]))
            events.append({
                "kind": "incident_audit", "source_type": "audit", "source_id": str(row["id"]),
                "ts": row["ts"], "source_ts": row["ts"], "received_ts": row["ts"],
                "source_clock": {"ordering": "local_time", "source_clock": "managed"},
                "category": "advanced", "actor": row["actor"], "action": row["action"],
                "target": row["target"], "detail": row["detail"], "available": True,
                "summary": f"{row['action']}: {row['detail']}".rstrip(": "),
            })
        for bundle in self.bundles(incident["id"]):
            available = True
            if self.bundle_root is not None:
                available = (self.bundle_root / bundle["bundle_name"]).is_file()
            events.append({
                "kind": "bundle", "source_type": "bundle", "source_id": bundle["bundle_name"],
                "ts": bundle["linked_ts"], "source_ts": bundle["linked_ts"],
                "received_ts": bundle["linked_ts"], "category": "advanced",
                "source_clock": {"ordering": "link_time", "source_clock": "managed"},
                "actor": bundle["linked_by"], "available": available,
                "summary": f"diagnostic bundle linked: {bundle['bundle_name']}",
            })
        links = self.conn.execute(
            "SELECT * FROM incident_evidence_links WHERE incident_id=? ORDER BY source_ts,received_ts,id",
            (incident["id"],)).fetchall()
        for row in links:
            link = dict(row)
            if link["source_type"] == "audit" and link["source_ref"] in native_audit_ids:
                continue
            events.append(self._resolve_evidence(link))
        # Source timestamp is authoritative for chronology. received_ts preserves
        # late-arrival ordering as a deterministic tie-breaker, followed by a
        # stable source-type/source-id/link-id order for equal timestamps.
        events.sort(key=lambda item: (
            float(item.get("source_ts") or item.get("ts") or 0),
            float(item.get("received_ts") or item.get("linked_ts") or 0),
            str(item.get("source_type") or item.get("kind") or ""),
            self._sort_source_id(item.get("source_id")),
            int(item.get("link_id") or 0),
        ))
        return events[-limit:]

    def investigation_view(self, ref, limit=500):
        """Return operator-oriented MC-5 groupings without inferring causation."""
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        timeline = self.timeline(ref, limit)
        groups = {name: [] for name in (
            "alerts", "changes", "network", "security", "infrastructure", "advanced")}
        affected = []
        seen = set()
        for item in timeline:
            category = item.get("category") or "advanced"
            groups.setdefault(category, []).append(item)
            for key in ("device", "entity_id", "resource", "source"):
                value = str(item.get(key) or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    affected.append(value)
        return {
            "incident": incident,
            "impact": {"affected_entities": affected[:200], "evidence_count": len(timeline)},
            "timeline": timeline,
            "related_alerts": groups["alerts"],
            "related_changes": groups["changes"],
            "network_evidence": groups["network"],
            "security_evidence": groups["security"],
            "infrastructure_evidence": groups["infrastructure"],
            "advanced_evidence": groups["advanced"],
            "root_cause": None,
            "root_cause_state": "NOT_EVALUATED",
        }

