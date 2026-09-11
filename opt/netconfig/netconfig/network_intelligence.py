"""VLAN-aware endpoint/topology correlation.

This module never invents topology facts.  It correlates authoritative SNMP
observations already persisted by NetConfig and makes ambiguity explicit.
"""
from __future__ import annotations

import re
import time

_MAC = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")


def normalize_mac(value):
    raw = str(value or "").strip().lower().replace("-", ":")
    if "." in raw and ":" not in raw:
        hexed = raw.replace(".", "")
        if len(hexed) == 12 and all(c in "0123456789abcdef" for c in hexed):
            raw = ":".join(hexed[i:i + 2] for i in range(0, 12, 2))
    if not _MAC.fullmatch(raw):
        return ""
    octets = [int(x, 16) for x in raw.split(":")]
    if not any(octets) or all(x == 0xff for x in octets) or (octets[0] & 1):
        return ""
    return raw


def _fresh(ts, now, max_age):
    try:
        return now - float(ts or 0) <= max_age
    except (TypeError, ValueError):
        return False


def _port_keys(row):
    keys = set()
    for key in ("ifindex", "ifdescr", "bridge_port", "port"):
        value = str(row.get(key, "") or "").strip().lower()
        if value:
            keys.add(value)
    return keys


def _neighbor_port_keys(row):
    keys = set()
    for key in ("local_port", "local_port_num"):
        value = str(row.get(key, "") or "").strip().lower()
        if value:
            keys.add(value)
    return keys


def correlate(db, device=None, *, max_age=1800, now=None):
    """Return endpoint attachment records with explicit confidence/provenance.

    Fresh FDB observations on ports with LLDP/CDP neighbours are treated as
    transit observations.  A single fresh non-neighbour-facing observation is
    considered a direct attachment candidate.  Multiple candidates remain
    AMBIGUOUS rather than being guessed.
    """
    now = time.time() if now is None else float(now)
    max_age = max(1, int(max_age))
    ip_rows = db.get_ip_neighbors(device)
    fdb_rows = db.get_vlan_fdb(device)
    topo = db.get_neighbors(device)

    neighbor_ports = {}
    downstream = {}
    for n in topo:
        dev = n.get("device", "")
        keys = _neighbor_port_keys(n)
        neighbor_ports.setdefault(dev, set()).update(keys)
        for key in keys:
            downstream.setdefault((dev, key), []).append({
                "neighbor": n.get("neighbor_device") or n.get("sys_name") or n.get("chassis_id") or "",
                "managed": bool(n.get("managed_neighbor")),
                "protocol": n.get("protocol", ""),
                "remote_port": n.get("port_id", ""),
            })

    by_mac_ip = {}
    for row in ip_rows:
        mac = normalize_mac(row.get("mac"))
        if not mac:
            continue
        item = dict(row)
        item["fresh"] = _fresh(row.get("ts"), now, max_age)
        by_mac_ip.setdefault(mac, []).append(item)

    by_mac_fdb = {}
    for row in fdb_rows:
        mac = normalize_mac(row.get("mac"))
        if not mac:
            continue
        item = dict(row)
        keys = _port_keys(item)
        nkeys = neighbor_ports.get(item.get("device", ""), set())
        match = sorted(keys & nkeys)
        item["fresh"] = _fresh(row.get("ts"), now, max_age)
        item["neighbor_facing"] = bool(match)
        item["downstream"] = []
        for key in match:
            item["downstream"].extend(downstream.get((item.get("device", ""), key), []))
        by_mac_fdb.setdefault(mac, []).append(item)

    out = []
    for mac in sorted(set(by_mac_ip) | set(by_mac_fdb)):
        ips = sorted(by_mac_ip.get(mac, []), key=lambda r: (r.get("ip", ""), r.get("device", "")))
        fdb = by_mac_fdb.get(mac, [])
        fresh = [r for r in fdb if r.get("fresh")]
        direct = [r for r in fresh if not r.get("neighbor_facing")]
        status = "UNRESOLVED"
        confidence = "NONE"
        attachment = None
        if len(direct) == 1:
            attachment = direct[0]
            if str(attachment.get("vlan_id", "")):
                status, confidence = "ATTACHED", "HIGH"
            else:
                status, confidence = "ATTACHED", "PARTIAL"
        elif len(direct) > 1:
            status, confidence = "AMBIGUOUS", "LOW"
        elif fresh:
            status, confidence = "TRANSIT_ONLY", "LOW"
        elif fdb:
            status, confidence = "STALE", "NONE"

        ipv4 = sorted({r.get("ip", "") for r in ips if r.get("address_family") == "ipv4" and r.get("ip")})
        ipv6 = sorted({r.get("ip", "") for r in ips if r.get("address_family") == "ipv6" and r.get("ip")})
        record = {
            "mac": mac,
            "ipv4": ipv4,
            "ipv6": ipv6,
            "status": status,
            "confidence": confidence,
            "attachment": None,
            "candidates": direct,
            "transit_observations": [r for r in fresh if r.get("neighbor_facing")],
            "neighbor_observations": ips,
            "max_age_seconds": max_age,
        }
        if attachment:
            record["attachment"] = {
                "device": attachment.get("device", ""),
                "vlan_id": str(attachment.get("vlan_id", "") or ""),
                "fdb_id": str(attachment.get("fdb_id", "") or ""),
                "ifindex": str(attachment.get("ifindex", "") or ""),
                "ifdescr": attachment.get("ifdescr", ""),
                "bridge_port": str(attachment.get("bridge_port", "") or ""),
                "source": attachment.get("source", ""),
                "ts": attachment.get("ts"),
            }
        out.append(record)
    return out


def summary(rows):
    stats = {"total": len(rows), "attached": 0, "ambiguous": 0, "transit_only": 0,
             "stale": 0, "unresolved": 0, "with_ipv4": 0, "with_ipv6": 0}
    for r in rows:
        key = str(r.get("status", "unresolved")).lower()
        if key in stats:
            stats[key] += 1
        if r.get("ipv4"):
            stats["with_ipv4"] += 1
        if r.get("ipv6"):
            stats["with_ipv6"] += 1
    return stats
