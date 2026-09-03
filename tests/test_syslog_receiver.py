from types import SimpleNamespace
from netconfig import syslog_receiver

class DB:
    def __init__(self): self.events=[]; self.audits=[]
    def record_syslog(self, source, message): self.events.append((source,message))
    def audit(self,*args): self.audits.append(args)
class Manager:
    def __init__(self): self.db=DB(); self.count=0
    def device_by_host(self, host): return {"name":"sw1"} if host=="10.0.0.1" else None
    def collect(self, name): self.count += 1; return SimpleNamespace(message="changed")

def test_syslog_change_triggers_bounded_debounced_collect():
    m=Manager(); c=syslog_receiver.Collector(m, debounce_seconds=30)
    c._handle(100, "10.0.0.1", "%SYS-5-CONFIG_I: Configured from console")
    c._handle(101, "10.0.0.1", "%SYS-5-CONFIG_I: Configured from console")
    assert m.count == 1
    assert len(m.db.events) == 2

def test_non_change_does_not_collect():
    m=Manager(); c=syslog_receiver.Collector(m)
    c._handle(100, "10.0.0.1", "%LINK-3-UPDOWN: Interface Gi1/0/1 changed state")
    assert m.count == 0
