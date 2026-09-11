import http.client
import json
import threading

from netconfig import snmp
from netconfig.apitokens import ApiTokens, VALID_SCOPES
from netconfig.db import Database
from netconfig.manager import Manager
from netconfig.network_intelligence import correlate
from netconfig.web import Console, _Server


def test_poll_ip_neighbors_modern_ipv4_ipv6(monkeypatch):
    addr_type = ".1.3.6.1.2.1.4.35.1.2"
    net = ".1.3.6.1.2.1.4.35.1.3"
    phys = ".1.3.6.1.2.1.4.35.1.4"
    ntype = ".1.3.6.1.2.1.4.35.1.6"
    state = ".1.3.6.1.2.1.4.35.1.7"

    def fake_walk(host, columns, **kwargs):
        if columns and columns[0] == addr_type:
            return {
                "7.1.192.0.2.10": {
                    addr_type: 1, net: b"\xc0\x00\x02\x0a", phys: b"\x00\x11\x22\x33\x44\x55",
                    ntype: 3, state: 1,
                },
                "8.2.32.1.13.184.0.0.0.0.0.0.0.0.0.0.0.9": {
                    addr_type: 2, net: bytes.fromhex("20010db8000000000000000000000009"),
                    phys: b"\x00\xaa\xbb\xcc\xdd\xee", ntype: 4, state: 2,
                },
            }
        return {}

    monkeypatch.setattr(snmp, "walk_table", fake_walk)
    rows = snmp.poll_ip_neighbors("192.0.2.1", ifdescr={"7": "Vlan20", "8": "Vlan30"})
    assert rows[0]["ip"] == "192.0.2.10" and rows[0]["address_family"] == "ipv4"
    assert rows[0]["state"] == "reachable" and rows[0]["ifdescr"] == "Vlan20"
    assert rows[1]["ip"] == "2001:db8::9" and rows[1]["address_family"] == "ipv6"
    assert rows[1]["neighbor_type"] == "static"


def test_poll_vlan_fdb_maps_qbridge_fdb_id_to_vlan_and_ifindex(monkeypatch):
    fdb_port = ".1.3.6.1.2.1.17.7.1.2.2.1.2"
    fdb_status = ".1.3.6.1.2.1.17.7.1.2.2.1.3"
    vlan_fdb = ".1.3.6.1.2.1.17.7.1.4.2.1.3"
    bp_ifindex = ".1.3.6.1.2.1.17.1.4.1.2"

    def fake_walk(host, columns, **kwargs):
        if columns and columns[0] == fdb_port:
            return {"100.0.17.34.51.68.85": {fdb_port: 5, fdb_status: 3}}
        if columns == [vlan_fdb]:
            return {"0.20": {vlan_fdb: 100}}
        if columns == [bp_ifindex]:
            return {"5": {bp_ifindex: 7}}
        return {}

    monkeypatch.setattr(snmp, "walk_table", fake_walk)
    rows = snmp.poll_vlan_fdb("192.0.2.1", ifdescr={"7": "Gi1/0/7"})
    assert rows == [{
        "vlan_id": "20", "fdb_id": "100", "mac": "00:11:22:33:44:55",
        "bridge_port": "5", "ifindex": "7", "ifdescr": "Gi1/0/7",
        "status": "learned", "source": "Q-BRIDGE-MIB",
    }]


def test_poll_vlan_fdb_does_not_guess_shared_fdb_vlan(monkeypatch):
    fdb_port = ".1.3.6.1.2.1.17.7.1.2.2.1.2"
    fdb_status = ".1.3.6.1.2.1.17.7.1.2.2.1.3"
    vlan_fdb = ".1.3.6.1.2.1.17.7.1.4.2.1.3"
    bp_ifindex = ".1.3.6.1.2.1.17.1.4.1.2"

    def fake_walk(host, columns, **kwargs):
        if columns and columns[0] == fdb_port:
            return {"100.0.17.34.51.68.85": {fdb_port: 5, fdb_status: 3}}
        if columns == [vlan_fdb]:
            return {"0.20": {vlan_fdb: 100}, "0.30": {vlan_fdb: 100}}
        if columns == [bp_ifindex]:
            return {"5": {bp_ifindex: 7}}
        return {}

    monkeypatch.setattr(snmp, "walk_table", fake_walk)
    row = snmp.poll_vlan_fdb("192.0.2.1")[0]
    assert row["fdb_id"] == "100" and row["vlan_id"] == ""


def test_correlation_prefers_single_non_neighbor_facing_access_port(tmp_path):
    db = Database(str(tmp_path / "ni.db"))
    mac = "00:11:22:33:44:55"
    db.set_ip_neighbors("core", [{
        "ip": "192.0.2.10", "address_family": "ipv4", "mac": mac,
        "ifindex": "20", "ifdescr": "Vlan20", "source": "ipNetToPhysicalTable",
    }])
    db.set_vlan_fdb("dist", [{
        "vlan_id": "20", "fdb_id": "20", "mac": mac, "bridge_port": "48",
        "ifindex": "48", "ifdescr": "Gi1/0/48", "source": "Q-BRIDGE-MIB",
    }])
    db.set_neighbors("dist", [{
        "protocol": "lldp", "local_port": "Gi1/0/48", "local_port_num": "48",
        "neighbor_device": "access", "sys_name": "access", "managed_neighbor": True,
    }])
    db.set_vlan_fdb("access", [{
        "vlan_id": "20", "fdb_id": "20", "mac": mac, "bridge_port": "5",
        "ifindex": "5", "ifdescr": "Gi1/0/5", "source": "Q-BRIDGE-MIB",
    }])
    rows = correlate(db, max_age=3600)
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "ATTACHED" and row["confidence"] == "HIGH"
    assert row["attachment"]["device"] == "access"
    assert row["attachment"]["vlan_id"] == "20"
    assert row["ipv4"] == ["192.0.2.10"]
    assert len(row["transit_observations"]) == 1
    assert row["transit_observations"][0]["downstream"][0]["neighbor"] == "access"
    db.close()


def test_correlation_keeps_multiple_direct_candidates_ambiguous(tmp_path):
    db = Database(str(tmp_path / "ni.db"))
    mac = "00:11:22:33:44:55"
    for dev, port in (("sw1", "5"), ("sw2", "7")):
        db.set_vlan_fdb(dev, [{
            "vlan_id": "20", "fdb_id": "20", "mac": mac, "bridge_port": port,
            "ifindex": port, "ifdescr": "Gi1/0/" + port, "source": "Q-BRIDGE-MIB",
        }])
    row = correlate(db, max_age=3600)[0]
    assert row["status"] == "AMBIGUOUS" and row["attachment"] is None
    assert len(row["candidates"]) == 2
    db.close()


def test_correlation_marks_old_only_observations_stale(tmp_path):
    db = Database(str(tmp_path / "ni.db"))
    db.set_vlan_fdb("sw1", [{
        "vlan_id": "20", "fdb_id": "20", "mac": "00:11:22:33:44:55",
        "bridge_port": "5", "ifindex": "5", "ifdescr": "Gi1/0/5", "source": "Q-BRIDGE-MIB",
    }])
    db.conn.execute("UPDATE vlan_fdb SET ts=1"); db.conn.commit()
    row = correlate(db, max_age=60, now=1000)[0]
    assert row["status"] == "STALE" and row["confidence"] == "NONE"
    db.close()


def test_network_intelligence_schema_is_additive(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    tables = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"ip_neighbors", "vlan_fdb"} <= tables
    db.close()


def test_endpoint_scope_cli_parser_and_api(tmp_path):
    assert "endpoint:read" in VALID_SCOPES
    from netconfig.cli import build_parser
    args = build_parser().parse_args(["endpoints", "--device", "sw1", "--json"])
    assert args.cmd == "endpoints" and args.device == "sw1" and args.json

    manager = Manager(str(tmp_path / "home"))
    manager.db.set_ip_neighbors("sw1", [{
        "ip": "192.0.2.10", "address_family": "ipv4", "mac": "00:11:22:33:44:55",
        "ifindex": "20", "ifdescr": "Vlan20", "source": "ipNetToPhysicalTable",
    }])
    manager.db.set_vlan_fdb("sw1", [{
        "vlan_id": "20", "fdb_id": "20", "mac": "00:11:22:33:44:55",
        "bridge_port": "5", "ifindex": "5", "ifdescr": "Gi1/0/5", "source": "Q-BRIDGE-MIB",
    }])
    _, raw = ApiTokens(manager.db.conn).create("reader", ["endpoint:read"], role="viewer")
    Console.manager = manager; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        conn.request("GET", "/api/v1/endpoints", headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200
        assert payload["summary"]["attached"] == 1
        assert payload["endpoints"][0]["attachment"]["vlan_id"] == "20"
    finally:
        conn.close(); server.shutdown(); server.server_close(); thread.join(timeout=5); manager.db.close()
