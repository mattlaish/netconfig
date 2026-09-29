import http.client
import json
import threading
import time
import urllib.parse

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig import monitor, netflow
from netconfig.drivers import get_driver
import netconfig.manager as manager_mod
import netconfig.web as web
from netconfig.web import Console, _Server


def _start_web(m, role="admin"):
    web._SESSIONS.clear()
    sid = "mc4-session"; csrf = "mc4-csrf"
    web._SESSIONS[sid] = {"username": "tester", "role": role, "csrf": csrf, "created": 1.0}
    Console.manager = m; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    return server, thread, sid, csrf


def _web_get(server, sid, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Cookie": f"ncsid={sid}"})
    res = conn.getresponse(); data = res.read().decode("utf-8", "replace")
    conn.close(); return res.status, data


def _start_api(m):
    Console.manager = m; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    return server, thread


def _api(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Authorization": "Bearer " + token})
    res = conn.getresponse(); payload = json.loads(res.read() or b"{}")
    conn.close(); return res.status, payload


def test_mc4_schema_and_config_collection_override_are_additive(tmp_path):
    m = Manager(str(tmp_path / "home"))
    device_cols = {r["name"] for r in m.db.conn.execute("PRAGMA table_info(devices)").fetchall()}
    alert_cols = {r["name"] for r in m.db.conn.execute("PRAGMA table_info(operational_alerts)").fetchall()}
    assert "config_collect_command" in device_cols
    assert {"correlation_key", "last_event_id"} <= alert_cols
    assert m.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
    m.db.close()


def test_monitor_sensor_event_alert_recovery_is_one_lifecycle(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="app1", host="192.0.2.10", platform="generic", device_type="system")
    dev = m.inv.get("app1")
    # Establish healthy state: first good observation is not an alert.
    monitor.normalize_results(m, dev, [{"kind": "port", "target": "tcp/443", "status": "open", "value": 2.0}])
    assert m.alert_lifecycle.list() == []
    # One bad transition -> one normalized event -> one operational alert.
    events = monitor.normalize_results(m, dev, [{"kind": "port", "target": "tcp/443", "status": "closed", "value": None}])
    assert len(events) == 1
    assert events[0]["domain"] == "SYSTEM" and events[0]["status"] == "CRITICAL"
    alerts = m.alert_lifecycle.list(); assert len(alerts) == 1 and alerts[0]["state"] == "OPEN"
    alert_id = alerts[0]["id"]
    # Unchanged bad state creates neither a new event nor a second alert.
    assert monitor.normalize_results(m, dev, [{"kind": "port", "target": "tcp/443", "status": "closed", "value": None}]) == []
    assert len(m.alert_lifecycle.list()) == 1
    # Recovery resolves the same lifecycle automatically.
    recovered = monitor.normalize_results(m, dev, [{"kind": "port", "target": "tcp/443", "status": "open", "value": 1.0}])
    assert len(recovered) == 1 and recovered[0]["status"] == "OK"
    alert = m.alert_lifecycle.get(alert_id)
    assert alert["state"] == "RESOLVED" and alert["resolved_by"] == "sensor-recovery"
    # MC-4 authority: no new legacy alert row was written.
    assert m.db.alerts() == []
    m.db.close()


def test_initial_bad_monitor_state_alerts_once(tmp_path):
    m = Manager(str(tmp_path / "home")); m.inv.upsert(name="app1", host="192.0.2.10", platform="generic", device_type="application")
    dev = m.inv.get("app1")
    bad = [{"kind": "http", "target": "https://app/health", "status": "down", "value": None}]
    first = monitor.normalize_results(m, dev, bad)
    assert first and len(m.alert_lifecycle.list()) == 1
    second = monitor.normalize_results(m, dev, bad)
    assert second == [] and len(m.alert_lifecycle.list()) == 1
    m.db.close()


def test_canonical_alert_api_and_legacy_alias_read_same_lifecycle(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.events.record(source_type="snmp_trap", device="sw1", event_type="LINK_DOWN", severity="MAJOR", message="down")
    _, raw = ApiTokens(m.db.conn).create("alerts-reader", ["alerts:read"], role="viewer")
    server, thread = _start_api(m)
    try:
        st1, p1 = _api(server, raw, "/api/v1/alerts?state=OPEN")
        st2, p2 = _api(server, raw, "/api/v1/operational-alerts")
        assert st1 == st2 == 200
        assert p1["authoritative"] == "operational_alerts"
        assert p1["alerts"][0]["id"] == p2["alerts"][0]["id"]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); m.db.close()


def test_alert_navigation_is_consolidated_but_legacy_routes_still_work(tmp_path):
    m = Manager(str(tmp_path / "home")); server, thread, sid, _ = _start_web(m)
    try:
        status, text = _web_get(server, sid, "/alerts")
        assert status == 200 and "Unified Alert Plane" in text
        assert "Active Alerts" in text and 'href="/events"' in text and "Maintenance" in text
        # Events and Ops Alerts are no longer duplicate top-level sidebar items.
        sidebar = text.split('</aside>', 1)[0]
        assert '>Events</a>' not in sidebar and '>Ops Alerts</a>' not in sidebar
        status, text = _web_get(server, sid, "/op-alerts")
        assert status == 303
        status, text = _web_get(server, sid, "/events")
        assert status == 200 and "Operational Events" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); m.db.close()


def test_endpoint_lookup_joins_gateway_arp_to_switch_fdb_before_filter(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="fw1", host="192.0.2.1", platform="generic")
    m.inv.upsert(name="access1", host="192.0.2.2", platform="generic")
    mac = "00:11:22:33:44:55"
    m.db.set_ip_neighbors("fw1", [{"ip": "10.20.30.40", "address_family": "ipv4", "mac": mac,
                                   "ifindex": "20", "ifdescr": "vlan20", "source": "ipNetToPhysicalTable"}])
    m.db.set_vlan_fdb("access1", [{"vlan_id": "20", "fdb_id": "20", "mac": mac,
                                   "bridge_port": "5", "ifindex": "5", "ifdescr": "1/1/5", "source": "Q-BRIDGE-MIB"}])
    rows = m.endpoint_inventory(device="fw1", query="10.20.30.40")
    assert len(rows) == 1
    row = rows[0]
    assert row["attachment"]["device"] == "access1" and row["attachment"]["ifdescr"] == "1/1/5"
    assert row["evidence_chain"]["ip_neighbors"][0]["device"] == "fw1"
    assert row["evidence_chain"]["fdb_candidates"][0]["device"] == "access1"
    m.db.close()


def test_endpoint_api_accepts_ip_search(tmp_path):
    m = Manager(str(tmp_path / "home")); mac="00:11:22:33:44:55"
    m.db.set_ip_neighbors("fw1", [{"ip":"10.0.0.9","address_family":"ipv4","mac":mac,"ifindex":"1","ifdescr":"vlan1","source":"arp"}])
    m.db.set_vlan_fdb("sw1", [{"vlan_id":"1","fdb_id":"1","mac":mac,"bridge_port":"7","ifindex":"7","ifdescr":"Gi1/0/7","source":"fdb"}])
    _, raw = ApiTokens(m.db.conn).create("ep-reader", ["endpoint:read"], role="viewer")
    server, thread = _start_api(m)
    try:
        st, payload = _api(server, raw, "/api/v1/endpoints?q=" + urllib.parse.quote("10.0.0.9"))
        assert st == 200 and payload["summary"]["total"] == 1
        assert payload["endpoints"][0]["attachment"]["ifdescr"] == "Gi1/0/7"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); m.db.close()


def test_netflow_summary_is_aggregated_and_raw_rows_are_advanced(tmp_path):
    flows = [
        {"ts":1,"src":"10.0.0.1","dst":"8.8.8.8","sport":50000,"dport":443,"proto":"TCP","packets":10,"bytes":1000},
        {"ts":2,"src":"10.0.0.1","dst":"8.8.8.8","sport":50001,"dport":443,"proto":"TCP","packets":5,"bytes":500},
        {"ts":3,"src":"10.0.0.2","dst":"1.1.1.1","sport":53000,"dport":53,"proto":"UDP","packets":2,"bytes":100},
    ]
    summary = netflow.summarize_flows(flows)
    assert summary["total_bytes"] == 1600 and summary["top_sources"][0]["label"] == "10.0.0.1"
    assert summary["top_ports"][0]["label"] == "TCP/443" and summary["insights"]

    m = Manager(str(tmp_path / "home")); m.inv.upsert(name="fw1", host="192.0.2.1", platform="generic", netflow=True)
    class FakeCollector:
        def status(self):
            return {"port": 2055}
        def packet_count(self, host):
            return 3
        def flows_for(self, host, limit=500):
            return list(reversed(flows))
    old = Console.netflow; Console.netflow = FakeCollector(); m.settings["netflow_enabled"] = True
    server, thread, sid, _ = _start_web(m)
    try:
        status, text = _web_get(server, sid, "/device?name=fw1")
        assert status == 200
        assert "NetFlow traffic view" in text and "Traffic analysis" in text and "Top sources" in text
        assert "Advanced: raw recent flow records" in text and "TCP/443" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); Console.netflow = old; m.db.close()


def test_config_collection_override_is_visible_bounded_and_used(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    assert m._validate_config_collect_command("show full-configuration") == "show full-configuration"
    with pytest.raises(ValueError):
        m._validate_config_collect_command("config system admin")
    with pytest.raises(ValueError):
        m._validate_config_collect_command("show x; delete y")
    m.inv.upsert(name="fw1", host="192.0.2.1", platform="generic", secret_ref="cred",
                 config_collect_command="show full-configuration")
    m._vault_unlocked = True
    class FakeTP:
        transcript=[]
        def discover_prompt(self):
            return b"#"
        def close(self):
            pass
    class FakeDriver:
        config_command="show running-config"
        def initialize(self, tp, enable_password=None):
            pass
        def run(self, tp, command):
            assert command == "show full-configuration"
            return "config system interface\nend"
        def fetch_config(self, tp):
            raise AssertionError("override must be used")
    monkeypatch.setattr(m, "_connect", lambda dev: (FakeTP(), None))
    monkeypatch.setattr(manager_mod, "get_driver", lambda platform: FakeDriver())
    result = m.collect("fw1")
    assert result.ok and "cli override" in result.message
    assert m.config_collection_method("fw1")["command"] == "show full-configuration"
    m.db.close()


def test_device_add_edit_exposes_effective_and_alternative_collection_command(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="fw1", host="192.0.2.1", platform="generic",
                 config_collect_command="show full-configuration")
    server, thread, sid, _ = _start_web(m)
    try:
        status, text = _web_get(server, sid, "/device-new?name=fw1")
        assert status == 200
        assert "Alternative config collection command" in text
        assert 'value="show full-configuration"' in text
        assert "show running-config" in text and "default_collect_command" in text
        status, text = _web_get(server, sid, "/device?name=fw1")
        assert status == 200 and "Config collection" in text and "device override" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); m.db.close()


def test_http_and_tls_monitor_transitions_normalize_to_application_events(tmp_path):
    m = Manager(str(tmp_path / "home")); m.inv.upsert(name="app1", host="app.example", platform="generic", device_type="application")
    dev = m.inv.get("app1"); url = "https://app.example/health"
    monitor.normalize_results(m, dev, [
        {"kind":"http","target":url,"status":"200","value":20.0},
        {"kind":"tls","target":url,"status":"valid","value":90},
    ])
    events = monitor.normalize_results(m, dev, [
        {"kind":"http","target":url,"status":"503","value":900.0},
        {"kind":"tls","target":url,"status":"invalid","value":-1},
    ])
    types = {e["event_type"] for e in events}
    assert "application.http_status.critical" in types
    assert "application.tls_valid.critical" in types
    assert all(e["domain"] == "APPLICATION" for e in events)
    # response time / expiry remain OK unless an explicit monitor rule breaches.
    assert len(m.alert_lifecycle.list()) == 2
    m.db.close()



def test_r51_active_alert_correlation_key_is_backfilled_before_escalation(tmp_path):
    home = str(tmp_path / "home")
    m = Manager(home)
    event = m.events.record(
        source_type="sensor_transition", source="test", device="sw1",
        event_type="interface.utilization.warning", severity="WARNING",
        message="utilization warning", status="WARNING",
        metadata={"sensor_key":"interface.utilization|sw1|Gi1/0/1",
                  "sensor_type":"interface.utilization",
                  "previous_status":"OK", "new_status":"WARNING"},
        evidence_ref="sensor-transition:9001")
    alert_id = m.db.operational_alert_for_event(event["id"])["id"]
    m.db.conn.execute("UPDATE operational_alerts SET correlation_key='' WHERE id=?", (alert_id,))
    m.db.conn.commit(); m.close()

    # Restart runs the additive R51 -> R52 migration/backfill before new events.
    m = Manager(home)
    try:
        migrated = m.alert_lifecycle.get(alert_id)
        assert migrated["correlation_key"] == "sensor:interface.utilization|sw1|Gi1/0/1"
        m.events.record(
            source_type="sensor_transition", source="test", device="sw1",
            event_type="interface.utilization.critical", severity="CRITICAL",
            message="utilization critical", status="CRITICAL",
            metadata={"sensor_key":"interface.utilization|sw1|Gi1/0/1",
                      "sensor_type":"interface.utilization",
                      "previous_status":"WARNING", "new_status":"CRITICAL"},
            evidence_ref="sensor-transition:9002")
        active = m.alert_lifecycle.list(state="OPEN")
        assert len(active) == 1 and active[0]["id"] == alert_id
        assert active[0]["severity"] == "CRITICAL"
    finally:
        m.close()


def test_manual_resolve_reopens_same_lifecycle_when_sensor_still_firing(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="app1", host="app.example", platform="generic", device_type="application")
    dev = m.inv.get("app1")
    bad = [{"kind":"http", "target":"https://app/health", "status":"503", "value":700.0}]
    monitor.normalize_results(m, dev, bad)
    alert = m.alert_lifecycle.list(state="OPEN")[0]
    m.alert_lifecycle.resolve(alert["id"], "operator", "investigating")
    assert m.alert_lifecycle.get(alert["id"])["state"] == "RESOLVED"

    # No Sensor transition occurs (CRITICAL -> CRITICAL), but DB-only reconcile
    # must reopen the same lifecycle rather than leave a firing Sensor unpaged.
    assert monitor.normalize_results(m, dev, bad) == []
    reopened = m.alert_lifecycle.get(alert["id"])
    assert reopened["state"] == "OPEN"
    assert reopened["resolved_by"] == "" and reopened["resolved_ts"] is None
    assert len(m.alert_lifecycle.list(state="OPEN")) == 1
    m.close()


def test_maintenance_expiry_re_evaluates_persistent_sensor_event(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="app1", host="app.example", platform="generic", device_type="application")
    dev = m.inv.get("app1")
    window = m.alert_lifecycle.add_maintenance(
        "deploy", "operator", minutes=60, device="app1", now=time.time())
    bad = [{"kind":"http", "target":"https://app/health", "status":"503", "value":700.0}]
    monitor.normalize_results(m, dev, bad)
    assert m.alert_lifecycle.list(state="OPEN") == []

    # Simulate natural expiry, not cancellation. The unchanged bad observation
    # has no new Sensor transition, so reconcile must re-evaluate durable evidence.
    m.db.conn.execute("UPDATE maintenance_windows SET end_ts=? WHERE id=?", (time.time()-1, window["id"]))
    m.db.conn.commit()
    assert monitor.normalize_results(m, dev, bad) == []
    active = m.alert_lifecycle.list(state="OPEN")
    assert len(active) == 1 and active[0]["device"] == "app1"
    assert active[0]["last_ts"] >= window["start_ts"]
    m.close()


def test_config_collection_rejects_cli_error_output_and_does_not_archive(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="fw1", host="192.0.2.1", platform="fortigate_fortios")

    class FakeTP:
        transcript = []

        def discover_prompt(self):
            return b"#"

        def execute(self, command, **kwargs):
            assert command == "show full-configuration"
            return "Unknown action 0\nCommand fail. Return code -61"

        def close(self):
            pass

    monkeypatch.setattr(m, "_connect", lambda dev: (FakeTP(), None))
    result = m.collect("fw1")
    assert result.ok is False
    assert "configuration collection command failed" in result.message
    assert m.store.current("fw1") is None
    m.close()


def test_fortigate_native_driver_and_read_only_override_boundary(tmp_path):
    driver = get_driver("fortigate")
    assert driver.name == "fortigate_fortios"
    assert driver.config_command == "show full-configuration"
    assert driver.disable_paging == []

    m = Manager(str(tmp_path / "home"))
    try:
        assert m._validate_config_collect_command("/export") == "/export"
        with pytest.raises(ValueError):
            m._validate_config_collect_command("/export file=netconfig-backup")
        with pytest.raises(ValueError):
            m._validate_config_collect_command("/export terse")
    finally:
        m.close()


def test_stale_arp_downgrades_combined_endpoint_confidence(tmp_path):
    m = Manager(str(tmp_path / "home")); mac = "00:11:22:33:44:55"
    m.db.set_ip_neighbors("fw1", [{"ip":"10.0.0.9", "address_family":"ipv4", "mac":mac,
                                    "ifindex":"1", "ifdescr":"vlan1", "source":"arp"}])
    m.db.set_vlan_fdb("sw1", [{"vlan_id":"1", "fdb_id":"1", "mac":mac,
                                "bridge_port":"7", "ifindex":"7", "ifdescr":"Gi1/0/7", "source":"fdb"}])
    m.db.conn.execute("UPDATE ip_neighbors SET ts=? WHERE device='fw1' AND ip='10.0.0.9'", (time.time()-7200,))
    m.db.conn.execute("UPDATE vlan_fdb SET ts=? WHERE device='sw1' AND mac=?", (time.time(), mac))
    m.db.conn.commit()
    row = m.endpoint_inventory(query="10.0.0.9")[0]
    assert row["status"] == "ATTACHED"
    assert row["confidence"] == "PARTIAL"
    assert row["ip_mapping_fresh"] is False
    assert row["evidence_chain"]["ip_neighbors"][0]["fresh"] is False
    m.close()
