import json
from contextlib import contextmanager

from netconfig.config import DEFAULT_SETTINGS
from netconfig.credentials import postgres_core_password
from netconfig.db import Database
from netconfig.postgres_core import (
    PostgresDatabase, postgres_params, postgres_schema_statements,
    translate_sql,
)
from netconfig.cli import build_parser


class FakeCursor:
    def __init__(self, rows=None, description=None, rowcount=0):
        self._rows = list(rows or [])
        self.description = description
        self.rowcount = rowcount
    def fetchall(self):
        return list(self._rows)
    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeRaw:
    def __init__(self):
        self.executed = []
        self.closed = False
        self.claim_row = None
    def execute(self, sql, params=()):
        self.executed.append((sql, tuple(params)))
        low = sql.lower()
        if "information_schema.columns" in low:
            return FakeCursor([{"column_name": params[1]}], [("column_name",)], 1)
        if "pg_try_advisory_lock" in low:
            return FakeCursor([{"locked": True}], [("locked",)], 1)
        if "pg_advisory_unlock" in low:
            return FakeCursor([{"unlocked": True}], [("unlocked",)], 1)
        if "for update skip locked" in low:
            row = self.claim_row
            return FakeCursor([row] if row else [], [("id",)], 1 if row else 0)
        if low.startswith("select * from distributed_tasks where id="):
            return FakeCursor([{"id": int(params[0]), "attempts": 2, "state": "CLAIMED"}], [("id",)], 1)
        if "select value,updated_ts from storage_meta" in low:
            return FakeCursor([{"value": "ph2-1", "updated_ts": 1.0}], [("value",)], 1)
        if low.startswith("select 1 as ok"):
            return FakeCursor([{"ok": 1}], [("ok",)], 1)
        if "returning id" in low:
            return FakeCursor([{"id": 41}], [("id",)], 1)
        return FakeCursor([], None, 1)
    @contextmanager
    def transaction(self):
        yield self
    def close(self):
        self.closed = True


class FakeDriver:
    def __init__(self):
        self.raw = FakeRaw()
        self.kwargs = None
    def connect(self, *args, **kwargs):
        self.kwargs = kwargs
        return self.raw


def test_postgres_translation_is_quote_safe_and_rewrites_sqlite_upserts():
    q = translate_sql("SELECT '?' AS literal, name FROM devices WHERE name=?")
    assert q == "SELECT '?' AS literal, name FROM devices WHERE name=%s"
    rep = translate_sql("INSERT OR REPLACE INTO groups (name,description,created) VALUES (?,?,?)")
    assert rep.startswith("INSERT INTO groups")
    assert "ON CONFLICT (name) DO UPDATE SET" in rep
    ign = translate_sql("INSERT OR IGNORE INTO group_members (group_name,device_name) VALUES (?,?)")
    assert ign.endswith("ON CONFLICT DO NOTHING")
    assert "%s" in ign


def test_postgres_schema_is_portable():
    script = "\n".join(postgres_schema_statements())
    assert "AUTOINCREMENT" not in script.upper()
    assert "BIGSERIAL PRIMARY KEY" in script.upper()
    assert "CREATE TABLE IF NOT EXISTS distributed_tasks" in script
    assert "CREATE TABLE IF NOT EXISTS storage_meta" in script


def test_postgres_database_bootstrap_and_readiness_with_fake_driver():
    drv = FakeDriver()
    db = PostgresDatabase(params={"host": "db", "dbname": "netconfig"}, driver=drv)
    try:
        status = db.readiness()
        assert status["backend"] == "postgres"
        assert status["distributed_capable"] is True
        assert status["schema_revision"] == "ph2-1"
        sql = "\n".join(q for q, _ in drv.raw.executed)
        assert "BIGSERIAL PRIMARY KEY" in sql.upper()
        assert "AUTOINCREMENT" not in sql.upper()
    finally:
        db.close()


def test_postgres_claim_uses_skip_locked_and_advisory_lock():
    drv = FakeDriver()
    db = PostgresDatabase(params={"host": "db", "dbname": "netconfig"}, driver=drv)
    try:
        drv.raw.claim_row = {"id": 7, "attempts": 1, "state": "PENDING"}
        row = db.claim_distributed_task("jobs", "worker-a", 100.0, 60)
        assert row["id"] == 7
        assert any("FOR UPDATE SKIP LOCKED" in q for q, _ in drv.raw.executed)
        assert db.try_advisory_lock("scheduler") is True
        assert db.try_advisory_lock("scheduler") is True
        assert db.advisory_unlock("scheduler") is True
    finally:
        db.close()


def test_sqlite_distributed_task_claim_is_single_claim(tmp_path):
    db = Database(str(tmp_path / "core.db"))
    try:
        task = db.enqueue_distributed_task("jobs", "collect", json.dumps({"device": "sw1"}), 100.0)
        claimed = db.claim_distributed_task("jobs", "worker-a", 100.0, 60)
        assert claimed["id"] == task["id"]
        assert claimed["attempts"] == 1
        assert db.claim_distributed_task("jobs", "worker-b", 101.0, 60) is None
        done = db.finish_distributed_task(task["id"], "worker-a", 102.0, result="ok")
        assert done["state"] == "DONE"
        assert db.storage_status()["backend"] == "sqlite"
        assert db.storage_status()["ok"] is True
    finally:
        db.close()


def test_core_postgres_password_prefers_secure_file(tmp_path):
    secret = tmp_path / "pgpw"
    secret.write_text("s3cret\n")
    secret.chmod(0o600)
    value, source = postgres_core_password({"NETCONFIG_DB_PASSWORD_FILE": str(secret),
                                            "NETCONFIG_DB_PASSWORD": "legacy"})
    assert value == "s3cret"
    assert source == "file"
    secret.chmod(0o622)
    try:
        postgres_core_password({"NETCONFIG_DB_PASSWORD_FILE": str(secret)})
        assert False, "writable credential must fail"
    except RuntimeError:
        pass


def test_postgres_params_do_not_require_or_persist_password():
    s = dict(DEFAULT_SETTINGS)
    s.update({"pg_host": "db.internal", "pg_dbname": "netconfig", "pg_user": "svc",
              "pg_sslmode": "verify-full", "core_db_application_name": "nc-a"})
    p = postgres_params(s)
    assert p["host"] == "db.internal"
    assert p["sslmode"] == "verify-full"
    assert "password" not in p
    p2 = postgres_params(s, password="secret")
    assert p2["password"] == "secret"


def test_storage_cli_surface_is_present():
    parser = build_parser()
    a = parser.parse_args(["storage", "status"])
    assert a.cmd == "storage" and a.action == "status"
    b = parser.parse_args(["storage", "claim", "--worker", "w1"])
    assert b.action == "claim" and b.worker == "w1"
    c = parser.parse_args(["storage", "migrate-sqlite", "--source", "/tmp/old.db"])
    assert c.action == "migrate-sqlite"


def test_sqlite_to_postgres_migration_copies_portable_rows(tmp_path):
    from netconfig.postgres_core import migrate_sqlite_to_postgres
    src = Database(str(tmp_path / "old.db"))
    try:
        src.conn.execute(
            "INSERT INTO devices(name,host,port,platform,created,updated) VALUES(?,?,?,?,?,?)",
            ("sw1", "192.0.2.10", 22, "cisco_ios", 1.0, 1.0))
        src.conn.commit()
    finally:
        src.close()
    drv = FakeDriver()
    target = PostgresDatabase(params={"host": "db", "dbname": "netconfig"}, driver=drv)
    try:
        out = migrate_sqlite_to_postgres(str(tmp_path / "old.db"), target)
        assert out["rows"] >= 1
        assert out["tables"]["devices"] == 1
        sql = "\n".join(q for q, _ in drv.raw.executed)
        assert "INSERT INTO devices" in sql
        assert "setval(pg_get_serial_sequence" in sql
    finally:
        target.close()
