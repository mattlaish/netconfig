import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'opt', 'netconfig'))

from netconfig.db import Database
from netconfig.sensor import SensorEngine


def make_engine():
    db = Database(":memory:")
    return db, SensorEngine(db.conn)


def by_type(engine, sensor_type, device=None):
    return engine.list(device=device, sensor_type=sensor_type, limit=2000)


def test_sensor_upsert_and_filters():
    db, engine = make_engine()
    try:
        engine.upsert("interface.utilization", device="sw1", resource="1",
                      value="82", unit="%", status="WARNING")
        engine.upsert("interface.status", device="sw1", resource="1",
                      value="UP", status="OK")
        engine.upsert("interface.status", device="sw2", resource="1",
                      value="UP", status="OK")
        assert len(engine.list(device="sw1")) == 2
        assert len(engine.list(sensor_type="interface.status")) == 2
        assert len(engine.list(status="WARNING")) == 1
        assert len(engine.list(limit=1)) == 1
    finally:
        db.close()


def test_sensor_status_contract_rejects_unknown_values():
    db, engine = make_engine()
    try:
        for status in ("OK", "WARNING", "CRITICAL", "UNKNOWN"):
            engine.upsert(f"contract.{status.lower()}", status=status)
        with pytest.raises(ValueError):
            engine.upsert("contract.invalid", status="BROKEN")
        with pytest.raises(ValueError):
            engine.list(status="BROKEN")
    finally:
        db.close()


def test_endpoint_evidence_absence_is_unknown_not_failure():
    db, engine = make_engine()
    try:
        engine.refresh_endpoint_evidence("sw1")
        arp = by_type(engine, "endpoint.arp_evidence", "sw1")[0]
        fdb = by_type(engine, "endpoint.fdb_evidence", "sw1")[0]
        assert arp["status"] == "UNKNOWN"
        assert arp["value"] == ""
        assert "not a failure verdict" in arp["message"]
        assert fdb["status"] == "UNKNOWN"
    finally:
        db.close()


def test_endpoint_evidence_uses_existing_rows_only():
    db, engine = make_engine()
    try:
        db.set_vlan_fdb("sw1", [{"vlan_id": "10", "fdb_id": "10", "mac": "00:11:22:33:44:55"}])
        db.set_ip_neighbors("sw1", [])
        engine.refresh_endpoint_evidence("sw1")
        arp = by_type(engine, "endpoint.arp_evidence", "sw1")[0]
        fdb = by_type(engine, "endpoint.fdb_evidence", "sw1")[0]
        assert arp["status"] == "UNKNOWN"
        assert fdb["status"] == "OK"
        assert fdb["value"] == "1"
    finally:
        db.close()


def test_interface_generator_status_utilization_errors_and_unknown_discards():
    db, engine = make_engine()
    try:
        db.conn.execute(
            "INSERT INTO interface_stats(device,ifindex,descr,admin,oper,speed,in_octets,out_octets,"
            "in_errors,out_errors,in_bps,out_bps,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("sw1", "1", "uplink", "up", "up", 1_000_000_000, 0, 0, 0, 0,
             500_000_000.0, 250_000_000.0, 1.0))
        db.conn.execute(
            "INSERT INTO interface_stats(device,ifindex,descr,admin,oper,speed,in_octets,out_octets,"
            "in_errors,out_errors,in_bps,out_bps,ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("sw1", "2", "edge", "up", "down", 1_000_000_000, 0, 0, 2, 1,
             None, None, 1.0))
        db.conn.commit()

        engine.refresh_interface_health("sw1")

        status = {s["resource"]: s for s in by_type(engine, "interface.status", "sw1")}
        assert status["1"]["value"] == "UP" and status["1"]["status"] == "OK"
        assert status["2"]["value"] == "DOWN" and status["2"]["status"] == "WARNING"

        util = {s["resource"]: s for s in by_type(engine, "interface.utilization", "sw1")}
        assert util["1"]["value"] == "50.00" and util["1"]["status"] == "OK"
        assert util["2"]["value"] == "" and util["2"]["status"] == "UNKNOWN"
        assert util["2"]["status"] not in {"WARNING", "CRITICAL"}

        errors = {s["resource"]: s for s in by_type(engine, "interface.errors", "sw1")}
        assert errors["1"]["value"] == "0" and errors["1"]["status"] == "OK"
        assert errors["2"]["value"] == "3" and errors["2"]["status"] == "WARNING"

        discards = by_type(engine, "interface.discards", "sw1")
        assert discards and all(s["status"] == "UNKNOWN" and s["value"] == "" for s in discards)
    finally:
        db.close()


def test_interface_generator_no_rows_creates_unknown_without_fake_value():
    db, engine = make_engine()
    try:
        engine.refresh_interface_health("sw-empty")
        util = by_type(engine, "interface.utilization", "sw-empty")[0]
        assert util["status"] == "UNKNOWN"
        assert util["value"] == ""
    finally:
        db.close()


def test_topology_generator_counts_managed_and_unmanaged_neighbors():
    db, engine = make_engine()
    try:
        db.set_neighbors("sw1", [
            {"protocol": "lldp", "local_port": "1/1/1", "sys_name": "sw2",
             "chassis_id": "aa", "port_id": "1", "managed_neighbor": True},
            {"protocol": "lldp", "local_port": "1/1/2", "sys_name": "phone-1",
             "chassis_id": "bb", "port_id": "2", "managed_neighbor": False},
        ])
        engine.refresh_topology_health("sw1")
        total = by_type(engine, "topology.neighbor", "sw1")[0]
        managed = by_type(engine, "topology.managed_neighbor_count", "sw1")[0]
        unmanaged = by_type(engine, "topology.unmanaged_neighbor_count", "sw1")[0]
        assert total["value"] == "2" and total["status"] == "WARNING"
        assert managed["value"] == "1" and managed["status"] == "OK"
        assert unmanaged["value"] == "1" and unmanaged["status"] == "WARNING"
    finally:
        db.close()


def test_topology_no_evidence_is_unknown():
    db, engine = make_engine()
    try:
        engine.refresh_topology_health("sw-empty")
        sensor = by_type(engine, "topology.neighbor", "sw-empty")[0]
        assert sensor["status"] == "UNKNOWN"
        assert sensor["value"] == ""
    finally:
        db.close()


def test_known_loop_protection_mib_maps_to_semantic_sensor_only():
    db, engine = make_engine()
    try:
        db.set_mib_values("sw1", [
            {"oid": "1.2.3.1", "name": "arubaWiredLoopProtectPortEnable.1", "value": "1", "mib_source": "ARUBA"},
            {"oid": "1.2.3.2", "name": "arubaWiredLoopProtectPortLoopDetected.1", "value": "2", "mib_source": "ARUBA"},
            {"oid": "1.2.3.3", "name": "arubaWiredLoopProtectPortLoopCount.1", "value": "0", "mib_source": "ARUBA"},
            {"oid": "1.2.3.99", "name": "vendorRawMysteryValue.7", "value": "123", "mib_source": "ARUBA"},
        ])
        engine.refresh_mib_summary("sw1")
        loop = by_type(engine, "loop_protection.health", "sw1")
        assert len(loop) == 1
        assert loop[0]["status"] == "OK"
        assert "Enabled ports=1" in loop[0]["message"]
        all_types = {s["sensor_type"] for s in engine.list(device="sw1", limit=2000)}
        assert "vendorRawMysteryValue.7" not in all_types
        assert len(all_types) == 1
    finally:
        db.close()


def test_loop_protection_current_detection_is_critical():
    db, engine = make_engine()
    try:
        db.set_mib_values("sw1", [
            {"oid": "1.2.3.2", "name": "arubaWiredLoopProtectPortLoopDetected.48", "value": "1", "mib_source": "ARUBA"},
        ])
        engine.refresh_mib_summary("sw1")
        sensor = by_type(engine, "loop_protection.health", "sw1")[0]
        assert sensor["status"] == "CRITICAL"
        assert "Loop detected=1" in sensor["message"]
    finally:
        db.close()


def test_inventory_refresh_generates_from_persisted_evidence_only():
    db, engine = make_engine()
    try:
        db.conn.execute(
            "INSERT INTO devices(name,host,created,updated) VALUES(?,?,?,?)",
            ("sw1", "192.0.2.10", 1.0, 1.0))
        db.conn.execute(
            "INSERT INTO device_facts(device,reachable,last_polled,error) VALUES(?,?,?,?)",
            ("sw1", 1, 2.0, ""))
        db.conn.commit()

        class Inventory:
            def list(self):
                return [{"name": "sw1"}]

        engine.refresh_inventory_health(Inventory())
        assert by_type(engine, "device.reachability", "sw1")[0]["status"] == "OK"
        assert by_type(engine, "device.polling", "sw1")[0]["status"] == "OK"
        assert by_type(engine, "endpoint.arp_evidence", "sw1")[0]["status"] == "UNKNOWN"
    finally:
        db.close()


def test_postgres_sensor_table_ddl_uses_bigserial_not_sqlite_autoincrement():
    class Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakePostgresConn:
        dialect = "postgres"

        def __init__(self):
            self.sql = []

        def execute(self, sql, params=()):
            self.sql.append(str(sql))
            return Result()

        def commit(self):
            return None

    conn = FakePostgresConn()
    SensorEngine(conn)
    ddl = "\n".join(conn.sql)
    assert "BIGSERIAL PRIMARY KEY" in ddl
    assert "AUTOINCREMENT" not in ddl
