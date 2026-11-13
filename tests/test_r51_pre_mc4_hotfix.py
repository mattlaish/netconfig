import hashlib
import http.client
import json
import threading
from types import SimpleNamespace

import netconfig.cli as cli
import netconfig.web as web
from netconfig import snmp, topology
from netconfig.web_ui import _topology_canvas_edges, _topology_url, _topology_view_tabs
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


def test_reciprocal_lldp_rows_become_one_physical_edge_with_one_port_pair():
    inventory = [{"name": "core"}, {"name": "access"}]
    neighbors = [
        {
            "device": "core", "neighbor_device": "access", "managed_neighbor": 1,
            "resolution_state": "RESOLVED", "protocol": "lldp",
            "local_port": "Gi1/0/1", "port_id": "Gi1/0/48",
        },
        {
            "device": "access", "neighbor_device": "core", "managed_neighbor": 1,
            "resolution_state": "RESOLVED", "protocol": "lldp",
            "local_port": "Gi1/0/48", "port_id": "Gi1/0/1",
        },
    ]
    graph = topology.build_graph(neighbors, inventory)
    assert len(graph["physical_edges"]) == 1
    assert graph["reachability_edges"] == []
    edge = graph["physical_edges"][0]
    assert edge["from"] == "access" and edge["to"] == "core"
    assert edge["links"] == [{"from_port": "Gi1/0/48", "to_port": "Gi1/0/1"}]
    assert edge["link_count"] == 1


def test_reciprocal_next_hops_remain_two_evidence_rows_but_one_canvas_line():
    evidence = [
        {"kind": "NEXT_HOP", "from": "device:r1", "to": "device:r2",
         "vrf": "default", "next_hop": "10.1.1.5", "outgoing_interface": "Gi0/0/0",
         "route_count": 1},
        {"kind": "NEXT_HOP", "from": "device:r2", "to": "device:r1",
         "vrf": "default", "next_hop": "10.1.1.6", "outgoing_interface": "Gi0/0/0",
         "route_count": 1},
    ]
    canvas = _topology_canvas_edges(evidence)
    assert len(evidence) == 2 and len(canvas) == 1
    assert canvas[0]["route_count"] == 2
    assert canvas[0]["path_labels"] == [
        "r1→r2 via 10.1.1.5 (Gi0/0/0)",
        "r2→r1 via 10.1.1.6 (Gi0/0/0)",
    ]


def test_reciprocal_fdb_reachability_is_one_canvas_line():
    evidence = [
        {"evidence_kind": "INFERRED", "from": "sw1", "to": "sw2",
         "evidence_count": 3},
        {"evidence_kind": "INFERRED", "from": "sw2", "to": "sw1",
         "evidence_count": 4},
    ]
    canvas = _topology_canvas_edges(evidence)
    assert len(evidence) == 2 and len(canvas) == 1
    assert canvas[0]["evidence_count"] == 7


def test_shared_connected_subnet_replaces_redundant_next_hop_canvas_chord():
    evidence = [
        {"kind": "DIRECTLY_CONNECTED", "from": "device:r1", "to": "subnet:default:10.1.1.4/30"},
        {"kind": "DIRECTLY_CONNECTED", "from": "device:r2", "to": "subnet:default:10.1.1.4/30"},
        {"kind": "NEXT_HOP", "from": "device:r1", "to": "device:r2", "vrf": "default"},
        {"kind": "NEXT_HOP", "from": "device:r2", "to": "device:r1", "vrf": "default"},
    ]
    canvas = _topology_canvas_edges(evidence)
    assert len(evidence) == 4 and len(canvas) == 2
    assert {edge["kind"] for edge in canvas} == {"DIRECTLY_CONNECTED"}


def test_shared_connected_subnet_can_keep_directional_next_hop_canvas_line():
    evidence = [
        {"kind": "DIRECTLY_CONNECTED", "from": "device:r1", "to": "subnet:default:192.168.0.0/24"},
        {"kind": "DIRECTLY_CONNECTED", "from": "device:r2", "to": "subnet:default:192.168.0.0/24"},
        {"kind": "NEXT_HOP", "from": "device:r1", "to": "device:r2", "vrf": "default",
         "next_hop": "192.168.0.1", "outgoing_interface": "Gi0/1", "route_count": 1},
    ]
    canvas = _topology_canvas_edges(evidence, show_shared_nexthops=True)
    assert len(canvas) == 3
    route = next(edge for edge in canvas if edge["kind"] == "NEXT_HOP")
    assert route["path_labels"] == ["r1→r2 via 192.168.0.1 (Gi0/1)"]


def test_shared_next_hop_option_is_preserved_by_topology_links():
    url = _topology_url(
        "combined", show_inferred=True, include_stale=True,
        show_shared_nexthops=True)
    assert "show_shared_nexthops=1" in url
    tabs = _topology_view_tabs(
        "l3", show_shared_nexthops=True, include_stale=True)
    assert tabs.count("show_shared_nexthops=1") == 3


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


def test_topology_web_defaults_to_observed_and_requires_opt_in_for_fdb_paths(tmp_path):
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
        assert "netconfig-topology-layout-v2-physical" in text
        assert "pointerdown" in text and "wheel" in text
        canvas = text.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]
        assert 'topology-edge inferred' not in canvas
        assert 'data-node="Forti101F-EH"' not in canvas
        assert 'data-node="switch-1"' not in canvas
        assert "Show inferred FDB paths" in text
        assert "Inferred FDB/MAC reachability evidence" in text and "FDB MAC" in text
        assert "Layout is stored only in this browser" in text

        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/topology?view=physical&show_inferred=1",
                     headers={"Cookie": f"ncsid={sid}"})
        response = conn.getresponse(); inferred = response.read().decode(); conn.close()
        inferred_canvas = inferred.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]
        assert response.status == 200
        assert 'topology-edge inferred' in inferred_canvas
        assert "FDB reachability" in inferred_canvas
        assert 'data-node="Forti101F-EH"' in inferred_canvas
        assert 'data-node="switch-1"' in inferred_canvas
        assert "INFERRED FDB/MAC reachability (not adjacency)" in inferred

        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/topology?view=combined", headers={"Cookie": f"ncsid={sid}"})
        response = conn.getresponse(); combined = response.read().decode(); conn.close()
        combined_canvas = combined.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]
        assert response.status == 200 and 'topology-edge reachability' not in combined_canvas
        assert "netconfig-topology-layout-v2-combined" in combined
        assert "Show inferred FDB paths" in combined

        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/topology?view=physical&show_unconnected=1",
                     headers={"Cookie": f"ncsid={sid}"})
        response = conn.getresponse(); unconnected = response.read().decode(); conn.close()
        unconnected_canvas = unconnected.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]
        assert response.status == 200
        assert 'data-node="Forti101F-EH"' in unconnected_canvas
        assert 'data-node="switch-1"' in unconnected_canvas
        assert 'topology-edge inferred' not in unconnected_canvas
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


def test_physical_default_keeps_confirmed_lldp_adjacency(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "core", "192.0.2.1")
    _device(manager, "access", "192.0.2.2")
    manager.db.set_neighbors("core", [{
        "protocol": "lldp", "local_port": "Gi1/0/1", "local_port_num": "1",
        "sys_name": "access", "chassis_id": "", "port_id": "Gi1/0/48",
        "managed_neighbor": True, "neighbor_device": "access",
        "resolution_state": "RESOLVED", "resolution_evidence": "sys_name:access",
    }])
    server, thread, sid = _start_console(manager)
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/topology?view=physical", headers={"Cookie": f"ncsid={sid}"})
        response = conn.getresponse(); page = response.read().decode(); conn.close()
        canvas = page.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]
        assert response.status == 200
        assert 'topology-edge observed' in canvas
        assert 'data-node="core"' in canvas and 'data-node="access"' in canvas
        assert 'topology-edge inferred' not in canvas
        assert "Gi1/0/48 ↔ Gi1/0/1" in canvas
        assert canvas.count('class="topology-edge observed"') == 1
        assert "Physical defaults to confirmed LLDP/CDP adjacency" in page
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_routing_views_hide_inventory_islands_and_combined_fdb_by_default(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "r1", "192.0.2.1")
    _device(manager, "isolated", "192.0.2.99")
    nodes = [
        {"id": "device:r1", "kind": "DEVICE", "device": "r1", "label": "r1", "host": "192.0.2.1"},
        {"id": "device:isolated", "kind": "DEVICE", "device": "isolated", "label": "isolated", "host": "192.0.2.99"},
        {"id": "subnet:default:10.0.0.0/30", "kind": "SUBNET", "label": "10.0.0.0/30", "vrf": "default"},
    ]
    direct = {
        "kind": "DIRECTLY_CONNECTED", "from": "device:r1",
        "to": "subnet:default:10.0.0.0/30", "vrf": "default",
        "outgoing_interface": "Gi0/0", "evidence_state": "FRESH",
        "resolution_state": "DIRECT", "route_count": 1,
    }
    fdb = {
        "kind": "FDB_PATH", "from": "device:r1", "to": "device:isolated",
        "vrf": "", "outgoing_interface": "Gi0/1",
        "evidence_state": "FRESH", "resolution_state": "INFERRED",
        "route_count": 0,
    }
    summary = {
        "managed_devices": 2, "subnets": 1, "next_hop_edges": 0,
        "unresolved_next_hops": 0, "ambiguous_next_hops": 0,
        "stale_routes_excluded": 0,
    }
    l3_graph = {
        "nodes": nodes, "edges": [direct], "summary": summary,
        "unresolved_next_hops": [], "ambiguous_next_hops": [],
        "collection_status": [],
    }
    combined_graph = {**l3_graph, "edges": [direct, fdb]}
    manager.l3_topology_graph = lambda include_stale=False: l3_graph
    manager.combined_topology_graph = lambda include_stale=False: combined_graph
    server, thread, sid = _start_console(manager)
    try:
        def canvas_for(path):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.request("GET", path, headers={"Cookie": f"ncsid={sid}"})
            response = conn.getresponse(); page = response.read().decode(); conn.close()
            assert response.status == 200
            return page, page.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]

        page, canvas = canvas_for("/topology?view=l3")
        assert 'data-node="device:r1"' in canvas
        assert 'data-node="device:isolated"' not in canvas
        assert 'topology-edge l3-connected' in canvas
        assert "netconfig-topology-layout-v2-l3" in page
        assert "Show unconnected inventory (1)" in page

        _page, canvas = canvas_for("/topology?view=l3&show_unconnected=1")
        assert 'data-node="device:isolated"' in canvas

        page, canvas = canvas_for("/topology?view=combined")
        assert 'topology-edge reachability' not in canvas
        assert 'data-node="device:isolated"' not in canvas
        assert "Show inferred FDB paths (1)" in page

        _page, canvas = canvas_for("/topology?view=combined&show_inferred=1")
        assert 'topology-edge reachability' in canvas
        assert "FDB reachability" in canvas
        assert 'data-node="device:isolated"' in canvas
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_routing_view_can_show_next_hop_line_on_shared_subnet(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "r1", "192.168.0.2")
    _device(manager, "r2", "192.168.0.1")
    nodes = [
        {"id": "device:r1", "kind": "DEVICE", "device": "r1", "label": "r1", "host": "192.168.0.2"},
        {"id": "device:r2", "kind": "DEVICE", "device": "r2", "label": "r2", "host": "192.168.0.1"},
        {"id": "subnet:default:192.168.0.0/24", "kind": "SUBNET", "label": "192.168.0.0/24", "vrf": "default"},
    ]
    edges = [
        {"kind": "DIRECTLY_CONNECTED", "from": "device:r1", "to": "subnet:default:192.168.0.0/24",
         "vrf": "default", "outgoing_interface": "Gi0/1", "route_count": 0},
        {"kind": "DIRECTLY_CONNECTED", "from": "device:r2", "to": "subnet:default:192.168.0.0/24",
         "vrf": "default", "outgoing_interface": "Gi0/1", "route_count": 0},
        {"kind": "NEXT_HOP", "from": "device:r1", "to": "device:r2", "vrf": "default",
         "next_hop": "192.168.0.1", "outgoing_interface": "Gi0/1",
         "evidence_state": "DISCOVERED", "resolution_state": "MANAGED_INTERFACE_IP", "route_count": 1},
    ]
    graph = {
        "nodes": nodes, "edges": edges,
        "summary": {"managed_devices": 2, "subnets": 1, "transit_subnets": 1,
                    "next_hop_edges": 1, "unresolved_next_hops": 0,
                    "ambiguous_next_hops": 0, "stale_routes_excluded": 0},
        "unresolved_next_hops": [], "ambiguous_next_hops": [],
        "collection_status": [],
    }
    manager.l3_topology_graph = lambda include_stale=False: graph
    manager.combined_topology_graph = lambda include_stale=False: graph
    server, thread, sid = _start_console(manager)
    try:
        def canvas_for(path):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            conn.request("GET", path, headers={"Cookie": f"ncsid={sid}"})
            response = conn.getresponse(); page = response.read().decode(); conn.close()
            assert response.status == 200
            return page, page.split('<svg id="topology-canvas"', 1)[1].split('</svg>', 1)[0]

        page, canvas = canvas_for("/topology?view=l3")
        assert "Show next-hop lines on shared subnets" in page
        assert 'topology-edge routing' not in canvas

        page, canvas = canvas_for("/topology?view=l3&show_shared_nexthops=1")
        assert "Hide next-hop lines on shared subnets" in page
        assert 'topology-edge routing' in canvas
        assert "r1→r2 via 192.168.0.1 (Gi0/1)" in canvas
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()
