import http.client
import json
import threading
import time
import sqlite3

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server


def _start_api(manager):
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _api(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Authorization": "Bearer " + token})
    response = conn.getresponse()
    payload = json.loads(response.read() or b"{}")
    conn.close()
    return response.status, payload


def _start_web(manager):
    web._SESSIONS.clear()
    sid = "mc3-session"
    web._SESSIONS[sid] = {
        "username": "viewer", "role": "viewer", "csrf": "mc3-csrf", "created": time.time()
    }
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, sid


def _web_get(server, sid, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Cookie": f"ncsid={sid}"})
    response = conn.getresponse()
    data = response.read().decode("utf-8", "replace")
    conn.close()
    return response.status, data


def test_mc3_schema_has_normalized_operational_evidence_fields_and_indexes(tmp_path):
    m = Manager(str(tmp_path / "home"))
    cols = {r["name"] for r in m.db.conn.execute("PRAGMA table_info(operational_events)").fetchall()}
    assert {
        "event_type", "domain", "source", "entity_type", "entity_id", "device",
        "resource", "severity", "status", "observed_at", "evidence_ref", "message", "metadata",
    } <= cols
    indexes = {r["name"] for r in m.db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='operational_events'"
    ).fetchall()}
    assert {
        "idx_operational_events_domain_time",
        "idx_operational_events_entity_time",
        "idx_operational_events_evidence_ref",
    } <= indexes
    assert m.db.storage_status()["schema_revision"] == "mc3-operational-evidence-1"
    m.db.close()



def test_mc3_additive_migration_upgrades_legacy_operational_events(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    raw = sqlite3.connect(path)
    raw.execute("""
        CREATE TABLE operational_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_ts REAL NOT NULL, last_ts REAL NOT NULL, event_count INTEGER NOT NULL DEFAULT 1,
            source_type TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', device TEXT NOT NULL DEFAULT '',
            event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'INFO',
            interface TEXT NOT NULL DEFAULT '', ifindex TEXT NOT NULL DEFAULT '', trap_oid TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '', dedup_key TEXT NOT NULL,
            suppressed INTEGER NOT NULL DEFAULT 0, suppression_id INTEGER, metadata TEXT NOT NULL DEFAULT '{}',
            alert_id INTEGER, maintenance_window_id INTEGER
        )
    """)
    raw.execute(
        "INSERT INTO operational_events(first_ts,last_ts,event_count,source_type,source,device,event_type,severity,interface,ifindex,trap_oid,message,dedup_key,suppressed,suppression_id,metadata) "
        "VALUES(123,123,1,'snmp_trap','10.0.0.1','sw1','LINK_DOWN','MAJOR','Gi1','1','','legacy','abc',0,NULL,'{}')")
    raw.commit(); raw.close()

    from netconfig.db import Database
    db = Database(path)
    row = db.operational_events()[0]
    assert row["domain"] == "NETWORK"
    assert row["entity_type"] == "interface" and row["entity_id"] == "Gi1"
    assert row["resource"] == "Gi1"
    assert row["observed_at"] == 123
    assert db.storage_status()["schema_revision"] == "mc3-operational-evidence-1"
    db.close()

def test_manager_bridges_only_new_durable_sensor_transitions(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="sw1", host="10.0.0.1", platform="generic", snmp_version="v2c")
    m.inv.set_facts("sw1", reachable=True, error="")

    assert m._refresh_sensors_and_bridge_events("sw1") == []
    assert m.events.list() == []

    m.inv.set_facts("sw1", reachable=False, error="")
    bridged = m._refresh_sensors_and_bridge_events("sw1")
    assert len(bridged) == 1
    event = bridged[0]
    assert event["event_type"] == "device.unreachable"
    assert event["domain"] == "NETWORK"
    assert event["status"] == "CRITICAL"
    assert event["severity"] == "CRITICAL"
    assert event["entity_type"] == "device" and event["entity_id"] == "sw1"
    assert event["evidence_ref"].startswith("sensor-transition:")

    # Same persisted state is an observation only; it must not generate another event.
    assert m._refresh_sensors_and_bridge_events("sw1") == []
    assert len(m.events.list()) == 1
    m.db.close()


def test_sensor_recovery_transition_becomes_normalized_recovery_event(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="sw1", host="10.0.0.1", platform="generic")
    m.inv.set_facts("sw1", reachable=True, error="")
    m._refresh_sensors_and_bridge_events("sw1")
    m.inv.set_facts("sw1", reachable=False, error="")
    m._refresh_sensors_and_bridge_events("sw1")
    m.inv.set_facts("sw1", reachable=True, error="")
    recovered = m._refresh_sensors_and_bridge_events("sw1")
    assert len(recovered) == 1
    assert recovered[0]["event_type"] == "device.reachable"
    assert recovered[0]["status"] == "OK"
    assert recovered[0]["severity"] == "INFO"
    m.db.close()


def test_unknown_transition_is_informational_not_critical(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.sensors.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK",
                     source="interface_stats")
    before = m.sensors.latest_transition_id()
    m.sensors.upsert("interface.status", device="sw1", resource="1", value="", status="UNKNOWN",
                     source="interface_stats")
    transition = m.sensors.transitions_after_id(before, device="sw1")[0]
    event = m.events.record_sensor_transition(transition)
    assert event["event_type"] == "interface.status.evidence_unavailable"
    assert event["status"] == "UNKNOWN"
    assert event["severity"] == "INFO"
    assert event.get("alert_id") is None
    m.db.close()


def test_sensor_transition_bridge_is_idempotent_by_evidence_reference(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.sensors.upsert("interface.status", device="sw1", resource="7", value="UP", status="OK")
    before = m.sensors.latest_transition_id()
    m.sensors.upsert("interface.status", device="sw1", resource="7", value="DOWN", status="WARNING")
    transition = m.sensors.transitions_after_id(before, device="sw1")[0]
    first = m.events.record_sensor_transition(transition)
    second = m.events.record_sensor_transition(transition)
    assert first["id"] == second["id"]
    assert len(m.events.list()) == 1
    assert first["event_type"] == "interface.down"
    m.db.close()


def test_legacy_syslog_and_trap_calls_are_normalized_at_event_boundary(tmp_path):
    m = Manager(str(tmp_path / "home"))
    config = m.events.record(
        source_type="syslog", source="10.0.0.1", device="sw1",
        event_type="CONFIG_CHANGE", severity="NOTICE", message="configured", now=100)
    trap = m.events.record(
        source_type="snmp_trap", source="10.0.0.1", device="sw1", interface="Gi1",
        event_type="LINK_DOWN", severity="MAJOR", message="down", now=200)
    auth = m.events.record(
        source_type="snmp_trap", source="10.0.0.1", device="sw1",
        event_type="AUTH_FAILURE", severity="WARNING", message="auth", now=300)
    assert config["domain"] == "CONFIGURATION" and config["entity_type"] == "device"
    assert trap["domain"] == "NETWORK" and trap["entity_type"] == "interface"
    assert trap["resource"] == "Gi1" and trap["entity_id"] == "Gi1"
    assert auth["domain"] == "SECURITY"
    m.db.close()


def test_dependency_suppression_semantics_are_preserved(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    monkeypatch.setattr(m, "downstream_impact", lambda *a, **k: {
        "devices": [{"device": "core"}, {"device": "access"}]
    })
    base = time.time()
    root = m.events.record(
        source_type="snmp_trap", device="core", interface="Gi1",
        event_type="LINK_DOWN", severity="MAJOR", message="down", now=base)
    m.events.suppress_downstream("core", "Gi1", root["id"], now=base)
    child = m.events.record(
        source_type="syslog", device="access", event_type="SYSLOG",
        severity="WARNING", message="child", now=base + 1)
    assert child["suppressed"] == 1
    assert m.events.suppressions(True)[0]["target_device"] == "access"
    m.db.close()


def test_events_api_filters_and_detail_include_related_sensor(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.sensors.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK")
    before = m.sensors.latest_transition_id()
    m.sensors.upsert("interface.status", device="sw1", resource="1", value="DOWN", status="WARNING")
    transition = m.sensors.transitions_after_id(before, device="sw1")[0]
    event = m.events.record_sensor_transition(transition)
    _, raw = ApiTokens(m.db.conn).create("events-reader", ["events:read"], role="viewer")
    server, thread = _start_api(m)
    try:
        status, payload = _api(server, raw, "/api/v1/events?domain=NETWORK&entity_type=interface")
        assert status == 200 and payload["events"][0]["id"] == event["id"]
        status, payload = _api(server, raw, f"/api/v1/events/{event['id']}")
        assert status == 200
        assert payload["event"]["evidence_ref"].startswith("sensor-transition:")
        assert payload["related_sensor"]["sensor_type"] == "interface.status"
        assert payload["related_sensor"]["status"] == "WARNING"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); m.db.close()


def test_events_web_detail_shows_mc3_semantics_and_current_sensor(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.sensors.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK")
    before = m.sensors.latest_transition_id()
    m.sensors.upsert("interface.status", device="sw1", resource="1", value="DOWN", status="WARNING")
    transition = m.sensors.transitions_after_id(before, device="sw1")[0]
    event = m.events.record_sensor_transition(transition)
    server, thread, sid = _start_web(m)
    try:
        status, text = _web_get(server, sid, f"/events?id={event['id']}")
        assert status == 200
        assert "MC-3 normalized cross-domain operational evidence" in text
        assert "Evidence reference" in text and "sensor-transition:" in text
        assert "Current related Sensor" in text and "interface.status" in text
        assert "NETWORK" in text and "interface.down" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); m.db.close()
