import http.client
import json
import threading
import sqlite3

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server
from netconfig.workflow import Workflow


def _seed_mc5_sources(m):
    c = m.db.conn
    # Sensor transition: old source time, intentionally inserted after newer evidence later.
    c.execute(
        "INSERT INTO sensor_transitions(sensor_key,sensor_type,device,resource,previous_status,new_status,"
        "previous_value,new_value,source,observed_at,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        ("application.http_status|app1|https://app/health", "application.http_status", "app1",
         "https://app/health", "OK", "CRITICAL", "200", "503", "monitor", 100.0, "{}", 140.0),
    )
    sensor_id = c.execute("SELECT max(id) AS id FROM sensor_transitions").fetchone()["id"]

    c.execute(
        "INSERT INTO operational_events(first_ts,last_ts,event_count,source_type,source,device,event_type,severity,"
        "message,dedup_key,suppressed,metadata,domain,entity_type,entity_id,resource,status,observed_at,evidence_ref) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (110.0, 111.0, 1, "sensor_transition", "monitor", "app1", "application.http_status.critical",
         "CRITICAL", "HTTP 503", "mc5-event", 0, '{}', "APPLICATION", "application", "https://app/health",
         "https://app/health", "CRITICAL", 110.0, f"sensor_transition:{sensor_id}"),
    )
    event_id = c.execute("SELECT max(id) AS id FROM operational_events").fetchone()["id"]
    c.execute(
        "INSERT INTO operational_alerts(event_id,correlation_key,last_event_id,state,severity,device,event_type,message,"
        "first_ts,last_ts,event_count) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, "sensor:application.http_status|app1|https://app/health", event_id, "OPEN", "CRITICAL",
         "app1", "application.http_status.critical", "HTTP 503", 112.0, 113.0, 1),
    )
    alert_id = c.execute("SELECT max(id) AS id FROM operational_alerts").fetchone()["id"]

    change = m.db.record_change_event(
        7, "EXECUTION_COMPLETED", "executed", "alice", "CR#7 executed: firewall policy changed",
        metadata={"job_id": 9, "affected_devices": ["fw1"]}, source_ts=105.0, received_ts=106.0,
    )
    c.execute(
        "INSERT INTO network_insights(tenant_id,insight_type,object_type,object_id,severity,confidence,summary,state,"
        "evidence_json,affected_json,fingerprint,first_seen_ts,last_seen_ts,occurrence_count) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("default", "CAPACITY", "DEVICE", "app1", "WARNING", 0.8, "API traffic saturation", "NEW", "{}", "[]",
         "mc5-insight", 115.0, 116.0, 1),
    )
    insight_id = c.execute("SELECT max(id) AS id FROM network_insights").fetchone()["id"]
    c.commit()
    external = m.db.record_external_event(
        "ndr-lab", "evt-42", "TRAFFIC_SPIKE", domain="SECURITY", severity="HIGH",
        entity_type="ip", entity_id="10.0.0.5", summary="NDR traffic anomaly",
        source_ts=90.0, received_ts=130.0,
        source_clock={"source_clock": "ndr-appliance", "offset_ms": 250},
        metadata={"schema": "test-v1"},
    )
    return {
        "sensor_transition": sensor_id,
        "operational_event": event_id,
        "operational_alert": alert_id,
        "change_event": change["id"],
        "analytics_insight": insight_id,
        "external_event": external["id"],
    }


def test_mc5_schema_revision_and_evidence_tables_are_additive(tmp_path):
    m = Manager(str(tmp_path / "home"))
    assert m.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
    cols = {r["name"] for r in m.db.conn.execute("PRAGMA table_info(incident_evidence_links)").fetchall()}
    assert {"source_ts", "received_ts", "source_clock_json"} <= cols
    tables = {r["name"] for r in m.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"change_events", "external_events"} <= tables
    m.db.close()


def test_mc5_all_new_evidence_types_are_typed_validated_and_resolved(tmp_path):
    m = Manager(str(tmp_path / "home"))
    ids = _seed_mc5_sources(m)
    incident = m.incidents.create("Cross-domain investigation", created_by="alice")
    key = incident["incident_key"]
    for source_type, source_id in ids.items():
        m.incidents.link_evidence(key, source_type, source_id, "alice")

    view = m.incidents.investigation_view(key)
    kinds = {item["kind"] for item in view["timeline"]}
    assert set(ids) <= kinds
    assert view["related_alerts"][0]["source_type"] == "operational_alert"
    assert view["related_changes"][0]["source_type"] == "change_event"
    assert any(x["source_type"] == "external_event" for x in view["security_evidence"])
    assert any(x["source_type"] == "analytics_insight" for x in view["network_evidence"])
    assert view["root_cause"] is None and view["root_cause_state"] == "NOT_EVALUATED"

    with pytest.raises(ValueError, match="evidence not found"):
        m.incidents.link_evidence(key, "operational_event", 999999, "alice")
    with pytest.raises(ValueError, match="invalid incident evidence type"):
        m.incidents.link_evidence(key, "root_cause", 1, "alice")
    m.db.close()


def test_mc5_timeline_uses_source_time_late_arrival_and_deterministic_ties(tmp_path):
    m = Manager(str(tmp_path / "home"))
    ids = _seed_mc5_sources(m)
    incident = m.incidents.create("Timeline ordering", created_by="alice")
    key = incident["incident_key"]
    # Link in deliberately non-chronological order.
    for source_type in ("analytics_insight", "operational_alert", "external_event", "sensor_transition", "change_event"):
        m.incidents.link_evidence(key, source_type, ids[source_type], "alice")

    timeline = [x for x in m.incidents.timeline(key) if x.get("link_id")]
    source_times = [x["source_ts"] for x in timeline]
    assert source_times == sorted(source_times)
    external = next(x for x in timeline if x["source_type"] == "external_event")
    assert external["source_ts"] == 90.0 and external["received_ts"] == 130.0
    assert external["source_clock"]["source_clock"] == "ndr-appliance"

    # Equal source timestamps remain deterministic by receive time/type/id.
    e2 = m.db.record_external_event(
        "waf-lab", "evt-43", "REQUEST_ANOMALY", domain="SECURITY", summary="WAF anomaly",
        source_ts=90.0, received_ts=131.0,
    )
    m.incidents.link_evidence(key, "external_event", e2["id"], "alice")
    first = [(x["source_type"], str(x["source_id"])) for x in m.incidents.timeline(key)]
    second = [(x["source_type"], str(x["source_id"])) for x in m.incidents.timeline(key)]
    assert first == second
    m.db.close()


def test_mc5_retention_missing_evidence_keeps_original_timeline_position(tmp_path):
    m = Manager(str(tmp_path / "home"))
    ext = m.db.record_external_event(
        "siem", "old-1", "AUTH_ANOMALY", domain="SECURITY", summary="old evidence",
        source_ts=50.0, received_ts=75.0,
    )
    key = m.incidents.create("Retention", created_by="alice")["incident_key"]
    link = m.incidents.link_evidence(key, "external_event", ext["id"], "alice")
    before = next(x for x in m.incidents.timeline(key) if x.get("link_id") == link["id"])
    assert before["source_ts"] == 50.0

    m.db.conn.execute("DELETE FROM external_events WHERE id=?", (ext["id"],))
    m.db.conn.commit()
    after = next(x for x in m.incidents.timeline(key) if x.get("link_id") == link["id"])
    assert after["available"] is False
    assert after["source_ts"] == 50.0 and after["received_ts"] == 75.0
    assert "no longer available" in after["summary"]
    m.db.close()


def test_mc5_workflow_emits_change_event_without_copying_command_body(tmp_path):
    m = Manager(str(tmp_path / "home"))
    wf = Workflow(m.db, m)
    rid = wf.submit(
        title="DNS update", body="set secret-value-do-not-copy", target_kind="all",
        target_value="", mode="config", requested_by="alice",
    )
    wf.approve(rid, "bob")
    rows = [dict(r) for r in m.db.conn.execute(
        "SELECT * FROM change_events WHERE request_id=? ORDER BY id", (rid,)).fetchall()]
    assert [x["event_type"] for x in rows] == ["REQUEST_SUBMITTED", "REQUEST_APPROVED"]
    serialized = json.dumps(rows)
    assert "secret-value-do-not-copy" not in serialized
    m.db.close()


def test_mc5_investigation_api_scope_and_web_sections(tmp_path):
    m = Manager(str(tmp_path / "home"))
    ids = _seed_mc5_sources(m)
    key = m.incidents.create("Operator investigation", created_by="admin")["incident_key"]
    for source_type in ("operational_alert", "change_event", "external_event", "sensor_transition"):
        m.incidents.link_evidence(key, source_type, ids[source_type], "admin")

    tokens = ApiTokens(m.db.conn)
    _, reader = tokens.create("mc5-reader", ["incident:read"], role="viewer")
    _, no_scope = tokens.create("mc5-no-scope", ["inventory:read"], role="viewer")
    Console.manager = m
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        def get(path, token):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.request("GET", path, headers={"Authorization": "Bearer " + token})
            res = conn.getresponse(); body = res.read(); conn.close()
            return res.status, body

        status, body = get(f"/api/v1/incidents/{key}/investigation", reader)
        payload = json.loads(body)
        assert status == 200 and payload["root_cause_state"] == "NOT_EVALUATED"
        assert payload["related_alerts"] and payload["related_changes"]
        status, _ = get(f"/api/v1/incidents/{key}/investigation", no_scope)
        assert status == 403
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); m.db.close()


def test_mc5_additive_migration_backfills_existing_link_timing(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    raw = sqlite3.connect(path)
    raw.executescript("""
        CREATE TABLE syslog_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            source TEXT NOT NULL,
            facility INTEGER,
            severity INTEGER,
            hostname TEXT,
            appname TEXT,
            message TEXT NOT NULL
        );
        CREATE TABLE incident_evidence_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            linked_by TEXT NOT NULL DEFAULT '',
            linked_ts REAL NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            UNIQUE(incident_id, source_type, source_ref)
        );
    """)
    raw.execute(
        "INSERT INTO syslog_events(ts,source,facility,severity,hostname,appname,message) VALUES(?,?,?,?,?,?,?)",
        (22.5, "10.0.0.1", 1, 5, "sw1", "syslog", "legacy"),
    )
    raw.execute(
        "INSERT INTO incident_evidence_links(incident_id,source_type,source_ref,linked_by,linked_ts,note) "
        "VALUES(1,'syslog','1','alice',99.0,'legacy link')"
    )
    raw.commit(); raw.close()

    from netconfig.db import Database
    db = Database(path)
    row = db.conn.execute("SELECT * FROM incident_evidence_links WHERE id=1").fetchone()
    assert row["source_ts"] == 22.5
    assert row["received_ts"] == 99.0
    assert json.loads(row["source_clock_json"] or "{}") == {}
    db.close()


def test_mc5_web_incident_has_operator_evidence_sections(tmp_path):
    m = Manager(str(tmp_path / "home"))
    ids = _seed_mc5_sources(m)
    key = m.incidents.create("MC5 web", created_by="tester")["incident_key"]
    for source_type in ("operational_alert", "change_event", "external_event", "sensor_transition"):
        m.incidents.link_evidence(key, source_type, ids[source_type], "tester")

    web._SESSIONS.clear()
    sid = "mc5-web-session"
    web._SESSIONS[sid] = {"username": "tester", "role": "operator", "csrf": "mc5", "created": 1.0}
    Console.manager = m; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", f"/incident?ref={key}", headers={"Cookie": f"ncsid={sid}"})
        res = conn.getresponse(); text = res.read().decode("utf-8", "replace"); conn.close()
        assert res.status == 200
        for heading in (
            "Impact", "Incident timeline", "Related alerts", "Related changes",
            "Network evidence", "Security evidence", "Infrastructure evidence", "Raw / advanced evidence",
        ):
            assert heading in text
        assert "does not infer root cause" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); m.db.close()
