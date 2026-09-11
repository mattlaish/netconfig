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
        if not isinstance(value, (dict, list)):
            raise StructuredProtocolError("RESTCONF controlled write accepts JSON object/array values only")
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

    def _gnmi_run(self, device, profile, argv_tail, *, label):
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
                                  timeout=self.manager.settings["command_timeout"], check=False)
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
            out = {"protocol": "gnmi", "raw": value, "generic_passthrough": False,
                   "get": True, "subscribe_once": True, "set": False,
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
                          "write": {"set": False, "reason": "gNMI Set is not exposed in PH-3"}}
        except Exception as exc:
            self._trace(device, "gnmi", "get", started, operation="gNMI Get",
                        status="error", path=typed.render(), error_type=type(exc).__name__)
            self._audit("system", "structured_read", device, "gnmi", "error", type(exc).__name__)
            if isinstance(exc, StructuredProtocolError):
                raise
            raise StructuredProtocolError(f"gNMI Get failed: {type(exc).__name__}") from exc

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
