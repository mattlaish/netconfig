import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'opt', 'netconfig'))

from netconfig.db import Database
from netconfig.sensor import SensorEngine


def _rows(db, table):
    return [dict(r) for r in db.conn.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]


def test_observation_is_recorded_for_each_sensor_upsert():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        engine.upsert("device.reachability", device="fw1", value="reachable", status="OK", source="test")
        engine.upsert("device.reachability", device="fw1", value="reachable", status="OK", source="test")
        observations = _rows(db, "sensor_observations")
        transitions = _rows(db, "sensor_transitions")
        assert len(observations) == 2
        assert observations[-1]["sensor_key"] == "device.reachability|fw1|"
        assert observations[-1]["status"] == "OK"
        assert transitions == []
    finally:
        db.close()


def test_unknown_to_ok_is_evidence_recovered_not_critical():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        engine.upsert("endpoint.arp_evidence", device="sw1", status="UNKNOWN", source="test")
        engine.upsert("endpoint.arp_evidence", device="sw1", value="4", status="OK", source="test")
        transitions = _rows(db, "sensor_transitions")
        assert len(transitions) == 1
        row = transitions[0]
        assert row["previous_status"] == "UNKNOWN"
        assert row["new_status"] == "OK"
        assert json.loads(row["metadata_json"])["reason"] == "evidence_recovered"
        assert row["new_status"] != "CRITICAL"
    finally:
        db.close()


def test_unknown_to_warning_is_recorded_without_fake_critical():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        engine.upsert("topology.neighbor", device="sw1", status="UNKNOWN", source="test")
        engine.upsert("topology.neighbor", device="sw1", value="3", status="WARNING", source="test")
        transitions = _rows(db, "sensor_transitions")
        assert len(transitions) == 1
        assert transitions[0]["previous_status"] == "UNKNOWN"
        assert transitions[0]["new_status"] == "WARNING"
        assert json.loads(transitions[0]["metadata_json"])["reason"] == "evidence_recovered"
    finally:
        db.close()


def test_numeric_thresholds_record_only_severity_crossings():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        engine.upsert("interface.utilization", device="sw1", resource="1", value="70", unit="%", status="OK")
        engine.upsert("interface.utilization", device="sw1", resource="1", value="75", unit="%", status="OK")
        assert _rows(db, "sensor_transitions") == []

        # Caller status is normalized by the Sensor threshold contract.
        engine.upsert("interface.utilization", device="sw1", resource="1", value="85", unit="%", status="OK")
        engine.upsert("interface.utilization", device="sw1", resource="1", value="97", unit="%", status="OK")
        transitions = _rows(db, "sensor_transitions")
        assert [(r["previous_status"], r["new_status"]) for r in transitions] == [
            ("OK", "WARNING"),
            ("WARNING", "CRITICAL"),
        ]
    finally:
        db.close()


def test_restart_does_not_duplicate_transition_for_unchanged_state(tmp_path):
    db_path = tmp_path / "netconfig.db"
    db = Database(str(db_path))
    engine = SensorEngine(db.conn)
    engine.upsert("device.polling", device="fw1", value="healthy", status="OK")
    engine.upsert("device.polling", device="fw1", value="error", status="WARNING")
    assert len(_rows(db, "sensor_transitions")) == 1
    db.close()

    db2 = Database(str(db_path))
    try:
        restarted = SensorEngine(db2.conn)
        restarted.upsert("device.polling", device="fw1", value="error", status="WARNING")
        transitions = _rows(db2, "sensor_transitions")
        assert len(transitions) == 1
        assert transitions[0]["previous_status"] == "OK"
        assert transitions[0]["new_status"] == "WARNING"
    finally:
        db2.close()


def test_interface_refresh_preserves_previous_snapshot_for_transition_detection():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        db.conn.execute(
            "INSERT INTO interface_stats(device,ifindex,descr,admin,oper,speed,in_octets,out_octets,"
            "in_errors,out_errors,in_bps,out_bps,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("sw1", "1", "uplink", "up", "up", 1_000_000_000, 0, 0, 0, 0,
             700_000_000.0, 100_000_000.0, 1.0))
        db.conn.commit()
        engine.refresh_interface_health("sw1")
        assert _rows(db, "sensor_transitions") == []

        db.conn.execute(
            "UPDATE interface_stats SET in_bps=?,out_bps=?,ts=? WHERE device=? AND ifindex=?",
            (850_000_000.0, 100_000_000.0, 2.0, "sw1", "1"))
        db.conn.commit()
        engine.refresh_interface_health("sw1")
        transitions = [r for r in _rows(db, "sensor_transitions")
                       if r["sensor_type"] == "interface.utilization"]
        assert len(transitions) == 1
        assert transitions[0]["previous_status"] == "OK"
        assert transitions[0]["new_status"] == "WARNING"
    finally:
        db.close()


def test_history_and_transition_queries_are_bounded_and_filterable():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        engine.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK")
        engine.upsert("interface.status", device="sw1", resource="1", value="DOWN", status="WARNING")
        key = engine.sensor_key("interface.status", "sw1", "1")
        history = engine.history_for(key, limit=10)
        assert history["sensor_key"] == key
        assert len(history["observations"]) == 2
        assert len(history["transitions"]) == 1

        transitions = engine.transitions(device="sw1", sensor_type="interface.status",
                                         from_status="OK", to_status="WARNING", limit=10)
        assert len(transitions) == 1
        assert transitions[0]["resource"] == "1"
    finally:
        db.close()


def _start_api(manager):
    import threading
    from netconfig.web import Console, _Server

    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _api_get(server, token, path):
    import http.client
    import json

    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Authorization": f"Bearer {token}"})
    response = conn.getresponse()
    data = json.loads(response.read().decode() or "null")
    status = response.status
    conn.close()
    return status, data


def test_history_api_and_transition_api_are_read_only(tmp_path):
    from urllib.parse import urlencode
    from netconfig.apitokens import ApiTokens
    from netconfig.manager import Manager

    manager = Manager(str(tmp_path / "home"))
    try:
        manager.sensors.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK")
        manager.sensors.upsert("interface.status", device="sw1", resource="1", value="DOWN", status="WARNING")
        key = manager.sensors.sensor_key("interface.status", "sw1", "1")
        before_obs = manager.db.conn.execute("SELECT COUNT(*) AS n FROM sensor_observations").fetchone()["n"]
        before_tr = manager.db.conn.execute("SELECT COUNT(*) AS n FROM sensor_transitions").fetchone()["n"]

        token = ApiTokens(manager.db.conn).create(
            "sensor-history-reader", {"analytics:read"}, created_by="test", role="viewer")[1]
        server, thread = _start_api(manager)
        try:
            status, history = _api_get(
                server, token, "/api/v1/sensor-history?" + urlencode({"sensor_key": key}))
            assert status == 200
            assert history["sensor_key"] == key
            assert len(history["observations"]) == 2
            assert len(history["transitions"]) == 1

            status, rows = _api_get(
                server, token,
                "/api/v1/sensor-transitions?" + urlencode({
                    "device": "sw1", "type": "interface.status",
                    "from_status": "OK", "to_status": "WARNING",
                }))
            assert status == 200
            assert len(rows) == 1
            assert rows[0]["resource"] == "1"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        after_obs = manager.db.conn.execute("SELECT COUNT(*) AS n FROM sensor_observations").fetchone()["n"]
        after_tr = manager.db.conn.execute("SELECT COUNT(*) AS n FROM sensor_transitions").fetchone()["n"]
        assert (after_obs, after_tr) == (before_obs, before_tr)
    finally:
        manager.close()


def test_transition_api_rejects_invalid_status(tmp_path):
    from netconfig.apitokens import ApiTokens
    from netconfig.manager import Manager

    manager = Manager(str(tmp_path / "home"))
    try:
        token = ApiTokens(manager.db.conn).create(
            "sensor-history-reader", {"inventory:read"}, created_by="test", role="viewer")[1]
        server, thread = _start_api(manager)
        try:
            status, body = _api_get(server, token, "/api/v1/sensor-transitions?to_status=BROKEN")
            assert status == 400
            assert body["error"] == "sensor_transition_query_failed"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    finally:
        manager.close()


def test_history_retention_prunes_expired_rows_on_record():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        db.conn.execute(
            "INSERT INTO sensor_observations(sensor_key,sensor_type,device,resource,value,unit,status,message,source,observed_at,metadata_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("old|sw1|", "old", "sw1", "", "", "", "OK", "", "test", 1.0, "{}", 1.0))
        db.conn.execute(
            "INSERT INTO sensor_transitions(sensor_key,sensor_type,device,resource,previous_status,new_status,previous_value,new_value,source,observed_at,metadata_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            ("old|sw1|", "old", "sw1", "", "OK", "WARNING", "1", "2", "test", 1.0, "{}", 1.0))
        db.conn.commit()

        engine.upsert("device.reachability", device="sw1", value="reachable", status="OK")
        assert db.conn.execute(
            "SELECT COUNT(*) AS n FROM sensor_observations WHERE sensor_key='old|sw1|'"
        ).fetchone()["n"] == 0
        assert db.conn.execute(
            "SELECT COUNT(*) AS n FROM sensor_transitions WHERE sensor_key='old|sw1|'"
        ).fetchone()["n"] == 0
    finally:
        db.close()


def test_mc2_history_indexes_cover_type_resource_status_and_time():
    db = Database(":memory:")
    try:
        names = {
            row["name"] for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_sensor_%'"
            ).fetchall()
        }
        assert {
            "idx_sensor_observations_device_time",
            "idx_sensor_observations_key_time",
            "idx_sensor_observations_type_time",
            "idx_sensor_observations_resource_time",
            "idx_sensor_transitions_device_time",
            "idx_sensor_transitions_key_time",
            "idx_sensor_transitions_status_time",
            "idx_sensor_transitions_type_time",
            "idx_sensor_transitions_resource_time",
        } <= names
    finally:
        db.close()
