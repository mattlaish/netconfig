from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.config import DEFAULT_SETTINGS
from netconfig.external_evidence import ExternalEvidenceService
from netconfig.manager import Manager
from netconfig.postgres_core import (
    PostgresConn, PostgresConnectionLost, PostgresDatabase, PostgresTransactionBusy,
    _retryable_transaction_failure,
)

ROOT = Path(__file__).resolve().parents[1]


class PgError(RuntimeError):
    def __init__(self, state, message="pg error"):
        super().__init__(message)
        self.sqlstate = state


class Cursor:
    def __init__(self, rows=None, description=None, rowcount=1):
        self.rows = list(rows or [])
        self.description = description
        self.rowcount = rowcount
    def fetchall(self):
        return list(self.rows)


class Raw:
    def __init__(self, fail_state="", fail_prefix=""):
        self.fail_state = fail_state
        self.fail_prefix = fail_prefix.upper()
        self.failed = False
        self.closed = False
        self.calls = []
    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if self.fail_state and not self.failed and sql.lstrip().upper().startswith(self.fail_prefix):
            self.failed = True
            self.closed = self.fail_state.startswith("08")
            raise PgError(self.fail_state)
        if sql.lstrip().upper().startswith(("SELECT", "SHOW", "VALUES")):
            return Cursor([{"ok": 1}], [("ok",)])
        return Cursor([], None)
    @contextmanager
    def transaction(self):
        yield self
    def close(self):
        self.closed = True


def _bare_db(raws, *, budget=2, retries=3, acquire=0.05):
    db = object.__new__(PostgresDatabase)
    db._driver = None
    db._conninfo = None
    db._connect_kwargs = {}
    db._max_concurrent_transactions = budget
    db._transaction_acquire_timeout = acquire
    db._transaction_retry_attempts = retries
    db._transaction_budget = threading.BoundedSemaphore(budget)
    queue = list(raws)
    db._connect_raw = lambda: queue.pop(0)
    return db


def test_r62_retryable_sqlstates_are_only_serialization_and_deadlock():
    assert _retryable_transaction_failure(PgError("40001"))
    assert _retryable_transaction_failure(PgError("40P01"))
    assert not _retryable_transaction_failure(PgError("23505"))
    assert not _retryable_transaction_failure(PgError("08006"))


def test_r62_read_reconnects_and_retries_once():
    broken = Raw("08006", "SELECT")
    fresh = Raw()
    conn = PostgresConn(broken, reconnect=lambda: fresh)
    row = conn.execute("SELECT 1 AS ok").fetchone()
    assert row["ok"] == 1
    assert len(broken.calls) == 1 and len(fresh.calls) == 1


def test_r62_write_connection_loss_is_never_replayed():
    broken = Raw("08006", "UPDATE")
    fresh = Raw()
    conn = PostgresConn(broken, reconnect=lambda: fresh)
    with pytest.raises(PostgresConnectionLost, match="not replayed"):
        conn.execute("UPDATE storage_meta SET value=? WHERE key=?", ("x", "y"))
    assert len(broken.calls) == 1
    assert fresh.calls == []


def test_r62_dedicated_transaction_retries_deadlock_then_succeeds():
    first, second = Raw(), Raw()
    db = _bare_db([first, second])
    calls = {"n": 0}
    def work(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PgError("40P01")
        return conn.execute("SELECT 1 AS ok").fetchone()["ok"]
    assert db.run_retryable_transaction(work) == 1
    assert calls["n"] == 2


def test_r62_dedicated_transaction_retries_serialization_then_succeeds():
    db = _bare_db([Raw(), Raw()])
    calls = {"n": 0}
    def work(conn):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PgError("40001")
        return "ok"
    assert db.run_retryable_transaction(work) == "ok"
    assert calls["n"] == 2


def test_r62_nonretryable_constraint_failure_is_not_replayed():
    db = _bare_db([Raw(), Raw()])
    calls = {"n": 0}
    def work(conn):
        calls["n"] += 1
        raise PgError("23505")
    with pytest.raises(PgError):
        db.run_retryable_transaction(work)
    assert calls["n"] == 1


def test_r62_connection_loss_in_dedicated_transaction_is_not_replayed():
    db = _bare_db([Raw()], retries=4)
    calls = {"n": 0}
    def work(conn):
        calls["n"] += 1
        raise PgError("08006")
    with pytest.raises(PostgresConnectionLost):
        db.run_retryable_transaction(work)
    assert calls["n"] == 1


def test_r62_transaction_budget_exhaustion_fails_boundedly():
    db = _bare_db([Raw()], budget=1, acquire=0.01)
    assert db._transaction_budget.acquire(timeout=0.01)
    try:
        with pytest.raises(PostgresTransactionBusy, match="budget exhausted"):
            db.run_retryable_transaction(lambda conn: None)
    finally:
        db._transaction_budget.release()


def test_r62_config_has_bounded_postgres_concurrency_defaults():
    assert DEFAULT_SETTINGS["pg_max_concurrent_transactions"] == 8
    assert DEFAULT_SETTINGS["pg_transaction_retry_attempts"] == 3
    assert DEFAULT_SETTINGS["pg_transaction_acquire_timeout_seconds"] == 5.0


def _event(event_id="evt-r62", idem="idem-r62"):
    return {"source_event_id": event_id, "idempotency_key": idem, "event_type": "r62.test",
            "source_ts": 1000.0, "severity": "INFO", "entity_type": "device",
            "entity_id": "r62", "summary": "R62 concurrency evidence", "payload": {"safe": True}}


def test_r62_external_evidence_same_identity_is_concurrency_idempotent(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    try:
        tokens = ApiTokens(manager.db.conn)
        token_id, raw = tokens.create("r62-ingest", ["external:ingest", "external:read"], created_by="test", role="operator")
        token = tokens.verify(raw)
        manager.external_evidence.register_source("r62-ndr", "NDR", "R62", ingest_token_id=token_id, actor="admin")
        def ingest(_):
            return manager.external_evidence.ingest("r62-ndr", _event(), token, request_bytes=128, received_ts=1100.0)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(ingest, range(8)))
        assert sum(not x["duplicate"] for x in results) == 1
        assert sum(x["duplicate"] for x in results) == 7
        assert manager.db.conn.execute("SELECT COUNT(*) AS n FROM external_events WHERE source_system=?", ("r62-ndr",)).fetchone()["n"] == 1
    finally:
        manager.close()


def test_r62_change_plan_same_identity_is_concurrency_idempotent(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    try:
        for name, host in (("r1", "192.0.2.1"), ("r2", "192.0.2.2")):
            manager.inv.upsert(name=name, host=host, port=22, platform="generic", device_type="network",
                               secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
                               enabled=True, tags=["r62"], notes="", snmp_version="", snmp_ref=None)
        def plan(_):
            return manager.change_planning.plan(source="r1", destination="r2", vrf="blue",
                                                destination_prefix="10.2.0.0/24", source_prefix="10.1.0.0/24",
                                                service="tcp/443", actor="r62")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(plan, range(8)))
        ids = {row["id"] for row in rows}
        assert len(ids) == 1
        assert manager.db.conn.execute("SELECT COUNT(*) AS n FROM change_plans").fetchone()["n"] == 1
    finally:
        manager.close()


def test_r62_runner_detects_historical_baseline_drift_under_r63(tmp_path):
    out = tmp_path / "evidence"
    cp = subprocess.run([sys.executable, str(ROOT / "qualification/r62_runner.py"), "--output-dir", str(out),
                         "--include-local", "--gate", "R62-BASE-001"], cwd=ROOT, text=True, capture_output=True)
    assert cp.returncode == 1, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["status_counts"]["FAIL"] == 1
    assert campaign["live_postgresql_pass_count"] == 0
    assert campaign["production_postgresql_claim"] is False
    assert campaign["release_promotion_performed"] is False


def test_r62_live_gate_without_postgres_target_is_not_false_pass(tmp_path):
    out = tmp_path / "evidence"
    cp = subprocess.run([sys.executable, str(ROOT / "qualification/r62_runner.py"), "--output-dir", str(out),
                         "--live", "--gate", "R62-PG-001"], cwd=ROOT, text=True, capture_output=True)
    assert cp.returncode == 0, cp.stdout + cp.stderr
    row = json.loads((out / "campaign.json").read_text())["gates"][0]
    assert row["status"] in {"BLOCKED_ENVIRONMENT", "NOT_RUN"}


def test_r62_runner_has_fixed_hooks_and_no_arbitrary_command_argument():
    source = (ROOT / "qualification/r62_runner.py").read_text()
    assert "--command" not in source and "shell=True" not in source and "bash -c" not in source
    assert "LIVE_POSTGRESQL" in source


def test_r62_does_not_create_mc12_or_expand_change_execution_authority():
    roadmap = (ROOT / "ROADMAP.md").read_text().lower()
    assert "do not create mc-12" in roadmap
    planning = (ROOT / "opt/netconfig/netconfig/change_planning.py").read_text().lower()
    assert "network_write\": false" in planning or '"network_write": false' in planning
