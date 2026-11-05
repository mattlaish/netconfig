"""History retention must not monopolize the connection used by sign-in."""
import http.client
import sqlite3
import threading
import time

import pytest

import netconfig.db as db_module
import netconfig.sensor as sensor_module
from netconfig.db import Database, delete_sensor_history_batch
from netconfig.sensor import SensorEngine


def _seed(conn, table, times):
    for stamp in times:
        conn.execute(f"INSERT INTO {table}(observed_at) VALUES(?)", (stamp,))
    conn.commit()


@pytest.mark.parametrize("table", ["sensor_observations", "sensor_transitions"])
def test_upgrade_adds_index_used_by_global_retention_query(tmp_path, table):
    path = str(tmp_path / "inventory.db")
    db = Database(path)
    _seed(db.conn, table, [1.0, 2.0])
    db.conn.execute(f"DROP INDEX idx_{table}_time")
    db.conn.commit()
    db.close()
    upgraded = Database(path)
    try:
        plan = upgraded.conn.execute(
            f"EXPLAIN QUERY PLAN SELECT id FROM {table} "
            "WHERE observed_at<? ORDER BY observed_at,id LIMIT ?", (10.0, 500)).fetchall()
        assert any(f"idx_{table}_time" in row[3] and "SEARCH" in row[3] for row in plan)
        assert not any("SCAN " in row[3] or "TEMP B-TREE" in row[3] for row in plan)
        assert upgraded.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 2
    finally:
        upgraded.close()


@pytest.mark.parametrize("on_disk", [False, True])
def test_backlog_is_bounded_retried_and_preserves_retention_boundaries(tmp_path, monkeypatch, on_disk):
    db = Database(str(tmp_path / "inventory.db") if on_disk else ":memory:")
    try:
        engine = SensorEngine(db.conn)
        recorder = engine.history
        now = time.time()
        clock = [100.0]
        monkeypatch.setattr(sensor_module.time, "monotonic", lambda: clock[0])
        monkeypatch.setattr(sensor_module, "_SENSOR_HISTORY_BATCH_ROWS", 2)
        for table, retention in [("sensor_observations", sensor_module._SENSOR_OBSERVATION_RETENTION_SECONDS),
                                 ("sensor_transitions", sensor_module._SENSOR_TRANSITION_RETENTION_SECONDS)]:
            cutoff = now - retention
            _seed(db.conn, table, [cutoff - 4, cutoff - 3, cutoff - 2, cutoff, now])
        recorder._prune_history(now)
        for table in ("sensor_observations", "sensor_transitions"):
            assert db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 3
        recorder._prune_history(now)  # backlog is not drained in a tight per-sensor loop
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 3
        clock[0] += sensor_module._SENSOR_HISTORY_BACKLOG_RETRY_SECONDS
        recorder._prune_history(now)
        for table in ("sensor_observations", "sensor_transitions"):
            assert db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 2
        # A completed sweep waits an hour; late/backdated inserts wait for it too.
        _seed(db.conn, "sensor_observations", [1.0])
        clock[0] += sensor_module._SENSOR_HISTORY_PRUNE_INTERVAL_SECONDS - 1
        recorder._prune_history(now)
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 3
        clock[0] += 1
        recorder._prune_history(now)
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 2
    finally:
        db.close()


def test_cleanup_failure_keeps_new_observations_and_transitions_and_backs_off(monkeypatch, caplog):
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        engine.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK")
        engine.history._next_prune = 0
        calls = []
        def broken(*args):
            calls.append(args)
            raise sqlite3.OperationalError("sensitive connection detail")
        monkeypatch.setattr(db.conn, "prune_sensor_history_batch", broken)
        engine.upsert("interface.status", device="sw1", resource="1", value="DOWN", status="WARNING")
        engine.upsert("interface.status", device="sw1", resource="1", value="UP", status="OK")
        assert len(calls) == 1
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 3
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_transitions").fetchone()[0] == 2
        assert engine.list(device="sw1")[0]["status"] == "OK"
        assert "cleanup deferred (OperationalError)" in caplog.text
        assert "sensitive connection detail" not in caplog.text
    finally:
        db.close()


def test_memory_cleanup_never_commits_another_callers_transaction():
    db = Database(":memory:")
    try:
        engine = SensorEngine(db.conn)
        _seed(db.conn, "sensor_observations", [1.0])
        db.conn.execute("INSERT INTO users(username,pw_hash,pw_salt,iters) VALUES(?,?,?,?)",
                        ("pending", b"hash", b"salt", 1))
        engine.history._prune_history(time.time())
        db.conn.rollback()
        assert db.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 1
    finally:
        db.close()


def test_busy_external_writer_defers_cleanup_quickly_and_recovers(tmp_path):
    path = str(tmp_path / "inventory.db")
    db = Database(path)
    writer = sqlite3.connect(path)
    try:
        engine = SensorEngine(db.conn)
        _seed(db.conn, "sensor_observations", [1.0])
        writer.execute("BEGIN IMMEDIATE")
        finished = threading.Event()
        def prune():
            try:
                engine.history._prune_history(time.time())
            finally:
                finished.set()
        thread = threading.Thread(target=prune, daemon=True)
        thread.start()
        try:
            assert finished.wait(2), "cleanup queued behind the external writer"
            assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 1
        finally:
            writer.rollback()
            thread.join(timeout=5)
        # The failed batch is retryable without changing the normal handle's timeout.
        engine.history._next_prune = 0
        engine.history._prune_history(time.time())
        assert db.conn.execute("SELECT COUNT(*) FROM sensor_observations").fetchone()[0] == 0
        assert db.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        writer.close()
        db.close()


def test_health_and_login_respond_while_real_cleanup_sql_is_paused(tmp_path, monkeypatch):
    from netconfig.manager import Manager
    from netconfig.web import Console, _Server

    manager = Manager(str(tmp_path / "home"))
    manager.users.create("admin", "test-password-123", role="admin")
    _seed(manager.db.conn, "sensor_observations", [1.0])
    entered, release = threading.Event(), threading.Event()
    original_connect = db_module.sqlite3.connect
    def connect(*args, **kwargs):
        raw = original_connect(*args, **kwargs)
        def trace(sql):
            if sql.startswith("DELETE FROM sensor_observations"):
                entered.set()
                release.wait(10)
        raw.set_trace_callback(trace)
        return raw
    monkeypatch.setattr(db_module.sqlite3, "connect", connect)
    Console.manager, Console.tls_enabled = manager, False
    server = _Server(("127.0.0.1", 0), Console)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    cleaning = threading.Thread(target=manager.sensors.history._prune_history, args=(time.time(),), daemon=True)
    serving.start()
    cleaning.start()
    try:
        assert entered.wait(5), "the maintenance connection never started cleanup"
        # Cleanup is still inside SQLite.execute, reproducing the reported stack.
        for endpoint in ("healthz", "login"):
            client = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
            try:
                client.request("GET", "/" + endpoint)
                response = client.getresponse()
                body = response.read().decode()
                assert response.status == 200
                if endpoint == "login":
                    assert 'action="/login"' in body
            finally:
                client.close()
        assert cleaning.is_alive(), "cleanup must still be paused during the HTTP checks"
    finally:
        release.set()
        cleaning.join(timeout=5)
        server.shutdown()
        server.server_close()
        serving.join(timeout=5)
        manager.close()
    assert not cleaning.is_alive()


def test_batch_sql_is_portable_to_postgres_adapter():
    from netconfig.postgres_core import PostgresConn
    class Cursor:
        rowcount = 2
        description = None
    class Raw:
        def __init__(self):
            self.statements = []
        def execute(self, sql, args):
            self.statements.append((sql, args))
            return Cursor()
    raw = Raw()
    assert delete_sensor_history_batch(PostgresConn(raw), 10.0, 20.0, 500) == [2, 2]
    assert len(raw.statements) == 2
    for sql, args in raw.statements:
        assert "ORDER BY observed_at,id LIMIT %s" in sql
        assert "WHERE id IN (SELECT id" in sql
        assert args[-1] == 500
