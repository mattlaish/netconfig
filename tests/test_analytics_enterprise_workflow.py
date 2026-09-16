import http.client
import json
import threading
import urllib.parse

from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server


def _device(manager, name, host):
    manager.inv.upsert(
        name=name, host=host, port=22, platform="cisco_iosxe", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["test"], notes="", snmp_version="", snmp_ref=None,
    )


def _manager(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "sw1", "192.0.2.10")
    _device(manager, "sw2", "192.0.2.11")
    _device(manager, "sw3", "192.0.2.12")
    # Deterministic numeric time-series evidence without requiring a live gNMI target.
    manager.db.conn.execute(
        "INSERT INTO telemetry_subscriptions (name,device,path,mode,encoding,sample_interval_ms,heartbeat_interval_ms,"
        "window_seconds,collection_interval_seconds,retention_days,next_run_ts,enabled,state,created_ts,updated_ts) "
        "VALUES ('cap','sw1','/interfaces','SAMPLE','json_ietf',10000,0,30,60,30,0,1,'IDLE',1,1)"
    )
    sid = manager.db.conn.execute("SELECT id FROM telemetry_subscriptions WHERE name='cap'").fetchone()["id"]
    for idx, value in enumerate((30.0, 32.0, 31.0, 85.0), start=1):
        manager.db.conn.execute(
            "INSERT INTO telemetry_points (subscription_id,device,path,value_path,observed_ts,source_ts,value_type,numeric_value,text_value) "
            "VALUES (?,?,?,?,?,0,'number',?,'')",
            (sid, "sw1", "/interfaces", "$.utilization", float(idx), value),
        )
    manager.db.conn.commit()
    return manager


def test_persisted_insight_lifecycle_and_health_refresh(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.events.record(source_type="test", device="sw1", event_type="INTERFACE_DOWN", severity="WARNING")
        result = manager.analytics.refresh("sw1", actor="alice")
        assert result["capacity"]["insight"]["insight_type"] == "CAPACITY"
        assert result["failure_risk"]["insight"]["insight_type"] == "FAILURE_RISK"
        health = result["health"]["insight"]
        assert health["insight_type"] == "HEALTH"
        assert health["state"] == "NEW"
        updated = manager.analytics.set_state(health["id"], "ACKNOWLEDGED", "bob", "investigating")
        assert updated["state"] == "ACKNOWLEDGED"
        assert updated["acknowledged_by"] == "bob"
        resolved = manager.analytics.set_state(health["id"], "RESOLVED", "bob", "cleared")
        assert resolved["state"] == "RESOLVED"
        assert manager.analytics.dashboard()["insights_total"] >= 3
        assert manager.analytics.jobs(20)
    finally:
        manager.close()


def test_impact_simulation_uses_managed_directional_topology_only(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.db.set_neighbors("sw1", [{
            "protocol":"lldp", "local_port":"Gi1", "neighbor_device":"sw2",
            "managed_neighbor":True, "resolution_state":"RESOLVED", "port_id":"Gi1",
        }])
        manager.db.set_neighbors("sw2", [{
            "protocol":"lldp", "local_port":"Gi2", "neighbor_device":"sw3",
            "managed_neighbor":False, "resolution_state":"UNMANAGED", "port_id":"Gi1",
        }])
        result = manager.analytics.simulate_impact("sw1", actor="alice", max_depth=5)
        devices = {x["object_id"] for x in result["affected"] if x["object_type"] == "DEVICE"}
        assert devices == {"sw2"}
        assert "sw3" not in devices
        insight = result["insight"]
        assert insight["insight_type"] == "DEPENDENCY_IMPACT"
        assert insight["affected"]
        assert "action" not in insight["evidence"]
    finally:
        manager.close()


def _start_console(manager, role="operator"):
    web._SESSIONS.clear()
    token, csrf = "analytics-session", "analytics-csrf"
    web._SESSIONS[token] = {"username":"analyst", "role":role, "csrf":csrf, "created":1.0}
    Console.manager = manager; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    return server, thread, token, csrf


def _request(server, token, method, path, form=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Cookie": f"ncsid={token}"}; body = None
    if form is not None:
        body = urllib.parse.urlencode(form); headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse(); data = response.read(); out = (response.status, dict(response.getheaders()), data)
    conn.close(); return out


def test_network_intelligence_ui_operator_workflow_and_action_boundary(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, headers, _ = _request(server, token, "POST", "/ops-analytics-refresh", {"csrf":csrf, "object_id":"sw1"})
        assert status == 303
        assert "tab=intelligence" in headers["Location"]
        status, _, data = _request(server, token, "GET", "/operations?tab=intelligence")
        text = data.decode()
        assert status == 200
        assert "Persisted insights" in text
        assert "Impact simulation" in text
        assert "Structured Change" in text or "Action boundary" not in text
        insight = manager.analytics.list(insight_type="HEALTH", object_id="sw1", limit=1)[0]
        status, _, data = _request(server, token, "GET", f"/operations?tab=intelligence&insight={insight['id']}")
        text = data.decode()
        assert "Action boundary" in text
        assert "/operations?tab=structured" in text
        assert "automatic remediation" not in text.lower()
        status, _, _ = _request(server, token, "POST", "/ops-insight-state", {"csrf":csrf, "insight_id":str(insight["id"]), "state":"ACKNOWLEDGED", "note":"triage"})
        assert status == 303
        assert manager.analytics.get(insight["id"])["state"] == "ACKNOWLEDGED"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); manager.close()


def test_network_intelligence_viewer_is_read_only(tmp_path):
    manager = _manager(tmp_path)
    manager.analytics.refresh("sw1", actor="seed")
    server, thread, token, _csrf = _start_console(manager, "viewer")
    try:
        status, _, data = _request(server, token, "GET", "/operations?tab=intelligence")
        text = data.decode()
        assert status == 200
        assert "Persisted insights" in text
        assert "Analyze and persist" not in text
        assert "Simulate impact" not in text
        assert 'action="/ops-insight-state"' not in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); manager.close()

def _api_request(server, token, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse(); data = json.loads(response.read().decode() or "{}")
    status = response.status; conn.close(); return status, data


def test_analytics_api_requires_scopes_and_persists_operator_actions(tmp_path):
    manager = _manager(tmp_path)
    token_id, raw = __import__("netconfig.apitokens", fromlist=["ApiTokens"]).ApiTokens(manager.db.conn).create(
        "analytics-operator", {"analytics:read", "analytics:write"}, created_by="test", role="operator"
    )
    Console.manager = manager; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        status, data = _api_request(server, raw, "POST", "/api/v1/analytics/refresh", {"object_id":"sw1"})
        assert status == 201
        assert data["health"]["insight"]["insight_type"] == "HEALTH"
        status, items = _api_request(server, raw, "GET", "/api/v1/analytics/insights?object_id=sw1")
        assert status == 200
        assert any(x["insight_type"] == "CAPACITY" for x in items)
        iid = next(x["id"] for x in items if x["insight_type"] == "HEALTH")
        status, item = _api_request(server, raw, "POST", f"/api/v1/analytics/insights/{iid}/state", {"state":"ACKNOWLEDGED", "note":"api triage"})
        assert status == 200
        assert item["state"] == "ACKNOWLEDGED"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()
