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
        self._sorted = []

    def rebuild(self):
        texts = []
        if os.path.isdir(self.mib_dir):
            for fn in os.listdir(self.mib_dir):
                if fn.startswith("."):
                    continue
                try:
                    with open(os.path.join(self.mib_dir, fn), encoding="utf-8",
                              errors="replace") as f:
                        texts.append(f.read())
                except OSError:
                    continue
        self.name_to_oid, self.oid_to_name = build_index(texts)
        self._sorted = sorted(self.oid_to_name.keys(),
                              key=lambda o: len(o.split(".")), reverse=True)
        try:
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump({"name_to_oid": self.name_to_oid,
                           "oid_to_name": self.oid_to_name}, f)
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

    def lookup(self, name):
        """Name -> numeric OID (or None)."""
        return self.name_to_oid.get(name)
