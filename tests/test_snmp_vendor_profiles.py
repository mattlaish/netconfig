from pathlib import Path
import json, threading, time, http.client
import pytest
from netconfig.manager import Manager
from netconfig.vendor_profiles import load_profile_file, validate_profile
from netconfig.cli import build_parser
import netconfig.manager as mm
import netconfig.web as web
from netconfig.web import Console, _Server
ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'usr/share/netconfig/snmp-profiles/fortinet.fortigate.json'

def dev(m, name='fg1'):
    m.inv.upsert(name=name, host='192.0.2.207', port=22, platform='fortigate', device_type='network', secret_ref='', enable_ref='', use_key=False, legacy=False, scrub=True, enabled=True, tags=[], notes='', snmp_version='v2c', snmp_ref=None)
    return m.inv.get(name)

def mib(oid, v):
    return {'oid': oid, 'name': oid, 'value': str(v), 'mib_source': 'test'}

def test_profile_match_and_scope():
    p = load_profile_file(PROFILE)
    assert p.matches('1.3.6.1.4.1.12356.101.1')
    roots = {x['root'] for x in p.collections}
    assert '1.3.6.1.4.1.12356.101.5' not in roots and '1.3.6.1.4.1.12356.101.13' not in roots and (p.total_limit == 1568)

def test_fail_closed_schema():
    raw = json.loads(PROFILE.read_text())
    raw['shell'] = 'x'
    with pytest.raises(ValueError):
        validate_profile(raw)

def test_install_remove(tmp_path):
    m = Manager(str(tmp_path / 'h'))
    try:
        raw = json.loads(PROFILE.read_text())
        raw['version'] = '1.0.1'
        f = tmp_path / 'p.json'
        f.write_text(json.dumps(raw))
        p, target = m.vendor_profiles.install(f)
        assert p.version == '1.0.1' and Path(target).stat().st_mode & 511 == 416
        removed, _ = m.vendor_profiles.remove_runtime('fortinet.fortigate')
        assert removed and m.vendor_profiles.profiles['fortinet.fortigate'].version == '1.0.0'
    finally:
        m.close()

def test_bounded_profile_poll_and_generic_fallback(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / 'h'))
    d = dev(m)
    calls = []
    monkeypatch.setattr(mm._snmp, 'walk_subtree', lambda host, root, **kw: calls.append((root, kw['max_vars'])) or [(root + '.999', '1')])
    try:
        r = m._poll_vendor_mibs('fg1', d, {'sysobjectid': '1.3.6.1.4.1.12356.101.1'}, 'v2c', 'public', None, 161, force=True)
        assert r['profile'] == 'fortinet.fortigate' and len(calls) == 7 and (dict(calls)['1.3.6.1.4.1.12356.101.7.2'] == 512)
    finally:
        m.close()

def test_normalize_and_prune(tmp_path):
    m = Manager(str(tmp_path / 'h'))
    dev(m)
    p = m.vendor_profiles.profiles['fortinet.fortigate']
    rows = [
        mib('1.3.6.1.4.1.12356.101.4.1.3.0', 2),
        mib('1.3.6.1.4.1.12356.101.4.2.1.0', '93.07999'),
        mib('1.3.6.1.4.1.12356.101.4.3.2.1.2.7', 'CPU Temp'),
        mib('1.3.6.1.4.1.12356.101.4.3.2.1.3.7', '39.3'),
        mib('1.3.6.1.4.1.12356.101.4.3.2.1.4.7', 0),
        mib('1.3.6.1.4.1.12356.101.4.4.2.1.1.4', 4),
        mib('1.3.6.1.4.1.12356.101.4.4.2.1.2.4', 19),
        mib('1.3.6.1.4.1.12356.101.3.2.1.1.2.1', 'root'),
        mib('1.3.6.1.4.1.12356.101.3.2.1.1.7.1', 11325),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.2.1.1', 'eHR-UAT-VPN'),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.3.1.1', 'eHR-UAT-Tunnel.A'),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.4.1.1', '42.200.50.249'),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.6.1.1', '118.143.135.82'),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.18.1.1', 27857642),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.19.1.1', 11320098),
        mib('1.3.6.1.4.1.12356.101.12.2.2.1.20.1.1', 2),
    ]
    try:
        m.db.set_mib_values('fg1', rows, roots=7)
        m.sensors.refresh_vendor_profile('fg1', p)
        keys = {(r['sensor_type'], r['resource']): r for r in m.sensors.list(device='fg1', limit=2000)}
        assert keys['vendor.fortigate.cpu', '']['value'] == '2'
        assert keys['vendor.fortigate.hardware', 'CPU Temp']['status'] == 'OK'
        assert keys['vendor.fortigate.processor_cpu', 'processor-4']['value'] == '19'
        assert keys['vendor.fortigate.vdom_sessions', 'root']['value'] == '11325'
        assert keys['vendor.fortigate.security_db', 'av']['value'] == '93.07999'
        vpn = keys['vendor.fortigate.vpn_tunnel', 'eHR-UAT-VPN/eHR-UAT-Tunnel.A']
        assert vpn['value'] == 'up' and vpn['status'] == 'OK'
        assert '42.200.50.249' in vpn['message']
        m.db.set_mib_values('fg1', [mib('1.3.6.1.4.1.12356.101.4.1.3.0', 3)], roots=7)
        m.sensors.refresh_vendor_profile('fg1', p)
        assert {(r['sensor_type'], r['resource']) for r in m.sensors.list(device='fg1', limit=2000) if r['source'].startswith('vendor-profile:')} == {('vendor.fortigate.cpu', '')}
    finally:
        m.close()

def test_cli_and_grouped_sidebar():
    p = build_parser()
    assert p.parse_args(['snmp', 'profiles']).action == 'profiles'
    assert p.parse_args(['snmp', 'profile-install', 'x.json']).file == 'x.json'
    from netconfig.web_ui import render_sidebar_nav
    h = render_sidebar_nav([('Overview', [('/dashboard', 'Dashboard')]), ('Monitor', [('/alerts', 'Alerts')])], '/alerts')
    assert 'Overview' in h and 'Monitor' in h and ('class="active" href="/alerts"' in h)

def test_web_panel_no_io(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / 'h'))
    dev(m)
    m.inv.set_facts('fg1', reachable=True, sysname='FG', sysdescr='FortiGate', uptime='1d', sysobjectid='1.3.6.1.4.1.12356.101.1', contact='', location='', error='')
    m.db.set_mib_values('fg1', [mib('1.3.6.1.4.1.12356.101.4.1.3.0', 2)], roots=7)
    m.sensors.refresh_vendor_profile('fg1', m.vendor_profiles.profiles['fortinet.fortigate'])
    monkeypatch.setattr(mm._snmp, 'poll_system', lambda *a, **k: (_ for _ in ()).throw(AssertionError('io')))
    web._SESSIONS.clear()
    web._SESSIONS['s'] = {'username': 'u', 'role': 'admin', 'csrf': 'c', 'created': time.time()}
    Console.manager = m
    Console.tls_enabled = False
    srv = _Server(('127.0.0.1', 0), Console)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        c = http.client.HTTPConnection('127.0.0.1', srv.server_address[1], timeout=5)
        c.request('GET', '/snmp?device=fg1', headers={'Cookie': 'ncsid=s'})
        r = c.getresponse()
        body = r.read().decode()
        assert r.status == 200 and 'Vendor profile telemetry' in body and ('vendor.fortigate.cpu' in body)
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(5)
        m.close()
        web._SESSIONS.clear()

def test_packaging():
    spec = (ROOT / 'packaging/netconfig.spec').read_text()
    rb = (ROOT / 'tools/rpm-builder/rpm_builder.py').read_text()
    assert '%{_datadir}/netconfig/snmp-profiles' in spec and '/usr/share/netconfig/snmp-profiles' in rb
