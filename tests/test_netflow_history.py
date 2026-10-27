"""Flow-history contract tests. SQLite SQL bridge is offline evidence, NOT PostgreSQL qualification."""
import socket
from contextlib import nullcontext
import sqlite3
import struct
import time
import uuid

import pytest

from netconfig import netflow
from netconfig import netflow_history as nh
from netconfig.manager import Manager
from netconfig.web_traffic import history_notice
from netconfig.web_ui import render_netflow_section


class SqlBridge:
    """Exercise actual history SQL/transactions on a test-only SQLite file."""
    def __init__(self, path):
        self.conn = sqlite3.connect(path)

    def __enter__(self):
        return self

    def __exit__(self, typ, val, tb):
        if typ:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def execute(self, sql, args=()):
        return self.conn.execute(sql.replace("%s", "?"), args)

    def executemany(self, sql, args):
        return self.conn.executemany(sql.replace("%s", "?"), args)

    def cursor(self):
        return nullcontext(self)

    def commit(self):
        self.conn.commit()


@pytest.fixture
def store(tmp_path, monkeypatch):
    path = str(tmp_path / "flows.sqlite")
    monkeypatch.setattr(nh.PgFlowHistory, "_connect", lambda self: SqlBridge(path))
    backend = nh.PgFlowHistory()
    backend.ensure_schema()
    return backend


def flow(ts=None, exporter="192.0.2.1", **kw):
    return {"record_id": uuid.uuid4().hex, "ts": time.time() if ts is None else ts,
            "exporter": exporter, "src": "10.0.0.2", "dst": "8.8.8.8", "sport": 50000,
            "dport": 443, "proto": "TCP", "packets": 2, "bytes": 1500, **kw}


def test_restart_reads_committed_flows_and_ipv6(store):
    now = time.time()
    rows = [flow(now - 3600, src="2001:db8::1", dst="2606:4700::1111"), flow(now - 1)]
    store.write(rows)
    restarted = nh.PgFlowHistory()
    got, truncated = restarted.read(now - 86400, now)
    assert not truncated and len(got) == 2
    assert got[1]["src"] == "2001:db8::1" and sum(f["bytes"] for f in got) == 3000


def test_retention_boundary_and_idle_cleanup(store):
    now = time.time()
    store.write([flow(now - 86401), flow(now - 86400), flow(now - 2), flow(now + 5)])
    got, _ = store.read(now - 1000000, now)
    assert len(got) == 2
    worker = nh.FlowHistory(lambda: store)
    assert worker.flush_once(now)  # no new flows; maintenance still runs
    with store._connect() as c:
        count = c.execute(f"SELECT count(*) FROM {nh.TABLE}").fetchone()[0]
    assert count == 3  # excludes expired; preserves boundary and future timestamp
    assert worker.status()["last_maintenance_ts"] == now


def test_retry_after_ambiguous_commit_is_idempotent(store, monkeypatch):
    real_write = store.write
    calls = []

    def uncertain(rows):
        real_write(rows)
        calls.append(1)
        if len(calls) == 1:
            raise OSError("password=never-show-this")
    monkeypatch.setattr(store, "write", uncertain)
    worker = nh.FlowHistory(lambda: store)
    worker.submit([flow()])
    assert not worker.flush_once()
    assert worker.status()["pending"] == 1
    assert "never-show-this" not in str(worker.status())
    assert worker.flush_once()
    assert worker.status()["pending"] == 0 and worker.status()["written"] == 1
    got, _ = store.read(time.time() - 60, time.time())
    assert len(got) == 1


def test_inflight_and_committed_rows_merge_without_double_count(store, monkeypatch):
    worker = nh.FlowHistory(lambda: store)
    worker.submit([flow()])
    seen = []
    real_write = store.write

    def commit_then_query(rows):
        real_write(rows)
        seen.append(worker.read_window(time.time() - 60, time.time()))
    monkeypatch.setattr(store, "write", commit_then_query)
    assert worker.flush_once()
    assert len(seen[0]["flows"]) == 1
    assert len(worker.read_window(time.time() - 60, time.time())["flows"]) == 1


class _Unreachable:
    """A configured History database that is temporarily unreachable."""
    _schema_ready = False

    def ensure_schema(self):
        raise ConnectionError("refused")


def test_queue_capacity_expiry_and_recovery_are_visible(store):
    worker = nh.FlowHistory(lambda: _Unreachable(), capacity=2)
    worker.submit([flow(time.time() - 86401), flow(), flow()])
    assert worker.status()["dropped"] == 1
    assert not worker.flush_once()
    assert worker.status()["expired"] == 1 and worker.status()["pending"] == 1
    worker.provider = lambda: store
    assert worker.flush_once()
    assert not worker.status()["write_error"]
    assert "History is incomplete" in history_notice({"status": worker.status()})


def test_exporter_filter_is_bound_and_query_limit_is_explicit(store):
    now = time.time()
    hostile = "a'; DELETE FROM netconfig_flow_history;--"
    store.write([flow(now - 3), flow(now - 2), flow(now - 1, exporter=hostile)])
    got, _ = store.read(now - 60, now, exporter=hostile)
    assert len(got) == 1 and got[0]["exporter"] == hostile
    got, truncated = store.read(now - 60, now, limit=1)
    assert truncated and len(got) == 1
    html = history_notice({"source": "postgres", "truncated": True, "query_limit": 1})
    assert "Results are incomplete" in html and "Older records remain stored" in html


def test_history_backend_reuses_vault_password_without_interface_enable(tmp_path):
    m = Manager(str(tmp_path / "home"))
    try:
        m.settings.update(if_history_enabled=False, if_history_pg_host="localhost",
                          if_history_pg_dbname="flowtest", if_history_hours=1)
        m._pg_password = lambda: "first-secret"
        first = nh.backend_for(m)
        assert first.params["password"] == "first-secret"
        assert nh.backend_for(m) is first
        m._pg_password = lambda: "second-secret"
        assert nh.backend_for(m) is not first
        assert nh.backend_for(m).params["password"] == "second-secret"
    finally:
        m.close()


def test_legacy_history_connection_override(tmp_path):
    m = Manager(str(tmp_path / "home"))
    try:
        m.settings["if_history_dsn"] = "host=legacy dbname=flows"
        assert nh.backend_for(m).conninfo == "host=legacy dbname=flows"
    finally:
        m.close()


def test_global_analysis_reads_history_beyond_ring_and_after_restart(store, tmp_path):
    now = time.time()
    store.write([flow(now - 7200), flow(now - 5)])
    m = Manager(str(tmp_path / "home"))
    try:
        col = netflow.Collector(max_flows=1, history=nh.FlowHistory(lambda: store))
        data = m.operations_console.traffic(col, window_seconds=86400, now=now)
        assert data["storage"]["source"] == "postgres"
        assert data["analysis"]["totals"]["bytes"] == 3000
        assert data["analysis"]["totals"]["records"] == 2
        assert not data["analysis"]["ring_full_exporters"]
        assert data["exporters"][0]["exporter"] == "192.0.2.1"
        short = m.operations_console.traffic(col, window_seconds=3600, now=now)
        assert short["analysis"]["totals"]["records"] == 1
    finally:
        m.close()


def test_database_failure_falls_back_to_ring_with_visible_error(tmp_path):
    now = time.time()

    class Down:
        def read(self, *a, **kw):
            raise ConnectionError("refused")

        def exporters(self, *a, **kw):
            raise ConnectionError("refused")

    col = netflow.Collector(history=nh.FlowHistory(lambda: Down()))
    col._flows["192.0.2.1"].append(flow(now))
    col._counts["192.0.2.1"] = 1
    m = Manager(str(tmp_path / "home"))
    try:
        data = m.operations_console.traffic(col, now=now)
        assert data["storage"]["source"] == "memory"
        assert data["analysis"]["totals"]["records"] == 1
        assert "Database history unavailable" in history_notice(data["storage"])
    finally:
        m.close()


def test_device_view_uses_saved_history_with_empty_ring(store, tmp_path):
    store.write([flow(time.time() - 7200)])
    m = Manager(str(tmp_path / "home"))
    try:
        m.settings["netflow_enabled"] = True
        handler = type("Handler", (), {"manager": m})()
        col = netflow.Collector(history=nh.FlowHistory(lambda: store))
        html = render_netflow_section(handler, {"host": "192.0.2.1", "netflow": 1}, col)
        assert "PostgreSQL flow history" in html and "10.0.0.2" in html
        assert "No flows received yet" not in html
    finally:
        m.close()


def test_udp_receiver_queues_and_persists_without_database_io_on_receiver(store):
    worker = nh.FlowHistory(lambda: store, batch_size=1)
    col = netflow.Collector(bind="127.0.0.1", port=0, history=worker)
    packet = bytearray(72)
    struct.pack_into(">HH", packet, 0, 5, 1)
    struct.pack_into(">II", packet, 24, 0x0a000002, 0x08080808)
    struct.pack_into(">II", packet, 40, 2, 1500)
    struct.pack_into(">HH", packet, 56, 50000, 443)
    packet[62] = 6
    col.start()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(packet, ("127.0.0.1", col._sock.getsockname()[1]))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and worker.status()["written"] < 1:
            time.sleep(.02)
        assert worker.status()["written"] == 1
        saved = worker.read_window(time.time() - 60, time.time(), exporter="127.0.0.1")
        assert saved["flows"][0]["bytes"] == 1500
    finally:
        col.stop()
    assert not worker._thread.is_alive()


def test_maintenance_failure_does_not_requeue_successful_writes(store, monkeypatch):
    monkeypatch.setattr(store, "prune", lambda now: (_ for _ in ()).throw(OSError("secret")))
    worker = nh.FlowHistory(lambda: store)
    worker.submit([flow()])
    assert worker.flush_once()
    assert worker.status()["pending"] == 0
    assert "cleanup failed" in worker.status()["maintenance_error"]
    assert "secret" not in history_notice({"status": worker.status()})


def test_graceful_stop_drains_multiple_batches(store):
    worker = nh.FlowHistory(lambda: store, batch_size=1)
    worker.submit([flow(), flow(), flow()])
    worker.start()
    worker.stop()
    assert worker.status()["pending"] == 0 and worker.status()["written"] == 3


def test_invalid_counter_cannot_poison_the_batch(store):
    worker = nh.FlowHistory(lambda: store)
    worker.submit([flow(bytes=1 << 80), flow(ts=float("nan")), flow()])
    assert worker.status()["dropped"] == 2
    assert worker.flush_once() and worker.status()["written"] == 1


def test_unconfigured_history_is_quiet_and_buffers_nothing():
    # Default install: history switch on, but no History PostgreSQL database set.
    h = nh.FlowHistory(lambda: None, capacity=5, batch_size=2)
    h.submit([flow() for _ in range(3)])            # before the first check: buffered
    assert h.flush_once() is False
    st = h.status()
    assert st["configured"] is False and st["pending"] == 0 and not st["write_error"]
    h.submit([flow() for _ in range(50)])           # afterwards: not buffered, not "lost"
    st = h.status()
    assert st["pending"] == 0 and st["dropped"] == 0
    assert h.read_window(time.time() - 60, time.time()) is None and not h.status()["read_error"]
    assert h.exporter_choices(time.time() - 60, time.time()) == [] and not h.status().get("exporter_error")
    notice = history_notice({"source": "memory", "status": h.status()})
    assert "class=err" not in notice and "Database settings" in notice


def test_history_becomes_active_once_a_database_is_set(store):
    backend = {"value": None}
    h = nh.FlowHistory(lambda: backend["value"], capacity=10, batch_size=2)
    h.flush_once()
    assert h.status()["configured"] is False
    backend["value"] = store
    assert h.flush_once() is True and h.status()["configured"] is True
    h.submit([flow(), flow()])
    assert h.flush_once() is True and h.status()["written"] == 2
