import http.client
import json
import threading
import urllib.parse

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.cli import build_parser
from netconfig.manager import Manager
import netconfig.operational_alerts as oa
import netconfig.web as web
from netconfig.web import Console, _Server


def _api_request(server, token, method, path, form=None):
    conn=http.client.HTTPConnection("127.0.0.1",server.server_address[1],timeout=5)
    headers={"Authorization":"Bearer "+token}; body=None
    if form is not None:
        body=urllib.parse.urlencode(form); headers["Content-Type"]="application/x-www-form-urlencoded"
    conn.request(method,path,body=body,headers=headers); r=conn.getresponse(); data=r.read(); status=r.status
    conn.close(); return status,json.loads(data or b"{}")


def _start_api(m):
    Console.manager=m; Console.tls_enabled=False
    server=_Server(("127.0.0.1",0),Console); t=threading.Thread(target=server.serve_forever,daemon=True); t.start(); return server,t


def _start_web(m, role):
    web._SESSIONS.clear(); token="ni4-session"; csrf="ni4-csrf"
    web._SESSIONS[token]={"username":"tester","role":role,"csrf":csrf,"created":1.0}
    Console.manager=m; Console.tls_enabled=False
    server=_Server(("127.0.0.1",0),Console); t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
    return server,t,token,csrf


def _web_request(server, token, method, path, form=None):
    conn=http.client.HTTPConnection("127.0.0.1",server.server_address[1],timeout=5)
    headers={"Cookie":f"ncsid={token}"}; body=None
    if form is not None:
        body=urllib.parse.urlencode(form); headers["Content-Type"]="application/x-www-form-urlencoded"
    conn.request(method,path,body=body,headers=headers); r=conn.getresponse(); data=r.read(); status=r.status; hdr=dict(r.getheaders())
    conn.close(); return status,hdr,data


def test_ni4_schema_and_warning_event_creates_alert(tmp_path):
    m=Manager(str(tmp_path/"home"))
    tables={r["name"] for r in m.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"operational_alerts","maintenance_windows","notification_deliveries","report_schedules","report_runs"} <= tables
    info=m.events.record(source_type="syslog",device="sw1",event_type="INFO_TEST",severity="INFO",message="info",now=100)
    assert info.get("alert_id") is None
    warn=m.events.record(source_type="snmp_trap",device="sw1",event_type="AUTH_FAILURE",severity="WARNING",message="auth",now=101)
    alerts=m.alert_lifecycle.list(); assert len(alerts)==1 and alerts[0]["event_id"]==warn["id"] and warn["alert_id"]==alerts[0]["id"]
    m.db.close()


def test_maintenance_suppresses_alert_but_preserves_event(tmp_path):
    m=Manager(str(tmp_path/"home")); m.inv.upsert(name="sw1",host="10.0.0.1",platform="generic")
    mw=m.alert_lifecycle.add_maintenance("change","ops",device="sw1",minutes=60,now=100)
    ev=m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down",now=110)
    assert m.alert_lifecycle.list()==[] and ev["maintenance_window_id"]==mw["id"] and ev.get("alert_id") is None
    assert m.db.conn.execute("SELECT COUNT(*) AS n FROM operational_events").fetchone()["n"]==1
    m.db.close()


def test_ack_resolve_and_dedup_touch_same_alert(tmp_path):
    m=Manager(str(tmp_path/"home"))
    a=m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down",now=100)
    b=m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down",now=110)
    alert=m.alert_lifecycle.list()[0]; assert a["id"]==b["id"] and alert["event_count"]==2
    ack=m.alert_lifecycle.acknowledge(alert["id"],"ops","triage",now=120); assert ack["state"]=="ACKNOWLEDGED" and ack["acknowledged_by"]=="ops"
    res=m.alert_lifecycle.resolve(alert["id"],"ops","fixed",now=130); assert res["state"]=="RESOLVED" and res["resolution_note"]=="fixed"
    with pytest.raises(ValueError):
        m.alert_lifecycle.acknowledge(alert["id"],"ops",now=140)
    acts=[r["action"] for r in m.db.recent_audit(20)]; assert "operational_alert_ack" in acts and "operational_alert_resolve" in acts
    m.db.close()


def test_notification_retry_backoff_is_bounded(tmp_path, monkeypatch):
    m=Manager(str(tmp_path/"home")); m.settings.update({"operational_notifications_enabled":True,"operational_notification_max_attempts":3,"operational_notification_backoff_base_seconds":10,"operational_notification_backoff_max_seconds":25})
    monkeypatch.setattr(oa.mailer,"resolve_auth",lambda manager:(None,None))
    calls=[]
    monkeypatch.setattr(oa.mailer,"send_mail",lambda *a,**k:(calls.append(1) and False,"smtp down"))
    m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down",now=100)
    first=m.alert_lifecycle.process_notifications(now=100)[0]
    assert first["state"]=="RETRY" and first["attempts"]==1 and first["next_attempt_ts"]==110
    second=m.alert_lifecycle.process_notifications(now=110)[0]
    assert second["state"]=="RETRY" and second["attempts"]==2 and second["next_attempt_ts"]==130
    third=m.alert_lifecycle.process_notifications(now=130)[0]
    assert third["state"]=="FAILED" and third["attempts"]==3 and len(calls)==3
    m.db.close()


def test_scheduled_report_run_is_durable_and_summary_is_bounded(tmp_path):
    m=Manager(str(tmp_path/"home"))
    m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down",now=1000)
    sched=m.alert_lifecycle.add_report_schedule("daily","ops",interval_seconds=300,lookback_hours=1,first_run_ts=1100,now=1000)
    runs=m.alert_lifecycle.run_due_reports(now=1100)
    assert len(runs)==1 and runs[0]["schedule_id"]==sched["id"] and runs[0]["status"]=="COMPLETE"
    assert runs[0]["summary"]["events"] and runs[0]["summary"]["alerts"]
    updated=m.alert_lifecycle.report_schedules()[0]; assert updated["next_run_ts"]==1400
    m.db.close()


def test_cli_scopes_and_api_lifecycle(tmp_path):
    args=build_parser().parse_args(["alerts","maintenance-add","change","--device","sw1","--minutes","30","--json"])
    assert args.action=="maintenance-add" and args.minutes==30
    from netconfig import apitokens
    assert {"alerts:read","alerts:write","reports:read","reports:write"} <= apitokens.VALID_SCOPES
    m=Manager(str(tmp_path/"home")); m.inv.upsert(name="sw1",host="10.0.0.1",platform="generic")
    m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down")
    aid=m.alert_lifecycle.list()[0]["id"]
    _,raw=ApiTokens(m.db.conn).create("ops",["alerts:read","alerts:write","reports:read","reports:write"],role="operator")
    server,t=_start_api(m)
    try:
        st,p=_api_request(server,raw,"GET","/api/v1/operational-alerts"); assert st==200 and p["alerts"][0]["id"]==aid
        st,p=_api_request(server,raw,"POST",f"/api/v1/operational-alerts/{aid}/ack",{"note":"triage"}); assert st==200 and p["state"]=="ACKNOWLEDGED"
        st,p=_api_request(server,raw,"POST","/api/v1/maintenance-windows",{"name":"change","device":"sw1","minutes":"15"}); assert st==201 and p["device"]=="sw1"
        st,p=_api_request(server,raw,"POST","/api/v1/report-schedules",{"name":"hourly","interval_seconds":"300","lookback_hours":"1"}); assert st==201
        st,p=_api_request(server,raw,"GET","/api/v1/operational-reports"); assert st==200 and p["schedules"]
    finally:
        server.shutdown(); server.server_close(); t.join(timeout=5); m.db.close()


def test_viewer_web_is_read_only_and_operator_can_ack(tmp_path):
    m=Manager(str(tmp_path/"home")); m.events.record(source_type="snmp_trap",device="sw1",event_type="LINK_DOWN",severity="MAJOR",message="down")
    aid=m.alert_lifecycle.list()[0]["id"]
    server,t,token,csrf=_start_web(m,"viewer")
    try:
        st,_h,data=_web_request(server,token,"GET","/op-alerts"); text=data.decode(); assert st==200 and "Operational alerts" in text and "Acknowledge" not in text
        st,_h,_d=_web_request(server,token,"POST","/op-alert-action",{"csrf":csrf,"id":str(aid),"action":"ack"}); assert st==403 and m.alert_lifecycle.get(aid)["state"]=="OPEN"
    finally:
        server.shutdown(); server.server_close(); t.join(timeout=5); web._SESSIONS.clear()
    server,t,token,csrf=_start_web(m,"operator")
    try:
        st,h,_d=_web_request(server,token,"POST","/op-alert-action",{"csrf":csrf,"id":str(aid),"action":"ack"}); assert st==303 and h["Location"]=="/op-alerts" and m.alert_lifecycle.get(aid)["state"]=="ACKNOWLEDGED"
    finally:
        server.shutdown(); server.server_close(); t.join(timeout=5); web._SESSIONS.clear(); m.db.close()


def test_default_settings_keep_scheduler_and_notifications_opt_in(tmp_path):
    from netconfig import config
    assert config.DEFAULT_SETTINGS["operational_lifecycle_interval"]==0
    assert config.DEFAULT_SETTINGS["operational_notifications_enabled"] is False
    assert config.DEFAULT_SETTINGS["operational_alert_min_severity"]=="WARNING"
