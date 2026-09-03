from types import SimpleNamespace
from netconfig import digest

class Store:
    def drift(self,name): return {'baselined':True,'drifted':name=='sw2'}
    def current(self,name): return 'service password-encryption\nno ip http server\n'
class Inv:
    def all(self): return [{'name':'sw1','platform':'cisco_ios','device_type':'network'},{'name':'sw2','platform':'cisco_ios','device_type':'network'}]

def test_digest_reports_drift(monkeypatch):
    m=SimpleNamespace(inv=Inv(),store=Store())
    r=digest.build(m)
    assert r['drifted']==['sw2']
    assert 'Drifted: 1' in r['body']
