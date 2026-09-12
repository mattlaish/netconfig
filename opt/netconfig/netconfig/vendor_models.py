"""VM-1 declarative vendor/model packs for safe structured automation.

Model packs are data, never executable plugins.  They map stable NetConfig
resource names to bounded NETCONF/RESTCONF/gNMI paths and value constraints.
Custom packs are accepted only after strict schema/path validation and cannot
contain credentials, shell fragments, caller-supplied RPC bodies, URLs, or
protobuf payloads.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.parse

_IDENT = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")
_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_ELEMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_NAMESPACE = re.compile(r"^(?:https?://|urn:)[^\x00\r\n ]{1,500}$")
_ALLOWED_TYPES = {"string", "boolean", "integer"}
_ALLOWED_RESOURCE_FIELDS = {
    "value_type", "selectors", "restconf_path", "restconf_json_key",
    "gnmi_path", "netconf_container", "netconf_namespace", "netconf_keys",
    "constraints", "description", "sensitive",
}
_ALLOWED_CONSTRAINTS = {"min", "max", "max_length", "enum"}


class VendorModelError(ValueError):
    pass


def _base_spec(vendor: str, os_family: str) -> dict:
    return {
        "vendor": vendor,
        "os_family": os_family,
        "description": "OpenConfig resource mapping with vendor qualification pending",
        "resources": {
            "system_hostname": {
                "description": "System hostname",
                "value_type": "string",
                "constraints": {"max_length": 253},
                "restconf_path": "/restconf/data/openconfig-system:system/config/hostname",
                "restconf_json_key": "openconfig-system:hostname",
                "gnmi_path": "/system/config/hostname",
                "netconf_container": ["system", "config", "hostname"],
                "netconf_namespace": "http://openconfig.net/yang/system",
            },
            "interface_description": {
                "description": "Interface description",
                "value_type": "string",
                "constraints": {"max_length": 1024},
                "selectors": ["interface"],
                "restconf_path": "/restconf/data/openconfig-interfaces:interfaces/interface={interface}/config/description",
                "restconf_json_key": "openconfig-interfaces:description",
                "gnmi_path": "/interfaces/interface[name={interface}]/config/description",
                "netconf_container": ["interfaces", "interface", "config", "description"],
                "netconf_namespace": "http://openconfig.net/yang/interfaces",
                "netconf_keys": {"interface": ["interfaces", "interface", "name"]},
            },
            "interface_enabled": {
                "description": "Interface administrative enabled state",
                "value_type": "boolean",
                "selectors": ["interface"],
                "restconf_path": "/restconf/data/openconfig-interfaces:interfaces/interface={interface}/config/enabled",
                "restconf_json_key": "openconfig-interfaces:enabled",
                "gnmi_path": "/interfaces/interface[name={interface}]/config/enabled",
                "netconf_container": ["interfaces", "interface", "config", "enabled"],
                "netconf_namespace": "http://openconfig.net/yang/interfaces",
                "netconf_keys": {"interface": ["interfaces", "interface", "name"]},
            },
            "interface_mtu": {
                "description": "Interface MTU",
                "value_type": "integer",
                "constraints": {"min": 576, "max": 9216},
                "selectors": ["interface"],
                "restconf_path": "/restconf/data/openconfig-interfaces:interfaces/interface={interface}/config/mtu",
                "restconf_json_key": "openconfig-interfaces:mtu",
                "gnmi_path": "/interfaces/interface[name={interface}]/config/mtu",
                "netconf_container": ["interfaces", "interface", "config", "mtu"],
                "netconf_namespace": "http://openconfig.net/yang/interfaces",
                "netconf_keys": {"interface": ["interfaces", "interface", "name"]},
            },
        },
    }


BUILTIN_PACKS = {
    "generic-openconfig": _base_spec("generic", "openconfig"),
    "cisco-iosxe-openconfig": _base_spec("cisco", "ios-xe"),
    "juniper-junos-openconfig": _base_spec("juniper", "junos"),
    "arista-eos-openconfig": _base_spec("arista", "eos"),
    "huawei-vrp-openconfig": _base_spec("huawei", "vrp"),
}


def _safe_selector(value: object) -> str:
    text = str(value or "").strip()
    if not text or len(text.encode("utf-8")) > 128 or not _IDENT.fullmatch(text):
        raise VendorModelError("selector value is outside the safe identifier grammar")
    return text


def _coerce(value, value_type: str, constraints: dict | None = None):
    constraints = constraints or {}
    if value_type == "string":
        text = str(value)
        max_length = min(4096, max(1, int(constraints.get("max_length", 4096))))
        if len(text.encode("utf-8")) > max_length or "\x00" in text:
            raise VendorModelError("string value exceeds safe bounds")
        enum = constraints.get("enum")
        if enum is not None and text not in enum:
            raise VendorModelError("string value is not in the model-pack enum")
        return text
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"true", "1"}:
            return True
        if str(value).lower() in {"false", "0"}:
            return False
        raise VendorModelError("boolean value must be true/false")
    if value_type == "integer":
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise VendorModelError("integer value required") from exc
        low = max(-(2**31), int(constraints.get("min", -(2**31))))
        high = min(2**31 - 1, int(constraints.get("max", 2**31 - 1)))
        if number < low or number > high:
            raise VendorModelError("integer value is outside model-pack bounds")
        return number
    raise VendorModelError("unsupported model-pack value type")


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{([A-Za-z][A-Za-z0-9_.-]{0,63})\}", text or ""))


def _validate_restconf_path(path: str, selectors: tuple[str, ...]) -> str:
    if not isinstance(path, str) or len(path) > 2048 or any(ch in path for ch in "\x00\r\n"):
        raise VendorModelError("invalid RESTCONF model path")
    if urllib.parse.urlsplit(path).scheme or urllib.parse.urlsplit(path).netloc or "?" in path or "#" in path:
        raise VendorModelError("RESTCONF model path must be an absolute /restconf/data path without query or URL authority")
    if not path.startswith("/restconf/data/"):
        raise VendorModelError("RESTCONF model path must remain below /restconf/data")
    if _placeholders(path) != set(selectors):
        raise VendorModelError("RESTCONF placeholders must exactly match resource selectors")
    rendered = path
    for key in selectors:
        rendered = rendered.replace("{" + key + "}", "safe-id")
    # Reject traversal even after percent decoding.
    decoded = urllib.parse.unquote(rendered)
    if "/../" in decoded or decoded.endswith("/..") or "/./" in decoded:
        raise VendorModelError("RESTCONF model path contains traversal")
    return path


def _validate_gnmi_path(path: str, selectors: tuple[str, ...]) -> str:
    if not isinstance(path, str) or len(path) > 2048 or _placeholders(path) != set(selectors):
        raise VendorModelError("gNMI placeholders must exactly match resource selectors")
    rendered = path
    for key in selectors:
        rendered = rendered.replace("{" + key + "}", "safe-id")
    try:
        from .structured_protocols import GnmiPath
        GnmiPath.parse(rendered)
    except Exception as exc:
        raise VendorModelError("invalid typed gNMI model path") from exc
    return path


def _validate_resource(resource: str, raw: dict) -> dict:
    if not _NAME.fullmatch(str(resource or "")):
        raise VendorModelError("invalid model-pack resource name")
    if not isinstance(raw, dict) or set(raw) - _ALLOWED_RESOURCE_FIELDS:
        raise VendorModelError(f"resource {resource} contains unsupported fields")
    value_type = str(raw.get("value_type") or "string")
    if value_type not in _ALLOWED_TYPES:
        raise VendorModelError(f"resource {resource} uses an unsupported value type")
    selectors_raw = raw.get("selectors") or []
    if not isinstance(selectors_raw, list) or len(selectors_raw) > 8:
        raise VendorModelError(f"resource {resource} selectors are invalid")
    selectors = tuple(str(x) for x in selectors_raw)
    if len(set(selectors)) != len(selectors) or any(not _NAME.fullmatch(x) for x in selectors):
        raise VendorModelError(f"resource {resource} selector names are invalid")
    constraints = raw.get("constraints") or {}
    if not isinstance(constraints, dict) or set(constraints) - _ALLOWED_CONSTRAINTS:
        raise VendorModelError(f"resource {resource} constraints are invalid")
    if "enum" in constraints:
        enum = constraints["enum"]
        if not isinstance(enum, list) or not enum or len(enum) > 128 or any(not isinstance(x, str) for x in enum):
            raise VendorModelError(f"resource {resource} enum is invalid")
    if raw.get("sensitive"):
        # The current PH-4 durable transaction ledger intentionally stores typed
        # before/after scalar values so it can perform compensating rollback.
        # Secret-bearing resources therefore fail closed until a write-only
        # secret transaction contract exists.
        raise VendorModelError("sensitive model-pack resources are not supported by PH-4")

    out = {
        "description": str(raw.get("description") or "")[:512],
        "value_type": value_type,
        "selectors": list(selectors),
        "constraints": constraints,
        "sensitive": False,
    }
    mappings = 0
    if raw.get("restconf_path"):
        out["restconf_path"] = _validate_restconf_path(str(raw["restconf_path"]), selectors)
        key = str(raw.get("restconf_json_key") or "").strip()
        if not key or len(key) > 256 or any(ch in key for ch in "\x00\r\n{}[]"):
            raise VendorModelError(f"resource {resource} requires a bounded restconf_json_key")
        out["restconf_json_key"] = key
        mappings += 1
    if raw.get("gnmi_path"):
        out["gnmi_path"] = _validate_gnmi_path(str(raw["gnmi_path"]), selectors)
        mappings += 1
    if raw.get("netconf_container"):
        container = raw["netconf_container"]
        namespace = str(raw.get("netconf_namespace") or "")
        if not isinstance(container, list) or not container or len(container) > 12:
            raise VendorModelError(f"resource {resource} NETCONF container is invalid")
        if any(not _ELEMENT.fullmatch(str(x)) for x in container) or not _NAMESPACE.fullmatch(namespace):
            raise VendorModelError(f"resource {resource} NETCONF element/namespace is invalid")
        keys = raw.get("netconf_keys") or {}
        if not isinstance(keys, dict) or set(keys) - set(selectors):
            raise VendorModelError(f"resource {resource} NETCONF keys are invalid")
        clean_keys = {}
        for selector, key_path in keys.items():
            if not isinstance(key_path, list) or not key_path or len(key_path) > 12:
                raise VendorModelError(f"resource {resource} NETCONF key path is invalid")
            if any(not _ELEMENT.fullmatch(str(x)) for x in key_path):
                raise VendorModelError(f"resource {resource} NETCONF key element is invalid")
            if key_path[:-1] != container[:len(key_path)-1]:
                raise VendorModelError(f"resource {resource} NETCONF key must remain inside its resource tree")
            clean_keys[selector] = list(key_path)
        if set(selectors) != set(clean_keys):
            raise VendorModelError(f"resource {resource} NETCONF mapping must key every selector")
        out.update({"netconf_container": list(container), "netconf_namespace": namespace,
                    "netconf_keys": clean_keys})
        mappings += 1
    if not mappings:
        raise VendorModelError(f"resource {resource} has no structured protocol mapping")
    return out


def validate_pack_spec(spec: dict) -> dict:
    if not isinstance(spec, dict) or set(spec) - {"vendor", "os_family", "description", "resources"}:
        raise VendorModelError("model-pack spec contains unsupported fields")
    vendor = str(spec.get("vendor") or "").strip().lower()
    os_family = str(spec.get("os_family") or "").strip().lower()
    if not _NAME.fullmatch(vendor) or not _NAME.fullmatch(os_family):
        raise VendorModelError("model-pack vendor/os_family must use safe identifiers")
    resources = spec.get("resources")
    if not isinstance(resources, dict) or not resources or len(resources) > 256:
        raise VendorModelError("model-pack requires 1..256 resources")
    clean_resources = {name: _validate_resource(name, value) for name, value in resources.items()}
    return {
        "vendor": vendor,
        "os_family": os_family,
        "description": str(spec.get("description") or "")[:1024],
        "resources": clean_resources,
    }


def _spec_hash(spec: dict) -> str:
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class VendorModelRegistry:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn
        self.ensure_builtins()

    def ensure_builtins(self):
        now = time.time()
        for name, raw in BUILTIN_PACKS.items():
            spec = validate_pack_spec(raw)
            payload = json.dumps(spec, sort_keys=True)
            self.conn.execute(
                "INSERT OR IGNORE INTO vendor_model_packs "
                "(name,vendor,os_family,revision,builtin,enabled,spec_json,updated_ts) VALUES (?,?,?,?,1,1,?,?)",
                (name, spec["vendor"], spec["os_family"], "1", payload, now),
            )
            self.conn.execute(
                "UPDATE vendor_model_packs SET vendor=?,os_family=?,revision=?,builtin=1,spec_json=?,updated_ts=? "
                "WHERE name=? AND builtin=1",
                (spec["vendor"], spec["os_family"], "1", payload, now, name),
            )
        self.conn.commit()

    def list(self):
        rows = self.conn.execute(
            "SELECT name,vendor,os_family,revision,builtin,enabled,updated_ts,spec_json "
            "FROM vendor_model_packs ORDER BY name"
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            spec = json.loads(item.pop("spec_json"))
            item["resource_count"] = len(spec.get("resources", {}))
            item["sha256"] = _spec_hash(spec)
            out.append(item)
        return out

    def get(self, name):
        row = self.conn.execute("SELECT * FROM vendor_model_packs WHERE name=?", (name,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["spec"] = json.loads(out.pop("spec_json"))
        out["sha256"] = _spec_hash(out["spec"])
        return out

    def create(self, *, name: str, revision: str, spec: dict, actor: str):
        name = str(name or "").strip()
        revision = str(revision or "").strip()
        if not _NAME.fullmatch(name) or not revision or len(revision) > 64:
            raise VendorModelError("invalid model-pack name or revision")
        if self.get(name):
            raise VendorModelError("model-pack name already exists")
        clean = validate_pack_spec(spec)
        now = time.time()
        self.conn.execute(
            "INSERT INTO vendor_model_packs(name,vendor,os_family,revision,builtin,enabled,spec_json,updated_ts) "
            "VALUES(?,?,?,?,0,1,?,?)",
            (name, clean["vendor"], clean["os_family"], revision, json.dumps(clean, sort_keys=True), now),
        )
        self.conn.commit()
        self.manager.db.audit(actor, "vendor_model_create", name,
                              f"revision={revision};sha256={_spec_hash(clean)};resources={len(clean['resources'])}")
        return self.get(name)

    def set_enabled(self, name: str, enabled: bool, actor: str):
        item = self.get(name)
        if not item:
            raise VendorModelError("unknown model pack")
        self.conn.execute("UPDATE vendor_model_packs SET enabled=?,updated_ts=? WHERE name=?",
                          (int(bool(enabled)), time.time(), name))
        self.conn.commit()
        self.manager.db.audit(actor, "vendor_model_enable", name, f"enabled={int(bool(enabled))}")
        return self.get(name)

    def delete(self, name: str, actor: str):
        item = self.get(name)
        if not item:
            raise VendorModelError("unknown model pack")
        if item.get("builtin"):
            raise VendorModelError("built-in model packs cannot be deleted")
        count = self.conn.execute(
            "SELECT COUNT(*) AS n FROM device_model_bindings WHERE pack_name=?", (name,)).fetchone()["n"]
        if count:
            raise VendorModelError("model pack is still bound to devices")
        self.conn.execute("DELETE FROM vendor_model_packs WHERE name=?", (name,))
        self.conn.commit()
        self.manager.db.audit(actor, "vendor_model_delete", name, f"revision={item['revision']}")

    def bind(self, device: str, pack_name: str, actor: str = "system"):
        if not self.manager.inv.get(device):
            raise VendorModelError("unknown device")
        pack = self.get(pack_name)
        if not pack or not pack.get("enabled"):
            raise VendorModelError("unknown or disabled model pack")
        self.conn.execute(
            "INSERT OR REPLACE INTO device_model_bindings (device,pack_name,updated_ts) VALUES (?,?,?)",
            (device, pack_name, time.time()),
        )
        self.conn.commit()
        self.manager.db.audit(actor, "vendor_model_bind", device, f"pack={pack_name};sha256={pack['sha256']}")
        return {"device": device, "pack_name": pack_name, "pack_sha256": pack["sha256"]}

    def unbind(self, device: str, actor: str = "system"):
        self.conn.execute("DELETE FROM device_model_bindings WHERE device=?", (device,))
        self.conn.commit()
        self.manager.db.audit(actor, "vendor_model_unbind", device, "")

    def list_bindings(self):
        rows = self.conn.execute(
            "SELECT device,pack_name,updated_ts FROM device_model_bindings ORDER BY device"
        ).fetchall()
        return [dict(row) for row in rows]

    def binding_detail(self, device: str):
        if not self.manager.inv.get(device):
            raise VendorModelError("unknown device")
        row = self.conn.execute(
            "SELECT device,pack_name,updated_ts FROM device_model_bindings WHERE device=?",
            (device,),
        ).fetchone()
        effective = self.binding(device)
        pack = self.get(effective)
        return {
            "device": device,
            "explicit": bool(row),
            "pack_name": effective,
            "updated_ts": float(row["updated_ts"]) if row else 0,
            "pack_sha256": (pack or {}).get("sha256", ""),
            "enabled": bool((pack or {}).get("enabled")),
        }

    def binding(self, device: str) -> str:
        row = self.conn.execute("SELECT pack_name FROM device_model_bindings WHERE device=?", (device,)).fetchone()
        if row:
            return row["pack_name"]
        dev = self.manager.inv.get(device) or {}
        platform = str(dev.get("platform") or "").lower()
        candidates = (
            ("cisco", "cisco-iosxe-openconfig"), ("ios", "cisco-iosxe-openconfig"),
            ("junos", "juniper-junos-openconfig"), ("juniper", "juniper-junos-openconfig"),
            ("arista", "arista-eos-openconfig"), ("eos", "arista-eos-openconfig"),
            ("huawei", "huawei-vrp-openconfig"), ("vrp", "huawei-vrp-openconfig"),
        )
        for token, name in candidates:
            if token in platform:
                return name
        return "generic-openconfig"

    def resources(self, device: str, protocol: str | None = None):
        pack = self.get(self.binding(device))
        if not pack or not pack.get("enabled"):
            raise VendorModelError("device model pack is missing or disabled")
        out = []
        mapping_key = {"netconf": "netconf_container", "restconf": "restconf_path", "gnmi": "gnmi_path"}.get(protocol or "")
        for name, spec in sorted(pack["spec"].get("resources", {}).items()):
            if mapping_key and not spec.get(mapping_key):
                continue
            out.append({"name": name, "description": spec.get("description", ""),
                        "value_type": spec.get("value_type", "string"),
                        "selectors": spec.get("selectors", []), "constraints": spec.get("constraints", {})})
        return {"device": device, "pack": pack["name"], "pack_sha256": pack["sha256"], "resources": out}

    def resolve(self, device: str, resource: str, selectors: dict, value, protocol: str | None = None):
        pack_name = self.binding(device)
        pack = self.get(pack_name)
        if not pack or not pack.get("enabled"):
            raise VendorModelError("bound model pack is missing or disabled")
        spec = pack["spec"].get("resources", {}).get(str(resource or ""))
        if not isinstance(spec, dict):
            raise VendorModelError("resource is not allow-listed by the device model pack")
        required = tuple(spec.get("selectors") or ())
        selectors = selectors or {}
        safe = {}
        for key in required:
            if key not in selectors:
                raise VendorModelError(f"missing selector: {key}")
            safe[key] = _safe_selector(selectors[key])
        if set(selectors) - set(required):
            raise VendorModelError("unexpected selector for resource")
        typed_value = _coerce(value, spec.get("value_type", "string"), spec.get("constraints") or {})
        mapping_key = {"netconf": "netconf_container", "restconf": "restconf_path", "gnmi": "gnmi_path"}.get(protocol or "")
        if mapping_key and not spec.get(mapping_key):
            raise VendorModelError(f"resource is not mapped for configured {protocol} transport")

        rest = str(spec.get("restconf_path") or "")
        gnmi = str(spec.get("gnmi_path") or "")
        for key, val in safe.items():
            rest = rest.replace("{" + key + "}", urllib.parse.quote(val, safe="-._~"))
            gnmi = gnmi.replace("{" + key + "}", val)
        return {
            "pack": pack_name,
            "pack_sha256": pack["sha256"],
            "resource": resource,
            "selectors": safe,
            "value": typed_value,
            "value_type": spec.get("value_type", "string"),
            "constraints": dict(spec.get("constraints") or {}),
            "sensitive": bool(spec.get("sensitive")),
            "restconf_path": rest,
            "restconf_json_key": str(spec.get("restconf_json_key") or ""),
            "gnmi_path": gnmi,
            "netconf_container": list(spec.get("netconf_container") or ()),
            "netconf_keys": dict(spec.get("netconf_keys") or {}),
            "netconf_namespace": str(spec.get("netconf_namespace") or ""),
        }
