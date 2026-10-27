"""24-hour PostgreSQL flow history, with bounded asynchronous write buffering.

Uses the existing History PostgreSQL connection, not the Core Database. Receive
timestamps and decoded counters are preserved; this is not lossless UDP capture
or exporter-time/sampling correction. No credentials appear in status/errors.
"""
from collections import deque
import math
import threading
import time
import uuid

from . import ifhistory

RETENTION_SECONDS = 86400
QUERY_LIMIT = 200000
COLUMNS = ("record_id", "ts", "exporter", "src", "dst", "sport", "dport",
           "proto", "packets", "bytes")
TABLE = "netconfig_flow_history"


class PgFlowHistory(ifhistory.PgHistory):
    """Separate raw-flow table. All variable values use bound parameters."""

    def _create(self, c):
        c.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} ("
                  "record_id text PRIMARY KEY, ts double precision NOT NULL, "
                  "exporter text NOT NULL, src text NOT NULL, dst text NOT NULL, "
                  "sport integer NOT NULL, dport integer NOT NULL, proto text NOT NULL, "
                  "packets numeric(20,0) NOT NULL, bytes numeric(20,0) NOT NULL)")
        c.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {TABLE} (ts)")
        c.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_exporter_ts "
                  f"ON {TABLE} (exporter, ts)")

    def _connect(self):
        c = super()._connect()
        try:
            c.execute("SET statement_timeout = '5000ms'")
            c.execute("SET lock_timeout = '2000ms'")
            return c
        except Exception:
            c.close()
            raise

    def write(self, flows):
        self.ensure_schema()
        rows = [tuple(f[k] for k in COLUMNS) for f in flows]
        with self._connect() as c:
            with c.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {TABLE} ({','.join(COLUMNS)}) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (record_id) DO NOTHING", rows)
            c.commit()

    def prune(self, now=None):
        self.ensure_schema()
        cutoff = (time.time() if now is None else now) - RETENTION_SECONDS
        with self._connect() as c:
            # Short transactions; repeat on later maintenance ticks after a backlog.
            result = c.execute(f"DELETE FROM {TABLE} WHERE record_id IN "
                      f"(SELECT record_id FROM {TABLE} WHERE ts < %s LIMIT 10000)", (cutoff,))
            c.commit()
            return result.rowcount

    def read(self, since, until, exporter=None, limit=QUERY_LIMIT):
        # Read-only: schema provisioning belongs to the background worker.
        limit = max(1, min(int(limit), QUERY_LIMIT))
        since = max(float(since), float(until) - RETENTION_SECONDS)
        where = "ts >= %s AND ts <= %s"
        args = [since, float(until)]
        if exporter:
            where += " AND exporter = %s"
            args.append(str(exporter))
        args.append(limit + 1)
        with self._connect() as c:
            rows = c.execute(f"SELECT {','.join(COLUMNS)} FROM {TABLE} WHERE {where} "
                             "ORDER BY ts DESC, record_id DESC LIMIT %s", args).fetchall()
        flows = [dict(zip(COLUMNS, row, strict=True)) for row in rows[:limit]]
        for f in flows:
            f["ts"] = float(f["ts"])
            f["packets"], f["bytes"] = int(f["packets"]), int(f["bytes"])
        return flows, len(rows) > limit


    def exporters(self, since, until):
        """All saved senders in the period, independent of the analysis row cap."""
        since = max(float(since), float(until) - RETENTION_SECONDS)
        with self._connect() as c:
            rows = c.execute(f"SELECT DISTINCT exporter FROM {TABLE} "
                             "WHERE ts >= %s AND ts <= %s ORDER BY exporter", (since, float(until))).fetchall()
        return [str(row[0]) for row in rows]


def backend_for(manager):
    """Refresh credentials lazily, including after a vault unlock/password change.

    Independent of the SNMP history enable flag and retention setting. The same
    protected password and connection details are reused, never duplicated.
    """
    settings = manager.settings
    base = ifhistory.build_backend(settings, password=manager._pg_password())
    if base is None:
        return None
    key = (base.conninfo, tuple(sorted(base.params.items())))
    cached = getattr(manager, "_flow_history_cache", None)
    if cached is None or cached[0] != key:
        cached = (key, PgFlowHistory(conninfo=base.conninfo, params=base.params))
        manager._flow_history_cache = cached
    return cached[1]


class FlowHistory:
    """Non-blocking receiver enqueue; one DB worker, retry-safe UUID records.

    Pending includes the in-flight batch until its transaction succeeds, so
    snapshots can merge it with committed rows without a gap or double count.
    The buffer is volatile: hard shutdown or prolonged outage can lose records.
    """

    def __init__(self, provider, *, capacity=20000, batch_size=500):
        self.provider = provider
        self.capacity = max(1, int(capacity))
        self.batch_size = max(1, min(int(batch_size), self.capacity))
        self._pending = deque()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._next_prune = 0.0
        # None = not yet known; False = no History database is set, so nothing is
        # buffered and nothing is reported as lost (memory mode is the setup).
        self._configured = None
        self._status = {"enabled": True, "configured": None, "retention_hours": 24, "written": 0,
                        "dropped": 0, "expired": 0, "last_write_ts": None,
                        "last_maintenance_ts": None, "write_error": "Waiting for database connection.",
                        "read_error": "", "maintenance_error": ""}

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="netflow-history", daemon=True)
        self._thread.start()

    def submit(self, flows):
        with self._lock:
            if self._configured is False:
                return
            for f in flows:
                try:
                    row = {k: f[k] for k in COLUMNS if k != "record_id"}
                    row["ts"] = float(row["ts"])
                    if not math.isfinite(row["ts"]):
                        raise ValueError("invalid timestamp")
                    for key in ("sport", "dport", "packets", "bytes"):
                        row[key] = int(row[key])
                        upper = 65535 if key in ("sport", "dport") else (1 << 64) - 1
                        if not 0 <= row[key] <= upper:
                            raise ValueError("invalid counter/port")
                except (KeyError, TypeError, ValueError, OverflowError):
                    self._status["dropped"] += 1
                    continue
                if len(self._pending) >= self.capacity:
                    self._status["dropped"] += 1
                else:
                    self._pending.append(dict(row, record_id=uuid.uuid4().hex))
            ready = len(self._pending) >= self.batch_size
        if ready:
            self._wake.set()

    def status(self):
        with self._lock:
            return {**self._status, "pending": len(self._pending)}

    def _error(self, key, message):
        with self._lock:
            self._status[key] = message

    def _set_configured(self, configured):
        with self._lock:
            self._configured = configured
            self._status["configured"] = configured
            if not configured:
                self._pending.clear()
                for key in ("write_error", "read_error", "maintenance_error", "exporter_error"):
                    self._status[key] = ""

    def flush_once(self, now=None):
        """One bounded batch; only the background worker calls this in production."""
        now = time.time() if now is None else float(now)
        with self._lock:
            while self._pending and self._pending[0]["ts"] < now - RETENTION_SECONDS:
                self._pending.popleft()
                self._status["expired"] += 1
            batch = list(self._pending)[:self.batch_size]
        backend = None
        try:
            backend = self.provider()
            if backend is None:
                self._set_configured(False)
                return False
            self._set_configured(True)
            backend.ensure_schema()
            if batch:
                backend.write(batch)
                with self._lock:
                    for _ in batch:
                        self._pending.popleft()
                    self._status["written"] += len(batch)
                    self._status["last_write_ts"] = now
            self._error("write_error", "")
        except Exception as exc:
            if backend is not None:
                backend._schema_ready = False
            self._error("write_error", f"Database write failed ({type(exc).__name__}). Check History PostgreSQL and vault access.")
            return False
        if now >= self._next_prune:
            try:
                removed = backend.prune(now)
                self._error("maintenance_error", "")
                with self._lock:
                    self._status["last_maintenance_ts"] = now
                self._next_prune = now + (1 if removed >= 10000 else 60)
            except Exception as exc:
                self._error("maintenance_error", f"History cleanup failed ({type(exc).__name__}).")
                self._next_prune = now + 60
        return True

    def _loop(self):
        while not self._stop.is_set():
            ok = self.flush_once()
            with self._lock:
                more = len(self._pending) >= self.batch_size
            if ok and more:
                continue
            if ok:
                self._wake.wait(2)
            else:
                # New exports must not turn a database outage into a busy retry loop.
                self._stop.wait(5)
            self._wake.clear()
        # Drain on graceful stop within a budget. Hard termination can still
        # lose volatile pending rows; the receive thread has already stopped.
        deadline = time.monotonic() + 2
        while self.status()["pending"] and time.monotonic() < deadline:
            if not self.flush_once():
                break

    def stop(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def exporter_choices(self, since, until):
        since = max(float(since), float(until) - RETENTION_SECONDS)
        with self._lock:
            names = {f["exporter"] for f in self._pending if since <= f["ts"] <= until}
        try:
            backend = self.provider()
            if backend is None:
                self._set_configured(False)
                return sorted(names)
            names.update(backend.exporters(since, until))
        except Exception:
            self._error("exporter_error", "Some saved exporters could not be listed. Check the database connection or enter a shorter period.")
        else:
            self._error("exporter_error", "")
        return sorted(names)

    def read_window(self, since, until, exporter=None, limit=QUERY_LIMIT):
        since = max(float(since), float(until) - RETENTION_SECONDS)
        # Snapshot before SELECT: committed in-flight rows have identical UUIDs.
        with self._lock:
            pending = [dict(f) for f in self._pending if since <= f["ts"] <= until
                       and (not exporter or f["exporter"] == exporter)]
        try:
            backend = self.provider()
            if backend is None:
                self._set_configured(False)
                return None
            stored, truncated = backend.read(since, until, exporter=exporter, limit=limit)
        except Exception as exc:
            self._error("read_error", f"Database history unavailable ({type(exc).__name__}); showing recent memory only.")
            return None
        self._error("read_error", "")
        merged = {f["record_id"]: f for f in stored}
        merged.update({f["record_id"]: f for f in pending})
        return {"flows": list(merged.values()), "source": "postgres",
                "truncated": truncated, "query_limit": min(int(limit), QUERY_LIMIT),
                "status": self.status()}
