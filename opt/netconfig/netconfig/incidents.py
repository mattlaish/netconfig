"""Incident model, evidence links, and unified incident timeline.

Phase D.5/4A established durable incident lifecycle state and diagnostic-bundle
association. Phase D.5/4B adds reference-only links to existing authoritative
evidence and renders those references as a time-ordered incident timeline.

The link table never copies syslog messages, audit details, compliance reports,
collection output, or configuration text. Timeline reads dereference the original
store at request time. Drift evidence is pinned to immutable archived baseline
and current configuration stamps so later collections do not rewrite history.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

SEVERITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
STATUSES = ("OPEN", "INVESTIGATING", "RESOLVED", "CLOSED")
EVIDENCE_TYPES = ("audit", "syslog", "collection", "compliance", "drift", "protocol_trace")

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
            incident_key = f"INC-{datetime.fromtimestamp(now, timezone.utc).year}-{cur.lastrowid:06d}"
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

    # ---- Phase D.5/4B evidence references + timeline --------------------
    def _source_exists(self, source_type, source_ref):
        table = {
            "audit": "audit",
            "syslog": "syslog_events",
            "collection": "runs",
            "compliance": "compliance_runs",
            "protocol_trace": "protocol_trace_sessions",
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

    def link_evidence(self, ref, source_type, source_ref, actor, note=""):
        incident = self.get(ref)
        if not incident:
            raise ValueError("incident not found")
        source_type, source_ref = self._canonical_source_ref(source_type, source_ref)
        note = _note(note)
        now = time.time()
        self.conn.execute(
            "INSERT OR IGNORE INTO incident_evidence_links"
            "(incident_id,source_type,source_ref,linked_by,linked_ts,note) VALUES(?,?,?,?,?,?)",
            (incident["id"], source_type, source_ref, actor or "", now, note))
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
            "SELECT id,source_type,source_ref,linked_by,linked_ts,note "
            "FROM incident_evidence_links WHERE incident_id=? ORDER BY linked_ts,id",
            (incident_id,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["available"] = self._source_exists(item["source_type"], item["source_ref"])
            if item["source_type"] == "drift":
                try:
                    item["source_ref"] = json.loads(item["source_ref"])
                except json.JSONDecodeError:
                    pass
            out.append(item)
        return out

    def _resolve_evidence(self, link):
        source_type = link["source_type"]
        source_ref = link["source_ref"]
        base = {
            "kind": source_type,
            "source_type": source_type,
            "source_id": source_ref,
            "link_id": link["id"],
            "linked_by": link["linked_by"],
            "linked_ts": link["linked_ts"],
            "note": link["note"],
            "available": True,
        }
        if source_type == "audit":
            row = self.conn.execute("SELECT * FROM audit WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["ts"], actor=row["actor"], action=row["action"],
                            target=row["target"],
                            summary=f"audit {row['action']} target={row['target']}".strip())
        elif source_type == "syslog":
            row = self.conn.execute(
                "SELECT * FROM syslog_events WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["ts"], source=row["source"],
                            summary=f"syslog event from {row['source']}")
        elif source_type == "collection":
            row = self.conn.execute("SELECT * FROM runs WHERE id=?", (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                state = "OK" if row["ok"] else "FAILED"
                change = " changed" if row["changed"] else ""
                return dict(base, ts=row["ts"], device=row["device"], ok=bool(row["ok"]),
                            changed=bool(row["changed"]),
                            summary=f"collection {row['device']} {state}{change}")
        elif source_type == "compliance":
            row = self.conn.execute(
                "SELECT id,ts,standard,run_by,total,passed,failed FROM compliance_runs WHERE id=?",
                (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["ts"], standard=row["standard"], actor=row["run_by"],
                            total=row["total"], passed=row["passed"], failed=row["failed"],
                            summary=(f"compliance {row['standard'] or 'all'}: "
                                     f"{row['passed']} passed / {row['failed']} failed"))
        elif source_type == "protocol_trace":
            row = self.conn.execute(
                "SELECT id,trace_key,device,protocol,status,created_by,created_ts,expires_ts,"
                "event_count,bytes_count FROM protocol_trace_sessions WHERE id=?",
                (int(source_ref),)).fetchone()
            if row:
                row = dict(row)
                return dict(base, ts=row["created_ts"], actor=row["created_by"],
                            trace_key=row["trace_key"], device=row["device"],
                            protocol=row["protocol"], status=row["status"],
                            event_count=row["event_count"], bytes_count=row["bytes_count"],
                            summary=(f"protocol trace {row['trace_key']} "
                                     f"{row['protocol']} {row['device']} {row['status']}"))
        elif source_type == "drift" and self.config_store is not None:
            try:
                ref = json.loads(source_ref)
                baseline = self.config_store.read_version(ref["device"], ref["baseline_stamp"])
                current = self.config_store.read_version(ref["device"], ref["current_stamp"])
                drifted = baseline != current
                return dict(base, source_id=ref, ts=link["linked_ts"], device=ref["device"],
                            baseline_stamp=ref["baseline_stamp"], current_stamp=ref["current_stamp"],
                            drifted=drifted,
                            summary=(f"drift {ref['device']}: "
                                     f"{'DRIFTED' if drifted else 'in sync'} "
                                     f"{ref['baseline_stamp']} -> {ref['current_stamp']}"))
            except (KeyError, TypeError, json.JSONDecodeError, FileNotFoundError):
                pass
        return dict(base, available=False, ts=link["linked_ts"],
                    summary=f"{source_type} evidence no longer available")

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
            "actor": incident["created_by"],
            "summary": f"incident created: {incident['title']}",
            "available": True,
        }]
        # Incident-native audit events are authoritative and automatically part
        # of its timeline; operators do not need to create self-referential links.
        audits = self.conn.execute(
            "SELECT * FROM audit WHERE target=? ORDER BY ts,id", (incident["incident_key"],)).fetchall()
        native_audit_ids = set()
        for row in audits:
            row = dict(row)
            native_audit_ids.add(str(row["id"]))
            events.append({
                "kind": "incident_audit", "source_type": "audit", "source_id": str(row["id"]),
                "ts": row["ts"], "actor": row["actor"], "action": row["action"],
                "target": row["target"], "detail": row["detail"], "available": True,
                "summary": f"{row['action']}: {row['detail']}".rstrip(": "),
            })
        for bundle in self.bundles(incident["id"]):
            available = True
            if self.bundle_root is not None:
                available = (self.bundle_root / bundle["bundle_name"]).is_file()
            events.append({
                "kind": "bundle", "source_type": "bundle", "source_id": bundle["bundle_name"],
                "ts": bundle["linked_ts"], "actor": bundle["linked_by"], "available": available,
                "summary": f"diagnostic bundle linked: {bundle['bundle_name']}",
            })
        links = self.conn.execute(
            "SELECT * FROM incident_evidence_links WHERE incident_id=? ORDER BY linked_ts,id",
            (incident["id"],)).fetchall()
        for row in links:
            link = dict(row)
            if link["source_type"] == "audit" and link["source_ref"] in native_audit_ids:
                continue
            events.append(self._resolve_evidence(link))
        events.sort(key=lambda item: (float(item.get("ts") or 0), str(item.get("kind") or ""),
                                      str(item.get("source_id") or "")))
        return events[-limit:]
