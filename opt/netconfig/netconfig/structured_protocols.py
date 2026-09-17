"""Platform Hardening PH-3 structured network-management adapters.

The adapters deliberately expose a *bounded internal contract*, not generic
protocol passthrough:

* NETCONF: hello/capability negotiation plus fixed ``<get>`` and
  ``<get-config>`` RPCs.  No caller supplied RPC XML is accepted.
* RESTCONF: HTTPS discovery/read operations under a strict path allow-list and
  an internal, approval-gated JSON subtree replace primitive with pre/post
  verification and best-effort pre-image rollback.  No arbitrary URL/method/
  body forwarding is exposed by the Web/API/CLI surfaces.
* gNMI: Capabilities, Get and bounded ONCE Subscribe through an allow-resolved
  ``gnmic`` binary.  Paths are parsed into a typed representation before they
  reach the process argv.  gNMI Set is intentionally not exposed.

Profiles contain references and non-secret transport policy only.  Credentials
are resolved from the encrypted vault at execution time.  Diagnostic protocol
trace integration records metadata only; raw protocol payloads and secrets are
never written to trace evidence.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .transport import SSHTransport


PROTOCOLS = ("cli_ssh", "netconf", "restconf", "gnmi")
DEFAULT_PORTS = {"cli_ssh": 22, "netconf": 830, "restconf": 443, "gnmi": 57400}
MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_XML_NODES = 100_000
MAX_XML_DEPTH = 64
MAX_GNMI_PATH_BYTES = 2048
NETCONF_BASE10 = "urn:ietf:params:netconf:base:1.0"
NETCONF_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"
_NETCONF_DELIM = b"]]>]]>"
_DNS_LABEL = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)$")
_GNMI_NAME = r"[A-Za-z_][A-Za-z0-9_.:-]*"
_GNMI_KEY = re.compile(rf"^{_GNMI_NAME}=([^\]\x00-\x1f]{{1,256}})$")
_GNMI_SEGMENT = re.compile(rf"^(?P<name>{_GNMI_NAME})(?P<keys>(?:\[[^\]]+\])*)$")
_GNMI_KEY_BLOCK = re.compile(r"\[([^\]]+)\]")
_ALLOWED_RESTCONF_QUERY = {"content", "depth", "fields", "with-defaults", "insert", "point"}
_ALLOWED_RESTCONF_CONTENT = {"config", "nonconfig", "all"}


class StructuredProtocolError(RuntimeError):
    """Fail-closed structured-adapter error with secret-safe messages."""


@dataclass(frozen=True)
class GnmiPathElem:
    name: str
    keys: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class GnmiPath:
    """Validated gNMI path used instead of arbitrary caller-supplied proto data."""

    elems: tuple[GnmiPathElem, ...]

    @classmethod
    def parse(cls, value: str | None) -> "GnmiPath":
        raw = str(value or "/").strip()
        if not raw.startswith("/") or len(raw.encode("utf-8")) > MAX_GNMI_PATH_BYTES:
            raise ValueError("gNMI path must be an absolute bounded path")
        if any(ord(c) < 0x20 for c in raw) or "//" in raw or raw.endswith("/.") or "/../" in raw:
            raise ValueError("invalid gNMI path")
        if raw == "/":
            return cls(())
        elems = []
        for segment in raw[1:].split("/"):
            if segment in {"", ".", ".."}:
                raise ValueError("invalid gNMI path segment")
            m = _GNMI_SEGMENT.fullmatch(segment)
            if not m:
                raise ValueError("invalid gNMI path segment")
            keys = []
            for block in _GNMI_KEY_BLOCK.findall(m.group("keys") or ""):
                km = _GNMI_KEY.fullmatch(block)
                if not km:
                    raise ValueError("invalid gNMI path key predicate")
                key, val = block.split("=", 1)
                if not val or len(val.encode("utf-8")) > 256:
                    raise ValueError("invalid gNMI path key value")
                keys.append((key, val))
            elems.append(GnmiPathElem(m.group("name"), tuple(keys)))
        return cls(tuple(elems))

    def render(self) -> str:
        if not self.elems:
            return "/"
        parts = []
        for elem in self.elems:
            keys = "".join(f"[{k}={v}]" for k, v in elem.keys)
            parts.append(elem.name + keys)
        return "/" + "/".join(parts)

    def as_dict(self) -> dict:
        return {"elem": [{"name": e.name, "key": dict(e.keys)} for e in self.elems]}


def _bool(value):
    return bool(int(value)) if isinstance(value, (int, str)) and str(value).isdigit() else bool(value)


def _secret_values(secret):
    values = []
    for value in (secret or {}).values():
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _redact_text(text, *secrets):
    out = str(text or "")
    for secret in secrets:
        if secret:
            out = out.replace(str(secret), "<redacted>")
    return out


def _validate_host(host):
    value = str(host or "").strip()
    if not value or len(value) > 253:
        raise StructuredProtocolError("invalid structured-protocol host")
    if any(ord(c) < 0x21 or ord(c) == 0x7F for c in value):
        raise StructuredProtocolError("invalid structured-protocol host")
    if any(ch in value for ch in "/\\@?#"):
        raise StructuredProtocolError("invalid structured-protocol host")
    candidate = value[1:-1] if value.startswith("[") and value.endswith("]") else value
    try:
        ip = ipaddress.ip_address(candidate)
        if ip.is_unspecified or ip.is_multicast:
            raise StructuredProtocolError("structured-protocol host is not a unicast address")
        return candidate
    except ValueError:
        pass
    dns = candidate[:-1] if candidate.endswith(".") else candidate
    if not dns or len(dns) > 253 or any(not _DNS_LABEL.fullmatch(x) for x in dns.split(".")):
        raise StructuredProtocolError("invalid structured-protocol DNS host")
    return dns


def _https_host(host):
    validated = _validate_host(host)
    try:
        ip = ipaddress.ip_address(validated)
    except ValueError:
        return validated
    return f"[{validated}]" if ip.version == 6 else validated


def _validate_abs_file(path, label, *, require_exists=False):
    value = str(path or "").strip()
    if not value:
        return ""
    if not os.path.isabs(value) or "\x00" in value:
        raise StructuredProtocolError(f"{label} must be an absolute path")
    if require_exists and not os.path.isfile(value):
        raise StructuredProtocolError(f"{label} is not a readable file")
    return value


def _tls_verify_allowed(verify):
    if verify:
        return
    if os.environ.get("NETCONFIG_ALLOW_INSECURE_STRUCTURED_TLS") != "1":
        raise StructuredProtocolError(
            "TLS verification cannot be disabled unless NETCONFIG_ALLOW_INSECURE_STRUCTURED_TLS=1 is explicitly set for a lab")


def _safe_xml_parse(payload, *, label="XML"):
    raw = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise StructuredProtocolError(f"{label} exceeds {MAX_PAYLOAD_BYTES // (1024 * 1024)} MiB limit")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise StructuredProtocolError(f"{label} contains forbidden DTD/entity declarations")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise StructuredProtocolError(f"malformed {label}: {exc}") from exc
    nodes = 0
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_XML_NODES:
            raise StructuredProtocolError(f"{label} exceeds XML node limit")
        if depth > MAX_XML_DEPTH:
            raise StructuredProtocolError(f"{label} exceeds XML depth limit")
        if len(node.attrib) > 256:
            raise StructuredProtocolError(f"{label} element has too many attributes")
        stack.extend((child, depth + 1) for child in list(node))
    return root


def _decode_structured_payload(raw, ctype, *, label):
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise StructuredProtocolError(f"{label} exceeds 16 MiB limit")
    text = raw.decode("utf-8", "strict")
    media = str(ctype or "application/octet-stream").split(";", 1)[0].strip().lower()
    if "json" in media:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StructuredProtocolError(f"malformed {label} JSON: {exc}") from exc
        return text, value, media
    if "xml" in media or media in {"application/yang-data+xml", "application/xrd+xml"}:
        return text, _safe_xml_parse(raw, label=label), media
    raise StructuredProtocolError(f"unsupported {label} content type: {media}")


def _restconf_path(path, *, discovery=False, require_data=False):
    value = str(path or "").strip()
    if not value.startswith("/") or len(value) > 4096:
        raise ValueError("RESTCONF path must be a bounded absolute path")
    split = urllib.parse.urlsplit(value)
    if split.scheme or split.netloc or split.fragment:
        raise ValueError("RESTCONF path must not contain a scheme, authority, or fragment")
    decoded = urllib.parse.unquote(split.path)
    if "\\" in decoded or any(ord(c) < 0x20 for c in decoded):
        raise ValueError("invalid RESTCONF path")
    if discovery and decoded == "/.well-known/host-meta":
        allowed = True
    else:
        allowed = decoded == "/restconf" or decoded.startswith("/restconf/")
    if not allowed:
        raise ValueError("RESTCONF path must remain below /restconf or the well-known discovery endpoint")
    if require_data and not (decoded == "/restconf/data" or decoded.startswith("/restconf/data/")):
        raise ValueError("RESTCONF configuration path must remain below /restconf/data")
    query = urllib.parse.parse_qs(split.query, keep_blank_values=True, strict_parsing=False)
    if any(key not in _ALLOWED_RESTCONF_QUERY for key in query):
        raise ValueError("RESTCONF query contains an unsupported parameter")
    if "content" in query and any(v not in _ALLOWED_RESTCONF_CONTENT for v in query["content"]):
        raise ValueError("RESTCONF content query value is unsupported")
    if any(len(v) != 1 for v in query.values()):
        raise ValueError("duplicate RESTCONF query parameters are not supported")
    return urllib.parse.urlunsplit(("", "", split.path, split.query, ""))


def _netconf_caps_from_hello(raw):
    body = raw[:-len(_NETCONF_DELIM)] if raw.endswith(_NETCONF_DELIM) else raw
    root = _safe_xml_parse(body, label="NETCONF hello")
    if root.tag.split("}")[-1] != "hello":
        raise StructuredProtocolError("NETCONF subsystem did not return a hello message")
    caps = sorted({(c.text or "").strip() for c in root.findall(".//{*}capability") if (c.text or "").strip()})
    if NETCONF_BASE10 not in caps:
        raise StructuredProtocolError("NETCONF server does not advertise base:1.0; base:1.1-only framing is unsupported")
    return caps


def _cap_contains(caps, token):
    return any(token in cap for cap in caps)


def _normalize_netconf_caps(caps):
    return {
        "raw": caps,
        "base_1_0": NETCONF_BASE10 in caps,
        "candidate": _cap_contains(caps, ":candidate"),
        "writable_running": _cap_contains(caps, ":writable-running"),
        "confirmed_commit": _cap_contains(caps, ":confirmed-commit"),
        "rollback_on_error": _cap_contains(caps, ":rollback-on-error"),
        "validate": _cap_contains(caps, ":validate"),
        "startup": _cap_contains(caps, ":startup"),
        "xpath": _cap_contains(caps, ":xpath"),
    }


class ProtocolProfiles:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn

    @staticmethod
    def _row(row):
        if not row:
            return None
        d = dict(row)
        for key in ("enabled", "tls_verify", "allow_cli_fallback"):
            d[key] = bool(d.get(key))
        return d

    def get(self, device):
        return self._row(self.conn.execute(
            "SELECT * FROM protocol_profiles WHERE device=?", (device,)).fetchone())

    def list(self):
        return [self._row(r) for r in self.conn.execute(
            "SELECT * FROM protocol_profiles ORDER BY device").fetchall()]

    def set(self, device, protocol, *, enabled=True, port=0, path="", secret_ref="",
            tls_verify=True, ca_file="", allow_cli_fallback=False):
        dev = self.manager.inv.get(device)
        if not dev:
            raise ValueError("unknown device")
        _validate_host(dev.get("host"))
        protocol = str(protocol or "").strip().lower()
        if protocol not in PROTOCOLS:
            raise ValueError("unsupported protocol")
        port = int(port or DEFAULT_PORTS[protocol])
        if port < 1 or port > 65535:
            raise ValueError("invalid protocol port")
        path = str(path or "").strip()
        if protocol == "restconf":
            path = _restconf_path(path or "/restconf/data?content=config", require_data=True)
        elif protocol == "gnmi":
            path = GnmiPath.parse(path or "/").render()
        elif path:
            raise ValueError("path is only valid for RESTCONF/gNMI profiles")
        ca_file = str(ca_file or "").strip()
        if ca_file and not os.path.isabs(ca_file):
            raise ValueError("CA file must be an absolute path")
        if protocol in {"restconf", "gnmi"}:
            try:
                _tls_verify_allowed(bool(tls_verify))
            except StructuredProtocolError as exc:
                raise ValueError(str(exc)) from exc
        now = time.time()
        self.conn.execute(
            "INSERT OR REPLACE INTO protocol_profiles "
            "(device,protocol,enabled,port,path,secret_ref,tls_verify,ca_file,allow_cli_fallback,updated_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (device, protocol, int(bool(enabled)), port, path, str(secret_ref or "").strip(),
             int(bool(tls_verify)), ca_file, int(bool(allow_cli_fallback)), now))
        self.conn.commit()
        self.manager.db.audit("system", "protocol_profile_set", device,
                              f"protocol={protocol};enabled={int(bool(enabled))};fallback={int(bool(allow_cli_fallback))}")
        return self.get(device)

    def delete(self, device):
        self.conn.execute("DELETE FROM protocol_profiles WHERE device=?", (device,))
        self.conn.commit()

    def rename(self, old, new):
        self.conn.execute("UPDATE protocol_profiles SET device=? WHERE device=?", (new, old))
        self.conn.commit()


class StructuredCollector:
    def __init__(self, manager):
        self.manager = manager

    def _secret(self, device, profile, *, require_username=False, require_password=False):
        ref = profile.get("secret_ref") or device.get("secret_ref")
        if not ref:
            raise StructuredProtocolError("structured protocol profile requires a vault secret reference")
        if not self.manager._vault_unlocked:
            raise StructuredProtocolError("vault locked")
        try:
            sec = self.manager.vault.get_secret(ref)
        except KeyError as exc:
            raise StructuredProtocolError("vault secret reference does not exist") from exc
        if require_username and not sec.get("username"):
            raise StructuredProtocolError("protocol credential has no username")
        if require_password and not sec.get("password"):
            raise StructuredProtocolError("protocol requires a password in the vault secret")
        return sec

    def _trace(self, device, protocol, event_type, started, *, operation=None,
               status="ok", tx=0, rx=0, **meta):
        safe_meta = {}
        for key, value in meta.items():
            if key.lower() in {"password", "username", "authorization", "body", "payload", "rpc", "proto"}:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe_meta[key] = value
        try:
            self.manager.protocol_traces.record(
                device["name"], protocol, event_type,
                operation=operation or f"{protocol} structured operation",
                status=status, duration_ms=(time.monotonic() - started) * 1000,
                tx_bytes=tx, rx_bytes=rx, metadata=safe_meta)
        except Exception:
            pass

    def _audit(self, actor, action, device, protocol, status, detail=""):
        safe = f"protocol={protocol};status={status}"
        if detail:
            safe += ";" + str(detail)[:300]
        try:
            self.manager.db.audit(actor or "system", action, device["name"], safe)
        except Exception:
            pass

    def collect(self, device, profile):
        protocol = profile.get("protocol")
        if protocol == "netconf":
            return self._netconf_read(device, profile, operation="get-config", datastore="running")
        if protocol == "restconf":
            discovery = self._restconf_discover(device, profile)
            text, meta = self._restconf_get(device, profile, profile.get("path") or "/restconf/data?content=config")
            meta["capabilities"] = discovery
            return text, meta
        if protocol == "gnmi":
            caps = self._gnmi_capabilities(device, profile)
            text, meta = self._gnmi_get(device, profile, profile.get("path") or "/", data_type="CONFIG")
            meta["capabilities"] = caps
            return text, meta
        raise StructuredProtocolError(f"no structured collector for {protocol}")

    def capabilities(self, device, profile):
        protocol = profile.get("protocol")
        if protocol == "netconf":
            return self._netconf_capabilities(device, profile)
        if protocol == "restconf":
            return self._restconf_discover(device, profile)
        if protocol == "gnmi":
            return self._gnmi_capabilities(device, profile)
        if protocol == "cli_ssh":
            return {"protocol": "cli_ssh", "structured": False}
        raise StructuredProtocolError("unsupported protocol")

    def read_config(self, device, profile, *, datastore="running", path=None):
        protocol = profile.get("protocol")
        if protocol == "netconf":
            return self._netconf_read(device, profile, operation="get-config", datastore=datastore)
        if protocol == "restconf":
            return self._restconf_get(device, profile, path or profile.get("path") or "/restconf/data?content=config")
        if protocol == "gnmi":
            return self._gnmi_get(device, profile, path or profile.get("path") or "/", data_type="CONFIG")
        raise StructuredProtocolError("structured config read unsupported for protocol")

    def read_state(self, device, profile, *, path=None):
        protocol = profile.get("protocol")
        if protocol == "netconf":
            return self._netconf_read(device, profile, operation="get")
        if protocol == "restconf":
            p = path or profile.get("path") or "/restconf/data"
            split = urllib.parse.urlsplit(p)
            query = urllib.parse.parse_qs(split.query, keep_blank_values=True)
            query["content"] = ["nonconfig"]
            q = urllib.parse.urlencode({k: v[0] for k, v in query.items()})
            state_path = urllib.parse.urlunsplit(("", "", split.path, q, ""))
            return self._restconf_get(device, profile, state_path)
        if protocol == "gnmi":
            return self._gnmi_get(device, profile, path or profile.get("path") or "/", data_type="STATE")
        raise StructuredProtocolError("structured operational-state read unsupported for protocol")

    def subscribe_once(self, device, profile, *, path=None):
        if profile.get("protocol") != "gnmi":
            raise StructuredProtocolError("bounded Subscribe is only available for gNMI profiles")
        return self._gnmi_subscribe_once(device, profile, path or profile.get("path") or "/")

    def subscribe_window(self, device, profile, *, path=None, mode="ON_CHANGE",
                         duration_seconds=30, sample_interval_ms=10000, heartbeat_interval_ms=0):
        if profile.get("protocol") != "gnmi":
            raise StructuredProtocolError("streaming Subscribe is only available for gNMI profiles")
        return self._gnmi_subscribe_window(
            device, profile, path or profile.get("path") or "/", mode=mode,
            duration_seconds=duration_seconds, sample_interval_ms=sample_interval_ms,
            heartbeat_interval_ms=heartbeat_interval_ms)

    @staticmethod
    def _coerce_observed_scalar(value, value_type):
        if value_type == "boolean":
            if isinstance(value, bool):
                return value
            text = str(value).strip().lower()
            if text in {"true", "1"}:
                return True
            if text in {"false", "0"}:
                return False
            raise StructuredProtocolError("observed structured value is not boolean")
        if value_type == "integer":
            if isinstance(value, bool):
                raise StructuredProtocolError("observed structured value is not integer")
            try:
                return int(value)
            except (TypeError, ValueError) as exc:
                raise StructuredProtocolError("observed structured value is not integer") from exc
        if value_type == "string":
            if isinstance(value, (dict, list)):
                raise StructuredProtocolError("observed structured value is not scalar text")
            return str(value)
        raise StructuredProtocolError("unsupported model-pack value type")

    @classmethod
    def _extract_json_scalar(cls, value, *, value_type, leaf_hint=""):
        """Extract one scalar from an exact structured-resource response.

        gNMI/RESTCONF implementations wrap an exact leaf differently.  Prefer a
        matching leaf key (including module-prefixed JSON names), then common
        ``val``/``value`` wrappers, and finally accept exactly one distinct
        scalar in the bounded response.  Ambiguity fails closed.
        """
        hint = str(leaf_hint or "").split(":")[-1]
        preferred = []
        all_scalars = []

        def walk(node, key=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    ktext = str(k)
                    base = ktext.split(":")[-1]
                    if not isinstance(v, (dict, list)):
                        all_scalars.append(v)
                        if base == hint or base in {"val", "value"}:
                            preferred.append(v)
                    else:
                        walk(v, ktext)
            elif isinstance(node, list):
                for item in node:
                    walk(item, key)
            else:
                all_scalars.append(node)
                if key.split(":")[-1] == hint:
                    preferred.append(node)

        walk(value)
        candidates = preferred or all_scalars
        converted = []
        for item in candidates[:4096]:
            try:
                converted.append(cls._coerce_observed_scalar(item, value_type))
            except StructuredProtocolError:
                continue
        distinct = []
        for item in converted:
            if item not in distinct:
                distinct.append(item)
        if len(distinct) != 1:
            raise StructuredProtocolError("structured exact-resource read did not resolve to one unambiguous scalar")
        return distinct[0]

    @staticmethod
    def _resolved_leaf_name(resolved):
        path = list(resolved.get("netconf_container") or ())
        if path:
            return str(path[-1])
        rkey = str(resolved.get("restconf_json_key") or "")
        if rkey:
            return rkey.split(":")[-1]
        try:
            typed = GnmiPath.parse(resolved.get("gnmi_path") or "/")
            return typed.elems[-1].name.split(":")[-1] if typed.elems else ""
        except Exception:
            return ""

    def read_resource_value(self, device, profile, resolved, *, datastore="running"):
        """Read one allow-listed typed scalar for PH-4/NA-1 verification."""
        protocol = profile.get("protocol")
        value_type = resolved.get("value_type", "string")
        leaf = self._resolved_leaf_name(resolved)
        if protocol == "netconf":
            return self._netconf_read_resolved(device, profile, resolved, datastore=datastore)
        if protocol == "restconf":
            path = resolved.get("restconf_path")
            if not path:
                raise StructuredProtocolError("model pack has no RESTCONF mapping for resource")
            raw, ctype, meta = self._restconf_request(device, profile, "GET", path, require_data=True)
            _text, decoded, media = _decode_structured_payload(raw, ctype, label="RESTCONF exact resource")
            value = self._extract_json_scalar(decoded, value_type=value_type, leaf_hint=leaf)
            return value, {"protocol": "restconf", "content_type": media, **meta}
        if protocol == "gnmi":
            path = resolved.get("gnmi_path")
            if not path:
                raise StructuredProtocolError("model pack has no gNMI mapping for resource")
            text, meta = self._gnmi_get(device, profile, path, data_type="CONFIG")
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise StructuredProtocolError("malformed gNMI exact-resource JSON") from exc
            value = self._extract_json_scalar(decoded, value_type=value_type, leaf_hint=leaf)
            return value, meta
        raise StructuredProtocolError("typed resource read requires NETCONF, RESTCONF, or gNMI")

    # ---- NETCONF ---------------------------------------------------------
    def _netconf_transport(self, device, profile, sec):
        _validate_host(device.get("host"))
        return SSHTransport(
            device["host"], sec["username"], port=int(profile.get("port") or 830),
            password=None if sec.get("key_path") else sec.get("password"),
            key_path=sec.get("key_path"), key_passphrase=sec.get("key_passphrase"),
            connect_timeout=self.manager.settings["connect_timeout"],
            command_timeout=self.manager.settings["command_timeout"],
            known_hosts=self.manager.paths.known_hosts,
            host_key_policy=self.manager.settings["host_key_policy"],
            legacy=device.get("legacy", False), subsystem="netconf")

    @staticmethod
    def _netconf_client_hello():
        return (b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">'
                b'<capabilities><capability>urn:ietf:params:netconf:base:1.0</capability>'
                b'</capabilities></hello>]]>]]>')

    def _netconf_open(self, device, profile):
        sec = self._secret(device, profile, require_username=True)
        tp = self._netconf_transport(device, profile, sec)
        delim = re.compile(re.escape(_NETCONF_DELIM))
        try:
            tp.connect(ready_pattern=delim, ready_max_bytes=MAX_PAYLOAD_BYTES)
            hello = getattr(tp, "ready_data", b"")
            caps = _netconf_caps_from_hello(hello)
            client_hello = self._netconf_client_hello()
            tp.write_raw(client_hello)
            return tp, caps, len(client_hello)
        except Exception:
            tp.close()
            raise

    def _netconf_capabilities(self, device, profile):
        started = time.monotonic()
        tp = None
        try:
            tp, caps, tx = self._netconf_open(device, profile)
            normalized = _normalize_netconf_caps(caps)
            self._trace(device, "netconf", "capabilities", started,
                        operation="NETCONF hello/capabilities", tx=tx, capability_count=len(caps))
            self._audit("system", "structured_capabilities", device, "netconf", "ok",
                        f"capability_count={len(caps)}")
            return {"protocol": "netconf", **normalized,
                    "read": {"get": True, "get_config": True},
                    "write": {"generic_passthrough": False,
                              "typed_edit_config": True,
                              "candidate": normalized["candidate"],
                              "rollback_on_error": normalized["rollback_on_error"],
                              "confirmed_commit_available": normalized["confirmed_commit"]}}
        except Exception as exc:
            self._trace(device, "netconf", "capabilities", started,
                        operation="NETCONF hello/capabilities", status="error",
                        error_type=type(exc).__name__)
            self._audit("system", "structured_capabilities", device, "netconf", "error",
                        type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"NETCONF capability negotiation failed: {type(exc).__name__}") from exc
        finally:
            if tp is not None:
                tp.close()

    def _netconf_read(self, device, profile, *, operation, datastore="running"):
        started = time.monotonic()
        tp = None
        rpc = b""
        try:
            tp, caps, hello_tx = self._netconf_open(device, profile)
            normalized = _normalize_netconf_caps(caps)
            if operation == "get":
                body = b"<get/>"
                event_type = "get"
            elif operation == "get-config":
                datastore = str(datastore or "running").lower()
                allowed = {"running"}
                if normalized["candidate"]:
                    allowed.add("candidate")
                if normalized["startup"]:
                    allowed.add("startup")
                if datastore not in allowed:
                    raise StructuredProtocolError(
                        f"NETCONF datastore {datastore!r} is not advertised by the server")
                body = (f"<get-config><source><{datastore}/></source></get-config>").encode()
                event_type = "get_config"
            else:
                raise StructuredProtocolError("unsupported fixed NETCONF read operation")
            rpc = (b'<?xml version="1.0" encoding="UTF-8"?>'
                   b'<rpc xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1">'
                   + body + b"</rpc>" + _NETCONF_DELIM)
            tp.write_raw(rpc)
            raw = tp.read_raw_until(re.compile(re.escape(_NETCONF_DELIM)),
                                    timeout=self.manager.settings["command_timeout"],
                                    max_bytes=MAX_PAYLOAD_BYTES)
            body_raw = raw[:-len(_NETCONF_DELIM)] if raw.endswith(_NETCONF_DELIM) else raw
            root = _safe_xml_parse(body_raw, label="NETCONF rpc-reply")
            if root.tag.split("}")[-1] != "rpc-reply":
                raise StructuredProtocolError("NETCONF response is not an rpc-reply")
            if root.findall(".//{*}rpc-error"):
                raise StructuredProtocolError(f"NETCONF {operation} returned rpc-error")
            text = body_raw.decode("utf-8", "strict").strip()
            self._trace(device, "netconf", event_type, started,
                        operation=f"NETCONF {operation}", tx=hello_tx + len(rpc), rx=len(raw),
                        datastore=datastore if operation == "get-config" else "")
            self._audit("system", "structured_read", device, "netconf", "ok", f"operation={operation}")
            return text, {"protocol": "netconf", "content_type": "application/xml",
                          "operation": operation,
                          "datastore": datastore if operation == "get-config" else None,
                          "capabilities": normalized,
                          "rollback": {"confirmed_commit": normalized["confirmed_commit"],
                                       "rollback_on_error": normalized["rollback_on_error"]}}
        except Exception as exc:
            self._trace(device, "netconf", "get_config" if operation == "get-config" else "get", started,
                        operation=f"NETCONF {operation}", status="error",
                        tx=len(rpc), error_type=type(exc).__name__)
            self._audit("system", "structured_read", device, "netconf", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"NETCONF {operation} failed: {type(exc).__name__}") from exc
        finally:
            if tp is not None:
                tp.close()

    def _netconf_rpc(self, tp, body, *, message_id=10):
        rpc = (b'<?xml version="1.0" encoding="UTF-8"?>'
               + f'<rpc xmlns="{NETCONF_NS}" message-id="{int(message_id)}">'.encode("utf-8")
               + body + b"</rpc>" + _NETCONF_DELIM)
        tp.write_raw(rpc)
        raw = tp.read_raw_until(re.compile(re.escape(_NETCONF_DELIM)),
                                timeout=self.manager.settings["command_timeout"],
                                max_bytes=MAX_PAYLOAD_BYTES)
        payload = raw[:-len(_NETCONF_DELIM)] if raw.endswith(_NETCONF_DELIM) else raw
        root = _safe_xml_parse(payload, label="NETCONF rpc-reply")
        if root.tag.split("}")[-1] != "rpc-reply":
            raise StructuredProtocolError("NETCONF response is not an rpc-reply")
        if root.findall(".//{*}rpc-error"):
            raise StructuredProtocolError("NETCONF write RPC returned rpc-error")
        return payload, len(rpc), len(raw)

    @staticmethod
    def _netconf_model_tree(resolved, *, include_value=True, filter_wrapper=False):
        path = list(resolved.get("netconf_container") or ())
        namespace = str(resolved.get("netconf_namespace") or "")
        if not path or not namespace or len(path) > 12:
            raise StructuredProtocolError("model pack lacks a bounded NETCONF mapping")
        if filter_wrapper:
            root = ET.Element(f"{{{NETCONF_NS}}}filter", {"type": "subtree"})
        else:
            root = ET.Element(f"{{{NETCONF_NS}}}config")
        cur = root
        node_by_path = {}
        walked = []
        for name in path:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,127}", str(name)):
                raise StructuredProtocolError("invalid model-pack NETCONF element")
            walked.append(name)
            cur = ET.SubElement(cur, f"{{{namespace}}}{name}")
            node_by_path[tuple(walked)] = cur
        selectors = resolved.get("selectors") or {}
        for selector, key_path in (resolved.get("netconf_keys") or {}).items():
            if selector not in selectors or not isinstance(key_path, list) or not key_path:
                raise StructuredProtocolError("invalid model-pack NETCONF key mapping")
            parent_path = tuple(key_path[:-1])
            parent = node_by_path.get(parent_path)
            if parent is None:
                raise StructuredProtocolError("NETCONF key mapping is outside the resource tree")
            key_name = key_path[-1]
            key = ET.Element(f"{{{namespace}}}{key_name}")
            key.text = str(selectors[selector])
            parent.insert(0, key)
        if include_value:
            value = resolved.get("value")
            cur.text = "true" if value is True else "false" if value is False else str(value)
        payload = ET.tostring(root, encoding="utf-8")
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise StructuredProtocolError("typed NETCONF configuration/filter exceeds 16 MiB limit")
        return payload

    @classmethod
    def _netconf_typed_config(cls, resolved):
        return cls._netconf_model_tree(resolved, include_value=True, filter_wrapper=False)

    @classmethod
    def _netconf_typed_filter(cls, resolved):
        return cls._netconf_model_tree(resolved, include_value=False, filter_wrapper=True)

    def _netconf_read_resolved_on_session(self, tp, normalized, resolved, *, datastore="running", message_id=31):
        datastore = str(datastore or "running").lower()
        allowed = {"running"}
        if normalized.get("candidate"):
            allowed.add("candidate")
        if normalized.get("startup"):
            allowed.add("startup")
        if datastore not in allowed:
            raise StructuredProtocolError(f"NETCONF datastore {datastore!r} is not advertised by the server")
        filt = self._netconf_typed_filter(resolved)
        body = (b"<get-config><source><" + datastore.encode() + b"/></source>" + filt + b"</get-config>")
        payload, tx, rx = self._netconf_rpc(tp, body, message_id=message_id)
        root = _safe_xml_parse(payload, label="NETCONF exact-resource read")
        leaf = self._resolved_leaf_name(resolved)
        matches = [(e.text or "").strip() for e in root.iter() if e.tag.split("}")[-1] == leaf]
        converted = []
        for item in matches:
            try:
                converted.append(self._coerce_observed_scalar(item, resolved.get("value_type", "string")))
            except StructuredProtocolError:
                continue
        distinct = []
        for item in converted:
            if item not in distinct:
                distinct.append(item)
        if len(distinct) != 1:
            raise StructuredProtocolError("NETCONF exact-resource read did not resolve to one unambiguous scalar")
        return distinct[0], tx, rx

    def _netconf_read_resolved(self, device, profile, resolved, *, datastore="running"):
        started = time.monotonic()
        tp = None
        try:
            tp, caps, hello_tx = self._netconf_open(device, profile)
            normalized = _normalize_netconf_caps(caps)
            value, tx, rx = self._netconf_read_resolved_on_session(
                tp, normalized, resolved, datastore=datastore, message_id=31)
            self._trace(device, "netconf", "get_config", started,
                        operation="NETCONF typed exact-resource read", tx=hello_tx + tx, rx=rx,
                        datastore=datastore, resource=resolved.get("resource"))
            self._audit("system", "structured_read", device, "netconf", "ok",
                        f"operation=typed_resource;resource={resolved.get('resource')};datastore={datastore}")
            return value, {"protocol": "netconf", "operation": "typed_resource", "datastore": datastore,
                           "capabilities": normalized}
        except Exception as exc:
            self._trace(device, "netconf", "get_config", started,
                        operation="NETCONF typed exact-resource read", status="error",
                        resource=resolved.get("resource"), error_type=type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"NETCONF typed exact-resource read failed: {type(exc).__name__}") from exc
        finally:
            if tp is not None:
                tp.close()

    def _netconf_apply_value_on_session(self, tp, normalized, resolved, *, target, message_base=40):
        cfg = self._netconf_typed_config(resolved)
        error_option = b"<error-option>rollback-on-error</error-option>" if normalized.get("rollback_on_error") else b""
        body = (b"<edit-config><target><" + target.encode() + b"/></target>"
                b"<default-operation>merge</default-operation>" + error_option + cfg + b"</edit-config>")
        _reply, tx, rx = self._netconf_rpc(tp, body, message_id=message_base)
        if target == "candidate" and normalized.get("validate"):
            _reply, n, r = self._netconf_rpc(
                tp, b"<validate><source><candidate/></source></validate>", message_id=message_base + 1)
            tx += n; rx += r
        return tx, rx

    def netconf_edit_typed(self, device, profile, *, resolved, actor, approved, before_value=None):
        """Execute one allow-listed typed edit-config transaction.

        Candidate is preferred.  Candidate content is verified before commit.  A
        confirmed commit is used when advertised; otherwise a bounded
        compensating write of the typed pre-image is attempted if post-commit
        verification fails.  Running-only devices must advertise
        ``:rollback-on-error`` and receive the same compensating pre-image
        treatment.  Caller-supplied XML is never accepted.
        """
        if profile.get("protocol") != "netconf" or not approved or not actor:
            raise StructuredProtocolError("NETCONF typed write requires approved NETCONF context")
        started = time.monotonic()
        tp = None
        locked = ""
        commit_state = "not_committed"
        rollback = "not_needed"
        tx = rx = 0
        normalized = {}
        target = ""
        try:
            tp, caps, hello_tx = self._netconf_open(device, profile)
            tx += hello_tx
            normalized = _normalize_netconf_caps(caps)
            target = "candidate" if normalized["candidate"] else "running"
            if target == "running" and not normalized["rollback_on_error"]:
                raise StructuredProtocolError(
                    "NETCONF running write refused because server lacks :rollback-on-error and no candidate datastore exists")
            _reply, n, r = self._netconf_rpc(
                tp, f"<lock><target><{target}/></target></lock>".encode(), message_id=20)
            tx += n; rx += r; locked = target
            n, r = self._netconf_apply_value_on_session(tp, normalized, resolved, target=target, message_base=21)
            tx += n; rx += r

            expected = resolved.get("value")
            if target == "candidate":
                observed_candidate, n, r = self._netconf_read_resolved_on_session(
                    tp, normalized, resolved, datastore="candidate", message_id=24)
                tx += n; rx += r
                if observed_candidate != expected:
                    raise StructuredProtocolError("NETCONF candidate verification failed before commit")
                if normalized["confirmed_commit"]:
                    _reply, n, r = self._netconf_rpc(
                        tp, b"<commit><confirmed/><confirm-timeout>30</confirm-timeout></commit>", message_id=25)
                    tx += n; rx += r
                    commit_state = "confirmed_pending"
                    rollback = "confirmed_commit_timeout_30s"
                else:
                    _reply, n, r = self._netconf_rpc(tp, b"<commit/>", message_id=25)
                    tx += n; rx += r
                    commit_state = "committed"
                    rollback = "compensating_preimage_available" if before_value is not None else "no_preimage"
            else:
                commit_state = "running_changed"
                rollback = "compensating_preimage_available" if before_value is not None else "rollback_on_error_only"

            observed, n, r = self._netconf_read_resolved_on_session(
                tp, normalized, resolved, datastore="running", message_id=26)
            tx += n; rx += r
            if observed != expected:
                raise StructuredProtocolError("NETCONF post-change verification failed")

            if commit_state == "confirmed_pending":
                _reply, n, r = self._netconf_rpc(tp, b"<commit/>", message_id=27)
                tx += n; rx += r
                commit_state = "confirmed"
                rollback = "confirmed"
            if locked:
                _reply, n, r = self._netconf_rpc(
                    tp, f"<unlock><target><{locked}/></target></unlock>".encode(), message_id=28)
                tx += n; rx += r; locked = ""
            self._trace(device, "netconf", "edit_config", started,
                        operation="NETCONF approved typed edit-config", tx=tx, rx=rx,
                        target=target, resource=resolved.get("resource"), rollback=rollback,
                        verification="exact_resource")
            self._audit(actor, "structured_change", device, "netconf", "ok",
                        f"operation=typed_edit;target={target};resource={resolved.get('resource')};rollback={rollback}")
            return {"protocol": "netconf", "operation": "typed_edit", "target": target,
                    "changed": True, "verified": True, "rollback": rollback,
                    "confirmed_commit": commit_state == "confirmed"}
        except Exception as exc:
            # If a confirmed commit is pending, *not* confirming it is the safest
            # rollback; the server reverts automatically after 30 seconds.
            if tp is not None and commit_state == "confirmed_pending":
                rollback = "confirmed_commit_timeout_pending"
            elif tp is not None and target == "candidate" and commit_state == "not_committed":
                try:
                    self._netconf_rpc(tp, b"<discard-changes/>", message_id=90)
                    rollback = "discarded_candidate"
                except Exception:
                    rollback = "FAILED"
            elif tp is not None and before_value is not None and commit_state in {"committed", "running_changed"}:
                try:
                    rollback_resolved = dict(resolved)
                    rollback_resolved["value"] = before_value
                    n, r = self._netconf_apply_value_on_session(
                        tp, normalized, rollback_resolved, target=target, message_base=91)
                    tx += n; rx += r
                    if target == "candidate":
                        old_candidate, n, r = self._netconf_read_resolved_on_session(
                            tp, normalized, rollback_resolved, datastore="candidate", message_id=93)
                        tx += n; rx += r
                        if old_candidate != before_value:
                            raise StructuredProtocolError("NETCONF compensating candidate verification failed") from exc
                        _reply, n, r = self._netconf_rpc(tp, b"<commit/>", message_id=94)
                        tx += n; rx += r
                    old_running, n, r = self._netconf_read_resolved_on_session(
                        tp, normalized, rollback_resolved, datastore="running", message_id=95)
                    tx += n; rx += r
                    if old_running != before_value:
                        raise StructuredProtocolError("NETCONF compensating running verification failed") from exc
                    rollback = "restored_preimage"
                except Exception:
                    rollback = "FAILED"
            if tp is not None and locked:
                try:
                    self._netconf_rpc(tp, f"<unlock><target><{locked}/></target></unlock>".encode(), message_id=99)
                except Exception:
                    pass
            self._trace(device, "netconf", "edit_config", started,
                        operation="NETCONF approved typed edit-config", status="error",
                        tx=tx, rx=rx, rollback=rollback, error_type=type(exc).__name__)
            self._audit(actor, "structured_change", device, "netconf", "error",
                        f"operation=typed_edit;rollback={rollback};error={type(exc).__name__}")
            if rollback == "FAILED":
                raise StructuredProtocolError(
                    "NETCONF change failed and compensating rollback also failed; manual recovery required; rollback=FAILED") from exc
            if isinstance(exc, StructuredProtocolError):
                raise StructuredProtocolError(f"{exc}; rollback={rollback}") from exc
            raise StructuredProtocolError(f"NETCONF typed change failed: {type(exc).__name__}; rollback={rollback}") from exc
        finally:
            if tp is not None:
                tp.close()

    # ---- RESTCONF --------------------------------------------------------
    def _restconf_secret_and_context(self, device, profile):
        sec = self._secret(device, profile)
        verify = _bool(profile.get("tls_verify", True))
        _tls_verify_allowed(verify)
        ca_file = _validate_abs_file(profile.get("ca_file"), "CA file", require_exists=bool(profile.get("ca_file")))
        context = ssl.create_default_context(cafile=ca_file or None) if verify else ssl._create_unverified_context()
        cert = _validate_abs_file(sec.get("client_cert_file"), "client certificate", require_exists=bool(sec.get("client_cert_file")))
        key = _validate_abs_file(sec.get("client_key_file"), "client key", require_exists=bool(sec.get("client_key_file")))
        if bool(cert) != bool(key):
            raise StructuredProtocolError("RESTCONF mTLS requires both client_cert_file and client_key_file in the vault secret")
        if cert:
            try:
                context.load_cert_chain(cert, key, password=sec.get("client_key_password"))
            except Exception as exc:
                raise StructuredProtocolError(f"RESTCONF mTLS certificate loading failed: {type(exc).__name__}") from exc
        if sec.get("password") and not sec.get("username"):
            raise StructuredProtocolError("RESTCONF password authentication requires a vault username")
        if not sec.get("password") and not cert:
            raise StructuredProtocolError("RESTCONF requires either vault username/password or mTLS client certificate credentials")
        return sec, context, verify, bool(cert)

    def _restconf_request(self, device, profile, method, path, *, body=None, content_type=None,
                          discovery=False, require_data=False, if_match=None):
        method = str(method or "").upper()
        if method not in {"GET", "PUT"}:
            raise StructuredProtocolError("RESTCONF method is not allow-listed")
        try:
            safe_path = _restconf_path(path, discovery=discovery, require_data=require_data)
        except ValueError as exc:
            raise StructuredProtocolError(str(exc)) from exc
        sec, context, verify, mtls = self._restconf_secret_and_context(device, profile)
        host = _https_host(device.get("host"))
        port = int(profile.get("port") or 443)
        url = f"https://{host}:{port}{safe_path}"
        headers = {"Accept": "application/yang-data+json, application/yang-data+xml;q=0.9",
                   "User-Agent": "NetConfig-PH3/2"}
        if sec.get("username") and sec.get("password"):
            auth = base64.b64encode(f"{sec['username']}:{sec['password']}".encode()).decode()
            headers["Authorization"] = "Basic " + auth
        data = None
        if body is not None:
            if not isinstance(body, (bytes, bytearray)):
                raise StructuredProtocolError("RESTCONF internal request body must already be serialized bytes")
            data = bytes(body)
            if len(data) > MAX_PAYLOAD_BYTES:
                raise StructuredProtocolError("RESTCONF request exceeds 16 MiB limit")
            headers["Content-Type"] = content_type or "application/yang-data+json"
        if if_match:
            headers["If-Match"] = str(if_match)
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.manager.settings["command_timeout"], context=context) as res:
                raw = res.read(MAX_PAYLOAD_BYTES + 1)
                if len(raw) > MAX_PAYLOAD_BYTES:
                    raise StructuredProtocolError("RESTCONF response exceeds 16 MiB limit")
                ctype = str(res.headers.get("Content-Type") or "application/octet-stream")
                etag = str(res.headers.get("ETag") or "")
                status = int(getattr(res, "status", 200) or 200)
        except urllib.error.HTTPError as exc:
            detail = f"HTTP {exc.code}"
            raise StructuredProtocolError(f"RESTCONF {method} failed: {detail}") from exc
        return raw, ctype, {"path": safe_path, "tls_verify": verify, "mtls": mtls,
                            "status": status, "etag": etag}

    def _restconf_discover(self, device, profile):
        started = time.monotonic()
        discovery = {"protocol": "restconf", "root": "/restconf", "well_known": False,
                     "content_types": [], "write": {"replace_json_internal": True,
                                                     "generic_passthrough": False}}
        try:
            # Host-meta is a discovery hint; absence is not fatal if /restconf is available.
            try:
                raw, ctype, _ = self._restconf_request(
                    device, profile, "GET", "/.well-known/host-meta", discovery=True)
                _decode_structured_payload(raw, ctype, label="RESTCONF host-meta")
                discovery["well_known"] = True
            except StructuredProtocolError as exc:
                if "HTTP 404" not in str(exc):
                    # Other failures (TLS/auth/malformed content) should not be hidden.
                    raise
            raw, ctype, meta = self._restconf_request(device, profile, "GET", "/restconf", discovery=True)
            _text, value, media = _decode_structured_payload(raw, ctype, label="RESTCONF root")
            discovery["root_content_type"] = media
            discovery["tls_verify"] = meta["tls_verify"]
            discovery["mtls"] = meta["mtls"]
            if isinstance(value, dict):
                discovery["top_level"] = sorted(str(k) for k in value.keys())[:64]
                caps = value.get("ietf-restconf-monitoring:restconf-state", {}).get("capabilities", {}).get("capability", [])
                if isinstance(caps, list):
                    discovery["capabilities"] = [str(x)[:1024] for x in caps[:256]]
            self._trace(device, "restconf", "capabilities", started,
                        operation="RESTCONF root discovery", rx=len(raw), path="/restconf",
                        tls_verify=meta["tls_verify"], mtls=meta["mtls"])
            self._audit("system", "structured_capabilities", device, "restconf", "ok")
            return discovery
        except Exception as exc:
            self._trace(device, "restconf", "capabilities", started,
                        operation="RESTCONF root discovery", status="error", error_type=type(exc).__name__)
            self._audit("system", "structured_capabilities", device, "restconf", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"RESTCONF discovery failed: {type(exc).__name__}") from exc

    def _restconf_get(self, device, profile, path):
        started = time.monotonic()
        try:
            raw, ctype, meta = self._restconf_request(
                device, profile, "GET", path, require_data=True)
            text, _value, media = _decode_structured_payload(raw, ctype, label="RESTCONF data")
            self._trace(device, "restconf", "get", started, operation="RESTCONF GET",
                        rx=len(raw), path=meta["path"], tls_verify=meta["tls_verify"], mtls=meta["mtls"])
            self._audit("system", "structured_read", device, "restconf", "ok", f"path={meta['path']}")
            return text, {"protocol": "restconf", "content_type": media,
                          "operation": "get", **meta,
                          "rollback": {"preimage_replace": True}}
        except Exception as exc:
            self._trace(device, "restconf", "get", started, operation="RESTCONF GET",
                        status="error", error_type=type(exc).__name__)
            self._audit("system", "structured_read", device, "restconf", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"RESTCONF collection failed: {type(exc).__name__}") from exc

    def restconf_replace_json(self, device, profile, *, path, value, actor, approved, verify):
        """Internal controlled RESTCONF JSON subtree replacement.

        This primitive is intentionally *not* exposed as generic Web/API/CLI
        passthrough.  The caller must already be inside an approved change path,
        must supply a callable post-read verifier, and receives fail-closed
        rollback semantics based on the pre-change representation.
        """
        if profile.get("protocol") != "restconf":
            raise StructuredProtocolError("RESTCONF replace requires a RESTCONF profile")
        if not approved or not actor:
            raise StructuredProtocolError("RESTCONF write requires an approved change and actor")
        if not callable(verify):
            raise StructuredProtocolError("RESTCONF write requires post-change verification")
        try:
            safe_path = _restconf_path(path, require_data=True)
        except ValueError as exc:
            raise StructuredProtocolError(str(exc)) from exc
        if urllib.parse.urlsplit(safe_path).path == "/restconf/data":
            raise StructuredProtocolError("RESTCONF whole-datastore replacement is not allowed")
        if isinstance(value, (bytes, bytearray)) or value is None:
            raise StructuredProtocolError("RESTCONF controlled write accepts bounded JSON values only")
        payload = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise StructuredProtocolError("RESTCONF write payload exceeds 16 MiB limit")
        started = time.monotonic()
        pre_raw = None
        pre_media = None
        try:
            pre_raw, pre_ctype, pre_meta = self._restconf_request(
                device, profile, "GET", safe_path, require_data=True)
            _pre_text, _pre_value, pre_media = _decode_structured_payload(
                pre_raw, pre_ctype, label="RESTCONF pre-read")
            if "json" not in pre_media:
                raise StructuredProtocolError("RESTCONF rollback requires a JSON pre-image")
            self._restconf_request(
                device, profile, "PUT", safe_path, body=payload,
                content_type="application/yang-data+json", require_data=True,
                if_match=pre_meta.get("etag") or None)
            post_raw, post_ctype, _post_meta = self._restconf_request(
                device, profile, "GET", safe_path, require_data=True)
            _post_text, post_value, _post_media = _decode_structured_payload(
                post_raw, post_ctype, label="RESTCONF post-read")
            if not bool(verify(post_value)):
                raise StructuredProtocolError("RESTCONF post-change verification failed")
            self._trace(device, "restconf", "replace", started,
                        operation="RESTCONF approved JSON replace", tx=len(payload), rx=len(post_raw),
                        path=safe_path, verified=True)
            self._audit(actor, "structured_change", device, "restconf", "ok",
                        f"operation=replace;path={safe_path};verified=1")
            return {"protocol": "restconf", "operation": "replace", "path": safe_path,
                    "verified": True, "rollback": "preimage", "changed": True}
        except Exception as exc:
            rollback = "not_attempted"
            if pre_raw is not None and pre_media and "json" in pre_media:
                try:
                    self._restconf_request(
                        device, profile, "PUT", safe_path, body=pre_raw,
                        content_type=pre_media, require_data=True)
                    rollback = "restored_preimage"
                except Exception:
                    rollback = "FAILED"
            self._trace(device, "restconf", "replace", started,
                        operation="RESTCONF approved JSON replace", status="error",
                        path=safe_path, rollback=rollback, error_type=type(exc).__name__)
            self._audit(actor, "structured_change", device, "restconf", "error",
                        f"operation=replace;path={safe_path};rollback={rollback};error={type(exc).__name__}")
            if rollback == "FAILED":
                raise StructuredProtocolError(
                    "RESTCONF change failed and pre-image rollback also failed; manual recovery required") from exc
            if isinstance(exc, StructuredProtocolError):
                raise StructuredProtocolError(f"{exc}; rollback={rollback}") from exc
            raise StructuredProtocolError(f"RESTCONF change failed: {type(exc).__name__}; rollback={rollback}") from exc

    def restconf_replace_typed(self, device, profile, *, resolved, actor, approved):
        """Replace one model-pack leaf using a generated YANG JSON envelope."""
        path = str(resolved.get("restconf_path") or "")
        key = str(resolved.get("restconf_json_key") or "")
        if not path or not key:
            raise StructuredProtocolError("model pack lacks a bounded RESTCONF typed mapping")
        value = resolved.get("value")
        envelope = {key: value}
        return self.restconf_replace_json(
            device, profile, path=path, value=envelope, actor=actor, approved=approved,
            verify=lambda observed: self._extract_json_scalar(
                observed, value_type=resolved.get("value_type", "string"),
                leaf_hint=key.split(":")[-1]) == value)

    # ---- gNMI ------------------------------------------------------------
    def _gnmi_binary(self):
        binary = os.environ.get("NETCONFIG_GNMIC") or shutil.which("gnmic")
        if not binary or not os.path.isabs(binary):
            raise StructuredProtocolError("gnmic binary is required for gNMI")
        return binary

    def _gnmi_config(self, device, profile, sec):
        _validate_host(device.get("host"))
        verify = _bool(profile.get("tls_verify", True))
        _tls_verify_allowed(verify)
        cfg = {"address": f"{device['host']}:{int(profile.get('port') or 57400)}",
               "skip-verify": not verify}
        if sec.get("username"):
            cfg["username"] = sec["username"]
        if sec.get("password"):
            cfg["password"] = sec["password"]
        if profile.get("ca_file"):
            cfg["tls-ca"] = _validate_abs_file(profile["ca_file"], "CA file", require_exists=True)
        cert = _validate_abs_file(sec.get("client_cert_file"), "client certificate", require_exists=bool(sec.get("client_cert_file")))
        key = _validate_abs_file(sec.get("client_key_file"), "client key", require_exists=bool(sec.get("client_key_file")))
        if bool(cert) != bool(key):
            raise StructuredProtocolError("gNMI mTLS requires both client_cert_file and client_key_file in the vault secret")
        if cert:
            cfg["tls-cert"] = cert
            cfg["tls-key"] = key
        if sec.get("password") and not sec.get("username"):
            raise StructuredProtocolError("gNMI password authentication requires a vault username")
        if not sec.get("password") and not cert:
            raise StructuredProtocolError("gNMI requires username/password or mTLS credentials")
        return cfg, verify, bool(cert)

    def _gnmi_run(self, device, profile, argv_tail, *, label, timeout=None, timeout_as_result=False):
        sec = self._secret(device, profile)
        binary = self._gnmi_binary()
        cfg, verify, mtls = self._gnmi_config(device, profile, sec)
        fd, cfg_path = tempfile.mkstemp(prefix="netconfig-gnmi-", suffix=".json")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(cfg, fh)
            argv = [binary, "--config", cfg_path, *argv_tail]
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=(timeout or self.manager.settings["command_timeout"]), check=False)
            stdout_raw = (proc.stdout or "").encode("utf-8", "replace")
            stderr = proc.stderr or ""
            if len(stdout_raw) > MAX_PAYLOAD_BYTES:
                raise StructuredProtocolError(f"{label} response exceeds 16 MiB limit")
            if len(stderr.encode("utf-8", "replace")) > 256 * 1024:
                stderr = stderr[:256 * 1024]
            if proc.returncode != 0:
                detail = _redact_text(stderr.strip()[:1000], *_secret_values(sec))
                raise StructuredProtocolError(f"{label} failed: " + (detail or f"exit {proc.returncode}"))
            text = stdout_raw.decode("utf-8", "strict")
            try:
                value = json.loads(text or "{}")
            except json.JSONDecodeError:
                # gnmic Subscribe may emit newline-delimited JSON objects.
                try:
                    value = [json.loads(line) for line in text.splitlines() if line.strip()]
                except json.JSONDecodeError as exc:
                    raise StructuredProtocolError(f"malformed {label} JSON") from exc
            return value, len(stdout_raw), {"tls_verify": verify, "mtls": mtls,
                                           "binary": os.path.basename(binary)}
        except subprocess.TimeoutExpired as exc:
            if timeout_as_result:
                stdout = exc.stdout or ""
                stderr = exc.stderr or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", "replace")
                if isinstance(stderr, bytes):
                    stderr = stderr.decode("utf-8", "replace")
                raw = stdout.encode("utf-8", "replace")
                if len(raw) > MAX_PAYLOAD_BYTES:
                    raise StructuredProtocolError(f"{label} response exceeds 16 MiB limit") from exc
                values = []
                for line in stdout.splitlines():
                    if not line.strip():
                        continue
                    try:
                        values.append(json.loads(line))
                    except json.JSONDecodeError as jexc:
                        raise StructuredProtocolError(f"malformed {label} JSON") from jexc
                return values, len(raw), {"tls_verify": verify, "mtls": mtls,
                                          "binary": os.path.basename(binary),
                                          "window_timeout": True}
            raise StructuredProtocolError(f"{label} timed out") from exc
        finally:
            try:
                os.unlink(cfg_path)
            except OSError:
                pass

    def _gnmi_capabilities(self, device, profile):
        started = time.monotonic()
        try:
            value, rx, meta = self._gnmi_run(
                device, profile, ["capabilities", "--format", "json"], label="gNMI Capabilities")
            # Preserve the PH-3 public capability contract: generic gNMI Set is
            # intentionally *not* exposed.  PH-4 adds only the constrained typed
            # Set path behind the approved structured-change engine.
            out = {"protocol": "gnmi", "raw": value, "generic_passthrough": False,
                   "get": True, "subscribe_once": True, "set": False,
                   "write": {"typed_set": True, "generic_passthrough": False,
                             "approval_required": True},
                   "tls_verify": meta["tls_verify"], "mtls": meta["mtls"]}
            self._trace(device, "gnmi", "capabilities", started,
                        operation="gNMI Capabilities", rx=rx, tls_verify=meta["tls_verify"], mtls=meta["mtls"])
            self._audit("system", "structured_capabilities", device, "gnmi", "ok")
            return out
        except Exception as exc:
            self._trace(device, "gnmi", "capabilities", started,
                        operation="gNMI Capabilities", status="error", error_type=type(exc).__name__)
            self._audit("system", "structured_capabilities", device, "gnmi", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"gNMI capability negotiation failed: {type(exc).__name__}") from exc

    def _gnmi_get(self, device, profile, path, *, data_type):
        started = time.monotonic()
        try:
            typed = GnmiPath.parse(path)
        except ValueError as exc:
            raise StructuredProtocolError(str(exc)) from exc
        try:
            value, rx, meta = self._gnmi_run(
                device, profile,
                ["get", "--path", typed.render(), "--type", data_type,
                 "--encoding", "json_ietf", "--format", "json"],
                label="gNMI Get")
            text = json.dumps(value, indent=2, sort_keys=True)
            self._trace(device, "gnmi", "get", started, operation="gNMI Get", rx=rx,
                        path=typed.render(), data_type=data_type, tls_verify=meta["tls_verify"], mtls=meta["mtls"])
            self._audit("system", "structured_read", device, "gnmi", "ok",
                        f"operation=get;type={data_type}")
            return text, {"protocol": "gnmi", "content_type": "application/json",
                          "operation": "get", "path": typed.as_dict(), "data_type": data_type,
                          "tls_verify": meta["tls_verify"], "mtls": meta["mtls"],
                          "write": {"set": True, "generic_passthrough": False,
                                    "typed_only": True}}
        except Exception as exc:
            self._trace(device, "gnmi", "get", started, operation="gNMI Get",
                        status="error", path=typed.render(), error_type=type(exc).__name__)
            self._audit("system", "structured_read", device, "gnmi", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"gNMI Get failed: {type(exc).__name__}") from exc

    @staticmethod
    def _json_contains_value(node, expected):
        if node == expected:
            return True
        if isinstance(node, dict):
            return any(StructuredCollector._json_contains_value(v, expected) for v in node.values())
        if isinstance(node, list):
            return any(StructuredCollector._json_contains_value(v, expected) for v in node)
        return False

    def gnmi_set_typed(self, device, profile, *, path, value, actor, approved,
                       before_value=None, value_type=None, leaf_hint=""):
        if profile.get("protocol") != "gnmi" or not approved or not actor:
            raise StructuredProtocolError("gNMI typed Set requires approved gNMI context")
        try:
            typed = GnmiPath.parse(path)
        except ValueError as exc:
            raise StructuredProtocolError(str(exc)) from exc
        encoded = json.dumps(value, separators=(",", ":"), sort_keys=True)
        if len(encoded.encode("utf-8")) > 64 * 1024:
            raise StructuredProtocolError("gNMI typed Set value exceeds 64 KiB limit")
        started = time.monotonic()
        rollback = "not_needed"
        try:
            result, rx, meta = self._gnmi_run(
                device, profile,
                ["set", "--replace-path", typed.render(), "--replace-value", encoded,
                 "--encoding", "json_ietf", "--format", "json"],
                label="gNMI Set")
            post, post_rx, _post_meta = self._gnmi_run(
                device, profile,
                ["get", "--path", typed.render(), "--type", "CONFIG",
                 "--encoding", "json_ietf", "--format", "json"],
                label="gNMI Set post-read")
            rx += post_rx
            if value_type:
                observed = self._extract_json_scalar(post, value_type=value_type,
                                                     leaf_hint=leaf_hint or (typed.elems[-1].name if typed.elems else ""))
                verified = observed == value
            else:
                verified = self._json_contains_value(post, value)
            if not verified:
                if before_value is not None:
                    rollback_encoded = json.dumps(before_value, separators=(",", ":"), sort_keys=True)
                    self._gnmi_run(
                        device, profile,
                        ["set", "--replace-path", typed.render(), "--replace-value", rollback_encoded,
                         "--encoding", "json_ietf", "--format", "json"],
                        label="gNMI compensating Set")
                    verify_old, old_rx, _old_meta = self._gnmi_run(
                        device, profile,
                        ["get", "--path", typed.render(), "--type", "CONFIG",
                         "--encoding", "json_ietf", "--format", "json"],
                        label="gNMI compensating Set post-read")
                    rx += old_rx
                    if value_type:
                        old_observed = self._extract_json_scalar(
                            verify_old, value_type=value_type,
                            leaf_hint=leaf_hint or (typed.elems[-1].name if typed.elems else ""))
                        if old_observed != before_value:
                            rollback = "FAILED"
                        else:
                            rollback = "restored_preimage"
                    elif self._json_contains_value(verify_old, before_value):
                        rollback = "restored_preimage"
                    else:
                        rollback = "FAILED"
                else:
                    rollback = "not_protocol_native"
                if rollback == "FAILED":
                    raise StructuredProtocolError(
                        "gNMI post-change verification failed and compensating rollback failed; manual recovery required; rollback=FAILED")
                raise StructuredProtocolError(f"gNMI post-change verification failed; rollback={rollback}")
            rollback = "compensating_preimage_available" if before_value is not None else "not_protocol_native"
            self._trace(device, "gnmi", "set", started, operation="gNMI approved typed Set",
                        tx=len(encoded.encode("utf-8")), rx=rx, path=typed.render(),
                        tls_verify=meta["tls_verify"], mtls=meta["mtls"], rollback=rollback,
                        verified=True)
            self._audit(actor, "structured_change", device, "gnmi", "ok",
                        f"operation=typed_set;path={typed.render()};rollback={rollback};verified=1")
            return {"protocol": "gnmi", "operation": "replace", "path": typed.as_dict(),
                    "changed": True, "verified": True, "rollback": rollback, "result": result}
        except Exception as exc:
            detail = str(exc)
            if "rollback=" in detail:
                rollback = detail.rsplit("rollback=", 1)[-1].split(";", 1)[0][:64]
            elif rollback == "not_needed":
                rollback = "not_attempted"
            self._trace(device, "gnmi", "set", started, operation="gNMI approved typed Set",
                        status="error", path=typed.render(), rollback=rollback,
                        error_type=type(exc).__name__)
            self._audit(actor, "structured_change", device, "gnmi", "error",
                        f"operation=typed_set;rollback={rollback};error={type(exc).__name__}")
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"gNMI typed Set failed: {type(exc).__name__}; rollback={rollback}") from exc

    def _gnmi_subscribe_window(self, device, profile, path, *, mode, duration_seconds,
                               sample_interval_ms, heartbeat_interval_ms):
        started = time.monotonic()
        try:
            typed = GnmiPath.parse(path)
        except ValueError as exc:
            raise StructuredProtocolError(str(exc)) from exc
        mode = str(mode or "ON_CHANGE").upper()
        if mode not in {"ON_CHANGE", "SAMPLE", "TARGET_DEFINED"}:
            raise StructuredProtocolError("unsupported gNMI stream mode")
        duration = int(duration_seconds)
        if duration < 1 or duration > 300:
            raise StructuredProtocolError("gNMI stream window must be 1..300 seconds")
        sample = int(sample_interval_ms)
        heartbeat = int(heartbeat_interval_ms)
        if sample < 1000 or sample > 3_600_000 or heartbeat < 0 or heartbeat > 3_600_000:
            raise StructuredProtocolError("gNMI stream interval outside safe bounds")
        tail = ["subscribe", "--path", typed.render(), "--mode", "stream",
                "--stream-mode", mode.lower(), "--encoding", "json_ietf", "--format", "json"]
        if mode == "SAMPLE":
            tail += ["--sample-interval", f"{sample}ms"]
        if heartbeat:
            tail += ["--heartbeat-interval", f"{heartbeat}ms"]
        try:
            value, rx, meta = self._gnmi_run(
                device, profile, tail, label="gNMI Subscribe STREAM", timeout=duration,
                timeout_as_result=True)
            text = json.dumps(value, indent=2, sort_keys=True)
            self._trace(device, "gnmi", "subscribe", started,
                        operation="gNMI Subscribe STREAM bounded window", rx=rx, path=typed.render(),
                        mode=mode, duration_seconds=duration,
                        tls_verify=meta["tls_verify"], mtls=meta["mtls"],
                        window_complete=bool(meta.get("window_timeout")))
            self._audit("system", "structured_read", device, "gnmi", "ok",
                        f"operation=subscribe_stream;mode={mode};duration={duration}")
            return text, {"protocol": "gnmi", "content_type": "application/json",
                          "operation": "subscribe", "mode": "stream", "stream_mode": mode,
                          "duration_seconds": duration, "path": typed.as_dict(),
                          "tls_verify": meta["tls_verify"], "mtls": meta["mtls"],
                          "window_complete": bool(meta.get("window_timeout"))}
        except Exception as exc:
            self._trace(device, "gnmi", "subscribe", started,
                        operation="gNMI Subscribe STREAM bounded window", status="error",
                        path=typed.render(), mode=mode, error_type=type(exc).__name__)
            self._audit("system", "structured_read", device, "gnmi", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"gNMI streaming Subscribe failed: {type(exc).__name__}") from exc

    def _gnmi_subscribe_once(self, device, profile, path):
        started = time.monotonic()
        try:
            typed = GnmiPath.parse(path)
        except ValueError as exc:
            raise StructuredProtocolError(str(exc)) from exc
        try:
            value, rx, meta = self._gnmi_run(
                device, profile,
                ["subscribe", "--path", typed.render(), "--mode", "once",
                 "--encoding", "json_ietf", "--format", "json"],
                label="gNMI Subscribe")
            text = json.dumps(value, indent=2, sort_keys=True)
            self._trace(device, "gnmi", "subscribe", started,
                        operation="gNMI Subscribe ONCE", rx=rx, path=typed.render(),
                        mode="once", tls_verify=meta["tls_verify"], mtls=meta["mtls"])
            self._audit("system", "structured_read", device, "gnmi", "ok", "operation=subscribe_once")
            return text, {"protocol": "gnmi", "content_type": "application/json",
                          "operation": "subscribe", "mode": "once", "path": typed.as_dict(),
                          "tls_verify": meta["tls_verify"], "mtls": meta["mtls"]}
        except Exception as exc:
            self._trace(device, "gnmi", "subscribe", started,
                        operation="gNMI Subscribe ONCE", status="error",
                        path=typed.render(), error_type=type(exc).__name__)
            self._audit("system", "structured_read", device, "gnmi", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"gNMI Subscribe failed: {type(exc).__name__}") from exc
