import hashlib
import http.client
import json
import threading
from types import SimpleNamespace

import netconfig.cli as cli
import netconfig.web as web
from netconfig import snmp, topology
from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def _device(manager, name, host):
    manager.inv.upsert(
        name=name, host=host, port=22, platform="generic", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=[], notes="", snmp_version="", snmp_ref=None,
    )


def test_aes256_uses_blumenthal_extension_compatible_with_netsnmp():
    engine_id = bytes.fromhex("8000304404464731303146544b3230303039313038")
    params = snmp.V3Params("fortisnmp", "sha1", "auth-passphrase", "aes256", "priv-passphrase")
    _ctor, _tag_len, _auth_key, priv_key = snmp._localized_for(params, engine_id)
    base = snmp.password_to_key("priv-passphrase", engine_id, hashlib.sha1)
    expected = (base + hashlib.sha1(base).digest())[:32]
    assert len(priv_key) == 32
    assert priv_key == expected
    # Regression guard: generic AES-256 must no longer use the Cisco/Reeder path.
    assert priv_key != snmp._extend_priv_key_reeder(base, engine_id, hashlib.sha1, 32)
    assert snmp.net_snmp_priv_name("aes256") == "AES-256"


def test_cisco_reeder_aes256_remains_explicit_compatibility_variant():
    engine_id = bytes.fromhex("800000090300001122334455")
    params = snmp.V3Params("user", "sha1", "auth-passphrase", "aes256c", "priv-passphrase")
    _ctor, _tag_len, _auth_key, priv_key = snmp._localized_for(params, engine_id)
    base = snmp.password_to_key("priv-passphrase", engine_id, hashlib.sha1)
    assert priv_key == snmp._extend_priv_key_reeder(base, engine_id, hashlib.sha1, 32)
    assert snmp.net_snmp_priv_name("aes256c") == "AES-256-C"


def test_fdb_graph_inference_keeps_inventory_nodes_and_marks_path_inferred():
    inventory = [
        {"name": "switch-1", "host": "192.0.2.10"},
        {"name": "Forti101F-EH", "host": "192.168.0.207"},
        {"name": "isolated", "host": "192.0.2.30"},
    ]
    interfaces = [
        {"device": "Forti101F-EH", "ifindex": "3", "ifname": "port3", "ifdescr": "port3",
         "phys_address": "00:11:22:33:44:55"},
    ]
    fdb = [
        {"device": "switch-1", "mac": "0011.2233.4455", "ifdescr": "1/1/48",
         "ifindex": "48", "bridge_port": "48", "vlan_id": "10", "source": "BRIDGE-MIB"},
    ]
    graph = topology.build_graph([], inventory, [], interfaces, fdb)
    assert {n["device"] for n in graph["nodes"]} == {"switch-1", "Forti101F-EH", "isolated"}
    edge = graph["edges"][0]
    assert edge["from"] == "switch-1" and edge["to"] == "Forti101F-EH"
    assert edge["local_port"] == "1/1/48" and edge["remote_port"] == "port3"
    assert edge["evidence_kind"] == "INFERRED"
    assert edge["direct_adjacency"] is False
    assert graph["summary"] == {
        "managed_nodes": 3, "observed_edges": 0, "inferred_edges": 1, "unknown_nodes": 1,
    }


def test_observed_neighbor_suppresses_duplicate_fdb_inference_and_remains_traversable():
    inventory = [{"name": "switch-1"}, {"name": "fw-1"}]
    interfaces = [{"device": "fw-1", "ifindex": "1", "ifname": "port1", "phys_address": "00:aa:bb:cc:dd:ee"}]
    fdb = [{"device": "switch-1", "mac": "00:aa:bb:cc:dd:ee", "ifdescr": "uplink", "ifindex": "9"}]
    neighbors = [{
        "device": "switch-1", "neighbor_device": "fw-1", "managed_neighbor": 1,
        "resolution_state": "RESOLVED", "protocol": "lldp", "local_port": "uplink", "port_id": "port1",
    }]
    graph = topology.build_graph(neighbors, inventory, [], interfaces, fdb)
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["evidence_kind"] == "OBSERVED"
    impact = topology.downstream_impact(neighbors, "switch-1")
    assert impact["device_count"] == 1 and impact["devices"][0]["device"] == "fw-1"


def test_manager_topology_graph_is_read_only_persisted_evidence(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    try:
        _device(manager, "switch-1", "192.0.2.10")
        _device(manager, "Forti101F-EH", "192.168.0.207")
        manager.db.set_topology_interfaces("Forti101F-EH", [{
            "ifindex": "3", "name": "port3", "descr": "port3", "alias": "", "phys": "00:11:22:33:44:55",
        }])
        manager.db.set_vlan_fdb("switch-1", [{
            "vlan_id": "10", "fdb_id": "", "mac": "00:11:22:33:44:55", "bridge_port": "48",
            "ifindex": "48", "ifdescr": "1/1/48", "status": "learned", "source": "BRIDGE-MIB",
        }])
        graph = manager.topology_graph()
        assert len(graph["nodes"]) == 2
        assert graph["summary"]["inferred_edges"] == 1
        assert graph["edges"][0]["evidence_kind"] == "INFERRED"
    finally:
        manager.close()


def test_topology_cli_discover_unlocks_vault_in_same_process(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(cli, "_master", lambda manager, required=True: called.append(manager))

    class Inv:
        def all(self):
            return [{"name": "fw", "snmp_version": "v3"}]

    class DB:
        def get_neighbors(self, device=None):
            return []

    manager = SimpleNamespace(inv=Inv(), db=DB(), discover_neighbors=lambda name: [])
    args = SimpleNamespace(discover=True, device="fw", identities=False, impact=None,
                           json=True, port=None, max_depth=16)
    cli.cmd_topology(manager, args)
    assert called == [manager]
    assert "fw: 0 neighbour(s)" in capsys.readouterr().out


def _start_console(manager, role="viewer"):
    web._SESSIONS.clear()
    sid = "topology-hotfix-session"
    web._SESSIONS[sid] = {"username": "tester", "role": role, "csrf": "csrf", "created": 1.0}
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, sid


def test_topology_web_is_interactive_and_shows_inventory_without_lldp(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "switch-1", "192.0.2.10")
    _device(manager, "Forti101F-EH", "192.168.0.207")
    manager.db.set_topology_interfaces("Forti101F-EH", [{
        "ifindex": "3", "name": "port3", "descr": "port3", "alias": "", "phys": "00:11:22:33:44:55",
    }])
    manager.db.set_vlan_fdb("switch-1", [{
        "vlan_id": "10", "fdb_id": "", "mac": "00:11:22:33:44:55", "bridge_port": "48",
        "ifindex": "48", "ifdescr": "1/1/48", "status": "learned", "source": "BRIDGE-MIB",
    }])
    server, thread, sid = _start_console(manager)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/topology", headers={"Cookie": f"ncsid={sid}"})
        response = conn.getresponse(); text = response.read().decode(); conn.close()
        assert response.status == 200
        assert 'id="topology-canvas"' in text
        assert 'id="topology-reset"' in text
        assert "netconfig-topology-layout-v1" in text
        assert "pointerdown" in text and "wheel" in text
        assert "Forti101F-EH" in text and "switch-1" in text
        assert "INFERRED" in text and "FDB MAC" in text
        assert "Layout is stored only in this browser" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_topology_graph_api_returns_nodes_and_inference(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "switch-1", "192.0.2.10")
    _device(manager, "fw-1", "192.0.2.20")
    manager.db.set_topology_interfaces("fw-1", [{"ifindex": "1", "name": "port1", "phys": "00:aa:bb:cc:dd:ee"}])
    manager.db.set_vlan_fdb("switch-1", [{"mac": "00:aa:bb:cc:dd:ee", "ifdescr": "uplink", "ifindex": "9"}])
    _, raw = ApiTokens(manager.db.conn).create("topology-reader", ["topology:read"], role="viewer")
    Console.manager = manager; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/api/v1/topology/graph", headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); payload = json.loads(response.read()); conn.close()
        assert response.status == 200
        assert len(payload["nodes"]) == 2
        assert payload["summary"]["inferred_edges"] == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()
