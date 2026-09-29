"""VLAN-aware endpoint/topology correlation.

This module never invents topology facts.  It correlates authoritative SNMP
observations already persisted by NetConfig and makes ambiguity explicit.
"""
from __future__ import annotations

import re
import time

from . import topology as _topology

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


def correlate(db, device=None, *, inventory=None, max_age=1800, now=None):
    """Return endpoint attachment records with explicit confidence/provenance.

    Fresh FDB observations on ports with LLDP/CDP neighbours are treated as
    transit observations.  A single fresh non-neighbour-facing observation is
    considered a direct attachment candidate.  Multiple candidates remain
    AMBIGUOUS rather than being guessed.
    """
    now = time.time() if now is None else float(now)
    max_age = max(1, int(max_age))
    # Correlate globally first. ARP/IP-neighbour evidence often lives on an L3
    # gateway while FDB evidence lives on access/distribution switches. Filtering
    # either table by device before the MAC join breaks the IP -> MAC -> port chain.
    ip_rows = db.get_ip_neighbors()
    fdb_rows = db.get_vlan_fdb()
    topo = db.get_neighbors()

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

    # R51-HF1 FDB-derived managed-device path evidence can identify additional
    # transit-facing ports when LLDP/CDP is absent (for example firewalls that do
    # not expose LLDP-MIB). It is supplementary only and never becomes a direct
    # adjacency assertion.
    if inventory:
        try:
            inferred = _topology.infer_fdb_edges(
                fdb_rows, inventory, db.get_topology_device_identities(),
                db.get_topology_interfaces())
        except Exception:
            inferred = []
        for edge in inferred:
            dev = str(edge.get("from") or "")
            port = str(edge.get("local_port") or "").strip().lower()
            if not dev or not port:
                continue
            neighbor_ports.setdefault(dev, set()).add(port)
            downstream.setdefault((dev, port), []).append({
                "neighbor": edge.get("to") or "", "managed": True,
                "protocol": "fdb-inferred", "remote_port": edge.get("remote_port") or "",
                "evidence_kind": "INFERRED",
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
        fresh_ip = [r for r in ips if r.get("fresh")]
        stale_ip_mapping = bool(ips) and not fresh_ip
        status = "UNRESOLVED"
        confidence = "NONE"
        attachment = None
        if len(direct) == 1:
            attachment = direct[0]
            if str(attachment.get("vlan_id", "")):
                status, confidence = "ATTACHED", ("PARTIAL" if stale_ip_mapping else "HIGH")
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
        transit = [r for r in fresh if r.get("neighbor_facing")]
        record = {
            "mac": mac,
            "ipv4": ipv4,
            "ipv6": ipv6,
            "status": status,
            "confidence": confidence,
            "attachment": None,
            "candidates": direct,
            "transit_observations": transit,
            "neighbor_observations": ips,
            "max_age_seconds": max_age,
            "ip_mapping_fresh": bool(fresh_ip) if ips else None,
            "evidence_chain": {
                "ip_neighbors": [{
                    "device": r.get("device", ""), "ip": r.get("ip", ""),
                    "ifdescr": r.get("ifdescr", ""), "ifindex": r.get("ifindex", ""),
                    "source": r.get("source", ""), "fresh": bool(r.get("fresh")),
                } for r in ips],
                "fdb_candidates": [{
                    "device": r.get("device", ""), "ifdescr": r.get("ifdescr", ""),
                    "ifindex": r.get("ifindex", ""), "bridge_port": r.get("bridge_port", ""),
                    "vlan_id": r.get("vlan_id", ""), "source": r.get("source", ""),
                    "fresh": bool(r.get("fresh")), "transit": bool(r.get("neighbor_facing")),
                } for r in fdb],
            },
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
        if device:
            observed_devices = {str(r.get("device") or "") for r in ips + fdb}
            if str(device) not in observed_devices:
                continue
        out.append(record)
    return out


def endpoint_matches(row, needle):
    needle = str(needle or "").strip().lower()
    if not needle:
        return True
    values = [row.get("mac", ""), row.get("status", ""), row.get("confidence", "")]
    values.extend(row.get("ipv4") or [])
    values.extend(row.get("ipv6") or [])
    attachment = row.get("attachment") or {}
    values.extend([attachment.get("device", ""), attachment.get("ifdescr", ""),
                   attachment.get("ifindex", ""), attachment.get("bridge_port", ""),
                   attachment.get("vlan_id", "")])
    for item in (row.get("candidates") or []) + (row.get("transit_observations") or []):
        values.extend([item.get("device", ""), item.get("ifdescr", ""),
                       item.get("ifindex", ""), item.get("bridge_port", "")])
    return any(needle in str(value or "").lower() for value in values)


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
