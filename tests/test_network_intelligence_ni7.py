import http.client
import json
import threading
import urllib.parse

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server


def _device(manager, name, host):
    manager.inv.upsert(
        name=name, host=host, port=22, platform="cisco_iosxe", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["ni7"], notes="", snmp_version="", snmp_ref=None,
    )


def _manager(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "r1", "192.0.2.1")
    _device(manager, "r2", "192.0.2.2")
    _device(manager, "r3", "192.0.2.3")
    return manager


def test_l3_path_is_same_vrf_and_explicit_terminal_only(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="10.20.0.0/16",
            next_hop="192.0.2.2", next_device="r2", protocol="ospf", actor="seed")
        manager.analytics.add_l3_route(
            device="r2", vrf="blue", destination_prefix="10.20.0.0/16",
            outgoing_interface="Gi0/2", terminal=True, protocol="connected", actor="seed")
        # Same destination in another VRF must never enter the blue traversal.
        manager.analytics.add_l3_route(
            device="r1", vrf="red", destination_prefix="10.20.0.0/16",
            next_device="r3", protocol="bgp", actor="seed")
        result = manager.analytics.simulate_l3_path(
            "r1", "blue", "10.20.0.0/16", actor="alice", max_hops=8)
        assert result["path"]["status"] == "REACHED_TERMINAL"
        assert [hop["device"] for hop in result["path"]["hops"]] == ["r1", "r2"]
        assert result["insight"]["insight_type"] == "L3_PATH"
        assert result["insight"]["severity"] == "INFO"
        assert "action" not in result["insight"]["evidence"]
    finally:
        manager.close()


def test_l3_path_fails_closed_on_unresolved_and_multipath(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.analytics.add_l3_route(
            device="r1", vrf="default", destination_prefix="203.0.113.0/24",
            next_hop="192.0.2.254", actor="seed")
        unresolved = manager.analytics.simulate_l3_path(
            "r1", "default", "203.0.113.0/24", actor="alice")
        assert unresolved["path"]["status"] == "INCOMPLETE"
        assert "next_device" in unresolved["path"]["stop_reason"]

        manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="198.51.100.0/24",
            next_hop="192.0.2.2", next_device="r2", metric=10, actor="seed")
        manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="198.51.100.0/24",
            next_hop="192.0.2.3", next_device="r3", metric=10, actor="seed")
        ambiguous = manager.analytics.simulate_l3_path(
            "r1", "blue", "198.51.100.0/24", actor="alice")
        assert ambiguous["path"]["status"] == "AMBIGUOUS"
        assert not ambiguous["path"]["hops"]
        assert "no path selected" in ambiguous["path"]["stop_reason"]
    finally:
        manager.close()


def test_route_dependency_candidates_preserve_distinct_routes_and_alternates(tmp_path):
    manager = _manager(tmp_path)
    try:
        first = manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="10.0.0.0/8",
            next_device="r2", next_hop="192.0.2.2", actor="seed")
        second = manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="172.16.0.0/12",
            next_device="r2", next_hop="192.0.2.2", actor="seed")
        manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="10.0.0.0/8",
            next_device="r3", next_hop="192.0.2.3", actor="seed")
        result = manager.analytics.analyze_route_dependencies("r2", actor="alice")
        assert result["candidate_count"] == 2
        route_ids = {x["evidence"]["route"]["id"] for x in result["candidates"]}
        assert route_ids == {first["id"], second["id"]}
        ten = next(x for x in result["candidates"] if x["evidence"]["route"]["id"] == first["id"])
        assert ten["evidence"]["candidate"] is True
        assert len(ten["evidence"]["observed_alternates"]) == 1
        assert "outage" not in ten["summary"].lower()
    finally:
        manager.close()


def _start_api(manager):
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _api(server, token, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode()
    data = json.loads(raw or "null")
    status = response.status
    conn.close()
    return status, data


def test_ni7_api_scope_and_operator_boundary(tmp_path):
    manager = _manager(tmp_path)
    reader = ApiTokens(manager.db.conn).create(
        "ni7-reader", {"analytics:read"}, created_by="test", role="viewer")[1]
    operator = ApiTokens(manager.db.conn).create(
        "ni7-operator", {"analytics:read", "analytics:write"}, created_by="test", role="operator")[1]
    server, thread = _start_api(manager)
    try:
        status, _ = _api(server, reader, "POST", "/api/v1/analytics/l3/routes", {
            "device": "r1", "vrf": "blue", "destination_prefix": "10.0.0.0/8", "terminal": True,
        })
        assert status == 403
        status, route = _api(server, operator, "POST", "/api/v1/analytics/l3/routes", {
            "device": "r1", "vrf": "blue", "destination_prefix": "10.0.0.0/8", "terminal": True,
        })
        assert status == 201 and route["terminal"] is True
        status, rows = _api(server, reader, "GET", "/api/v1/analytics/l3/routes?device=r1&vrf=blue")
        assert status == 200 and len(rows) == 1
        status, path = _api(server, operator, "POST", "/api/v1/analytics/l3/path/simulate", {
            "source_device": "r1", "vrf": "blue", "destination_prefix": "10.0.0.0/8", "max_hops": 4,
        })
        assert status == 201 and path["path"]["status"] == "REACHED_TERMINAL"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()


def _web_request(server, token, method, path, form=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Cookie": f"ncsid={token}"}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse(); data = response.read(); status = response.status
    headers_out = dict(response.getheaders()); conn.close()
    return status, headers_out, data


def test_ni7_operations_ui_is_read_only_for_viewer_and_has_no_execution_path(tmp_path):
    manager = _manager(tmp_path)
    web._SESSIONS.clear()
    token, csrf = "ni7-viewer", "ni7-csrf"
    web._SESSIONS[token] = {"username": "viewer", "role": "viewer", "csrf": csrf, "created": 1.0}
    Console.manager = manager; Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        status, _, data = _web_request(server, token, "GET", "/operations?tab=intelligence")
        text = data.decode()
        assert status == 200
        assert "NI-7 · L3/VRF path intelligence" in text
        assert "Explicit route evidence only" in text
        assert 'action="/ops-l3-route-observe"' not in text
        assert 'action="/ops-l3-path"' not in text
        assert 'action="/ops-l3-dependencies"' not in text
        assert "no network mutation" in text.lower()
        assert "/operations?tab=structured" not in text or "approved Structured Changes" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear(); manager.close()
