import http.client
import json
import threading
import time

import pytest

from netconfig import snmp
from netconfig import snmp_trap
from netconfig.apitokens import ApiTokens
from netconfig.db import Database
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def _vb(oid, value_tlv):
    return snmp.enc_seq(snmp.enc_oid(oid), value_tlv)


def _trap(community="very-secret-community", trap_oid=".1.3.6.1.6.3.1.1.5.3", ifindex=1):
    varbinds = snmp.enc_seq(
        _vb(".1.3.6.1.2.1.1.3.0", snmp._tlv(snmp.TIMETICKS, (12345).to_bytes(2, "big"))),
        _vb(snmp_trap.TRAP_OID_VAR, snmp.enc_oid(trap_oid)),
        _vb(snmp_trap.IFINDEX, snmp.enc_int(ifindex)),
    )
    pdu = snmp._tlv(snmp_trap.TRAP_V2, snmp.enc_int(7) + snmp.enc_int(0) + snmp.enc_int(0) + varbinds)
    return snmp.enc_seq(snmp.enc_int(1), snmp.enc_octet(community), pdu)


def test_v2c_trap_parses_without_exposing_community():
    parsed = snmp_trap.parse_packet(_trap())
    assert parsed["version"] == "v2c"
    assert parsed["trap_oid"] == ".1.3.6.1.6.3.1.1.5.3"
    assert parsed["varbinds"][snmp_trap.IFINDEX] == 1
    assert "community" not in parsed
    assert "very-secret-community" not in json.dumps(parsed)


def test_v3_and_inform_fail_closed():
    fake_v3 = snmp.enc_seq(snmp.enc_int(3), snmp.enc_octet("x"), snmp.enc_null())
    with pytest.raises(snmp_trap.TrapError, match="SNMPv3"):
        snmp_trap.parse_packet(fake_v3)
    inform = snmp.enc_seq(snmp.enc_int(1), snmp.enc_octet("public"),
        snmp._tlv(snmp_trap.INFORM, snmp.enc_int(1) + snmp.enc_int(0) + snmp.enc_int(0) + snmp.enc_seq()))
    with pytest.raises(snmp_trap.TrapError, match="INFORM"):
        snmp_trap.parse_packet(inform)


def test_event_dedup_and_schema_are_durable(tmp_path):
    m = Manager(str(tmp_path / "home"))
    tables = {r["name"] for r in m.db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"operational_events", "operational_suppressions"} <= tables
    a = m.events.record(source_type="snmp_trap", source="10.0.0.1", device="sw1", event_type="LINK_DOWN", message="down", now=100)
    b = m.events.record(source_type="snmp_trap", source="10.0.0.1", device="sw1", event_type="LINK_DOWN", message="down", now=110)
    assert a["id"] == b["id"] and b["event_count"] == 2 and b["deduplicated"]
    m.db.close()


def test_linkdown_creates_downstream_suppression_and_linkup_clears(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="core", host="10.0.0.1", platform="generic", snmp_version="v2c")
    m.inv.upsert(name="access", host="10.0.0.2", platform="generic", snmp_version="v2c")
    m.db.set_topology_interfaces("core", [{"ifindex":"1","name":"Gi1","descr":"Gi1"}])
    m.db.set_neighbors("core", [{"protocol":"lldp","local_port":"Gi1","neighbor_device":"access","sys_name":"access","managed_neighbor":True,"resolution_state":"RESOLVED","port_id":"Gi24"}])
    monkeypatch.setattr(m, "snmp_poll", lambda name: {"ok": True})
    c = snmp_trap.Collector(m)
    base = time.time()
    c._handle(base, "10.0.0.1", 40000, _trap(trap_oid=".1.3.6.1.6.3.1.1.5.3"))
    sups = m.events.suppressions(True)
    assert len(sups) == 1 and sups[0]["target_device"] == "access" and sups[0]["root_port"] == "Gi1"
    child = m.events.record(source_type="syslog", source="10.0.0.2", device="access", event_type="SYSLOG", message="child alarm", now=base+1)
    assert child["suppressed"] == 1
    c._handle(base+2, "10.0.0.1", 40000, _trap(trap_oid=".1.3.6.1.6.3.1.1.5.4"))
    assert m.events.suppressions(True) == []
    m.db.close()


def test_targeted_repoll_is_debounced(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="sw1", host="192.0.2.1", platform="generic", snmp_version="v2c")
    calls=[]
    monkeypatch.setattr(m, "snmp_poll", lambda name: calls.append(name) or {"ok":True})
    m.settings["snmp_trap_repoll_debounce_seconds"] = 30
    c=snmp_trap.Collector(m)
    c._handle(100,"192.0.2.1",40000,_trap(trap_oid=".1.3.6.1.6.3.1.1.5.1"))
    c._handle(110,"192.0.2.1",40000,_trap(trap_oid=".1.3.6.1.6.3.1.1.5.2"))
    c._handle(131,"192.0.2.1",40000,_trap(trap_oid=".1.3.6.1.6.3.1.1.5.2"))
    assert calls == ["sw1","sw1"] and c.repolls == 2
    m.db.close()


def test_rejected_trap_does_not_store_raw_or_secret(tmp_path):
    m=Manager(str(tmp_path / "home")); c=snmp_trap.Collector(m)
    c._handle(100,"203.0.113.5",1234,b"not-snmp-secret-community")
    assert c.rejected == 1 and m.events.list() == []
    raw = m.db.conn.execute("SELECT detail FROM audit WHERE action='trap_rejected'").fetchone()[0]
    assert "secret-community" not in raw
    m.db.close()


def test_syslog_is_normalized_into_operational_stream(tmp_path):
    from netconfig import syslog_receiver
    m=Manager(str(tmp_path / "home"))
    m.inv.upsert(name="sw1", host="10.0.0.1", platform="generic")
    c=syslog_receiver.Collector(m)
    c._handle(100,"10.0.0.1","%LINK-3-UPDOWN: Interface Gi1 changed state")
    rows=m.events.list()
    assert rows[0]["source_type"] == "syslog" and rows[0]["device"] == "sw1"
    m.db.close()


def test_events_cli_scope_and_api(tmp_path):
    from netconfig.cli import build_parser
    args=build_parser().parse_args(["events","--device","sw1","--json"])
    assert args.device == "sw1" and args.json
    assert "events:read" in __import__("netconfig.apitokens", fromlist=["VALID_SCOPES"]).VALID_SCOPES
    m=Manager(str(tmp_path / "home"))
    m.events.record(source_type="snmp_trap",source="10.0.0.1",device="sw1",event_type="COLD_START",message="cold")
    _,raw=ApiTokens(m.db.conn).create("event-reader",["events:read"],role="viewer")
    Console.manager=m; Console.tls_enabled=False
    server=_Server(("127.0.0.1",0),Console); t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
    conn=http.client.HTTPConnection("127.0.0.1",server.server_address[1],timeout=5)
    try:
        conn.request("GET","/api/v1/events",headers={"Authorization":"Bearer "+raw})
        r=conn.getresponse(); payload=json.loads(r.read())
        assert r.status==200 and payload["events"][0]["event_type"]=="COLD_START"
    finally:
        conn.close(); server.shutdown(); server.server_close(); t.join(timeout=5); m.db.close()
