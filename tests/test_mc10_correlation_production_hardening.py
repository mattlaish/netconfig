import http.client
import json
import threading
import time
import urllib.parse

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.correlation_hardening import MAX_REPLAY_RANGE_SECONDS
from netconfig.manager import Manager
from netconfig.postgres_core import SERIAL_ID_TABLES, postgres_schema_statements
from netconfig.web import Console, _Server
import netconfig.web as web


def _manager(tmp_path):
    return Manager(str(tmp_path / "home"))


def _seed_change_sensor(m, *, incident=None, change_ts=1000.0, sensor_ts=1010.0,
                        sensor_received=None, device="app1"):
    incident = incident or m.incidents.create("MC10 incident", created_by="test")
    change = m.db.record_change_event(
        900, "EXECUTION_COMPLETED", "executed", "test", "bounded change",
        metadata={"affected_devices": [device]}, source_ts=change_ts, received_ts=change_ts)
    c = m.db.conn
    c.execute(
        "INSERT INTO sensor_transitions(sensor_key,sensor_type,device,resource,previous_status,new_status,"
        "previous_value,new_value,source,observed_at,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"application.http_status|{device}|api", "application.http_status", device, "api",
         "OK", "CRITICAL", "200", "503", "monitor", sensor_ts, "{}",
         sensor_received if sensor_received is not None else sensor_ts),
    )
    c.commit()
    sid = c.execute("SELECT max(id) AS id FROM sensor_transitions").fetchone()["id"]
    m.incidents.link_evidence(incident["incident_key"], "change_event", change["id"], "test")
    m.incidents.link_evidence(incident["incident_key"], "sensor_transition", sid, "test")
    return incident


def _insert_external(m, incident, *, event_id, source_ts, received_ts, severity="MAJOR"):
    c = m.db.conn
    cur = c.execute(
        "INSERT INTO external_events(source_system,source_event_id,domain,event_type,severity,entity_type,entity_id,summary,"
        "source_ts,received_ts,source_clock_json,metadata_json,tenant_id,source_key,idempotency_key,schema_version,"
        "payload_sha256,payload_json,ingest_principal,ingest_result,connector_type) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("mc10-test", event_id, "APPLICATION", "app.health", severity, "device", "app1", event_id,
         source_ts, received_ts, "{}", "{}", "default", "mc10-test", "idem-" + event_id, "1",
         event_id.ljust(64, "0")[:64], "{}", "test", "ACCEPTED", "APM"),
    )
    c.commit()
    m.incidents.link_evidence(incident["incident_key"], "external_event", cur.lastrowid, "test")
    return cur.lastrowid


def test_mc10_schema_postgres_surface_and_bounds(tmp_path):
    m = _manager(tmp_path)
    try:
        assert m.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
        tables = {r["name"] for r in m.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "correlation_runs" in tables
        pg = "\n".join(postgres_schema_statements()).lower()
        assert "create table if not exists correlation_runs" in pg
        assert "correlation_runs" in SERIAL_ID_TABLES
        bounds = m.correlation_hardening.bounds()
        assert bounds["max_facts_per_run"] == 500
        assert bounds["max_hypotheses_per_run"] == 25
        assert bounds["max_dependency_edges"] == 1000
        assert bounds["max_relationship_depth"] == 4
        assert bounds["max_relationship_nodes"] == 250
        assert bounds["max_incident_timeline_events"] == 2000
        assert bounds["max_replay_range_seconds"] == 604800
        assert bounds["external_payload_hard_limit_bytes"] == 262144
    finally:
        m.close()


def test_mc10_repeated_correlation_records_deterministic_replay_without_hypothesis_churn(tmp_path):
    m = _manager(tmp_path)
    try:
        incident = _seed_change_sensor(m)
        first = m.correlation.correlate(incident["incident_key"], actor="test")
        before = [dict(r) for r in m.db.conn.execute(
            "SELECT id,hypothesis_key,updated_at FROM correlation_hypotheses ORDER BY id").fetchall()]
        second = m.correlation.correlate(incident["incident_key"], actor="test")
        after = [dict(r) for r in m.db.conn.execute(
            "SELECT id,hypothesis_key,updated_at FROM correlation_hypotheses ORDER BY id").fetchall()]
        assert first["input_fingerprint"] == second["input_fingerprint"]
        assert first["result_fingerprint"] == second["result_fingerprint"]
        assert second["run"]["replay_of_id"] is not None
        assert second["run"]["deterministic_match"] is True
        assert before == after
        runs = m.correlation_hardening.runs(incident["incident_key"])
        assert len(runs) == 2 and all(r["state"] == "COMPLETED" for r in runs)
    finally:
        m.close()


def test_mc10_late_out_of_order_and_future_clock_skew_are_explicit_diagnostics(tmp_path):
    m = _manager(tmp_path)
    try:
        incident = m.incidents.create("Clock evidence", created_by="test")
        _insert_external(m, incident, event_id="e-newer", source_ts=200.0, received_ts=300.0)
        _insert_external(m, incident, event_id="e-late", source_ts=100.0, received_ts=1000.0)
        _insert_external(m, incident, event_id="e-future", source_ts=2000.0, received_ts=1000.0)
        result = m.correlation.correlate(incident["incident_key"])
        diag = result["diagnostics"]
        assert diag["late_evidence_count"] >= 1
        assert diag["future_clock_skew_count"] >= 1
        assert diag["out_of_order_count"] >= 1
        run = m.correlation_hardening.runs(incident["incident_key"], limit=1)[0]
        assert run["late_evidence_count"] >= 1
        assert run["future_skew_count"] >= 1
        assert run["out_of_order_count"] >= 1
    finally:
        m.close()


def test_mc10_replay_preview_is_bounded_deterministic_and_does_not_mutate_hypotheses(tmp_path):
    m = _manager(tmp_path)
    try:
        incident = _seed_change_sensor(m, change_ts=1000, sensor_ts=1010)
        m.correlation.correlate(incident["incident_key"])
        before = [dict(r) for r in m.db.conn.execute(
            "SELECT * FROM correlation_hypotheses ORDER BY id").fetchall()]
        first = m.correlation_hardening.replay_preview(
            incident["incident_key"], 900, 1100, actor="test")
        second = m.correlation_hardening.replay_preview(
            incident["incident_key"], 900, 1100, actor="test")
        after = [dict(r) for r in m.db.conn.execute(
            "SELECT * FROM correlation_hypotheses ORDER BY id").fetchall()]
        assert first["mode"] == "REPLAY_PREVIEW"
        assert first["result_fingerprint"] == second["result_fingerprint"]
        assert second["run"]["replay_of_id"] is not None
        assert before == after
        with pytest.raises(ValueError, match="replay range exceeds"):
            m.correlation_hardening.replay_preview(
                incident["incident_key"], 1, 1 + MAX_REPLAY_RANGE_SECONDS + 1)
    finally:
        m.close()


def test_mc10_restart_marks_abandoned_running_correlation_interrupted(tmp_path):
    home = tmp_path / "home"
    m = Manager(str(home))
    incident = m.incidents.create("Restart", created_by="test")
    now = time.time() - 60
    m.db.conn.execute(
        "INSERT INTO correlation_runs(incident_id,run_key,mode,rule_version,input_fingerprint,state,queued_ts,started_ts) "
        "VALUES(?,?,?,?,?,'RUNNING',?,?)",
        (incident["id"], "corr-abandoned", "CORRELATE", "mc7-r55-v1", "a" * 64, now, now),
    )
    m.db.conn.commit()
    m.close()
    m2 = Manager(str(home))
    try:
        row = m2.correlation_hardening.run("corr-abandoned")
        assert row["state"] == "INTERRUPTED"
        assert row["error"] == "ProcessRestart"
        assert row["finished_ts"] > 0
    finally:
        m2.close()


def test_mc10_runtime_retention_prunes_only_finished_old_run_metadata(tmp_path):
    m = _manager(tmp_path)
    try:
        incident = m.incidents.create("Retention", created_by="test")
        now = 10_000_000.0
        old = now - 40 * 86400
        recent = now - 10 * 86400
        for key, state, finished in (("old", "COMPLETED", old), ("running", "RUNNING", 0), ("recent", "COMPLETED", recent)):
            m.db.conn.execute(
                "INSERT INTO correlation_runs(incident_id,run_key,mode,rule_version,input_fingerprint,state,queued_ts,started_ts,finished_ts) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (incident["id"], key, "CORRELATE", "mc7-r55-v1", key * 16, state, old, old, finished),
            )
        m.db.conn.commit()
        result = m.correlation_hardening.prune_runs(30, now=now, actor="test")
        assert result["deleted_runs"] == 1
        assert m.correlation_hardening.run("old") is None
        assert m.correlation_hardening.run("running")["state"] == "RUNNING"
        assert m.correlation_hardening.run("recent")["state"] == "COMPLETED"
    finally:
        m.close()


def test_mc10_large_incident_evidence_fan_in_fails_boundedly(tmp_path):
    m = _manager(tmp_path)
    try:
        incident = m.incidents.create("Fan in", created_by="test")
        c = m.db.conn
        for i in range(510):
            source_ts = 1000.0 + i
            cur = c.execute(
                "INSERT INTO external_events(source_system,source_event_id,domain,event_type,severity,entity_type,entity_id,summary,"
                "source_ts,received_ts,source_clock_json,metadata_json,tenant_id,source_key,idempotency_key,schema_version,"
                "payload_sha256,payload_json,ingest_principal,ingest_result,connector_type) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("bulk", f"e-{i}", "APPLICATION", "bulk.signal", "MAJOR", "device", "app1", f"signal {i}",
                 source_ts, source_ts, "{}", "{}", "default", "bulk", f"i-{i}", "1", f"{i:064x}"[-64:],
                 "{}", "test", "ACCEPTED", "APM"),
            )
            c.execute(
                "INSERT INTO incident_evidence_links(incident_id,source_type,source_ref,linked_by,linked_ts,source_ts,received_ts,source_clock_json,note) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (incident["id"], "external_event", str(cur.lastrowid), "test", source_ts, source_ts, source_ts, "{}", ""),
            )
        c.commit()
        result = m.correlation.correlate(incident["incident_key"])
        assert result["facts_considered"] == 500
        assert result["facts_available"] == 510
        assert result["fact_evidence_truncated"] is True
        assert result["run"]["state"] == "COMPLETED"
    finally:
        m.close()


def test_mc10_self_monitoring_and_qualification_truth_are_bounded(tmp_path):
    m = _manager(tmp_path)
    try:
        incident = _seed_change_sensor(m, change_ts=time.time() - 10, sensor_ts=time.time() - 5)
        m.correlation.correlate(incident["incident_key"])
        health = m.correlation_hardening.health(window_seconds=900)
        assert health["correlation"]["runs"] >= 1
        assert health["correlation"]["latency_ms"]["p95"] >= 0
        assert health["rates"]["sensor_transitions"] >= 1
        assert health["rates"]["incidents_created"] >= 1
        assert health["correlation"]["execution_model"] == "synchronous-bounded"
        report = m.correlation_hardening.qualification_report()
        assert report["status"] == "IMPLEMENTED_TESTING_DEFERRED"
        assert report["local_ready"] is True
        assert report["release_eligible"] is False
        assert all(x["status"] == "NOT_RUN" for x in report["deferred_live_gates"])
        assert any(x["name"] == "live-postgresql-concurrency" for x in report["deferred_live_gates"])
    finally:
        m.close()



def test_mc10_same_incident_concurrent_runs_are_serialized(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        incident = _seed_change_sensor(m)
        original = m.correlation._evaluate
        state = {"active": 0, "max_active": 0}
        state_lock = threading.Lock()

        def slow(*args, **kwargs):
            with state_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            try:
                time.sleep(0.08)
                return original(*args, **kwargs)
            finally:
                with state_lock:
                    state["active"] -= 1

        monkeypatch.setattr(m.correlation, "_evaluate", slow)
        results = []
        errors = []

        def run():
            try:
                results.append(m.correlation.correlate(incident["incident_key"], actor="thread"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert errors == []
        assert len(results) == 2
        assert state["max_active"] == 1
        runs = m.correlation_hardening.runs(incident["incident_key"])
        assert len(runs) == 2
        assert sum(1 for r in runs if r.get("replay_of_id") is not None) == 1
    finally:
        m.close()

def _start_api(manager):
    Console.manager = manager
    Console.tls_enabled = False
    Console.netflow = None
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _api(server, method, path, token, data=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + token}
    body = ""
    if data is not None:
        body = urllib.parse.urlencode(data)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read()
    status = res.status
    conn.close()
    return status, json.loads(raw or b"{}")


def test_mc10_api_health_runs_replay_and_retention_scopes(tmp_path):
    m = _manager(tmp_path)
    server = None
    try:
        incident = _seed_change_sensor(m)
        m.correlation.correlate(incident["incident_key"])
        tokens = ApiTokens(m.db.conn)
        _, incident_reader = tokens.create("mc10-incident-reader", ["incident:read"], role="viewer")
        _, analytics_reader = tokens.create("mc10-analytics-reader", ["analytics:read"], role="viewer")
        _, writer = tokens.create("mc10-writer", ["incident:read", "incident:write", "analytics:read", "analytics:write"], role="operator")
        server, thread = _start_api(m)

        status, _ = _api(server, "GET", "/api/v1/operations/correlation/health", incident_reader)
        assert status == 403
        status, health = _api(server, "GET", "/api/v1/operations/correlation/health?window_seconds=900", analytics_reader)
        assert status == 200 and health["bounds"]["max_facts_per_run"] == 500
        status, report = _api(server, "GET", "/api/v1/operations/qualification/correlation", analytics_reader)
        assert status == 200 and report["release_eligible"] is False
        status, runs = _api(server, "GET", f"/api/v1/incidents/{incident['incident_key']}/correlation-runs", incident_reader)
        assert status == 200 and runs
        status, _ = _api(server, "POST", f"/api/v1/incidents/{incident['incident_key']}/correlation-replay", incident_reader, {"start_ts": 900, "end_ts": 1100})
        assert status == 403
        status, replay = _api(server, "POST", f"/api/v1/incidents/{incident['incident_key']}/correlation-replay", writer, {"start_ts": 900, "end_ts": 1100})
        assert status == 200 and replay["mode"] == "REPLAY_PREVIEW"
        status, _ = _api(server, "POST", "/api/v1/operations/correlation/retention", analytics_reader, {"retention_days": 30})
        assert status == 403
        status, retention = _api(server, "POST", "/api/v1/operations/correlation/retention", writer, {"retention_days": 30})
        assert status == 200 and retention["retention_days"] == 30
    finally:
        if server:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        m.close()


def test_mc10_dashboard_surfaces_read_only_correlation_health(tmp_path):
    m = _manager(tmp_path)
    server = None
    try:
        web._SESSIONS.clear()
        token = "mc10-session"
        web._SESSIONS[token] = {"username": "viewer", "role": "viewer", "csrf": "csrf", "created": time.time()}
        Console.manager = m; Console.tls_enabled = False; Console.netflow = None
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        conn.request("GET", "/dashboard", headers={"Cookie": f"ncsid={token}"})
        res = conn.getresponse(); text = res.read().decode(); conn.close()
        assert res.status == 200
        assert "Correlation production health" in text
        assert "Hard bounds:" in text
        assert "deferred live PostgreSQL" in text
        assert "correlation-replay" not in text and "correlation/retention" not in text
    finally:
        if server:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); m.close()
