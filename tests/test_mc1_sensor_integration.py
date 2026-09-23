import http.client
import json
import threading

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def _device(manager, name="sw1"):
    manager.inv.upsert(
        name=name, host="192.0.2.10", port=22, platform="aruba_aoscx", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["mc1"], notes="", snmp_version="", snmp_ref=None,
    )


def _start_api(manager):
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Authorization": f"Bearer {token}"})
    response = conn.getresponse()
    body = json.loads(response.read().decode() or "null")
    status = response.status
    conn.close()
    return status, body


def test_mc1_sensor_snapshot_contains_collection_truth(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager)
    try:
        manager.inv.set_facts("sw1", reachable=True, error="")
        manager.inv.set_interfaces("sw1", [{
            "ifindex": "1", "descr": "1/1/1", "admin": "up", "oper": "up",
            "speed": 1000000000, "in_octets": 100, "out_octets": 200,
            "in_errors": 0, "out_errors": 0,
        }])

        manager.sensors.refresh_inventory_health(manager.inv)
        sensors = manager.sensors.list(device="sw1", limit=100)
        assert any(s["sensor_type"] == "device.reachability" for s in sensors)
        assert any(s["sensor_type"] == "interface.status" for s in sensors)
    finally:
        manager.close()


def test_mc1_sensor_api_is_read_only_for_snapshot(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager)
    token = ApiTokens(manager.db.conn).create(
        "sensor-reader", {"analytics:read"}, created_by="test", role="viewer"
    )[1]
    server, thread = _start_api(manager)
    try:
        before = manager.sensors.list(device="sw1", limit=100)
        status, body = _get(server, token, "/api/v1/sensors")
        after = manager.sensors.list(device="sw1", limit=100)
        assert status == 200
        assert isinstance(body, list)
        assert before == after
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        manager.close()


def test_mc1_missing_evidence_remains_unknown(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager)
    try:
        manager.sensors.refresh_inventory_health(manager.inv)
        sensors = manager.sensors.list(device="sw1", limit=100)
        unknown_types = {s["sensor_type"] for s in sensors if s["status"] == "UNKNOWN"}
        assert "endpoint.arp_evidence" in unknown_types
        assert "topology.neighbor" in unknown_types
    finally:
        manager.close()
