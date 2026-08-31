from netconfig import configmodel
from netconfig.drivers import get_driver


def test_cisco_semantic_plan_removes_rogue_and_restores_baseline():
    baseline = """hostname sw1
interface Gi1/0/1
 description Server
 switchport access vlan 10
!
"""
    current = """hostname sw1
interface Gi1/0/1
 description Hacked
 switchport access vlan 10
 ip access-group EVIL in
!
"""
    plan = configmodel.plan_indented(baseline, current)
    commands = plan["commands"]
    assert "interface Gi1/0/1" in commands
    assert "no description Hacked" in commands
    assert "no ip access-group EVIL in" in commands
    assert "description Server" in commands


def test_comware_uses_undo_negation():
    plan = get_driver("hp_comware").remediation_plan(
        "interface GigabitEthernet1/0/1\n description safe\n",
        "interface GigabitEthernet1/0/1\n description rogue\n",
    )
    assert "undo description rogue" in plan["commands"]


def test_junos_set_diff_uses_delete():
    plan = configmodel.plan_junos_set(
        "set system host-name edge\nset system services ssh\n",
        "set system host-name edge\nset system services ssh\nset system services telnet\n",
    )
    assert plan["commands"] == ["delete system services telnet"]


def test_whole_rogue_subtree_is_removed_at_parent():
    plan = configmodel.plan_indented(
        "hostname sw1\n",
        "hostname sw1\ninterface Loopback999\n description rogue\n ip address 192.0.2.1 255.255.255.255\n",
    )
    assert "no interface Loopback999" in plan["commands"]
    assert "no description rogue" not in plan["commands"]
