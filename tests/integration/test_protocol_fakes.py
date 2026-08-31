import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NETCONFIG_INTEGRATION") != "1",
    reason="set NETCONFIG_INTEGRATION=1 with CI protocol services running",
)


def test_real_openssh_transport_against_scripted_network_shell(tmp_path):
    from netconfig.transport import SSHTransport
    from netconfig.drivers import get_driver

    tp = SSHTransport(
        "127.0.0.1", "netops", port=2222, password="netconfig",
        known_hosts=str(tmp_path / "known_hosts"), host_key_policy="accept-new",
        connect_timeout=5, command_timeout=5,
    )
    try:
        tp.connect()
        driver = get_driver("generic")
        driver.initialize(tp)
        cfg = driver.fetch_config(tp)
        assert "hostname R1" in cfg
        assert "switchport access vlan 10" in cfg
    finally:
        tp.close()


def test_real_net_snmp_agent():
    from netconfig import snmp

    facts = snmp.poll_system(
        "127.0.0.1", port=1161, version="v2c", community="public", timeout=3.0
    )
    assert facts["reachable"] is True
    assert facts.get("sysdescr")


def test_real_postgres_history_roundtrip():
    from netconfig.ifhistory import PgHistory

    pg = PgHistory(
        params={
            "host": "127.0.0.1",
            "port": 5432,
            "dbname": "netconfig_test",
            "user": "netconfig",
            "password": "netconfig",
            "sslmode": "disable",
        },
        retention_hours=1,
    )
    ready = pg.ensure_ready()
    assert ready["ok"], ready
    import time
    now = time.time()
    pg.write("ci-device", [("1", "eth0", 100.0, 200.0, now)])
    data = pg.read("ci-device", hours=1, bucket_seconds=1)
    assert "1" in data
    assert data["1"]["points"]
