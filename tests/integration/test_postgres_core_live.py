"""Q-1 service-backed PostgreSQL qualification tests.

These tests are intentionally skipped outside the explicit integration tier. They
exercise the actual PostgreSQL core adapter, not a fake psycopg driver.
"""
import concurrent.futures
import os
import shutil
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NETCONFIG_INTEGRATION") != "1",
    reason="set NETCONFIG_INTEGRATION=1 with PostgreSQL service running",
)


def _base_params(dbname="netconfig_test"):
    return {
        "host": os.environ.get("NETCONFIG_TEST_PG_HOST", "127.0.0.1"),
        "port": int(os.environ.get("NETCONFIG_TEST_PG_PORT", "5432")),
        "dbname": os.environ.get("NETCONFIG_TEST_PG_DB", dbname),
        "user": os.environ.get("NETCONFIG_TEST_PG_USER", "netconfig"),
        "password": os.environ.get("NETCONFIG_TEST_PG_PASSWORD", "netconfig"),
        "sslmode": os.environ.get("NETCONFIG_TEST_PG_SSLMODE", "disable"),
    }


@pytest.fixture
def isolated_schema():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql

    params = _base_params()
    schema = "q1_" + uuid.uuid4().hex[:16]
    admin = psycopg.connect(**params, autocommit=True)
    admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        yield params, schema
    finally:
        admin.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


def _db_in_schema(params, schema):
    from netconfig.postgres_core import PostgresDatabase

    p = dict(params)
    p["options"] = f"-c search_path={schema}"
    return PostgresDatabase(params=p)


def test_real_postgres_core_multinode_claim_leadership_and_heartbeat(isolated_schema):
    params, schema = isolated_schema
    db1 = _db_in_schema(params, schema)
    db2 = _db_in_schema(params, schema)
    try:
        now = time.time()
        task = db1.enqueue_distributed_task("q1", "one-claim", "{}", now)

        def claim(db, worker):
            return db.claim_distributed_task("q1", worker, now + 0.1, 60)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda pair: claim(*pair), [(db1, "node-a"), (db2, "node-b")]))
        claimed = [row for row in rows if row]
        assert len(claimed) == 1
        assert claimed[0]["id"] == task["id"]
        assert claimed[0]["claimed_by"] in {"node-a", "node-b"}

        assert db1.try_advisory_lock("netconfig:q1:leader") is True
        assert db2.try_advisory_lock("netconfig:q1:leader") is False
        assert db1.advisory_unlock("netconfig:q1:leader") is True
        assert db2.try_advisory_lock("netconfig:q1:leader") is True

        db1.register_cluster_node("node-a", "host-a", 1001, now)
        db2.register_cluster_node("node-b", "host-b", 1002, now)
        nodes = db1.list_cluster_nodes(now - 1)
        assert {row["node_id"] for row in nodes} >= {"node-a", "node-b"}
    finally:
        db1.close()
        db2.close()


def test_real_postgres_core_lock_released_when_session_dies(isolated_schema):
    params, schema = isolated_schema
    db1 = _db_in_schema(params, schema)
    db2 = _db_in_schema(params, schema)
    try:
        assert db1.try_advisory_lock("netconfig:q1:session-loss") is True
        assert db2.try_advisory_lock("netconfig:q1:session-loss") is False
        # Simulate process/connection death without calling advisory_unlock().
        db1.conn.raw.close()
        deadline = time.time() + 5
        acquired = False
        while time.time() < deadline:
            if db2.try_advisory_lock("netconfig:q1:session-loss"):
                acquired = True
                break
            time.sleep(0.1)
        assert acquired is True
    finally:
        try:
            db1.conn.close()
        except Exception:
            pass
        db2.close()


def test_real_sqlite_to_postgres_migration_repairs_serial_sequence(tmp_path, isolated_schema):
    from netconfig.db import Database
    from netconfig.postgres_core import migrate_sqlite_to_postgres

    params, schema = isolated_schema
    source_path = tmp_path / "source.db"
    source = Database(str(source_path))
    try:
        source.conn.execute(
            "INSERT INTO runs(id,device,ts,ok,changed,message) VALUES(?,?,?,?,?,?)",
            (9001, "sw-q1", 1.0, 1, 0, "migrated"),
        )
        source.conn.commit()
    finally:
        source.close()

    target = _db_in_schema(params, schema)
    try:
        result = migrate_sqlite_to_postgres(str(source_path), target)
        assert result["rows"] >= 1
        row = target.conn.execute("SELECT id,message FROM runs WHERE id=?", (9001,)).fetchone()
        assert row and row["message"] == "migrated"
        inserted = target.conn.execute(
            "INSERT INTO runs(device,ts,ok,changed,message) VALUES(?,?,?,?,?)",
            ("sw-q1", 2.0, 1, 0, "after-migration"),
        )
        assert inserted.lastrowid > 9001
    finally:
        target.close()


@pytest.mark.skipif(
    os.environ.get("NETCONFIG_POSTGRES_BACKUP_INTEGRATION") != "1",
    reason="set NETCONFIG_POSTGRES_BACKUP_INTEGRATION=1 with pg_dump/pg_restore available",
)
def test_real_postgres_backup_restore_drill(tmp_path):
    psycopg = pytest.importorskip("psycopg")
    if not shutil.which("pg_dump") or not shutil.which("pg_restore"):
        pytest.skip("pg_dump/pg_restore are required")

    from psycopg import sql
    from netconfig.postgres_core import PostgresDatabase
    from netconfig.postgres_backup import backup_core_database, restore_core_database

    base = _base_params()
    suffix = uuid.uuid4().hex[:12]
    source_db = f"q1_src_{suffix}"
    target_db = f"q1_dst_{suffix}"
    admin = psycopg.connect(**base, autocommit=True)
    try:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source_db)))
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
        source_params = dict(base)
        source_params["dbname"] = source_db
        db = PostgresDatabase(params=source_params)
        try:
            db.conn.execute(
                "INSERT INTO devices(name,host,port,platform,created,updated) VALUES(?,?,?,?,?,?)",
                ("q1-restore-marker", "192.0.2.44", 22, "generic", 1.0, 1.0),
            )
        finally:
            db.close()

        settings = {
            "core_db_backend": "postgres",
            "pg_host": base["host"], "pg_port": base["port"], "pg_dbname": source_db,
            "pg_user": base["user"], "pg_sslmode": base["sslmode"],
            "core_db_application_name": "netconfig-q1-integration",
        }
        dump_path = tmp_path / "core.dump"
        evidence = backup_core_database(settings, base["password"], str(dump_path))
        assert evidence["bytes"] > 0
        restored = restore_core_database(
            settings, base["password"], str(dump_path), target_dbname=target_db,
            confirm="RESTORE_DATABASE",
        )
        assert restored["verified"] is True

        target_params = dict(base)
        target_params["dbname"] = target_db
        check = psycopg.connect(**target_params, autocommit=True)
        try:
            row = check.execute(
                "SELECT host FROM devices WHERE name='q1-restore-marker'"
            ).fetchone()
            assert row and row[0] == "192.0.2.44"
            revision = check.execute(
                "SELECT value FROM storage_meta WHERE key='schema_revision'"
            ).fetchone()
            assert revision and revision[0] == "ph3-1"
        finally:
            check.close()
    finally:
        # Terminate any leaked sessions so cleanup itself is deterministic.
        for name in (source_db, target_db):
            try:
                admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=%s AND pid<>pg_backend_pid()",
                    (name,),
                )
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
            except Exception:
                pass
        admin.close()
