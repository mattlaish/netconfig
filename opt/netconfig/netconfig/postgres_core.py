"""PH-2 PostgreSQL core storage backend and distributed coordination.

SQLite remains the zero-dependency development/default backend. PostgreSQL is an
explicit production opt-in. The adapter preserves the existing qmark SQL surface
used by NetConfig while translating it to psycopg safely, bootstraps the same
core schema, and provides PostgreSQL-only SKIP LOCKED worker claiming and
advisory-lock scheduler leadership.
"""
from __future__ import annotations

import hashlib
import re
import threading
from contextlib import contextmanager

from .db import Database, _MIGRATIONS, _Result, _SCHEMA

SERIAL_ID_TABLES = {
    "runs", "scripts", "change_requests", "jobs", "job_results", "compliance_runs",
    "audit", "monitor_results", "alert_rules", "alerts", "syslog_events", "api_tokens",
    "digest_runs", "operational_events", "operational_suppressions", "operational_alerts",
    "maintenance_windows", "notification_deliveries", "report_schedules", "report_runs",
    "incidents", "incident_evidence_links", "incident_case_exports", "protocol_trace_sessions",
    "protocol_trace_events", "distributed_tasks",
    "structured_change_transactions", "telemetry_subscriptions", "telemetry_samples", "telemetry_points",
    "desired_states", "desired_state_runs", "fleet_campaigns", "fleet_campaign_targets",
    "recovery_drills", "network_insights", "analytics_jobs", "l3_route_observations",
}

CONFLICT_KEYS = {
    "groups": ("name",),
    "group_members": ("group_name", "device_name"),
    "device_facts": ("device",),
    "arp_entries": ("device", "ip"),
    "mac_table": ("device", "mac"),
    "ip_neighbors": ("device", "ip", "ifindex", "mac"),
    "vlan_fdb": ("device", "fdb_id", "mac", "ifindex", "bridge_port"),
    "l2_neighbors": ("device", "protocol", "local_port", "sys_name", "chassis_id", "port_id"),
    "topology_device_identity": ("device",),
    "topology_interface_identity": ("device", "ifindex"),
    "mib_values": ("device", "oid"),
    "mib_poll_status": ("device",),
    "storage_meta": ("key",),
    "protocol_profiles": ("device",),
    "vendor_model_packs": ("name",),
    "device_model_bindings": ("device",),
}


def _qmark(sql: str) -> str:
    """Translate DB-API qmark placeholders without touching quoted literals."""
    out = []
    quote = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1]); i += 1
                else:
                    quote = None
        elif ch in ("'", '"'):
            quote = ch; out.append(ch)
        elif ch == "?":
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _portable_type(text: str) -> str:
    text = re.sub(r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", "BIGSERIAL PRIMARY KEY", text,
                  flags=re.I)
    text = re.sub(r"\bBLOB\b", "BYTEA", text, flags=re.I)
    text = re.sub(r"\bREAL\b", "DOUBLE PRECISION", text, flags=re.I)
    return text


def _rewrite_insert(sql: str) -> str:
    m = re.match(r"\s*INSERT\s+OR\s+(IGNORE|REPLACE)\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)\s*"
                 r"\(([^)]*)\)\s*(.*)$", sql, flags=re.I | re.S)
    if not m:
        return sql
    mode, table, cols_raw, rest = m.groups()
    cols = [c.strip() for c in cols_raw.split(",")]
    base = f"INSERT INTO {table} ({cols_raw}) {rest}"
    if mode.upper() == "IGNORE":
        return base + " ON CONFLICT DO NOTHING"
    keys = CONFLICT_KEYS.get(table.lower())
    if not keys:
        raise RuntimeError(f"PostgreSQL compatibility has no conflict key for {table}")
    update_cols = [c for c in cols if c.lower() not in {k.lower() for k in keys}]
    if not update_cols:
        return base + f" ON CONFLICT ({','.join(keys)}) DO NOTHING"
    sets = ",".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
    return base + f" ON CONFLICT ({','.join(keys)}) DO UPDATE SET {sets}"


def translate_sql(sql: str) -> str:
    return _qmark(_rewrite_insert(sql.strip()))


def postgres_schema_statements():
    script = _portable_type(_SCHEMA)
    return [part.strip() for part in script.split(";") if part.strip()]


class PostgresConn:
    def __init__(self, raw):
        self._c = raw
        self.lock = threading.RLock()
        self.dialect = "postgres"

    @property
    def raw(self):
        return self._c

    def execute(self, sql, params=()):
        q = translate_sql(sql)
        table = None
        im = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", q, re.I)
        if im:
            table = im.group(1).lower()
            if table in SERIAL_ID_TABLES and " RETURNING " not in q.upper():
                q += " RETURNING id"
        with self.lock:
            cur = self._c.execute(q, tuple(params))
            rows = cur.fetchall() if cur.description else []
            lastrowid = None
            if table in SERIAL_ID_TABLES and rows:
                first = rows[0]
                try:
                    lastrowid = first["id"]
                except Exception:
                    lastrowid = first[0]
            return _Result(rows, lastrowid, cur.rowcount, cur.description)

    def executescript(self, sql):
        with self.lock:
            for stmt in [_portable_type(x.strip()) for x in sql.split(";") if x.strip()]:
                self._c.execute(stmt)

    def commit(self):
        # Core PostgreSQL connection runs autocommit to avoid idle transactions.
        return None

    def close(self):
        with self.lock:
            self._c.close()

    @contextmanager
    def transaction(self):
        with self.lock:
            with self._c.transaction():
                yield self


class PostgresDatabase(Database):
    dialect = "postgres"
    distributed_capable = True

    def __init__(self, params=None, conninfo=None, driver=None):
        self.path = "postgresql"
        if driver is None:
            import psycopg as driver  # optional dependency, loaded only when selected
        if conninfo:
            kwargs = {"connect_timeout": 5, "autocommit": True}
            try:
                from psycopg.rows import dict_row
                kwargs["row_factory"] = dict_row
            except Exception:
                pass
            raw = driver.connect(conninfo, **kwargs)
        else:
            kwargs = dict(params or {})
            kwargs.setdefault("connect_timeout", 5)
            kwargs["autocommit"] = True
            try:
                from psycopg.rows import dict_row
                kwargs["row_factory"] = dict_row
            except Exception:
                pass
            raw = driver.connect(**kwargs)
        self._lock = threading.RLock()
        self.conn = PostgresConn(raw)
        for stmt in postgres_schema_statements():
            raw.execute(stmt)
        self._migrate_postgres()
        self._stamp_schema_revision()
        self._held_advisory = set()

    def _migrate_postgres(self):
        for table, col, coldef in _MIGRATIONS:
            row = self.conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=? AND column_name=?",
                (table, col)).fetchone()
            if not row:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {_portable_type(coldef)}")
        # MC-3 normalized evidence indexes/backfill mirror the SQLite additive migration.
        self.conn.execute("UPDATE operational_events SET observed_at=last_ts WHERE observed_at=0")
        self.conn.execute("UPDATE operational_events SET domain='NETWORK' WHERE source_type IN ('snmp_trap','snmp_poll') AND domain='SYSTEM'")
        self.conn.execute("UPDATE operational_events SET domain='CONFIGURATION' WHERE event_type IN ('CONFIG_CHANGE','CONFIGURATION_CHANGE')")
        self.conn.execute("UPDATE operational_events SET domain='SECURITY' WHERE (UPPER(event_type) LIKE '%AUTH%' OR UPPER(event_type) LIKE '%LOGIN%')")
        self.conn.execute("UPDATE operational_events SET entity_type='interface', entity_id=CASE WHEN interface<>'' THEN interface ELSE ifindex END, resource=CASE WHEN resource='' THEN CASE WHEN interface<>'' THEN interface ELSE ifindex END ELSE resource END WHERE entity_type='unknown' AND (interface<>'' OR ifindex<>'')")
        self.conn.execute("UPDATE operational_events SET entity_type='device', entity_id=device WHERE entity_type='unknown' AND device<>''")
        self.conn.execute("UPDATE operational_events SET entity_type='source', entity_id=source WHERE entity_type='unknown' AND source<>''")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_events_domain_time ON operational_events(domain, observed_at DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_events_entity_time ON operational_events(entity_type, entity_id, observed_at DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_events_evidence_ref ON operational_events(evidence_ref)")

    def claim_distributed_task(self, queue, worker_id, now, lease_seconds=60):
        lease_until = float(now) + max(5, int(lease_seconds))
        raw = self.conn.raw
        with self.conn.lock:
            with raw.transaction():
                cur = raw.execute(
                    "SELECT * FROM distributed_tasks WHERE queue=%s AND available_ts<=%s "
                    "AND (state='PENDING' OR (state='CLAIMED' AND lease_until<%s)) "
                    "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1",
                    (queue or "default", float(now), float(now)))
                row = cur.fetchone()
                if not row:
                    return None
                task_id = row["id"] if isinstance(row, dict) else row[0]
                attempts = (row["attempts"] if isinstance(row, dict) else row[8]) + 1
                raw.execute(
                    "UPDATE distributed_tasks SET state='CLAIMED',claimed_by=%s,claim_ts=%s,lease_until=%s,"
                    "attempts=%s,updated_ts=%s WHERE id=%s",
                    (worker_id, float(now), lease_until, int(attempts), float(now), int(task_id)))
        out = self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone()
        return dict(out) if out else None

    @staticmethod
    def _lock_key(name):
        raw = hashlib.sha256(str(name).encode("utf-8")).digest()[:8]
        value = int.from_bytes(raw, "big", signed=False)
        return value - (1 << 64) if value >= (1 << 63) else value

    def try_advisory_lock(self, name):
        key = self._lock_key(name)
        if key in self._held_advisory:
            return True
        row = self.conn.execute("SELECT pg_try_advisory_lock(?) AS locked", (key,)).fetchone()
        ok = bool(row and row["locked"])
        if ok:
            self._held_advisory.add(key)
        return ok

    def advisory_unlock(self, name):
        key = self._lock_key(name)
        if key not in self._held_advisory:
            return True
        row = self.conn.execute("SELECT pg_advisory_unlock(?) AS unlocked", (key,)).fetchone()
        self._held_advisory.discard(key)
        return bool(row and row["unlocked"])

    def close(self):
        for key in list(getattr(self, "_held_advisory", ())):
            try:
                self.conn.execute("SELECT pg_advisory_unlock(?) AS unlocked", (key,))
            except Exception:
                pass
        self.conn.close()


def postgres_params(settings, password=None):
    host = str(settings.get("pg_host") or "").strip()
    dbname = str(settings.get("pg_dbname") or "").strip()
    if not host or not dbname:
        raise RuntimeError("PostgreSQL core requires pg_host and pg_dbname")
    out = {"host": host, "dbname": dbname, "port": int(settings.get("pg_port") or 5432)}
    user = str(settings.get("pg_user") or "").strip()
    sslmode = str(settings.get("pg_sslmode") or "").strip()
    if user:
        out["user"] = user
    if sslmode:
        out["sslmode"] = sslmode
    if password:
        out["password"] = password
    out["application_name"] = str(settings.get("core_db_application_name") or "netconfig")[:63]
    return out


def build_core_database(settings, sqlite_path, password=None, driver=None):
    backend = str(settings.get("core_db_backend") or "sqlite").strip().lower()
    if backend == "sqlite":
        return Database(sqlite_path)
    if backend != "postgres":
        raise RuntimeError("core_db_backend must be sqlite or postgres")
    return PostgresDatabase(params=postgres_params(settings, password=password), driver=driver)


def migrate_sqlite_to_postgres(sqlite_path, target, *, allow_nonempty=False):
    """Copy the portable core dataset from a SQLite database into PostgreSQL.

    The destination schema must already be bootstrapped. By default the copy
    fails closed when any application table in the destination already contains
    rows. PH-2 deliberately does not merge two live control-plane databases.
    """
    import sqlite3
    import time

    source = sqlite3.connect(sqlite_path)
    source.row_factory = sqlite3.Row
    allowed = []
    for m in re.finditer(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)", _SCHEMA, re.I):
        name = m.group(1)
        if name not in allowed and name not in {"storage_meta", "cluster_nodes", "distributed_tasks"}:
            allowed.append(name)
    existing = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    tables = [t for t in allowed if t in existing]
    if not allow_nonempty:
        dirty = []
        for table in tables:
            row = target.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            if row and int(row["n"] or 0):
                dirty.append(table)
        if dirty:
            raise RuntimeError("PostgreSQL destination is not empty: " + ", ".join(dirty[:10]))
    copied = {}
    # The schema declaration order is FK-safe for NetConfig's current tables.
    with target.conn.transaction():
        for table in tables:
            rows = source.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                copied[table] = 0
                continue
            cols = list(rows[0].keys())
            binds = ",".join("?" for _ in cols)
            colsql = ",".join(cols)
            for row in rows:
                target.conn.execute(
                    f"INSERT INTO {table} ({colsql}) VALUES ({binds})",
                    tuple(row[c] for c in cols))
            copied[table] = len(rows)
        # Explicit BIGSERIAL id inserts require sequence repair.
        for table in SERIAL_ID_TABLES:
            if table not in tables:
                continue
            cols = {r[1] for r in source.execute(f"PRAGMA table_info({table})")}
            if "id" not in cols:
                continue
            target.conn.raw.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}','id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}),1), "
                f"EXISTS(SELECT 1 FROM {table}))")
    target.conn.execute(
        "INSERT OR REPLACE INTO storage_meta(key,value,updated_ts) VALUES(?,?,?)",
        ("sqlite_migration", f"source={sqlite_path};rows={sum(copied.values())}", time.time()))
    target.conn.commit()
    source.close()
    return {"tables": copied, "rows": sum(copied.values())}
