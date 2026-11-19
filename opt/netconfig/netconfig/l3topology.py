"""Read-only Layer-3 topology evidence collection and graph construction.

The collector deliberately reuses the SSH session opened for configuration
collection.  It sends only driver-declared read-only commands, persists parsed
interface/route observations, and treats a next-hop IP as a managed device only
when it resolves uniquely to fresh same-VRF interface evidence, or to a unique
Network-device Host/IP that is proven on-link by fresh same-VRF connected
evidence from the source device.
"""
from __future__ import annotations

import ipaddress
import hashlib
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


def _network_device(device):
    return "network" in str(device.get("device_type") or "network").replace(",", " ").lower().split()


def _ip_in_prefix(address, prefix):
    try:
        return ipaddress.ip_address(str(address)) in ipaddress.ip_network(str(prefix), strict=False)
    except Exception:
        return False


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


def parse_configured_static_routes(platform, text):
    """Parse configured IPv4 static-route intent without retaining raw config.

    Returned evidence references are hashes of normalized route identity only;
    configuration text (which may contain credentials) is never persisted here.
    """
    platform = _platform(platform)
    text = str(text or "")
    rows = []
    seen = set()

    def add(destination, mask="", next_hop="", interface="", vrf="default"):
        try:
            prefix = str(ipaddress.ip_network(
                str(destination) if "/" in str(destination) else f"{destination}/{mask}",
                strict=False))
        except Exception:
            return
        vrf = str(vrf or "default").strip().strip('"') or "default"
        next_hop = str(next_hop or "").strip()
        if next_hop:
            try:
                next_hop = str(ipaddress.ip_address(next_hop))
            except Exception:
                return
        interface = str(interface or "").strip().strip('"')
        if not next_hop and not interface:
            return
        key = (vrf, prefix, next_hop, interface)
        if key in seen:
            return
        seen.add(key)
        digest = hashlib.sha256("\x00".join((platform,) + key).encode()).hexdigest()[:24]
        rows.append({
            "vrf": vrf, "destination_prefix": prefix, "next_hop": next_hop,
            "outgoing_interface": interface,
            "config_evidence_ref": f"configured-static:{digest}",
        })

    if platform == "fortigate_fortios":
        in_static = False
        current = {}

        def flush():
            if current:
                add(current.get("dst", "0.0.0.0/0"), next_hop=current.get("gateway", ""),
                    interface=current.get("device", ""), vrf=current.get("vrf", "default"))
                current.clear()

        for raw in text.splitlines():
            line = raw.strip()
            low = line.lower()
            if low == "config router static":
                in_static = True
                continue
            if not in_static:
                continue
            if low.startswith("edit "):
                flush()
            elif low == "next":
                flush()
            elif low == "end":
                flush()
                in_static = False
            else:
                match = re.match(r'^set\s+(dst|gateway|device|vrf)\s+(.+)$', line, re.I)
                if match:
                    value = match.group(2).strip().strip('"')
                    if match.group(1).lower() == "dst":
                        parts = value.split()
                        value = (f"{parts[0]}/{_mask_prefix(parts[1])}"
                                 if len(parts) >= 2 and "/" not in parts[0] else parts[0])
                    current[match.group(1).lower()] = value
        flush()
        return rows

    if platform == "juniper_junos":
        for raw in text.splitlines():
            match = re.match(
                rf"^set\s+(?:routing-instances\s+(\S+)\s+)?routing-options\s+static\s+route\s+({_PREFIX})\s+next-hop\s+({_IPV4})\b",
                raw.strip(), re.I)
            if match:
                add(match.group(2), next_hop=match.group(3), vrf=match.group(1) or "default")
        return rows

    if platform == "mikrotik_routeros":
        for raw in text.splitlines():
            line = raw.strip()
            if "dst-address=" not in line or "gateway=" not in line:
                continue
            destination = re.search(rf"\bdst-address=({_PREFIX})\b", line)
            gateway_match = re.search(r"\bgateway=([^\s]+)", line)
            table = re.search(r"\brouting-table=([^\s]+)", line)
            if destination and gateway_match:
                gateway = gateway_match.group(1).split(",")[0]
                add(destination.group(1),
                    next_hop=(gateway if re.fullmatch(_IPV4, gateway) else ""),
                    interface=("" if re.fullmatch(_IPV4, gateway) else gateway),
                    vrf=(table.group(1) if table else "main"))
        return rows

    # Cisco IOS/NX-OS, Arista EOS, Aruba AOS-CX and Comware route syntax.
    for raw in text.splitlines():
        line = raw.strip()
        low = line.lower()
        tokens = line.split()
        vrf = "default"
        if low.startswith("ip route-static "):
            pos = 2
            if len(tokens) > pos + 1 and tokens[pos].lower() == "vpn-instance":
                vrf = tokens[pos + 1]
                pos += 2
        elif low.startswith("ip route "):
            pos = 2
            if len(tokens) > pos + 1 and tokens[pos].lower() == "vrf":
                vrf = tokens[pos + 1]
                pos += 2
        else:
            continue
        if len(tokens) <= pos:
            continue
        destination = tokens[pos]
        pos += 1
        mask = ""
        if "/" not in destination:
            if len(tokens) <= pos:
                continue
            mask = tokens[pos]
            pos += 1
        remaining = tokens[pos:]
        next_hop = next((token for token in remaining if re.fullmatch(_IPV4, token)), "")
        interface = ""
        if remaining and remaining[0] != next_hop and not remaining[0].isdigit():
            interface = remaining[0]
        add(destination, mask=mask, next_hop=next_hop, interface=interface, vrf=vrf)
    return rows


def _classify_route_origin(route, configured_routes):
    protocol = str(route.get("protocol") or "").upper()
    if protocol in {"CONNECTED", "LOCAL"}:
        return "CONNECTED", "DIRECT", ""
    if protocol == "STATIC":
        for configured in configured_routes:
            if (configured["vrf"] != str(route.get("vrf") or "default")
                    or configured["destination_prefix"] != route.get("destination_prefix")
                    or configured["next_hop"] != str(route.get("next_hop") or "")):
                continue
            configured_interface = configured.get("outgoing_interface") or ""
            active_interface = str(route.get("outgoing_interface") or "")
            if configured_interface and active_interface and configured_interface != active_interface:
                continue
            return "CONFIGURED_STATIC", "CONFIRMED", configured["config_evidence_ref"]
        return "OBSERVED_STATIC", "OBSERVED_CURRENT", ""
    if protocol in {"OSPF", "BGP", "RIP", "EIGRP", "ISIS"}:
        return "DYNAMIC_LEARNED", "OBSERVED_CURRENT", ""
    return "OBSERVED_ROUTE_TABLE", "OBSERVED_CURRENT", ""


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
        from .drivers import get_driver
        saved = {r["device"]: dict(r) for r in self.conn.execute("SELECT * FROM l3_collection_state ORDER BY device").fetchall()}
        profiles = {p["device"]: p for p in self.manager.protocol_profiles.list()}
        devices = [self.manager.inv.get(device)] if device else self.manager.inv.all()
        rows = []
        for dev in devices:
            if not dev or (not device and "network" not in str(dev.get("device_type") or "network").replace(",", " ").split()):
                continue
            try:
                supported = bool(getattr(get_driver(dev.get("platform") or "generic"), "l3_route_command", None))
            except Exception:
                supported = False
            supported = supported and "network" in str(dev.get("device_type") or "network").replace(",", " ").split()
            row = dict(saved.get(dev["name"]) or {"device": dev["name"], "status": "NOT_COLLECTED" if supported else "UNSUPPORTED",
                       "collection_id": "", "route_count": 0, "interface_count": 0, "observed_ts": 0, "error": ""})
            row["platform"] = dev.get("platform") or "generic"
            row["supports_cli_collection"] = supported
            profile = profiles.get(dev["name"]) or {}
            uses_cli = not (profile.get("enabled") and profile.get("protocol") != "cli_ssh")
            row["route_collection_available"] = supported and uses_cli
            row["display_status"] = row["status"]
            if row["status"] == "OK" and not self._fresh({"observed_ts": row.get("observed_ts"), "max_age_seconds": self.MAX_AGE_SECONDS}, time.time()):
                row["display_status"] = "STALE"
            row["action_hint"] = ("Choose a supported Network platform to collect route data." if not supported else
                                  "The selected structured collection method does not learn CLI routes. Review Collection settings; no fallback is forced." if not uses_cli else
                                  "Collect config + routes. The existing SSH credentials and collection method are used.")
            rows.append(row)
        if device:
            return rows[0] if rows else {"device": device, "status": "NOT_COLLECTED", "display_status": "NOT_COLLECTED", "supports_cli_collection": False}
        return rows

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

    def collect_from_session(self, device, driver, transport, config_text=""):
        """Collect L3 evidence using the already-authenticated config SSH session."""
        if not getattr(driver, "l3_route_command", None):
            try:
                self._set_state(device["name"], platform=_platform(getattr(driver, "name", None) or device.get("platform")),
                                status="UNSUPPORTED", received_ts=time.time(), error="This platform has no route collection command.")
            except Exception:
                pass  # status bookkeeping only; never fail the config collection
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
            configured_routes = parse_configured_static_routes(driver.name, config_text)
            confirmed_static = 0
            for row in route_rows:
                origin, confidence, config_ref = _classify_route_origin(row, configured_routes)
                row["route_origin"] = origin
                row["route_confidence"] = confidence
                row["config_evidence_ref"] = config_ref
                if origin == "CONFIGURED_STATIC":
                    confirmed_static += 1

            for i, row in enumerate(interface_rows):
                self.conn.execute(
                    "INSERT INTO l3_interface_observations(tenant_id,device,vrf,interface,ip_address,prefix_length,network_prefix,source_kind,collection_id,evidence_ref,observed_ts,received_ts,max_age_seconds) "
                    "VALUES('default',?,?,?,?,?,?, 'CLI_COLLECTION',?,?,?,?,?)",
                    (device["name"], row["vrf"], row["interface"], row["ip_address"], int(row["prefix_length"]), row["network_prefix"],
                     cid, f"l3-cli:{device['name']}:{cid}:interface:{i}", now, now, self.MAX_AGE_SECONDS))
            for i, row in enumerate(route_rows):
                self.conn.execute(
                    "INSERT INTO l3_route_observations(tenant_id,device,vrf,destination_prefix,protocol,next_hop,outgoing_interface,next_device,metric,terminal,evidence_ref,actor,observed_ts,received_ts,max_age_seconds,source_kind,collection_id,route_origin,route_confidence,config_evidence_ref) "
                    "VALUES('default',?,?,?,?,?,?, '',?,?,?,'system',?,?,?,'CLI_COLLECTION',?,?,?,?)",
                    (device["name"], row["vrf"], row["destination_prefix"], row["protocol"], row["next_hop"], row["outgoing_interface"],
                     int(row["metric"]), 1 if row["terminal"] else 0,
                     f"l3-cli:{device['name']}:{cid}:route:{i}", now, now, self.MAX_AGE_SECONDS, cid,
                     row["route_origin"], row["route_confidence"], row["config_evidence_ref"]))
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
            self.db.audit(
                "system", "l3_topology_collect", device["name"],
                f"routes={len(route_rows)};interfaces={len(interface_rows)};"
                f"configured_static={confirmed_static};platform={driver.name}")
            return {
                "status": "OK", "routes": len(route_rows),
                "interfaces": len(interface_rows),
                "configured_static": confirmed_static,
                "collection_id": cid,
            }
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
                  "label": name, "host": str(dev.get("host") or ""), "vrf": "",
                  "platform": str(dev.get("platform") or ""),
                  "device_type": str(dev.get("device_type") or "")}
                 for name, dev in sorted(devices.items())]
        node_ids = {n["id"] for n in nodes}
        interfaces = self.interfaces()
        routes = self.routes()
        ip_map = {}
        current_interfaces = []
        for row in interfaces:
            fresh = self._fresh(row, now)
            if not fresh and not include_stale:
                continue
            ip_map.setdefault((str(row.get("vrf") or "default"), str(row.get("ip_address") or "")), []).append(row)
            current_interfaces.append((row, fresh))

        # A Host/IP fallback is deliberately narrower than interface matching:
        # it is accepted only for a unique managed Network device and only when
        # fresh connected evidence proves that the gateway is on-link from the
        # source device in the same VRF.  This covers production designs where
        # the managed address is also the gateway but the peer's interface
        # command did not yield a usable observation.
        inventory_hosts = {}
        for name, dev in devices.items():
            if not _network_device(dev):
                continue
            host = str(dev.get("host") or "").strip()
            try:
                host = str(ipaddress.ip_address(host))
            except Exception:
                continue
            inventory_hosts.setdefault(host, []).append(name)

        connected_prefixes = {}
        for row, fresh in current_interfaces:
            prefix = str(row.get("network_prefix") or "")
            if not fresh or not prefix:
                continue
            key = (str(row.get("device") or ""), str(row.get("vrf") or "default"))
            connected_prefixes.setdefault(key, set()).add(prefix)
        for route in routes:
            if (not self._fresh(route, now) or not bool(route.get("terminal"))
                    or str(route.get("protocol") or "").upper() != "CONNECTED"):
                continue
            prefix = str(route.get("destination_prefix") or "")
            if not prefix:
                continue
            key = (str(route.get("device") or ""), str(route.get("vrf") or "default"))
            connected_prefixes.setdefault(key, set()).add(prefix)

        edges_by_key = {}
        route_origin_counts = {}
        unresolved, ambiguous, stale_count = [], [], 0

        def put_edge(key, edge, route):
            current = edges_by_key.get(key)
            if current is None:
                edge["route_count"] = 1
                edge["destination_prefixes"] = [route.get("destination_prefix", "")]
                edge["protocols"] = [route.get("protocol", "")]
                edge["route_origins"] = [edge.get("route_origin", "")]
                edge["route_confidences"] = [edge.get("route_confidence", "")]
                edge["config_evidence_refs"] = (
                    [edge["config_evidence_ref"]] if edge.get("config_evidence_ref") else [])
                edges_by_key[key] = edge
                return
            current["route_count"] = int(current.get("route_count") or 0) + 1
            pfx = route.get("destination_prefix", "")
            proto = route.get("protocol", "")
            if pfx and pfx not in current["destination_prefixes"] and len(current["destination_prefixes"]) < 12:
                current["destination_prefixes"].append(pfx)
            if proto and proto not in current["protocols"]:
                current["protocols"].append(proto)
            origin = str(route.get("route_origin") or "OBSERVED_ROUTE_TABLE")
            route_confidence = str(route.get("route_confidence") or "OBSERVED_CURRENT")
            config_ref = str(route.get("config_evidence_ref") or "")
            origins = current.setdefault("route_origins", [current.get("route_origin", "")])
            confidences = current.setdefault(
                "route_confidences", [current.get("route_confidence", "")])
            config_refs = current.setdefault("config_evidence_refs", [])
            if origin and origin not in origins:
                origins.append(origin)
            if route_confidence and route_confidence not in confidences:
                confidences.append(route_confidence)
            if config_ref and config_ref not in config_refs:
                config_refs.append(config_ref)
            current["route_origin"] = (
                origins[0] if len(origins) == 1 else "MIXED")
            current["route_confidence"] = (
                confidences[0] if len(confidences) == 1 else "MIXED")
            if not current.get("outgoing_interface") and route.get("outgoing_interface"):
                current["outgoing_interface"] = str(route.get("outgoing_interface"))

        def ensure_subnet(vrf, prefix):
            subnet_id = f"subnet:{vrf}:{prefix}"
            if subnet_id not in node_ids:
                nodes.append({"id": subnet_id, "kind": "SUBNET", "device": "",
                              "label": prefix, "host": "", "vrf": vrf})
                node_ids.add(subnet_id)
            return subnet_id

        # Interface evidence is the primary truth for directly connected
        # transit networks.  Do not require every platform's route-table parser
        # to repeat the same connected route before two routers can share a
        # subnet node.
        for row, fresh in current_interfaces:
            device = str(row.get("device") or "")
            vrf = str(row.get("vrf") or "default")
            prefix = str(row.get("network_prefix") or "")
            interface = str(row.get("interface") or "")
            address = str(row.get("ip_address") or "")
            prefix_length = int(row.get("prefix_length") or 0)
            if device not in devices or not prefix or prefix_length <= 0:
                continue
            subnet_id = ensure_subnet(vrf, prefix)
            key = ("DIRECTLY_CONNECTED", f"device:{device}", subnet_id, vrf)
            edge = edges_by_key.get(key)
            address_label = f"{address}/{prefix_length}" if address else ""
            if edge is None:
                edges_by_key[key] = {
                    "id": f"interface:{device}:{vrf}:{prefix}",
                    "from": f"device:{device}", "to": subnet_id,
                    "kind": "DIRECTLY_CONNECTED", "vrf": vrf,
                    "outgoing_interface": interface, "next_hop": "",
                    "resolution_state": "INTERFACE_SUBNET",
                    "evidence_state": "FRESH" if fresh else "STALE",
                    "fresh": fresh, "confidence": "HIGH" if fresh else "STALE",
                    "route_origin": "INTERFACE_ADDRESS", "route_confidence": "DIRECT",
                    "identity_confidence": "HIGH" if fresh else "STALE",
                    "config_evidence_ref": "",
                    "evidence_ref": str(row.get("evidence_ref") or f"l3-interface:{row.get('id')}"),
                    "route_count": 0, "interface_count": 1,
                    "interface_addresses": [address_label] if address_label else [],
                    "destination_prefixes": [prefix], "protocols": ["INTERFACE"],
                    "route_origins": ["INTERFACE_ADDRESS"],
                    "route_confidences": ["DIRECT"], "config_evidence_refs": [],
                }
            else:
                edge["interface_count"] = int(edge.get("interface_count") or 0) + 1
                if address_label and address_label not in edge.setdefault("interface_addresses", []):
                    edge["interface_addresses"].append(address_label)

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
            route_origin = str(route.get("route_origin") or "OBSERVED_ROUTE_TABLE")
            route_confidence = str(route.get("route_confidence") or "OBSERVED_CURRENT")
            config_evidence_ref = str(route.get("config_evidence_ref") or "")
            route_origin_counts[route_origin] = route_origin_counts.get(route_origin, 0) + 1
            # Preserve the established collection provenance contract; route
            # intent/proof is additive and exposed in separate fields.
            evidence_state = (
                "DISCOVERED" if route.get("source_kind") == "CLI_COLLECTION"
                else "CONFIGURED")
            if not fresh:
                evidence_state = "STALE"
                route_confidence = "STALE"
            if bool(route.get("terminal")) and str(route.get("protocol") or "").upper() != "LOCAL":
                subnet_id = ensure_subnet(vrf, pfx)
                edge = {
                    "id": f"connected:{device}:{vrf}:{pfx}", "from": f"device:{device}", "to": subnet_id,
                    "kind": "DIRECTLY_CONNECTED", "vrf": vrf,
                    "outgoing_interface": str(route.get("outgoing_interface") or ""),
                    "next_hop": "", "resolution_state": "RESOLVED", "evidence_state": evidence_state,
                    "fresh": fresh, "confidence": "HIGH" if fresh else "STALE",
                    "route_origin": route_origin, "route_confidence": route_confidence,
                    "identity_confidence": "HIGH" if fresh else "STALE",
                    "config_evidence_ref": config_evidence_ref,
                    "evidence_ref": str(route.get("evidence_ref") or f"l3-route:{route.get('id')}")}
                put_edge((edge["kind"], edge["from"], edge["to"], vrf), edge, route)
                continue
            next_hop = str(route.get("next_hop") or "")
            explicit = str(route.get("next_device") or "").strip()
            candidates = []
            resolution = "UNRESOLVED"
            resolution_detail = ""
            resolution_confidence = "NONE"
            if explicit:
                if explicit in devices:
                    candidates = [explicit]
                    resolution = "EXPLICIT"
                    resolution_detail = "explicit managed next-device evidence"
                    resolution_confidence = "HIGH"
            elif next_hop:
                matches = ip_map.get((vrf, next_hop), [])
                candidates = sorted({str(x.get("device") or "") for x in matches if str(x.get("device") or "") in devices and str(x.get("device")) != device})
                if len(candidates) == 1:
                    resolution = "MANAGED_INTERFACE_IP"
                    resolution_detail = "unique fresh managed-interface IP in the same VRF"
                    resolution_confidence = "HIGH"
                elif len(candidates) > 1:
                    resolution = "AMBIGUOUS"
                    resolution_detail = "multiple fresh managed interfaces claim this IP in the same VRF"
                else:
                    on_link = sorted(
                        prefix for prefix in connected_prefixes.get((device, vrf), set())
                        if _ip_in_prefix(next_hop, prefix)
                    )
                    host_candidates = sorted(
                        name for name in inventory_hosts.get(next_hop, [])
                        if name != device
                    )
                    if on_link and len(host_candidates) == 1:
                        candidates = host_candidates
                        resolution = "INVENTORY_HOST_ON_LINK"
                        resolution_detail = (
                            f"unique Network device Host/IP; gateway is on-link via {on_link[0]}"
                        )
                        resolution_confidence = "MEDIUM"
                    elif on_link and len(host_candidates) > 1:
                        candidates = host_candidates
                        resolution = "AMBIGUOUS"
                        resolution_detail = "multiple Network devices use this on-link Host/IP"
                    elif host_candidates:
                        resolution_detail = (
                            "Host/IP matched a managed Network device, but no fresh same-VRF "
                            "connected prefix proves that the gateway is on-link"
                        )
                    else:
                        resolution_detail = (
                            "no unique fresh same-VRF interface or on-link Network-device Host/IP match"
                        )
            if len(candidates) == 1:
                target = candidates[0]
                target_rows = [x for x in ip_map.get((vrf, next_hop), [])
                               if str(x.get("device") or "") == target]
                target_interfaces = sorted({str(x.get("interface") or "")
                                            for x in target_rows if x.get("interface")})
                if route_confidence == "CONFIRMED":
                    resolution_detail = (
                        f"running configuration matches the active static route; {resolution_detail}")
                edge = {
                    "id": f"nexthop:{device}:{target}:{vrf}", "from": f"device:{device}", "to": f"device:{target}",
                    "kind": "NEXT_HOP", "vrf": vrf,
                    "outgoing_interface": str(route.get("outgoing_interface") or ""),
                    "next_hop": next_hop, "resolution_state": resolution, "evidence_state": evidence_state,
                    "resolution_detail": resolution_detail,
                    "target_interface": target_interfaces[0] if len(target_interfaces) == 1 else "",
                    "fresh": fresh,
                    "confidence": (
                        "CONFIRMED" if fresh and route_confidence == "CONFIRMED"
                        else resolution_confidence if fresh else "STALE"),
                    "route_origin": route_origin,
                    "route_confidence": route_confidence,
                    "identity_confidence": resolution_confidence if fresh else "STALE",
                    "config_evidence_ref": config_evidence_ref,
                    "evidence_ref": str(route.get("evidence_ref") or f"l3-route:{route.get('id')}")}
                put_edge((edge["kind"], edge["from"], edge["to"], vrf), edge, route)
            elif len(candidates) > 1:
                ambiguous.append({
                    "device": device, "vrf": vrf, "destination_prefix": pfx,
                    "next_hop": next_hop, "candidates": candidates,
                    "route_origin": route_origin, "route_confidence": route_confidence,
                    "config_evidence_ref": config_evidence_ref,
                    "resolution_detail": resolution_detail,
                    "route_id": int(route.get("id") or 0)})
            elif next_hop or explicit:
                unresolved.append({
                    "device": device, "vrf": vrf, "destination_prefix": pfx,
                    "next_hop": next_hop, "explicit_next_device": explicit,
                    "route_origin": route_origin, "route_confidence": route_confidence,
                    "config_evidence_ref": config_evidence_ref,
                    "resolution_detail": resolution_detail,
                    "route_id": int(route.get("id") or 0)})

        edges = sorted(edges_by_key.values(), key=lambda x: (x["kind"], x["from"], x["to"], x["vrf"]))
        subnet_degree = {}
        for edge in edges:
            if edge.get("kind") == "DIRECTLY_CONNECTED":
                subnet_degree[edge.get("to")] = subnet_degree.get(edge.get("to"), 0) + 1
        resolution_counts = {}
        for edge in edges:
            if edge.get("kind") == "NEXT_HOP":
                state = str(edge.get("resolution_state") or "UNKNOWN")
                resolution_counts[state] = resolution_counts.get(state, 0) + 1
        return {
            "nodes": nodes, "edges": edges, "unresolved_next_hops": unresolved,
            "ambiguous_next_hops": ambiguous, "collection_status": self.collection_status(),
            "summary": {
                "managed_devices": len(devices),
                "subnets": sum(1 for x in nodes if x["kind"] == "SUBNET"),
                "transit_subnets": sum(1 for count in subnet_degree.values() if count >= 2),
                "connected_edges": sum(1 for x in edges if x["kind"] == "DIRECTLY_CONNECTED"),
                "next_hop_edges": sum(1 for x in edges if x["kind"] == "NEXT_HOP"),
                "next_hop_resolution_sources": resolution_counts,
                "route_origins": route_origin_counts,
                "unresolved_next_hops": len(unresolved), "ambiguous_next_hops": len(ambiguous),
                "stale_routes_excluded": 0 if include_stale else stale_count,
            },
        }

    def combined_graph(self, physical_graph, *, include_stale=False, now=None):
        graph = self.graph(include_stale=include_stale, now=now)
        edges = list(graph["edges"])
        physical_edges = physical_graph.get("physical_edges")
        if physical_edges is None:
            physical_edges = [edge for edge in physical_graph.get("edges", [])
                              if edge.get("evidence_kind") == "OBSERVED"]
        reachability_edges = physical_graph.get("reachability_edges")
        if reachability_edges is None:
            reachability_edges = [edge for edge in physical_graph.get("edges", [])
                                  if edge.get("evidence_kind") == "INFERRED"]
        for edge in list(physical_edges) + list(reachability_edges):
            src, dst = str(edge.get("from") or ""), str(edge.get("to") or "")
            if not src or not dst:
                continue
            edges.append({
                "id": f"physical:{src}:{dst}:{edge.get('protocol','')}",
                "from": f"device:{src}", "to": f"device:{dst}",
                "kind": "PHYSICAL_ADJACENCY" if edge.get("evidence_kind") == "OBSERVED" else "FDB_PATH",
                "vrf": "", "outgoing_interface": str(edge.get("local_port") or ""),
                "remote_interface": str(edge.get("remote_port") or ""),
                "link_count": int(edge.get("link_count") or 1),
                "next_hop": "", "resolution_state": "RESOLVED", "evidence_state": str(edge.get("evidence_kind") or "UNKNOWN"),
                "fresh": True, "confidence": str(edge.get("confidence") or ""),
                "evidence_ref": str(edge.get("evidence") or ""), "route_count": 0,
                "destination_prefixes": [], "protocols": [str(edge.get("protocol") or "")],
            })
        graph["edges"] = sorted(edges, key=lambda x: (x["kind"], x["from"], x["to"], x.get("vrf", "")))
        graph["summary"] = dict(graph["summary"])
        graph["summary"]["physical_edges"] = sum(1 for x in edges if x["kind"] == "PHYSICAL_ADJACENCY")
        graph["summary"]["reachability_edges"] = sum(1 for x in edges if x["kind"] == "FDB_PATH")
        return graph
