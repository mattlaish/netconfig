"""HTTP coverage for account, structured-read and evidence console controls."""
import http.client
import html
import json
import os
import tarfile
import threading
import urllib.parse

import pytest

from netconfig import config, web
from netconfig.debug import DebugBundle
from netconfig.manager import Manager


class Client:
    def __init__(self, manager, server):
        self.manager = manager
        self.server = server
        self.sessions = {}

    def session(self, username="owner", role="admin"):
        if username not in self.sessions:
            if not self.manager.users.exists(username):
                self.manager.users.create(username, "test-only-password", role=role)
            token, record = web._create_managed_session(self.manager.users.get(username))
            self.sessions[username] = (token, record["csrf"])
        return self.sessions[username]

    def request(self, method, path, form=None, username="owner", role="admin", csrf=True):
        token, csrf_token = self.session(username, role)
        headers = {"Cookie": f"ncsid={token}"}
        body = None
        if form is not None:
            fields = dict(form)
            fields["csrf"] = csrf_token if csrf else "invalid-csrf"
            body = urllib.parse.urlencode(fields)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read().decode("utf-8")
        finally:
            conn.close()


@pytest.fixture
def console(tmp_path, monkeypatch):
    for name in ("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", "NETCONFIG_EVIDENCE_SIGNING_REQUIRED",
                 "NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS", "CREDENTIALS_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)
    manager = Manager(str(tmp_path / "home"))
    manager.inv.upsert(name="sw1", host="192.0.2.10", platform="generic", device_type="network")
    web._SESSIONS.clear()
    web.Console.manager = manager
    web.Console.tls_enabled = False
    server = web._Server(("127.0.0.1", 0), web.Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    client = Client(manager, server)
    client.session()
    try:
        yield client
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        web._SESSIONS.clear()
        manager.close()


def test_user_enable_disable_delete_revokes_existing_managed_sessions(console):
    manager = console.manager
    console.session("departed", "admin")
    status, _, body = console.request("GET", "/users")
    assert status == 200 and 'value="disable"' in body and 'value=delete' in body
    assert 'type=password name=password' in body
    assert console.request("POST", "/user-access", {"username": "departed", "action": "disable"})[0] == 200
    assert manager.users.get("departed")["disabled"]
    assert manager.users.verify("departed", "test-only-password") is None
    assert console.request("GET", "/users", username="departed")[0] == 303
    assert console.request("POST", "/user-access", {"username": "departed", "action": "enable"})[0] == 200
    assert not manager.users.get("departed")["disabled"]
    # Enabling the account never resurrects the old session.
    assert console.request("GET", "/users", username="departed")[0] == 303
    console.sessions.pop("departed")
    console.session("departed")
    assert console.request("POST", "/user-access", {"username": "departed", "action": "delete"})[0] == 200
    assert manager.users.get("departed") is None
    assert console.request("GET", "/users", username="departed")[0] == 303
    actions = {row["action"] for row in manager.db.recent_audit(30)}
    assert {"user_enable", "user_disable", "user_delete"} <= actions


def test_netflow_history_settings_roundtrip_and_access_guards(console):
    settings = console.manager.settings
    status, _, body = console.request("GET", "/settings?section=netflow")
    assert status == 200 and "Save flow history for 24 hours" in body
    original = dict(settings)
    form = {"section": "netflow", "netflow_enabled": "1", "netflow_history_enabled": "1"}
    assert console.request("POST", "/settings-save", form, csrf=False)[0] == 403
    console.request("POST", "/settings-save", form, username="read-only", role="viewer")
    assert settings == original
    assert console.request("POST", "/settings-save", form)[0] == 200
    assert settings["netflow_history_enabled"] is True
    assert config.load_settings(console.manager.paths)["netflow_history_enabled"] is True
    assert console.request("POST", "/settings-save", {"section": "netflow"})[0] == 200
    assert settings["netflow_history_enabled"] is False
    assert config.load_settings(console.manager.paths)["netflow_history_enabled"] is False


@pytest.mark.parametrize("action", ["disable", "delete"])
def test_current_account_cannot_be_disabled_or_deleted(console, action):
    assert console.request("POST", "/user-access", {"username": "owner", "action": action})[0] == 400
    assert not console.manager.users.get("owner")["disabled"]


def test_role_update_revalidates_session_and_rejects_invalid_or_last_admin_demotion(console):
    console.session("departed", "admin")
    assert console.request("POST", "/user-update", {"username": "departed", "role": "viewer"})[0] == 200
    assert console.request("GET", "/users", username="departed")[0] == 403
    assert console.request("POST", "/user-update", {"username": "owner", "role": "viewer"})[0] == 400
    assert console.request("POST", "/user-update", {"username": "departed", "role": "root", "password": "not-applied"})[0] == 400
    assert console.manager.users.get("departed")["role"] == "viewer"
    with pytest.raises(ValueError, match="last enabled admin"):
        console.manager.users.change_access("owner", actor="another-admin", role="viewer")


def test_concurrent_admin_removal_preserves_one_enabled_admin(console):
    users = console.manager.users
    users.create("second", "test-only-password", role="admin")
    errors = []

    def disable(username):
        try:
            users.change_access(username, actor="separate-test-actor", disabled=True)
        except ValueError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=disable, args=(name,)) for name in ("owner", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(errors) == 1 and "last enabled admin" in errors[0]
    assert sum(u["role"] == "admin" and not u["disabled"] for u in users.all()) == 1


def test_profile_delete_preserves_device_and_is_audited(console):
    manager = console.manager
    manager.protocol_profiles.set("sw1", "netconf")
    status, _, body = console.request("GET", "/protocols?device=sw1")
    assert status == 200 and 'action="/protocol-delete"' in body and 'action="/protocol-inspect"' in body
    status, _, _ = console.request("POST", "/protocol-delete", {"device": "sw1"})
    assert status == 303
    assert manager.protocol_profiles.get("sw1") is None
    assert manager.inv.get("sw1") is not None
    assert any(row["action"] == "protocol_profile_delete" for row in manager.db.recent_audit(20))
    assert console.request("POST", "/protocol-delete", {"device": "sw1"})[0] == 404


@pytest.mark.parametrize("operation,method", [
    ("capabilities", "protocol_capabilities"), ("read-state", "protocol_read_state"),
    ("subscribe-once", "protocol_subscribe_once"),
])
def test_explicit_protocol_inspection_delegates_only_bounded_reads(console, monkeypatch, operation, method):
    calls = []

    def read(device, **kwargs):
        calls.append((device, kwargs))
        return {"data": "<script>hostile</script>", "read": True}

    monkeypatch.setattr(console.manager, method, read)
    assert console.request("GET", "/protocols?device=sw1")[0] == 200
    assert calls == []
    status, _, body = console.request("POST", "/protocol-inspect", {"device": "sw1", "operation": operation, "path": "/interfaces"}, username="reader", role="operator")
    assert status == 200 and "&lt;script&gt;hostile&lt;/script&gt;" in body
    assert calls == [("sw1", {} if operation == "capabilities" else {"path": "/interfaces"})]


def test_protocol_collect_uses_real_collect_capability(console, monkeypatch):
    from types import SimpleNamespace

    calls = []

    def collect(device):
        calls.append(device)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(console.manager, "protocol_collect", collect)
    assert console.request("POST", "/protocol-collect", {"device": "sw1"}, username="reader", role="operator")[0] == 303
    assert calls == ["sw1"]


def test_evidence_policy_roundtrip_normalizes_pins_preserves_other_settings(console, monkeypatch):
    manager = console.manager
    manager.settings["backup_keep"] = 37
    env_pin = "SHA256:" + "e" * 64
    monkeypatch.setenv("NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS", env_pin)
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_REQUIRED", "true")
    status, _, body = console.request("GET", "/settings?section=evidence")
    assert status == 200 and 'name=evidence_signing_required' in body and env_pin in body
    colon_digest = ":".join(["AB"] * 32)
    form = {"section": "evidence", "evidence_signing_required": "1",
            "evidence_trusted_fingerprints": colon_digest + "\n" + "a" * 64 + "," + "a" * 64}
    assert console.request("POST", "/settings-save", form)[0] == 200
    stored = json.loads(open(manager.paths.settings_file, encoding="utf-8").read())
    assert stored["evidence_signing_required"] is True and stored["backup_keep"] == 37
    assert stored["evidence_trusted_fingerprints"] == ["SHA256:" + "a" * 64, "SHA256:" + "ab" * 32]
    assert env_pin not in stored["evidence_trusted_fingerprints"]
    assert console.request("POST", "/settings-save", {"section": "evidence", "evidence_trusted_fingerprints": ""})[0] == 200
    assert manager.settings["evidence_signing_required"] is False
    assert manager.settings["evidence_trusted_fingerprints"] == []
    assert '"required": true' in html.unescape(console.request("GET", "/settings?section=evidence")[2])


def test_invalid_evidence_policy_does_not_mutate_settings_or_disk(console):
    manager = console.manager
    config.save_settings(manager.paths, manager.settings)
    before = dict(manager.settings)
    disk = open(manager.paths.settings_file, encoding="utf-8").read()
    assert console.request("POST", "/settings-save", {"section": "evidence", "evidence_signing_required": "1", "evidence_trusted_fingerprints": "not-a-fingerprint"})[0] == 400
    assert manager.settings == before
    assert open(manager.paths.settings_file, encoding="utf-8").read() == disk


def test_device_capture_creates_real_redacted_archive_without_polling(console, monkeypatch):
    def no_io(*args, **kwargs):
        raise AssertionError("Unexpected device I/O")

    monkeypatch.setattr(console.manager, "collect", no_io)
    monkeypatch.setattr(console.manager, "snmp_poll", no_io)
    console.manager.inv.upsert(name="sw1", host="192.0.2.10", platform="generic", notes="token=not-a-real-secret")
    status, _, body = console.request("GET", "/diagnostics")
    assert status == 200 and "Per-device capture" in body and "Effective signing status" in body
    assert console.request("POST", "/debug-create", {"mode": "device", "device": "sw1"})[0] == 303
    bundles = DebugBundle(console.manager)
    archive = bundles.get_bundle(bundles.list_bundles()[0]["name"])
    with tarfile.open(archive) as stream:
        names = stream.getnames()
        assert any(name.endswith("/security/redaction-report.json") for name in names)
        inventory = next(member for member in stream.getmembers() if member.name.endswith("/device/inventory.json"))
        assert json.load(stream.extractfile(inventory))["name"] == "sw1"
    assert console.request("POST", "/debug-create", {"mode": "device", "device": "missing"})[0] == 400


def test_required_signing_fails_closed_without_key(console):
    console.manager.settings["evidence_signing_required"] = True
    status, _, body = console.request("POST", "/debug-create", {"mode": "full"})
    assert status == 400 and "required" in body
    assert DebugBundle(console.manager).list_bundles() == []


def test_bundle_verification_displays_validity_separately_from_trust(console, monkeypatch):
    monkeypatch.setattr(DebugBundle, "verify_bundle", lambda self, name: {"signature_valid": True, "trusted": False})
    status, _, body = console.request("POST", "/debug-verify", {"name": "capture.tar.gz"})
    assert status == 200 and "NOT trusted" in body


def test_unsigned_or_unsafe_bundle_verification_fails_closed(console):
    archive = DebugBundle(console.manager).collect()
    assert console.request("POST", "/debug-verify", {"name": archive.name})[0] == 409
    assert console.request("POST", "/debug-verify", {"name": "../outside.tar.gz"})[0] == 409
    assert console.request("GET", "/debug-download?name=../outside.tar.gz")[0] == 404


def test_cleanup_is_bounded_and_only_removes_old_managed_bundles(console, tmp_path):
    bundles = DebugBundle(console.manager)
    for name in ("netconfig-support-20260101.tar.gz", "netconfig-support-20260102.tar.gz"):
        (bundles.root / name).write_bytes(b"fixture")
    keep_file = bundles.root / "unrelated.txt"
    keep_file.write_text("keep")
    external = tmp_path / "external.tar.gz"
    external.write_bytes(b"keep")
    assert console.request("POST", "/debug-cleanup", {"keep": "-1"})[0] == 400
    assert len(bundles.list_bundles()) == 2
    status, _, body = console.request("POST", "/debug-cleanup", {"keep": "1"})
    assert status == 200 and "Removed 1 old bundle" in body
    assert [item["name"] for item in bundles.list_bundles()] == ["netconfig-support-20260102.tar.gz"]
    assert external.exists() and keep_file.exists()


def test_cleanup_keeps_newest_capture_across_device_and_full_bundle_names(console):
    bundles = DebugBundle(console.manager)
    old = bundles.root / "netconfig-support-20260101.tar.gz"
    new = bundles.root / "netconfig-device-support-20260102.tar.gz"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    os.utime(old, (100, 100))
    os.utime(new, (200, 200))
    assert bundles.list_bundles()[0]["name"] == new.name
    assert console.request("POST", "/debug-cleanup", {"keep": "1"})[0] == 200
    assert new.exists() and not old.exists()


def test_standalone_trace_start_list_detail_events_stop_without_incident(console):
    form = {"device": "sw1", "protocol": "snmp", "ttl": "60", "max_events": "5", "max_bytes": "4096"}
    status, headers, _ = console.request("POST", "/trace-start", form, username="reader", role="operator")
    assert status == 303 and headers["Location"].startswith("/traces?ref=PTR-")
    trace = console.manager.protocol_traces.list()[0]
    assert trace["incident_id"] is None and trace["max_events"] == 5
    console.manager.protocol_traces.record("sw1", "snmp", "poll", metadata={"password": "not-a-real-secret"})
    status, _, body = console.request("GET", headers["Location"])
    assert status == 200 and "Captured events" in body and "not-a-real-secret" not in body
    assert console.request("GET", "/traces?device=sw1&status=ACTIVE")[0] == 200
    assert console.request("POST", "/trace-stop", {"trace": trace["trace_key"]}, username="reader", role="operator")[0] == 303
    assert console.manager.protocol_traces.get(trace["id"])["status"] == "STOPPED"


@pytest.mark.parametrize("field,value", [("ttl", "1"), ("max_events", "5001"), ("max_bytes", "1"), ("protocol", "shell")])
def test_invalid_trace_budgets_and_protocol_are_rejected(console, field, value):
    form = {"device": "sw1", "protocol": "snmp", "ttl": "60", "max_events": "5", "max_bytes": "4096"}
    form[field] = value
    assert console.request("POST", "/trace-start", form)[0] == 400
    assert console.manager.protocol_traces.list() == []


def test_trace_viewer_can_read_but_cannot_start_or_stop(console):
    status, _, body = console.request("GET", "/traces", username="observer", role="viewer")
    assert status == 200 and 'href="/traces"' in body
    assert 'action="/trace-start"' not in body
    assert console.request("POST", "/trace-start", {"device": "sw1", "protocol": "snmp"}, username="observer")[0] == 403
    assert console.request("POST", "/trace-stop", {"trace": "missing"}, username="observer")[0] == 403


def test_trace_can_optionally_link_existing_incident_and_rejects_missing_references(console):
    incident = console.manager.incidents.create("Investigate", created_by="owner")
    form = {"device": "sw1", "protocol": "snmp", "incident_ref": incident["incident_key"]}
    assert console.request("POST", "/trace-start", form)[0] == 303
    assert console.manager.protocol_traces.list()[0]["incident_id"] == incident["id"]
    form["incident_ref"] = "missing"
    assert console.request("POST", "/trace-start", form)[0] == 400
    assert console.request("GET", "/traces?ref=missing")[0] == 404
    assert console.request("GET", "/traces?status=invalid")[0] == 400
    assert console.request("POST", "/trace-stop", {"trace": "missing"})[0] == 404


def test_approver_can_remove_profile_but_cannot_manage_users(console):
    console.manager.protocol_profiles.set("sw1", "netconf")
    assert console.request("POST", "/protocol-delete", {"device": "sw1"}, username="reviewer", role="approver")[0] == 303
    assert console.request("POST", "/user-access", {"username": "owner", "action": "disable"}, username="reviewer")[0] == 403


def test_operator_collection_view_has_reads_but_no_profile_mutation_forms(console):
    console.manager.protocol_profiles.set("sw1", "netconf")
    status, _, body = console.request("GET", "/protocols?device=sw1", username="reader", role="operator")
    assert status == 200 and 'action="/protocol-inspect"' in body
    assert 'action="/protocol-save"' not in body and 'action="/protocol-delete"' not in body


def test_new_pages_escape_user_device_and_trace_evidence(console):
    hostile = '<img src=x onerror="alert(1)">'
    console.manager.users.create("another", "test-only-password", fullname=hostile)
    status, _, body = console.request("GET", "/users")
    assert status == 200 and hostile not in body and "&lt;img" in body
    console.manager.inv.upsert(name=hostile, host="192.0.2.20", platform="generic")
    trace = console.manager.protocol_traces.start(hostile, "snmp", reason=hostile)
    status, _, body = console.request("GET", "/traces?ref=" + trace["trace_key"])
    assert status == 200 and hostile not in body and "&lt;img" in body


@pytest.mark.parametrize("path,form", [
    ("/user-access", {"username": "owner", "action": "delete"}),
    ("/protocol-delete", {"device": "sw1"}),
    ("/protocol-inspect", {"device": "sw1", "operation": "capabilities"}),
    ("/debug-create", {"mode": "full"}),
    ("/debug-verify", {"name": "x.tar.gz"}),
    ("/debug-cleanup", {"keep": "1"}),
    ("/settings-save", {"section": "evidence"}),
    ("/trace-start", {"device": "sw1", "protocol": "snmp"}),
    ("/trace-stop", {"trace": "missing"}),
])
def test_every_new_mutation_requires_csrf(console, path, form):
    assert console.request("POST", path, form, csrf=False)[0] == 403


@pytest.mark.parametrize("path,form", [
    ("/user-access", {"username": "owner", "action": "delete"}),
    ("/user-update", {"username": "owner", "role": "viewer"}),
    ("/protocol-delete", {"device": "sw1"}),
    ("/debug-create", {"mode": "full"}),
    ("/debug-verify", {"name": "x.tar.gz"}),
    ("/debug-cleanup", {"keep": "1"}),
    ("/settings-save", {"section": "evidence"}),
])
def test_nonadmin_cannot_perform_privileged_management(console, path, form):
    assert console.request("POST", path, form, username="reader", role="operator")[0] == 403


def test_viewer_cannot_trigger_protocol_io_or_see_bundle_controls(console):
    for path in ("/protocol-inspect", "/protocol-collect"):
        assert console.request("POST", path, {"device": "sw1", "operation": "capabilities"}, username="observer", role="viewer")[0] == 403
    status, _, body = console.request("GET", "/diagnostics", username="observer")
    assert status == 200 and 'action="/debug-create"' not in body and 'action="/debug-cleanup"' not in body
