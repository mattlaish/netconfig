import http.client
import threading
import urllib.parse

from netconfig.debug import DebugBundle
from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server


def _start_console(manager, role="operator"):
    web._SESSIONS.clear()
    token = "test-session"
    csrf = "test-csrf"
    web._SESSIONS[token] = {
        "username": "webtester",
        "role": role,
        "csrf": csrf,
        "created": 1.0,
    }
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, token, csrf


def _request(server, token, method, path, form=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Cookie": f"ncsid={token}"}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form, doseq=True)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    headers_out = dict(response.getheaders())
    status = response.status
    conn.close()
    return status, headers_out, data


def _stop_console(server, thread, manager):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    web._SESSIONS.clear()
    manager.db.close()


def test_phase4f_incident_register_is_read_only_for_viewer(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("Viewer-visible incident", created_by="admin")
    server, thread, token, csrf = _start_console(manager, "viewer")
    try:
        status, _headers, data = _request(server, token, "GET", "/incidents")
        text = data.decode()
        assert status == 200
        assert "Viewer-visible incident" in text
        assert "/incident?ref=" in text
        assert "Create incident" not in text
        assert ">Incidents<" in text

        status, _headers, _data = _request(
            server, token, "POST", "/incident-create",
            {"csrf": csrf, "title": "should fail", "severity": "LOW"},
        )
        assert status == 403
        assert manager.incidents.get(incident["incident_key"])
        assert len(manager.incidents.list()) == 1
    finally:
        _stop_console(server, thread, manager)


def test_phase4f_operator_web_incident_lifecycle_and_timeline(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, headers, _data = _request(
            server, token, "POST", "/incident-create",
            {
                "csrf": csrf,
                "title": "Web incident",
                "severity": "HIGH",
                "tags": "critical,network",
                "description": "Created from the Phase 4F console",
            },
        )
        assert status == 303
        location = headers["Location"]
        assert location.startswith("/incident?ref=INC-")
        key = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["ref"][0]

        status, _headers, data = _request(server, token, "GET", f"/incident?ref={key}")
        text = data.decode()
        assert status == 200
        assert "Web incident" in text
        assert "Incident timeline" in text
        assert "Evidence references" in text
        assert "Protocol traces" in text
        assert "Diagnostic bundles" in text
        assert "Support-case exports" in text

        status, headers, _data = _request(
            server, token, "POST", "/incident-status",
            {"csrf": csrf, "ref": key, "status": "INVESTIGATING", "note": "triage"},
        )
        assert status == 303 and "notice=status" in headers["Location"]
        assert manager.incidents.get(key)["status"] == "INVESTIGATING"

        manager.db.audit("sensor", "external_event", "sw1", "safe reference")
        audit_id = manager.db.conn.execute("SELECT MAX(id) AS id FROM audit").fetchone()["id"]
        status, _headers, _data = _request(
            server, token, "POST", "/incident-evidence-link",
            {"csrf": csrf, "ref": key, "type": "audit", "source_ref": str(audit_id), "note": "triage evidence"},
        )
        assert status == 303
        assert any(x["source_type"] == "audit" for x in manager.incidents.evidence_links(key))

        status, _headers, data = _request(server, token, "GET", f"/incident?ref={key}")
        text = data.decode()
        assert status == 200
        assert "triage evidence" in text
        assert "incident_status" in text
    finally:
        _stop_console(server, thread, manager)


def test_phase4f_trace_bundle_case_export_and_secure_download_workflow(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    manager.inv.upsert(name="sw1", host="192.0.2.10", platform="generic")
    incident = manager.incidents.create("Integrated workflow", created_by="admin")
    key = incident["incident_key"]
    dbg = DebugBundle(manager)
    bundle = dbg.root / "netconfig-support-phase4f.tar.gz"
    bundle.write_bytes(b"diagnostic evidence")

    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, _headers, _data = _request(
            server, token, "POST", "/incident-bundle-link",
            {"csrf": csrf, "ref": key, "bundle": bundle.name},
        )
        assert status == 303

        status, _headers, _data = _request(
            server, token, "POST", "/incident-trace-start",
            {"csrf": csrf, "ref": key, "device": "sw1", "protocol": "snmp", "ttl": "300", "reason": "link issue"},
        )
        assert status == 303
        traces = manager.protocol_traces.list(incident_ref=key)
        assert len(traces) == 1 and traces[0]["status"] == "ACTIVE"
        trace_key = traces[0]["trace_key"]
        manager.protocol_traces.record("sw1", "snmp", "exchange", status="ok", tx_bytes=32, rx_bytes=64)

        status, _headers, data = _request(server, token, "GET", f"/incident?ref={key}&trace={trace_key}")
        text = data.decode()
        assert status == 200
        assert trace_key in text
        assert "exchange" in text
        assert "32 / 64" in text

        status, _headers, _data = _request(
            server, token, "POST", "/incident-trace-stop",
            {"csrf": csrf, "ref": key, "trace": trace_key},
        )
        assert status == 303
        assert manager.protocol_traces.get(trace_key)["status"] == "STOPPED"

        status, _headers, _data = _request(
            server, token, "POST", "/incident-export-create",
            {"csrf": csrf, "ref": key, "reason": "vendor escalation", "bundle": bundle.name},
        )
        assert status == 303
        exports = manager.case_exports.list_exports(key)
        assert len(exports) == 1
        export_key = exports[0]["export_key"]

        status, headers, data = _request(
            server, token, "GET",
            f"/incident-export-download?incident={urllib.parse.quote(key)}&export={urllib.parse.quote(export_key)}",
        )
        assert status == 200
        assert data.startswith(b"\x1f\x8b")
        assert headers["Content-Type"] == "application/gzip"
        assert "attachment" in headers["Content-Disposition"]
        assert any(a["action"] == "incident_case_export_download" for a in manager.db.recent_audit(50))
    finally:
        _stop_console(server, thread, manager)


def test_phase4f_csrf_and_cross_incident_trace_stop_are_fail_closed(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    manager.inv.upsert(name="sw1", host="192.0.2.10", platform="generic")
    a = manager.incidents.create("A", created_by="admin")
    b = manager.incidents.create("B", created_by="admin")
    trace = manager.protocol_traces.start("sw1", "snmp", actor="admin", incident_ref=a["incident_key"])
    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, _headers, _data = _request(
            server, token, "POST", "/incident-update",
            {"csrf": "wrong", "ref": a["incident_key"], "title": "tampered", "severity": "HIGH"},
        )
        assert status == 403
        assert manager.incidents.get(a["incident_key"])["title"] == "A"

        status, _headers, data = _request(
            server, token, "POST", "/incident-trace-stop",
            {"csrf": csrf, "ref": b["incident_key"], "trace": trace["trace_key"]},
        )
        assert status == 400
        assert b"not linked to this incident" in data
        assert manager.protocol_traces.get(trace["trace_key"])["status"] == "ACTIVE"
    finally:
        _stop_console(server, thread, manager)


def test_phase4f_web_escapes_incident_content_and_viewer_cannot_export_download(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create(
        '<img src=x onerror="alert(1)">',
        '<script>alert("description")</script>',
        created_by="admin",
        tags=['<b>tag</b>'],
    )
    key = incident["incident_key"]
    record = manager.case_exports.export_case(key, "admin")
    server, thread, token, _csrf = _start_console(manager, "viewer")
    try:
        status, _headers, data = _request(server, token, "GET", f"/incident?ref={key}")
        text = data.decode()
        assert status == 200
        assert '<img src=x onerror="alert(1)">' not in text
        assert '<script>alert("description")</script>' not in text
        assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in text
        assert '&lt;script&gt;alert(&quot;description&quot;)&lt;/script&gt;' in text
        assert '&lt;b&gt;tag&lt;/b&gt;' in text

        status, _headers, _data = _request(
            server, token, "GET",
            f"/incident-export-download?incident={urllib.parse.quote(key)}&export={urllib.parse.quote(record['export_key'])}",
        )
        assert status == 403
    finally:
        _stop_console(server, thread, manager)
