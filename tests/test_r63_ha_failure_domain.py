from __future__ import annotations

import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from netconfig.config import DEFAULT_SETTINGS
from netconfig.db import Database
from netconfig.ha import HAService
from netconfig.manager import Manager
from netconfig.postgres_core import PostgresConn, PostgresDatabase

ROOT = Path(__file__).resolve().parents[1]


class PgError(RuntimeError):
    def __init__(self, state="08006", message="postgres connection failed"):
        super().__init__(message)
        self.sqlstate = state


class Cursor:
    def __init__(self, rows=None, description=None, rowcount=1):
        self.rows = list(rows or [])
        self.description = description
        self.rowcount = rowcount
    def fetchall(self):
        return list(self.rows)
    def fetchone(self):
        return self.rows[0] if self.rows else None


class LockRaw:
    def __init__(self, *, fail_health=False, lock_result=True):
        self.fail_health = fail_health
        self.lock_result = lock_result
        self.closed = False
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        low = sql.lower().strip()
        if low.startswith("select 1 as ok"):
            if self.fail_health:
                self.fail_health = False
                self.closed = True
                raise PgError()
            return Cursor([{"ok": 1}], [("ok",)])
        if "pg_try_advisory_lock" in low:
            return Cursor([{"locked": self.lock_result}], [("locked",)])
        if "pg_advisory_unlock" in low:
            return Cursor([{"unlocked": True}], [("unlocked",)])
        return Cursor([], None)
    @contextmanager
    def transaction(self):
        yield self
    def close(self):
        self.closed = True


def test_r63_postgres_connection_generation_changes_after_reconnect():
    first = LockRaw(fail_health=True)
    second = LockRaw()
    conn = PostgresConn(first, reconnect=lambda: second)
    assert conn.session_generation == 0
    assert conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    assert conn.session_generation == 1
    assert first.closed is True


def test_r63_advisory_lock_is_reacquired_after_session_reconnect():
    first = LockRaw(lock_result=True)
    second = LockRaw(lock_result=False)
    conn = PostgresConn(first, reconnect=lambda: second)
    db = object.__new__(PostgresDatabase)
    db.conn = conn
    db._held_advisory = {}
    assert db.try_advisory_lock("netconfig:scheduler:test") is True
    key = db._lock_key("netconfig:scheduler:test")
    assert db._held_advisory[key] == 0
    first.fail_health = True
    assert db.try_advisory_lock("netconfig:scheduler:test") is False
    assert conn.session_generation == 1
    assert key not in db._held_advisory
    assert any("pg_try_advisory_lock" in sql.lower() for sql, _ in second.calls)


def test_r63_task_finish_requires_current_fencing_token(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    try:
        task = db.enqueue_distributed_task("jobs", "collect", "{}", 100.0)
        claim = db.claim_distributed_task("jobs", "worker-a", 101.0, 30, instance_id="inst-a")
        assert claim["claim_generation"] == 1
        assert claim["claim_token"]
        with pytest.raises(ValueError, match="claim_token"):
            db.finish_distributed_task(task["id"], "worker-a", 102.0)
        with pytest.raises(ValueError, match="fencing token"):
            db.finish_distributed_task(task["id"], "worker-a", 102.0,
                                       claim_token="wrong", claim_generation=1)
        done = db.finish_distributed_task(task["id"], "worker-a", 102.0,
                                          claim_token=claim["claim_token"],
                                          claim_generation=claim["claim_generation"], result="ok")
        assert done["state"] == "DONE"
    finally:
        db.close()


def test_r63_task_renewal_requires_current_unexpired_fence(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    try:
        db.enqueue_distributed_task("jobs", "collect", "{}", 100.0)
        claim = db.claim_distributed_task("jobs", "worker-a", 101.0, 10)
        renewed = db.renew_distributed_task(claim["id"], "worker-a", claim["claim_token"],
                                            claim["claim_generation"], 105.0, 20)
        assert renewed["lease_until"] == 125.0
        with pytest.raises(ValueError, match="stale"):
            db.renew_distributed_task(claim["id"], "worker-a", claim["claim_token"],
                                      claim["claim_generation"], 126.0, 20)
    finally:
        db.close()


def test_r63_expired_claim_never_auto_replays(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    try:
        task = db.enqueue_distributed_task("jobs", "device-write", "{}", 100.0)
        claim = db.claim_distributed_task("jobs", "worker-a", 100.0, 5)
        assert claim["lease_until"] == 105.0
        assert db.claim_distributed_task("jobs", "worker-b", 106.0, 5) is None
        rows = db.recover_expired_distributed_tasks(106.0)
        assert [r["id"] for r in rows] == [task["id"]]
        assert rows[0]["state"] == "RECOVERY_REQUIRED"
        assert "automatic replay disabled" in rows[0]["recovery_reason"]
        assert db.claim_distributed_task("jobs", "worker-b", 107.0, 5) is None
    finally:
        db.close()


def test_r63_only_declared_replay_safe_task_can_be_explicitly_requeued(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    try:
        unsafe = db.enqueue_distributed_task("jobs", "device-write", "{}", 100.0)
        db.claim_distributed_task("jobs", "w", 100.0, 5)
        db.recover_expired_distributed_tasks(106.0)
        with pytest.raises(ValueError, match="not declared replay-safe"):
            db.requeue_distributed_task(unsafe["id"], 107.0)

        safe = db.enqueue_distributed_task("safe", "read-only", "{}", 200.0, replay_safe=True)
        first = db.claim_distributed_task("safe", "w1", 200.0, 5)
        db.recover_expired_distributed_tasks(206.0)
        requeued = db.requeue_distributed_task(safe["id"], 207.0, reason="operator verified idempotent")
        assert requeued["state"] == "PENDING"
        second = db.claim_distributed_task("safe", "w2", 208.0, 5)
        assert second["claim_generation"] == first["claim_generation"] + 1
        with pytest.raises(ValueError, match="fencing token"):
            db.finish_distributed_task(safe["id"], "w1", 209.0,
                                       claim_token=first["claim_token"],
                                       claim_generation=first["claim_generation"])
        done = db.finish_distributed_task(safe["id"], "w2", 209.0,
                                          claim_token=second["claim_token"],
                                          claim_generation=second["claim_generation"])
        assert done["state"] == "DONE"
    finally:
        db.close()


def test_r63_cluster_membership_records_instance_and_failure_domain(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    try:
        db.register_cluster_node("node-a", "host-a", 123, 100.0,
                                 failure_domain="rack-a", instance_id="boot-a")
        row = db.get_cluster_node("node-a")
        assert row["failure_domain"] == "rack-a"
        assert row["instance_id"] == "boot-a"
        assert db.heartbeat_cluster_node("node-a", 110.0, "wrong") is False
        assert db.heartbeat_cluster_node("node-a", 111.0, "boot-a") is True
    finally:
        db.close()


class FakeHADB:
    dialect = "postgres"
    distributed_capable = True
    def __init__(self, nodes, lock=True):
        self.nodes = nodes
        self.lock = lock
        self.conn = None
    def list_cluster_nodes(self, since):
        return list(self.nodes)
    def get_cluster_node(self, node_id):
        return next((x for x in self.nodes if x["node_id"] == node_id), None)
    def try_advisory_lock(self, name):
        return self.lock
    def heartbeat_cluster_node(self, *args, **kwargs):
        return True


def _ha(nodes, *, lock=True):
    db = FakeHADB(nodes, lock=lock)
    manager = SimpleNamespace(db=db, cluster_node_id="node-a", cluster_instance_id="i-a",
                              cluster_identity_lock="netconfig:cluster-node:node-a")
    manager.storage_status = lambda: {"backend": "postgres", "distributed_capable": True, "reachable": True, "ok": True}
    return HAService(manager)


def test_r63_readiness_requires_two_distinct_failure_domains(monkeypatch):
    monkeypatch.setattr("netconfig.ha.time.time", lambda: 1000.0)
    same = _ha([
        {"node_id":"node-a","state":"ACTIVE","last_heartbeat_ts":999.0,"failure_domain":"rack-a"},
        {"node_id":"node-b","state":"ACTIVE","last_heartbeat_ts":999.0,"failure_domain":"rack-a"},
    ])
    result = same.readiness(90)
    assert result["ready_for_multi_node"] is False
    assert result["distinct_failure_domain_count"] == 1
    assert any("distinct declared failure domains" in x for x in result["issues"])

    separate = _ha([
        {"node_id":"node-a","state":"ACTIVE","last_heartbeat_ts":999.0,"failure_domain":"rack-a"},
        {"node_id":"node-b","state":"ACTIVE","last_heartbeat_ts":999.0,"failure_domain":"rack-b"},
    ])
    result = separate.readiness(90)
    assert result["ready_for_multi_node"] is True
    assert result["identity_fenced"] is True


def test_r63_identity_fence_failure_refuses_automation(monkeypatch):
    monkeypatch.setattr("netconfig.ha.time.time", lambda: 1000.0)
    ha = _ha([{"node_id":"node-a","state":"ACTIVE","last_heartbeat_ts":999.0,"failure_domain":"rack-a"}], lock=False)
    assert ha.accepts_automation_work() is False
    assert "identity fence" in " ".join(ha.readiness()["issues"])


def test_r63_scheduler_loops_revalidate_leadership_each_iteration():
    expectations = {
        "opt/netconfig/netconfig/web.py": 'manager.scheduler_leader("snmp-poller")',
        "opt/netconfig/netconfig/digest.py": 'manager.scheduler_leader("compliance-digest")',
        "opt/netconfig/netconfig/monitor.py": 'manager.scheduler_leader("monitor-poller")',
        "opt/netconfig/netconfig/operational_alerts.py": 'manager.scheduler_leader("operational-lifecycle")',
        "opt/netconfig/netconfig/telemetry.py": 'manager.scheduler_leader("telemetry-lifecycle")',
        "opt/netconfig/netconfig/diagnostic_maintenance.py": 'manager.scheduler_leader("diagnostic-maintenance")',
    }
    for relative, needle in expectations.items():
        assert needle in (ROOT / relative).read_text(), relative
    web=(ROOT/'opt/netconfig/netconfig/web.py').read_text()
    assert 'if interval > 0 and manager.scheduler_leader("snmp-poller"):' not in web
    assert 'if digest_iv > 0 and manager.scheduler_leader("compliance-digest"):' not in web


def test_r63_config_defaults_are_bounded_and_failure_domain_explicit():
    assert DEFAULT_SETTINGS["cluster_failure_domain"] == ""
    assert DEFAULT_SETTINGS["cluster_stale_seconds"] == 90
    assert DEFAULT_SETTINGS["distributed_task_lease_seconds"] == 60


def test_r63_recovery_drill_types_cover_failure_domains(tmp_path):
    m = Manager(str(tmp_path / "home"))
    try:
        for kind in ("NODE_FAILOVER", "WORKER_FAILOVER", "DATABASE_FAILOVER", "NETWORK_PARTITION",
                     "SPLIT_BRAIN_FENCE", "PARTIAL_JOB_RECOVERY", "REPLAY_RECOVERY"):
            row = m.ha.record_drill(kind=kind, actor="test", state="NOT_RUN", detail={"truth":"local-only"})
            assert row["kind"] == kind and row["state"] == "NOT_RUN"
    finally:
        m.close()


def test_r63_historical_runner_detects_release_64_baseline_drift(tmp_path):
    out=tmp_path/'evidence'
    cp=subprocess.run([sys.executable,str(ROOT/'qualification/r63_runner.py'),'--output-dir',str(out),
                       '--include-local','--gate','R63-BASE-001'],cwd=ROOT,text=True,capture_output=True)
    assert cp.returncode == 1
    campaign=json.loads((out/'campaign.json').read_text())
    assert campaign['status_counts']['FAIL'] == 1
    assert campaign['production_ha_claim'] is False
    assert campaign['release_promotion_performed'] is False

def test_r63_live_gate_without_lab_is_blocked_not_false_pass(tmp_path):
    out=tmp_path/'evidence'
    cp=subprocess.run([sys.executable,str(ROOT/'qualification/r63_runner.py'),'--output-dir',str(out),
                       '--live','--gate','R63-HA-010'],cwd=ROOT,text=True,capture_output=True)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    row=json.loads((out/'campaign.json').read_text())['gates'][0]
    assert row['status'] in {'BLOCKED_ENVIRONMENT','NOT_RUN'}


def test_r63_runner_has_fixed_hooks_and_no_arbitrary_shell_command():
    source=(ROOT/'qualification/r63_runner.py').read_text()
    assert '--command' not in source
    assert 'shell=True' not in source
    assert 'LIVE_HA' in source
    assert 'split-brain-fencing' in source


def test_r63_package_and_authority_truth():
    spec=(ROOT/'packaging/netconfig.spec').read_text()
    installer=(ROOT/'packaging/install-rpm.sh').read_text()
    road=(ROOT/'ROADMAP.md').read_text().lower()
    planning=(ROOT/'opt/netconfig/netconfig/change_planning.py').read_text().lower()
    assert 'Release:        67.2%{?dist}' in spec
    assert '${RELEASE%%.*} != "67"' in installer
    assert 'do not create mc-12' in road
    assert 'network_write": false' in planning or '"network_write": false' in planning
