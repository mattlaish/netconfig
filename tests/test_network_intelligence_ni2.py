import http.client
import json
import threading

from netconfig import topology
from netconfig.apitokens import ApiTokens
from netconfig.db import Database
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def test_parse_device_identity_prefers_explicit_chassis_class():
    local = [
        (topology.LLDP_LOCAL_IDENTITY["chassis_id_subtype"], 4),
        (topology.LLDP_LOCAL_IDENTITY["chassis_id"], bytes.fromhex("001122334455")),
        (topology.LLDP_LOCAL_IDENTITY["sys_name"], b"dist-1"),
        (topology.LLDP_LOCAL_IDENTITY["sys_cap_enabled"], b"\x00\x14"),
    ]
    e = topology.ENTITY_COLUMNS
    entities = {
        "1": {e["class"]: 9, e["serial"]: b"module-serial", e["name"]: b"linecard"},
        "2": {e["class"]: 3, e["serial"]: b"CHASSIS123", e["name"]: b"dist-1-chassis", e["model"]: b"C9300"},
    }
    row = topology.parse_device_identity(local, entities, {"sysname": "fallback"})
    assert row["sys_name"] == "dist-1"
    assert row["chassis_id_subtype"] == "macAddress"
    assert row["chassis_id"] == "00:11:22:33:44:55"
    assert row["chassis_mac"] == "00:11:22:33:44:55"
    assert row["chassis_serial"] == "CHASSIS123"
    assert row["chassis_model"] == "C9300"


def test_lldp_hex_mac_is_normalized():
    b = topology.LLDP_REM_BASE
    rows = topology.parse_lldp_walk([
        (b + ".4.1.7.1", "4"),
        (b + ".5.1.7.1", "0x001122334455"),
        (b + ".9.1.7.1", "access-1"),
    ])
    assert rows[0]["chassis_id"] == "00:11:22:33:44:55"


def test_identity_resolution_is_unique_and_conflicts_fail_closed():
    inventory = [
        {"name": "sw1", "host": "10.0.0.1"},
        {"name": "sw2", "host": "10.0.0.2"},
    ]
    identities = [
        {"device": "sw1", "sys_name": "edge-a", "chassis_mac": "00:11:22:33:44:55"},
        {"device": "sw2", "sys_name": "edge-b", "chassis_mac": "00:aa:bb:cc:dd:ee"},
    ]
    resolved = topology.analyze([{"sys_name": "edge-a", "chassis_id": "00:11:22:33:44:55"}], inventory, identities)[0]
    assert resolved["resolution_state"] == "RESOLVED" and resolved["neighbor_device"] == "sw1"
    conflict = topology.analyze([{"sys_name": "edge-a", "chassis_id": "00:aa:bb:cc:dd:ee"}], inventory, identities)[0]
    assert conflict["resolution_state"] == "AMBIGUOUS"
    assert not conflict["managed_neighbor"] and conflict["neighbor_device"] == ""


def test_downstream_impact_is_bounded_cycle_safe_and_port_scoped():
    rows = [
        {"device": "core", "local_port": "Gi1", "neighbor_device": "dist", "managed_neighbor": 1, "resolution_state": "RESOLVED", "protocol": "lldp", "port_id": "Gi48"},
        {"device": "core", "local_port": "Gi2", "neighbor_device": "other", "managed_neighbor": 1, "resolution_state": "RESOLVED", "protocol": "lldp", "port_id": "Gi48"},
        {"device": "dist", "local_port": "Gi10", "neighbor_device": "access", "managed_neighbor": 1, "resolution_state": "RESOLVED", "protocol": "lldp", "port_id": "Gi24"},
        {"device": "access", "local_port": "Gi24", "neighbor_device": "core", "managed_neighbor": 1, "resolution_state": "RESOLVED", "protocol": "lldp", "port_id": "Gi1"},
        {"device": "dist", "local_port": "Gi11", "neighbor_device": "ambig", "managed_neighbor": 0, "resolution_state": "AMBIGUOUS", "protocol": "lldp"},
    ]
    impact = topology.downstream_impact(rows, "core", root_port="Gi1", max_depth=8)
    assert [x["device"] for x in impact["devices"]] == ["dist", "access"]
    assert impact["device_count"] == 2
    assert all(x["device"] != "other" for x in impact["devices"])
    assert impact["scope"] == "observed_managed_l2_adjacency"


def test_ni2_schema_and_identity_view_are_additive(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    tables = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"topology_device_identity", "topology_interface_identity"} <= tables
    db.set_topology_device_identity("sw1", {"sys_name": "sw1.example", "chassis_serial": "SER1"})
    db.set_topology_interfaces("sw1", [{"ifindex": "7", "name": "Gi1/0/7", "descr": "GigabitEthernet1/0/7", "alias": "users", "phys": "00:11:22:33:44:77"}])
    view = topology.identity_view([{"name": "sw1", "host": "10.0.0.1"}], db.get_topology_device_identities(), db.get_topology_interfaces())
    assert view[0]["chassis_serial"] == "SER1"
    assert view[0]["interfaces"][0]["ifname"] == "Gi1/0/7"
    db.close()


def test_manager_refresh_collects_bounded_identity_and_interfaces(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    manager.inv.upsert(name="sw1", host="192.0.2.1", platform="generic", snmp_version="v2c")
    e = topology.ENTITY_COLUMNS
    monkeypatch.setattr("netconfig.manager._snmp.get_oids", lambda *a, **k: [
        (topology.LLDP_LOCAL_IDENTITY["chassis_id_subtype"], 4),
        (topology.LLDP_LOCAL_IDENTITY["chassis_id"], bytes.fromhex("001122334455")),
        (topology.LLDP_LOCAL_IDENTITY["sys_name"], b"sw1.example"),
    ])
    monkeypatch.setattr("netconfig.manager._snmp.walk_table", lambda *a, **k: {
        "10": {e["class"]: 3, e["serial"]: b"SERIAL-1", e["model"]: b"MODEL-1"}
    })
    dev = manager.inv.get("sw1")
    manager._refresh_topology_identity(dev, "v2c", "public", None, 161,
        facts={"sysname": "fallback"}, interfaces=[{"ifindex": "1", "name": "Gi1", "descr": "Gi1", "alias": "uplink", "phys": "00:11:22:33:44:66"}])
    ident = manager.db.get_topology_device_identities("sw1")[0]
    assert ident["chassis_serial"] == "SERIAL-1" and ident["chassis_mac"] == "00:11:22:33:44:55"
    assert manager.db.get_topology_interfaces("sw1")[0]["ifname"] == "Gi1"
    manager.db.close()


def test_topology_cli_parser_supports_identity_and_impact():
    from netconfig.cli import build_parser
    args = build_parser().parse_args(["topology", "--identities", "--json"])
    assert args.identities and args.json
    args = build_parser().parse_args(["topology", "--impact", "core", "--port", "Gi1", "--max-depth", "4"])
    assert args.impact == "core" and args.port == "Gi1" and args.max_depth == 4


def test_topology_identity_and_impact_api(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    manager.inv.upsert(name="core", host="10.0.0.1", platform="generic")
    manager.inv.upsert(name="access", host="10.0.0.2", platform="generic")
    manager.db.set_topology_device_identity("core", {"sys_name": "core.example", "chassis_serial": "C1"})
    manager.db.set_neighbors("core", [{
        "protocol": "lldp", "local_port": "Gi1", "local_port_num": "7", "neighbor_device": "access",
        "sys_name": "access", "managed_neighbor": True, "resolution_state": "RESOLVED", "port_id": "Gi24",
    }])
    _, raw = ApiTokens(manager.db.conn).create("topology-reader", ["topology:read"], role="viewer")
    Console.manager = manager; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        headers = {"Authorization": "Bearer " + raw}
        conn.request("GET", "/api/v1/topology/identities", headers=headers)
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200
        core = next(x for x in payload if x["device"] == "core")
        assert core["chassis_serial"] == "C1"
        conn.request("GET", "/api/v1/topology/impact/core", headers=headers)
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200 and payload["devices"][0]["device"] == "access"
    finally:
        conn.close(); server.shutdown(); server.server_close(); thread.join(timeout=5); manager.db.close()
