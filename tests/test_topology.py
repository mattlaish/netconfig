from netconfig import topology


def test_lldp_walk_and_unmanaged_detection():
    b = topology.LLDP_REM_BASE
    remote = [
        (b + ".9.100.7.1", "core-2"),
        (b + ".7.100.7.1", "Gi1/0/48"),
        (b + ".5.100.7.1", "00:11:22:33:44:55"),
        (b + ".9.100.8.1", "rogue-switch"),
        (b + ".7.100.8.1", "Eth1"),
    ]
    local = [(topology.LLDP_LOC_PORT_DESC + ".7", "Gi1/0/7"),
             (topology.LLDP_LOC_PORT_DESC + ".8", "Gi1/0/8")]
    rows = topology.parse_lldp_walk(remote, local)
    assert rows[0]["local_port"] == "Gi1/0/7"
    analyzed = topology.analyze(rows, [{"name": "core-2", "host": "10.0.0.2"}])
    assert any(r["managed_neighbor"] for r in analyzed)
    assert any(r["unmanaged"] for r in analyzed)


def test_cdp_detail_parser():
    text = """Device ID: access-2\nIP address: 10.0.0.22\nPlatform: cisco WS-C2960, Capabilities: Switch\nInterface: GigabitEthernet1/0/1,  Port ID (outgoing port): GigabitEthernet0/24\n"""
    rows = topology.parse_cdp_detail(text)
    assert rows[0]["sys_name"] == "access-2"
    assert rows[0]["local_port"] == "GigabitEthernet1/0/1"
    assert rows[0]["port_id"] == "GigabitEthernet0/24"
