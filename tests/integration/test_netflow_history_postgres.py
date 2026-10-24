"""Opt-in real PostgreSQL history gate; always uses a new isolated schema."""
import os
import time
import uuid

import pytest

from netconfig.netflow_history import PgFlowHistory


@pytest.mark.integration
def test_real_postgres_history_restart_retention_and_unsigned_counters():
    dsn = os.environ.get("NETCONFIG_TEST_FLOW_PG_DSN")
    if not dsn:
        pytest.skip("NETCONFIG_TEST_FLOW_PG_DSN required for isolated-schema PostgreSQL qualification")
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    schema = "flow_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            backend = PgFlowHistory(conninfo=make_conninfo(dsn, options=f"-c search_path={schema}"))
            now = time.time()
            row = {"record_id": uuid.uuid4().hex, "ts": now - 10, "exporter": "192.0.2.1",
                   "src": "2001:db8::1", "dst": "2606:4700::1111", "sport": 50000,
                   "dport": 443, "proto": "TCP", "packets": 2, "bytes": (1 << 64) - 1}
            backend.write([row, dict(row, record_id=uuid.uuid4().hex, ts=now - 86401)])
            backend.write([row])  # retry must not duplicate
            restarted = PgFlowHistory(conninfo=backend.conninfo)
            rows, truncated = restarted.read(now - 86400, now, exporter="192.0.2.1")
            assert not truncated and len(rows) == 1 and rows[0]["bytes"] == (1 << 64) - 1
            assert restarted.prune(now) == 1
            assert restarted.read(now - 86400, now, exporter="other")[0] == []
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
