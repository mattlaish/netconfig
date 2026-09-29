"""Zero-dependency NetFlow collector (v5 fully, v9 template-based).

A small UDP listener that receives NetFlow export packets from network devices,
parses flow records, and keeps a bounded in-memory ring of recent flows per
exporter (keyed by the exporter's source IP, which maps to a device host).

Only the Python standard library is used. IPFIX (v10) shares v9's structure and
can be added later; unknown versions are counted and ignored.
"""
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
}


def _int(b):
    return int.from_bytes(b, "big")


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
                    rec[key] = _ip(_int(raw)) if len(raw) == 4 else ""
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

    def __init__(self, bind="0.0.0.0", port=2055, max_flows=500):
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

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

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
