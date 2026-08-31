"""Global MIB automap: parse uploaded MIBs into an OID<->name index and resolve
numeric OIDs to names (longest-prefix) automatically across all SNMP views.

Stdlib only. This is a pragmatic ASN.1/SMI subset parser: it extracts
``name ... ::= { parent sub sub ... }`` definitions (OBJECT-TYPE,
OBJECT IDENTIFIER, MODULE-IDENTITY, OBJECT-IDENTITY) plus name(number) paths,
seeds the well-known roots, and resolves every name to a full numeric OID.
"""
import json
import os
import re

# Well-known anchors so we can resolve without every parent MIB being present.
_ROOTS = {
    "ccitt": "0", "iso": "1", "org": "1.3", "dod": "1.3.6", "internet": "1.3.6.1",
    "directory": "1.3.6.1.1", "mgmt": "1.3.6.1.2", "mib-2": "1.3.6.1.2.1",
    "transmission": "1.3.6.1.2.1.10", "experimental": "1.3.6.1.3",
    "private": "1.3.6.1.4", "enterprises": "1.3.6.1.4.1", "security": "1.3.6.1.5",
    "snmpV2": "1.3.6.1.6", "snmpModules": "1.3.6.1.6.3",
    "system": "1.3.6.1.2.1.1", "interfaces": "1.3.6.1.2.1.2", "ip": "1.3.6.1.2.1.4",
    "ifMIB": "1.3.6.1.2.1.31", "dot1dBridge": "1.3.6.1.2.1.17",
    # standard SNMPv2-MIB / RFC1213 system group leaves
    "sysDescr": "1.3.6.1.2.1.1.1", "sysObjectID": "1.3.6.1.2.1.1.2",
    "sysUpTime": "1.3.6.1.2.1.1.3", "sysContact": "1.3.6.1.2.1.1.4",
    "sysName": "1.3.6.1.2.1.1.5", "sysLocation": "1.3.6.1.2.1.1.6",
    "sysServices": "1.3.6.1.2.1.1.7",
    # IF-MIB ifTable
    "ifNumber": "1.3.6.1.2.1.2.1", "ifIndex": "1.3.6.1.2.1.2.2.1.1",
    "ifDescr": "1.3.6.1.2.1.2.2.1.2", "ifType": "1.3.6.1.2.1.2.2.1.3",
    "ifMtu": "1.3.6.1.2.1.2.2.1.4", "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
    "ifPhysAddress": "1.3.6.1.2.1.2.2.1.6", "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
    "ifOperStatus": "1.3.6.1.2.1.2.2.1.8", "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
    "ifInErrors": "1.3.6.1.2.1.2.2.1.14", "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
    "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
    # IF-MIB ifXTable (high-capacity + names)
    "ifName": "1.3.6.1.2.1.31.1.1.1.1", "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10", "ifHighSpeed": "1.3.6.1.2.1.31.1.1.1.15",
    "ifAlias": "1.3.6.1.2.1.31.1.1.1.18",
    # IP-MIB ARP + BRIDGE-MIB forwarding
    "ipNetToMediaPhysAddress": "1.3.6.1.2.1.4.22.1.2",
    "ipNetToMediaNetAddress": "1.3.6.1.2.1.4.22.1.3",
    "dot1dTpFdbAddress": "1.3.6.1.2.1.17.4.3.1.1",
    "dot1dTpFdbPort": "1.3.6.1.2.1.17.4.3.1.2",
    "dot1dBasePortIfIndex": "1.3.6.1.2.1.17.1.4.1.2",
}

# a definition start: NAME  MACRO ... ::= { body }
_DEF = re.compile(
    r"([a-zA-Z][\w-]*)\s+"
    r"(?:OBJECT-TYPE|OBJECT\s+IDENTIFIER|MODULE-IDENTITY|OBJECT-IDENTITY|"
    r"OBJECT-GROUP|NOTIFICATION-TYPE)\b"
    r".*?::=\s*\{([^}]*)\}", re.S)

_TOKEN = re.compile(r"([a-zA-Z][\w-]*)\((\d+)\)|([a-zA-Z][\w-]*)|(\d+)")
_OBJECT_TYPE = re.compile(r"([a-zA-Z][\w-]*)\s+OBJECT-TYPE\b")

# A Net-SNMP Linux agent identifies itself below enterprise 8072, while much
# of its useful host telemetry is exposed in the UCD tree and the standard
# HOST-RESOURCES tree.
_NET_SNMP_ENTERPRISE = "1.3.6.1.4.1.8072"
_UCD_SNMP_ENTERPRISE = "1.3.6.1.4.1.2021"
_HOST_RESOURCES = "1.3.6.1.2.1.25"


def _strip_comments(text):
    # SMI comments run from -- to end of line (or next --)
    out = []
    for line in text.splitlines():
        i = line.find("--")
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


def parse_defs(text):
    """Return {name: [component, ...]} where each component is a name or int."""
    text = _strip_comments(text)
    defs = {}
    for m in _DEF.finditer(text):
        name = m.group(1)
        body = m.group(2)
        comps = []
        for tok in _TOKEN.finditer(body):
            if tok.group(2) is not None:      # name(num)
                comps.append(int(tok.group(2)))
            elif tok.group(4) is not None:    # bare number
                comps.append(int(tok.group(4)))
            elif tok.group(3) is not None:    # bare name (only meaningful as first = parent)
                comps.append(tok.group(3))
        if comps:
            defs[name] = comps
    return defs


def build_index(mib_texts):
    """Given a list of MIB file contents, return (name_to_oid, oid_to_name)."""
    defs = {}
    for txt in mib_texts:
        for k, v in parse_defs(txt).items():
            defs.setdefault(k, v)
    name_to_oid = dict(_ROOTS)
    resolving = set()

    def resolve(name):
        if name in name_to_oid:
            return name_to_oid[name]
        if name not in defs or name in resolving:
            return None
        resolving.add(name)
        comps = defs[name]
        # first component may be a parent name; the rest are numbers
        oid = None
        subs = []
        for i, c in enumerate(comps):
            if isinstance(c, str):
                if i == 0:
                    oid = resolve(c)
                    if oid is None:
                        resolving.discard(name)
                        return None
                else:
                    # rare: a named sub in the middle; try to resolve, else stop
                    r = resolve(c)
                    if r:
                        oid = r
                    continue
            else:
                subs.append(str(c))
        resolving.discard(name)
        if oid is None:
            # bare numeric path like { 1 3 6 1 }
            if subs:
                oid = ".".join(subs)
                name_to_oid[name] = oid
                return oid
            return None
        full = oid + ("." + ".".join(subs) if subs else "")
        name_to_oid[name] = full
        return full

    for nm in list(defs):
        resolve(nm)
    # drop the seed roots from the user-facing name map but keep for reverse
    oid_to_name = {}
    for nm, oid in name_to_oid.items():
        # prefer the most specific (longest) name per OID
        if oid not in oid_to_name or len(nm) > len(oid_to_name[oid]):
            oid_to_name[oid] = nm
    return name_to_oid, oid_to_name


class MibIndex:
    """Loads/persists the global index and resolves OIDs to names."""

    def __init__(self, mib_dir, cache_path=None):
        self.mib_dir = mib_dir
        self.cache_path = cache_path or os.path.join(mib_dir, ".mibindex.json")
        self.name_to_oid = dict(_ROOTS)
        self.oid_to_name = {}
        self.name_source = {}
        self.file_stats = {}
        self.conflicts = []
        self.collection_objects = []
        self._sorted = []

    def rebuild(self):
        texts = []
        file_defs = {}
        if os.path.isdir(self.mib_dir):
            for fn in sorted(os.listdir(self.mib_dir)):
                if fn.startswith("."):
                    continue
                try:
                    with open(os.path.join(self.mib_dir, fn), encoding="utf-8",
                              errors="replace") as f:
                        text = f.read()
                    texts.append(text)
                    file_defs[fn] = parse_defs(text)
                except OSError:
                    continue
        self.name_to_oid, self.oid_to_name = build_index(texts)
        first_source = {}
        conflicts_by_file = {fn: [] for fn in file_defs}
        self.conflicts = []
        for fn, defs in file_defs.items():
            for name in defs:
                if name in first_source:
                    conflict = {"name": name, "winner": first_source[name], "duplicate": fn}
                    self.conflicts.append(conflict)
                    conflicts_by_file[fn].append(name)
                    conflicts_by_file[first_source[name]].append(name)
                else:
                    first_source[name] = fn
        self.name_source = {
            name: fn for name, fn in first_source.items()
            if name in self.name_to_oid
        }
        self.file_stats = {}
        for fn, defs in file_defs.items():
            won = [name for name in defs if first_source.get(name) == fn]
            resolved = [name for name in won if name in self.name_to_oid]
            unresolved = [name for name in won if name not in self.name_to_oid]
            self.file_stats[fn] = {
                "definitions": len(defs),
                "resolved": len(resolved),
                "unresolved": len(unresolved),
                "unresolved_names": unresolved[:50],
                "conflicts": len(set(conflicts_by_file.get(fn, []))),
                "conflict_names": sorted(set(conflicts_by_file.get(fn, [])))[:50],
                "collectible": 0,
            }
        self.collection_objects = []
        for fn, defs in file_defs.items():
            try:
                with open(os.path.join(self.mib_dir, fn), encoding="utf-8",
                          errors="replace") as f:
                    object_names = set(_OBJECT_TYPE.findall(_strip_comments(f.read())))
            except OSError:
                object_names = set()
            for name in sorted(object_names):
                oid = self.name_to_oid.get(name)
                if (oid and (oid.startswith("1.3.6.1.4.1.") or
                             oid == _HOST_RESOURCES or
                             oid.startswith(_HOST_RESOURCES + ".")) and
                        first_source.get(name) == fn):
                    self.collection_objects.append(
                        {"name": name, "oid": oid, "source": fn})
                    self.file_stats[fn]["collectible"] += 1
        self._sorted = sorted(self.oid_to_name.keys(),
                              key=lambda o: len(o.split(".")), reverse=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump({"name_to_oid": self.name_to_oid,
                           "oid_to_name": self.oid_to_name,
                           "name_source": self.name_source,
                           "file_stats": self.file_stats,
                           "conflicts": self.conflicts,
                           "collection_objects": self.collection_objects}, f)
        except OSError:
            pass
        return len(self.name_to_oid)

    def load(self):
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                d = json.load(f)
            self.name_to_oid = d.get("name_to_oid", dict(_ROOTS))
            self.oid_to_name = d.get("oid_to_name", {})
            if "sysDescr" not in self.name_to_oid:   # stale cache from before the standard seed
                return False
            has_mibs = (os.path.isdir(self.mib_dir) and any(
                not fn.startswith(".") for fn in os.listdir(self.mib_dir)))
            if has_mibs and ("file_stats" not in d or "collection_objects" not in d):
                return False
            self.name_source = d.get("name_source", {})
            self.file_stats = d.get("file_stats", {})
            self.conflicts = d.get("conflicts", [])
            self.collection_objects = d.get("collection_objects", [])
            self._sorted = sorted(self.oid_to_name.keys(),
                                  key=lambda o: len(o.split(".")), reverse=True)
            return True
        except (OSError, ValueError):
            return False

    def resolve(self, oid):
        """Numeric OID -> 'name' or 'name.sub.sub' by longest-prefix match.
        Returns the input unchanged if nothing matches."""
        oid = oid.lstrip(".")
        if oid in self.oid_to_name:
            return self.oid_to_name[oid]
        for base in self._sorted:
            if oid == base or oid.startswith(base + "."):
                rest = oid[len(base):]
                return self.oid_to_name[base] + rest
        return oid

    def resolve_detail(self, oid):
        """Return the resolved name plus the uploaded MIB that supplied it."""
        raw = str(oid).lstrip(".")
        base = raw if raw in self.oid_to_name else None
        if base is None:
            for candidate in self._sorted:
                if raw.startswith(candidate + "."):
                    base = candidate
                    break
        if base is None:
            return {"oid": raw, "name": raw, "base_oid": "", "source": "", "mapped": False}
        leaf = self.oid_to_name[base]
        suffix = raw[len(base):]
        return {"oid": raw, "name": leaf + suffix, "base_oid": base,
                "source": self.name_source.get(leaf, "Built-in standard MIB"),
                "mapped": True}

    def lookup(self, name):
        """Name -> numeric OID (or None)."""
        return self.name_to_oid.get(name)

    def lookup_detail(self, name):
        oid = self.lookup(name)
        return {"name": name, "oid": oid,
                "source": self.name_source.get(name, "Built-in standard MIB") if oid else ""}

    def collection_roots(self, sysobjectid, max_roots=12):
        """Bounded vendor walk roots derived from uploaded OBJECT-TYPE entries.

        Normally only objects in the device's own enterprises.<vendor> branch
        qualify. Net-SNMP Linux agents are an exception: sysObjectID is below
        8072 while host data also lives below UCD-SNMP 2021 and the standard
        HOST-RESOURCES-MIB tree.
        """
        raw = str(sysobjectid or "").lstrip(".")
        match = re.match(r"^1\.3\.6\.1\.4\.1\.(\d+)(?:\.|$)", raw)
        if not match:
            return []
        vendor_prefix = "1.3.6.1.4.1." + match.group(1)
        allowed = [vendor_prefix]
        if vendor_prefix == _NET_SNMP_ENTERPRISE:
            allowed = [_NET_SNMP_ENTERPRISE, _UCD_SNMP_ENTERPRISE, _HOST_RESOURCES]

        roots = []
        for prefix in allowed:
            matched = [obj for obj in self.collection_objects
                       if obj.get("oid", "") == prefix or
                       obj.get("oid", "").startswith(prefix + ".")]
            if not matched:
                continue
            sources = sorted(set(obj.get("source", "Uploaded MIB") for obj in matched))
            roots.append({"root": prefix, "source": ", ".join(sources[:4]),
                          "objects": len(matched)})
        return roots[:max(1, int(max_roots))]
