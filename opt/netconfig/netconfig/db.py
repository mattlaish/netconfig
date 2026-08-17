"""
db.py -- Shared SQLite database for a netconfig instance (WAL, stdlib only).

v1 kept a single `inventory.py` connection with two tables (devices, runs). v2
adds groups, users/RBAC, scripts, the change-approval workflow, jobs/results,
compliance history, SNMP facts, and an audit trail -- so a single owning
connection is cleaner than each module opening its own handle to the same file.

`Database` opens the connection, applies the schema idempotently, and runs small
additive migrations so an existing v1 data directory upgrades in place without
losing devices or history. Every module (Inventory, Users, Automation, Workflow,
Compliance) takes this shared connection.
"""

import sqlite3
import threading

_SCHEMA = """
-- ---- devices (v1) ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    name        TEXT PRIMARY KEY,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 22,
    platform    TEXT NOT NULL DEFAULT 'generic',
    device_type TEXT NOT NULL DEFAULT 'network',
    netflow     INTEGER NOT NULL DEFAULT 0,
    monitor_ports TEXT NOT NULL DEFAULT '',
    monitor_urls TEXT NOT NULL DEFAULT '',
    secret_ref  TEXT,
    enable_ref  TEXT,
    use_key     INTEGER NOT NULL DEFAULT 0,
    legacy      INTEGER NOT NULL DEFAULT 0,
    scrub       INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    tags        TEXT NOT NULL DEFAULT '[]',
    notes       TEXT NOT NULL DEFAULT '',
    created     REAL,
    updated     REAL
);
CREATE TABLE IF NOT EXISTS runs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    device   TEXT NOT NULL,
    ts       REAL NOT NULL,
    ok       INTEGER NOT NULL,
    changed  INTEGER NOT NULL DEFAULT 0,
    message  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_runs_device ON runs(device, ts);

-- ---- groups ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS groups (
    name        TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT '',
    created     REAL
);
CREATE TABLE IF NOT EXISTS group_members (
    group_name  TEXT NOT NULL,
    device_name TEXT NOT NULL,
    PRIMARY KEY (group_name, device_name)
);

-- ---- users / RBAC ----------------------------------------------------------
-- Console authentication is user-based (PBKDF2, suite standard). This is
-- distinct from the credential vault, which holds *device* secrets and is
-- unlocked separately by an admin. Roles gate the approval workflow.
CREATE TABLE IF NOT EXISTS users (
    username  TEXT PRIMARY KEY,
    pw_salt   BLOB NOT NULL,
    pw_hash   BLOB NOT NULL,
    iters     INTEGER NOT NULL,
    role      TEXT NOT NULL DEFAULT 'viewer',   -- admin|approver|operator|viewer
    fullname  TEXT NOT NULL DEFAULT '',
    disabled  INTEGER NOT NULL DEFAULT 0,
    created   REAL,
    last_login REAL
);

-- ---- automation: reusable scripts -----------------------------------------
CREATE TABLE IF NOT EXISTS scripts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    body        TEXT NOT NULL,          -- one command per line; ${VAR} allowed
    platform    TEXT NOT NULL DEFAULT '',   -- optional platform hint/filter
    created_by  TEXT NOT NULL DEFAULT '',
    created_ts  REAL
);

-- ---- change-approval workflow ---------------------------------------------
-- A change request is the unit of the approval workflow. A junior submits it;
-- an approver reviews; on approval it is executed, producing a job + per-device
-- results. Config-changing work always flows through here.
CREATE TABLE IF NOT EXISTS change_requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL,          -- resolved commands (with ${VAR})
    target_kind  TEXT NOT NULL,          -- device|group|tag|all
    target_value TEXT NOT NULL DEFAULT '',
    mode         TEXT NOT NULL DEFAULT 'config',  -- config|remediate
    requested_by TEXT NOT NULL,
    requested_ts REAL,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|rejected|executed|failed|cancelled
    reviewed_by  TEXT,
    reviewed_ts  REAL,
    review_note  TEXT NOT NULL DEFAULT '',
    job_id       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cr_status ON change_requests(status, requested_ts);

CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER,                -- NULL for ad-hoc (read-only) jobs
    kind        TEXT NOT NULL,          -- config|remediate|collect|command
    title       TEXT NOT NULL DEFAULT '',
    run_by      TEXT NOT NULL DEFAULT '',
    started_ts  REAL,
    finished_ts REAL,
    ok_count    INTEGER NOT NULL DEFAULT 0,
    fail_count  INTEGER NOT NULL DEFAULT 0,
    summary     TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS job_results (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id   INTEGER NOT NULL,
    device   TEXT NOT NULL,
    ok       INTEGER NOT NULL,
    changed  INTEGER NOT NULL DEFAULT 0,
    output   TEXT NOT NULL DEFAULT '',
    ts       REAL
);
CREATE INDEX IF NOT EXISTS idx_jobres_job ON job_results(job_id);

-- ---- compliance history ----------------------------------------------------
CREATE TABLE IF NOT EXISTS compliance_runs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL,
    standard   TEXT NOT NULL,
    run_by     TEXT NOT NULL DEFAULT '',
    total      INTEGER NOT NULL DEFAULT 0,
    passed     INTEGER NOT NULL DEFAULT 0,
    failed     INTEGER NOT NULL DEFAULT 0,
    report     TEXT NOT NULL DEFAULT ''   -- JSON detail
);

-- ---- SNMP-discovered facts -------------------------------------------------
CREATE TABLE IF NOT EXISTS device_facts (
    device      TEXT PRIMARY KEY,
    reachable   INTEGER NOT NULL DEFAULT 0,
    sysname     TEXT NOT NULL DEFAULT '',
    sysdescr    TEXT NOT NULL DEFAULT '',
    sysobjectid TEXT NOT NULL DEFAULT '',
    uptime      TEXT NOT NULL DEFAULT '',
    contact     TEXT NOT NULL DEFAULT '',
    location    TEXT NOT NULL DEFAULT '',
    last_polled REAL,
    error       TEXT NOT NULL DEFAULT ''
);

-- ---- SNMP-discovered interface stats --------------------------------------
CREATE TABLE IF NOT EXISTS interface_stats (
    device     TEXT NOT NULL,
    ifindex    TEXT NOT NULL,
    descr      TEXT NOT NULL DEFAULT '',
    admin      TEXT NOT NULL DEFAULT '',
    oper       TEXT NOT NULL DEFAULT '',
    speed      INTEGER NOT NULL DEFAULT 0,
    in_octets  INTEGER NOT NULL DEFAULT 0,
    out_octets INTEGER NOT NULL DEFAULT 0,
    in_errors  INTEGER NOT NULL DEFAULT 0,
    out_errors INTEGER NOT NULL DEFAULT 0,
    in_bps     REAL,
    out_bps    REAL,
    ts         REAL,
    PRIMARY KEY (device, ifindex)
);

-- rolling per-interface rate samples for live graphs (pruned by time window)
CREATE TABLE IF NOT EXISTS interface_samples (
    device  TEXT NOT NULL,
    ifindex TEXT NOT NULL,
    ts      REAL NOT NULL,
    in_bps  REAL,
    out_bps REAL
);
CREATE INDEX IF NOT EXISTS idx_ifsamp ON interface_samples(device, ts);

-- ---- audit trail -----------------------------------------------------------
-- Append-only record of who did what. Satisfies the "who requested / approved /
-- executed / affected" requirement for internal control and forensics.
CREATE TABLE IF NOT EXISTS audit (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    actor  TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts);

-- ---- monitor history + alerting -------------------------------------------
CREATE TABLE IF NOT EXISTS monitor_results (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     REAL NOT NULL,
    device TEXT NOT NULL,
    kind   TEXT NOT NULL,          -- port | http | tls
    target TEXT NOT NULL,          -- tcp/22, https://host/api, host:443
    status TEXT NOT NULL,          -- open/closed/filtered | 200/down | valid/invalid
    value  REAL,                   -- latency ms | http code | days-to-expiry
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_mr ON monitor_results(device, kind, target, ts);

CREATE TABLE IF NOT EXISTS alert_rules (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT NOT NULL,
    device    TEXT NOT NULL DEFAULT '',   -- '' = all devices
    metric    TEXT NOT NULL,              -- port_state|http_status|response_time|tls_expiry|tls_valid
    target    TEXT NOT NULL DEFAULT '',   -- '' = any target of that kind
    op        TEXT NOT NULL,              -- is|is_not|==|!=|>|<|>=|<=
    threshold TEXT NOT NULL DEFAULT '',
    severity  TEXT NOT NULL DEFAULT 'medium',
    enabled   INTEGER NOT NULL DEFAULT 1,
    created   REAL
);

CREATE TABLE IF NOT EXISTS alerts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id   INTEGER,
    rule_name TEXT NOT NULL DEFAULT '',
    device    TEXT NOT NULL,
    target    TEXT NOT NULL DEFAULT '',
    metric    TEXT NOT NULL DEFAULT '',
    severity  TEXT NOT NULL DEFAULT 'medium',
    message   TEXT NOT NULL DEFAULT '',
    state     TEXT NOT NULL,              -- firing | resolved
    first_ts  REAL,
    last_ts   REAL
);
CREATE INDEX IF NOT EXISTS idx_alerts_state ON alerts(state, device);

-- ---- L2/L3 reachability tables (network devices) ---------------------------
CREATE TABLE IF NOT EXISTS arp_entries (
    device  TEXT NOT NULL,
    ip      TEXT NOT NULL,
    mac     TEXT NOT NULL,
    ifindex TEXT NOT NULL DEFAULT '',
    ts      REAL,
    PRIMARY KEY (device, ip)
);
CREATE TABLE IF NOT EXISTS mac_table (
    device  TEXT NOT NULL,
    mac     TEXT NOT NULL,
    port    TEXT NOT NULL DEFAULT '',
    ifindex TEXT NOT NULL DEFAULT '',
    ifdescr TEXT NOT NULL DEFAULT '',
    ts      REAL,
    PRIMARY KEY (device, mac)
);
"""

# Additive column migrations: (table, column, coldef). Applied only if absent.
_MIGRATIONS = [
    ("devices", "snmp_version", "TEXT NOT NULL DEFAULT ''"),   # '', v2c, v3
    ("devices", "snmp_ref", "TEXT"),                            # vault entry
    ("devices", "device_type", "TEXT NOT NULL DEFAULT 'network'"),  # system|network|application
    ("devices", "netflow", "INTEGER NOT NULL DEFAULT 0"),      # collect NetFlow (network devices)
    ("devices", "monitor_ports", "TEXT NOT NULL DEFAULT ''"),  # tcp/udp ports (system devices)
    ("devices", "monitor_urls", "TEXT NOT NULL DEFAULT ''"),   # http(s) endpoints (application devices)
]


class _Result:
    """Eagerly-materialised result of one execute(), so no cursor state is shared
    across threads. Supports the fetchall/fetchone/iterate/lastrowid usage in the
    codebase."""
    __slots__ = ("_rows", "_i", "lastrowid", "rowcount", "description")

    def __init__(self, rows, lastrowid, rowcount, description):
        self._rows = rows
        self._i = 0
        self.lastrowid = lastrowid
        self.rowcount = rowcount
        self.description = description

    def fetchall(self):
        return self._rows

    def fetchone(self):
        if self._i < len(self._rows):
            r = self._rows[self._i]
            self._i += 1
            return r
        return None

    def __iter__(self):
        return iter(self._rows)


class _LockedConn:
    """A thread-safe front for a single sqlite3.Connection. Every statement (and
    its result fetch) runs while holding one re-entrant lock, so request threads
    and the background SNMP poller can't corrupt each other's cursor state. The
    lock is exposed so multi-statement critical sections can be made atomic."""

    def __init__(self, conn, lock):
        self._c = conn
        self.lock = lock

    def execute(self, sql, params=()):
        with self.lock:
            cur = self._c.execute(sql, params)
            rows = cur.fetchall()          # [] for INSERT/UPDATE/DELETE/DDL
            return _Result(rows, cur.lastrowid, cur.rowcount, cur.description)

    def executescript(self, sql):
        with self.lock:
            self._c.executescript(sql)

    def commit(self):
        with self.lock:
            self._c.commit()

    def close(self):
        with self.lock:
            self._c.close()

    def __getattr__(self, name):
        # row_factory, total_changes, etc. — read-only/attribute access
        return getattr(self._c, name)


class Database:
    def __init__(self, path):
        self.path = path
        raw = sqlite3.connect(path, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA busy_timeout=5000")
        raw.executescript(_SCHEMA)
        self._lock = threading.RLock()
        self.conn = _LockedConn(raw, self._lock)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        for table, col, coldef in _MIGRATIONS:
            cols = {r["name"] for r in
                    self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")

    def audit(self, actor, action, target="", detail=""):
        import time
        self.conn.execute(
            "INSERT INTO audit (ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
            (time.time(), actor or "", action, target, detail))
        self.conn.commit()

    def recent_audit(self, limit=200):
        rows = self.conn.execute(
            "SELECT * FROM audit ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---- monitor history ------------------------------------------------
    def record_result(self, device, kind, target, status, value=None, detail=""):
        import time
        self.conn.execute(
            "INSERT INTO monitor_results (ts, device, kind, target, status, value, detail) "
            "VALUES (?,?,?,?,?,?,?)",
            (time.time(), device, kind, target, status,
             None if value is None else float(value), detail or ""))
        self.conn.commit()

    def result_history(self, device, kind=None, target=None, since=None, limit=500):
        q = "SELECT * FROM monitor_results WHERE device=?"
        args = [device]
        if kind:
            q += " AND kind=?"; args.append(kind)
        if target:
            q += " AND target=?"; args.append(target)
        if since:
            q += " AND ts>=?"; args.append(since)
        q += " ORDER BY ts DESC LIMIT ?"; args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def prune_results(self, older_than_ts):
        self.conn.execute("DELETE FROM monitor_results WHERE ts < ?", (older_than_ts,))
        self.conn.commit()

    # ---- alert rules ----------------------------------------------------
    def add_rule(self, name, device, metric, target, op, threshold, severity="medium"):
        import time
        cur = self.conn.execute(
            "INSERT INTO alert_rules (name, device, metric, target, op, threshold, "
            "severity, enabled, created) VALUES (?,?,?,?,?,?,?,1,?)",
            (name, device or "", metric, target or "", op, str(threshold), severity, time.time()))
        self.conn.commit()
        return cur.lastrowid

    def rules(self, enabled_only=False):
        q = "SELECT * FROM alert_rules"
        if enabled_only:
            q += " WHERE enabled=1"
        q += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(q).fetchall()]

    def delete_rule(self, rule_id):
        self.conn.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
        self.conn.commit()

    def set_rule_enabled(self, rule_id, enabled):
        self.conn.execute("UPDATE alert_rules SET enabled=? WHERE id=?",
                          (1 if enabled else 0, rule_id))
        self.conn.commit()

    # ---- alerts (firing/resolved state) ---------------------------------
    def firing_alert(self, rule_id, device, target):
        r = self.conn.execute(
            "SELECT * FROM alerts WHERE rule_id=? AND device=? AND target=? AND state='firing' "
            "ORDER BY id DESC LIMIT 1", (rule_id, device, target)).fetchone()
        return dict(r) if r else None

    def open_alert(self, rule_id, rule_name, device, target, metric, severity, message):
        import time
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO alerts (rule_id, rule_name, device, target, metric, severity, "
            "message, state, first_ts, last_ts) VALUES (?,?,?,?,?,?,?, 'firing', ?, ?)",
            (rule_id, rule_name, device, target, metric, severity, message, now, now))
        self.conn.commit()
        return cur.lastrowid

    def touch_alert(self, alert_id):
        import time
        self.conn.execute("UPDATE alerts SET last_ts=? WHERE id=?", (time.time(), alert_id))
        self.conn.commit()

    def resolve_alert(self, alert_id):
        import time
        self.conn.execute("UPDATE alerts SET state='resolved', last_ts=? WHERE id=?",
                          (time.time(), alert_id))
        self.conn.commit()

    def alerts(self, state=None, limit=200):
        q = "SELECT * FROM alerts"
        args = []
        if state:
            q += " WHERE state=?"; args.append(state)
        q += " ORDER BY last_ts DESC LIMIT ?"; args.append(limit)
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def set_arp(self, device, entries):
        import time
        now = time.time()
        self.conn.execute("DELETE FROM arp_entries WHERE device=?", (device,))
        for e in entries:
            self.conn.execute(
                "INSERT OR REPLACE INTO arp_entries (device, ip, mac, ifindex, ts) "
                "VALUES (?,?,?,?,?)", (device, e.get("ip", ""), e.get("mac", ""),
                                       e.get("ifindex", ""), now))
        self.conn.commit()

    def get_arp(self, device):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM arp_entries WHERE device=? ORDER BY ip", (device,)).fetchall()]

    def set_mac_table(self, device, entries):
        import time
        now = time.time()
        self.conn.execute("DELETE FROM mac_table WHERE device=?", (device,))
        for e in entries:
            self.conn.execute(
                "INSERT OR REPLACE INTO mac_table (device, mac, port, ifindex, ifdescr, ts) "
                "VALUES (?,?,?,?,?,?)", (device, e.get("mac", ""), e.get("port", ""),
                                        e.get("ifindex", ""), e.get("ifdescr", ""), now))
        self.conn.commit()

    def get_mac_table(self, device):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM mac_table WHERE device=? ORDER BY ifdescr, mac", (device,)).fetchall()]

    def close(self):
        self.conn.close()
