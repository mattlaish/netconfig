"""Web-console management of SNMP vendor profiles (upload / reload / remove).

Covers the gap where the declarative SNMP vendor-profile framework was manageable
only from the CLI: the SNMP page now lists profiles and an operator with
manage_devices can upload a validated JSON profile, reload from disk, and remove
operator-installed profiles, mirroring the MIB library.
"""
import http.client
import json
import threading
import uuid

from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server

_VALID_PROFILE = {
    "schema_version": 1,
    "id": "test.widget",
    "version": "1.0",
    "vendor": "TestVendor",
    "product": "Widget",
    "match": {"sysobject_prefixes": ["1.3.6.1.4.1.99999"]},
    "collections": [{"id": "c1", "root": "1.3.6.1.4.1.99999.1", "max_values": 10}],
}


def _manager(tmp_path):
    return Manager(str(tmp_path / "home"))


def _start_console(manager, role="admin"):
    web._SESSIONS.clear()
    token = "vp-session"
    csrf = "vp-csrf"
    web._SESSIONS[token] = {"username": "vptester", "role": role,
                            "csrf": csrf, "created": 1.0}
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, token, csrf


def _request(server, token, method, path, form=None, multipart=None, csrf=None):
    import urllib.parse
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Cookie": f"ncsid={token}"}
    body = None
    if multipart is not None:
        boundary = "----netconfigtest" + uuid.uuid4().hex
        filename, content = multipart
        parts = []
        if csrf is not None:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"csrf\"\r\n\r\n{csrf}\r\n")
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"profile\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/json\r\n\r\n")
        body = ("".join(parts)).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif form is not None:
        body = urllib.parse.urlencode(form, doseq=True)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    status = response.status
    loc = response.getheader("Location")
    conn.close()
    return status, loc, data


def _stop(server, thread, manager):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    web._SESSIONS.clear()
    manager.close()


def test_snmp_page_lists_builtin_vendor_profile(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "admin")
    try:
        status, _loc, data = _request(server, token, "GET", "/snmp")
        text = data.decode()
        assert status == 200
        assert "SNMP vendor profiles" in text
        # the shipped fortinet fortigate profile ships in usr/share
        assert "fortinet" in text.lower()
        # an admin sees the upload control
        assert 'action="/vendor-profile-upload"' in text
    finally:
        _stop(server, thread, manager)


def test_admin_can_upload_reload_and_remove_profile(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "admin")
    try:
        payload = json.dumps(_VALID_PROFILE).encode()
        status, loc, _d = _request(server, token, "POST", "/vendor-profile-upload",
                                   multipart=("widget.json", payload), csrf=csrf)
        assert status in (302, 303)
        assert "profile_notice" in (loc or "")
        assert "test.widget" in manager.vendor_profiles.profiles

        # remove it again
        status, loc, _d = _request(server, token, "POST", "/vendor-profile-delete",
                                   form={"csrf": csrf, "id": "test.widget"})
        assert status in (302, 303)
        assert "test.widget" not in manager.vendor_profiles.profiles
    finally:
        _stop(server, thread, manager)


def test_invalid_profile_upload_is_rejected_cleanly(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "admin")
    try:
        bad = json.dumps({"schema_version": 1, "id": "bad"}).encode()
        status, loc, _d = _request(server, token, "POST", "/vendor-profile-upload",
                                   multipart=("bad.json", bad), csrf=csrf)
        assert status in (302, 303)
        assert "profile_error" in (loc or "")
        assert "bad" not in manager.vendor_profiles.profiles
    finally:
        _stop(server, thread, manager)


def test_upload_requires_csrf(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "admin")
    try:
        payload = json.dumps(_VALID_PROFILE).encode()
        status, _loc, _d = _request(server, token, "POST", "/vendor-profile-upload",
                                    multipart=("widget.json", payload), csrf="wrong")
        assert status == 403
        assert "test.widget" not in manager.vendor_profiles.profiles
    finally:
        _stop(server, thread, manager)


def test_viewer_cannot_manage_profiles(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "viewer")
    try:
        status, _loc, data = _request(server, token, "GET", "/snmp")
        assert status == 200
        # viewer sees the section but no upload control
        assert 'action="/vendor-profile-upload"' not in data.decode()
        payload = json.dumps(_VALID_PROFILE).encode()
        status, _loc, _d = _request(server, token, "POST", "/vendor-profile-upload",
                                    multipart=("widget.json", payload), csrf=csrf)
        assert status == 403
        assert "test.widget" not in manager.vendor_profiles.profiles
    finally:
        _stop(server, thread, manager)
