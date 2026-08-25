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
operators who opt in and provide a DSN pull in psycopg and a running server.

Only the raw rate samples are stored here (device, ifindex, ts, in/out bps);
interface descriptions are read from the live SQLite stats at display time, so
this table stays lean and always reflects the current interface names.
"""

import time

# Table name is a fixed identifier (never user input); values are always bound.
_TABLE = "netconfig_if_history"


class PgHistory:
    """A thin PostgreSQL writer/reader for interface rate samples.

    Connections are opened per operation. At poll cadence (tens of seconds) this
    is negligible and keeps the writer (background poller thread) and readers
    (per-request web threads) trivially isolated without a shared pool.
    """

    def __init__(self, dsn, retention_hours=24):
        self.dsn = dsn
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
        return self._driver().connect(self.dsn, connect_timeout=5)

    def ensure_schema(self):
        if self._schema_ready:
            return
        with self._connect() as c:
            c.execute(
                f"CREATE TABLE IF NOT EXISTS {_TABLE} ("
                "device text NOT NULL, ifindex text NOT NULL, "
                "ts double precision NOT NULL, "
                "in_bps double precision, out_bps double precision)")
            c.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_dev_ts "
                f"ON {_TABLE} (device, ts)")
            c.commit()
        self._schema_ready = True

    def available(self):
        """True if the driver imports and the server is reachable/writable."""
        try:
            self.ensure_schema()
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

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


def get_backend(settings):
    """Build a history backend from settings, or None when disabled/unconfigured.

    Never raises and never imports psycopg: construction is cheap and lazy, so a
    misconfigured or driver-less host degrades to "no history backend" rather
    than breaking SNMP polling or the web console.
    """
    try:
        if not settings.get("if_history_enabled"):
            return None
        dsn = (settings.get("if_history_dsn") or "").strip()
        if not dsn:
            return None
        return PgHistory(dsn, retention_hours=settings.get("if_history_hours", 24))
    except Exception:
        return None
