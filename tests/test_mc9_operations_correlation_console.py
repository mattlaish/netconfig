import http.client
import json
import threading
import time

from netconfig.manager import Manager
from netconfig.operations_correlation import OperationsCorrelationConsole
from netconfig.web import Console, _Server
import netconfig.web as web
from netconfig.web_ui import render_incident_investigation


def _manager(tmp_path):
    return Manager(str(tmp_path / "home"))


def _hypothesis(manager, incident, *, affected=None, support=None, contradict=None, summary="Evidence is consistent with a recent change"):
    now = time.time()
    manager.db.conn.execute(
        "INSERT INTO correlation_hypotheses(incident_id,hypothesis_key,hypothesis_type,summary,confidence,confidence_label,"
        "initiating_source_type,initiating_source_ref,first_evidence_at,last_evidence_at,supporting_json,contradicting_json,"
        "affected_entities_json,rule_id,rule_version,evidence_fingerprint,score_breakdown_json,active,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
        (incident["id"], "hyp-" + incident["incident_key"], "RECENT_CONFIGURATION_CHANGE", summary, 80, "HIGH",
         "change_event", "42", now-60, now, json.dumps(support or []), json.dumps(contradict or []),
         json.dumps(affected or []), "recent-change", "mc7-r55-v1", "f"*64, "{}", now, now))
    manager.db.conn.commit()


def _start(manager, role="viewer"):
    web._SESSIONS.clear(); token="mc9-session"
    web._SESSIONS[token]={"username":"tester","role":role,"csrf":"csrf","created":time.time()}
    Console.manager=manager; Console.tls_enabled=False; Console.netflow=None
    server=_Server(("127.0.0.1",0),Console); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    return server,thread,token


def _get(server, token, path):
    c=http.client.HTTPConnection("127.0.0.1",server.server_address[1],timeout=5)
    c.request("GET",path,headers={"Cookie":f"ncsid={token}"}); r=c.getresponse(); data=r.read().decode(); status=r.status; c.close(); return status,data


def _stop(server,thread,manager):
    server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); manager.close()


def test_mc9_empty_console_is_read_only_and_truthful(tmp_path):
    m=_manager(tmp_path)
    try:
        data=m.operations_console.dashboard()
        assert data["active_incident_count"] == 0
        assert data["impacted_services"] == []
        assert data["critical_alerts"] == []
        assert data["truth"] == {"correlation_is_causation":False,"device_polling_performed":False,"external_actions_performed":False}
    finally: m.close()


def test_mc9_dashboard_correlates_incident_service_and_change_without_claiming_causation(tmp_path):
    m=_manager(tmp_path)
    try:
        m.dependencies.put_entity("svc:payments","SERVICE","Payments",actor="test")
        inc=m.incidents.create("Checkout degraded",severity="HIGH",created_by="test")
        _hypothesis(m,inc,affected=[{"entity_key":"svc:payments"}],support=[{"source_type":"change_event","source_ref":"42","summary":"change applied"}])
        data=m.operations_console.dashboard()
        assert data["active_incidents"][0]["current_hypothesis"]["confidence"] == 80
        assert [x["entity_key"] for x in data["impacted_services"]] == ["svc:payments"]
        assert data["correlated_changes"][0]["source_ref"] == "42"
        assert data["truth"]["correlation_is_causation"] is False
    finally: m.close()


def test_mc9_unknown_and_stale_dependency_evidence_stays_explicit(tmp_path):
    m=_manager(tmp_path)
    try:
        for key in ("svc:a","svc:b","svc:c"):
            m.dependencies.put_entity(key,"SERVICE",key,actor="test")
        m.dependencies.put_dependency("svc:a","svc:b","DEPENDS_ON",evidence_state="UNKNOWN",provenance="operator",actor="test")
        m.dependencies.put_dependency("svc:a","svc:c","DEPENDS_ON",evidence_state="DISCOVERED",provenance="cmdb",evidence_ref="ref-1",observed_ts=time.time()-7200,max_age_seconds=60,actor="test")
        states={x["console_state"] for x in m.operations_console.dashboard()["unhealthy_dependencies"]}
        assert {"UNKNOWN","STALE"} <= states
    finally: m.close()


class _Collector:
    max_flows=20
    def __init__(self, now):
        self.now=now
        self.rows={"192.0.2.1":[
            {"ts":now-30,"exporter":"192.0.2.1","src":"10.0.0.1","dst":"10.0.0.2","sport":1234,"dport":443,"proto":"TCP","packets":10,"bytes":1000},
            {"ts":now-330,"exporter":"192.0.2.1","src":"10.0.0.3","dst":"10.0.0.2","sport":2222,"dport":53,"proto":"UDP","packets":5,"bytes":500},
            {"ts":now-7200,"exporter":"192.0.2.1","src":"old","dst":"old","sport":1,"dport":1,"proto":"TCP","packets":1,"bytes":9999},
        ],"192.0.2.2":[{"ts":now-20,"exporter":"192.0.2.2","src":"10.0.0.1","dst":"10.0.0.4","sport":1,"dport":80,"proto":"TCP","packets":2,"bytes":250}]}
    def exporters(self):
        return {"192.0.2.1": 3, "192.0.2.2": 1}

    def flows_for(self, exporter, limit=100):
        return list(reversed(self.rows.get(exporter, [])))[:limit]

    def status(self):
        return {"running": True, "exporters": 2}


def test_mc9_global_traffic_window_trend_and_exporters_are_bounded(tmp_path, monkeypatch):
    m=_manager(tmp_path); now=10000.0
    try:
        monkeypatch.setattr(m,"endpoint_inventory",lambda: [{"mac":"aa:bb","ipv4":["10.0.0.1"],"ipv6":[],"status":"ATTACHED","confidence":"HIGH","attachment":{"device":"sw1","ifdescr":"Gi1/0/1"}}])
        data=m.operations_console.traffic(_Collector(now),window_seconds=3600,bucket_seconds=300,now=now)
        assert data["summary"]["flow_count"] == 3
        assert data["summary"]["total_bytes"] == 1750
        assert len(data["trend"]) == 2
        assert {x["exporter"] for x in data["exporters"]} == {"192.0.2.1","192.0.2.2"}
        assert data["summary"]["top_sources"][0]["endpoint"]["attachment"]["device"] == "sw1"
        assert data["ring_bounded"] is True
    finally: m.close()


def test_mc9_viewer_routes_are_read_only_and_legacy_routes_remain_compatible(tmp_path):
    m=_manager(tmp_path); server,thread,token=_start(m,"viewer")
    try:
        for path in ("/","/dashboard","/traffic","/events","/alerts?view=active","/incidents"):
            status,text=_get(server,token,path); assert status==200, path
        status,_text=_get(server,token,"/op-alerts"); assert status==303
        _,dash=_get(server,token,"/dashboard")
        assert "Operations Correlation Dashboard" in dash
        assert "Run correlation" not in dash and "incident-correlate" not in dash and "maintenance-add" not in dash
        _,alerts=_get(server,token,"/alerts")
        assert 'href="/incidents"' in alerts and "Maintenance" in alerts
    finally: _stop(server,thread,m)


def test_mc9_console_escapes_untrusted_incident_and_hypothesis_content(tmp_path):
    m=_manager(tmp_path); server,thread,token=_start(m,"viewer")
    try:
        inc=m.incidents.create('<script>alert(1)</script>',created_by="test")
        _hypothesis(m,inc,summary='<img src=x onerror=alert(1)>')
        status,text=_get(server,token,"/dashboard")
        assert status==200
        assert '<script>alert(1)</script>' not in text and '&lt;script&gt;alert(1)&lt;/script&gt;' in text
        assert '<img src=x onerror=alert(1)>' not in text and '&lt;img src=x onerror=alert(1)&gt;' in text
    finally: _stop(server,thread,m)


def test_mc9_current_hypothesis_shows_supporting_and_contradicting_evidence_details():
    inv={"hypotheses":[{"hypothesis_type":"NETWORK_PATH_DEGRADATION","confidence":70,"confidence_label":"MEDIUM","summary":"evidence supports degradation; causation is not established","rule_version":"mc7-r55-v1","supporting_evidence":[{"source_type":"external_event","source_ref":"ndr:1","summary":"packet loss"}],"contradicting_evidence":[{"source_type":"sensor_transition","source_ref":"9","summary":"link recovered"}]}],"timeline":[],"impact":{"affected_entities":[],"evidence_count":0},"related_alerts":[],"related_changes":[],"network_evidence":[],"security_evidence":[],"infrastructure_evidence":[],"advanced_evidence":[]}
    text=render_incident_investigation(inv)
    assert "Supporting evidence" in text and "Contradicting evidence" in text
    assert "ndr:1" in text and "link recovered" in text
    assert "does not confirm causation" in text and "confirmed root cause" in text


def test_mc9_incident_console_keeps_large_timeline_bounded_and_current_hypothesis(tmp_path):
    m=_manager(tmp_path)
    try:
        inc=m.incidents.create("Large timeline",created_by="test")
        _hypothesis(m,inc)
        for i in range(550):
            m.db.audit("sensor","mc9_event",inc["incident_key"],f"event {i}")
        data=m.operations_console.incident(inc["incident_key"],timeline_limit=500)
        assert len(data["timeline"]) == 500
        assert data["current_hypothesis"]["hypothesis_type"] == "RECENT_CONFIGURATION_CHANGE"
        assert data["root_cause"] is None and data["root_cause_state"] == "NOT_CONFIRMED"
    finally: m.close()
