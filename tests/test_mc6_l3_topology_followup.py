import http.client
import json
import threading
import time

from netconfig.apitokens import ApiTokens
from netconfig.drivers import get_driver
from netconfig.l3topology import parse_interfaces, parse_routes
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def _add(manager, name, host, platform="aruba_aoscx"):
    manager.inv.upsert(
        name=name, host=host, port=22, platform=platform, device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["mc6-l3"], notes="", snmp_version="", snmp_ref=None,
    )


class _EvidenceTransport:
    def __init__(self, address, routes, config="hostname sw\n"):
        self.address = address
        self.routes = routes
        self.config = config
        self.transcript = b""
        self.prompt = b"sw#"
        self.command_timeout = 5
        self.closed = False

    def discover_prompt(self):
        return self.prompt

    def execute(self, command, expect=None):
        if command == "no page":
            return ""
        if command == "show running-config":
            return self.config
        if command == "show ip interface brief":
            return self.address
        if command == "show ip route":
            return self.routes
        raise AssertionError(f"unexpected command {command}")

    def close(self):
        self.closed = True


def test_supported_parsers_keep_vrf_and_do_not_invent_next_device():
    interfaces = parse_interfaces("aruba_aoscx", "1/1/1 10.0.0.1/30 up up\n")
    assert interfaces == [{
        "vrf": "default", "interface": "1/1/1", "ip_address": "10.0.0.1",
        "prefix_length": 30, "network_prefix": "10.0.0.0/30",
    }]
    routes = parse_routes(
        "cisco_ios",
        "Routing Table: BLUE\n"
        "C    10.0.0.0/30 is directly connected, Gi0/1\n"
        "O    10.20.0.0/16 [110/20] via 10.0.0.2, 00:00:10, Gi0/1\n"
        "S*   0.0.0.0/0 [1/0] via 10.0.0.2\n",
    )
    assert routes[0]["vrf"] == "BLUE"
    assert routes[0]["terminal"] is True
    assert routes[1]["protocol"] == "OSPF"
    assert routes[1]["next_hop"] == "10.0.0.2"
    assert "next_device" not in routes[1]
    assert routes[2]["protocol"] == "STATIC"


def test_config_collection_reuses_session_and_persists_l3_evidence(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "core", "192.0.2.10")
    tp = _EvidenceTransport(
        "1/1/1 10.0.0.1/30 up up\n",
        "C    10.0.0.0/30 is directly connected, 1/1/1\n"
        "S    172.16.0.0/16 [1/0] via 10.0.0.2, 1/1/1\n",
    )
    monkeypatch.setattr(manager, "_connect", lambda _device: (tp, None))
    try:
        result = manager.collect("core")
        assert result.ok is True
        assert result.l3["status"] == "OK"
        assert result.l3["routes"] == 2
        assert result.l3["interfaces"] == 1
        state = manager.l3_collection_status("core")
        assert state["status"] == "OK"
        assert state["route_count"] == 2
        assert state["interface_count"] == 1
        assert tp.closed is True
    finally:
        manager.close()


def test_unique_same_vrf_interface_match_builds_next_hop_edge(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "r1", "192.0.2.1", "cisco_ios")
    _add(manager, "r2", "192.0.2.2", "cisco_ios")
    try:
        one = _EvidenceTransport(
            "Gi0/1 10.0.0.1 YES manual up up\n",
            "C 10.0.0.0/30 is directly connected, Gi0/1\n"
            "O 10.20.0.0/16 [110/2] via 10.0.0.2, 00:00:10, Gi0/1\n",
        )
        two = _EvidenceTransport(
            "Gi0/1 10.0.0.2 YES manual up up\n",
            "C 10.0.0.0/30 is directly connected, Gi0/1\n"
            "C 10.20.0.0/16 is directly connected, Gi0/2\n",
        )
        assert manager.l3_topology.collect_from_session(manager.inv.get("r1"), get_driver("cisco_ios"), one)["status"] == "OK"
        assert manager.l3_topology.collect_from_session(manager.inv.get("r2"), get_driver("cisco_ios"), two)["status"] == "OK"
        graph = manager.l3_topology_graph()
        edges = [e for e in graph["edges"] if e["kind"] == "NEXT_HOP"]
        assert len(edges) == 1
        assert edges[0]["from"] == "device:r1"
        assert edges[0]["to"] == "device:r2"
        assert edges[0]["resolution_state"] == "MANAGED_INTERFACE_IP"
        assert edges[0]["vrf"] == "default"
    finally:
        manager.close()


def test_ambiguous_or_cross_vrf_next_hop_fails_closed(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    for name in ("r1", "r2", "r3"):
        _add(manager, name, f"192.0.2.{len(name)}", "cisco_ios")
    now = time.time()
    try:
        # Manually seed two equally valid fresh managed-interface claims in BLUE.
        for dev in ("r2", "r3"):
            manager.db.conn.execute(
                "INSERT INTO l3_interface_observations(tenant_id,device,vrf,interface,ip_address,prefix_length,network_prefix,source_kind,collection_id,evidence_ref,observed_ts,received_ts,max_age_seconds) "
                "VALUES('default',?,?,?,?,?,?, 'MANUAL','',?,?,?,3600)",
                (dev, "BLUE", "Gi0/1", "10.1.1.2", 30, "10.1.1.0/30", f"test:{dev}", now, now),
            )
        manager.analytics.add_l3_route(
            device="r1", vrf="BLUE", destination_prefix="203.0.113.0/24",
            next_hop="10.1.1.2", protocol="ospf", actor="test")
        # RED evidence with the same IP may never resolve the BLUE route either.
        manager.db.conn.execute(
            "INSERT INTO l3_interface_observations(tenant_id,device,vrf,interface,ip_address,prefix_length,network_prefix,source_kind,collection_id,evidence_ref,observed_ts,received_ts,max_age_seconds) "
            "VALUES('default',?,?,?,?,?,?, 'MANUAL','',?,?,?,3600)",
            ("r2", "RED", "Gi0/2", "10.1.1.2", 30, "10.1.1.0/30", "test:red", now, now),
        )
        manager.db.conn.commit()
        graph = manager.l3_topology_graph()
        assert not [e for e in graph["edges"] if e["kind"] == "NEXT_HOP"]
        assert graph["summary"]["ambiguous_next_hops"] == 1
        assert set(graph["ambiguous_next_hops"][0]["candidates"]) == {"r2", "r3"}
    finally:
        manager.close()


def test_stale_interface_evidence_cannot_resolve_fresh_route(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "r1", "192.0.2.1", "cisco_ios")
    _add(manager, "r2", "192.0.2.2", "cisco_ios")
    now = time.time()
    try:
        manager.db.conn.execute(
            "INSERT INTO l3_interface_observations(tenant_id,device,vrf,interface,ip_address,prefix_length,network_prefix,source_kind,collection_id,evidence_ref,observed_ts,received_ts,max_age_seconds) "
            "VALUES('default','r2','default','Gi0/1','10.0.0.2',30,'10.0.0.0/30','MANUAL','','stale',?,?,60)",
            (now - 3600, now - 3600),
        )
        manager.analytics.add_l3_route(
            device="r1", vrf="default", destination_prefix="10.20.0.0/16",
            next_hop="10.0.0.2", protocol="ospf", actor="test")
        graph = manager.l3_topology_graph()
        assert graph["summary"]["next_hop_edges"] == 0
        assert graph["summary"]["unresolved_next_hops"] == 1
    finally:
        manager.close()


def test_failed_refresh_preserves_last_successful_generation(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "r1", "192.0.2.1", "cisco_ios")
    try:
        good = _EvidenceTransport(
            "Gi0/1 10.0.0.1 YES manual up up\n",
            "C 10.0.0.0/30 is directly connected, Gi0/1\n",
        )
        assert manager.l3_topology.collect_from_session(manager.inv.get("r1"), get_driver("cisco_ios"), good)["status"] == "OK"
        before = manager.l3_collection_status("r1")["collection_id"]
        bad = _EvidenceTransport(
            "Gi0/1 10.0.0.1 YES manual up up\n",
            "% Invalid input detected at '^' marker.\n",
        )
        failed = manager.l3_topology.collect_from_session(manager.inv.get("r1"), get_driver("cisco_ios"), bad)
        assert failed["status"] == "ERROR"
        state = manager.l3_collection_status("r1")
        assert state["collection_id"] == before
        assert state["status"] == "ERROR"
        # Last good route generation is still available; ERROR is collection status, not evidence deletion.
        assert len(manager.l3_topology.routes("r1")) == 1
    finally:
        manager.close()


def _start_api(manager):
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _api(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Authorization": f"Bearer {token}"})
    response = conn.getresponse()
    body = json.loads(response.read().decode() or "null")
    status = response.status
    conn.close()
    return status, body


def test_l3_topology_api_requires_topology_read_and_is_db_only(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "r1", "192.0.2.1")
    allowed = ApiTokens(manager.db.conn).create("l3-reader", {"topology:read"}, created_by="test", role="viewer")[1]
    denied = ApiTokens(manager.db.conn).create("l3-denied", {"inventory:read"}, created_by="test", role="viewer")[1]
    server, thread = _start_api(manager)
    try:
        status, payload = _api(server, allowed, "/api/v1/topology/l3")
        assert status == 200
        assert payload["summary"]["managed_devices"] == 1
        status, _ = _api(server, denied, "/api/v1/topology/l3")
        assert status == 403
        status, payload = _api(server, allowed, "/api/v1/topology/combined")
        assert status == 200 and "edges" in payload
        status, payload = _api(server, allowed, "/api/v1/topology/l3/status?device=r1")
        assert status == 200 and payload["status"] == "NOT_COLLECTED"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()


def test_l3_failure_does_not_destroy_valid_configuration_collection(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "core", "192.0.2.10")
    tp = _EvidenceTransport(
        "1/1/1 10.0.0.1/30 up up\n",
        "% Invalid input detected at '^' marker.\n",
        config="hostname core\ninterface 1/1/1\n no shutdown\n",
    )
    monkeypatch.setattr(manager, "_connect", lambda _device: (tp, None))
    try:
        result = manager.collect("core")
        assert result.ok is True
        assert result.l3["status"] == "ERROR"
        assert manager.l3_collection_status("core")["status"] == "ERROR"
        assert "hostname core" in result.config
    finally:
        manager.close()


def test_l3_topology_web_view_is_persisted_evidence_only(tmp_path, monkeypatch):
    import netconfig.web as web
    manager = Manager(str(tmp_path / "home"))
    _add(manager, "core", "192.0.2.10")
    # Rendering the page must not create an SSH/SNMP side effect.
    monkeypatch.setattr(manager, "_connect", lambda _device: (_ for _ in ()).throw(AssertionError("device I/O from GET")))
    web._SESSIONS.clear()
    sid = "mc6-l3-viewer"
    web._SESSIONS[sid] = {"username": "viewer", "role": "viewer", "csrf": "x", "created": time.time()}
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/topology?view=l3", headers={"Cookie": f"ncsid={sid}"})
        response = conn.getresponse(); body = response.read().decode(); conn.close()
        assert response.status == 200
        assert "Topology view" in body and "Layer 3" in body and "Combined" in body
        assert "Rendering never polls a device" in body
        assert 'action="/topology-discover"' not in body
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()
