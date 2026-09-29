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
import time
from contextlib import contextmanager

from .db import (Database, _MIGRATIONS, _Result, _SCHEMA, _schema_statements,
                 backfill_operational_alert_correlation_keys)

SERIAL_ID_TABLES = {
    "runs", "scripts", "change_requests", "jobs", "job_results", "compliance_runs",
    "audit", "monitor_results", "alert_rules", "alerts", "syslog_events", "api_tokens",
    "digest_runs", "operational_events", "operational_suppressions", "operational_alerts",
    "maintenance_windows", "notification_deliveries", "report_schedules", "report_runs",
    "incidents", "incident_evidence_links", "incident_case_exports", "protocol_trace_sessions",
    "change_events", "external_events",
    "protocol_trace_events", "distributed_tasks",
    "structured_change_transactions", "telemetry_subscriptions", "telemetry_samples", "telemetry_points",
    "desired_states", "desired_state_runs", "fleet_campaigns", "fleet_campaign_targets",
    "recovery_drills", "network_insights", "analytics_jobs", "l3_route_observations",
    "service_entities", "service_dependencies", "l3_interface_observations", "correlation_hypotheses",
    "external_sources", "external_ingest_receipts", "correlation_runs",
    "change_planning_evidence", "change_plans",
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
    "external_events": ("source_system", "source_event_id"),
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


def postgres_schema_statements(*, indexes=None):
    return [_portable_type(stmt) for stmt in _schema_statements(indexes=indexes)]


class PostgresConnectionLost(RuntimeError):
    """Connection failed. Writes are never replayed because commit outcome may be unknown."""


class PostgresTransactionBusy(RuntimeError):
    """Bounded transaction concurrency budget was exhausted."""


def _sqlstate(exc):
    state = getattr(exc, "sqlstate", None)
    if not state:
        state = getattr(getattr(exc, "diag", None), "sqlstate", None)
    return str(state or "")


def _connection_failure(exc, raw=None):
    state = _sqlstate(exc)
    if state.startswith("08"):
        return True
    closed = getattr(raw, "closed", False)
    return bool(closed)


def _retryable_transaction_failure(exc):
    return _sqlstate(exc) in {"40001", "40P01"}


def _read_only_sql(sql):
    head = str(sql or "").lstrip().split(None, 1)
    return bool(head and head[0].upper() in {"SELECT", "SHOW", "VALUES"})


class PostgresConn:
    def __init__(self, raw, reconnect=None):
        self._c = raw
        self._reconnect = reconnect
        self.lock = threading.RLock()
        self.dialect = "postgres"
        self._session_generation = 0

    @property
    def session_generation(self):
        return self._session_generation

    @property
    def raw(self):
        return self._c

    def _recover_connection(self):
        if self._reconnect is None:
            return False
        old = self._c
        self._c = self._reconnect()
        self._session_generation += 1
        try:
            old.close()
        except Exception:
            pass
        return True

    def execute(self, sql, params=()):
        q = translate_sql(sql)
        table = None
        im = re.match(r"\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)", q, re.I)
        if im:
            table = im.group(1).lower()
            if table in SERIAL_ID_TABLES and " RETURNING " not in q.upper():
                q += " RETURNING id"
        with self.lock:
            try:
                cur = self._c.execute(q, tuple(params))
            except Exception as exc:
                if not _connection_failure(exc, self._c):
                    raise
                recovered = self._recover_connection()
                if recovered and _read_only_sql(q):
                    cur = self._c.execute(q, tuple(params))
                else:
                    raise PostgresConnectionLost(
                        "PostgreSQL connection was lost; write/transaction was not replayed because outcome may be unknown"
                    ) from exc
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
            try:
                with self._c.transaction():
                    yield self
            except Exception as exc:
                if _connection_failure(exc, self._c):
                    try:
                        self._recover_connection()
                    except Exception:
                        pass
                    raise PostgresConnectionLost(
                        "PostgreSQL connection was lost inside a transaction; transaction was not replayed"
                    ) from exc
                raise


class PostgresDatabase(Database):
    dialect = "postgres"
    distributed_capable = True

    def __init__(self, params=None, conninfo=None, driver=None, *,
                 max_concurrent_transactions=8, transaction_acquire_timeout=5.0,
                 transaction_retry_attempts=3):
        self.path = "postgresql"
        if driver is None:
            import psycopg as driver  # optional dependency, loaded only when selected
        self._driver = driver
        self._conninfo = conninfo
        self._connect_kwargs = dict(params or {})
        self._connect_kwargs.setdefault("connect_timeout", 5)
        self._connect_kwargs["autocommit"] = True
        try:
            from psycopg.rows import dict_row
            self._connect_kwargs["row_factory"] = dict_row
        except Exception:
            pass
        self._max_concurrent_transactions = max(1, min(int(max_concurrent_transactions), 64))
        self._transaction_acquire_timeout = max(0.05, min(float(transaction_acquire_timeout), 60.0))
        self._transaction_retry_attempts = max(1, min(int(transaction_retry_attempts), 8))
        self._transaction_budget = threading.BoundedSemaphore(self._max_concurrent_transactions)
        raw = self._connect_raw()
        self._lock = threading.RLock()
        self.conn = PostgresConn(raw, reconnect=self._connect_raw)
        # As with SQLite, migrate additive columns before creating indexes that
        # may reference those newer columns. This is essential for upgrades.
        for stmt in postgres_schema_statements(indexes=False):
            raw.execute(stmt)
        self._migrate_postgres()
        for stmt in postgres_schema_statements(indexes=True):
            raw.execute(stmt)
        self._stamp_schema_revision()
        self._held_advisory = {}

    def _connect_raw(self):
        kwargs = dict(self._connect_kwargs)
        if self._conninfo:
            return self._driver.connect(self._conninfo, **kwargs)
        return self._driver.connect(**kwargs)

    def run_retryable_transaction(self, callback, *, max_attempts=None):
        """Run a database-only callback in a dedicated transaction with bounded retries.

        Only serialization failures (40001) and deadlocks (40P01) are retried.
        Connection failures are never replayed because the commit outcome may be
        unknown. Callers must keep network/device side effects outside callback.
        """
        attempts = self._transaction_retry_attempts if max_attempts is None else max(1, min(int(max_attempts), 8))
        if not self._transaction_budget.acquire(timeout=self._transaction_acquire_timeout):
            raise PostgresTransactionBusy("PostgreSQL transaction concurrency budget exhausted")
        try:
            last = None
            for attempt in range(1, attempts + 1):
                raw = self._connect_raw()
                conn = PostgresConn(raw)
                try:
                    with raw.transaction():
                        return callback(conn)
                except Exception as exc:
                    last = exc
                    if _connection_failure(exc, raw):
                        raise PostgresConnectionLost(
                            "PostgreSQL connection lost during dedicated transaction; transaction not replayed"
                        ) from exc
                    if not _retryable_transaction_failure(exc) or attempt >= attempts:
                        raise
                    time.sleep(min(0.05 * (2 ** (attempt - 1)), 0.5))
                finally:
                    try:
                        raw.close()
                    except Exception:
                        pass
            raise last
        finally:
            self._transaction_budget.release()

    def resilience_status(self):
        return {
            "backend": "postgres",
            "max_concurrent_transactions": self._max_concurrent_transactions,
            "transaction_acquire_timeout_seconds": self._transaction_acquire_timeout,
            "transaction_retry_attempts": self._transaction_retry_attempts,
            "retryable_sqlstates": ["40001", "40P01"],
            "connection_failure_write_replay": False,
        }

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
        self.conn.execute("UPDATE operational_alerts SET last_event_id=event_id WHERE last_event_id IS NULL")
        backfill_operational_alert_correlation_keys(self.conn)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_operational_alert_correlation ON operational_alerts(correlation_key, state, last_ts DESC)")
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_external_events_tenant_source_time ON external_events(tenant_id, source_key, received_ts, id)")
        self._backfill_incident_evidence_timing()

    def claim_distributed_task(self, queue, worker_id, now, lease_seconds=60, instance_id=""):
        lease_until = float(now) + max(5, int(lease_seconds))
        token = self._claim_token()
        raw = self.conn.raw
        with self.conn.lock:
            with raw.transaction():
                cur = raw.execute(
                    "SELECT * FROM distributed_tasks WHERE queue=%s AND available_ts<=%s "
                    "AND state='PENDING' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1",
                    (queue or "default", float(now)))
                row = cur.fetchone()
                if not row:
                    return None
                task_id = row["id"] if isinstance(row, dict) else row[0]
                attempts = int(row.get("attempts", 0) if isinstance(row, dict) else row[8]) + 1
                generation = int(row.get("claim_generation", 0) if isinstance(row, dict) else 0) + 1
                raw.execute(
                    "UPDATE distributed_tasks SET state='CLAIMED',claimed_by=%s,claimed_instance=%s,"
                    "claim_ts=%s,lease_until=%s,attempts=%s,claim_generation=%s,claim_token=%s,"
                    "recovery_reason='',updated_ts=%s WHERE id=%s AND state='PENDING'",
                    (worker_id, str(instance_id or "")[:128], float(now), lease_until, int(attempts),
                     int(generation), token, float(now), int(task_id)))
        out = self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone()
        return dict(out) if out else None

    def recover_expired_distributed_tasks(self, now, limit=100):
        limit = min(5000, max(1, int(limit)))
        raw = self.conn.raw
        recovered = []
        with self.conn.lock:
            with raw.transaction():
                cur = raw.execute(
                    "SELECT id FROM distributed_tasks WHERE state='CLAIMED' AND lease_until<%s "
                    "ORDER BY id FOR UPDATE SKIP LOCKED LIMIT %s", (float(now), limit))
                rows = cur.fetchall()
                recovered = [int(r["id"] if isinstance(r, dict) else r[0]) for r in rows]
                for task_id in recovered:
                    raw.execute(
                        "UPDATE distributed_tasks SET state='RECOVERY_REQUIRED',lease_until=NULL,"
                        "recovery_reason=%s,updated_ts=%s WHERE id=%s AND state='CLAIMED' AND lease_until<%s",
                        ("worker lease expired; automatic replay disabled", float(now), task_id, float(now)))
        return [dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (i,)).fetchone())
                for i in recovered]

    @staticmethod
    def _lock_key(name):
        raw = hashlib.sha256(str(name).encode("utf-8")).digest()[:8]
        value = int.from_bytes(raw, "big", signed=False)
        return value - (1 << 64) if value >= (1 << 63) else value

    def try_advisory_lock(self, name):
        key = self._lock_key(name)
        generation = int(getattr(self.conn, "session_generation", 0))
        held_generation = self._held_advisory.get(key)
        if held_generation == generation:
            # Force a round trip before trusting a session-scoped lock. A read
            # reconnect increments session_generation; the old lock is then known
            # to be gone and must be reacquired/fenced against peer nodes.
            try:
                self.conn.execute("SELECT 1 AS ok").fetchone()
            except Exception:
                return False
            generation = int(getattr(self.conn, "session_generation", 0))
            if held_generation == generation:
                return True
            self._held_advisory.pop(key, None)
        elif held_generation is not None:
            # The PostgreSQL session changed; all session-scoped locks from the
            # prior generation are gone. Never trust stale in-process lock state.
            self._held_advisory.pop(key, None)
        row = self.conn.execute("SELECT pg_try_advisory_lock(?) AS locked", (key,)).fetchone()
        generation = int(getattr(self.conn, "session_generation", 0))
        ok = bool(row and row["locked"])
        if ok:
            self._held_advisory[key] = generation
        return ok

    def advisory_unlock(self, name):
        key = self._lock_key(name)
        generation = int(getattr(self.conn, "session_generation", 0))
        held_generation = self._held_advisory.get(key)
        if held_generation is None:
            return True
        if held_generation != generation:
            self._held_advisory.pop(key, None)
            return True
        row = self.conn.execute("SELECT pg_advisory_unlock(?) AS unlocked", (key,)).fetchone()
        self._held_advisory.pop(key, None)
        return bool(row and row["unlocked"])

    def close(self):
        generation = int(getattr(self.conn, "session_generation", 0))
        for key, held_generation in list(getattr(self, "_held_advisory", {}).items()):
            if held_generation != generation:
                continue
            try:
                self.conn.execute("SELECT pg_advisory_unlock(?) AS unlocked", (key,))
            except Exception:
                pass
        self._held_advisory.clear()
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


def preflight_core_postgres(settings, password=None, driver=None):
    """Fail-closed Core PostgreSQL readiness/bootstrap check.

    This validates required connection fields, a protected pre-vault credential,
    driver availability, connectivity, schema bootstrap/migration and final
    schema revision. It never mutates settings.json.
    """
    if not password:
        return {"ok": False, "stage": "credential",
                "error": "Core PostgreSQL credential is not configured"}
    try:
        params = postgres_params(settings, password=password)
    except Exception as exc:
        return {"ok": False, "stage": "configuration", "error": str(exc)[:300]}
    db = None
    try:
        db = PostgresDatabase(
            params=params, driver=driver,
            max_concurrent_transactions=int(settings.get("pg_max_concurrent_transactions") or 8),
            transaction_acquire_timeout=float(settings.get("pg_transaction_acquire_timeout_seconds") or 5.0),
            transaction_retry_attempts=int(settings.get("pg_transaction_retry_attempts") or 3),
        )
        status = db.readiness()
        if not status.get("ok"):
            return {"ok": False, "stage": "schema",
                    "error": str(status.get("error") or "schema revision mismatch")[:300]}
        return {"ok": True, "stage": "ready",
                "schema_revision": status.get("schema_revision", ""),
                "backend": "postgres"}
    except ModuleNotFoundError as exc:
        return {"ok": False, "stage": "driver",
                "error": "psycopg 3 driver is not installed for the NetConfig Python runtime"}
    except Exception as exc:
        return {"ok": False, "stage": "connection-or-schema", "error": str(exc)[:300]}
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def build_core_database(settings, sqlite_path, password=None, driver=None):
    backend = str(settings.get("core_db_backend") or "sqlite").strip().lower()
    if backend == "sqlite":
        return Database(sqlite_path)
    if backend != "postgres":
        raise RuntimeError("core_db_backend must be sqlite or postgres")
    return PostgresDatabase(
        params=postgres_params(settings, password=password), driver=driver,
        max_concurrent_transactions=int(settings.get("pg_max_concurrent_transactions") or 8),
        transaction_acquire_timeout=float(settings.get("pg_transaction_acquire_timeout_seconds") or 5.0),
        transaction_retry_attempts=int(settings.get("pg_transaction_retry_attempts") or 3),
    )


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
