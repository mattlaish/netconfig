"""Safety/UX regression for MAC locations, visible route learning and MIB health."""
import json
import time
import urllib.parse
from pathlib import Path

import pytest

from test_web_ux import console as _console_fixture, _device
from test_mc6_l3_topology_followup import _EvidenceTransport
from netconfig import network_intelligence as ni
from netconfig.sensor import SensorEngine
from netconfig.vendor_profiles import load_profile_file, validate_profile, normalize
from netconfig.vendor_measurements import validate_numeric, reading
from netconfig.web_ux import _nav_active

console = _console_fixture
PROFILE = Path(__file__).resolve().parents[1] / 'usr/share/netconfig/snmp-profiles/fortinet.fortigate.json'
CPU = '1.3.6.1.4.1.12356.101.4.1.3.0'
MEMORY = '1.3.6.1.4.1.12356.101.4.1.4.0'
MAC = '02:00:00:00:00:01'


def seed_fdb(m, neighbor=False):
    _device(m, 'sw', '192.0.2.1', snmp_version='v2c')
    m.db.set_ip_neighbors('gateway', [{'ip': '192.0.2.10', 'mac': MAC, 'address_family': 'ipv4', 'source': 'ARP'}])
    m.db.set_vlan_fdb('sw', [{'mac': MAC, 'vlan_id': '10', 'ifindex': '10', 'bridge_port': '10', 'ifdescr': 'uplink', 'source': 'Q-BRIDGE-MIB'}])
    m.db.set_mac_table('sw', [{'mac': MAC, 'port': '10', 'ifindex': '10', 'ifdescr': 'uplink'}])
    if neighbor:
        m.db.set_neighbors('sw', [{'protocol': 'lldp', 'local_port': 'uplink', 'local_port_num': '10', 'sys_name': 'downstream', 'managed_neighbor': False}])


def seed_profile(m):
    _device(m, 'fg', '192.0.2.2', platform='fortigate', snmp_version='v2c')
    m.inv.set_facts('fg', reachable=True, sysname='FG', sysdescr='FortiGate', uptime='1d',
                    sysobjectid='1.3.6.1.4.1.12356.101.1', contact='', location='', error='')
    return m.vendor_profiles.match('1.3.6.1.4.1.12356.101.1')


def save_cpu(m, value):
    m.db.set_mib_values('fg', [{'oid': CPU, 'name': 'fgSysCpuUsage.0', 'value': str(value), 'mib_source': 'test'}], roots=1)


def test_unique_mac_is_only_candidate_and_not_proven_attachment(console):
    seed_fdb(console.m)
    row = console.m.endpoint_inventory()[0]
    assert row['status'] == 'CANDIDATE' and row['confidence'] == 'LOW'
    assert row['attachment'] is None and not row['direct_connection_proven']
    assert row['observed_location']['device'] == 'sw'
    assert console.m.endpoint_summary()['candidate'] == 1 and console.m.endpoint_summary()['attached'] == 0
    code, _, page = console.request('GET', '/endpoints', token=console.session())
    assert code == 200 and 'candidate, not proven direct' in page and 'proof of direct attachment' in page


@pytest.mark.parametrize('neighbor,label', [(False, 'Candidate location; not proven direct'), (True, 'Forwarded via known neighbor')])
def test_mac_table_explains_forwarded_vs_candidate_and_joins_gateway_ip(console, neighbor, label):
    seed_fdb(console.m, neighbor)
    code, _, page = console.request('GET', '/device?name=sw', token=console.session())
    assert code == 200 and 'Location evidence' in page and label in page
    assert '192.0.2.10' in page and 'no direct connection is asserted' in page
    if neighbor:
        assert console.m.endpoint_inventory()[0]['status'] == 'TRANSIT_ONLY'


def test_old_fdb_is_not_a_current_mac_location(console):
    seed_fdb(console.m)
    console.m.db.conn.execute('UPDATE vlan_fdb SET ts=1')
    console.m.db.conn.commit()
    _, _, page = console.request('GET', '/device?name=sw', token=console.session())
    assert 'Outdated observation' in page and console.m.endpoint_inventory()[0]['status'] == 'STALE'


@pytest.mark.parametrize('ts', [0, float('nan'), float('inf'), time.time() + 86400])
def test_invalid_timestamps_never_count_as_fresh(ts):
    assert not ni._fresh(ts, time.time(), 1800)


def test_routing_entry_and_uncollected_devices_are_visible_without_io(console, monkeypatch):
    _device(console.m, 'router', '192.0.2.1', platform='aruba_aoscx')
    _device(console.m, 'unsupported', '192.0.2.2')
    monkeypatch.setattr(console.m, '_connect', lambda *a: (_ for _ in ()).throw(AssertionError('GET contacted a device')))
    code, _, page = console.request('GET', '/topology?view=l3', token=console.session())
    assert code == 200 and 'Routing topology' in page and 'Route learning status' in page
    assert 'router' in page and 'Not collected' in page and 'Unsupported' in page
    assert 'Collect config + routes' in page and 'SNMP Poll' in page
    assert _nav_active('/topology?view=l3', '/topology?view=l3')
    assert not _nav_active('/topology', '/topology?view=l3')


def test_route_collect_button_reuses_cli_session_and_returns_to_topology(console, monkeypatch):
    _device(console.m, 'router', '192.0.2.1', platform='aruba_aoscx')
    tp = _EvidenceTransport('1/1/1 10.0.0.1/30 up up\n', 'C    10.0.0.0/30 is directly connected, 1/1/1\n')
    monkeypatch.setattr(console.m, '_connect', lambda dev: (tp, None))
    token = console.session()
    code, headers, _ = console.request('POST', '/collect', {'csrf':'ux-csrf','name':'router','back':'routes'}, token=token)
    assert code == 303 and headers['Location'] == '/topology?view=l3' and tp.closed
    _, _, page = console.request('GET', headers['Location'], token=token)
    assert 'Routes learned: 1' in page and '10.0.0.0/30' in page
    assert console.m.l3_collection_status('router')['status'] == 'OK'


def test_outdated_routes_are_explained_not_silently_lost(console):
    from netconfig.drivers import get_driver
    _device(console.m, 'router', '192.0.2.1', platform='aruba_aoscx')
    tp = _EvidenceTransport('1/1/1 10.0.0.1/30 up up\n', 'C    10.0.0.0/30 is directly connected, 1/1/1\n')
    console.m.l3_topology.collect_from_session(console.m.inv.get('router'), get_driver('aruba_aoscx'), tp)
    for table in ('l3_route_observations', 'l3_interface_observations', 'l3_collection_state'):
        console.m.db.conn.execute(f'UPDATE {table} SET observed_ts=1')
    console.m.db.conn.commit()
    _, _, page = console.request('GET', '/topology?view=l3', token=console.session())
    assert 'hidden; they were not deleted' in page and 'Stale' in page
    assert '10.0.0.0/30' not in str(console.m.l3_topology_graph()['edges'])
    _, _, old = console.request('GET', '/topology?view=l3&include_stale=1', token=console.session())
    assert '10.0.0.0/30' in old and 'STALE' in old


def test_viewer_can_read_routes_but_cannot_trigger_collection(console, monkeypatch):
    _device(console.m, 'router', '192.0.2.1', platform='aruba_aoscx')
    called = []
    monkeypatch.setattr(console.m, 'collect', lambda *a: called.append(1))
    token = console.session('viewer', 'reader')
    _, _, page = console.request('GET', '/topology?view=l3', token=token)
    assert '<button>Collect config + routes' not in page
    console.request('POST', '/collect', {'csrf':'ux-csrf','name':'router','back':'routes'}, token=token)
    assert not called


@pytest.mark.parametrize('rule', [{'scale':0}, {'scale':True}, {'minimum':10,'maximum':0}, {'warning_above':95,'critical_above':80}, {'warning_above':float('nan')}, {'warning_above':'80'}, {'unknown':1}, {'offset':10**400}])
def test_invalid_numeric_rules_fail_closed(rule):
    with pytest.raises(ValueError):
        validate_numeric(rule)


@pytest.mark.parametrize('value,status', [('0','OK'), ('79.9','OK'), ('80','WARNING'), ('95','CRITICAL'), ('99','CRITICAL'), ('-1','UNKNOWN'), ('101','UNKNOWN'), ('nan','UNKNOWN'), ('inf','UNKNOWN'), ('bad','UNKNOWN'), ('1e999999','UNKNOWN')])
def test_cpu_numeric_health_boundaries(value, status):
    profile = load_profile_file(PROFILE)
    result = normalize(profile, [{'oid':CPU, 'value':value}])[0]
    assert result['status'] == status and result['threshold']
    assert result['unit'] == '%'


def test_numeric_scaling_low_thresholds_and_zero_values():
    spec = {'numeric':validate_numeric({'scale':0.1,'offset':-1,'minimum':-1,'maximum':100,'warning_below':10,'critical_below':5})}
    assert reading(spec, '60', 'OK')[:2] == ('5', 'CRITICAL')
    assert reading(spec, '110', 'OK')[:2] == ('10', 'WARNING')
    assert reading(spec, '120', 'OK')[:2] == ('11', 'OK')
    result = normalize(load_profile_file(PROFILE), [{'oid':CPU,'value':0}])[0]
    assert result['value'] == '0' and result['status'] == 'OK'


def test_old_custom_cpu_profile_without_rules_is_unknown_not_ok():
    raw = json.loads(PROFILE.read_text())
    for metric in raw['metrics']:
        metric.pop('numeric', None)
    result = normalize(validate_profile(raw), [{'oid':CPU,'value':'99'}])[0]
    assert result['status'] == 'UNKNOWN' and 'No numeric health policy' in result['message']


def test_table_cpu_thresholds_and_existing_hardware_enum_both_work():
    profile = load_profile_file(PROFILE)
    rows = [{'oid':'1.3.6.1.4.1.12356.101.4.4.2.1.1.1','value':1},
            {'oid':'1.3.6.1.4.1.12356.101.4.4.2.1.2.1','value':99},
            {'oid':'1.3.6.1.4.1.12356.101.4.3.2.1.2.7','value':'fan'},
            {'oid':'1.3.6.1.4.1.12356.101.4.3.2.1.3.7','value':0},
            {'oid':'1.3.6.1.4.1.12356.101.4.3.2.1.4.7','value':1}]
    result = {r['sensor_type']:r for r in normalize(profile, rows)}
    assert result['vendor.fortigate.processor_cpu']['status'] == 'CRITICAL'
    assert result['vendor.fortigate.hardware']['status'] == 'CRITICAL'
    assert result['vendor.fortigate.hardware']['value'] == '0'


def test_cpu_degrade_and_recovery_enter_history_events_and_alerts(console):
    m = console.m
    seed_profile(m)
    save_cpu(m, 10)
    m._refresh_sensors_and_bridge_events('fg')
    save_cpu(m, 99)
    events = m._refresh_sensors_and_bridge_events('fg')
    cpu = [r for r in m.sensors.list(device='fg') if r['sensor_type']=='vendor.fortigate.cpu'][0]
    assert cpu['status']=='CRITICAL' and 'Critical >= 95' in cpu['threshold']
    assert any(r['event_type']=='vendor.fortigate.cpu.critical' for r in events)
    alerts = [a for a in m.alert_lifecycle.list() if 'vendor.fortigate.cpu' in a['event_type']]
    assert any(a['state']=='OPEN' for a in alerts)
    save_cpu(m, 0)
    events = m._refresh_sensors_and_bridge_events('fg')
    assert any(r['event_type']=='vendor.fortigate.cpu.recovered' for r in events)
    alerts = [a for a in m.alert_lifecycle.list() if 'vendor.fortigate.cpu' in a['event_type']]
    assert all(a['state']=='RESOLVED' for a in alerts)
    history = m.sensors.history_for(SensorEngine.sensor_key('vendor.fortigate.cpu','fg',''))
    assert [r['status'] for r in history['observations']][:3] == ['OK','CRITICAL','OK']


def test_vendor_ui_shows_health_rules_and_same_device_history(console, monkeypatch):
    m = console.m
    profile = seed_profile(m)
    save_cpu(m, 99)
    m.sensors.refresh_vendor_profile('fg', profile)
    monkeypatch.setattr(m, 'snmp_poll', lambda *a,**kw: (_ for _ in ()).throw(AssertionError('GET polled device')))
    key = SensorEngine.sensor_key('vendor.fortigate.cpu','fg','')
    url = '/snmp?' + urllib.parse.urlencode({'device':'fg','measurement':key})
    code, _, page = console.request('GET', url, token=console.session())
    assert code==200 and 'CPU usage' in page and 'CRITICAL' in page and 'Critical &gt;= 95' in page
    assert 'Measurement history' in page and '99 %' in page and 'Health rule' in page
    code, _, bad = console.request('GET', '/snmp?device=fg&measurement=another-device', token=console.session())
    assert code==200 and 'not in the displayed device profile' in bad


def test_unmatched_mib_profile_explains_missing_semantics(console):
    _device(console.m, 'linux', '192.0.2.3', snmp_version='v2c')
    console.m.inv.set_facts('linux', reachable=True, sysname='Linux', sysdescr='AlmaLinux', uptime='1d',
                            sysobjectid='1.3.6.1.4.1.8072.3.2.10', contact='', location='', error='')
    code, _, page = console.request('GET', '/snmp?device=linux', token=console.session())
    assert code==200 and 'No monitoring profile matches' in page and 'do not automatically define CPU' in page


def test_structured_profile_is_not_silently_bypassed_for_route_learning(console):
    _device(console.m, 'router', '192.0.2.1', platform='aruba_aoscx')
    console.m.protocol_profiles.set('router', 'gnmi', path='/')
    status = console.m.l3_collection_status('router')
    assert status['supports_cli_collection'] and not status['route_collection_available']
    _, _, page = console.request('GET', '/topology?view=l3', token=console.session())
    assert 'does not learn CLI routes' in page and '<button>Collect config + routes' not in page
