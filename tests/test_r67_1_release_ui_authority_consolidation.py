from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

from netconfig.manager import Manager
from netconfig.workflow import Workflow
import netconfig.web as web
from netconfig.web import Console, _Server

ROOT = Path(__file__).resolve().parents[1]


def _start_web(manager, role="admin"):
    web._SESSIONS.clear()
    sid = "r671-session"
    csrf = "r671-csrf"
    web._SESSIONS[sid] = {
        "username": "tester", "role": role, "csrf": csrf,
        "created": time.time(),
    }
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, sid, csrf


def _request(server, sid, method, path, data=None):
    body = urllib.parse.urlencode(data or {}, doseq=True)
    headers = {"Cookie": f"ncsid={sid}"}
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Content-Length"] = str(len(body.encode()))
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request(method, path, body=body if method == "POST" else None, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8", "replace")
    result = response.status, raw, dict(response.getheaders())
    conn.close()
    return result


def test_p0_legacy_exec_surfaces_are_read_only_at_service_boundary(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    try:
        with pytest.raises(ValueError, match="read-only"):
            manager.run("missing", "configure terminal")
        with pytest.raises(ValueError, match="read-only"):
            manager.run("missing", "reload")
        assert manager.run

        workflow = Workflow(manager.db, manager)
        with pytest.raises(ValueError, match="read-only"):
            workflow.run_adhoc(devices=[], mode="config", body="hostname bad", run_by="admin")
        with pytest.raises(ValueError, match="read-only"):
            workflow.run_adhoc(devices=[], mode="command", body="show version", run_by="admin", save=True)

        calls = []
        monkeypatch.setattr(manager, "bulk", lambda devices, **kwargs: calls.append(kwargs) or [])
        job = workflow.run_adhoc(
            devices=[{"name": "sw1"}], mode="command", body="show version", run_by="admin")
        assert job["summary"] == "0 ok, 0 failed"
        assert calls == [{"mode": "command", "body": "show version", "save": False, "extra_vars": None}]
    finally:
        manager.close()


def test_p0_web_adhoc_forged_config_is_rejected_before_execution(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    monkeypatch.setattr(manager, "vault_ready", lambda: True)
    class NeverExecute:
        def run_adhoc(self, **kwargs):
            raise AssertionError("forged config reached execution")
        def list(self):
            return []
    manager._wf = NeverExecute()
    manager._scripts = type("Scripts", (), {"all": lambda self: []})()
    server, thread, sid, csrf = _start_web(manager, "admin")
    try:
        status, text, _ = _request(server, sid, "GET", "/automation")
        assert status == 200
        assert "Run now (read-only)" in text
        assert "config (push)" not in text
        status, text, _ = _request(server, sid, "POST", "/run-adhoc", {
            "csrf": csrf, "target_kind": "all", "target_value": "", "mode": "config",
            "body": "hostname bypass", "save": "1",
        })
        assert status == 200
        assert "Ad-hoc execution is read-only" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_p1_reports_are_in_canonical_alert_console_and_legacy_route_redirects(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    manager.alert_lifecycle.add_report_schedule("daily", "tester", interval_seconds=86400, lookback_hours=24)
    server, thread, sid, _ = _start_web(manager, "operator")
    try:
        status, text, _ = _request(server, sid, "GET", "/alerts?view=reports")
        assert status == 200
        assert "Operational report schedules" in text and "daily" in text
        assert 'action="/report-schedule-add"' in text
        status, _, headers = _request(server, sid, "GET", "/op-alerts")
        assert status == 303
        assert headers.get("Location") == "/alerts?view=active"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_p1_integrations_console_manages_api_token_lifecycle_without_cli(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    server, thread, sid, csrf = _start_web(manager, "admin")
    try:
        status, text, _ = _request(server, sid, "GET", "/settings?section=integrations")
        assert status == 200 and "API bearer tokens" in text
        status, text, _ = _request(server, sid, "POST", "/api-token-create", {
            "csrf": csrf, "name": "ndr-ingest", "role": "operator", "scopes": "external:ingest",
        })
        assert status == 200
        assert "API token created" in text and "nct_" in text
        tokens = manager.db.conn.execute("SELECT id,name,disabled FROM api_tokens").fetchall()
        assert len(tokens) == 1 and tokens[0]["name"] == "ndr-ingest" and not tokens[0]["disabled"]
        token_id = int(tokens[0]["id"])
        status, text, _ = _request(server, sid, "POST", "/api-token-revoke", {
            "csrf": csrf, "id": str(token_id),
        })
        assert status == 200 and f"API token #{token_id} revoked" in text
        assert manager.db.conn.execute("SELECT disabled FROM api_tokens WHERE id=?", (token_id,)).fetchone()["disabled"] == 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_p1_supportability_snapshot_is_visible_but_bundle_admin_boundary_remains(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    server, thread, sid, csrf = _start_web(manager, "viewer")
    try:
        status, text, _ = _request(server, sid, "GET", "/diagnostics")
        assert status == 200
        assert "Runtime Supportability" in text and "r66-supportability-1" in text
        assert "Create support bundle" not in text
        status, _, _ = _request(server, sid, "POST", "/debug-create", {"csrf": csrf})
        assert status == 403
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear()
    server, thread, sid, _ = _start_web(manager, "admin")
    try:
        status, text, _ = _request(server, sid, "GET", "/diagnostics")
        assert status == 200 and "Create support bundle" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_p1_ha_console_exposes_fenced_replay_safe_recovery(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    now = 1000.0
    task = manager.db.enqueue_distributed_task("ops", "safe-work", json.dumps({"x": 1}), now, replay_safe=True)
    claimed = manager.db.claim_distributed_task("ops", "worker-a", now, lease_seconds=1, instance_id="node-a")
    assert claimed["id"] == task["id"]
    manager.db.recover_expired_distributed_tasks(now + 6)
    server, thread, sid, csrf = _start_web(manager, "admin")
    try:
        status, text, _ = _request(server, sid, "GET", "/operations?tab=ha")
        assert status == 200
        assert "Distributed work recovery" in text and "RECOVERY_REQUIRED" in text
        assert "Requeue safe task" in text
        status, _, headers = _request(server, sid, "POST", "/ops-ha-task-requeue", {
            "csrf": csrf, "task_id": str(task["id"]), "reason": "verified no side effect",
        })
        assert status == 303 and "tab=ha" in headers.get("Location", "")
        row = manager.db.conn.execute("SELECT state,claim_generation FROM distributed_tasks WHERE id=?", (task["id"],)).fetchone()
        assert row["state"] == "PENDING" and int(row["claim_generation"]) == int(claimed["claim_generation"])
        reclaimed = manager.db.claim_distributed_task("ops", "worker-b", time.time(), lease_seconds=5, instance_id="node-b")
        assert int(reclaimed["claim_generation"]) == int(claimed["claim_generation"]) + 1
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_current_docs_do_not_present_r60_or_session_expiry_as_current_truth():
    readme = (ROOT / "README.md").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()
    security = (ROOT / "SECURITY.md").read_text()
    assert readme.startswith("# NetConfig\n\n## Current baseline — R67.2")
    assert roadmap.startswith("# Roadmap\n\n## Current baseline — R67.2")
    current_security = security.split("## Historical", 1)[0].lower()
    assert "session idle/absolute expiry remains" not in current_security
    assert "session idle/absolute expiry is implemented" in current_security


def _load_r671_runner():
    import importlib.util
    import sys
    path = ROOT / "qualification/r67_1_runner.py"
    spec = importlib.util.spec_from_file_location("r67_1_runner_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_r671_release_identity_and_fixed_live_rc_matrix():
    spec = (ROOT / "packaging/netconfig.spec").read_text()
    assert "Release:        67.2%{?dist}" in spec
    mod = _load_r671_runner()
    live = [gate for gate in mod.GATES if gate.evidence_class == "LIVE_RC"]
    assert len(live) == 12
    assert len({gate.gate_id for gate in live}) == 12
    assert len({gate.hook_name for gate in live}) == 12
    source = (ROOT / "qualification/r67_1_runner.py").read_text()
    assert "NETCONFIG_R67_1_LIVE_RC" in source
    assert "selected_live_ids == required_live_ids" in source
    assert '"product_baseline": "2.0.0-67.1"' in source
    assert '"production_release_claim": False' in source


def test_r671_local_baseline_passes_but_never_claims_release(tmp_path):
    import subprocess
    import sys
    out = tmp_path / "r671"
    cp = subprocess.run([
        sys.executable, str(ROOT / "qualification/r67_1_runner.py"),
        "--output-dir", str(out), "--include-local", "--gate", "R67.1-BASE-001",
    ], cwd=ROOT, text=True, capture_output=True)
    assert cp.returncode == 1, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["product_baseline"] == "2.0.0-67.1"
    assert campaign["gates"][0]["status"] == "FAIL"
    assert campaign["release_candidate_qualified"] is False
    assert campaign["production_release_claim"] is False
    assert campaign["release_promotion_performed"] is False
