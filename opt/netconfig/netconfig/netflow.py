"""Zero-dependency NetFlow collector (v5 fully, v9 template-based).

A small UDP listener that receives NetFlow export packets from network devices,
parses flow records, and keeps a bounded in-memory ring of recent flows per
exporter (keyed by the exporter's source IP, which maps to a device host).

The receiver uses only the Python standard library. Optional 24-hour PostgreSQL
history is written by a separate bounded background worker. IPFIX (v10) is not
decoded; unknown versions are counted and ignored.
"""
import ipaddress
import queue
import socket
import struct
import threading
import time
from collections import deque, defaultdict

_PROTO = {1: "ICMP", 2: "IGMP", 6: "TCP", 17: "UDP", 47: "GRE", 50: "ESP",
          51: "AH", 58: "ICMPv6", 89: "OSPF", 132: "SCTP"}


def proto_name(n):
    return _PROTO.get(n, str(n))


def _ip(v):
    return f"{(v >> 24) & 0xFF}.{(v >> 16) & 0xFF}.{(v >> 8) & 0xFF}.{v & 0xFF}"


# v9 field type -> (our key, length-agnostic reader)
_V9_FIELDS = {
    1: "bytes",       # IN_BYTES
    2: "packets",     # IN_PKTS
    4: "proto",       # PROTOCOL
    7: "sport",       # L4_SRC_PORT
    8: "src",         # IPV4_SRC_ADDR
    11: "dport",      # L4_DST_PORT
    12: "dst",        # IPV4_DST_ADDR
    27: "src",        # IPV6_SRC_ADDR
    28: "dst",        # IPV6_DST_ADDR
}


def _int(b):
    return int.from_bytes(b, "big")


def _addr(raw):
    """Render a 4-byte IPv4 or 16-byte IPv6 address field; '' otherwise."""
    if len(raw) == 4:
        return _ip(_int(raw))
    if len(raw) == 16:
        return str(ipaddress.IPv6Address(bytes(raw)))
    return ""


class NetflowParser:
    """Parses packets. Holds v9 templates per (exporter, source_id, template_id)."""

    def __init__(self):
        self.templates = {}

    def parse(self, data, exporter, now=None):
        now = now or time.time()
        if len(data) < 2:
            return []
        version = struct.unpack(">H", data[:2])[0]
        if version == 5:
            return self._v5(data, exporter, now)
        if version == 9:
            return self._v9(data, exporter, now)
        return []  # IPFIX/other: ignored for now

    # ---- NetFlow v5: fixed 24-byte header + 48-byte records ----
    def _v5(self, data, exporter, now):
        if len(data) < 24:
            return []
        count = struct.unpack(">H", data[2:4])[0]
        out = []
        off = 24
        for _ in range(count):
            if off + 48 > len(data):
                break
            r = data[off:off + 48]
            src, dst = struct.unpack(">II", r[0:8])
            d_pkts, d_oct = struct.unpack(">II", r[16:24])
            sport, dport = struct.unpack(">HH", r[32:36])
            prot = r[38]
            out.append({"ts": now, "exporter": exporter, "src": _ip(src), "dst": _ip(dst),
                        "sport": sport, "dport": dport, "proto": proto_name(prot),
                        "packets": d_pkts, "bytes": d_oct})
            off += 48
        return out

    # ---- NetFlow v9: template-based ----
    def _v9(self, data, exporter, now):
        if len(data) < 20:
            return []
        count = struct.unpack(">H", data[2:4])[0]
        source_id = struct.unpack(">I", data[16:20])[0]
        out = []
        off = 20
        seen = 0
        while off + 4 <= len(data) and seen < count:
            fsid, length = struct.unpack(">HH", data[off:off + 4])
            if length < 4 or off + length > len(data):
                break
            body = data[off + 4:off + length]
            if fsid == 0:               # template flowset
                self._v9_templates(body, exporter, source_id)
            elif fsid == 1:             # options template - skip
                pass
            elif fsid >= 256:           # data flowset
                key = (exporter, source_id, fsid)
                tmpl = self.templates.get(key)
                if tmpl:
                    out.extend(self._v9_records(body, tmpl, exporter, now))
                    seen += len(out)
            off += length
        return out

    def _v9_templates(self, body, exporter, source_id):
        o = 0
        while o + 4 <= len(body):
            tid, fcount = struct.unpack(">HH", body[o:o + 4])
            o += 4
            fields = []
            for _ in range(fcount):
                if o + 4 > len(body):
                    break
                ftype, flen = struct.unpack(">HH", body[o:o + 4])
                fields.append((ftype, flen))
                o += 4
            if fields:
                self.templates[(exporter, source_id, tid)] = fields

    def _v9_records(self, body, tmpl, exporter, now):
        rec_len = sum(flen for _, flen in tmpl)
        if rec_len == 0:
            return []
        out = []
        o = 0
        while o + rec_len <= len(body):
            rec = {"ts": now, "exporter": exporter, "src": "", "dst": "",
                   "sport": 0, "dport": 0, "proto": "", "packets": 0, "bytes": 0}
            p = o
            for ftype, flen in tmpl:
                raw = body[p:p + flen]
                p += flen
                key = _V9_FIELDS.get(ftype)
                if not key:
                    continue
                if key in ("src", "dst"):
                    addr = _addr(raw)
                    # A template may carry both IPv4 and IPv6 address fields;
                    # the unused family is all-zero and must not overwrite.
                    if addr and (not rec[key] or any(raw)):
                        rec[key] = addr
                elif key == "proto":
                    rec[key] = proto_name(_int(raw))
                else:
                    rec[key] = _int(raw)
            out.append(rec)
            o += rec_len
        return out


def summarize_flows(flows, limit=8):
    """Return FortiView-style bounded summaries from already-collected flows."""
    flows = list(flows or [])
    limit = max(1, min(int(limit), 20))
    total_bytes = sum(max(0, int(f.get("bytes") or 0)) for f in flows)
    total_packets = sum(max(0, int(f.get("packets") or 0)) for f in flows)

    def aggregate(key_fn, label_fn=None):
        buckets = {}
        for f in flows:
            key = key_fn(f)
            if key in (None, "", ("", "")):
                continue
            item = buckets.setdefault(key, {"bytes": 0, "packets": 0, "flows": 0})
            item["bytes"] += max(0, int(f.get("bytes") or 0))
            item["packets"] += max(0, int(f.get("packets") or 0))
            item["flows"] += 1
        rows = []
        for key, values in buckets.items():
            label = label_fn(key) if label_fn else str(key)
            rows.append({"key": key, "label": label, **values,
                         "byte_share": (values["bytes"] / total_bytes) if total_bytes else 0.0})
        rows.sort(key=lambda x: (x["bytes"], x["packets"], x["flows"]), reverse=True)
        return rows[:limit]

    top_sources = aggregate(lambda f: f.get("src"))
    top_destinations = aggregate(lambda f: f.get("dst"))
    protocols = aggregate(lambda f: f.get("proto") or "UNKNOWN")
    top_ports = aggregate(lambda f: (str(f.get("proto") or "UNKNOWN"), int(f.get("dport") or 0)),
                          lambda k: f"{k[0]}/{k[1]}" if k[1] else str(k[0]))
    conversations = aggregate(
        lambda f: (str(f.get("src") or ""), str(f.get("dst") or ""),
                   str(f.get("proto") or "UNKNOWN"), int(f.get("dport") or 0)),
        lambda k: f"{k[0]} → {k[1]} {k[2]}/{k[3]}" if k[3] else f"{k[0]} → {k[1]} {k[2]}")

    insights = []
    if top_sources and total_bytes:
        lead = top_sources[0]
        insights.append(f'Top source {lead["label"]} accounts for {lead["byte_share"]*100:.0f}% of observed bytes.')
    if protocols and total_bytes:
        lead = protocols[0]
        insights.append(f'{lead["label"]} is the largest protocol by bytes ({lead["byte_share"]*100:.0f}%).')
    if top_ports:
        lead = top_ports[0]
        insights.append(f'Most observed destination traffic is {lead["label"]} ({lead["flows"]} flow records).')
    if not flows:
        insights.append("No recent flow records are available for this exporter.")

    times = [float(f.get("ts") or 0) for f in flows if f.get("ts")]
    return {
        "flow_count": len(flows), "total_bytes": total_bytes, "total_packets": total_packets,
        "unique_sources": len({f.get("src") for f in flows if f.get("src")}),
        "unique_destinations": len({f.get("dst") for f in flows if f.get("dst")}),
        "first_ts": min(times) if times else None, "last_ts": max(times) if times else None,
        "top_sources": top_sources, "top_destinations": top_destinations,
        "protocols": protocols, "top_ports": top_ports, "conversations": conversations,
        "insights": insights,
    }


class Collector:
    """UDP NetFlow collector. Keeps a bounded ring of recent flows per exporter."""

    def __init__(self, bind="0.0.0.0", port=2055, max_flows=500, history=None):
        self.history = history
        self.bind = bind
        self.port = int(port)
        self.max_flows = int(max_flows)
        self._parser = NetflowParser()
        self._flows = defaultdict(lambda: deque(maxlen=self.max_flows))
        self._counts = defaultdict(int)
        self._sock = None
        self._thread = None
        self._running = False
        self._lock = threading.Lock()
        self.started_at = None
        self.last_error = None
        self.total_packets = 0
        self.total_flows = 0

    def start(self):
        if self._running:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((self.bind, self.port))
        except OSError as e:
            self.last_error = str(e)
            s.close()
            raise
        s.settimeout(0.5)
        self._sock = s
        self._running = True
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        if self.history is not None:
            self.history.start()

    def _loop(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            exporter = addr[0]
            try:
                flows = self._parser.parse(data, exporter)
            except Exception:
                continue
            with self._lock:
                self.total_packets += 1
                self._counts[exporter] += 1
                if flows:
                    self.total_flows += len(flows)
                    self._flows[exporter].extend(flows)
            if flows and self.history is not None:
                self.history.submit(flows)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self.history is not None:
            self.history.stop()

    def flows_for(self, exporter_ip, limit=100):
        with self._lock:
            fl = list(self._flows.get(exporter_ip, ()))
        return list(reversed(fl))[:limit]

    def packet_count(self, exporter_ip):
        with self._lock:
            return self._counts.get(exporter_ip, 0)

    def exporters(self):
        with self._lock:
            return dict(self._counts)

    def status(self):
        return {"running": self._running, "port": self.port, "bind": self.bind,
                "started_at": self.started_at, "total_packets": self.total_packets,
                "total_flows": self.total_flows, "exporters": len(self._counts),
                "last_error": self.last_error}


# ---------------------------------------------------------------------------
# Direction-aware traffic analytics (FortiView-style views over the flow ring)
# ---------------------------------------------------------------------------
#
# NetFlow v5/v9 records are unidirectional and carry no application identity,
# so names here are PORT-BASED service labels, not DPI application detection.

def _ports(proto, ports, name):
    return {(proto, p): name for p in ports}


_SERVICES = {}
for _proto in ("TCP", "UDP"):
    _SERVICES.update(_ports(_proto, (53,), "DNS"))
    _SERVICES.update(_ports(_proto, (3478, 3479, 5349), "STUN/TURN"))
    _SERVICES.update(_ports(_proto, (5060,), "SIP"))
    _SERVICES.update(_ports(_proto, range(6881, 6890), "BitTorrent"))
    _SERVICES.update(_ports(_proto, (51413,), "BitTorrent"))
_SERVICES.update({
    ("TCP", 80): "HTTP", ("TCP", 443): "HTTPS", ("UDP", 443): "QUIC",
    ("TCP", 8080): "HTTP-alt", ("TCP", 8443): "HTTPS-alt", ("TCP", 9443): "HTTPS-alt",
    ("TCP", 853): "DNS over TLS", ("UDP", 853): "DNS over QUIC", ("UDP", 5353): "mDNS",
    ("UDP", 123): "NTP", ("UDP", 67): "DHCP", ("UDP", 68): "DHCP",
    ("UDP", 546): "DHCPv6", ("UDP", 547): "DHCPv6", ("UDP", 1900): "SSDP",
    ("TCP", 22): "SSH", ("TCP", 23): "Telnet", ("TCP", 21): "FTP", ("TCP", 3389): "RDP",
    ("TCP", 445): "SMB", ("TCP", 139): "NetBIOS", ("UDP", 137): "NetBIOS", ("UDP", 138): "NetBIOS",
    ("TCP", 25): "SMTP", ("TCP", 465): "SMTPS", ("TCP", 587): "SMTP submission",
    ("TCP", 143): "IMAP", ("TCP", 993): "IMAPS", ("TCP", 110): "POP3", ("TCP", 995): "POP3S",
    ("TCP", 5223): "Apple Push", ("TCP", 5228): "Google Push", ("TCP", 5061): "SIP TLS",
    ("UDP", 500): "IPsec IKE", ("UDP", 4500): "IPsec NAT-T", ("UDP", 1194): "OpenVPN",
    ("TCP", 1194): "OpenVPN", ("UDP", 51820): "WireGuard",
    ("UDP", 161): "SNMP", ("UDP", 162): "SNMP trap", ("UDP", 514): "Syslog",
    ("UDP", 2055): "NetFlow", ("UDP", 4739): "IPFIX", ("TCP", 179): "BGP",
    ("TCP", 1883): "MQTT", ("TCP", 8883): "MQTT over TLS", ("TCP", 554): "RTSP",
    ("TCP", 3306): "MySQL", ("TCP", 5432): "PostgreSQL", ("TCP", 1433): "MS SQL",
    ("TCP", 6379): "Redis", ("TCP", 8291): "Winbox", ("TCP", 3128): "HTTP proxy",
})
_PORTLESS = {"ICMP", "ICMPv6", "GRE", "ESP", "AH", "OSPF", "IGMP"}
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def service_for(proto, sport, dport):
    """Return (name, port, server_side) for one flow record.

    server_side is "dst" when the destination port is the service port, else
    "src" (a reply record). Ephemeral client ports are never used as labels.
    """
    proto = str(proto or "").upper() or "UNKNOWN"
    sport, dport = int(sport or 0), int(dport or 0)
    if proto in _PORTLESS or (not sport and not dport):
        return proto, 0, "dst"
    known_d, known_s = (proto, dport) in _SERVICES, (proto, sport) in _SERVICES
    if known_d and not known_s:
        port, side = dport, "dst"
    elif known_s and not known_d:
        port, side = sport, "src"
    elif (known_d and known_s) or min(sport, dport) >= 1024:
        # Both well-known (e.g. DNS 53<->53) or both high: the lower port is
        # the service; the higher one is the client's ephemeral port.
        port, side = (dport, "dst") if dport <= sport else (sport, "src")
    elif dport < 1024:
        port, side = dport, "dst"
    else:
        port, side = sport, "src"
    return _SERVICES.get((proto, port), f"{proto}/{port}"), port, side


def ip_scope(ip):
    """private | public | multicast | loopback | unknown (for labelling)."""
    try:
        addr = ipaddress.ip_address(str(ip))
    except ValueError:
        return "unknown"
    if addr.is_loopback:
        return "loopback"
    if addr.is_multicast or str(addr) == "255.255.255.255":
        return "multicast"
    if addr.is_private or addr.is_link_local or (addr.version == 4 and addr in _CGNAT):
        return "private"
    return "public"


def analyze_traffic(flows, *, window_seconds=3600, now=None, bucket_seconds=300,
                    local_ips=(), query="", limit=50):
    """Direction-aware Sources / Destinations / Services / Conversations.

    A host is "local" when its address is private/CGNAT/link-local or it is a
    known managed/ARP host (``local_ips``). Per local host, bytes it sent and
    received are tracked separately. When both ends are local (or both remote)
    the client side, i.e. the side NOT using the service port, is the source.
    Sessions are unique client/server 5-tuples, so both directions and repeated
    active-timeout records of one conversation count once.
    """
    now = time.time() if now is None else float(now)
    window_seconds = max(60, int(window_seconds or 3600))
    bucket_seconds = max(10, int(bucket_seconds or 300))
    limit = max(1, int(limit or 50))
    known = {str(x) for x in (local_ips or ()) if x}
    needle = str(query or "").strip().lower()
    scope_cache = {}

    def is_local(ip):
        if ip in known:
            return True
        sc = scope_cache.get(ip)
        if sc is None:
            sc = scope_cache[ip] = ip_scope(ip)
        return sc in ("private", "loopback")

    def bucket():
        return {"sent": 0, "received": 0, "packets": 0, "sessions": set(),
                "services": defaultdict(int), "peers": set()}

    sources = defaultdict(bucket)
    dests = defaultdict(bucket)
    services = defaultdict(lambda: {"bytes": 0, "packets": 0, "sessions": set(),
                                    "sources": set(), "destinations": set(),
                                    "labels": defaultdict(int)})
    convs = defaultdict(lambda: {"sent": 0, "received": 0, "sessions": set()})
    trend = defaultdict(int)
    first_ts = None
    total_b = total_p = records = 0
    all_sessions = set()

    for f in flows or ():
        src, dst = str(f.get("src") or ""), str(f.get("dst") or "")
        if not src or not dst:
            continue
        proto = str(f.get("proto") or "")
        sport, dport = int(f.get("sport") or 0), int(f.get("dport") or 0)
        b = max(0, int(f.get("bytes") or 0))
        p = max(0, int(f.get("packets") or 0))
        ts = float(f.get("ts") or now)
        name, port, side = service_for(proto, sport, dport)
        src_l, dst_l = is_local(src), is_local(dst)
        if src_l != dst_l:
            local, remote = (src, dst) if src_l else (dst, src)
        else:  # both local or both remote: client is the source
            local, remote = (src, dst) if side == "dst" else (dst, src)
        outbound = (src == local)
        if needle and needle not in local.lower() and needle not in remote.lower() \
                and needle not in name.lower():
            continue
        lport = sport if outbound else dport
        sess = (local, lport, remote, port, proto)
        records += 1
        total_b += b
        total_p += p
        first_ts = ts if first_ts is None else min(first_ts, ts)
        all_sessions.add(sess)
        trend[int(ts // bucket_seconds) * bucket_seconds] += b
        for agg, peer in ((sources[local], remote), (dests[remote], local)):
            agg["sent" if outbound else "received"] += b
            agg["packets"] += p
            agg["sessions"].add(sess)
            agg["services"][name] += b
            agg["peers"].add(peer)
        sv = services[name]
        sv["bytes"] += b
        sv["packets"] += p
        sv["sessions"].add(sess)
        sv["sources"].add(local)
        sv["destinations"].add(remote)
        sv["labels"][f"{proto}/{port}" if port else proto] += b
        cv = convs[(local, remote, name)]
        cv["sent" if outbound else "received"] += b
        cv["sessions"].add(sess)

    # Coverage is measured on the interval grid (first spanned interval through
    # the current one), so the average is the mean interval rate and can never
    # exceed the peak interval rate.
    if first_ts is None:
        first_bucket, coverage = None, window_seconds
    else:
        first_bucket = int(first_ts // bucket_seconds) * bucket_seconds
        coverage = int(now // bucket_seconds) * bucket_seconds + bucket_seconds - first_bucket

    def rate(nbytes):
        return nbytes * 8.0 / coverage if coverage else 0.0

    def top_services(counter, n=3):
        return [k for k, _ in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:n]]

    def host_rows(table):
        rows = []
        for ip, a in table.items():
            total = a["sent"] + a["received"]
            svc = top_services(a["services"])
            rows.append({"ip": ip, "scope": scope_cache.get(ip) or ip_scope(ip),
                         "sent": a["sent"], "received": a["received"], "bytes": total,
                         "packets": a["packets"], "sessions": len(a["sessions"]),
                         "avg_bps": rate(total), "services": svc,
                         "service_count": len(a["services"]), "peer_count": len(a["peers"])})
        rows.sort(key=lambda r: (r["bytes"], r["sessions"], r["ip"]), reverse=True)
        return rows[:limit]

    def port_label(labels):
        ranked = [k for k, _ in sorted(labels.items(), key=lambda kv: kv[1], reverse=True)]
        return ", ".join(ranked[:2]) + (f" +{len(ranked) - 2}" if len(ranked) > 2 else "")

    svc_rows = [{"name": k, "label": port_label(v["labels"]), "bytes": v["bytes"], "packets": v["packets"],
                 "sessions": len(v["sessions"]), "source_count": len(v["sources"]),
                 "destination_count": len(v["destinations"]), "avg_bps": rate(v["bytes"])}
                for k, v in services.items()]
    svc_rows.sort(key=lambda r: (r["bytes"], r["sessions"], r["name"]), reverse=True)
    conv_rows = [{"local": k[0], "remote": k[1], "service": k[2], "sent": v["sent"],
                  "received": v["received"], "bytes": v["sent"] + v["received"],
                  "sessions": len(v["sessions"]), "avg_bps": rate(v["sent"] + v["received"])}
                 for k, v in convs.items()]
    conv_rows.sort(key=lambda r: (r["bytes"], r["sessions"]), reverse=True)
    trend_rows = [{"ts": t, "bytes": trend[t], "bps": trend[t] * 8.0 / bucket_seconds}
                  for t in sorted(trend)]
    return {
        "window_seconds": window_seconds, "bucket_seconds": bucket_seconds,
        "coverage_seconds": coverage, "first_bucket_ts": first_bucket, "query": needle,
        "totals": {"bytes": total_b, "packets": total_p, "records": records,
                   "sessions": len(all_sessions), "avg_bps": rate(total_b),
                   "peak_bps": max((r["bps"] for r in trend_rows), default=0.0),
                   "sources": len(sources), "destinations": len(dests),
                   "services": len(services)},
        "sources": host_rows(sources), "destinations": host_rows(dests),
        "services": svc_rows[:limit], "conversations": conv_rows[:limit], "trend": trend_rows,
    }


class ReverseDnsCache:
    """Non-blocking, bounded reverse-DNS cache for traffic views.

    ``name(ip)`` never waits on DNS: a miss is queued for a small pool of daemon
    workers and the page simply shows the IP until a later refresh. Results
    (including failures) are cached with a TTL; queue and cache are bounded.
    """

    def __init__(self, ttl=3600, negative_ttl=900, max_entries=4096, max_queue=512, workers=3,
                 resolver=None):
        self.ttl, self.negative_ttl = ttl, negative_ttl
        self.max_entries = max_entries
        self._resolver = resolver or (lambda ip: socket.gethostbyaddr(ip)[0])
        self._cache = {}
        self._pending = set()
        self._queue = queue.Queue(maxsize=max_queue)
        self._lock = threading.Lock()
        self._workers = workers
        self._started = False

    def _ensure_started(self):
        if self._started:
            return
        self._started = True
        for _ in range(self._workers):
            threading.Thread(target=self._work, daemon=True).start()

    def name(self, ip, now=None):
        ip = str(ip or "")
        if not ip or ip_scope(ip) in ("multicast", "unknown"):
            return ""
        now = time.time() if now is None else now
        with self._lock:
            hit = self._cache.get(ip)
            if hit and hit[1] > now:
                return hit[0]
            if ip in self._pending:
                return ""
            try:
                self._queue.put_nowait(ip)
            except queue.Full:
                return ""
            self._pending.add(ip)
        self._ensure_started()
        return ""

    def _work(self):
        while True:
            ip = self._queue.get()
            try:
                name = str(self._resolver(ip) or "").rstrip(".")
            except Exception:
                name = ""
            if name == ip:
                name = ""
            expires = time.time() + (self.ttl if name else self.negative_ttl)
            with self._lock:
                self._pending.discard(ip)
                if len(self._cache) >= self.max_entries:
                    for old in sorted(self._cache, key=lambda k: self._cache[k][1])[:self.max_entries // 10 or 1]:
                        self._cache.pop(old, None)
                self._cache[ip] = (name, expires)


REVERSE_DNS = ReverseDnsCache()
