"""
ifhistory.py -- optional PostgreSQL-backed long interface throughput history.

The base product is stdlib-only and keeps live interface samples in SQLite,
pruned to a short window (snmp_history_seconds, ~30 min) so the live graph stays
cheap. This module adds an OPTIONAL longer-retention store -- backed by
PostgreSQL -- so the SNMP page can also show a 24h history graph.

It is imported lazily and is never required. When it is disabled in settings, or
the psycopg driver / PostgreSQL server is unavailable, the rest of NetConfig runs
exactly as before and the history graph simply reports that no backend is
configured. This preserves the zero-dependency, air-gapped default install: only
operators who opt in and provide connection details pull in psycopg and a running
server.

Connection details are entered in Settings -> Database as discrete columns
(host / port / dbname / user / sslmode); the password is kept in the vault like
the SMTP/O365 secrets, never in settings.json. A legacy single-string DSN
(if_history_dsn) still works as an override. Only the raw rate samples are stored
(device, ifindex, ts, in/out bps); interface descriptions are read from the live
SQLite stats at display time, so this table stays lean and always reflects the
current interface names.
"""

import time

# Table name is a fixed identifier (never user input); values are always bound.
_TABLE = "netconfig_if_history"

# Vault secret that holds the PostgreSQL password (kept out of settings.json).
VAULT_SECRET = "__pg_history__"

# Columns created for the history table, exposed so the UI can describe them.
TABLE_COLUMNS = (
    ("device", "text NOT NULL"),
    ("ifindex", "text NOT NULL"),
    ("ts", "double precision NOT NULL"),
    ("in_bps", "double precision"),
    ("out_bps", "double precision"),
)


class PgHistory:
    """A thin PostgreSQL writer/reader for interface rate samples.

    Connections are opened per operation. At poll cadence (tens of seconds) this
    is negligible and keeps the writer (background poller thread) and readers
    (per-request web threads) trivially isolated without a shared pool.

    Construct with EITHER a legacy conninfo string, OR a params dict of discrete
    libpq keywords (host, port, dbname, user, password, sslmode). psycopg is only
    imported when a connection is actually opened.
    """

    def __init__(self, conninfo=None, params=None, retention_hours=24):
        self.conninfo = conninfo or None
        self.params = dict(params or {})
        self.retention_hours = float(retention_hours or 24)
        self._psycopg = None
        self._schema_ready = False
        self.last_error = None

    def _driver(self):
        if self._psycopg is None:
            import psycopg  # lazy: absent driver must not break the base app
            self._psycopg = psycopg
        return self._psycopg

    def _connect(self):
        drv = self._driver()
        if self.conninfo:
            return drv.connect(self.conninfo, connect_timeout=5)
        # psycopg escapes/quotes each keyword parameter safely.
        return drv.connect(connect_timeout=5, **self.params)

    def _create(self, c):
        cols = ", ".join(f"{name} {typ}" for name, typ in TABLE_COLUMNS)
        c.execute(f"CREATE TABLE IF NOT EXISTS {_TABLE} ({cols})")
        c.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_dev_ts "
                  f"ON {_TABLE} (device, ts)")

    def ensure_schema(self):
        if self._schema_ready:
            return
        with self._connect() as c:
            self._create(c)
            c.commit()
        self._schema_ready = True

    def ensure_ready(self):
        """Connect and make sure the history table exists, creating it (with all
        its columns and index) when missing.

        Returns {ok, created, error}: `created` is True only when this call made
        the table, so the UI can tell "table already present" from "table
        created". Never raises -- connection/permission failures come back as
        {ok: False, error: ...}.
        """
        try:
            with self._connect() as c:
                row = c.execute("SELECT to_regclass(%s)", (_TABLE,)).fetchone()
                existed = bool(row and row[0])
                if not existed:
                    self._create(c)
                    c.commit()
            self._schema_ready = True
            self.last_error = None
            return {"ok": True, "created": not existed, "error": None}
        except Exception as e:
            self.last_error = str(e)
            return {"ok": False, "created": False, "error": str(e)}

    def available(self):
        """True if the driver imports and the server is reachable/writable."""
        return self.ensure_ready()["ok"]

    def write(self, device, samples):
        """Persist samples and prune beyond the retention window.

        `samples` is an iterable of (ifindex, descr, in_bps, out_bps, ts) as
        returned by Inventory.set_interfaces; descr is ignored here.
        """
        rows = []
        for s in samples or ():
            ifindex, _descr, in_bps, out_bps, ts = s
            rows.append((device, str(ifindex), float(ts),
                         None if in_bps is None else float(in_bps),
                         None if out_bps is None else float(out_bps)))
        if not rows:
            return
        self.ensure_schema()
        cutoff = time.time() - self.retention_hours * 3600.0
        with self._connect() as c:
            with c.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {_TABLE} (device, ifindex, ts, in_bps, out_bps) "
                    "VALUES (%s,%s,%s,%s,%s)", rows)
            c.execute(f"DELETE FROM {_TABLE} WHERE ts < %s", (cutoff,))
            c.commit()

    def read(self, device, hours=24, bucket_seconds=60):
        """Return {ifindex: {points: [[bucket_ts, avg_in_bps, avg_out_bps], ...]}}
        downsampled into fixed-width time buckets to bound the payload."""
        self.ensure_schema()
        since = time.time() - float(hours) * 3600.0
        bucket = max(int(bucket_seconds or 60), 1)
        out = {}
        with self._connect() as c:
            cur = c.execute(
                f"SELECT ifindex, floor(ts/%s)*%s AS bucket, "
                f"avg(in_bps), avg(out_bps) FROM {_TABLE} "
                "WHERE device=%s AND ts >= %s "
                "GROUP BY ifindex, bucket ORDER BY ifindex, bucket",
                (bucket, bucket, device, since))
            for ifindex, bkt, avg_in, avg_out in cur:
                d = out.setdefault(str(ifindex), {"points": []})
                d["points"].append([
                    float(bkt),
                    None if avg_in is None else float(avg_in),
                    None if avg_out is None else float(avg_out)])
        return out


def _params_from_settings(settings, password=None):
    """Build a libpq keyword dict from the discrete Settings -> Database fields.
    Returns None when the minimum (host + dbname) is not configured."""
    host = (settings.get("pg_host") or "").strip()
    dbname = (settings.get("pg_dbname") or "").strip()
    if not host or not dbname:
        return None
    params = {"host": host, "dbname": dbname}
    try:
        params["port"] = int(settings.get("pg_port") or 5432)
    except (TypeError, ValueError):
        params["port"] = 5432
    user = (settings.get("pg_user") or "").strip()
    if user:
        params["user"] = user
    sslmode = (settings.get("pg_sslmode") or "").strip()
    if sslmode:
        params["sslmode"] = sslmode
    if password:
        params["password"] = password
    return params


def build_backend(settings, password=None):
    """Construct a PgHistory from settings, or None when disabled/unconfigured.

    A non-empty legacy `if_history_dsn` wins as an explicit override; otherwise
    the discrete Settings -> Database columns are used. Never imports psycopg.
    """
    retention = settings.get("if_history_hours", 24)
    dsn = (settings.get("if_history_dsn") or "").strip()
    if dsn:
        return PgHistory(conninfo=dsn, retention_hours=retention)
    params = _params_from_settings(settings, password=password)
    if params is None:
        return None
    return PgHistory(params=params, retention_hours=retention)


def get_backend(settings, password=None):
    """Backend for normal use: honours the master enable flag. Returns None when
    disabled or unconfigured, and never raises or imports psycopg."""
    try:
        if not settings.get("if_history_enabled"):
            return None
        return build_backend(settings, password=password)
    except Exception:
        return None
