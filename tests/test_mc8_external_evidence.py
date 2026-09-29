import http.client
import json
import threading

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.external_evidence import ExternalEvidenceError, SOURCE_TYPES
from netconfig.manager import Manager
from netconfig.postgres_core import postgres_schema_statements
from netconfig.web import Console, _Server


def _manager(tmp_path):
    return Manager(str(tmp_path / "home"))


def _token(tokens, name, scopes, role):
    token_id, raw = tokens.create(name, scopes, created_by="test", role=role)
    return token_id, raw, tokens.verify(raw)


def _register(manager, *, key="ndr-main", source_type="NDR", rate=120, max_bytes=65536):
    tokens = ApiTokens(manager.db.conn)
    token_id, raw, verified = _token(tokens, key + "-token", ["external:ingest", "external:read"], "operator")
    source = manager.external_evidence.register_source(
        key, source_type, key.upper(), ingest_token_id=token_id,
        max_payload_bytes=max_bytes, rate_limit_per_minute=rate, actor="admin")
    return source, raw, verified


def _event(event_id="evt-1", idem="idem-1", **extra):
    value = {
        "source_event_id": event_id,
        "idempotency_key": idem,
        "event_type": "traffic.spike",
        "source_ts": 1000.0,
        "severity": "MAJOR",
        "entity_type": "ip",
        "entity_id": "10.0.0.10",
        "summary": "Traffic volume spike",
        "metadata": {"sensor": "ndr-a"},
        "payload": {"bytes": 1234},
        "source_clock": {"quality": "source-reported"},
    }
    value.update(extra)
    return value


def test_mc8_schema_revision_sources_and_postgres_schema(tmp_path):
    manager = _manager(tmp_path)
    try:
        assert manager.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
        tables = {row["name"] for row in manager.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"external_sources", "external_ingest_receipts", "external_events"} <= tables
        pg = "\n".join(postgres_schema_statements()).lower()
        assert "create table if not exists external_sources" in pg
        assert "create table if not exists external_ingest_receipts" in pg
        assert set(SOURCE_TYPES) == {
            "NDR", "WAF", "SIEM", "EDR", "APM", "DATABASE", "STORAGE", "VIRTUALIZATION", "CLOUD"
        }
    finally:
        manager.close()


def test_mc8_source_registration_is_token_bound_and_rejects_unknown_types(tmp_path):
    manager = _manager(tmp_path)
    try:
        tokens = ApiTokens(manager.db.conn)
        reader_id, _, _ = _token(tokens, "reader", ["external:read"], "viewer")
        with pytest.raises(ExternalEvidenceError, match="lacks external:ingest"):
            manager.external_evidence.register_source(
                "ndr-main", "NDR", "NDR", ingest_token_id=reader_id, actor="admin")
        ingest_id, _, _ = _token(tokens, "ingest", ["external:ingest"], "operator")
        with pytest.raises(ExternalEvidenceError, match="unsupported external source type"):
            manager.external_evidence.register_source(
                "bad", "FIREWALL_ACTION", "Bad", ingest_token_id=ingest_id, actor="admin")
        source = manager.external_evidence.register_source(
            "ndr-main", "NDR", "Primary NDR", ingest_token_id=ingest_id, actor="admin")
        assert source["source_key"] == "ndr-main"
        assert source["auth_mode"] == "BEARER"
        assert source["status"] == "CONFIGURED"
        assert "token_hash" not in source
    finally:
        manager.close()


def test_mc8_ingest_redacts_secrets_records_clock_skew_and_health(tmp_path):
    manager = _manager(tmp_path)
    try:
        source, _, token = _register(manager)
        envelope = _event(
            payload={
                "username": "alice",
                "password": "dont-store-me",
                "nested": {"api_key": "dont-store-this-either", "safe": "value"},
            },
            metadata={"Authorization": "Bearer secret", "classification": "network"},
        )
        result = manager.external_evidence.ingest(
            source["source_key"], envelope, token, request_bytes=512, received_ts=1012.5)
        assert result["result"] == "ACCEPTED"
        event = result["event"]
        assert event["payload"]["password"] == "[REDACTED]"
        assert event["payload"]["nested"]["api_key"] == "[REDACTED]"
        assert event["payload"]["nested"]["safe"] == "value"
        assert event["metadata"]["Authorization"] == "[REDACTED]"
        assert event["source_clock"]["observed_skew_seconds"] == 12.5
        health = manager.external_evidence.get_source(source["source_key"])
        assert health["status"] == "CONNECTED"
        assert health["auth_state"] == "OK"
        assert health["received_count"] == 1
        raw = manager.db.conn.execute(
            "SELECT payload_json,metadata_json FROM external_events WHERE id=?", (event["id"],)).fetchone()
        stored = raw["payload_json"] + raw["metadata_json"]
        assert "dont-store-me" not in stored
        assert "dont-store-this-either" not in stored
        assert "Bearer secret" not in stored
    finally:
        manager.close()


def test_mc8_idempotency_duplicate_and_replay_conflict_are_deterministic(tmp_path):
    manager = _manager(tmp_path)
    try:
        source, _, token = _register(manager)
        first = manager.external_evidence.ingest(
            source["source_key"], _event(), token, request_bytes=400, received_ts=1001.0)
        duplicate = manager.external_evidence.ingest(
            source["source_key"], _event(), token, request_bytes=400, received_ts=1002.0)
        assert duplicate["result"] == "DUPLICATE_IDEMPOTENT"
        assert duplicate["event"]["id"] == first["event"]["id"]
        assert manager.db.conn.execute("SELECT COUNT(*) c FROM external_events").fetchone()["c"] == 1
        with pytest.raises(ExternalEvidenceError) as excinfo:
            manager.external_evidence.ingest(
                source["source_key"], _event(payload={"bytes": 9999}), token,
                request_bytes=400, received_ts=1003.0)
        assert excinfo.value.code == "IDEMPOTENCY_CONFLICT"
        assert excinfo.value.status == 409
        health = manager.external_evidence.get_source(source["source_key"])
        assert health["duplicate_count"] == 1
        assert health["rejected_count"] == 1
    finally:
        manager.close()


def test_mc8_source_event_replay_conflict_is_rejected_even_with_new_idempotency_key(tmp_path):
    manager = _manager(tmp_path)
    try:
        source, _, token = _register(manager)
        manager.external_evidence.ingest(
            source["source_key"], _event(), token, request_bytes=400, received_ts=1001.0)
        same = manager.external_evidence.ingest(
            source["source_key"], _event(idem="idem-2"), token, request_bytes=400, received_ts=1002.0)
        assert same["result"] == "DUPLICATE_SOURCE_EVENT"
        with pytest.raises(ExternalEvidenceError) as excinfo:
            manager.external_evidence.ingest(
                source["source_key"], _event(idem="idem-3", payload={"bytes": 8}), token,
                request_bytes=400, received_ts=1003.0)
        assert excinfo.value.code == "SOURCE_EVENT_CONFLICT"
        assert excinfo.value.status == 409
    finally:
        manager.close()


def test_mc8_source_binding_auth_failure_and_disabled_source_fail_closed(tmp_path):
    manager = _manager(tmp_path)
    try:
        source, _, _ = _register(manager, key="ndr-main")
        _, _, wrong_token = _register(manager, key="waf-main", source_type="WAF")
        with pytest.raises(ExternalEvidenceError) as excinfo:
            manager.external_evidence.ingest(
                source["source_key"], _event(), wrong_token, request_bytes=300, received_ts=1001.0)
        assert excinfo.value.code == "AUTH_FAILURE"
        health = manager.external_evidence.get_source(source["source_key"])
        assert health["auth_state"] == "FAILED"
        assert health["auth_failure_count"] == 1
        manager.external_evidence.set_enabled(source["source_key"], False, actor="admin")
        with pytest.raises(ExternalEvidenceError) as disabled:
            manager.external_evidence.ingest(
                source["source_key"], _event(), wrong_token, request_bytes=300, received_ts=1002.0)
        assert disabled.value.code == "SOURCE_DISABLED"
    finally:
        manager.close()


def test_mc8_schema_payload_and_rate_limit_rejections_are_visible_health(tmp_path):
    manager = _manager(tmp_path)
    try:
        source, _, token = _register(manager, rate=2, max_bytes=1024)
        with pytest.raises(ExternalEvidenceError) as malformed:
            manager.external_evidence.ingest(
                source["source_key"], {"source_event_id": "bad"}, token,
                request_bytes=100, received_ts=1000.0)
        assert malformed.value.code == "SCHEMA_REJECTED"
        with pytest.raises(ExternalEvidenceError) as oversized:
            manager.external_evidence.ingest(
                source["source_key"], _event(), token, request_bytes=2048, received_ts=1001.0)
        assert oversized.value.status == 413
        # Those two attempts consume the bounded source window; a third is rate-limited.
        with pytest.raises(ExternalEvidenceError) as limited:
            manager.external_evidence.ingest(
                source["source_key"], _event(event_id="evt-2", idem="idem-2"), token,
                request_bytes=100, received_ts=1002.0)
        assert limited.value.code == "RATE_LIMITED"
        health = manager.external_evidence.get_source(source["source_key"])
        assert health["schema_rejection_count"] == 1
        assert health["rate_limited_count"] == 1
        assert health["rejected_count"] == 3
        assert health["status"] == "DEGRADED"
    finally:
        manager.close()


def test_mc8_incident_advanced_external_evidence_is_sanitized(tmp_path):
    manager = _manager(tmp_path)
    try:
        source, _, token = _register(manager)
        result = manager.external_evidence.ingest(
            source["source_key"], _event(payload={"secret": "never", "safe": "yes"}), token,
            request_bytes=400, received_ts=1010.0)
        incident = manager.incidents.create("External evidence", created_by="alice")
        manager.incidents.link_evidence(
            incident["incident_key"], "external_event", result["event"]["id"], "alice", "NDR evidence")
        timeline = manager.incidents.timeline(incident["incident_key"])
        external = next(item for item in timeline if item.get("source_type") == "external_event")
        assert external["source_key"] == source["source_key"]
        assert external["advanced"]["payload"]["secret"] == "[REDACTED]"
        assert external["advanced"]["payload"]["safe"] == "yes"
    finally:
        manager.close()


def test_mc8_api_source_management_ingest_read_and_scope_boundaries(tmp_path):
    manager = _manager(tmp_path)
    server = None
    try:
        tokens = ApiTokens(manager.db.conn)
        ingest_id, ingest_raw, _ = _token(tokens, "connector", ["external:ingest"], "operator")
        _, admin_raw, _ = _token(tokens, "integration-admin", ["external:manage", "external:read"], "admin")
        _, reader_raw, _ = _token(tokens, "integration-reader", ["external:read"], "viewer")
        _, wrong_raw, _ = _token(tokens, "wrong-connector", ["external:ingest"], "operator")

        Console.manager = manager
        Console.tls_enabled = False
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(method, path, token, payload=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            headers = {"Authorization": "Bearer " + token}
            body = ""
            if payload is not None:
                body = json.dumps(payload)
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            data = json.loads(response.read() or b"{}")
            status = response.status
            conn.close()
            return status, data

        status, _ = request("POST", "/api/v1/external-sources", reader_raw, {
            "source_key": "ndr-api", "source_type": "NDR", "display_name": "NDR API",
            "ingest_token_id": ingest_id,
        })
        assert status == 403
        status, source = request("POST", "/api/v1/external-sources", admin_raw, {
            "source_key": "ndr-api", "source_type": "NDR", "display_name": "NDR API",
            "ingest_token_id": ingest_id, "rate_limit_per_minute": 120, "max_payload_bytes": 65536,
        })
        assert status == 201 and source["source_key"] == "ndr-api"
        status, denied = request("POST", "/api/v1/external-evidence/ndr-api/events", wrong_raw, _event())
        assert status == 403 and denied["error"] == "AUTH_FAILURE"
        status, accepted = request("POST", "/api/v1/external-evidence/ndr-api/events", ingest_raw, _event())
        assert status == 201 and accepted["result"] == "ACCEPTED"
        status, duplicate = request("POST", "/api/v1/external-evidence/ndr-api/events", ingest_raw, _event())
        assert status == 200 and duplicate["duplicate"] is True
        status, sources = request("GET", "/api/v1/external-sources", reader_raw)
        assert status == 200 and sources[0]["received_count"] == 1
        event_id = accepted["event"]["id"]
        status, event = request("GET", f"/api/v1/external-evidence/{event_id}", reader_raw)
        assert status == 200 and event["source_key"] == "ndr-api"
    finally:
        if server:
            server.shutdown()
            server.server_close()
        manager.close()


def test_mc8_upgrade_from_legacy_external_events_preserves_rows(tmp_path):
    import sqlite3
    from netconfig.db import Database

    path = tmp_path / "legacy.db"
    raw = sqlite3.connect(path)
    raw.execute(
        "CREATE TABLE external_events ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,source_system TEXT NOT NULL,source_event_id TEXT NOT NULL,"
        "domain TEXT NOT NULL DEFAULT 'EXTERNAL',event_type TEXT NOT NULL,severity TEXT NOT NULL DEFAULT 'INFO',"
        "entity_type TEXT NOT NULL DEFAULT 'unknown',entity_id TEXT NOT NULL DEFAULT '',summary TEXT NOT NULL DEFAULT '',"
        "source_ts REAL NOT NULL,received_ts REAL NOT NULL,source_clock_json TEXT NOT NULL DEFAULT '{}',"
        "metadata_json TEXT NOT NULL DEFAULT '{}',UNIQUE(source_system,source_event_id))"
    )
    raw.execute(
        "INSERT INTO external_events(source_system,source_event_id,event_type,source_ts,received_ts) VALUES(?,?,?,?,?)",
        ("legacy-siem", "legacy-1", "legacy.event", 10.0, 11.0),
    )
    raw.commit()
    raw.close()
    db = Database(str(path))
    try:
        row = dict(db.conn.execute("SELECT * FROM external_events WHERE id=1").fetchone())
        assert row["source_system"] == "legacy-siem"
        assert row["source_event_id"] == "legacy-1"
        assert row["tenant_id"] == "default"
        assert row["payload_json"] == "{}"
        assert row["connector_type"] == ""
        assert db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
    finally:
        db.close()


def test_mc8_settings_integrations_page_exposes_health_without_secrets(tmp_path):
    import urllib.parse
    import netconfig.web as web

    manager = _manager(tmp_path)
    server = None
    try:
        source, raw_token, token = _register(manager)
        manager.external_evidence.ingest(
            source["source_key"], _event(), token, request_bytes=300, received_ts=1010.0)
        web._SESSIONS.clear()
        session = "mc8-admin-session"
        web._SESSIONS[session] = {
            "username": "admin", "role": "admin", "csrf": "mc8-csrf", "created": 1.0,
        }
        Console.manager = manager
        Console.tls_enabled = False
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/settings?section=integrations", headers={"Cookie": f"ncsid={session}"})
        response = conn.getresponse()
        text = response.read().decode()
        conn.close()
        assert response.status == 200
        assert "External evidence integrations" in text
        assert "Primary" not in text or "NDR" in text
        assert "NDR-MAIN" in text
        assert "CONNECTED" in text
        assert "Received" in text and "Rejected" in text and "Authentication" in text
        assert raw_token not in text
        assert "reconfigure external systems" in text
    finally:
        if server:
            server.shutdown()
            server.server_close()
        web._SESSIONS.clear()
        manager.close()


def test_mc8_ingest_token_is_exclusive_to_one_source_and_schema_version_is_v1(tmp_path):
    manager = _manager(tmp_path)
    try:
        tokens = ApiTokens(manager.db.conn)
        ingest_id, _, verified = _token(tokens, "shared-ingest", ["external:ingest"], "operator")
        first = manager.external_evidence.register_source(
            "ndr-one", "NDR", "NDR One", ingest_token_id=ingest_id, actor="admin")
        assert first["source_key"] == "ndr-one"
        with pytest.raises(ExternalEvidenceError) as bound:
            manager.external_evidence.register_source(
                "waf-two", "WAF", "WAF Two", ingest_token_id=ingest_id, actor="admin")
        assert bound.value.code == "INGEST_TOKEN_ALREADY_BOUND"

        with pytest.raises(ExternalEvidenceError) as schema:
            manager.external_evidence.ingest(
                "ndr-one", _event(schema_version="2"), verified,
                request_bytes=300, received_ts=1001.0)
        assert schema.value.code == "SCHEMA_REJECTED"
        health = manager.external_evidence.get_source("ndr-one")
        assert health["schema_rejection_count"] == 1
    finally:
        manager.close()
