import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from netconfig.apitokens import ApiTokens, VALID_SCOPES
from netconfig.cli import build_parser
from netconfig.manager import Manager
from netconfig.protocols import available_protocols
from netconfig.structured_protocols import (
    GnmiPath,
    MAX_PAYLOAD_BYTES,
    StructuredProtocolError,
    _safe_xml_parse,
)


def manager(tmp_path):
    m = Manager(str(tmp_path))
    m.inv.upsert(name="r1", host="192.0.2.10", platform="generic", secret_ref="dev1")
    m.vault.create("master")
    m.vault.unlock("master")
    m._vault_unlocked = True
    m.vault.set_secret("dev1", username="ops", password="topsecret")
    return m


def netconf_hello(*extra):
    caps = ["urn:ietf:params:netconf:base:1.0", *extra]
    body = "".join(f"<capability>{c}</capability>" for c in caps)
    return (f'<hello xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"><capabilities>{body}'
            f'</capabilities><session-id>7</session-id></hello>]]>]]>').encode()


def test_structured_capabilities_are_implemented():
    caps = available_protocols()
    assert caps["cli_ssh"].implemented
    for name in ("netconf", "restconf", "gnmi"):
        assert caps[name].structured and caps[name].implemented


def test_profile_defaults_path_guards_and_tls_fail_closed(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "netconf")
    assert p["port"] == 830 and p["allow_cli_fallback"] is False

    p = m.protocol_profiles.set("r1", "restconf")
    assert p["path"].startswith("/restconf/data") and p["tls_verify"] is True
    with pytest.raises(ValueError):
        m.protocol_profiles.set("r1", "restconf", path="/restconf/database")
    with pytest.raises(ValueError):
        m.protocol_profiles.set("r1", "restconf", path="https://evil.invalid/restconf/data")
    with pytest.raises(ValueError):
        m.protocol_profiles.set("r1", "restconf", tls_verify=False)
    monkeypatch.setenv("NETCONFIG_ALLOW_INSECURE_STRUCTURED_TLS", "1")
    assert m.protocol_profiles.set("r1", "restconf", tls_verify=False)["tls_verify"] is False

    p = m.protocol_profiles.set("r1", "gnmi", path="/interfaces/interface[name=Ethernet1]/state")
    assert p["path"] == "/interfaces/interface[name=Ethernet1]/state"
    with pytest.raises(ValueError):
        m.protocol_profiles.set("r1", "gnmi", path="../interfaces")


def test_host_validation_rejects_url_like_inventory_host(tmp_path):
    m = Manager(str(tmp_path))
    m.inv.upsert(name="bad", host="https://router.invalid", platform="generic")
    with pytest.raises(StructuredProtocolError):
        m.protocol_profiles.set("bad", "restconf")


def test_restconf_and_gnmi_password_auth_require_username(tmp_path, monkeypatch):
    m = manager(tmp_path)
    m.vault.set_secret("password-only", password="topsecret")

    rest = m.protocol_profiles.set("r1", "restconf", secret_ref="password-only")
    with pytest.raises(StructuredProtocolError, match="requires a vault username"):
        m.structured_collector.capabilities(m.inv.get("r1"), rest)

    gnmi = m.protocol_profiles.set("r1", "gnmi", secret_ref="password-only")
    monkeypatch.setattr("netconfig.structured_protocols.shutil.which", lambda x: "/usr/bin/gnmic")
    with pytest.raises(StructuredProtocolError, match="requires a vault username"):
        m.structured_collector.capabilities(m.inv.get("r1"), gnmi)


def test_gnmi_typed_path_representation():
    path = GnmiPath.parse("/interfaces/interface[name=Ethernet1][index=1]/state")
    assert path.render() == "/interfaces/interface[name=Ethernet1][index=1]/state"
    assert path.as_dict()["elem"][1]["key"] == {"name": "Ethernet1", "index": "1"}
    for bad in ("relative", "/a//b", "/a/../b", "/a[*=x]", "/a[bad]"):
        with pytest.raises(ValueError):
            GnmiPath.parse(bad)


def test_safe_xml_rejects_dtd_entity_and_depth():
    with pytest.raises(StructuredProtocolError, match="DTD/entity"):
        _safe_xml_parse(b'<!DOCTYPE x [<!ENTITY e "boom">]><x>&e;</x>')
    deep = ("<x>" * 70 + "</x>" * 70).encode()
    with pytest.raises(StructuredProtocolError, match="depth"):
        _safe_xml_parse(deep)


def test_structured_collect_fail_closed_and_explicit_fallback(tmp_path, monkeypatch):
    m = manager(tmp_path)
    m.protocol_profiles.set("r1", "netconf")
    monkeypatch.setattr(
        m.structured_collector,
        "collect",
        lambda *a, **k: (_ for _ in ()).throw(StructuredProtocolError("down")),
    )
    r = m.collect("r1")
    assert not r.ok and "StructuredProtocolError" in r.message

    m.protocol_profiles.set("r1", "netconf", allow_cli_fallback=True)
    called = {}

    def fake_connect(dev):
        called["yes"] = True
        raise RuntimeError("cli tried")

    monkeypatch.setattr(m, "_connect", fake_connect)
    r = m.collect("r1")
    assert called["yes"] and not r.ok


def test_netconf_hello_capability_negotiation_get_config_and_trace(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "netconf")
    seen = {"writes": [], "limits": []}

    class FakeSSH:
        def __init__(self, *a, **kw):
            seen["subsystem"] = kw.get("subsystem")
            self.ready_data = b""

        def connect(self, ready_pattern=None, ready_max_bytes=None):
            assert ready_pattern is not None
            assert ready_max_bytes == MAX_PAYLOAD_BYTES
            self.ready_data = netconf_hello(
                "urn:ietf:params:netconf:capability:candidate:1.0",
                "urn:ietf:params:netconf:capability:confirmed-commit:1.1",
                "urn:ietf:params:netconf:capability:rollback-on-error:1.0",
            )

        def write_raw(self, b):
            seen["writes"].append(b)

        def read_raw_until(self, ptn, timeout=None, max_bytes=None):
            seen["limits"].append(max_bytes)
            return b'<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"><data><x/></data></rpc-reply>]]>]]>'

        def close(self):
            pass

    monkeypatch.setattr("netconfig.structured_protocols.SSHTransport", FakeSSH)
    text, meta = m.structured_collector.collect(m.inv.get("r1"), p)
    joined = b"".join(seen["writes"])
    assert seen["subsystem"] == "netconf"
    assert b"<hello" in joined and b"<get-config>" in joined and b"edit-config" not in joined
    assert meta["capabilities"]["candidate"] is True
    assert meta["capabilities"]["confirmed_commit"] is True
    assert meta["rollback"]["rollback_on_error"] is True
    assert seen["limits"] == [MAX_PAYLOAD_BYTES]
    assert meta["protocol"] == "netconf" and "rpc-reply" in text
    tr = m.protocol_traces.start("r1", "netconf", actor="test", ttl=30, max_events=10, max_bytes=4096)
    assert tr["status"] == "ACTIVE"


def test_netconf_get_and_unsupported_datastore_fail_closed(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "netconf")
    seen = []

    class FakeSSH:
        def __init__(self, *a, **kw): self.ready_data = b""
        def connect(self, ready_pattern=None, ready_max_bytes=None):
            self.ready_data = netconf_hello()
        def write_raw(self, b): seen.append(b)
        def read_raw_until(self, ptn, timeout=None, max_bytes=None):
            return b'<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0"><data/></rpc-reply>]]>]]>'
        def close(self): pass

    monkeypatch.setattr("netconfig.structured_protocols.SSHTransport", FakeSSH)
    text, meta = m.structured_collector.read_state(m.inv.get("r1"), p)
    assert b"<get/>" in b"".join(seen)
    assert meta["operation"] == "get" and "rpc-reply" in text
    with pytest.raises(StructuredProtocolError, match="not advertised"):
        m.structured_collector.read_config(m.inv.get("r1"), p, datastore="candidate")


def test_netconf_malformed_or_base11_only_hello_fails_closed(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "netconf")

    class FakeSSH:
        def __init__(self, *a, **kw): self.ready_data = b""
        def connect(self, ready_pattern=None, ready_max_bytes=None):
            self.ready_data = netconf_hello("urn:ietf:params:netconf:base:1.1").replace(
                b"<capability>urn:ietf:params:netconf:base:1.0</capability>", b"")
        def write_raw(self, b): pass
        def close(self): pass

    monkeypatch.setattr("netconfig.structured_protocols.SSHTransport", FakeSSH)
    with pytest.raises(StructuredProtocolError, match="base:1.1-only"):
        m.structured_collector.capabilities(m.inv.get("r1"), p)


def test_restconf_discovery_get_content_validation_and_secret_not_in_url(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "restconf")
    seen = []

    class Resp:
        status = 200
        def __init__(self, body, ctype):
            self.body = body
            self.headers = {"Content-Type": ctype, "ETag": '"v1"'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return self.body

    def fake(req, timeout=None, context=None):
        seen.append((req.full_url, req.headers.get("Authorization")))
        if "/.well-known/host-meta" in req.full_url:
            return Resp(b'<XRD xmlns="http://docs.oasis-open.org/ns/xri/xrd-1.0"/>', "application/xrd+xml")
        if req.full_url.endswith(":443/restconf"):
            return Resp(b'{"ietf-restconf:restconf":{}}', "application/yang-data+json")
        return Resp(b'{"ietf-system:system":{"hostname":"r1"}}', "application/yang-data+json")

    monkeypatch.setattr("netconfig.structured_protocols.urllib.request.urlopen", fake)
    text, meta = m.structured_collector.collect(m.inv.get("r1"), p)
    assert len(seen) == 3
    assert all(url.startswith("https://") and "topsecret" not in url for url, _ in seen)
    assert all(auth and auth.startswith("Basic ") for _, auth in seen)
    assert json.loads(text)["ietf-system:system"]["hostname"] == "r1"
    assert meta["capabilities"]["well_known"] is True
    assert meta["capabilities"]["root_content_type"] == "application/yang-data+json"


def test_restconf_malformed_and_oversized_payload_rejected(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "restconf")

    class Resp:
        status = 200
        headers = {"Content-Type": "application/yang-data+json"}
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return self.body

    monkeypatch.setattr("netconfig.structured_protocols.urllib.request.urlopen", lambda *a, **k: Resp(b"{bad"))
    with pytest.raises(StructuredProtocolError, match="malformed"):
        m.structured_collector.read_config(m.inv.get("r1"), p)

    monkeypatch.setattr(
        "netconfig.structured_protocols.urllib.request.urlopen",
        lambda *a, **k: Resp(b"x" * (MAX_PAYLOAD_BYTES + 1)),
    )
    with pytest.raises(StructuredProtocolError, match="exceeds 16 MiB"):
        m.structured_collector.read_config(m.inv.get("r1"), p)


def test_restconf_controlled_replace_pre_post_verify_and_rollback(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "restconf")
    state = {"ietf-interfaces:interface": {"name": "Ethernet1", "enabled": False}}
    puts = []

    class Resp:
        status = 200
        def __init__(self, body=b"{}"):
            self.body = body
            self.headers = {"Content-Type": "application/yang-data+json", "ETag": '"e1"'}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self, n): return self.body

    def fake(req, timeout=None, context=None):
        nonlocal state
        if req.get_method() == "PUT":
            state = json.loads(req.data.decode())
            puts.append(state)
            return Resp(json.dumps(state).encode())
        return Resp(json.dumps(state).encode())

    monkeypatch.setattr("netconfig.structured_protocols.urllib.request.urlopen", fake)
    desired = {"ietf-interfaces:interface": {"name": "Ethernet1", "enabled": True}}
    out = m.structured_collector.restconf_replace_json(
        m.inv.get("r1"), p, path="/restconf/data/ietf-interfaces:interfaces/interface=Ethernet1",
        value=desired, actor="approver", approved=True,
        verify=lambda post: post == desired,
    )
    assert out["verified"] and state == desired and puts[-1] == desired

    bad_desired = {"ietf-interfaces:interface": {"name": "Ethernet1", "enabled": False}}
    with pytest.raises(StructuredProtocolError, match="rollback=restored_preimage"):
        m.structured_collector.restconf_replace_json(
            m.inv.get("r1"), p, path="/restconf/data/ietf-interfaces:interfaces/interface=Ethernet1",
            value=bad_desired, actor="approver", approved=True,
            verify=lambda post: False,
        )
    assert state == desired
    with pytest.raises(StructuredProtocolError, match="approved change"):
        m.structured_collector.restconf_replace_json(
            m.inv.get("r1"), p, path="/restconf/data/x:y", value={}, actor="approver",
            approved=False, verify=lambda post: True)


def test_gnmi_capabilities_get_secret_only_in_0600_config_not_argv(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "gnmi", path="/interfaces/interface[name=Ethernet1]/state")
    monkeypatch.setattr("netconfig.structured_protocols.shutil.which", lambda x: "/usr/bin/gnmic")
    seen = []

    def fake_run(argv, **kw):
        cfg_path = argv[argv.index("--config") + 1]
        cfg = Path(cfg_path).read_text()
        seen.append({"argv": list(argv), "mode": os.stat(cfg_path).st_mode & 0o777, "cfg": cfg})
        if "capabilities" in argv:
            return SimpleNamespace(returncode=0, stdout='{"supported_models":[]}', stderr="")
        return SimpleNamespace(returncode=0, stdout='{"notification":[]}', stderr="")

    monkeypatch.setattr("netconfig.structured_protocols.subprocess.run", fake_run)
    text, meta = m.structured_collector.collect(m.inv.get("r1"), p)
    assert len(seen) == 2
    assert all(item["mode"] == 0o600 for item in seen)
    assert all("topsecret" in item["cfg"] for item in seen)
    assert all(all("topsecret" not in arg for arg in item["argv"]) for item in seen)
    get_argv = next(item["argv"] for item in seen if "get" in item["argv"])
    assert "/interfaces/interface[name=Ethernet1]/state" in get_argv
    assert meta["capabilities"]["get"] is True
    assert meta["capabilities"]["set"] is False
    assert json.loads(text) == {"notification": []}


def test_gnmi_mtls_fields_resolved_from_vault_and_not_profile(tmp_path, monkeypatch):
    m = manager(tmp_path)
    cert = tmp_path / "client.crt"; cert.write_text("placeholder")
    key = tmp_path / "client.key"; key.write_text("placeholder")
    m.vault.set_secret("dev1", client_cert_file=str(cert), client_key_file=str(key))
    p = m.protocol_profiles.set("r1", "gnmi")
    monkeypatch.setattr("netconfig.structured_protocols.shutil.which", lambda x: "/usr/bin/gnmic")
    captured = {}

    def fake_run(argv, **kw):
        cfg_path = argv[argv.index("--config") + 1]
        captured.update(json.loads(Path(cfg_path).read_text()))
        return SimpleNamespace(returncode=0, stdout='{"supported_models":[]}', stderr="")

    monkeypatch.setattr("netconfig.structured_protocols.subprocess.run", fake_run)
    caps = m.structured_collector.capabilities(m.inv.get("r1"), p)
    assert captured["tls-cert"] == str(cert) and captured["tls-key"] == str(key)
    assert caps["mtls"] is True
    assert "client_key_file" not in p


def test_gnmi_subscribe_once_is_fixed_mode_and_bounded_path(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "gnmi")
    monkeypatch.setattr("netconfig.structured_protocols.shutil.which", lambda x: "/usr/bin/gnmic")
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"] = list(argv)
        return SimpleNamespace(returncode=0, stdout='{"update":{"v":1}}\n{"sync_response":true}\n', stderr="")

    monkeypatch.setattr("netconfig.structured_protocols.subprocess.run", fake_run)
    text, meta = m.structured_collector.subscribe_once(
        m.inv.get("r1"), p, path="/interfaces/interface[name=Ethernet1]/state")
    assert "subscribe" in seen["argv"] and seen["argv"][seen["argv"].index("--mode") + 1] == "once"
    assert meta["mode"] == "once" and isinstance(json.loads(text), list)


def test_gnmi_timeout_malformed_and_oversized_outputs_fail_closed(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "gnmi")
    monkeypatch.setattr("netconfig.structured_protocols.shutil.which", lambda x: "/usr/bin/gnmic")

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd=a[0], timeout=k.get("timeout", 1))

    monkeypatch.setattr("netconfig.structured_protocols.subprocess.run", timeout)
    with pytest.raises(StructuredProtocolError, match="timed out"):
        m.structured_collector.capabilities(m.inv.get("r1"), p)

    monkeypatch.setattr(
        "netconfig.structured_protocols.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="{not-json", stderr=""),
    )
    with pytest.raises(StructuredProtocolError, match="malformed gNMI Capabilities JSON"):
        m.structured_collector.capabilities(m.inv.get("r1"), p)

    monkeypatch.setattr(
        "netconfig.structured_protocols.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="x" * (MAX_PAYLOAD_BYTES + 1), stderr=""),
    )
    with pytest.raises(StructuredProtocolError, match="exceeds 16 MiB limit"):
        m.structured_collector.capabilities(m.inv.get("r1"), p)


def test_gnmi_error_redacts_all_vault_string_values(tmp_path, monkeypatch):
    m = manager(tmp_path)
    p = m.protocol_profiles.set("r1", "gnmi")
    monkeypatch.setattr("netconfig.structured_protocols.shutil.which", lambda x: "/usr/bin/gnmic")
    monkeypatch.setattr(
        "netconfig.structured_protocols.subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="ops topsecret failed"),
    )
    with pytest.raises(StructuredProtocolError) as exc:
        m.structured_collector.capabilities(m.inv.get("r1"), p)
    text = str(exc.value)
    assert "topsecret" not in text and "ops" not in text and "<redacted>" in text


def test_profile_rename_delete_follow_inventory(tmp_path):
    m = manager(tmp_path)
    m.protocol_profiles.set("r1", "gnmi")
    m.rename_device("r1", "edge1")
    assert m.protocol_profiles.get("edge1")["protocol"] == "gnmi"
    m.inv.delete("edge1")
    assert m.protocol_profiles.get("edge1") is None


def test_cli_and_scopes_expose_ph3_read_operations_without_generic_write():
    p = build_parser()
    a = p.parse_args(["protocol", "set", "r1", "restconf", "--allow-cli-fallback"])
    assert a.cmd == "protocol" and a.protocol == "restconf" and a.allow_cli_fallback
    assert p.parse_args(["protocol", "capabilities", "r1"]).action == "capabilities"
    assert p.parse_args(["protocol", "state", "r1", "--path", "/restconf/data/x:y"]).action == "state"
    assert p.parse_args(["protocol", "subscribe-once", "r1", "--path", "/interfaces"]).action == "subscribe-once"
    t = p.parse_args(["trace", "start", "r1", "--protocol", "gnmi"])
    assert t.protocol == "gnmi"
    assert {"protocol:read", "protocol:write"} <= VALID_SCOPES


def test_api_token_protocol_write_requires_operator(tmp_path):
    m = manager(tmp_path)
    tokens = ApiTokens(m.db.conn)
    with pytest.raises(ValueError):
        tokens.create("bad", ["protocol:write"], role="viewer")
    _id, raw = tokens.create("ok", ["protocol:read", "protocol:write"], role="operator")
    assert tokens.verify(raw)["role"] == "operator"


def test_protocol_api_and_web_rbac_surface(tmp_path, monkeypatch):
    import http.client
    import threading

    from netconfig.web import Console, _Server
    from netconfig.web_ui import render_protocols_page

    m = manager(tmp_path)
    m.protocol_profiles.set("r1", "restconf")

    class H:
        manager = m
        def _csrf_field(self): return '<input name=csrf value=x>'

    viewer = render_protocols_page(H(), {"role": "viewer"})
    operator = render_protocols_page(H(), {"role": "operator"})
    assert "/protocol-save" not in viewer and "/protocol-collect" not in viewer
    assert "/protocol-save" in operator and "/protocol-collect" in operator

    monkeypatch.setattr(m, "protocol_capabilities", lambda device: {"protocol": "restconf", "root": "/restconf"})
    _, raw = ApiTokens(m.db.conn).create("proto-reader", ["protocol:read"], role="viewer")
    Console.manager = m
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        conn.request("GET", "/api/v1/protocol-profiles", headers={"Authorization": "Bearer " + raw})
        res = conn.getresponse(); payload = json.loads(res.read())
        assert res.status == 200 and payload[0]["profile"]["protocol"] == "restconf"
        conn.request("GET", "/api/v1/protocol-capabilities/r1", headers={"Authorization": "Bearer " + raw})
        res = conn.getresponse(); payload = json.loads(res.read())
        assert res.status == 200 and payload["protocol"] == "restconf"
    finally:
        conn.close(); server.shutdown(); server.server_close(); thread.join(timeout=5); m.db.close()
