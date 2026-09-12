import json
import tarfile
import threading
import http.client

from netconfig.apitokens import ApiTokens, VALID_SCOPES
from netconfig.manager import Manager
from netconfig.protocoltrace import safe_command
from netconfig.transport import SSHTransport
from netconfig import snmp
from netconfig.web import Console, _Server


def _manager(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(name="sw1", host="192.0.2.10", platform="cisco_ios", snmp_version="v2c")
    return m


def test_trace_session_records_metadata_and_redacts_sensitive_command(tmp_path):
    m = _manager(tmp_path)
    trace = m.protocol_traces.start("sw1", "cli_ssh", actor="alice", ttl=300)
    m.protocol_traces.record(
        "sw1", "cli_ssh", "command", operation="username admin password SuperSecret!",
        status="ok", duration_ms=12.5, tx_bytes=40, rx_bytes=99,
        metadata={"password": "never-store", "note": "token=abc"})
    events = m.protocol_traces.events(trace["trace_key"])
    assert len(events) == 1
    event = events[0]
    assert event["operation"] == "<redacted-sensitive-command>"
    assert event["metadata"]["password"] == "<redacted>"
    dumped = json.dumps(event)
    assert "SuperSecret" not in dumped and "never-store" not in dumped and "token=abc" not in dumped
    assert event["tx_bytes"] == 40 and event["rx_bytes"] == 99
    m.db.close()


def test_trace_budget_fails_closed_and_stop_is_audited(tmp_path):
    m = _manager(tmp_path)
    trace = m.protocol_traces.start("sw1", "cli_ssh", actor="alice", ttl=300, max_events=1)
    assert m.protocol_traces.record("sw1", "cli_ssh", "command", operation="show clock") == 1
    assert m.protocol_traces.record("sw1", "cli_ssh", "command", operation="show version") == 0
    assert m.protocol_traces.get(trace["trace_key"])["status"] == "LIMIT_REACHED"
    stopped = m.protocol_traces.stop(trace["trace_key"], actor="alice")
    assert stopped["status"] == "LIMIT_REACHED"
    actions = [r["action"] for r in m.db.recent_audit(20)]
    assert "protocol_trace_start" in actions and "protocol_trace_limit" in actions
    m.db.close()


def test_trace_incident_link_and_timeline(tmp_path):
    m = _manager(tmp_path)
    inc = m.incidents.create("trace incident", created_by="alice")
    trace = m.protocol_traces.start("sw1", "snmp", actor="alice", incident_ref=inc["incident_key"])
    links = m.incidents.evidence_links(inc["id"])
    assert any(x["source_type"] == "protocol_trace" and x["source_ref"] == str(trace["id"]) for x in links)
    timeline = m.incidents.timeline(inc["incident_key"])
    item = next(x for x in timeline if x.get("source_type") == "protocol_trace")
    assert item["trace_key"] == trace["trace_key"] and item["protocol"] == "snmp"
    m.db.close()


def test_snmp_udp_trace_captures_metadata_not_packet(monkeypatch):
    events = []

    class FakeSocket:
        def settimeout(self, _timeout):
            pass
        def sendto(self, payload, target):
            self.payload = payload; self.target = target
        def recvfrom(self, _size):
            return b"response-secret-bytes", ("192.0.2.10", 161)
        def close(self):
            pass

    monkeypatch.setattr(snmp.socket, "socket", lambda *a, **k: FakeSocket())
    with snmp.trace_capture(events.append):
        data = snmp._udp_exchange("192.0.2.10", 161, b"community-private-packet", 1.0, 0)
    assert data == b"response-secret-bytes"
    assert len(events) == 1
    event = events[0]
    assert event["tx_bytes"] == len(b"community-private-packet")
    assert event["rx_bytes"] == len(b"response-secret-bytes")
    assert "community-private-packet" not in json.dumps(event)
    assert "response-secret-bytes" not in json.dumps(event)


def test_ssh_execute_trace_callback_captures_no_output():
    events = []
    tp = SSHTransport("192.0.2.10", "admin", trace_callback=events.append)
    tp.prompt = b"R1#"
    def fake_write(*args, **kwargs):
        return None

    def fake_read_until(patterns, timeout):
        return (0, None, b"\r\nSECRET-DEVICE-OUTPUT\r\nR1#")

    tp._write = fake_write
    tp._read_until = fake_read_until
    out = tp.execute("show version")
    assert "SECRET-DEVICE-OUTPUT" in out
    assert len(events) == 1
    assert events[0]["event_type"] == "command"
    assert events[0]["operation"] == "show version"
    assert "SECRET-DEVICE-OUTPUT" not in json.dumps(events[0])


def test_case_export_embeds_sanitized_protocol_trace(tmp_path):
    m = _manager(tmp_path)
    inc = m.incidents.create("trace export", created_by="alice")
    trace = m.protocol_traces.start("sw1", "cli_ssh", actor="alice", incident_ref=inc["incident_key"])
    m.protocol_traces.record("sw1", "cli_ssh", "command",
                             operation="snmp-server community SuperCommunity ro",
                             metadata={"secret": "DoNotExport"})
    record = m.case_exports.export_case(inc["incident_key"], "alice")
    _, archive = m.case_exports.get_export(inc["incident_key"], record["export_key"])
    with tarfile.open(archive, "r:gz") as tar:
        member = next(x for x in tar.getmembers() if x.name.endswith("/protocol-traces.json"))
        payload = tar.extractfile(member).read().decode()
    assert trace["trace_key"] in payload
    assert "SuperCommunity" not in payload and "DoNotExport" not in payload
    assert "<redacted-sensitive-command>" in payload
    m.db.close()


def test_trace_scopes_and_rest_api(tmp_path):
    assert {"trace:read", "trace:capture"} <= VALID_SCOPES
    m = _manager(tmp_path)
    inc = m.incidents.create("api trace", created_by="alice")
    _, raw = ApiTokens(m.db.conn).create(
        "trace-api", ["trace:read", "trace:capture", "incident:read"],
        created_by="admin", role="operator")
    Console.manager = m
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + raw, "Content-Type": "application/json"}
    try:
        body = json.dumps({"device": "sw1", "protocol": "snmp", "incident": inc["incident_key"], "ttl": 300})
        conn.request("POST", "/api/v1/traces", body=body, headers=headers)
        response = conn.getresponse(); created = json.loads(response.read())
        assert response.status == 201 and created["protocol"] == "snmp"
        key = created["trace_key"]
        m.protocol_traces.record("sw1", "snmp", "udp_exchange", operation="SNMP request", tx_bytes=10, rx_bytes=20)
        conn.request("GET", f"/api/v1/traces/{key}/events", headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); events = json.loads(response.read())
        assert response.status == 200 and len(events) == 1
        conn.request("POST", f"/api/v1/traces/{key}/stop", body="{}", headers=headers)
        response = conn.getresponse(); stopped = json.loads(response.read())
        assert response.status == 200 and stopped["status"] == "STOPPED"
    finally:
        conn.close(); server.shutdown(); server.server_close(); thread.join(timeout=5); m.db.close()


def test_safe_command_hash_is_stable_and_sensitive_summary_is_redacted():
    summary1, digest1 = safe_command("username admin secret hunter2")
    summary2, digest2 = safe_command("username admin secret hunter2")
    assert summary1 == summary2 == "<redacted-sensitive-command>"
    assert digest1 == digest2 and len(digest1) == 64
    import hashlib
    assert digest1 == hashlib.sha256(b"<redacted-sensitive-command>").hexdigest()


def test_structured_protocol_trace_providers_are_available_after_ph3(tmp_path):
    m = _manager(tmp_path)
    for protocol in ("netconf", "restconf", "gnmi"):
        item = m.protocol_traces.start("sw1", protocol, actor="alice")
        assert item["protocol"] == protocol
        assert item["status"] == "ACTIVE"
        m.protocol_traces.stop(item["trace_key"], actor="alice")
    m.db.close()

def test_trace_ttl_expiry_preserves_evidence(tmp_path):
    m = _manager(tmp_path)
    trace = m.protocol_traces.start("sw1", "snmp", actor="alice", ttl=30)
    m.db.conn.execute("UPDATE protocol_trace_sessions SET expires_ts=0 WHERE id=?", (trace["id"],))
    m.db.conn.commit()
    expired = m.protocol_traces.get(trace["trace_key"])
    assert expired["status"] == "EXPIRED"
    assert m.protocol_traces.events(trace["trace_key"]) == []
    assert any(r["action"] == "protocol_trace_expire" for r in m.db.recent_audit(20))
    m.db.close()
