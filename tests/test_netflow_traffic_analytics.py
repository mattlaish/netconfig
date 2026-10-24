"""NetFlow traffic analytics and the FortiView-style /traffic views."""
import http.client
import ipaddress
import struct
import threading
import time

import pytest

from netconfig import netflow as nf
from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server


def _v9_packet(fields, record, template_id=256):
    tmpl = struct.pack(">HH", template_id, len(fields)) + b"".join(struct.pack(">HH", t, n) for t, n in fields)
    tset = struct.pack(">HH", 0, 4 + len(tmpl)) + tmpl
    dset = struct.pack(">HH", template_id, 4 + len(record)) + record
    header = struct.pack(">HHIIII", 9, 2, 0, 0, 1, 7)
    return header + tset + dset


def test_v9_ipv6_addresses_are_decoded():
    src, dst = ipaddress.IPv6Address("2001:db8::10"), ipaddress.IPv6Address("2606:4700::1111")
    fields = [(27, 16), (28, 16), (7, 2), (11, 2), (4, 1), (1, 4), (2, 4)]
    record = src.packed + dst.packed + struct.pack(">HHBII", 50000, 443, 6, 1500, 3)
    flows = nf.NetflowParser().parse(_v9_packet(fields, record), "192.0.2.1")
    assert flows and flows[0]["src"] == "2001:db8::10" and flows[0]["dst"] == "2606:4700::1111"
    assert flows[0]["dport"] == 443 and flows[0]["bytes"] == 1500


def test_v9_mixed_family_template_keeps_the_real_address():
    fields = [(8, 4), (27, 16), (12, 4), (28, 16), (4, 1)]
    record = (b"\0" * 4 + ipaddress.IPv6Address("2001:db8::1").packed
              + b"\0" * 4 + ipaddress.IPv6Address("2001:db8::2").packed + bytes([17]))
    flow = nf.NetflowParser().parse(_v9_packet(fields, record), "192.0.2.1")[0]
    assert (flow["src"], flow["dst"]) == ("2001:db8::1", "2001:db8::2")


@pytest.mark.parametrize("proto,sport,dport,name,side", [
    ("TCP", 43332, 443, "HTTPS", "dst"),
    ("TCP", 443, 43332, "HTTPS", "src"),        # reply record: never "TCP/43332"
    ("UDP", 52000, 443, "QUIC", "dst"),
    ("UDP", 40000, 6881, "BitTorrent", "dst"),
    ("UDP", 53, 53, "DNS", "dst"),
    ("UDP", 21290, 50000, "UDP/21290", "src"),  # unknown: lower port is the service
    ("ICMP", 0, 0, "ICMP", "dst"),
])
def test_service_detection_ignores_ephemeral_ports(proto, sport, dport, name, side):
    got = nf.service_for(proto, sport, dport)
    assert (got[0], got[2]) == (name, side)


def _pair(ts, local, remote, lport, rport, proto, up, down):
    return [
        {"ts": ts, "src": local, "dst": remote, "sport": lport, "dport": rport, "proto": proto, "packets": 1, "bytes": up},
        {"ts": ts, "src": remote, "dst": local, "sport": rport, "dport": lport, "proto": proto, "packets": 2, "bytes": down},
    ]


def test_analysis_is_direction_aware_and_merges_both_directions_into_one_session():
    now = 10_000.0
    flows = (_pair(now - 60, "192.168.1.10", "8.8.8.8", 50001, 443, "TCP", 1000, 9000)
             + _pair(now - 30, "192.168.1.10", "8.8.8.8", 50001, 443, "TCP", 500, 500)   # same session again
             + _pair(now - 20, "192.168.1.11", "1.1.1.1", 50002, 53, "UDP", 80, 120))
    a = nf.analyze_traffic(flows, window_seconds=3600, now=now, bucket_seconds=60)
    assert [r["ip"] for r in a["sources"]] == ["192.168.1.10", "192.168.1.11"]   # only local hosts
    top = a["sources"][0]
    assert (top["sent"], top["received"], top["sessions"]) == (1500, 9500, 1)
    assert top["services"] == ["HTTPS"]
    dest = {r["ip"]: r for r in a["destinations"]}
    assert dest["8.8.8.8"]["scope"] == "public" and dest["8.8.8.8"]["sent"] == 1500
    assert {s["name"] for s in a["services"]} == {"HTTPS", "DNS"}
    assert a["totals"]["sessions"] == 2 and a["totals"]["records"] == 6
    assert a["totals"]["peak_bps"] >= a["totals"]["avg_bps"] > 0


def test_lan_to_lan_traffic_uses_the_client_as_source_and_known_hosts_are_local():
    now = 5_000.0
    flows = _pair(now - 5, "10.0.0.5", "10.0.0.9", 51000, 22, "TCP", 100, 200)
    a = nf.analyze_traffic(flows, now=now)
    assert a["sources"][0]["ip"] == "10.0.0.5" and a["destinations"][0]["ip"] == "10.0.0.9"
    # A public address that is a known managed/ARP host counts as local.
    flows = _pair(now - 5, "203.0.113.7", "8.8.4.4", 51000, 443, "TCP", 100, 200)
    a = nf.analyze_traffic(flows, now=now, local_ips={"203.0.113.7"})
    assert a["sources"][0]["ip"] == "203.0.113.7"


def test_query_filters_by_address_or_service():
    now = 5_000.0
    flows = (_pair(now - 5, "192.168.1.10", "8.8.8.8", 51000, 443, "TCP", 100, 200)
             + _pair(now - 5, "192.168.1.11", "9.9.9.9", 51001, 6881, "UDP", 100, 200))
    assert [r["ip"] for r in nf.analyze_traffic(flows, now=now, query="bittorrent")["sources"]] == ["192.168.1.11"]
    assert [r["ip"] for r in nf.analyze_traffic(flows, now=now, query="8.8.8.8")["destinations"]] == ["8.8.8.8"]


def test_reverse_dns_cache_never_blocks_the_caller():
    gate = threading.Event()

    def slow(ip):
        gate.wait(2)
        return "dns.example"
    cache = nf.ReverseDnsCache(resolver=slow, workers=1)
    started = time.monotonic()
    assert cache.name("8.8.8.8") == ""            # miss: queued, returns at once
    assert time.monotonic() - started < 0.2
    gate.set()
    for _ in range(50):
        if cache.name("8.8.8.8"):
            break
        time.sleep(0.02)
    assert cache.name("8.8.8.8") == "dns.example"
    assert cache.name("224.0.0.251") == ""        # multicast is never looked up


class _Collector:
    def __init__(self, flows, max_flows=1000):
        self.max_flows = max_flows
        self._flows = {"192.0.2.1": [dict(f, exporter="192.0.2.1") for f in flows]}

    def exporters(self):
        return {k: len(v) for k, v in self._flows.items()}

    def flows_for(self, exporter, limit=100):
        return list(reversed(self._flows.get(exporter, [])))[:limit]

    def status(self):
        return {"running": True, "port": 2055, "exporters": len(self._flows)}

    def packet_count(self, exporter):
        return len(self._flows.get(exporter, []))


@pytest.fixture
def traffic_console(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="fgt", host="192.0.2.1", port=22, platform="generic", device_type="network",
                 secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True, enabled=True,
                 tags=[], notes="", snmp_version="", snmp_ref=None, netflow=1)
    m.settings["netflow_enabled"] = True
    now = time.time()
    flows = (_pair(now - 60, "192.168.1.10", "8.8.8.8", 50001, 443, "TCP", 1000, 9000)
             + _pair(now - 30, "192.168.1.11", "1.1.1.1", 50002, 6881, "UDP", 200, 300))
    web._SESSIONS.clear()
    web._SESSIONS["tr"] = {"username": "viewer1", "role": "viewer", "csrf": "c", "created": 1.0}
    Console.manager = m
    Console.netflow = _Collector(flows)
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    saved = dict(nf.REVERSE_DNS._cache)

    def get(path):
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", path, headers={"Cookie": "ncsid=tr"})
        res = conn.getresponse()
        body = res.read().decode()
        conn.close()
        return res.status, body
    yield m, get
    nf.REVERSE_DNS._cache.clear()
    nf.REVERSE_DNS._cache.update(saved)
    server.shutdown(); server.server_close(); thread.join(timeout=5)
    Console.netflow = None
    web._SESSIONS.clear()
    m.close()


def test_traffic_views_render_for_viewer(traffic_console):
    _m, get = traffic_console
    for view in ("sources", "destinations", "services", "conversations", "exporters"):
        status, body = get(f"/traffic?view={view}")
        assert status == 200, view
        assert "Records are held in memory" in body
        assert 'class="nf-views"' in body and "Throughput" in body
    status, body = get("/traffic?view=sources")
    assert "192.168.1.10" in body and "Bytes (sent / received)" in body
    assert "8.8.8.8" not in body.split("Top sources")[1].split("</table>")[0]  # remote hosts are not sources
    status, body = get("/traffic?view=services")
    assert "HTTPS" in body and "BitTorrent" in body and "TCP/50001" not in body
    status, body = get("/traffic?view=exporters")
    assert "fgt" in body                     # exporter mapped to its inventory device


def test_traffic_drill_down_and_bad_parameters(traffic_console):
    _m, get = traffic_console
    status, body = get("/traffic?view=destinations&q=192.168.1.11")
    assert status == 200 and "Filtered: matching" in body
    table = body.split("Top destinations")[1]
    assert "1.1.1.1" in table and "8.8.8.8" not in table.split("</table>")[0]
    status, body = get("/traffic?view=bogus&window=abc&exporter=%3Cx%3E")
    assert status == 200 and "<x>" not in body


def test_traffic_escapes_untrusted_reverse_dns_names(traffic_console):
    m, get = traffic_console
    m.settings["netflow_resolve_names"] = True
    hostile = '<img src=x onerror=alert(1)>'
    nf.REVERSE_DNS._cache["8.8.8.8"] = (hostile, time.time() + 3600)
    status, body = get("/traffic?view=destinations")
    assert status == 200
    assert hostile not in body and "&lt;img src=x onerror=alert(1)&gt;" in body


def test_traffic_warns_when_the_flow_ring_limits_coverage(traffic_console):
    _m, get = traffic_console
    Console.netflow.max_flows = 2                    # ring "full" with only recent records
    status, body = get("/traffic")
    assert status == 200 and "Flow memory is full" in body


def test_traffic_page_uses_saved_history_and_reports_partial_results(traffic_console):
    _m, get = traffic_console
    now = time.time()

    class History:
        def read_window(self, since, until, exporter=None):
            flows = [dict(f, exporter="192.0.2.1") for f in
                     _pair(now - 7200, "10.4.5.6", "8.8.4.4", 51000, 443, "TCP", 100, 900)]
            return {"flows": [f for f in flows if since <= f["ts"] <= until],
                    "source": "postgres", "truncated": True, "query_limit": 200000,
                    "status": {"pending": 2, "written": 8}}

    Console.netflow.history = History()
    Console.netflow.max_flows = 2
    status, body = get("/traffic?window=86400")
    assert status == 200 and "10.4.5.6" in body
    assert "PostgreSQL flow history" in body and "Results are incomplete" in body
    assert "Flow memory is full" not in body and "Records are held in memory" not in body
    status, body = get("/traffic?window=3600")
    assert status == 200 and "10.4.5.6" not in body


def test_device_page_netflow_section_uses_the_analytics_views(traffic_console):
    _m, get = traffic_console
    status, body = get("/device?name=fgt")
    assert status == 200
    assert "NetFlow traffic" in body and "Top sources" in body and "Open in Traffic Analytics" in body


def test_throughput_panel_always_renders_with_a_reason_when_no_chart_is_possible():
    from netconfig.web_traffic import throughput_chart
    now = 1_000_000.0
    empty = nf.analyze_traffic([], now=now, bucket_seconds=120)
    assert "No traffic was recorded" in throughput_chart(empty, now)
    one = nf.analyze_traffic(_pair(now - 5, "192.168.1.10", "8.8.8.8", 50001, 443, "TCP", 10, 20),
                             now=now, bucket_seconds=120)
    html = throughput_chart(one, now)
    assert "Throughput" in html and "current 2 min interval" in html and "<svg" not in html
    two = nf.analyze_traffic(_pair(now - 300, "192.168.1.10", "8.8.8.8", 50001, 443, "TCP", 10, 20)
                             + _pair(now - 5, "192.168.1.10", "8.8.8.8", 50002, 443, "TCP", 10, 20),
                             now=now, bucket_seconds=120)
    assert 'class="nf-chart"' in throughput_chart(two, now)
