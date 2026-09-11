import http.client
import json
import threading

import pytest

from netconfig.apitokens import ApiTokens, VALID_SCOPES
from netconfig.db import Database
from netconfig.debug import DebugBundle
from netconfig.incidents import Incidents
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def test_incident_create_update_status_and_audit(tmp_path):
    db = Database(str(tmp_path / "incidents.db"))
    store = Incidents(db, tmp_path / "bundles")
    item = store.create("Core switch instability", "Intermittent flap", "high",
                        created_by="alice", tags=["network", "hospital"])
    assert item["incident_key"].startswith("INC-")
    assert item["severity"] == "HIGH"
    assert item["status"] == "OPEN"
    assert item["tags"] == ["network", "hospital"]

    item = store.update(item["incident_key"], "alice", severity="CRITICAL",
                        title="Core switch outage")
    assert item["severity"] == "CRITICAL"
    assert item["title"] == "Core switch outage"

    item = store.set_status(item["incident_key"], "INVESTIGATING", "bob", "on-call engaged")
    assert item["status"] == "INVESTIGATING"
    item = store.set_status(item["incident_key"], "RESOLVED", "bob")
    item = store.set_status(item["incident_key"], "CLOSED", "alice")
    assert item["closed_by"] == "alice"
    assert item["closed_ts"] is not None

    actions = [row["action"] for row in db.recent_audit(20)]
    assert "incident_create" in actions
    assert "incident_update" in actions
    assert "incident_status" in actions
    db.close()


def test_incident_transition_validation_and_reopen(tmp_path):
    db = Database(str(tmp_path / "incidents.db"))
    store = Incidents(db)
    item = store.create("test", created_by="alice")
    closed = store.set_status(item["incident_key"], "CLOSED", "alice")
    assert closed["status"] == "CLOSED"
    with pytest.raises(ValueError, match="invalid incident transition"):
        store.set_status(item["incident_key"], "RESOLVED", "alice")
    # Closed incidents can be explicitly reopened into INVESTIGATING.
    reopened = store.set_status(item["incident_key"], "INVESTIGATING", "alice")
    assert reopened["status"] == "INVESTIGATING"
    assert reopened["closed_ts"] is None
    db.close()


def test_incident_bundle_link_requires_managed_existing_bundle(tmp_path):
    db = Database(str(tmp_path / "incidents.db"))
    root = tmp_path / "bundles"
    root.mkdir()
    store = Incidents(db, root)
    item = store.create("bundle test", created_by="alice")
    (root / "netconfig-support-1.tar.gz").write_bytes(b"bundle")

    linked = store.link_bundle(item["incident_key"], "netconfig-support-1.tar.gz", "alice")
    assert [b["bundle_name"] for b in linked["bundles"]] == ["netconfig-support-1.tar.gz"]
    with pytest.raises(ValueError, match="invalid diagnostic bundle name"):
        store.link_bundle(item["incident_key"], "../outside.tar.gz", "alice")
    with pytest.raises(ValueError, match="not found"):
        store.link_bundle(item["incident_key"], "missing.tar.gz", "alice")
    unlinked = store.unlink_bundle(item["incident_key"], "netconfig-support-1.tar.gz", "alice")
    assert unlinked["bundles"] == []
    db.close()


def test_incident_filters_and_input_bounds(tmp_path):
    db = Database(str(tmp_path / "incidents.db"))
    store = Incidents(db)
    store.create("one", severity="LOW", created_by="alice")
    high = store.create("two", severity="HIGH", created_by="alice")
    store.set_status(high["incident_key"], "INVESTIGATING", "alice")
    assert [i["title"] for i in store.list(severity="HIGH")] == ["two"]
    assert [i["title"] for i in store.list(status="OPEN")] == ["one"]
    with pytest.raises(ValueError):
        store.create("", created_by="alice")
    with pytest.raises(ValueError):
        store.create("bad", severity="SEVERE", created_by="alice")
    db.close()


def test_phase3d_and_incident_api_scopes_are_creatable(tmp_path):
    assert {"debug:download", "debug:admin", "incident:read", "incident:write"} <= VALID_SCOPES
    db = Database(str(tmp_path / "tokens.db"))
    tokens = ApiTokens(db.conn)
    _, raw = tokens.create("operator", ["incident:read", "incident:write", "debug:download"],
                           created_by="admin", role="operator")
    assert tokens.verify(raw)["role"] == "operator"
    with pytest.raises(ValueError, match="requires role operator"):
        tokens.create("viewer-write", ["incident:write"], role="viewer")
    db.close()


def test_incident_json_api_create_read_status_and_bundle_link(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    tokens = ApiTokens(manager.db.conn)
    _, raw = tokens.create("ir-bot", ["incident:read", "incident:write"],
                           created_by="admin", role="operator")
    dbg = DebugBundle(manager)
    bundle = dbg.root / "netconfig-support-api.tar.gz"
    bundle.write_bytes(b"test")

    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + raw, "Content-Type": "application/json"}
    try:
        body = json.dumps({"title": "API incident", "severity": "HIGH", "tags": ["api"]})
        conn.request("POST", "/api/v1/incidents", body=body, headers=headers)
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 201
        key = payload["incident_key"]

        conn.request("GET", f"/api/v1/incidents/{key}", headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200 and payload["title"] == "API incident"

        conn.request("POST", f"/api/v1/incidents/{key}/status",
                     body=json.dumps({"status": "INVESTIGATING"}), headers=headers)
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200 and payload["status"] == "INVESTIGATING"

        conn.request("POST", f"/api/v1/incidents/{key}/bundles",
                     body=json.dumps({"bundle": bundle.name}), headers=headers)
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200
        assert payload["bundles"][0]["bundle_name"] == bundle.name
    finally:
        conn.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        manager.db.close()


def test_incident_schema_is_additive_for_existing_database(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.db"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE devices(name TEXT PRIMARY KEY, host TEXT NOT NULL, port INTEGER NOT NULL DEFAULT 22, platform TEXT NOT NULL DEFAULT 'generic')")
    raw.execute("INSERT INTO devices(name,host) VALUES('legacy-sw','10.0.0.1')")
    raw.commit(); raw.close()

    db = Database(str(path))
    assert db.conn.execute("SELECT name FROM devices WHERE name='legacy-sw'").fetchone()["name"] == "legacy-sw"
    tables = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"incidents", "incident_bundles"} <= tables
    db.close()


def test_incident_cli_parser_and_new_scopes():
    from netconfig.cli import build_parser

    args = build_parser().parse_args(["incident", "create", "--title", "test", "--severity", "HIGH"])
    assert args.cmd == "incident" and args.action == "create" and args.severity == "HIGH"
    token_args = build_parser().parse_args([
        "api-token", "create", "ir", "--scope", "incident:read",
        "--scope", "debug:download", "--role", "operator",
    ])
    assert token_args.scope == ["incident:read", "debug:download"]


def test_phase3d_debug_download_scope_works_over_api(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    tokens = ApiTokens(manager.db.conn)
    _, raw = tokens.create("support", ["debug:download"], created_by="admin", role="viewer")
    dbg = DebugBundle(manager)
    bundle = dbg.root / "netconfig-support-download.tar.gz"
    bundle.write_bytes(b"support-bundle")

    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        conn.request("GET", f"/api/v1/debug/bundles/{bundle.name}",
                     headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); data = response.read()
        assert response.status == 200
        assert data == b"support-bundle"
        assert response.getheader("Content-Type") == "application/gzip"
    finally:
        conn.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        manager.db.close()


def test_incident_timeline_resolves_authoritative_evidence_without_copying(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("Timeline test", created_by="alice")
    key = incident["incident_key"]

    manager.db.audit("noc", "device_note", "sw1", "authoritative audit detail")
    audit_id = manager.db.conn.execute("SELECT max(id) AS id FROM audit").fetchone()["id"]
    manager.db.record_syslog("10.0.0.1", "%SYS-5-CONFIG_I: Configured from console")
    syslog_id = manager.db.conn.execute("SELECT max(id) AS id FROM syslog_events").fetchone()["id"]
    manager.inv.log_run("sw1", True, True, "changed")
    run_id = manager.db.conn.execute("SELECT max(id) AS id FROM runs").fetchone()["id"]
    manager.db.conn.execute(
        "INSERT INTO compliance_runs(ts,standard,run_by,total,passed,failed,report) VALUES(?,?,?,?,?,?,?)",
        (1234.5, "PCI-DSS", "auditor", 2, 1, 1, '{"secret":"authoritative-report"}'))
    manager.db.conn.commit()
    compliance_id = manager.db.conn.execute(
        "SELECT max(id) AS id FROM compliance_runs").fetchone()["id"]

    manager.store.save("sw1", "hostname sw1\ninterface Gi1\n description old\n")
    manager.store.set_baseline("sw1")
    manager.store.save("sw1", "hostname sw1\ninterface Gi1\n description changed\n")
    drift_link = manager.incidents.link_drift(key, "sw1", "alice", "suspected drift")
    pinned_ref = json.loads(drift_link["source_ref"])

    manager.incidents.link_evidence(key, "audit", audit_id, "alice")
    manager.incidents.link_evidence(key, "syslog", syslog_id, "alice")
    manager.incidents.link_evidence(key, "collection", run_id, "alice")
    manager.incidents.link_evidence(key, "compliance", compliance_id, "alice")
    bundle_root = tmp_path / "home" / "debug-bundles"
    bundle_root.mkdir(exist_ok=True)
    (bundle_root / "netconfig-support-timeline.tar.gz").write_bytes(b"bundle")
    manager.incidents.link_bundle(key, "netconfig-support-timeline.tar.gz", "alice")

    # Later collection must not rewrite the drift reference captured above.
    manager.store.save("sw1", "hostname sw1\ninterface Gi1\n description later\n")
    timeline = manager.incidents.timeline(key)
    kinds = {item["kind"] for item in timeline}
    assert {"incident", "incident_audit", "audit", "syslog", "collection",
            "compliance", "drift", "bundle"} <= kinds
    drift = next(item for item in timeline if item["kind"] == "drift")
    assert drift["source_id"]["current_stamp"] == pinned_ref["current_stamp"]
    assert drift["drifted"] is True
    # Timeline dereferences metadata but does not replay external authoritative payloads.
    timeline_json = json.dumps(timeline)
    assert "%SYS-5-CONFIG_I" not in timeline_json
    assert "authoritative audit detail" not in timeline_json
    assert "authoritative-report" not in timeline_json

    # Reference table stores pointers/link metadata, not copied authoritative content.
    refs = manager.db.conn.execute(
        "SELECT source_type,source_ref,note FROM incident_evidence_links WHERE incident_id=?",
        (incident["id"],)).fetchall()
    serialized = json.dumps([dict(r) for r in refs])
    assert "%SYS-5-CONFIG_I" not in serialized
    assert "authoritative audit detail" not in serialized
    assert "authoritative-report" not in serialized
    manager.db.close()


def test_incident_evidence_validation_dedup_and_missing_source_marker(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("Evidence test", created_by="alice")
    key = incident["incident_key"]
    manager.db.record_syslog("10.0.0.2", "linkDown")
    sid = manager.db.conn.execute("SELECT max(id) AS id FROM syslog_events").fetchone()["id"]

    first = manager.incidents.link_evidence(key, "syslog", sid, "alice", "port event")
    second = manager.incidents.link_evidence(key, "syslog", sid, "alice", "ignored duplicate")
    assert first["id"] == second["id"]
    assert len(manager.incidents.evidence_links(incident["id"])) == 1
    with pytest.raises(ValueError, match="evidence not found"):
        manager.incidents.link_evidence(key, "syslog", 999999, "alice")
    with pytest.raises(ValueError, match="invalid incident evidence type"):
        manager.incidents.link_evidence(key, "packet", 1, "alice")

    manager.db.conn.execute("DELETE FROM syslog_events WHERE id=?", (sid,))
    manager.db.conn.commit()
    item = next(x for x in manager.incidents.timeline(key) if x.get("link_id") == first["id"])
    assert item["available"] is False
    assert "no longer available" in item["summary"]
    links = manager.incidents.unlink_evidence(key, first["id"], "alice")
    assert links == []
    manager.db.close()


def test_incident_drift_evidence_requires_archived_baseline_and_is_path_safe(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    key = manager.incidents.create("Drift test", created_by="alice")["incident_key"]
    with pytest.raises(ValueError, match="no baseline"):
        manager.incidents.link_drift(key, "sw1", "alice")

    manager.store.save("sw1", "hostname sw1\n")
    manager.store.set_baseline("sw1")
    manager.store.save("sw1", "hostname sw1-new\n")
    with pytest.raises(ValueError, match="drift evidence"):
        manager.incidents.link_evidence(key, "drift", {
            "device": "sw1", "baseline_stamp": "../outside.cfg",
            "current_stamp": manager.store.versions("sw1")[-1]["stamp"],
        }, "alice")
    manager.db.close()


def test_incident_timeline_api_link_read_and_unlink(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    tokens = ApiTokens(manager.db.conn)
    _, raw = tokens.create("ir-timeline", ["incident:read", "incident:write"],
                           created_by="admin", role="operator")
    incident = manager.incidents.create("API timeline", created_by="admin")
    manager.db.record_syslog("10.10.10.1", "configuration saved")
    sid = manager.db.conn.execute("SELECT max(id) AS id FROM syslog_events").fetchone()["id"]

    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + raw, "Content-Type": "application/json"}
    key = incident["incident_key"]
    try:
        conn.request("POST", f"/api/v1/incidents/{key}/evidence",
                     body=json.dumps({"source_type": "syslog", "source_id": sid,
                                      "note": "change event"}), headers=headers)
        response = conn.getresponse(); linked = json.loads(response.read())
        assert response.status == 200 and linked["source_type"] == "syslog"

        conn.request("GET", f"/api/v1/incidents/{key}/timeline",
                     headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); timeline = json.loads(response.read())
        assert response.status == 200
        assert any(x["kind"] == "syslog" and x["source_id"] == str(sid) for x in timeline)

        conn.request("GET", f"/api/v1/incidents/{key}/evidence",
                     headers={"Authorization": "Bearer " + raw})
        response = conn.getresponse(); evidence = json.loads(response.read())
        assert response.status == 200 and evidence[0]["id"] == linked["id"]

        conn.request("POST", f"/api/v1/incidents/{key}/evidence/{linked['id']}/unlink",
                     body="{}", headers=headers)
        response = conn.getresponse(); remaining = json.loads(response.read())
        assert response.status == 200 and remaining == []
    finally:
        conn.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        manager.db.close()


def test_phase4b_schema_and_cli_parser(tmp_path):
    db = Database(str(tmp_path / "phase4b.db"))
    cols = {r["name"] for r in db.conn.execute(
        "PRAGMA table_info(incident_evidence_links)").fetchall()}
    assert {"id", "incident_id", "source_type", "source_ref", "linked_by", "linked_ts", "note"} <= cols
    db.close()

    from netconfig.cli import build_parser
    args = build_parser().parse_args([
        "incident", "link-evidence", "INC-2026-000001", "syslog", "42", "--note", "link flap",
    ])
    assert args.action == "link-evidence" and args.type == "syslog" and args.source_id == "42"
    args = build_parser().parse_args(["incident", "timeline", "INC-2026-000001", "--limit", "25"])
    assert args.action == "timeline" and args.limit == 25


def _read_case_archive(path):
    import tarfile
    with tarfile.open(path, "r:gz") as tar:
        files = {}
        for member in tar.getmembers():
            if member.isfile():
                data = tar.extractfile(member).read()
                files[member.name.split("/", 1)[-1]] = data
        return files


def test_phase4c_case_export_is_reference_only_and_embeds_linked_bundle_verbatim(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create(
        "Case export password=hunter2", "operator token=should-not-leak", created_by="alice")
    key = incident["incident_key"]

    manager.db.audit("noc", "device_note", "sw1", "AUTHORITATIVE-AUDIT-SECRET")
    audit_id = manager.db.conn.execute("SELECT max(id) AS id FROM audit").fetchone()["id"]
    manager.db.record_syslog("10.0.0.10", "AUTHORITATIVE-SYSLOG-PAYLOAD password=raw")
    syslog_id = manager.db.conn.execute("SELECT max(id) AS id FROM syslog_events").fetchone()["id"]
    manager.incidents.link_evidence(key, "audit", audit_id, "alice", "token=abc123")
    manager.incidents.link_evidence(key, "syslog", syslog_id, "alice")

    debug = DebugBundle(manager)
    bundle = debug.root / "netconfig-support-case-source.tar.gz"
    bundle_bytes = b"opaque-diagnostic-bundle-bytes\x00\x01"
    bundle.write_bytes(bundle_bytes)
    manager.incidents.link_bundle(key, bundle.name, "alice")

    record = manager.case_exports.export_case(key, "alice", reason="password=case-secret")
    assert record["export_key"].startswith("CEX-")
    assert record["bundle_names"] == [bundle.name]
    assert record["bundle_count"] == 1
    assert record["available"] is True
    meta, archive = manager.case_exports.get_export(key, record["export_key"])
    assert meta["sha256"] and archive.is_file()

    files = _read_case_archive(archive)
    assert files[f"bundles/{bundle.name}"] == bundle_bytes
    case = json.loads(files["case.json"])
    assert case["incident"]["incident_key"] == key
    assert case["incident"]["title"] == "Case export password=<redacted>"
    assert case["incident"]["description"] == "operator token=<redacted>"
    assert case["reason"] == "password=<redacted>"
    evidence = json.loads(files["evidence-links.json"])
    assert any(row["source_type"] == "audit" and row["source_ref"] == str(audit_id)
               for row in evidence)
    assert evidence[0]["note"] == "token=<redacted>"
    timeline = json.loads(files["timeline-references.json"])
    assert all(set(row) <= {"kind", "source_type", "source_id", "link_id", "ts", "available"}
               for row in timeline)

    # External authoritative payloads are not copied into the case indexes/package.
    archive_text = b"\n".join(v for k, v in files.items() if not k.startswith("bundles/"))
    assert b"AUTHORITATIVE-AUDIT-SECRET" not in archive_text
    assert b"AUTHORITATIVE-SYSLOG-PAYLOAD" not in archive_text
    assert b"hunter2" not in archive_text
    assert b"should-not-leak" not in archive_text
    assert b"abc123" not in archive_text
    assert b"case-secret" not in archive_text

    # Manifest checksum and payload hashes are independently verifiable.
    import hashlib
    digest_line = files["manifest.sha256"].decode().split()[0]
    assert digest_line == hashlib.sha256(files["manifest.json"]).hexdigest()
    manifest = json.loads(files["manifest.json"])
    listed = {row["path"]: row for row in manifest["files"]}
    assert listed[f"bundles/{bundle.name}"]["sha256"] == hashlib.sha256(bundle_bytes).hexdigest()
    manager.db.close()


def test_phase4c_case_export_selection_missing_and_unlinked_fail_closed(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    key = manager.incidents.create("Bundle selection", created_by="alice")["incident_key"]
    debug = DebugBundle(manager)
    a = debug.root / "a.tar.gz"; a.write_bytes(b"aaa")
    b = debug.root / "b.tar.gz"; b.write_bytes(b"bbb")
    other = debug.root / "other.tar.gz"; other.write_bytes(b"other")
    manager.incidents.link_bundle(key, a.name, "alice")
    manager.incidents.link_bundle(key, b.name, "alice")

    record = manager.case_exports.export_case(key, "alice", [b.name])
    _meta, archive = manager.case_exports.get_export(key, record["export_key"])
    files = _read_case_archive(archive)
    assert f"bundles/{b.name}" in files
    assert f"bundles/{a.name}" not in files

    with pytest.raises(ValueError, match="not linked"):
        manager.case_exports.export_case(key, "alice", [other.name])
    with pytest.raises(ValueError, match="invalid diagnostic bundle name"):
        manager.case_exports.export_case(key, "alice", ["../a.tar.gz"])

    # Default export records a linked-but-pruned bundle as missing rather than
    # inventing/replacing evidence; an explicitly requested missing file fails.
    a.unlink()
    record = manager.case_exports.export_case(key, "alice")
    assert record["missing_bundles"] == [a.name]
    with pytest.raises(ValueError, match="not found"):
        manager.case_exports.export_case(key, "alice", [a.name])
    manager.db.close()


def test_phase4c_case_export_budget_and_record_path_validation(tmp_path, monkeypatch):
    import netconfig.caseexport as caseexport
    manager = Manager(str(tmp_path / "home"))
    key = manager.incidents.create("Budget", created_by="alice")["incident_key"]
    debug = DebugBundle(manager)
    bundle = debug.root / "budget.tar.gz"; bundle.write_bytes(b"12345")
    manager.incidents.link_bundle(key, bundle.name, "alice")
    monkeypatch.setattr(caseexport, "MAX_CASE_BUNDLE_BYTES", 4)
    with pytest.raises(ValueError, match="byte budget"):
        manager.case_exports.export_case(key, "alice")
    assert manager.case_exports.get_export(key, "../bad")[0] is None
    manager.db.close()


def test_phase4c_case_export_scope_role_schema_and_cli(tmp_path):
    assert "incident:export" in VALID_SCOPES
    db = Database(str(tmp_path / "phase4c.db"))
    cols = {r["name"] for r in db.conn.execute(
        "PRAGMA table_info(incident_case_exports)").fetchall()}
    assert {"incident_id", "export_key", "filename", "created_by", "created_ts", "reason",
            "bundle_names", "missing_bundles", "bundle_count", "size", "sha256"} <= cols
    tokens = ApiTokens(db.conn)
    with pytest.raises(ValueError, match="requires role operator"):
        tokens.create("bad", ["incident:export"], created_by="admin", role="viewer")
    _, raw = tokens.create("good", ["incident:export"], created_by="admin", role="operator")
    assert tokens.verify(raw)["role"] == "operator"
    db.close()

    from netconfig.cli import build_parser
    args = build_parser().parse_args([
        "incident", "export-case", "INC-2026-000001", "--bundle", "one.tar.gz",
        "--bundle", "two.tar.gz", "--reason", "vendor case",
    ])
    assert args.action == "export-case" and args.bundle == ["one.tar.gz", "two.tar.gz"]
    args = build_parser().parse_args(["incident", "exports", "INC-2026-000001", "--limit", "25"])
    assert args.action == "exports" and args.limit == 25


def test_phase4c_case_export_api_create_list_download_and_scope(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("API case", created_by="admin")
    key = incident["incident_key"]
    debug = DebugBundle(manager)
    bundle = debug.root / "api-case.tar.gz"; bundle.write_bytes(b"api-bundle")
    manager.incidents.link_bundle(key, bundle.name, "admin")
    tokens = ApiTokens(manager.db.conn)
    _, export_raw = tokens.create(
        "case-exporter", ["incident:read", "incident:export"], created_by="admin", role="operator")
    _, read_raw = tokens.create(
        "case-reader", ["incident:read"], created_by="admin", role="viewer")

    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try:
        def request(method, path, raw, body=None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            headers = {"Authorization": "Bearer " + raw}
            if body is not None:
                headers["Content-Type"] = "application/json"
                body = json.dumps(body)
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse(); data = response.read(); headers_out = dict(response.getheaders())
            conn.close()
            return response.status, headers_out, data

        status, _headers, data = request(
            "POST", f"/api/v1/incidents/{key}/exports", export_raw,
            {"bundles": [bundle.name], "reason": "vendor escalation"})
        assert status == 201
        created = json.loads(data)
        export_key = created["export_key"]

        status, _headers, data = request("GET", f"/api/v1/incidents/{key}/exports", read_raw)
        assert status == 200
        rows = json.loads(data)
        assert rows[0]["export_key"] == export_key

        status, _headers, _data = request(
            "GET", f"/api/v1/incidents/{key}/exports/{export_key}", read_raw)
        assert status == 403

        status, headers, data = request(
            "GET", f"/api/v1/incidents/{key}/exports/{export_key}", export_raw)
        assert status == 200 and data.startswith(b"\x1f\x8b")
        assert headers["Content-Type"] == "application/gzip"
        assert "attachment" in headers["Content-Disposition"]

        audits = manager.db.recent_audit(50)
        assert any(a["action"] == "incident_case_export_create" and a["target"] == key for a in audits)
        assert any(a["action"] == "incident_case_export_download" and a["target"] == key for a in audits)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        manager.db.close()


def test_phase4c_case_download_rejects_tampered_archive(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("Tamper check", created_by="admin")
    key = incident["incident_key"]
    record = manager.case_exports.export_case(key, "admin")
    _meta, path = manager.case_exports.get_export(key, record["export_key"])
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="integrity mismatch"):
        manager.case_exports.record_download(key, record["export_key"], "admin")
    assert any(row["action"] == "incident_case_export_integrity_failure"
               for row in manager.db.recent_audit(20))
    manager.db.close()
