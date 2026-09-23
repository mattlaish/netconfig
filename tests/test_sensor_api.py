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
        enabled=True, tags=["sensor"], notes="", snmp_version="", snmp_ref=None,
    )


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
    data = json.loads(response.read().decode() or "null")
    status = response.status
    conn.close()
    return status, data


def test_sensor_api_filters_device_type_and_unknown_status(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager)
    manager.inv.set_facts("sw1", reachable=True, error="")
    manager.inv.set_interfaces("sw1", [{
        "ifindex": "1", "descr": "1/1/1", "admin": "up", "oper": "up",
        "speed": 1_000_000_000, "in_octets": 100, "out_octets": 200,
        "in_errors": 0, "out_errors": 0,
    }])
    # MC-1 contract: collection/evidence ingestion refreshes the canonical Sensor
    # snapshot; GET /api/v1/sensors is read-only and must not refresh it.
    manager.sensors.refresh_inventory_health(manager.inv)
    token = ApiTokens(manager.db.conn).create(
        "sensor-reader", {"analytics:read"}, created_by="test", role="viewer")[1]
    server, thread = _start_api(manager)
    try:
        status, rows = _api(server, token, "/api/v1/sensors")
        assert status == 200
        assert rows and all("sensor_type" in row and "status" in row for row in rows)

        status, rows = _api(server, token, "/api/v1/sensors?device=sw1")
        assert status == 200 and rows
        assert all(row["device"] == "sw1" for row in rows)

        status, rows = _api(server, token, "/api/v1/sensors?type=interface.status")
        assert status == 200 and rows
        assert all(row["sensor_type"] == "interface.status" for row in rows)

        status, rows = _api(server, token, "/api/v1/sensors?status=UNKNOWN")
        assert status == 200 and rows
        assert all(row["status"] == "UNKNOWN" for row in rows)
        assert any(row["sensor_type"] == "endpoint.arp_evidence" for row in rows)
        assert any(row["sensor_type"] == "topology.neighbor" for row in rows)
        assert any(row["sensor_type"] == "interface.utilization" for row in rows)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        manager.close()


def test_sensor_api_rejects_invalid_status_filter(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager)
    token = ApiTokens(manager.db.conn).create(
        "sensor-reader", {"inventory:read"}, created_by="test", role="viewer")[1]
    server, thread = _start_api(manager)
    try:
        status, body = _api(server, token, "/api/v1/sensors?status=BROKEN")
        assert status == 400
        assert body["error"] == "sensor_query_failed"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        manager.close()
