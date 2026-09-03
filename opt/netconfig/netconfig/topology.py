"""LLDP/CDP neighbour normalization and fleet-topology analysis."""
import re

LLDP_REM_BASE = "1.0.8802.1.1.2.1.4.1.1"
LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"
LLDP_COLUMNS = {
    "chassis_id": LLDP_REM_BASE + ".5",
    "port_id": LLDP_REM_BASE + ".7",
    "port_desc": LLDP_REM_BASE + ".8",
    "sys_name": LLDP_REM_BASE + ".9",
    "sys_desc": LLDP_REM_BASE + ".10",
}


def _rows(pairs, base):
    out = {}
    pfx = base + "."
    for oid, value in pairs:
        oid = oid.lstrip(".")
        if oid.startswith(pfx):
            out[oid[len(pfx):]] = str(value)
    return out


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


def analyze(neighbors, inventory):
    """Mark neighbours managed/unmanaged by inventory hostname, host IP, or name."""
    by_name = {str(d.get("name", "")).lower(): d for d in inventory}
    by_host = {str(d.get("host", "")).lower(): d for d in inventory}
    by_sysname = {str(d.get("sysname", "")).lower(): d for d in inventory if d.get("sysname")}
    edges = []
    for n in neighbors:
        candidates = [str(n.get("sys_name", "")).lower(), str(n.get("chassis_id", "")).lower()]
        managed = next((by_name.get(c) or by_host.get(c) or by_sysname.get(c) for c in candidates if c), None)
        x = dict(n)
        x["managed_neighbor"] = bool(managed)
        x["neighbor_device"] = managed.get("name", "") if managed else ""
        x["unmanaged"] = not bool(managed)
        edges.append(x)
    return edges
