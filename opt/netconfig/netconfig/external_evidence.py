"""MC-8 authenticated external evidence ingestion and connector health.

The first connector plane is intentionally inbound/read-only: external products
push normalized evidence into NetConfig.  A connector source is bound to one
scoped API token and cannot reconfigure the external product, execute response
actions, or gain device/change execution authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import deque

SOURCE_TYPES = (
    "NDR", "WAF", "SIEM", "EDR", "APM", "DATABASE", "STORAGE",
    "VIRTUALIZATION", "CLOUD",
)
SEVERITIES = {"DEBUG", "INFO", "NOTICE", "WARNING", "MINOR", "MAJOR", "ERROR", "CRITICAL"}
DOMAINS = {"SECURITY", "NETWORK", "APPLICATION", "INFRASTRUCTURE", "SYSTEM", "CONFIGURATION", "EXTERNAL"}
DEFAULT_DOMAIN = {
    "NDR": "SECURITY", "WAF": "SECURITY", "SIEM": "SECURITY", "EDR": "SECURITY",
    "APM": "APPLICATION", "DATABASE": "INFRASTRUCTURE", "STORAGE": "INFRASTRUCTURE",
    "VIRTUALIZATION": "INFRASTRUCTURE", "CLOUD": "INFRASTRUCTURE",
}
_SOURCE_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,127}$")
_EVENT_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SENSITIVE = re.compile(
    r"(^|[_-])(password|passwd|pwd|secret|token|authorization|api[_-]?key|client[_-]?secret|cookie|bearer|credential)([_-]|$)",
    re.I,
)
_GLOBAL_MAX_PAYLOAD = 262144
_DEFAULT_MAX_PAYLOAD = 65536
_DEFAULT_RATE = 120


class ExternalEvidenceError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = str(code)
        self.status = int(status)


def _text(value, limit):
    return str(value or "").replace("\x00", "").strip()[:limit]


def _tenant(value="default"):
    tenant = _text(value or "default", 128) or "default"
    if tenant != "default":
        raise ExternalEvidenceError("TENANT_SCOPE_UNAVAILABLE", "tenant scope is not available in this deployment", 400)
    return tenant


def _decode(value, default):
    if isinstance(value, type(default)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def redact_external(value, *, depth=0):
    """Recursively redact secret-bearing keys from untrusted external payloads."""
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        out = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= 256:
                out["_truncated"] = True
                break
            name = _text(key, 128)
            out[name] = "[REDACTED]" if _SENSITIVE.search(name) else redact_external(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        items = [redact_external(item, depth=depth + 1) for item in value[:256]]
        if len(value) > 256:
            items.append("[TRUNCATED]")
        return items
    if isinstance(value, str):
        return value.replace("\x00", "")[:8192]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _text(value, 8192)


class ExternalEvidenceService:
    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self._rate_lock = threading.RLock()
        self._rate = {}
        self._ingest_lock_guard = threading.Lock()
        self._ingest_locks = {}

    @staticmethod
    def global_payload_limit():
        return _GLOBAL_MAX_PAYLOAD

    def _source_key(self, value):
        key = _text(value, 128).lower()
        if not _SOURCE_KEY.fullmatch(key):
            raise ExternalEvidenceError("INVALID_SOURCE_KEY", "source_key must use lowercase letters, digits, dot, colon, underscore or hyphen")
        return key

    @staticmethod
    def _source_type(value):
        source_type = _text(value, 32).upper()
        if source_type not in SOURCE_TYPES:
            raise ExternalEvidenceError("UNKNOWN_SOURCE_TYPE", "unsupported external source type")
        return source_type

    def _row(self, row):
        if not row:
            return None
        item = dict(row)
        for key in ("enabled",):
            item[key] = bool(item.get(key))
        item["max_payload_bytes"] = int(item.get("max_payload_bytes") or _DEFAULT_MAX_PAYLOAD)
        item["rate_limit_per_minute"] = int(item.get("rate_limit_per_minute") or _DEFAULT_RATE)
        item.pop("token_scopes", None)
        disabled = item.get("token_disabled")
        if disabled is not None and bool(disabled):
            item["auth_state"] = "FAILED"
            item["status"] = "DEGRADED" if item["enabled"] else "DISABLED"
        return item

    def get_source(self, source_key, *, tenant_id="default"):
        tenant = _tenant(tenant_id)
        key = self._source_key(source_key)
        row = self.conn.execute(
            "SELECT s.*,t.name AS token_name,t.disabled AS token_disabled,t.scopes AS token_scopes "
            "FROM external_sources s LEFT JOIN api_tokens t ON t.id=s.ingest_token_id "
            "WHERE s.tenant_id=? AND s.source_key=?",
            (tenant, key),
        ).fetchone()
        return self._row(row)

    def sources(self, *, tenant_id="default", limit=500):
        tenant = _tenant(tenant_id)
        limit = max(1, min(int(limit), 1000))
        rows = self.conn.execute(
            "SELECT s.*,t.name AS token_name,t.disabled AS token_disabled,t.scopes AS token_scopes "
            "FROM external_sources s LEFT JOIN api_tokens t ON t.id=s.ingest_token_id "
            "WHERE s.tenant_id=? ORDER BY s.display_name,s.source_key LIMIT ?",
            (tenant, limit),
        ).fetchall()
        return [self._row(row) for row in rows]

    def _validate_ingest_token(self, token_id):
        try:
            token_id = int(token_id)
        except (TypeError, ValueError) as exc:
            raise ExternalEvidenceError("INVALID_INGEST_TOKEN", "ingest_token_id is required") from exc
        row = self.conn.execute(
            "SELECT id,name,scopes,role,disabled FROM api_tokens WHERE id=?", (token_id,)
        ).fetchone()
        if not row or bool(row["disabled"]):
            raise ExternalEvidenceError("INVALID_INGEST_TOKEN", "ingest token does not exist or is disabled")
        scopes = set(_decode(row["scopes"], []))
        if "external:ingest" not in scopes:
            raise ExternalEvidenceError("INVALID_INGEST_TOKEN", "ingest token lacks external:ingest scope")
        return dict(row)

    def register_source(self, source_key, source_type, display_name, *, ingest_token_id,
                        max_payload_bytes=_DEFAULT_MAX_PAYLOAD, rate_limit_per_minute=_DEFAULT_RATE,
                        enabled=True, actor="system", tenant_id="default"):
        tenant = _tenant(tenant_id)
        key = self._source_key(source_key)
        stype = self._source_type(source_type)
        name = _text(display_name, 160)
        if not name:
            raise ExternalEvidenceError("INVALID_SOURCE", "display_name is required")
        token = self._validate_ingest_token(ingest_token_id)
        bound = self.conn.execute(
            "SELECT source_key FROM external_sources WHERE tenant_id=? AND ingest_token_id=? AND source_key<>?",
            (tenant, token["id"], key),
        ).fetchone()
        if bound:
            raise ExternalEvidenceError(
                "INGEST_TOKEN_ALREADY_BOUND",
                "ingest token is already bound to external source " + str(bound["source_key"]))
        max_bytes = int(max_payload_bytes or _DEFAULT_MAX_PAYLOAD)
        rate = int(rate_limit_per_minute or _DEFAULT_RATE)
        if max_bytes < 1024 or max_bytes > _GLOBAL_MAX_PAYLOAD:
            raise ExternalEvidenceError("INVALID_PAYLOAD_LIMIT", f"max_payload_bytes must be 1024..{_GLOBAL_MAX_PAYLOAD}")
        if rate < 1 or rate > 6000:
            raise ExternalEvidenceError("INVALID_RATE_LIMIT", "rate_limit_per_minute must be 1..6000")
        now = time.time()
        existing = self.get_source(key, tenant_id=tenant)
        if existing:
            self.conn.execute(
                "UPDATE external_sources SET source_type=?,display_name=?,ingest_token_id=?,enabled=?,"
                "max_payload_bytes=?,rate_limit_per_minute=?,updated_by=?,updated_ts=?,status=?,auth_state='UNVERIFIED',"
                "last_error_class='',last_error='' WHERE id=?",
                (stype, name, token["id"], int(bool(enabled)), max_bytes, rate, _text(actor, 128), now,
                 "CONFIGURED" if enabled else "DISABLED", existing["id"]),
            )
            source_id = existing["id"]
            action = "external_source_update"
        else:
            cur = self.conn.execute(
                "INSERT INTO external_sources(tenant_id,source_key,source_type,display_name,ingest_token_id,enabled,"
                "auth_mode,schema_version,max_payload_bytes,rate_limit_per_minute,created_by,created_ts,updated_by,updated_ts) "
                "VALUES(?,?,?,?,?,?, 'BEARER','1',?,?,?,?,?,?)",
                (tenant, key, stype, name, token["id"], int(bool(enabled)), max_bytes, rate,
                 _text(actor, 128), now, _text(actor, 128), now),
            )
            source_id = cur.lastrowid
            action = "external_source_create"
        self.conn.commit()
        self.db.audit(actor, action, key, f"type={stype} token_id={token['id']}")
        return self.get_source(key, tenant_id=tenant)

    def set_enabled(self, source_key, enabled, *, actor="system", tenant_id="default"):
        source = self.get_source(source_key, tenant_id=tenant_id)
        if not source:
            raise ExternalEvidenceError("SOURCE_NOT_FOUND", "external source not found", 404)
        now = time.time()
        status = "CONFIGURED" if enabled else "DISABLED"
        auth_state = "UNVERIFIED" if enabled else source.get("auth_state", "UNVERIFIED")
        self.conn.execute(
            "UPDATE external_sources SET enabled=?,status=?,auth_state=?,updated_by=?,updated_ts=? WHERE id=?",
            (int(bool(enabled)), status, auth_state, _text(actor, 128), now, source["id"]),
        )
        self.conn.commit()
        self.db.audit(actor, "external_source_state", source["source_key"], status)
        return self.get_source(source["source_key"], tenant_id=tenant_id)

    def payload_limit(self, source_key):
        try:
            source = self.get_source(source_key)
        except ExternalEvidenceError:
            return _DEFAULT_MAX_PAYLOAD
        return min(_GLOBAL_MAX_PAYLOAD, int((source or {}).get("max_payload_bytes") or _DEFAULT_MAX_PAYLOAD))

    def _health_failure(self, source, error_class, message, *, auth=False, rate=False, schema=False):
        now = time.time()
        fields = ["rejected_count=rejected_count+1", "last_rejected_ts=?", "last_error_class=?", "last_error=?", "status='DEGRADED'"]
        args = [now, _text(error_class, 64), _text(message, 500)]
        if auth:
            fields += ["auth_failure_count=auth_failure_count+1", "last_auth_failure_ts=?", "auth_state='FAILED'"]
            args.append(now)
        else:
            fields += ["auth_state='OK'"]
        if rate:
            fields += ["rate_limited_count=rate_limited_count+1", "last_rate_limited_ts=?"]
            args.append(now)
        if schema:
            fields += ["schema_rejection_count=schema_rejection_count+1"]
        args.append(source["id"])
        self.conn.execute("UPDATE external_sources SET " + ",".join(fields) + " WHERE id=?", tuple(args))
        self.conn.commit()

    def _health_duplicate(self, source, *, received_ts):
        self.conn.execute(
            "UPDATE external_sources SET duplicate_count=duplicate_count+1,last_received_ts=?,auth_state='OK',"
            "status='CONNECTED',last_error_class='',last_error='' WHERE id=?",
            (received_ts, source["id"]),
        )
        self.conn.commit()

    def _health_success(self, source, *, source_ts, received_ts):
        self.conn.execute(
            "UPDATE external_sources SET status='CONNECTED',auth_state='OK',last_event_ts=?,last_received_ts=?,"
            "received_count=received_count+1,last_error_class='',last_error='' WHERE id=?",
            (source_ts, received_ts, source["id"]),
        )
        self.conn.commit()

    def _rate_check(self, source, now):
        limit = int(source.get("rate_limit_per_minute") or _DEFAULT_RATE)
        with self._rate_lock:
            queue = self._rate.setdefault(source["id"], deque())
            cutoff = now - 60.0
            while queue and queue[0] <= cutoff:
                queue.popleft()
            if len(queue) >= limit:
                self._health_failure(source, "RATE_LIMITED", "source ingestion rate limit exceeded", rate=True)
                raise ExternalEvidenceError("RATE_LIMITED", "source ingestion rate limit exceeded", 429)
            queue.append(now)

    def _normalize(self, source, envelope, received_ts):
        if not isinstance(envelope, dict):
            raise ExternalEvidenceError("SCHEMA_REJECTED", "normalized external event must be an object")
        schema_version = _text(envelope.get("schema_version") or "1", 16)
        if schema_version != "1":
            raise ExternalEvidenceError("SCHEMA_REJECTED", "unsupported external evidence schema_version")
        source_event_id = _text(envelope.get("source_event_id"), 256)
        idempotency_key = _text(envelope.get("idempotency_key"), 256)
        event_type = _text(envelope.get("event_type"), 128)
        if not source_event_id or not idempotency_key or not event_type:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "source_event_id, idempotency_key and event_type are required")
        if not _EVENT_TYPE.fullmatch(event_type):
            raise ExternalEvidenceError("SCHEMA_REJECTED", "event_type contains unsupported characters")
        if "source_ts" not in envelope or envelope.get("source_ts") in (None, ""):
            raise ExternalEvidenceError("SCHEMA_REJECTED", "source_ts is required")
        try:
            source_ts = float(envelope["source_ts"])
        except (TypeError, ValueError) as exc:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "source_ts must be numeric epoch seconds") from exc
        if source_ts <= 0:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "source_ts must be positive")
        severity = _text(envelope.get("severity") or "INFO", 32).upper()
        if severity not in SEVERITIES:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "unsupported severity")
        domain = _text(envelope.get("domain") or DEFAULT_DOMAIN[source["source_type"]], 64).upper()
        if domain not in DOMAINS:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "unsupported domain")
        entity_type = _text(envelope.get("entity_type") or "unknown", 64).lower() or "unknown"
        if not re.fullmatch(r"[a-z0-9][a-z0-9._:-]{0,63}", entity_type):
            raise ExternalEvidenceError("SCHEMA_REJECTED", "invalid entity_type")
        entity_id = _text(envelope.get("entity_id"), 255)
        summary = _text(envelope.get("summary"), 1000)
        metadata = redact_external(envelope.get("metadata") or {})
        payload = redact_external(envelope.get("payload") or {})
        source_clock = redact_external(envelope.get("source_clock") or {})
        if not isinstance(metadata, dict) or not isinstance(payload, dict) or not isinstance(source_clock, dict):
            raise ExternalEvidenceError("SCHEMA_REJECTED", "metadata, payload and source_clock must be objects")
        source_clock = dict(source_clock)
        source_clock["observed_skew_seconds"] = round(float(received_ts) - source_ts, 6)
        metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        clock_json = json.dumps(source_clock, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        if len(metadata_json.encode()) > 16384:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "metadata exceeds normalized limit")
        if len(payload_json.encode()) > source["max_payload_bytes"]:
            raise ExternalEvidenceError("PAYLOAD_TOO_LARGE", "sanitized payload exceeds source limit", 413)
        if len(clock_json.encode()) > 4096:
            raise ExternalEvidenceError("SCHEMA_REJECTED", "source_clock exceeds normalized limit")
        normalized = {
            "source_event_id": source_event_id,
            "idempotency_key": idempotency_key,
            "event_type": event_type,
            "domain": domain,
            "severity": severity,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary": summary,
            "source_ts": source_ts,
            "source_clock": source_clock,
            "metadata": metadata,
            "payload": payload,
            "schema_version": schema_version,
        }
        digest_body = dict(normalized)
        digest_body.pop("idempotency_key", None)
        digest_body["source_clock"] = {
            key: value for key, value in source_clock.items() if key != "observed_skew_seconds"
        }
        payload_sha = hashlib.sha256(
            json.dumps(digest_body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        ).hexdigest()
        return normalized, metadata_json, payload_json, clock_json, payload_sha

    def ingest(self, source_key, envelope, token, *, request_bytes=0, tenant_id="default", received_ts=None):
        """Serialize the same idempotency identity locally and across PostgreSQL nodes."""
        raw_key = envelope.get("idempotency_key") if isinstance(envelope, dict) else ""
        identity = hashlib.sha256(
            f"{_text(source_key,128)}:{_text(raw_key,256)}".encode("utf-8")
        ).hexdigest()
        with self._ingest_lock_guard:
            local = self._ingest_locks.setdefault(identity, threading.RLock())
        if not local.acquire(timeout=5.0):
            raise ExternalEvidenceError("INGEST_BUSY", "external evidence identity is busy", 503)
        lock_name = f"r62:external-ingest:{identity}"
        advisory = False
        try:
            if getattr(self.db, "dialect", "sqlite") == "postgres":
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if self.db.try_advisory_lock(lock_name):
                        advisory = True
                        break
                    time.sleep(0.05)
                if not advisory:
                    raise ExternalEvidenceError("INGEST_BUSY", "PostgreSQL ingest identity is busy", 503)
            return self._ingest_locked(
                source_key, envelope, token, request_bytes=request_bytes,
                tenant_id=tenant_id, received_ts=received_ts,
            )
        finally:
            if advisory:
                try:
                    self.db.advisory_unlock(lock_name)
                except Exception:
                    pass
            local.release()

    def _ingest_locked(self, source_key, envelope, token, *, request_bytes=0, tenant_id="default", received_ts=None):
        tenant = _tenant(tenant_id)
        source = self.get_source(source_key, tenant_id=tenant)
        if not source:
            raise ExternalEvidenceError("SOURCE_NOT_FOUND", "external source not found", 404)
        if not source["enabled"]:
            raise ExternalEvidenceError("SOURCE_DISABLED", "external source is disabled", 409)
        if not token or "external:ingest" not in set(token.get("scopes") or ()):
            self._health_failure(source, "AUTH_FAILURE", "authenticated principal lacks external:ingest", auth=True)
            raise ExternalEvidenceError("AUTH_FAILURE", "external:ingest scope required", 403)
        if int(token.get("id") or 0) != int(source.get("ingest_token_id") or 0):
            self._health_failure(source, "AUTH_FAILURE", "token is not bound to this source", auth=True)
            raise ExternalEvidenceError("AUTH_FAILURE", "token is not bound to this source", 403)
        now = time.time() if received_ts is None else float(received_ts)
        self._rate_check(source, now)
        if int(request_bytes or 0) > int(source["max_payload_bytes"]):
            self._health_failure(source, "PAYLOAD_TOO_LARGE", "request body exceeds source payload limit")
            raise ExternalEvidenceError("PAYLOAD_TOO_LARGE", "request body exceeds source payload limit", 413)
        try:
            normalized, metadata_json, payload_json, clock_json, payload_sha = self._normalize(source, envelope, now)
        except ExternalEvidenceError as exc:
            self._health_failure(source, exc.code, str(exc), schema=(exc.code == "SCHEMA_REJECTED"))
            raise

        receipt = self.conn.execute(
            "SELECT * FROM external_ingest_receipts WHERE tenant_id=? AND source_id=? AND idempotency_key=?",
            (tenant, source["id"], normalized["idempotency_key"]),
        ).fetchone()
        if receipt:
            if receipt["payload_sha256"] != payload_sha:
                self._health_failure(source, "IDEMPOTENCY_CONFLICT", "idempotency key replayed with different evidence")
                raise ExternalEvidenceError("IDEMPOTENCY_CONFLICT", "idempotency key replayed with different evidence", 409)
            self._health_duplicate(source, received_ts=now)
            event = self.conn.execute("SELECT * FROM external_events WHERE id=?", (receipt["event_id"],)).fetchone()
            return {"result": "DUPLICATE_IDEMPOTENT", "duplicate": True, "event": self._event_row(event)}

        existing = self.conn.execute(
            "SELECT * FROM external_events WHERE source_system=? AND source_event_id=?",
            (source["source_key"], normalized["source_event_id"]),
        ).fetchone()
        if existing:
            existing = dict(existing)
            if existing.get("payload_sha256") and existing["payload_sha256"] != payload_sha:
                self._health_failure(source, "SOURCE_EVENT_CONFLICT", "source_event_id replayed with different evidence")
                raise ExternalEvidenceError("SOURCE_EVENT_CONFLICT", "source_event_id replayed with different evidence", 409)
            self.conn.execute(
                "INSERT OR IGNORE INTO external_ingest_receipts(tenant_id,source_id,idempotency_key,source_event_id,event_id,payload_sha256,received_ts,result) "
                "VALUES(?,?,?,?,?,?,?,'DUPLICATE_SOURCE_EVENT')",
                (tenant, source["id"], normalized["idempotency_key"], normalized["source_event_id"],
                 existing["id"], payload_sha, now),
            )
            self.conn.commit()
            self._health_duplicate(source, received_ts=now)
            return {"result": "DUPLICATE_SOURCE_EVENT", "duplicate": True, "event": self._event_row(existing)}

        cur = self.conn.execute(
            "INSERT INTO external_events(source_system,source_event_id,domain,event_type,severity,entity_type,entity_id,summary,"
            "source_ts,received_ts,source_clock_json,metadata_json,tenant_id,source_key,idempotency_key,schema_version,"
            "payload_sha256,payload_json,ingest_principal,ingest_result,connector_type) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACCEPTED',?)",
            (source["source_key"], normalized["source_event_id"], normalized["domain"], normalized["event_type"],
             normalized["severity"], normalized["entity_type"], normalized["entity_id"], normalized["summary"],
             normalized["source_ts"], now, clock_json, metadata_json, tenant, source["source_key"],
             normalized["idempotency_key"], normalized["schema_version"], payload_sha, payload_json,
             _text(token.get("name"), 128), source["source_type"]),
        )
        event_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO external_ingest_receipts(tenant_id,source_id,idempotency_key,source_event_id,event_id,payload_sha256,received_ts,result) "
            "VALUES(?,?,?,?,?,?,?,'ACCEPTED')",
            (tenant, source["id"], normalized["idempotency_key"], normalized["source_event_id"], event_id, payload_sha, now),
        )
        self.conn.commit()
        self._health_success(source, source_ts=normalized["source_ts"], received_ts=now)
        self.db.audit("external:" + source["source_key"], "external_evidence_ingest", str(event_id),
                      f"type={normalized['event_type']} principal={_text(token.get('name'),128)}")
        row = self.conn.execute("SELECT * FROM external_events WHERE id=?", (event_id,)).fetchone()
        return {"result": "ACCEPTED", "duplicate": False, "event": self._event_row(row)}

    def _event_row(self, row, *, include_payload=True):
        if not row:
            return None
        item = dict(row)
        item["source_clock"] = _decode(item.pop("source_clock_json", "{}"), {})
        item["metadata"] = _decode(item.pop("metadata_json", "{}"), {})
        payload = _decode(item.pop("payload_json", "{}"), {})
        if include_payload:
            item["payload"] = payload
        return item

    def events(self, source_key="", *, tenant_id="default", limit=200, include_payload=False):
        tenant = _tenant(tenant_id)
        limit = max(1, min(int(limit), 1000))
        q = "SELECT * FROM external_events WHERE tenant_id=?"
        args = [tenant]
        if source_key:
            q += " AND source_key=?"
            args.append(self._source_key(source_key))
        q += " ORDER BY received_ts DESC,id DESC LIMIT ?"
        args.append(limit)
        return [self._event_row(row, include_payload=include_payload) for row in self.conn.execute(q, tuple(args)).fetchall()]

    def event(self, event_id, *, tenant_id="default", include_payload=True):
        tenant = _tenant(tenant_id)
        row = self.conn.execute("SELECT * FROM external_events WHERE tenant_id=? AND id=?", (tenant, int(event_id))).fetchone()
        return self._event_row(row, include_payload=include_payload)
