"""LLDP/CDP neighbour normalization and fleet-topology analysis."""
import re

LLDP_REM_BASE = "1.0.8802.1.1.2.1.4.1.1"
LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"
LLDP_COLUMNS = {
    "chassis_id_subtype": LLDP_REM_BASE + ".4",
    "chassis_id": LLDP_REM_BASE + ".5",
    "port_id_subtype": LLDP_REM_BASE + ".6",
    "port_id": LLDP_REM_BASE + ".7",
    "port_desc": LLDP_REM_BASE + ".8",
    "sys_name": LLDP_REM_BASE + ".9",
    "sys_desc": LLDP_REM_BASE + ".10",
    "sys_cap_supported": LLDP_REM_BASE + ".11",
    "sys_cap_enabled": LLDP_REM_BASE + ".12",
}

LLDP_LOCAL_IDENTITY = {
    "chassis_id_subtype": ".1.0.8802.1.1.2.1.3.1.0",
    "chassis_id": ".1.0.8802.1.1.2.1.3.2.0",
    "sys_name": ".1.0.8802.1.1.2.1.3.3.0",
    "sys_cap_supported": ".1.0.8802.1.1.2.1.3.5.0",
    "sys_cap_enabled": ".1.0.8802.1.1.2.1.3.6.0",
}
ENTITY_COLUMNS = {
    "descr": ".1.3.6.1.2.1.47.1.1.1.1.2",
    "class": ".1.3.6.1.2.1.47.1.1.1.1.5",
    "name": ".1.3.6.1.2.1.47.1.1.1.1.7",
    "serial": ".1.3.6.1.2.1.47.1.1.1.1.11",
    "model": ".1.3.6.1.2.1.47.1.1.1.1.13",
}


def _rows(pairs, base):
    out = {}
    pfx = base + "."
    for oid, value in pairs:
        oid = oid.lstrip(".")
        if oid.startswith(pfx):
            out[oid[len(pfx):]] = str(value)
    return out



def _text(value):
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "replace").strip()
        except Exception:
            return ""
    return str(value or "").strip()


def _mac(value):
    if isinstance(value, bytes) and len(value) == 6:
        return ":".join(f"{x:02x}" for x in value)
    text = _text(value).lower().replace("-", ":")
    if re.fullmatch(r"0x[0-9a-f]{12}", text):
        raw = text[2:]
        return ":".join(raw[i:i+2] for i in range(0, 12, 2))
    if re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", text):
        return text
    return ""


def normalize_identity_token(value):
    text = _text(value).strip().lower().rstrip(".")
    mac = _mac(value)
    return mac or text


def _subtype(value, kind="chassis"):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return _text(value)
    if kind == "chassis":
        return {1:"chassisComponent",2:"interfaceAlias",3:"portComponent",4:"macAddress",5:"networkAddress",6:"interfaceName",7:"local"}.get(n, str(n))
    return {1:"interfaceAlias",2:"portComponent",3:"macAddress",4:"networkAddress",5:"interfaceName",6:"agentCircuitId",7:"local"}.get(n, str(n))


def _caps(value):
    if isinstance(value, bytes):
        return value.hex()
    return _text(value)

def parse_device_identity(local_pairs=(), entity_rows=None, facts=None):
    """Normalize local LLDP + ENTITY-MIB identity without guessing.

    ENTITY-MIB chassis rows (entPhysicalClass=3) are preferred.  If no chassis
    class exists, serial/model/name are left empty rather than borrowing an
    arbitrary component identity.
    """
    facts = facts or {}
    by_oid = {"." + str(oid).lstrip("."): value for oid, value in (local_pairs or [])}
    ident = {
        "sys_name": _text(by_oid.get(LLDP_LOCAL_IDENTITY["sys_name"])) or _text(facts.get("sysname")),
        "chassis_id_subtype": _subtype(by_oid.get(LLDP_LOCAL_IDENTITY["chassis_id_subtype"]), "chassis"),
        "chassis_id": _text(by_oid.get(LLDP_LOCAL_IDENTITY["chassis_id"])),
        "chassis_mac": "",
        "chassis_serial": "",
        "chassis_name": "",
        "chassis_model": "",
        "sys_cap_supported": _caps(by_oid.get(LLDP_LOCAL_IDENTITY["sys_cap_supported"])),
        "sys_cap_enabled": _caps(by_oid.get(LLDP_LOCAL_IDENTITY["sys_cap_enabled"])),
        "source": "LLDP-MIB/ENTITY-MIB",
    }
    if ident["chassis_id_subtype"] == "macAddress":
        ident["chassis_mac"] = _mac(by_oid.get(LLDP_LOCAL_IDENTITY["chassis_id"]))
        if ident["chassis_mac"]:
            ident["chassis_id"] = ident["chassis_mac"]
    rev = {v: k for k, v in ENTITY_COLUMNS.items()}
    for _idx, row in sorted((entity_rows or {}).items(), key=lambda item: str(item[0])):
        klass = row.get(ENTITY_COLUMNS["class"])
        try:
            is_chassis = int(klass) == 3
        except (TypeError, ValueError):
            is_chassis = False
        if not is_chassis:
            continue
        ident["chassis_serial"] = _text(row.get(ENTITY_COLUMNS["serial"]))
        ident["chassis_name"] = _text(row.get(ENTITY_COLUMNS["name"])) or _text(row.get(ENTITY_COLUMNS["descr"]))
        ident["chassis_model"] = _text(row.get(ENTITY_COLUMNS["model"]))
        break
    return ident


def parse_lldp_walk(remote_pairs, local_port_pairs=()):
    """Normalize canned/live LLDP-MIB walks into neighbour records.

    Remote row index is timeMark.localPortNum.remIndex. The parser is pure and
    therefore easy to test with captured walks.
    """
    cols = {name: _rows(remote_pairs, base) for name, base in LLDP_COLUMNS.items()}
    local = _rows(local_port_pairs, LLDP_LOC_PORT_DESC)
    indexes = sorted({idx for values in cols.values() for idx in values})
    out = []
    for idx in indexes:
        parts = idx.split(".")
        local_port = parts[-2] if len(parts) >= 3 else ""
        row = {name: values.get(idx, "") for name, values in cols.items()}
        row["chassis_id_subtype"] = _subtype(row.get("chassis_id_subtype"), "chassis")
        row["port_id_subtype"] = _subtype(row.get("port_id_subtype"), "port")
        if row.get("chassis_id_subtype") == "macAddress":
            row["chassis_id"] = _mac(row.get("chassis_id")) or _text(row.get("chassis_id"))
        else:
            row["chassis_id"] = _text(row.get("chassis_id"))
        row["port_id"] = _text(row.get("port_id"))
        row["sys_name"] = _text(row.get("sys_name"))
        row["sys_desc"] = _text(row.get("sys_desc"))
        row["sys_cap_supported"] = _caps(row.get("sys_cap_supported"))
        row["sys_cap_enabled"] = _caps(row.get("sys_cap_enabled"))
        row.update({"protocol": "lldp", "local_port_num": local_port,
                    "local_port": local.get(local_port, local_port), "raw_index": idx})
        if row["sys_name"] or row["chassis_id"] or row["port_id"]:
            out.append(row)
    return out


def parse_cdp_detail(text):
    """Best-effort parser for common `show cdp neighbors detail` output."""
    records = []
    chunks = re.split(r"\n-{3,}\n|\nDevice ID:\s*", "\n" + (text or ""))
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        sys_name = lines[0].strip() if not lines[0].lower().startswith("device id:") else lines[0].split(":",1)[1].strip()
        port = re.search(r"Interface:\s*([^,\n]+).*?Port ID \(outgoing port\):\s*([^\n]+)", chunk, re.I|re.S)
        platform = re.search(r"Platform:\s*([^,\n]+)", chunk, re.I)
        ip = re.search(r"IP address:\s*([^\s]+)", chunk, re.I)
        records.append({"protocol": "cdp", "sys_name": sys_name,
                        "chassis_id": ip.group(1) if ip else "",
                        "local_port": port.group(1).strip() if port else "",
                        "local_port_num": "", "port_id": port.group(2).strip() if port else "",
                        "port_desc": "", "sys_desc": platform.group(1).strip() if platform else "",
                        "raw_index": ""})
    return [r for r in records if r["sys_name"]]



def _identity_tokens(device, identity=None):
    identity = identity or {}
    tokens = []
    for kind, value in (
        ("inventory_name", device.get("name")),
        ("inventory_host", device.get("host")),
        ("sys_name", identity.get("sys_name") or device.get("sysname")),
        ("chassis_id", identity.get("chassis_id")),
        ("chassis_mac", identity.get("chassis_mac")),
        ("chassis_serial", identity.get("chassis_serial")),
    ):
        token = normalize_identity_token(value)
        if token:
            tokens.append((kind, token))
    return tokens


def analyze(neighbors, inventory, identities=None):
    """Resolve observed neighbours to managed devices without identity guessing.

    A token is usable only when it uniquely names one inventory device.  When
    different usable tokens on the same observation point at different managed
    devices, the edge is AMBIGUOUS and is not considered traversable.
    """
    identities = identities or []
    id_by_device = {x.get("device", ""): x for x in identities}
    token_map = {}
    for dev in inventory:
        for kind, token in _identity_tokens(dev, id_by_device.get(dev.get("name", ""))):
            token_map.setdefault(token, []).append((dev, kind))

    edges = []
    for n in neighbors:
        observed = []
        for kind, value in (("sys_name", n.get("sys_name")), ("chassis_id", n.get("chassis_id"))):
            token = normalize_identity_token(value)
            if token:
                observed.append((kind, token))
        matches = []
        evidence = []
        for observed_kind, token in observed:
            candidates = token_map.get(token, [])
            unique_devices = {c[0].get("name", "") for c in candidates if c[0].get("name")}
            if len(unique_devices) == 1:
                name = next(iter(unique_devices))
                matches.append(name)
                evidence.append(f"{observed_kind}:{token}")
            elif len(unique_devices) > 1:
                evidence.append(f"conflict:{observed_kind}:{token}")
        unique_matches = sorted(set(matches))
        x = dict(n)
        if len(unique_matches) == 1:
            x["managed_neighbor"] = True
            x["neighbor_device"] = unique_matches[0]
            x["unmanaged"] = False
            x["resolution_state"] = "RESOLVED"
        elif len(unique_matches) > 1 or any(e.startswith("conflict:") for e in evidence):
            x["managed_neighbor"] = False
            x["neighbor_device"] = ""
            x["unmanaged"] = False
            x["resolution_state"] = "AMBIGUOUS"
        else:
            x["managed_neighbor"] = False
            x["neighbor_device"] = ""
            x["unmanaged"] = True
            x["resolution_state"] = "UNMANAGED"
        x["resolution_evidence"] = ",".join(evidence)[:512]
        edges.append(x)
    return edges


def identity_view(inventory, identities, interfaces):
    id_by = {r.get("device", ""): r for r in identities}
    if_by = {}
    for row in interfaces:
        if_by.setdefault(row.get("device", ""), []).append(dict(row))
    out = []
    for dev in sorted(inventory, key=lambda d: d.get("name", "")):
        name = dev.get("name", "")
        ident = dict(id_by.get(name, {}))
        out.append({
            "device": name,
            "host": dev.get("host", ""),
            "sys_name": ident.get("sys_name", ""),
            "chassis_id": ident.get("chassis_id", ""),
            "chassis_id_subtype": ident.get("chassis_id_subtype", ""),
            "chassis_mac": ident.get("chassis_mac", ""),
            "chassis_serial": ident.get("chassis_serial", ""),
            "chassis_name": ident.get("chassis_name", ""),
            "chassis_model": ident.get("chassis_model", ""),
            "sys_cap_supported": ident.get("sys_cap_supported", ""),
            "sys_cap_enabled": ident.get("sys_cap_enabled", ""),
            "interfaces": sorted(if_by.get(name, []), key=lambda r: str(r.get("ifindex", ""))),
            "ts": ident.get("ts"),
        })
    return out


def downstream_impact(neighbors, root_device, root_port=None, max_depth=16):
    """Traverse only unambiguous managed adjacency observations.

    This is observed-L2 downstream impact, not a routing-dependency claim.
    Traversal is cycle-safe and bounded.  root_port limits only the first hop.
    """
    root = str(root_device or "").strip()
    if not root:
        raise ValueError("root device is required")
    max_depth = max(1, min(int(max_depth), 64))
    adjacency = {}
    for row in neighbors:
        if not row.get("managed_neighbor") or row.get("resolution_state") not in ("", "RESOLVED"):
            continue
        src = row.get("device", "")
        dst = row.get("neighbor_device", "")
        if not src or not dst:
            continue
        adjacency.setdefault(src, []).append(dict(row))
    queue = [(root, 0)]
    visited = {root}
    devices = []
    edges = []
    while queue:
        current, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        for row in adjacency.get(current, []):
            if depth == 0 and root_port:
                keys = {str(row.get("local_port", "")), str(row.get("local_port_num", ""))}
                if str(root_port) not in keys:
                    continue
            dst = row.get("neighbor_device", "")
            edge = {
                "from": current, "to": dst, "local_port": row.get("local_port", ""),
                "remote_port": row.get("port_id", ""), "protocol": row.get("protocol", ""),
                "depth": depth + 1, "provenance": "observed_l2_neighbor",
            }
            edges.append(edge)
            if dst not in visited:
                visited.add(dst)
                devices.append({"device": dst, "depth": depth + 1, "via": current})
                queue.append((dst, depth + 1))
    return {
        "root_device": root, "root_port": root_port or "", "max_depth": max_depth,
        "scope": "observed_managed_l2_adjacency", "devices": devices, "edges": edges,
        "device_count": len(devices), "edge_count": len(edges),
    }
