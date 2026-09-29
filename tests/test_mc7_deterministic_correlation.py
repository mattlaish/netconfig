import http.client
import json
import threading
import urllib.parse

from netconfig.apitokens import ApiTokens
from netconfig.correlation import RULE_SET_VERSION
from netconfig.manager import Manager
from netconfig.postgres_core import postgres_schema_statements
from netconfig.web import Console, _Server


def _manager(tmp_path):
    return Manager(str(tmp_path / "home"))


def _sensor(m, *, ts, device="app1", resource="payment-api", status="CRITICAL", previous="OK"):
    c = m.db.conn
    c.execute(
        "INSERT INTO sensor_transitions(sensor_key,sensor_type,device,resource,previous_status,new_status,"
        "previous_value,new_value,source,observed_at,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"application.http_status|{device}|{resource}", "application.http_status", device, resource,
         previous, status, "200", "503" if status != "OK" else "200", "monitor", ts, "{}", ts),
    )
    c.commit()
    return c.execute("SELECT max(id) AS id FROM sensor_transitions").fetchone()["id"]


def _alert(m, *, ts, device="app1", severity="CRITICAL", state="OPEN"):
    c = m.db.conn
    c.execute(
        "INSERT INTO operational_events(first_ts,last_ts,event_count,source_type,source,device,event_type,severity,"
        "message,dedup_key,suppressed,metadata,domain,entity_type,entity_id,resource,status,observed_at,evidence_ref) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ts, ts, 1, "sensor_transition", "monitor", device, "application.http_status.critical", severity,
         "HTTP degraded", f"mc7-event-{device}-{ts}", 0, "{}", "APPLICATION", "application", device,
         "payment-api", "CRITICAL", ts, f"mc7:{device}:{ts}"),
    )
    event_id = c.execute("SELECT max(id) AS id FROM operational_events").fetchone()["id"]
    c.execute(
        "INSERT INTO operational_alerts(event_id,correlation_key,last_event_id,state,severity,device,event_type,message,"
        "first_ts,last_ts,event_count) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, f"sensor:app|{device}", event_id, state, severity, device,
         "application.http_status.critical", "HTTP degraded", ts, ts, 1),
    )
    c.commit()
    return c.execute("SELECT max(id) AS id FROM operational_alerts").fetchone()["id"]


def _insight(m, *, ts, object_id="r1", insight_type="L3_PATH", severity="WARNING", path_status="INCOMPLETE"):
    c = m.db.conn
    evidence = {"path": {"status": path_status}} if insight_type == "L3_PATH" else {}
    c.execute(
        "INSERT INTO network_insights(tenant_id,insight_type,object_type,object_id,severity,confidence,summary,state,"
        "evidence_json,affected_json,fingerprint,first_seen_ts,last_seen_ts,occurrence_count) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("default", insight_type, "DEVICE", object_id, severity, 0.8, f"{insight_type} evidence", "NEW",
         json.dumps(evidence), "[]", f"mc7-{insight_type}-{object_id}-{ts}-{path_status}", ts, ts, 1),
    )
    c.commit()
    return c.execute("SELECT max(id) AS id FROM network_insights").fetchone()["id"]


def _link(m, incident, kind, source_id):
    m.incidents.link_evidence(incident, kind, source_id, "alice")


def _seed_service_relation(m):
    m.dependencies.put_entity("service:payment", "SERVICE", "Payment", metadata={"device": "app1"}, actor="seed")
    m.dependencies.put_entity("network:r1", "SERVICE", "R1 path", metadata={"device": "r1"}, actor="seed")
    m.dependencies.put_entity("network:fw1", "SERVICE", "FW1", metadata={"device": "fw1"}, actor="seed")
    m.dependencies.put_dependency(
        "service:payment", "network:fw1", "ROUTES_THROUGH", evidence_state="CONFIGURED",
        provenance="operator", vrf="prod", destination_prefix="10.0.0.0/24", actor="seed")
    m.dependencies.put_dependency(
        "network:fw1", "network:r1", "ROUTES_THROUGH", evidence_state="CONFIGURED",
        provenance="operator", vrf="prod", destination_prefix="10.0.0.0/24", actor="seed")


def test_mc7_schema_and_postgres_surface(tmp_path):
    m = _manager(tmp_path)
    try:
        assert m.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
        tables = {r["name"] for r in m.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "correlation_hypotheses" in tables
        pg = "\n".join(postgres_schema_statements()).lower()
        assert "create table if not exists correlation_hypotheses" in pg
    finally:
        m.close()


def test_mc7_same_evidence_is_deterministic_and_replay_idempotent(tmp_path):
    m = _manager(tmp_path)
    try:
        _seed_service_relation(m)
        key = m.incidents.create("Payment degradation", created_by="alice")["incident_key"]
        change = m.db.record_change_event(
            10, "EXECUTION_COMPLETED", "executed", "alice", "Firewall change",
            metadata={"affected_devices": ["fw1"]}, source_ts=100.0, received_ts=101.0)
        sid = _sensor(m, ts=120.0)
        aid = _alert(m, ts=121.0)
        for kind, ref in (("change_event", change["id"]), ("sensor_transition", sid), ("operational_alert", aid)):
            _link(m, key, kind, ref)

        first = m.correlation.correlate(key, actor="alice")
        before = [dict(r) for r in m.db.conn.execute("SELECT * FROM correlation_hypotheses ORDER BY id").fetchall()]
        second = m.correlation.correlate(key, actor="alice")
        after = [dict(r) for r in m.db.conn.execute("SELECT * FROM correlation_hypotheses ORDER BY id").fetchall()]
        assert [(x["hypothesis_type"], x["confidence"], x["evidence_fingerprint"]) for x in first["hypotheses"]] == [
            (x["hypothesis_type"], x["confidence"], x["evidence_fingerprint"]) for x in second["hypotheses"]]
        assert [(x["id"], x["hypothesis_key"], x["updated_at"]) for x in before] == [
            (x["id"], x["hypothesis_key"], x["updated_at"]) for x in after]
        assert any(x["hypothesis_type"] == "RECENT_CONFIGURATION_CHANGE" for x in first["hypotheses"])
        assert first["rule_version"] == RULE_SET_VERSION and first["causation_confirmed"] is False
    finally:
        m.close()


def test_mc7_unrelated_simultaneous_events_do_not_correlate_by_time_alone(tmp_path):
    m = _manager(tmp_path)
    try:
        key = m.incidents.create("Unrelated events", created_by="alice")["incident_key"]
        change = m.db.record_change_event(
            11, "EXECUTION_COMPLETED", "executed", "alice", "FW change",
            metadata={"affected_devices": ["fw1"]}, source_ts=100.0, received_ts=100.0)
        sid = _sensor(m, ts=101.0, device="app1")
        _link(m, key, "change_event", change["id"])
        _link(m, key, "sensor_transition", sid)
        result = m.correlation.correlate(key)
        assert result["hypotheses"] == []
    finally:
        m.close()


def test_mc7_dependency_relationship_allows_cross_entity_correlation(tmp_path):
    m = _manager(tmp_path)
    try:
        _seed_service_relation(m)
        key = m.incidents.create("Dependency correlation", created_by="alice")["incident_key"]
        change = m.db.record_change_event(
            12, "EXECUTION_COMPLETED", "executed", "alice", "FW policy updated",
            metadata={"affected_devices": ["fw1"]}, source_ts=200.0, received_ts=200.0)
        sid = _sensor(m, ts=220.0, device="app1")
        _link(m, key, "change_event", change["id"])
        _link(m, key, "sensor_transition", sid)
        result = m.correlation.correlate(key)
        hyp = next(x for x in result["hypotheses"] if x["hypothesis_type"] == "RECENT_CONFIGURATION_CHANGE")
        assert hyp["confidence"] >= 70
        assert any("dependency_path" in x["reason"] for x in hyp["supporting_evidence"])
    finally:
        m.close()


def test_mc7_contradictory_healthy_evidence_lowers_confidence(tmp_path):
    m = _manager(tmp_path)
    try:
        _seed_service_relation(m)
        key = m.incidents.create("Contradiction", created_by="alice")["incident_key"]
        bad = _insight(m, ts=300.0, object_id="r1", path_status="INCOMPLETE")
        sid = _sensor(m, ts=305.0, device="app1")
        _link(m, key, "analytics_insight", bad)
        _link(m, key, "sensor_transition", sid)
        first = m.correlation.correlate(key)
        initial = next(x for x in first["hypotheses"] if x["hypothesis_type"] == "NETWORK_PATH_DEGRADATION")

        good = _insight(m, ts=306.0, object_id="r1", severity="INFO", path_status="REACHED_TERMINAL")
        _link(m, key, "analytics_insight", good)
        second = m.correlation.correlate(key)
        updated = next(x for x in second["hypotheses"] if x["hypothesis_type"] == "NETWORK_PATH_DEGRADATION")
        assert updated["confidence"] < initial["confidence"]
        assert updated["contradicting_evidence"]
        assert updated["score_breakdown"]["contradiction"] > 0
    finally:
        m.close()


def test_mc7_stale_or_inferred_dependency_is_not_used_for_correlation(tmp_path):
    m = _manager(tmp_path)
    try:
        m.dependencies.put_entity("service:payment", "SERVICE", "Payment", metadata={"device": "app1"}, actor="seed")
        m.dependencies.put_entity("network:fw1", "SERVICE", "FW1", metadata={"device": "fw1"}, actor="seed")
        m.dependencies.put_dependency(
            "service:payment", "network:fw1", "DEPENDS_ON", evidence_state="INFERRED",
            provenance="flow", evidence_ref="flow:1", max_age_seconds=3600, actor="seed")
        key = m.incidents.create("Inferred relation", created_by="alice")["incident_key"]
        change = m.db.record_change_event(
            13, "EXECUTION_COMPLETED", "executed", "alice", "FW change",
            metadata={"affected_devices": ["fw1"]}, source_ts=400.0, received_ts=400.0)
        sid = _sensor(m, ts=410.0, device="app1")
        _link(m, key, "change_event", change["id"])
        _link(m, key, "sensor_transition", sid)
        assert m.correlation.correlate(key)["hypotheses"] == []
    finally:
        m.close()


def test_mc7_language_never_claims_confirmed_causation(tmp_path):
    m = _manager(tmp_path)
    try:
        _seed_service_relation(m)
        key = m.incidents.create("Language", created_by="alice")["incident_key"]
        change = m.db.record_change_event(
            14, "EXECUTION_COMPLETED", "executed", "alice", "FW change",
            metadata={"affected_devices": ["fw1"]}, source_ts=500.0, received_ts=500.0)
        sid = _sensor(m, ts=510.0)
        _link(m, key, "change_event", change["id"])
        _link(m, key, "sensor_transition", sid)
        result = m.correlation.correlate(key)
        rendered = json.dumps(result).lower()
        assert "root cause proven" not in rendered
        assert "attack confirmed" not in rendered
        assert "causation_confirmed\": true" not in rendered
        assert "consistent with" in rendered or "evidence supports" in rendered
    finally:
        m.close()


def test_mc7_api_read_write_scope_and_investigation_surface(tmp_path):
    m = _manager(tmp_path)
    server = None
    try:
        _seed_service_relation(m)
        key = m.incidents.create("API correlation", created_by="admin")["incident_key"]
        change = m.db.record_change_event(
            15, "EXECUTION_COMPLETED", "executed", "admin", "FW change",
            metadata={"affected_devices": ["fw1"]}, source_ts=600.0, received_ts=600.0)
        sid = _sensor(m, ts=610.0)
        _link(m, key, "change_event", change["id"])
        _link(m, key, "sensor_transition", sid)

        tokens = ApiTokens(m.db.conn)
        _, reader = tokens.create("mc7-reader", ["incident:read"], role="viewer")
        _, writer = tokens.create("mc7-writer", ["incident:read", "incident:write"], role="operator")
        Console.manager = m
        Console.tls_enabled = False
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def request(method, path, token):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            headers = {"Authorization": "Bearer " + token}
            body = ""
            if method == "POST":
                body = urllib.parse.urlencode({})
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            conn.request(method, path, body=body, headers=headers)
            res = conn.getresponse()
            payload = json.loads(res.read() or b"{}")
            status = res.status
            conn.close()
            return status, payload

        status, _ = request("POST", f"/api/v1/incidents/{key}/correlate", reader)
        assert status == 403
        status, result = request("POST", f"/api/v1/incidents/{key}/correlate", writer)
        assert status == 201 and result["hypotheses"]
        status, hypotheses = request("GET", f"/api/v1/incidents/{key}/hypotheses", reader)
        assert status == 200 and hypotheses
        status, investigation = request("GET", f"/api/v1/incidents/{key}/investigation", reader)
        assert status == 200 and investigation["current_hypothesis"]
        assert investigation["root_cause"] is None
        assert investigation["root_cause_state"] == "NOT_CONFIRMED"
    finally:
        if server:
            server.shutdown(); server.server_close()
        m.close()
