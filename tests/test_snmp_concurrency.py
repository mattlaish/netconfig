import threading
import time

from netconfig.manager import Manager


class _Inv:
    def all(self):
        return [{"name": f"d{i}", "snmp_version": "v2c"} for i in range(6)]


def test_snmp_poll_all_uses_bounded_parallel_workers():
    m = Manager.__new__(Manager)
    m.inv = _Inv()
    m.settings = {"snmp_workers": 3}
    lock = threading.Lock()
    active = 0
    maximum = 0

    def poll(name, vendor_force=False):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return {"ok": True, "device": name}

    m.snmp_poll = poll
    result = Manager.snmp_poll_all(m)
    assert len(result) == 6
    assert 2 <= maximum <= 3
