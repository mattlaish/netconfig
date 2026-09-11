"""Bounded protocol-trace evidence for D.5 Phase 4E.

Trace capture is metadata-only by design.  It records protocol operations,
outcomes, timing and byte counts without storing credentials, raw SSH terminal
output, SNMP packets/community strings, or protocol authentication material.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from datetime import datetime, timezone

PROTOCOLS = ("cli_ssh", "snmp", "netconf", "restconf", "gnmi")
IMPLEMENTED_CAPTURE_PROTOCOLS = ("cli_ssh", "snmp", "netconf", "restconf", "gnmi")
STATUSES = ("ACTIVE", "STOPPED", "EXPIRED", "LIMIT_REACHED")
DEFAULT_TTL = 900
MAX_TTL = 3600
DEFAULT_MAX_EVENTS = 500
MAX_EVENTS = 5000
DEFAULT_MAX_BYTES = 1024 * 1024
MAX_BYTES = 8 * 1024 * 1024

_SENSITIVE_COMMAND = re.compile(
    r"(?i)(password|passwd|secret|community|private[-_ ]?key|pre[-_ ]?shared[-_ ]?key|"
    r"auth(?:entication)?[-_ ]?key|priv(?:acy)?[-_ ]?key|encrypted[-_ ]?password|"
    r"plain(?:text)?[-_ ]?password|client[-_ ]?secret|api[-_ ]?token|"
    r"snmp(?:-server)?\s+community|username\s+\S+\s+(password|secret))"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|community|client[_-]?secret|api[_-]?token|"
    r"auth[_-]?pass|priv[_-]?pass)(\s*[:=]\s*)([^\s,;]+)"
)


def safe_command(command):
    """Return a bounded non-secret command summary plus a stable hash."""
    raw = str(command or "").strip()
    digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()
    if not raw:
        return "", digest
    if _SENSITIVE_COMMAND.search(raw):
        # Do not persist a hash of secret-bearing command material: low-entropy
        # secrets could otherwise be dictionary-tested offline.
        marker = "<redacted-sensitive-command>"
        return marker, hashlib.sha256(marker.encode()).hexdigest()
    raw = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", raw)
    return raw[:240], digest


def _sanitize(value, depth=0):
    if depth > 6:
        return "<truncated>"
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            k = str(key)[:80]
            if any(word in k.lower() for word in (
                    "password", "passwd", "secret", "community", "token", "private",
                    "auth_pass", "priv_pass", "credential")):
                out[k] = "<redacted>"
            else:
                out[k] = _sanitize(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(x, depth + 1) for x in value[:100]]
    if isinstance(value, bytes):
        return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", str(value))
    return text[:1000]


class ProtocolTraceStore:
    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn

    @staticmethod
    def _row(row):
        if not row:
            return None
        item = dict(row)
        item["max_events"] = int(item.get("max_events") or 0)
        item["max_bytes"] = int(item.get("max_bytes") or 0)
        item["event_count"] = int(item.get("event_count") or 0)
        item["bytes_count"] = int(item.get("bytes_count") or 0)
        return item

    def _expire(self):
        now = time.time()
        rows = self.conn.execute(
            "SELECT id,trace_key FROM protocol_trace_sessions WHERE status='ACTIVE' AND expires_ts<=?",
            (now,)).fetchall()
        if rows:
            self.conn.execute(
                "UPDATE protocol_trace_sessions SET status='EXPIRED',stopped_ts=? "
                "WHERE status='ACTIVE' AND expires_ts<=?", (now, now))
            self.conn.commit()
            for row in rows:
                self.db.audit("system", "protocol_trace_expire", row["trace_key"], "ttl elapsed")

    def start(self, device, protocol, actor="", incident_ref=None, ttl=DEFAULT_TTL,
              max_events=DEFAULT_MAX_EVENTS, max_bytes=DEFAULT_MAX_BYTES, reason=""):
        device = str(device or "").strip()
        protocol = str(protocol or "").strip().lower()
        reason = str(_sanitize(str(reason or "").strip()))[:1000]
        if protocol not in PROTOCOLS:
            raise ValueError("unsupported trace protocol")
        if protocol not in IMPLEMENTED_CAPTURE_PROTOCOLS:
            raise ValueError(f"trace provider not implemented for {protocol}")
        if not device:
            raise ValueError("trace device is required")
        if not self.manager.inv.get(device):
            raise ValueError("unknown device")
        ttl = int(ttl)
        max_events = int(max_events)
        max_bytes = int(max_bytes)
        if ttl < 30 or ttl > MAX_TTL:
            raise ValueError(f"trace ttl must be 30..{MAX_TTL} seconds")
        if max_events < 1 or max_events > MAX_EVENTS:
            raise ValueError(f"trace max-events must be 1..{MAX_EVENTS}")
        if max_bytes < 4096 or max_bytes > MAX_BYTES:
            raise ValueError(f"trace max-bytes must be 4096..{MAX_BYTES}")
        incident = None
        if incident_ref:
            incident = self.manager.incidents.get(incident_ref)
            if not incident:
                raise ValueError("incident not found")
        now = time.time()
        key = f"PTR-{datetime.fromtimestamp(now, timezone.utc).year}-{secrets.token_hex(6).upper()}"
        cur = self.conn.execute(
            "INSERT INTO protocol_trace_sessions(trace_key,device,protocol,incident_id,status,"
            "created_by,created_ts,expires_ts,reason,max_events,max_bytes,event_count,bytes_count) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, device, protocol, incident["id"] if incident else None, "ACTIVE", actor or "",
             now, now + ttl, reason, max_events, max_bytes, 0, 0))
        self.conn.commit()
        item = self.get(cur.lastrowid)
        self.db.audit(actor, "protocol_trace_start", key,
                      f"device={device};protocol={protocol};ttl={ttl};incident={incident_ref or ''}")
        if incident:
            self.manager.incidents.link_evidence(
                incident["incident_key"], "protocol_trace", str(item["id"]), actor,
                note=f"protocol trace {key}")
        return item

    def get(self, ref):
        self._expire()
        text = str(ref or "").strip()
        if text.isdigit():
            row = self.conn.execute("SELECT * FROM protocol_trace_sessions WHERE id=?", (int(text),)).fetchone()
        else:
            row = self.conn.execute("SELECT * FROM protocol_trace_sessions WHERE trace_key=?", (text,)).fetchone()
        return self._row(row)

    def list(self, device=None, incident_ref=None, status=None, limit=200):
        self._expire()
        q = "SELECT * FROM protocol_trace_sessions WHERE 1=1"
        args = []
        if device:
            q += " AND device=?"; args.append(device)
        if incident_ref:
            incident = self.manager.incidents.get(incident_ref)
            if not incident:
                raise ValueError("incident not found")
            q += " AND incident_id=?"; args.append(incident["id"])
        if status:
            status = str(status).upper()
            if status not in STATUSES:
                raise ValueError("invalid trace status")
            q += " AND status=?"; args.append(status)
        q += " ORDER BY created_ts DESC,id DESC LIMIT ?"; args.append(max(1, min(int(limit), 1000)))
        return [self._row(row) for row in self.conn.execute(q, args).fetchall()]

    def stop(self, ref, actor=""):
        item = self.get(ref)
        if not item:
            raise ValueError("protocol trace not found")
        if item["status"] == "ACTIVE":
            now = time.time()
            self.conn.execute(
                "UPDATE protocol_trace_sessions SET status='STOPPED',stopped_by=?,stopped_ts=? WHERE id=?",
                (actor or "", now, item["id"]))
            self.conn.commit()
            self.db.audit(actor, "protocol_trace_stop", item["trace_key"], "")
        return self.get(item["id"])

    def events(self, ref, limit=1000):
        item = self.get(ref)
        if not item:
            raise ValueError("protocol trace not found")
        rows = self.conn.execute(
            "SELECT * FROM protocol_trace_events WHERE session_id=? ORDER BY seq,id LIMIT ?",
            (item["id"], max(1, min(int(limit), MAX_EVENTS)))).fetchall()
        out = []
        for row in rows:
            event = dict(row)
            try:
                event["metadata"] = json.loads(event.get("metadata") or "{}")
            except json.JSONDecodeError:
                event["metadata"] = {}
            out.append(event)
        return out

    def _active(self, device, protocol):
        self._expire()
        return [self._row(r) for r in self.conn.execute(
            "SELECT * FROM protocol_trace_sessions WHERE status='ACTIVE' AND device=? AND protocol=? "
            "ORDER BY id", (device, protocol)).fetchall()]

    def record(self, device, protocol, event_type, operation="", status="ok", duration_ms=None,
               tx_bytes=0, rx_bytes=0, metadata=None):
        sessions = self._active(str(device or ""), str(protocol or ""))
        if not sessions:
            return 0
        safe_operation, command_hash = safe_command(operation)
        meta = _sanitize(dict(metadata or {}))
        if operation:
            meta.setdefault("operation_sha256", command_hash)
        encoded = json.dumps(meta, sort_keys=True, separators=(",", ":"))
        event_size = len(encoded.encode("utf-8")) + len(safe_operation.encode("utf-8"))
        written = 0
        for session in sessions:
            if session["event_count"] >= session["max_events"] or session["bytes_count"] + event_size > session["max_bytes"]:
                self.conn.execute(
                    "UPDATE protocol_trace_sessions SET status='LIMIT_REACHED',stopped_ts=? WHERE id=?",
                    (time.time(), session["id"]))
                self.conn.commit()
                self.db.audit("system", "protocol_trace_limit", session["trace_key"], "capture budget reached")
                continue
            seq = session["event_count"] + 1
            self.conn.execute(
                "INSERT INTO protocol_trace_events(session_id,seq,ts,event_type,operation,status,duration_ms,"
                "tx_bytes,rx_bytes,metadata) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (session["id"], seq, time.time(), str(event_type)[:80], safe_operation,
                 str(status or "")[:40], None if duration_ms is None else float(duration_ms),
                 max(0, int(tx_bytes or 0)), max(0, int(rx_bytes or 0)), encoded))
            self.conn.execute(
                "UPDATE protocol_trace_sessions SET event_count=event_count+1,bytes_count=bytes_count+? WHERE id=?",
                (event_size, session["id"]))
            self.conn.commit()
            written += 1
        return written

    def callback(self, device, protocol):
        if not self._active(device, protocol):
            return None
        def emit(event):
            event = dict(event or {})
            self.record(
                device, protocol, event.pop("event_type", "protocol"),
                operation=event.pop("operation", ""), status=event.pop("status", "ok"),
                duration_ms=event.pop("duration_ms", None), tx_bytes=event.pop("tx_bytes", 0),
                rx_bytes=event.pop("rx_bytes", 0), metadata=event)
        return emit

    def export_for_incident(self, incident_id, max_sessions=100, max_events_per_session=2000):
        rows = self.conn.execute(
            "SELECT DISTINCT s.* FROM protocol_trace_sessions s "
            "JOIN incident_evidence_links l ON l.source_type='protocol_trace' "
            "AND CAST(l.source_ref AS INTEGER)=s.id WHERE l.incident_id=? "
            "ORDER BY s.created_ts,s.id LIMIT ?", (int(incident_id), int(max_sessions))).fetchall()
        result = []
        for row in rows:
            session = self._row(row)
            result.append({"session": session, "events": self.events(session["id"], max_events_per_session)})
        return result
