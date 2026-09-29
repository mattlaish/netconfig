"""R62 live PostgreSQL concurrency/recovery qualification tests.

These are never local substitutes: set NETCONFIG_R62_POSTGRES_INTEGRATION=1 and
provide a disposable PostgreSQL qualification database.
"""
import concurrent.futures
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NETCONFIG_R62_POSTGRES_INTEGRATION") != "1",
    reason="set NETCONFIG_R62_POSTGRES_INTEGRATION=1 with disposable PostgreSQL target",
)


def _params():
    return {
        "host": os.environ.get("NETCONFIG_TEST_PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("NETCONFIG_TEST_PG_PORT", "5432")),
        "dbname": os.environ.get("NETCONFIG_TEST_PG_DB", "netconfig_test"),
        "user": os.environ.get("NETCONFIG_TEST_PG_USER", "netconfig"),
        "password": os.environ.get("NETCONFIG_TEST_PG_PASSWORD", "netconfig"),
        "sslmode": os.environ.get("NETCONFIG_TEST_PG_SSLMODE", "disable"),
    }


@pytest.fixture
def schema():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    base = _params(); name = "r62_" + uuid.uuid4().hex[:16]
    admin = psycopg.connect(**base, autocommit=True)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        yield base, name, admin
    finally:
        admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(name)))
        admin.close()


def _db(base, schema):
    from netconfig.postgres_core import PostgresDatabase
    p = dict(base); p["options"] = f"-c search_path={schema}"
    return PostgresDatabase(params=p, max_concurrent_transactions=4, transaction_retry_attempts=3)


def test_r62_live_dedicated_transactions_are_bounded_and_atomic(schema):
    base, name, _ = schema; db = _db(base, name)
    try:
        db.conn.raw.execute("CREATE TABLE r62_counter(id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        db.conn.raw.execute("INSERT INTO r62_counter(id,value) VALUES(1,0)")
        def increment(_):
            def work(conn):
                row = conn.execute("SELECT value FROM r62_counter WHERE id=1 FOR UPDATE").fetchone()
                conn.execute("UPDATE r62_counter SET value=? WHERE id=1", (int(row["value"])+1,))
            db.run_retryable_transaction(work)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(increment, range(20)))
        assert db.conn.execute("SELECT value FROM r62_counter WHERE id=1").fetchone()["value"] == 20
    finally:
        db.close()


def test_r62_live_advisory_lock_excludes_other_control_plane_session(schema):
    base, name, _ = schema; db1 = _db(base, name); db2 = _db(base, name)
    try:
        assert db1.try_advisory_lock("r62:mc10:incident:1") is True
        assert db2.try_advisory_lock("r62:mc10:incident:1") is False
        assert db1.advisory_unlock("r62:mc10:incident:1") is True
        assert db2.try_advisory_lock("r62:mc10:incident:1") is True
    finally:
        db1.close(); db2.close()


def test_r62_live_connection_loss_reconnects_read_but_does_not_replay_write(schema):
    from netconfig.postgres_core import PostgresConnectionLost
    base, name, admin = schema; db = _db(base, name)
    try:
        pid = db.conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
        assert db.conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
        pid = db.conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
        with pytest.raises(PostgresConnectionLost):
            db.conn.execute("UPDATE storage_meta SET value=? WHERE key=?", ("unsafe-replay", "schema_revision"))
        assert db.conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    finally:
        db.close()
