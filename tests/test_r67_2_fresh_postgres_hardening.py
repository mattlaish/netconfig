from __future__ import annotations

import http.client
import json
import sqlite3
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

from netconfig import ifhistory
from netconfig.config import DEFAULT_SETTINGS
from netconfig.db import Database
from netconfig.manager import Manager
from netconfig.postgres_core import postgres_schema_statements, preflight_core_postgres
import netconfig.web as web
from netconfig.web import Console, _Server

ROOT = Path(__file__).resolve().parents[1]


def _start_web(manager, role="admin"):
    web._SESSIONS.clear()
    sid = "r672-session"
    csrf = "r672-csrf"
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


def _request(server, method, path, data=None, sid=None):
    body = urllib.parse.urlencode(data or {}, doseq=True)
    headers = {}
    if sid:
        headers["Cookie"] = f"ncsid={sid}"
    if method == "POST":
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        headers["Content-Length"] = str(len(body.encode()))
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request(method, path, body=body if method == "POST" else None, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8", "replace")
    out = response.status, raw, dict(response.getheaders())
    conn.close()
    return out


def test_fresh_login_real_http_post_succeeds(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    manager.users.create("admin", "correct horse battery staple", role="admin")
    web._SESSIONS.clear()
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, body, _ = _request(server, "GET", "/login")
        assert status == 200 and "Sign in" in body
        status, _, headers = _request(server, "POST", "/login", {
            "username": "admin", "password": "correct horse battery staple",
        })
        assert status == 303
        assert headers.get("Location") == "/"
        assert "ncsid=" in headers.get("Set-Cookie", "")
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_sqlite_upgrade_adds_columns_before_dependent_indexes(tmp_path):
    path = tmp_path / "legacy.db"
    db = Database(str(path))
    db.close()
    con = sqlite3.connect(path)
    try:
        con.execute("DROP INDEX IF EXISTS idx_l3_route_collection")
        con.execute("ALTER TABLE l3_route_observations RENAME TO l3_route_observations_new")
        con.execute("""
            CREATE TABLE l3_route_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
                device TEXT NOT NULL, vrf TEXT NOT NULL DEFAULT 'default', destination_prefix TEXT NOT NULL,
                protocol TEXT NOT NULL DEFAULT '', next_hop TEXT NOT NULL DEFAULT '',
                outgoing_interface TEXT NOT NULL DEFAULT '', next_device TEXT NOT NULL DEFAULT '',
                metric INTEGER NOT NULL DEFAULT 0, terminal INTEGER NOT NULL DEFAULT 0,
                evidence_ref TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT '', observed_ts REAL NOT NULL
            )
        """)
        con.execute("DROP TABLE l3_route_observations_new")
        con.commit()
    finally:
        con.close()

    upgraded = Database(str(path))
    try:
        cols = {r["name"] for r in upgraded.conn.execute("PRAGMA table_info(l3_route_observations)")}
        assert {"received_ts", "max_age_seconds", "source_kind", "collection_id"} <= cols
        indexes = {r["name"] for r in upgraded.conn.execute("PRAGMA index_list(l3_route_observations)")}
        assert "idx_l3_route_collection" in indexes
    finally:
        upgraded.close()


def test_postgres_schema_defers_indexes_until_after_migrations():
    base = "\n".join(postgres_schema_statements(indexes=False))
    indexes = "\n".join(postgres_schema_statements(indexes=True))
    assert "CREATE TABLE IF NOT EXISTS l3_route_observations" in base
    assert "idx_l3_route_collection" not in base
    assert "CREATE INDEX IF NOT EXISTS idx_l3_route_collection" in indexes


def test_core_postgres_preflight_requires_pre_vault_credential():
    settings = dict(DEFAULT_SETTINGS)
    settings.update(pg_host="db.example", pg_dbname="netconfig_core", pg_user="netconfig")
    out = preflight_core_postgres(settings, password=None)
    assert out["ok"] is False
    assert out["stage"] == "credential"


def test_history_postgres_uses_dedicated_keys_and_preserves_legacy_fallback():
    legacy = dict(DEFAULT_SETTINGS)
    legacy.update(pg_host="legacy-db", pg_port=5432, pg_dbname="legacy", pg_user="old", pg_sslmode="require")
    p = ifhistory._params_from_settings(legacy, password="x")
    assert p["host"] == "legacy-db" and p["dbname"] == "legacy"

    split = dict(legacy)
    split.update(if_history_pg_host="history-db", if_history_pg_port=5433,
                 if_history_pg_dbname="history", if_history_pg_user="hist",
                 if_history_pg_sslmode="verify-full")
    p = ifhistory._params_from_settings(split, password="x")
    assert p["host"] == "history-db" and p["port"] == 5433
    assert p["dbname"] == "history" and p["user"] == "hist"
    assert p["sslmode"] == "verify-full"


def test_database_console_separates_core_and_history(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    server, thread, sid, _ = _start_web(manager)
    try:
        status, body, _ = _request(server, "GET", "/settings?section=db", sid=sid)
        assert status == 200
        assert "Core Database" in body
        assert "Interface History Store" in body
        assert 'formaction="/core-db-test"' in body
        assert 'formaction="/history-db-test"' in body
        assert "Core PostgreSQL host" in body
        assert "History PostgreSQL host" in body
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_failed_core_preflight_does_not_persist_backend_switch(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    server, thread, sid, csrf = _start_web(manager)
    monkeypatch.setattr("netconfig.credentials.postgres_core_password", lambda: ("secret", "test"))
    monkeypatch.setattr("netconfig.postgres_core.preflight_core_postgres",
                        lambda settings, password=None, driver=None: {"ok": False, "stage": "connection", "error": "offline"})
    try:
        status, body, _ = _request(server, "POST", "/settings-save", {
            "csrf": csrf, "section": "db", "db_scope": "core",
            "core_db_backend": "postgres", "core_db_application_name": "netconfig",
            "pg_host": "db", "pg_port": "5432", "pg_dbname": "netconfig_core",
            "pg_user": "netconfig", "pg_sslmode": "require",
            "cluster_node_id": "", "cluster_failure_domain": "",
            "cluster_stale_seconds": "90", "distributed_task_lease_seconds": "60",
        }, sid=sid)
        assert status == 200
        assert "NOT saved" in body
        assert manager.settings["core_db_backend"] == "sqlite"
        persisted = json.loads(Path(manager.paths.settings_file).read_text()) if Path(manager.paths.settings_file).exists() else {}
        assert persisted.get("core_db_backend", "sqlite") == "sqlite"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_successful_core_preflight_persists_switch_but_runtime_stays_current_until_restart(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    server, thread, sid, csrf = _start_web(manager)
    monkeypatch.setattr("netconfig.credentials.postgres_core_password", lambda: ("secret", "test"))
    monkeypatch.setattr("netconfig.postgres_core.preflight_core_postgres",
                        lambda settings, password=None, driver=None: {"ok": True, "stage": "ready", "schema_revision": "mc11-topology-change-planning-1"})
    try:
        status, body, _ = _request(server, "POST", "/settings-save", {
            "csrf": csrf, "section": "db", "db_scope": "core",
            "core_db_backend": "postgres", "core_db_application_name": "netconfig",
            "pg_host": "db", "pg_port": "5432", "pg_dbname": "netconfig_core",
            "pg_user": "netconfig", "pg_sslmode": "require",
            "cluster_node_id": "", "cluster_failure_domain": "",
            "cluster_stale_seconds": "90", "distributed_task_lease_seconds": "60",
        }, sid=sid)
        assert status == 200
        assert "preflight/bootstrap passed" in body
        persisted = json.loads(Path(manager.paths.settings_file).read_text())
        assert persisted["core_db_backend"] == "postgres"
        assert manager.db.dialect == "sqlite"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()


def test_fresh_postgres_bootstrap_is_packaged_and_resume_is_fail_closed():
    script = (ROOT / "packaging/bootstrap-postgres-core.sh").read_text()
    assert "--resume" in script
    assert "existing SQLite core" in script
    assert "psycopg 3 is required" in script
    assert "LoadCredential=postgres-core-password" in script
    assert "netconfig-backup.service" in script and "netconfig-web.service" in script
    assert "storage status" in script
