"""
snmp.py -- SNMP client for inventory enrichment, pure stdlib.

Purpose: SSH collection tells you a device's *config*; SNMP tells you cheaply what
a device *is* and whether it's alive -- sysName, sysDescr, sysObjectID, uptime,
contact, location. NetConfig uses it to enrich the inventory and flag
unreachable devices, not to pull configs (SNMP is a poor fit for that).

What's implemented, all in stdlib (socket + hashlib + hmac + the local AES):
  * A minimal BER/ASN.1 encoder+decoder (the subset SNMP needs).
  * SNMP v2c GET.
  * SNMP v3 (USM): engine discovery, then noAuthNoPriv / authNoPriv (HMAC-MD5 or
    HMAC-SHA) / authPriv (AES-128-CFB, RFC 3826), with RFC 3414 key localization.

Security note for the hospital estate: v2c sends its community string in
cleartext, so prefer v3 authPriv on any network where that matters. v2c remains
available as a fallback for gear that can't do v3.
"""

import hashlib
import ipaddress
import hmac
import os
import socket
import struct
import binascii
import re
import sys
import time as _time
from contextlib import contextmanager
from contextvars import ContextVar

_DEBUG = int(os.environ.get("NETCONFIG_SNMP_DEBUG", "0") or 0)
_TRACE_CALLBACK = ContextVar("netconfig_snmp_trace_callback", default=None)

@contextmanager
def trace_capture(callback):
    """Attach a context-local metadata-only SNMP trace callback."""
    token = _TRACE_CALLBACK.set(callback)
    try:
        yield
    finally:
        _TRACE_CALLBACK.reset(token)

def _trace(event):
    callback = _TRACE_CALLBACK.get()
    if callback:
        try:
            callback(event)
        except Exception:
            pass


def set_debug(level):
    global _DEBUG
    _DEBUG = int(level)


def _dbg(level, msg):
    if _DEBUG >= level:
        sys.stderr.write("[snmp] " + msg + "\n")
        sys.stderr.flush()


def _hx(b, n=80):
    h = binascii.hexlify(b[:n]).decode()
    return h + ("..." if len(b) > n else "")

from . import aes

# ---- BER/ASN.1 ----------------------------------------------------------
# universal tags
INTEGER = 0x02
OCTET_STRING = 0x04
NULL = 0x05
OID = 0x06
SEQUENCE = 0x30
# application tags seen in responses
IPADDRESS = 0x40
COUNTER32 = 0x41
GAUGE32 = 0x42
TIMETICKS = 0x43
COUNTER64 = 0x46
NOSUCHOBJECT = 0x80
NOSUCHINSTANCE = 0x81
ENDOFMIBVIEW = 0x82
# PDU tags
GET_REQUEST = 0xA0
GET_NEXT = 0xA1
GET_RESPONSE = 0xA2
REPORT = 0xA8


class SNMPError(Exception):
    pass


def _enc_len(n):
    if n < 0x80:
        return bytes([n])
    b = []
    while n:
        b.insert(0, n & 0xFF)
        n >>= 8
    return bytes([0x80 | len(b)]) + bytes(b)


def _tlv(tag, value):
    return bytes([tag]) + _enc_len(len(value)) + value


def enc_int(n):
    if n == 0:
        return _tlv(INTEGER, b"\x00")
    neg = n < 0
    v = n if not neg else (~n)
    b = []
    while v:
        b.insert(0, v & 0xFF)
        v >>= 8
    if not b:
        b = [0]
    if not neg and (b[0] & 0x80):
        b.insert(0, 0)
    if neg:
        # two's complement
        val = n & ((1 << (8 * len(b))) - 1)
        b = list(val.to_bytes(len(b), "big"))
        if not (b[0] & 0x80):
            b.insert(0, 0xFF)
    return _tlv(INTEGER, bytes(b))


def enc_octet(b):
    if isinstance(b, str):
        b = b.encode()
    return _tlv(OCTET_STRING, b)


def enc_null():
    return _tlv(NULL, b"")


def enc_oid(oid):
    parts = [int(x) for x in oid.strip(".").split(".")]
    if len(parts) < 2:
        raise SNMPError("bad OID")
    first = 40 * parts[0] + parts[1]
    body = bytearray([first])
    for p in parts[2:]:
        if p < 0x80:
            body.append(p)
        else:
            chunk = []
            while p:
                chunk.insert(0, p & 0x7F)
                p >>= 7
            for i in range(len(chunk) - 1):
                chunk[i] |= 0x80
            body += bytes(chunk)
    return _tlv(OID, bytes(body))


def enc_seq(*chunks):
    return _tlv(SEQUENCE, b"".join(chunks))


def _read_len(data, i):
    first = data[i]
    i += 1
    if first < 0x80:
        return first, i
    n = first & 0x7F
    val = int.from_bytes(data[i:i + n], "big")
    return val, i + n


def _parse_oid(body):
    if not body:
        return ""
    first = body[0]
    parts = [first // 40, first % 40]
    val = 0
    for b in body[1:]:
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            parts.append(val)
            val = 0
    return "." + ".".join(str(p) for p in parts)


def decode(data, i=0):
    """Recursive TLV decode -> (tag, value, next_index). Constructed types
    return a list of children as value; primitives return python scalars/bytes."""
    tag = data[i]
    length, j = _read_len(data, i + 1)
    body = data[j:j + length]
    end = j + length
    if tag in (SEQUENCE, GET_REQUEST, GET_NEXT, GET_RESPONSE, REPORT):
        children = []
        k = 0
        while k < len(body):
            t, v, k = decode(body, k)
            children.append((t, v))
        return tag, children, end
    if tag == INTEGER or tag in (COUNTER32, GAUGE32, TIMETICKS, COUNTER64):
        return tag, int.from_bytes(body, "big"), end
    if tag == OID:
        return tag, _parse_oid(body), end
    if tag == OCTET_STRING:
        return tag, body, end
    if tag == IPADDRESS:
        return tag, ".".join(str(b) for b in body), end
    if tag == NULL or tag in (NOSUCHOBJECT, NOSUCHINSTANCE, ENDOFMIBVIEW):
        return tag, None, end
    return tag, body, end


# ---- common OIDs --------------------------------------------------------
SYS = {
    "sysDescr": ".1.3.6.1.2.1.1.1.0",
    "sysObjectID": ".1.3.6.1.2.1.1.2.0",
    "sysUpTime": ".1.3.6.1.2.1.1.3.0",
    "sysContact": ".1.3.6.1.2.1.1.4.0",
    "sysName": ".1.3.6.1.2.1.1.5.0",
    "sysLocation": ".1.3.6.1.2.1.1.6.0",
}


def _fmt_uptime(ticks):
    if ticks is None:
        return ""
    secs = ticks // 100
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{d}d {h}h {m}m {s}s"


# ---- v2c ----------------------------------------------------------------
def _build_get_pdu(request_id, oids, pdu_tag=GET_REQUEST):
    varbinds = enc_seq(*[enc_seq(enc_oid(o), enc_null()) for o in oids])
    return _tlv(pdu_tag,
                enc_int(request_id) + enc_int(0) + enc_int(0) + varbinds)


def _extract_varbinds(pdu_children):
    """pdu_children: decoded list; find the varbind sequence and return
    [(oid, value)]."""
    # PDU: [req_id, err_status, err_index, varbind-list]
    vb = pdu_children[3][1]
    out = []
    for _, entry in vb:
        oid = entry[0][1]
        val = entry[1][1]
        out.append((oid, val))
    return out


def _udp_exchange(host, port, payload, timeout, retries=1):
    last = None
    for attempt in range(retries + 1):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        try:
            _dbg(1, f"send {len(payload)}B -> {host}:{port} (timeout {timeout}s, attempt {attempt + 1})")
            _dbg(2, f"  tx {_hx(payload)}")
            t0 = _time.time()
            s.sendto(payload, (host, port))
            data, _ = s.recvfrom(65535)
            elapsed = (_time.time() - t0) * 1000
            _dbg(1, f"recv {len(data)}B in {elapsed:.0f}ms")
            _dbg(2, f"  rx {_hx(data)}")
            _trace({"event_type": "udp_exchange", "operation": "SNMP request", "status": "ok",
                    "duration_ms": elapsed, "tx_bytes": len(payload), "rx_bytes": len(data),
                    "host": host, "port": port, "attempt": attempt + 1})
            return data
        except socket.timeout as e:
            last = e
            elapsed = (_time.time() - t0) * 1000
            _trace({"event_type": "udp_exchange", "operation": "SNMP request", "status": "timeout",
                    "duration_ms": elapsed, "tx_bytes": len(payload), "rx_bytes": 0,
                    "host": host, "port": port, "attempt": attempt + 1})
            _dbg(1, f"timeout after {timeout}s")
        finally:
            s.close()
    raise SNMPError(f"no SNMP response from {host}:{port} ({last})")


def get_v3(host, params, oids, port=161, timeout=2.0, retries=1):
    engine = _engine_for(params, host, port, timeout, retries)
    return _v3_request(host, params, oids, GET_REQUEST, engine, port, timeout, retries)


def getnext_v3(host, params, oids, engine, port=161, timeout=2.0, retries=1):
    return _v3_request(host, params, oids, GET_NEXT, engine, port, timeout, retries)


def getnext_v2c(host, community, oids, port=161, timeout=2.0, retries=1):
    rid = struct.unpack(">I", os.urandom(4))[0] & 0x7FFFFFFF
    pdu = _build_get_pdu(rid, oids, GET_NEXT)
    msg = enc_seq(enc_int(1), enc_octet(community), pdu)
    data = _udp_exchange(host, port, msg, timeout, retries)
    _, children, _ = decode(data)
    return _extract_varbinds(children[2][1])


def walk_table(host, columns, *, version="v2c", community="public", v3=None,
               port=161, timeout=2.0, retries=1, max_rows=512, single=False):
    """Walk a set of table columns (base OIDs) in lock-step via GETNEXT and
    return {row_index: {column_base: value}}. Works for v2c and v3; for v3 the
    engine is discovered once and reused for the whole walk.

    single=True walks one OID per request (like `snmpwalk`), for agents that
    reject multi-varbind GETNEXT."""
    if single:
        merged = {}
        for c in columns:
            part = walk_table(host, [c], version=version, community=community, v3=v3,
                              port=port, timeout=timeout, retries=retries,
                              max_rows=max_rows, single=False)
            for idx, d in part.items():
                merged.setdefault(idx, {}).update(d)
        return merged
    engine = _engine_for(v3, host, port, timeout, retries) if version == "v3" else None
    active = [[c, c] for c in columns]
    rows = {}
    guard = 0
    _dbg(1, f"walk: {len(columns)} columns, version={version}, max_rows={max_rows}")
    while active and guard < max_rows:
        guard += 1
        send = [a[1] for a in active]
        _dbg(2, f"  iter {guard}: GETNEXT {len(send)} varbinds")
        if version == "v3":
            vbs = getnext_v3(host, v3, send, engine, port, timeout, retries)
        else:
            vbs = getnext_v2c(host, community, send, port, timeout, retries)
        if len(vbs) != len(active):
            _dbg(1, f"  WARNING: asked {len(active)} varbinds, agent returned {len(vbs)} "
                    f"(agent may not support multi-varbind GETNEXT)")
        still = []
        for (base, _cur), (oid, val) in zip(active, vbs):
            if oid.startswith(base + ".") and val is not None:
                idx = oid[len(base) + 1:]
                rows.setdefault(idx, {})[base] = val
                still.append([base, oid])
        active = still
    _dbg(1, f"walk done: {len(rows)} rows in {guard} iteration(s)")
    return rows


# ---- interface table (IF-MIB) ------------------------------------------
IF = {
    "descr": ".1.3.6.1.2.1.2.2.1.2",
    "type": ".1.3.6.1.2.1.2.2.1.3",
    "phys": ".1.3.6.1.2.1.2.2.1.6",
    "name": ".1.3.6.1.2.1.31.1.1.1.1",
    "alias": ".1.3.6.1.2.1.31.1.1.1.18",
    "speed": ".1.3.6.1.2.1.2.2.1.5",
    "admin": ".1.3.6.1.2.1.2.2.1.7",
    "oper": ".1.3.6.1.2.1.2.2.1.8",
    "in_octets": ".1.3.6.1.2.1.2.2.1.10",
    "in_errors": ".1.3.6.1.2.1.2.2.1.14",
    "out_octets": ".1.3.6.1.2.1.2.2.1.16",
    "out_errors": ".1.3.6.1.2.1.2.2.1.20",
}
_IF_STATUS = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant",
              6: "notPresent", 7: "lowerLayerDown"}


def _mac_from_octets(val):
    """SNMP OctetString MAC -> aa:bb:cc:dd:ee:ff."""
    if isinstance(val, bytes):
        b = val
    elif isinstance(val, str):
        # net-snmp may render as 'aa:bb:..' or raw; try hex-pairs
        parts = re.split(r"[:\s]", val.strip())
        try:
            b = bytes(int(p, 16) for p in parts if p)
        except ValueError:
            return val
    else:
        return str(val)
    return ":".join("%02x" % x for x in b) if b else ""


def _mac_from_oid_tail(tail):
    """Six trailing OID sub-ids -> MAC string."""
    nums = [int(x) for x in tail.split(".") if x != ""]
    if len(nums) >= 6:
        return ":".join("%02x" % (n & 0xFF) for n in nums[-6:])
    return ""


def poll_arp(host, *, port=161, version="v2c", community="public",
             v3=None, timeout=2.0, retries=1):
    """IP-MIB ipNetToMediaTable -> list of {ip, mac, ifindex}."""
    PHYS = ".1.3.6.1.2.1.4.22.1.2"   # ipNetToMediaPhysAddress
    NET = ".1.3.6.1.2.1.4.22.1.3"    # ipNetToMediaNetAddress
    rows = walk_table(host, [PHYS, NET], version=version, community=community,
                      v3=v3, port=port, timeout=timeout, retries=retries)
    if not rows:
        rows = walk_table(host, [PHYS, NET], version=version, community=community,
                          v3=v3, port=port, timeout=timeout, retries=retries, single=True)
    out = []
    for idx, cols in rows.items():
        # index is ifIndex.a.b.c.d
        parts = idx.split(".")
        ifindex = parts[0] if parts else ""
        ip = ".".join(parts[1:5]) if len(parts) >= 5 else cols.get(NET, "")
        mac = _mac_from_octets(cols.get(PHYS))
        if mac:
            out.append({"ip": ip, "mac": mac, "ifindex": ifindex})
    return out


def _inet_address(value, addr_type=None):
    """Best-effort InetAddress -> (family, text) without guessing malformed rows."""
    try:
        if isinstance(value, bytes):
            if len(value) in (4, 16):
                ip = ipaddress.ip_address(value)
                return ("ipv4" if ip.version == 4 else "ipv6", str(ip))
            return ("", "")
        text = str(value or "").strip()
        if not text:
            return ("", "")
        ip = ipaddress.ip_address(text)
        return ("ipv4" if ip.version == 4 else "ipv6", str(ip))
    except ValueError:
        return ("", "")


def poll_ip_neighbors(host, *, port=161, version="v2c", community="public",
                      v3=None, timeout=2.0, retries=1, ifdescr=None):
    """IP-MIB ipNetToPhysicalTable, with legacy IPv4 fallback.

    Returns normalized records with source/provenance; malformed or secret-like
    data is never persisted.
    """
    ADDR_TYPE = ".1.3.6.1.2.1.4.35.1.2"
    NET = ".1.3.6.1.2.1.4.35.1.3"
    PHYS = ".1.3.6.1.2.1.4.35.1.4"
    NTYPE = ".1.3.6.1.2.1.4.35.1.6"
    STATE = ".1.3.6.1.2.1.4.35.1.7"
    rows = walk_table(host, [ADDR_TYPE, NET, PHYS, NTYPE, STATE], version=version,
                      community=community, v3=v3, port=port, timeout=timeout, retries=retries)
    if not rows:
        rows = walk_table(host, [ADDR_TYPE, NET, PHYS, NTYPE, STATE], version=version,
                          community=community, v3=v3, port=port, timeout=timeout, retries=retries,
                          single=True)
    ifdescr = ifdescr or {}
    type_map = {1: "other", 2: "invalid", 3: "dynamic", 4: "static", 5: "local"}
    state_map = {1: "reachable", 2: "stale", 3: "delay", 4: "probe", 5: "invalid",
                 6: "unknown", 7: "incomplete"}
    out = []
    for idx, cols in rows.items():
        parts = idx.split(".")
        ifindex = parts[0] if parts else ""
        family, ip = _inet_address(cols.get(NET), cols.get(ADDR_TYPE))
        mac = _mac_from_octets(cols.get(PHYS))
        if not family or not ip or not mac:
            continue
        ntype = cols.get(NTYPE)
        state = cols.get(STATE)
        out.append({
            "ip": ip, "address_family": family, "mac": mac, "ifindex": ifindex,
            "ifdescr": ifdescr.get(str(ifindex), ""),
            "neighbor_type": type_map.get(ntype, str(ntype or "")),
            "state": state_map.get(state, str(state or "")),
            "source": "ipNetToPhysicalTable",
        })
    if out:
        return out
    # Compatibility fallback for older agents.  This cannot provide IPv6 or
    # neighbour-state metadata, so provenance remains explicit.
    for row in poll_arp(host, port=port, version=version, community=community,
                        v3=v3, timeout=timeout, retries=retries):
        try:
            ip = str(ipaddress.ip_address(row.get("ip", "")))
        except ValueError:
            continue
        out.append({
            "ip": ip, "address_family": "ipv4", "mac": row.get("mac", ""),
            "ifindex": row.get("ifindex", ""),
            "ifdescr": ifdescr.get(str(row.get("ifindex", "")), ""),
            "neighbor_type": "", "state": "", "source": "ipNetToMediaTable",
        })
    return out


def poll_vlan_fdb(host, *, port=161, version="v2c", community="public",
                  v3=None, timeout=2.0, retries=1, ifdescr=None):
    """Q-BRIDGE-MIB FDB with explicit FDB-ID -> VLAN mapping.

    VLAN is emitted only when the Q-BRIDGE mapping is unambiguous.  Shared-VLAN
    learning contexts therefore remain unresolved rather than being guessed.
    """
    FDB_PORT = ".1.3.6.1.2.1.17.7.1.2.2.1.2"
    FDB_STATUS = ".1.3.6.1.2.1.17.7.1.2.2.1.3"
    VLAN_FDB_ID = ".1.3.6.1.2.1.17.7.1.4.2.1.3"
    BP_IFINDEX = ".1.3.6.1.2.1.17.1.4.1.2"
    fdb = walk_table(host, [FDB_PORT, FDB_STATUS], version=version, community=community,
                     v3=v3, port=port, timeout=timeout, retries=retries)
    if not fdb:
        fdb = walk_table(host, [FDB_PORT, FDB_STATUS], version=version, community=community,
                         v3=v3, port=port, timeout=timeout, retries=retries, single=True)
    vlan_rows = walk_table(host, [VLAN_FDB_ID], version=version, community=community,
                           v3=v3, port=port, timeout=timeout, retries=retries)
    bp = walk_table(host, [BP_IFINDEX], version=version, community=community,
                    v3=v3, port=port, timeout=timeout, retries=retries)
    bp_map = {}
    for bridge_port, cols in bp.items():
        try:
            bp_map[str(bridge_port)] = str(int(cols.get(BP_IFINDEX)))
        except (TypeError, ValueError):
            pass
    fdb_to_vlans = {}
    for idx, cols in vlan_rows.items():
        try:
            vlan = str(int(idx.split(".")[-1]))
            fdb_id = str(int(cols.get(VLAN_FDB_ID)))
        except (TypeError, ValueError):
            continue
        if 1 <= int(vlan) <= 4094:
            fdb_to_vlans.setdefault(fdb_id, set()).add(vlan)
    status_map = {1: "other", 2: "invalid", 3: "learned", 4: "self", 5: "mgmt"}
    ifdescr = ifdescr or {}
    out = []
    for idx, cols in fdb.items():
        parts = [p for p in idx.split(".") if p]
        if len(parts) < 7:
            continue
        fdb_id = parts[0]
        mac = _mac_from_oid_tail(".".join(parts[-6:]))
        bridge_port = cols.get(FDB_PORT)
        if not mac or bridge_port in (None, ""):
            continue
        bridge_port = str(int(bridge_port)) if str(bridge_port).lstrip("-").isdigit() else str(bridge_port)
        ifindex = bp_map.get(bridge_port, "")
        vlans = sorted(fdb_to_vlans.get(str(fdb_id), set()), key=lambda x: int(x))
        vlan_id = vlans[0] if len(vlans) == 1 else ""
        out.append({
            "vlan_id": vlan_id, "fdb_id": str(fdb_id), "mac": mac,
            "bridge_port": bridge_port, "ifindex": ifindex,
            "ifdescr": ifdescr.get(ifindex, ""),
            "status": status_map.get(cols.get(FDB_STATUS), str(cols.get(FDB_STATUS) or "")),
            "source": "Q-BRIDGE-MIB",
        })
    if out:
        return out
    # Compatibility fallback preserves legacy visibility but deliberately leaves
    # vlan_id empty because BRIDGE-MIB has no VLAN context.
    legacy = poll_mac_table(host, port=port, version=version, community=community,
                            v3=v3, timeout=timeout, retries=retries, ifdescr=ifdescr)
    return [{
        "vlan_id": "", "fdb_id": "", "mac": r.get("mac", ""),
        "bridge_port": r.get("port", ""), "ifindex": r.get("ifindex", ""),
        "ifdescr": r.get("ifdescr", ""), "status": "", "source": "BRIDGE-MIB",
    } for r in legacy]


def poll_mac_table(host, *, port=161, version="v2c", community="public",
                   v3=None, timeout=2.0, retries=1, ifdescr=None):
    """BRIDGE-MIB dot1dTpFdbTable -> list of {mac, port, ifindex, ifdescr}.
    Maps bridge port -> ifIndex via dot1dBasePortIfIndex, then ifIndex -> name
    via the supplied ifdescr map (from poll_interfaces)."""
    FDB_PORT = ".1.3.6.1.2.1.17.4.3.1.2"     # dot1dTpFdbPort (index = MAC)
    BP_IFINDEX = ".1.3.6.1.2.1.17.1.4.1.2"   # dot1dBasePortIfIndex
    fdb = walk_table(host, [FDB_PORT], version=version, community=community,
                     v3=v3, port=port, timeout=timeout, retries=retries)
    if not fdb:
        fdb = walk_table(host, [FDB_PORT], version=version, community=community,
                         v3=v3, port=port, timeout=timeout, retries=retries, single=True)
    bp = walk_table(host, [BP_IFINDEX], version=version, community=community,
                    v3=v3, port=port, timeout=timeout, retries=retries)
    bp_map = {}
    for base_port, cols in bp.items():
        try:
            bp_map[str(base_port)] = str(int(cols.get(BP_IFINDEX)))
        except (TypeError, ValueError):
            pass
    ifdescr = ifdescr or {}
    out = []
    for tail, cols in fdb.items():
        mac = _mac_from_oid_tail(tail)
        bport = cols.get(FDB_PORT)
        if not mac or bport in (None, ""):
            continue
        ifindex = bp_map.get(str(int(bport))) if str(bport).lstrip("-").isdigit() else ""
        out.append({"mac": mac, "port": str(bport), "ifindex": ifindex or "",
                    "ifdescr": ifdescr.get(ifindex or "", "")})
    return out


def poll_interfaces(host, *, port=161, version="v2c", community="public",
                    v3=None, timeout=2.0, retries=1):
    """Return a list of per-interface dicts from the IF-MIB ifTable."""
    cols = list(IF.values())
    rows = walk_table(host, cols, version=version, community=community, v3=v3,
                      port=port, timeout=timeout, retries=retries)
    if not rows:
        _dbg(1, "interface walk empty via multi-varbind GETNEXT; retrying one OID at a time")
        rows = walk_table(host, cols, version=version, community=community, v3=v3,
                          port=port, timeout=timeout, retries=retries, single=True)
    rev = {v: k for k, v in IF.items()}
    out = []
    for idx in sorted(rows, key=lambda x: [int(p) for p in x.split(".") if p.isdigit()] or [0]):
        r = rows[idx]
        rec = {"ifindex": idx}
        for base, val in r.items():
            key = rev[base]
            if key in ("descr", "name", "alias"):
                rec[key] = val.decode("utf-8", "replace").strip() if isinstance(val, bytes) else ("" if val is None else str(val))
            elif key == "phys":
                rec[key] = _mac_from_octets(val)
            elif key in ("admin", "oper"):
                rec[key] = _IF_STATUS.get(val, str(val))
            else:
                rec[key] = val
        out.append(rec)
    return out


def _extend_priv_key(kul, engine_id, hash_ctor, keylen):
    """AES-192/256 need a longer priv key than the hash digest. Extend per the
    Reeder key-localization draft (as net-snmp does for AES-192/AES-256)."""
    key = bytearray(kul)
    while len(key) < keylen:
        ku = hash_ctor(bytes(key)).digest()
        kul = hash_ctor(ku + engine_id + ku).digest()
        key += kul
    return bytes(key[:keylen])


def _localized_for(params, engine_id):
    """Return cached USM keys for one engine (RFC 3414 KDF is intentionally costly)."""
    cached = params._localized_keys.get(engine_id)
    ctor, tag_len = _AUTH[params.auth_proto]
    if cached:
        return ctor, tag_len, cached[0], cached[1]
    auth_key = password_to_key(params.auth_pass, engine_id, ctor)
    priv_key = None
    if params.priv_proto:
        keylen = _PRIV_KEYLEN[params.priv_proto]
        base = password_to_key(params.priv_pass, engine_id, ctor)
        priv_key = base[:keylen] if len(base) >= keylen else \
            _extend_priv_key(base, engine_id, ctor, keylen)
    params._localized_keys[engine_id] = (auth_key, priv_key)
    return ctor, tag_len, auth_key, priv_key


def _v3_request(host, params, oids, pdu_tag, engine, port=161, timeout=2.0, retries=1):
    engine_id, boots, etime = engine
    hash_ctor = None
    auth_key = priv_key = None
    tl = 12
    if params.auth_proto:
        hash_ctor, tl, auth_key, priv_key = _localized_for(params, engine_id)

    msg_id = struct.unpack(">I", os.urandom(4))[0] & 0x7FFFFFFF
    scoped = enc_seq(enc_octet(engine_id), enc_octet(b""),
                     _build_get_pdu(msg_id & 0x7FFFFFFF, oids, pdu_tag))

    priv_param = b""
    scoped_field = scoped
    encrypted = False
    if params.priv_proto:
        salt = os.urandom(8)
        iv = struct.pack(">II", boots, etime) + salt
        enc = aes.cfb128_encrypt(priv_key, iv, scoped)
        scoped_field = enc
        priv_param = salt
        encrypted = True

    auth_param = b"\x00" * tl if params.auth_proto else b""
    sec = _usm_params(engine_id, boots, etime, params.username.encode(),
                      auth_param, priv_param)
    msg = _v3_message(msg_id, params.flags(), sec, scoped_field, encrypted)

    if params.auth_proto:
        placeholder = b"\x04" + bytes([tl]) + b"\x00" * tl
        digest = hmac.new(auth_key, msg, hash_ctor).digest()[:tl]
        idx = msg.find(placeholder)
        if idx < 0:
            raise SNMPError("internal: auth placeholder not found")
        msg = msg[:idx + 2] + digest + msg[idx + 2 + tl:]

    data = _udp_exchange(host, port, msg, timeout, retries)
    _, top, _ = decode(data)
    resp_sec_octets = top[2][1]
    _, rsec, _ = decode(resp_sec_octets)
    resp_boots = rsec[1][1]
    resp_time = rsec[2][1]
    resp_priv = rsec[5][1]
    data_field = top[3]
    if data_field[0] == OCTET_STRING:  # encrypted response
        if not params.priv_proto:
            raise SNMPError("got encrypted response but no priv configured")
        iv = struct.pack(">II", resp_boots, resp_time) + resp_priv
        dec = aes.cfb128_decrypt(priv_key, iv, data_field[1])
        _, scoped_resp, _ = decode(dec)
    else:
        scoped_resp = data_field[1]
    pdu = scoped_resp[2]
    if pdu[0] == REPORT:
        raise SNMPError("SNMP v3 report (auth/priv/user error) from agent")
    return _extract_varbinds(pdu[1])


def get_v2c(host, community, oids, port=161, timeout=2.0, retries=1):
    rid = struct.unpack(">I", os.urandom(4))[0] & 0x7FFFFFFF
    pdu = _build_get_pdu(rid, oids)
    msg = enc_seq(enc_int(1), enc_octet(community), pdu)  # version 1 == v2c
    data = _udp_exchange(host, port, msg, timeout, retries)
    _, children, _ = decode(data)
    return _extract_varbinds(children[2][1])


# ---- v3 USM -------------------------------------------------------------
def password_to_key(password, engine_id, hash_ctor):
    """RFC 3414 password-to-key with engine localization."""
    pw = password.encode()
    plen = len(pw)
    h = hash_ctor()
    count = 0
    idx = 0
    while count < 1048576:
        block = bytearray(64)
        for i in range(64):
            block[i] = pw[idx % plen]
            idx += 1
        h.update(block)
        count += 64
    ku = h.digest()
    return hash_ctor(ku + engine_id + ku).digest()


_AUTH = {
    "md5": (hashlib.md5, 12),
    "sha": (hashlib.sha1, 12),
    "sha1": (hashlib.sha1, 12),
    "sha224": (hashlib.sha224, 16),   # RFC 7860: usmHMAC128SHA224, 128-bit tag
    "sha256": (hashlib.sha256, 24),   # usmHMAC192SHA256, 192-bit tag
    "sha384": (hashlib.sha384, 32),   # usmHMAC256SHA384, 256-bit tag
    "sha512": (hashlib.sha512, 48),   # usmHMAC384SHA512, 384-bit tag
}


def _norm_auth(p):
    if not p:
        return None
    k = str(p).lower().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {"sha": "sha1", "hmacsha": "sha1", "sha1": "sha1", "md5": "md5",
               "sha2224": "sha224", "sha224": "sha224",
               "sha2256": "sha256", "sha256": "sha256",
               "sha2384": "sha384", "sha384": "sha384",
               "sha2512": "sha512", "sha512": "sha512"}
    if k not in aliases:
        raise SNMPError(f"unsupported auth protocol {p!r} "
                        f"(use md5, sha, sha224, sha256, sha384, sha512)")
    return aliases[k]


def _norm_priv(p):
    if not p:
        return None
    k = str(p).lower().replace("-", "").replace("_", "").replace(" ", "")
    aliases = {"aes": "aes128", "aes128": "aes128", "aescfb128": "aes128",
               "aes192": "aes192", "aes256": "aes256",
               "des": "des"}
    if k not in aliases:
        raise SNMPError(f"unsupported privacy protocol {p!r} "
                        f"(use aes/aes128, aes192, aes256)")
    if aliases[k] == "des":
        raise SNMPError("DES privacy is deprecated and not supported; use AES")
    return aliases[k]


# priv protocol -> AES key length in bytes
_PRIV_KEYLEN = {"aes128": 16, "aes192": 24, "aes256": 32}


class V3Params:
    def __init__(self, username, auth_proto=None, auth_pass=None,
                 priv_proto=None, priv_pass=None):
        self.username = username
        self.auth_proto = _norm_auth(auth_proto)          # md5|sha1|sha224|sha256|sha384|sha512
        self.auth_pass = auth_pass
        self.priv_proto = _norm_priv(priv_proto)          # aes128|aes192|aes256
        self.priv_pass = priv_pass or auth_pass
        self._localized_keys = {}
        self._engines = {}
        if self.priv_proto and not self.auth_proto:
            raise SNMPError("priv requires auth (authPriv)")

    @property
    def level(self):
        if self.priv_proto:
            return "authPriv"
        if self.auth_proto:
            return "authNoPriv"
        return "noAuthNoPriv"

    def flags(self):
        f = 0x04  # reportable
        if self.auth_proto:
            f |= 0x01
        if self.priv_proto:
            f |= 0x02
        return bytes([f])


def _usm_params(engine_id, boots, time_, user, auth_param, priv_param):
    return enc_octet(enc_seq(
        enc_octet(engine_id), enc_int(boots), enc_int(time_),
        enc_octet(user), enc_octet(auth_param), enc_octet(priv_param)))


def _v3_message(msg_id, flags, sec_params, scoped_or_enc, encrypted):
    header = enc_seq(enc_int(msg_id), enc_int(65507),
                     enc_octet(flags), enc_int(3))
    data = enc_octet(scoped_or_enc) if encrypted else scoped_or_enc
    return enc_seq(enc_int(3), header, sec_params, data)


def _discover_engine(host, port, timeout, retries):
    """Send an unauthenticated get for engine discovery; parse the Report."""
    msg_id = struct.unpack(">I", os.urandom(4))[0] & 0x7FFFFFFF
    sec = _usm_params(b"", 0, 0, b"", b"", b"")
    scoped = enc_seq(enc_octet(b""), enc_octet(b""),
                     _build_get_pdu(1, [], GET_REQUEST))
    msg = _v3_message(msg_id, bytes([0x04]), sec, scoped, False)
    data = _udp_exchange(host, port, msg, timeout, retries)
    _, top, _ = decode(data)
    # top: [version, header, secParams(OCTET), data]
    sec_octets = top[2][1]
    _, secseq, _ = decode(sec_octets)
    engine_id = secseq[0][1]
    boots = secseq[1][1]
    etime = secseq[2][1]
    if not engine_id:
        raise SNMPError("engine discovery returned no engineID")
    _dbg(1, f"v3 engine: id={binascii.hexlify(engine_id).decode()} boots={boots} time={etime}")
    return engine_id, boots, etime


def _engine_for(params, host, port, timeout, retries):
    """Discover an SNMPv3 engine once per target for this poll operation."""
    key = (str(host), int(port))
    engine = params._engines.get(key)
    if engine is None:
        engine = _discover_engine(host, port, timeout, retries)
        params._engines[key] = engine
    return engine


# ---- high-level: poll system group -------------------------------------
def _fmt_value(val):
    """Render a decoded SNMP value for display."""
    if isinstance(val, bytes):
        try:
            s = val.decode("utf-8")
            if all((32 <= ord(c) < 127) or c in "\t\r\n" for c in s):
                return s.strip()
        except Exception:
            pass
        return "0x" + val.hex()
    return str(val)


def walk_subtree(host, root, *, version="v2c", community="public", v3=None,
                 port=161, timeout=2.0, retries=1, max_vars=400):
    """Walk every OID under `root` via GETNEXT (one at a time, like snmpwalk).
    Returns a list of (oid, value_str). Bounded by max_vars."""
    engine = _engine_for(v3, host, port, timeout, retries) if version == "v3" else None
    root = root.lstrip(".")
    cur = "." + root
    out = []
    guard = 0
    while guard < max_vars:
        guard += 1
        if version == "v3":
            vbs = getnext_v3(host, v3, [cur], engine, port, timeout, retries)
        else:
            vbs = getnext_v2c(host, community, [cur], port, timeout, retries)
        if not vbs:
            break
        oid, val = vbs[0]
        noid = oid.lstrip(".")
        if val is None or not (noid == root or noid.startswith(root + ".")):
            break
        out.append((noid, _fmt_value(val)))
        cur = oid
    return out


def get_oids(host, oids, *, port=161, version="v2c", community="public",
             v3=None, timeout=2.0, retries=1):
    """Read an explicit bounded OID set without exposing credential material."""
    if version == "v3":
        if v3 is None:
            raise SNMPError("v3 requested but no credentials given")
        return get_v3(host, v3, list(oids), port=port, timeout=timeout, retries=retries)
    return get_v2c(host, community, list(oids), port=port, timeout=timeout, retries=retries)


def poll_system(host, *, port=161, version="v2c", community="public",
                v3=None, timeout=2.0, retries=1):
    """Return a facts dict for the system group. Raises SNMPError on failure."""
    oids = [SYS["sysDescr"], SYS["sysObjectID"], SYS["sysUpTime"],
            SYS["sysContact"], SYS["sysName"], SYS["sysLocation"]]
    if version == "v3":
        if v3 is None:
            raise SNMPError("v3 requested but no credentials given")
        vbs = get_v3(host, v3, oids, port=port, timeout=timeout, retries=retries)
    else:
        vbs = get_v2c(host, community, oids, port=port, timeout=timeout, retries=retries)
    by_oid = {o: v for o, v in vbs}

    def s(oid):
        v = by_oid.get(oid)
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace").strip()
        return "" if v is None else str(v)

    return {
        "reachable": True,
        "sysdescr": s(SYS["sysDescr"]),
        "sysobjectid": by_oid.get(SYS["sysObjectID"]) or "",
        "uptime": _fmt_uptime(by_oid.get(SYS["sysUpTime"])),
        "contact": s(SYS["sysContact"]),
        "sysname": s(SYS["sysName"]),
        "location": s(SYS["sysLocation"]),
    }
