from __future__ import annotations

import http.client
import importlib.util
import io
import json
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

from netconfig.apitokens import ApiTokens
from netconfig.debug import DebugBundle
from netconfig.manager import Manager
from netconfig.observability import Metrics
from netconfig.web import Console, _Server


ROOT = Path(__file__).resolve().parents[1]


def _manager(tmp_path):
    return Manager(str(tmp_path / "home"))


def _api_request(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Authorization": "Bearer " + token})
    res = conn.getresponse()
    raw = res.read()
    headers = dict(res.getheaders())
    status = res.status
    conn.close()
    return status, json.loads(raw or b"{}"), headers


def test_r66_snapshot_is_read_only_aggregate_and_schema_stays_mc11(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        monkeypatch.setattr(m, "collect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("polling not allowed")))
        monkeypatch.setattr(m, "storage_status", lambda: (_ for _ in ()).throw(AssertionError("heartbeat write not allowed")))
        monkeypatch.setattr(m.ha, "readiness", lambda *a, **k: (_ for _ in ()).throw(AssertionError("identity-lock probe not allowed")))
        snap = m.supportability.snapshot(now=time.time())
        assert snap["schema"] == "r66-supportability-1"
        assert snap["truth"] == {
            "read_only": True,
            "device_polling_performed": False,
            "network_write_authority": False,
            "qualification_claim": False,
            "secrets_included": False,
        }
        assert m.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
        assert "node_id" not in json.dumps(snap)
    finally:
        m.close()


def test_r66_queue_lag_recovery_and_last_success_are_visible(tmp_path):
    m = _manager(tmp_path)
    try:
        now = time.time()
        m.db.enqueue_distributed_task("r66", "safe", {}, now - 30, available_ts=now - 20, replay_safe=True)
        m.db.conn.execute(
            "INSERT INTO telemetry_subscriptions(name,device,path,mode,encoding,sample_interval_ms,heartbeat_interval_ms,"
            "window_seconds,collection_interval_seconds,retention_days,next_run_ts,enabled,state,last_error,created_ts,updated_ts,last_run_ts) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("r66-telemetry", "sw1", "/x", "SAMPLE", "json_ietf", 1000, 0, 5, 60, 30,
             now - 12, 1, "ERROR", "bounded failure", now - 100, now - 10, now - 15),
        )
        m.db.conn.commit()
        snap = m.supportability.snapshot(now=now)
        tasks = snap["queues"]["distributed_tasks"]
        assert tasks["pending"] == 1
        assert tasks["oldest_pending_age_seconds"] >= 19
        assert snap["telemetry"]["due"] == 1
        assert snap["telemetry"]["error"] == 1
        assert snap["telemetry"]["max_schedule_lag_seconds"] >= 11
        assert snap["state"] == "DEGRADED"
    finally:
        m.close()


def test_r66_collector_drop_and_error_are_sanitized(tmp_path):
    class Collector:
        def status(self):
            return {"running": True, "queue_depth": 7, "total_packets": 10, "dropped": 3,
                    "last_error": "Authorization=secret-token password=hunter2"}
    m = _manager(tmp_path)
    try:
        m.settings["syslog_enabled"] = True
        m.runtime_collectors["syslog"] = Collector()
        snap = m.supportability.snapshot()
        row = snap["collectors"]["syslog"]
        assert row["queue_depth"] == 7 and row["dropped"] == 3
        assert "hunter2" not in row["last_error"]
        assert "secret-token" not in row["last_error"]
        assert "collector packet drops observed" in snap["issues"]
    finally:
        m.close()


def test_r66_support_bundle_contains_sanitized_supportability_and_no_db_path(tmp_path):
    m = _manager(tmp_path)
    try:
        m.settings["api_secret"] = "do-not-leak"
        bundle = DebugBundle(m).collect()
        with tarfile.open(bundle, "r:gz") as tar:
            names = tar.getnames()
            support_name = next(name for name in names if name.endswith("/system/supportability.json"))
            db_name = next(name for name in names if name.endswith("/database/metadata.json"))
            support = json.load(io.TextIOWrapper(tar.extractfile(support_name), encoding="utf-8"))
            dbmeta = json.load(io.TextIOWrapper(tar.extractfile(db_name), encoding="utf-8"))
        assert support["schema"] == "r66-supportability-1"
        assert "path" not in dbmeta
        assert "do-not-leak" not in json.dumps(support)
        assert "do-not-leak" not in json.dumps(dbmeta)
    finally:
        m.close()


def test_r66_api_requires_debug_read_and_returns_read_only_snapshot(tmp_path):
    m = _manager(tmp_path)
    server = None
    try:
        tokens = ApiTokens(m.db.conn)
        _, limited = tokens.create("limited", ["inventory:read"], role="viewer")
        _, reader = tokens.create("support-reader", ["debug:read"], role="viewer")
        Console.manager = m
        Console.tls_enabled = False
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        status, _, _ = _api_request(server, limited, "/api/v1/supportability")
        assert status == 403
        status, payload, headers = _api_request(server, reader, "/api/v1/supportability")
        assert status == 200
        assert payload["schema"] == "r66-supportability-1"
        assert payload["truth"]["network_write_authority"] is False
        assert len(headers.get("X-Request-ID", "")) == 16
    finally:
        if server:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        m.close()


def test_r66_metrics_publish_bounded_supportability_without_identifiers(tmp_path):
    m = _manager(tmp_path)
    try:
        metrics = Metrics()
        snap = m.supportability.publish_metrics(metrics)
        text = metrics.render()
        for name in (
            "netconfig_supportability_ready", "netconfig_storage_ready", "netconfig_disk_free_bytes",
            "netconfig_distributed_tasks_pending", "netconfig_telemetry_due",
            "netconfig_external_ingest_rejected_total", "netconfig_collector_dropped_total",
        ):
            assert name in text
        assert m.cluster_node_id not in text
        assert snap["truth"]["device_polling_performed"] is False
    finally:
        m.close()


def test_r66_release_identity_and_no_mc12_contract():
    spec = (ROOT / "packaging/netconfig.spec").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()
    assert "Release:        67.2%{?dist}" in spec
    assert "R66" in roadmap
    assert "mc11-topology-change-planning-1" in roadmap
    assert "do not create mc-12" in roadmap.lower()
    assert "Release:" in spec


def test_r66_runner_contract_is_fixed_hook_and_fail_closed(tmp_path):
    runner = ROOT / "qualification/r66_runner.py"
    if not runner.exists():
        return
    source = runner.read_text()
    assert "shell=True" not in source
    assert "NETCONFIG_R66_LIVE_SUPPORT" in source
    assert "production_supportability_claim" in source
    spec = importlib.util.spec_from_file_location("r66_runner_test", runner)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    live = [g for g in mod.GATES if g.evidence_class == "LIVE_SUPPORT"]
    assert len(live) == 10


def test_r66_runner_historical_baseline_detects_release67_drift(tmp_path):
    out = tmp_path / "evidence"
    cp = subprocess.run(
        [sys.executable, str(ROOT / "qualification/r66_runner.py"), "--output-dir", str(out),
         "--include-local", "--gate", "R66-BASE-001"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 1, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["product_baseline"] == "2.0.0-66"
    assert campaign["gates"][0]["status"] == "FAIL"
    assert campaign["production_supportability_claim"] is False
    assert campaign["all_required_live_support_gates_selected"] is False
    assert campaign["live_support_pass_count"] == 0
    assert campaign["release_promotion_performed"] is False


def test_r66_live_gate_without_support_lab_is_blocked_not_false_pass(tmp_path):
    out = tmp_path / "live"
    cp = subprocess.run(
        [sys.executable, str(ROOT / "qualification/r66_runner.py"), "--output-dir", str(out),
         "--live", "--gate", "R66-SUP-010"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["gates"][0]["status"] in {"BLOCKED_ENVIRONMENT", "NOT_RUN"}
    assert campaign["production_supportability_claim"] is False


def test_r66_runner_redaction_partial_live_claim_and_executable_contract():
    spec = importlib.util.spec_from_file_location("r66_runner_exec_test", ROOT / "qualification/r66_runner.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    redacted = mod.redact("Bearer abc token=xyz password:secret")
    assert "abc" not in redacted and "xyz" not in redacted and "secret" not in redacted
    assert "selected_live_ids == required_live_ids" in (ROOT / "qualification/r66_runner.py").read_text()
    for relative in ("qualification/r66_runner.py", "packaging/r66-qualify.sh"):
        assert (ROOT / relative).stat().st_mode & 0o777 == 0o755
