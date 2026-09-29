"""Read-only Layer-3 topology evidence collection and graph construction.

The collector deliberately reuses the SSH session opened for configuration
collection.  It sends only driver-declared read-only commands, persists parsed
interface/route observations, and never treats a next-hop IP as a managed
device unless that IP resolves uniquely to fresh managed-interface evidence in
the same VRF.
"""
from __future__ import annotations

import ipaddress
import re
import time
import uuid


_READ_ERROR = re.compile(
    r"(?im)^\s*(?:%\s*(?:invalid input|incomplete command|ambiguous command|unknown command|error).*|"
    r"unknown action(?:\s+\d+)?|command fail(?:\.\s*return code\s*-?\d+)?|"
    r"command parse error.*|invalid command.*|unrecognized command.*|syntax error.*)\s*$"
)
_IPV4 = r"(?:\d{1,3}\.){3}\d{1,3}"
_PREFIX = rf"{_IPV4}/\d{{1,2}}"


def _platform(value):
    key = str(value or "generic").strip().lower()
    return {
        "fortigate": "fortigate_fortios",
        "fortios": "fortigate_fortios",
        "fortinet_fortigate": "fortigate_fortios",
    }.get(key, key)


def _clean_output(text, command):
    text = str(text or "").replace("\x00", "")
    if not text.strip():
        raise ValueError(f"L3 evidence command returned empty output: {command}")
    m = _READ_ERROR.search(text)
    if m:
        raise ValueError(f"L3 evidence command failed: {' '.join(m.group(0).split())[:180]}")
    return text


def _mask_prefix(mask):
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except Exception:
        return 0


def _network(address, prefix):
    try:
        if int(prefix) <= 0:
            return ""
        return str(ipaddress.ip_interface(f"{address}/{int(prefix)}").network)
    except Exception:
        return ""


def parse_interfaces(platform, text):
    """Parse bounded interface address evidence from supported read-only output."""
    platform = _platform(platform)
    text = str(text or "")
    rows = []
    seen = set()

    def add(interface, address, prefix=0, vrf="default"):
        interface = str(interface or "").strip().strip('"')
        address = str(address or "").strip()
        vrf = str(vrf or "default").strip().strip('"') or "default"
        try:
            ipaddress.ip_address(address)
        except Exception:
            return
        key = (vrf, interface, address, int(prefix or 0))
        if not interface or key in seen:
            return
        seen.add(key)
        rows.append({
            "vrf": vrf,
            "interface": interface,
            "ip_address": address,
            "prefix_length": int(prefix or 0),
            "network_prefix": _network(address, prefix),
        })

    if platform == "juniper_junos":
        for line in text.splitlines():
            m = re.match(rf"^\s*(\S+)\s+\S+\s+\S+\s+inet\s+({_PREFIX})\b", line)
            if not m:
                continue
            addr, plen = m.group(2).split("/")
            add(m.group(1), addr, int(plen))
        return rows

    if platform == "mikrotik_routeros":
        for line in text.splitlines():
            ma = re.search(rf"\baddress=({_PREFIX})\b", line)
            mi = re.search(r"\binterface=([^\s]+)", line)
            mt = re.search(r"\brouting-table=([^\s]+)", line)
            if ma and mi:
                addr, plen = ma.group(1).split("/")
                add(mi.group(1), addr, int(plen), (mt.group(1) if mt else "main"))
        return rows

    if platform == "fortigate_fortios":
        current = ""
        current_vrf = "default"
        for line in text.splitlines():
            mh = re.search(r"==\s*\[\s*([^\]]+)\s*\]", line)
            if mh:
                current = mh.group(1).strip()
                current_vrf = "default"
            mn = re.search(r"\bname[:=]\s*([^\s]+)", line, re.I)
            if mn:
                current = mn.group(1).strip('"')
            mv = re.search(r"\bvrf[:=]\s*(\d+|[^\s]+)", line, re.I)
            if mv:
                current_vrf = mv.group(1)
            mip = re.search(rf"\bip[:=]\s*({_IPV4})(?:/([0-9]{{1,2}})|\s+({_IPV4}))", line, re.I)
            if current and mip:
                plen = int(mip.group(2)) if mip.group(2) else _mask_prefix(mip.group(3))
                add(current, mip.group(1), plen, current_vrf)
        return rows

    # Cisco IOS/NX-OS/ASA, Arista EOS, Aruba AOS-CX and Comware brief tables.
    current_vrf = "default"
    for line in text.splitlines():
        mv = (re.search(r"(?:VRF|Routing Table)\s*[:\"]+\s*\"?([^\"\s:]+)", line, re.I)
              or re.search(r"IP Route Table for VRF\s+\"([^\"]+)\"", line, re.I))
        if mv:
            current_vrf = mv.group(1).strip('"') or "default"
        m = re.match(rf"^\s*([^\s]+)\s+({_IPV4})(?:/([0-9]{{1,2}}))?\b", line)
        if m and m.group(2) != "0.0.0.0":
            add(m.group(1), m.group(2), int(m.group(3) or 0), current_vrf)
            continue
        # Some platforms print address/mask after interface name.
        m = re.match(rf"^\s*([^\s]+)\s+({_IPV4})\s+({_IPV4})\b", line)
        if m and m.group(2) != "0.0.0.0":
            add(m.group(1), m.group(2), _mask_prefix(m.group(3)), current_vrf)
    return rows


def _route_proto(code):
    c = str(code or "").strip().upper().split()[0] if str(code or "").strip() else ""
    c = c.rstrip("*+")
    return {
        "C": "CONNECTED", "L": "LOCAL", "S": "STATIC", "O": "OSPF",
        "B": "BGP", "R": "RIP", "D": "EIGRP", "I": "ISIS", "K": "KERNEL",
        "DIRECT": "CONNECTED", "STATIC": "STATIC", "OSPF": "OSPF", "BGP": "BGP",
        "RIP": "RIP", "ISIS": "ISIS", "LOCAL": "LOCAL",
    }.get(c, c or "UNKNOWN")


def parse_routes(platform, text):
    """Parse active IPv4 route evidence without inventing managed next devices."""
    platform = _platform(platform)
    text = str(text or "")
    rows = []
    seen = set()

    def add(prefix, protocol="", next_hop="", interface="", metric=0, terminal=False, vrf="default"):
        try:
            prefix = str(ipaddress.ip_network(str(prefix).strip(), strict=False))
        except Exception:
            return
        vrf = str(vrf or "default").strip().strip('"') or "default"
        protocol = _route_proto(protocol)
        next_hop = str(next_hop or "").lstrip(">").strip()
        if next_hop:
            try:
                ipaddress.ip_address(next_hop)
            except Exception:
                next_hop = ""
        interface = str(interface or "").lstrip(">").strip().rstrip(",")
        key = (vrf, prefix, protocol, next_hop, interface, int(metric or 0), bool(terminal))
        if key in seen:
            return
        seen.add(key)
        rows.append({
            "vrf": vrf, "destination_prefix": prefix, "protocol": protocol,
            "next_hop": next_hop, "outgoing_interface": interface,
            "metric": int(metric or 0), "terminal": bool(terminal),
        })

    if platform == "juniper_junos":
        vrf = "default"
        for line in text.splitlines():
            mh = re.match(r"^\s*([A-Za-z0-9_.:-]+):\s+\d+\s+destinations", line)
            if mh:
                table = mh.group(1)
                if table == "inet.0":
                    vrf = "default"
                elif table.endswith(".inet.0"):
                    vrf = table[:-7]
                else:
                    vrf = table
                continue
            m = re.match(rf"^\s*[+\-* ]*\s*({_PREFIX})\s+([A-Za-z]+)\s+(\d+)\s+(.*)$", line)
            if not m:
                continue
            rest = m.group(4).strip()
            tokens = rest.split()
            selected = ""
            for token in tokens:
                if token.startswith(">"):
                    selected = token[1:]
                    break
            proto = _route_proto(m.group(2))
            terminal = proto in {"CONNECTED", "LOCAL"}
            if selected and re.fullmatch(_IPV4, selected):
                add(m.group(1), proto, next_hop=selected, metric=int(m.group(3)), vrf=vrf)
            else:
                add(m.group(1), proto, interface=selected, metric=int(m.group(3)), terminal=terminal, vrf=vrf)
        return rows

    if platform == "mikrotik_routeros":
        for line in text.splitlines():
            md = re.search(rf"\bdst-address=({_PREFIX})\b", line)
            if not md:
                continue
            mg = re.search(r"\bgateway=([^\s]+)", line)
            mt = re.search(r"\brouting-table=([^\s]+)", line)
            mm = re.search(r"\bdistance=(\d+)", line)
            proto = "CONNECTED" if re.search(r"^\s*[^\s]*C", line) else "STATIC"
            gateway = mg.group(1).split(",")[0] if mg else ""
            if re.fullmatch(_IPV4, gateway):
                add(md.group(1), proto, next_hop=gateway, metric=int(mm.group(1) if mm else 0), vrf=(mt.group(1) if mt else "main"))
            else:
                add(md.group(1), proto, interface=gateway, metric=int(mm.group(1) if mm else 0), terminal=(proto == "CONNECTED"), vrf=(mt.group(1) if mt else "main"))
        return rows

    # Comware table format: Destination/Mask Proto ... NextHop Interface
    if platform == "hp_comware":
        vrf = "default"
        for line in text.splitlines():
            mv = re.search(r"(?:VPN-Instance|Routing Table)\s*[:\"]+\s*\"?([^\"\s:]+)", line, re.I)
            if mv:
                vrf = mv.group(1).strip('"') or "default"
            m = re.match(rf"^\s*({_PREFIX})\s+([A-Za-z][A-Za-z0-9_-]*)\s+\d+\s+(\d+)\s+({_IPV4}|0\.0\.0\.0)\s+(\S+)", line)
            if m:
                proto = _route_proto(m.group(2))
                terminal = proto == "CONNECTED" or m.group(5) == "0.0.0.0"
                add(m.group(1), proto, next_hop=("" if terminal else m.group(5)), interface=m.group(6), metric=int(m.group(3)), terminal=terminal, vrf=vrf)
        return rows

    # Cisco-like route tables, also used by FortiOS, Arista and AOS-CX.
    vrf = "default"
    for line in text.splitlines():
        mv = (re.search(r"Routing Table:\s*([^\s]+)", line, re.I)
              or re.search(r"Routing table for VRF[=:]\s*([^\s]+)", line, re.I)
              or re.search(r"IP Route Table for VRF\s+\"([^\"]+)\"", line, re.I)
              or re.search(r"^\s*VRF:\s*([^\s]+)", line, re.I))
        if mv:
            vrf = mv.group(1).strip('"') or "default"
            continue
        m = re.match(rf"^\s*([A-Za-z][A-Za-z0-9* ]{{0,8}})\s+({_PREFIX})\s+(.+)$", line)
        if not m:
            continue
        code, prefix, rest = m.group(1).strip(), m.group(2), m.group(3).strip()
        proto = _route_proto(code)
        metric = 0
        mb = re.search(r"\[(?:\d+)/(-?\d+)\]", rest)
        if mb:
            try:
                metric = int(mb.group(1))
            except Exception:
                metric = 0
        direct = "directly connected" in rest.lower() or proto in {"CONNECTED", "LOCAL"}
        if direct:
            mi = re.search(r"directly connected,\s*([^,\s]+)", rest, re.I)
            add(prefix, proto, interface=(mi.group(1) if mi else ""), metric=metric, terminal=True, vrf=vrf)
            continue
        mn = re.search(rf"\bvia\s+({_IPV4})", rest, re.I)
        mi = re.search(rf"\bvia\s+{_IPV4}(?:,\s*[^,]+)?(?:,\s*([^,\s\[]+))", rest, re.I)
        if mn:
            add(prefix, proto, next_hop=mn.group(1), interface=(mi.group(1) if mi else ""), metric=metric, vrf=vrf)
    return rows


class L3TopologyService:
    MAX_AGE_SECONDS = 3600

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn

    def _state(self, device):
        row = self.conn.execute("SELECT * FROM l3_collection_state WHERE device=?", (device,)).fetchone()
        return dict(row) if row else None

    def collection_status(self, device=None):
        if device:
            row = self._state(device)
            return row or {"device": device, "status": "NOT_COLLECTED", "collection_id": "", "route_count": 0, "interface_count": 0, "error": ""}
        return [dict(r) for r in self.conn.execute("SELECT * FROM l3_collection_state ORDER BY device").fetchall()]

    def _set_state(self, device, **values):
        current = self._state(device)
        fields = {
            "collection_id": "", "platform": "", "status": "UNKNOWN", "route_count": 0,
            "interface_count": 0, "observed_ts": 0.0, "received_ts": 0.0, "error": "",
        }
        if current:
            fields.update({k: current.get(k, v) for k, v in fields.items()})
        fields.update(values)
        if current:
            self.conn.execute(
                "UPDATE l3_collection_state SET collection_id=?,platform=?,status=?,route_count=?,interface_count=?,observed_ts=?,received_ts=?,error=? WHERE device=?",
                (fields["collection_id"], fields["platform"], fields["status"], int(fields["route_count"]), int(fields["interface_count"]),
                 float(fields["observed_ts"]), float(fields["received_ts"]), fields["error"], device))
        else:
            self.conn.execute(
                "INSERT INTO l3_collection_state(device,collection_id,platform,status,route_count,interface_count,observed_ts,received_ts,error) VALUES(?,?,?,?,?,?,?,?,?)",
                (device, fields["collection_id"], fields["platform"], fields["status"], int(fields["route_count"]), int(fields["interface_count"]),
                 float(fields["observed_ts"]), float(fields["received_ts"]), fields["error"]))
        self.conn.commit()

    def record_failure(self, device, platform, error):
        self._set_state(device, platform=_platform(platform), status="ERROR", received_ts=time.time(), error=str(error)[:500])

    def collect_from_session(self, device, driver, transport):
        """Collect L3 evidence using the already-authenticated config SSH session."""
        if not getattr(driver, "l3_route_command", None):
            return {"status": "UNSUPPORTED", "routes": 0, "interfaces": 0}
        now = time.time()
        cid = f"cli-{int(now * 1000)}-{uuid.uuid4().hex[:10]}"
        try:
            interface_rows = []
            if getattr(driver, "l3_interface_command", None):
                raw_if = _clean_output(transport.execute(driver.l3_interface_command), driver.l3_interface_command)
                interface_rows = parse_interfaces(driver.name, raw_if)
            raw_routes = _clean_output(transport.execute(driver.l3_route_command), driver.l3_route_command)
            route_rows = parse_routes(driver.name, raw_routes)
            if not route_rows:
                raise ValueError(f"no parseable IPv4 routes from {driver.l3_route_command}")

            for i, row in enumerate(interface_rows):
                self.conn.execute(
                    "INSERT INTO l3_interface_observations(tenant_id,device,vrf,interface,ip_address,prefix_length,network_prefix,source_kind,collection_id,evidence_ref,observed_ts,received_ts,max_age_seconds) "
                    "VALUES('default',?,?,?,?,?,?, 'CLI_COLLECTION',?,?,?,?,?)",
                    (device["name"], row["vrf"], row["interface"], row["ip_address"], int(row["prefix_length"]), row["network_prefix"],
                     cid, f"l3-cli:{device['name']}:{cid}:interface:{i}", now, now, self.MAX_AGE_SECONDS))
            for i, row in enumerate(route_rows):
                self.conn.execute(
                    "INSERT INTO l3_route_observations(tenant_id,device,vrf,destination_prefix,protocol,next_hop,outgoing_interface,next_device,metric,terminal,evidence_ref,actor,observed_ts,received_ts,max_age_seconds,source_kind,collection_id) "
                    "VALUES('default',?,?,?,?,?,?, '',?,?,?,'system',?,?,?,'CLI_COLLECTION',?)",
                    (device["name"], row["vrf"], row["destination_prefix"], row["protocol"], row["next_hop"], row["outgoing_interface"],
                     int(row["metric"]), 1 if row["terminal"] else 0,
                     f"l3-cli:{device['name']}:{cid}:route:{i}", now, now, self.MAX_AGE_SECONDS, cid))
            # Publish the new generation only after every row has been inserted.
            self._set_state(
                device["name"], collection_id=cid, platform=driver.name, status="OK",
                route_count=len(route_rows), interface_count=len(interface_rows),
                observed_ts=now, received_ts=now, error="")
            self.conn.execute(
                "DELETE FROM l3_route_observations WHERE device=? AND source_kind='CLI_COLLECTION' AND collection_id<>?",
                (device["name"], cid))
            self.conn.execute(
                "DELETE FROM l3_interface_observations WHERE device=? AND source_kind='CLI_COLLECTION' AND collection_id<>?",
                (device["name"], cid))
            self.conn.commit()
            self.db.audit("system", "l3_topology_collect", device["name"], f"routes={len(route_rows)};interfaces={len(interface_rows)};platform={driver.name}")
            return {"status": "OK", "routes": len(route_rows), "interfaces": len(interface_rows), "collection_id": cid}
        except Exception as exc:
            # A generation is invisible until l3_collection_state points at it.
            # Remove any partially inserted rows so generic route APIs cannot
            # expose an uncommitted collection attempt.
            try:
                self.conn.execute(
                    "DELETE FROM l3_route_observations WHERE device=? AND source_kind='CLI_COLLECTION' AND collection_id=?",
                    (device["name"], cid))
                self.conn.execute(
                    "DELETE FROM l3_interface_observations WHERE device=? AND source_kind='CLI_COLLECTION' AND collection_id=?",
                    (device["name"], cid))
                self.conn.commit()
            except Exception:
                pass
            self.record_failure(device["name"], getattr(driver, "name", device.get("platform", "")), exc)
            return {"status": "ERROR", "routes": 0, "interfaces": 0, "error": str(exc)}

    def _current_rows(self, table, device=None):
        states = {r["device"]: r["collection_id"] for r in self.collection_status() if r.get("collection_id")}
        q = f"SELECT * FROM {table} WHERE tenant_id='default'"
        args = []
        if device:
            q += " AND device=?"; args.append(device)
        q += " ORDER BY observed_ts DESC,id DESC"
        out = []
        for raw in self.conn.execute(q, tuple(args)).fetchall():
            row = dict(raw)
            if row.get("source_kind") == "CLI_COLLECTION" and row.get("collection_id") != states.get(row.get("device")):
                continue
            if "terminal" in row:
                row["terminal"] = bool(row.get("terminal"))
            out.append(row)
        return out

    def interfaces(self, device=None):
        return self._current_rows("l3_interface_observations", device=device)

    def routes(self, device=None):
        return self._current_rows("l3_route_observations", device=device)

    @staticmethod
    def _fresh(row, now):
        max_age = int(row.get("max_age_seconds") or 0)
        return max_age <= 0 or (now - float(row.get("observed_ts") or 0)) <= max_age

    def graph(self, *, include_stale=False, now=None):
        now = time.time() if now is None else float(now)
        devices = {d["name"]: d for d in self.manager.inv.all()}
        nodes = [{"id": f"device:{name}", "kind": "DEVICE", "device": name,
                  "label": name, "host": str(dev.get("host") or ""), "vrf": ""}
                 for name, dev in sorted(devices.items())]
        node_ids = {n["id"] for n in nodes}
        interfaces = self.interfaces()
        routes = self.routes()
        ip_map = {}
        for row in interfaces:
            fresh = self._fresh(row, now)
            if not fresh and not include_stale:
                continue
            ip_map.setdefault((str(row.get("vrf") or "default"), str(row.get("ip_address") or "")), []).append(row)

        edges_by_key = {}
        unresolved, ambiguous, stale_count = [], [], 0

        def put_edge(key, edge, route):
            current = edges_by_key.get(key)
            if current is None:
                edge["route_count"] = 1
                edge["destination_prefixes"] = [route.get("destination_prefix", "")]
                edge["protocols"] = [route.get("protocol", "")]
                edges_by_key[key] = edge
                return
            current["route_count"] += 1
            pfx = route.get("destination_prefix", "")
            proto = route.get("protocol", "")
            if pfx and pfx not in current["destination_prefixes"] and len(current["destination_prefixes"]) < 12:
                current["destination_prefixes"].append(pfx)
            if proto and proto not in current["protocols"]:
                current["protocols"].append(proto)

        for route in routes:
            fresh = self._fresh(route, now)
            if not fresh:
                stale_count += 1
                if not include_stale:
                    continue
            device = str(route.get("device") or "")
            if device not in devices:
                continue
            vrf = str(route.get("vrf") or "default")
            pfx = str(route.get("destination_prefix") or "")
            evidence_state = "DISCOVERED" if route.get("source_kind") == "CLI_COLLECTION" else "CONFIGURED"
            if not fresh:
                evidence_state = "STALE"
            if bool(route.get("terminal")) and str(route.get("protocol") or "").upper() != "LOCAL":
                subnet_id = f"subnet:{vrf}:{pfx}"
                if subnet_id not in node_ids:
                    nodes.append({"id": subnet_id, "kind": "SUBNET", "device": "", "label": pfx, "host": "", "vrf": vrf})
                    node_ids.add(subnet_id)
                edge = {
                    "id": f"connected:{device}:{vrf}:{pfx}", "from": f"device:{device}", "to": subnet_id,
                    "kind": "DIRECTLY_CONNECTED", "vrf": vrf,
                    "outgoing_interface": str(route.get("outgoing_interface") or ""),
                    "next_hop": "", "resolution_state": "RESOLVED", "evidence_state": evidence_state,
                    "fresh": fresh, "confidence": "HIGH" if fresh else "STALE",
                    "evidence_ref": str(route.get("evidence_ref") or f"l3-route:{route.get('id')}")}
                put_edge((edge["kind"], edge["from"], edge["to"], vrf), edge, route)
                continue
            next_hop = str(route.get("next_hop") or "")
            explicit = str(route.get("next_device") or "").strip()
            candidates = []
            resolution = "UNRESOLVED"
            if explicit:
                if explicit in devices:
                    candidates = [explicit]; resolution = "EXPLICIT"
            elif next_hop:
                matches = ip_map.get((vrf, next_hop), [])
                candidates = sorted({str(x.get("device") or "") for x in matches if str(x.get("device") or "") in devices and str(x.get("device")) != device})
                resolution = "MANAGED_INTERFACE_IP" if len(candidates) == 1 else ("AMBIGUOUS" if len(candidates) > 1 else "UNRESOLVED")
            if len(candidates) == 1:
                target = candidates[0]
                edge = {
                    "id": f"nexthop:{device}:{target}:{vrf}", "from": f"device:{device}", "to": f"device:{target}",
                    "kind": "NEXT_HOP", "vrf": vrf,
                    "outgoing_interface": str(route.get("outgoing_interface") or ""),
                    "next_hop": next_hop, "resolution_state": resolution, "evidence_state": evidence_state,
                    "fresh": fresh, "confidence": "HIGH" if fresh else "STALE",
                    "evidence_ref": str(route.get("evidence_ref") or f"l3-route:{route.get('id')}")}
                put_edge((edge["kind"], edge["from"], edge["to"], vrf), edge, route)
            elif len(candidates) > 1:
                ambiguous.append({"device": device, "vrf": vrf, "destination_prefix": pfx, "next_hop": next_hop, "candidates": candidates, "route_id": int(route.get("id") or 0)})
            elif next_hop or explicit:
                unresolved.append({"device": device, "vrf": vrf, "destination_prefix": pfx, "next_hop": next_hop, "explicit_next_device": explicit, "route_id": int(route.get("id") or 0)})

        edges = sorted(edges_by_key.values(), key=lambda x: (x["kind"], x["from"], x["to"], x["vrf"]))
        return {
            "nodes": nodes, "edges": edges, "unresolved_next_hops": unresolved,
            "ambiguous_next_hops": ambiguous, "collection_status": self.collection_status(),
            "summary": {
                "managed_devices": len(devices),
                "subnets": sum(1 for x in nodes if x["kind"] == "SUBNET"),
                "connected_edges": sum(1 for x in edges if x["kind"] == "DIRECTLY_CONNECTED"),
                "next_hop_edges": sum(1 for x in edges if x["kind"] == "NEXT_HOP"),
                "unresolved_next_hops": len(unresolved), "ambiguous_next_hops": len(ambiguous),
                "stale_routes_excluded": 0 if include_stale else stale_count,
            },
        }

    def combined_graph(self, physical_graph, *, include_stale=False, now=None):
        graph = self.graph(include_stale=include_stale, now=now)
        edges = list(graph["edges"])
        for edge in physical_graph.get("edges", []):
            src, dst = str(edge.get("from") or ""), str(edge.get("to") or "")
            if not src or not dst:
                continue
            edges.append({
                "id": f"physical:{src}:{dst}:{edge.get('protocol','')}",
                "from": f"device:{src}", "to": f"device:{dst}",
                "kind": "PHYSICAL_ADJACENCY" if edge.get("evidence_kind") == "OBSERVED" else "FDB_PATH",
                "vrf": "", "outgoing_interface": str(edge.get("local_port") or ""),
                "next_hop": "", "resolution_state": "RESOLVED", "evidence_state": str(edge.get("evidence_kind") or "UNKNOWN"),
                "fresh": True, "confidence": str(edge.get("confidence") or ""),
                "evidence_ref": str(edge.get("evidence") or ""), "route_count": 0,
                "destination_prefixes": [], "protocols": [str(edge.get("protocol") or "")],
            })
        graph["edges"] = sorted(edges, key=lambda x: (x["kind"], x["from"], x["to"], x.get("vrf", "")))
        graph["summary"] = dict(graph["summary"])
        graph["summary"]["physical_edges"] = sum(1 for x in edges if x["kind"] in {"PHYSICAL_ADJACENCY", "FDB_PATH"})
        return graph
