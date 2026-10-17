"""Regression tests for the 2026-10-17 security policy fixes.

* REST protocol-profile writes require approver/admin, as in the console.
* debug:create / debug:admin token scopes require admin; scopes above a token's
  role are dropped at use time, so tokens issued before the change lose them.
* Operator-facing password policy (minimum length, not equal to username).
"""
import http.client
import json
import threading
import time
import urllib.parse

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig.users import MIN_PASSWORD_LENGTH, validate_password
import netconfig.web as web
from netconfig.web import Console, _Server


def _manager(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="r1", host="192.0.2.1", port=22, platform="generic", device_type="network",
                 secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
                 enabled=True, tags=[], notes="", snmp_version="", snmp_ref=None)
    return m


def _serve(manager):
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server, thread, manager):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    web._SESSIONS.clear()
    manager.close()


def _post(server, path, form, headers):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    body = urllib.parse.urlencode(form, doseq=True)
    conn.request("POST", path, body=body,
                 headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, data


def test_api_protocol_profile_write_requires_approver_or_admin(tmp_path):
    m = _manager(tmp_path)
    tokens = ApiTokens(m.db.conn)
    _, op = tokens.create("op", ["protocol:write"], role="operator")
    _, ap = tokens.create("ap", ["protocol:write"], role="approver")
    server, thread = _serve(m)
    try:
        form = {"device": "r1", "protocol": "restconf", "secret_ref": "vault-r1"}
        status, data = _post(server, "/api/v1/protocol-profiles", form, {"Authorization": "Bearer " + op})
        assert status == 403
        assert json.loads(data)["error"] == "insufficient_scope"
        assert m.protocol_profiles.get("r1") is None
        status, _ = _post(server, "/api/v1/protocol-profiles", form, {"Authorization": "Bearer " + ap})
        assert status == 201
        assert m.protocol_profiles.get("r1")["protocol"] == "restconf"
    finally:
        _stop(server, thread, m)


def test_operator_token_can_still_collect_with_protocol_write(tmp_path):
    m = _manager(tmp_path)
    _, op = ApiTokens(m.db.conn).create("op", ["protocol:write"], role="operator")
    assert "protocol:write" in ApiTokens(m.db.conn).verify(op)["scopes"]
    m.close()


def test_debug_create_scope_requires_admin_role(tmp_path):
    m = _manager(tmp_path)
    tokens = ApiTokens(m.db.conn)
    for role in ("viewer", "operator", "approver"):
        with pytest.raises(ValueError, match="requires role admin"):
            tokens.create(f"dbg-{role}", ["debug:create"], role=role)
        with pytest.raises(ValueError, match="requires role admin"):
            tokens.create(f"dbga-{role}", ["debug:admin"], role=role)
    _, raw = tokens.create("dbg-admin", ["debug:create"], role="admin")
    assert "debug:create" in tokens.verify(raw)["scopes"]
    # Delegated read/download stays available to a support token (by design).
    _, support = tokens.create("support", ["debug:read", "debug:download"], role="viewer")
    assert tokens.verify(support)["scopes"] == {"debug:read", "debug:download"}
    m.close()


def test_scopes_above_token_role_are_dropped_at_use_time(tmp_path):
    """A token stored before a minimum role was raised cannot keep using it."""
    m = _manager(tmp_path)
    tokens = ApiTokens(m.db.conn)
    raw = "nct_legacy-viewer-token"
    m.db.conn.execute(
        "INSERT INTO api_tokens(name, token_hash, scopes, role, created_by, created_ts, disabled) "
        "VALUES (?,?,?,?,?,?,0)",
        ("legacy", __import__("hashlib").sha256(raw.encode()).hexdigest(),
         json.dumps(["debug:create", "debug:read", "incident:write"]), "viewer", "test", time.time()))
    m.db.conn.commit()
    assert tokens.verify(raw)["scopes"] == {"debug:read"}
    server, thread = _serve(m)
    try:
        status, data = _post(server, "/api/v1/debug/bundles", {}, {"Authorization": "Bearer " + raw})
        assert status == 403
        assert json.loads(data)["required"] == "debug:create"
    finally:
        _stop(server, thread, m)


@pytest.mark.parametrize("password", ["", "short", "x" * (MIN_PASSWORD_LENGTH - 1), "a" * 1025])
def test_validate_password_rejects_weak_or_oversized(password):
    with pytest.raises(ValueError):
        validate_password(password, "alice")


def test_validate_password_rejects_username_and_accepts_policy_length():
    with pytest.raises(ValueError, match="same as the username"):
        validate_password("Administrator1", "administrator1")
    validate_password("correct-horse-battery", "alice")


def _admin_console(m):
    web._SESSIONS.clear()
    web._SESSIONS["pw-session"] = {"username": "owner", "role": "admin", "csrf": "pw-csrf", "created": 1.0}
    server, thread = _serve(m)
    return server, thread, {"Cookie": "ncsid=pw-session"}


def test_console_user_create_and_update_enforce_password_policy(tmp_path):
    m = _manager(tmp_path)
    m.users.create("owner", "owner-password-1", role="admin")
    m.users.create("bob", "bob-password-123", role="viewer")
    server, thread, cookie = _admin_console(m)
    try:
        status, data = _post(server, "/user-create",
                             {"csrf": "pw-csrf", "username": "eve", "role": "viewer", "password": "short"}, cookie)
        assert status == 400 and b"at least" in data
        assert not m.users.exists("eve")
        # A rejected password must not leave a half-applied role change.
        status, _ = _post(server, "/user-update",
                          {"csrf": "pw-csrf", "username": "bob", "role": "operator", "password": "tiny"}, cookie)
        assert status == 400
        assert m.users.get("bob")["role"] == "viewer"
        assert m.users.verify("bob", "bob-password-123")
        status, _ = _post(server, "/user-create",
                          {"csrf": "pw-csrf", "username": "eve", "role": "viewer",
                           "password": "a-long-enough-password"}, cookie)
        assert status == 200 and m.users.exists("eve")
    finally:
        _stop(server, thread, m)
