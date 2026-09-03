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
    return "%d.%d.%d.%d" % ((v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)


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
