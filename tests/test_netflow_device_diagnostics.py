"""Device-level NetFlow section turns received-but-unmatched flows into
actionable diagnostics instead of a dead-end "no flows received" note.

Flows are matched to a device by the exporter's UDP source IP, which must equal
the device's Host/IP. When datagrams arrive from a different source IP, the
section now says so and lists the exporters actually sending, so the operator
can reconcile the device Host/IP (the common real-world NetFlow mismatch).
"""
from netconfig.web_ui import render_netflow_section


class _Settings(dict):
    pass


class _Manager:
    def __init__(self, enabled=True):
        self.settings = _Settings(netflow_enabled=enabled, netflow_port=2055,
                                  netflow_max_flows=500)


class _Handler:
    def __init__(self, enabled=True):
        self.manager = _Manager(enabled)

    @staticmethod
    def _human_bytes(v):
        return f"{int(v or 0)} B"


class _Collector:
    def __init__(self, flows_by_host=None, exporters=None, packets=None):
        self._flows = flows_by_host or {}
        self._exporters = exporters or {}
        self._packets = packets or {}

    def status(self):
        return {"port": 2055, "bind": "0.0.0.0"}

    def flows_for(self, host, limit=100):
        return list(self._flows.get(host, []))

    def packet_count(self, host):
        return self._packets.get(host, 0)

    def exporters(self):
        return dict(self._exporters)


_DEV = {"host": "192.0.2.10", "netflow": 1}


def test_flows_matching_device_host_render_summary():
    flows = [{"ts": 1.0, "src": "10.0.0.1", "dst": "10.0.0.2", "sport": 1,
              "dport": 443, "proto": "TCP", "packets": 5, "bytes": 4000}]
    col = _Collector(flows_by_host={"192.0.2.10": flows},
                     exporters={"192.0.2.10": 3}, packets={"192.0.2.10": 3})
    html = render_netflow_section(_Handler(), _DEV, col)
    assert "Top sources" in html
    assert "10.0.0.1" in html
    # no mismatch / empty note when flows are present
    assert "no datagrams came from this device" not in html.lower()


def test_exporter_ip_mismatch_is_surfaced():
    # datagrams arriving, but from a different source IP than the device host
    col = _Collector(flows_by_host={}, exporters={"198.51.100.7": 12},
                     packets={"192.0.2.10": 0})
    html = render_netflow_section(_Handler(), _DEV, col)
    assert "no datagrams came from this device" in html.lower()
    assert "198.51.100.7" in html          # the real exporter is listed
    assert "/traffic" in html               # pointed at the global view


def test_datagrams_received_but_no_decoded_flows():
    col = _Collector(flows_by_host={}, exporters={"192.0.2.10": 4},
                     packets={"192.0.2.10": 4})
    html = render_netflow_section(_Handler(), _DEV, col)
    assert "no flow records decoded yet" in html.lower()


def test_nothing_received_keeps_configuration_hint():
    col = _Collector(flows_by_host={}, exporters={}, packets={})
    html = render_netflow_section(_Handler(), _DEV, col)
    assert "no flows received yet" in html.lower()
    assert "udp/2055" in html
