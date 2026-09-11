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

-- ---- Network Intelligence: modern IP neighbour + VLAN-aware FDB -----------
CREATE TABLE IF NOT EXISTS ip_neighbors (
    device TEXT NOT NULL, ip TEXT NOT NULL, address_family TEXT NOT NULL DEFAULT '',
    mac TEXT NOT NULL, ifindex TEXT NOT NULL DEFAULT '', ifdescr TEXT NOT NULL DEFAULT '',
    neighbor_type TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '', ts REAL,
    PRIMARY KEY (device, ip, ifindex, mac)
);
CREATE INDEX IF NOT EXISTS idx_ip_neighbors_mac ON ip_neighbors(mac, ts);
CREATE TABLE IF NOT EXISTS vlan_fdb (
    device TEXT NOT NULL, vlan_id TEXT NOT NULL DEFAULT '', fdb_id TEXT NOT NULL DEFAULT '',
    mac TEXT NOT NULL, bridge_port TEXT NOT NULL DEFAULT '', ifindex TEXT NOT NULL DEFAULT '',
    ifdescr TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '', ts REAL,
    PRIMARY KEY (device, fdb_id, mac, ifindex, bridge_port)
);
CREATE INDEX IF NOT EXISTS idx_vlan_fdb_mac ON vlan_fdb(mac, ts);
CREATE INDEX IF NOT EXISTS idx_vlan_fdb_vlan ON vlan_fdb(device, vlan_id, ts);

-- ---- uploaded-MIB-driven vendor values ------------------------------------
CREATE TABLE IF NOT EXISTS mib_values (
    device     TEXT NOT NULL,
    oid        TEXT NOT NULL,
    name       TEXT NOT NULL DEFAULT '',
    value      TEXT NOT NULL DEFAULT '',
    mib_source TEXT NOT NULL DEFAULT '',
    ts         REAL,
    PRIMARY KEY (device, oid)
);
CREATE INDEX IF NOT EXISTS idx_mib_values_device ON mib_values(device, mib_source, name);

-- ---- topology / event-driven collection / API -----------------------------
CREATE TABLE IF NOT EXISTS l2_neighbors (
    device TEXT NOT NULL, protocol TEXT NOT NULL, local_port TEXT NOT NULL DEFAULT '',
    local_port_num TEXT NOT NULL DEFAULT '', neighbor_device TEXT NOT NULL DEFAULT '',
    sys_name TEXT NOT NULL DEFAULT '', chassis_id TEXT NOT NULL DEFAULT '',
    port_id TEXT NOT NULL DEFAULT '', port_desc TEXT NOT NULL DEFAULT '',
    sys_desc TEXT NOT NULL DEFAULT '', managed_neighbor INTEGER NOT NULL DEFAULT 0,
    ts REAL, PRIMARY KEY(device, protocol, local_port, sys_name, chassis_id, port_id)
);
CREATE INDEX IF NOT EXISTS idx_l2_neighbors_device ON l2_neighbors(device, ts);

-- ---- Network Intelligence NI-2: normalized topology identity ---------------
CREATE TABLE IF NOT EXISTS topology_device_identity (
    device TEXT PRIMARY KEY, sys_name TEXT NOT NULL DEFAULT '',
    chassis_id TEXT NOT NULL DEFAULT '', chassis_id_subtype TEXT NOT NULL DEFAULT '',
    chassis_mac TEXT NOT NULL DEFAULT '', chassis_serial TEXT NOT NULL DEFAULT '',
    chassis_name TEXT NOT NULL DEFAULT '', chassis_model TEXT NOT NULL DEFAULT '',
    sys_cap_supported TEXT NOT NULL DEFAULT '', sys_cap_enabled TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '', ts REAL
);
CREATE INDEX IF NOT EXISTS idx_topology_identity_chassis ON topology_device_identity(chassis_id, chassis_mac, chassis_serial);
CREATE TABLE IF NOT EXISTS topology_interface_identity (
    device TEXT NOT NULL, ifindex TEXT NOT NULL, ifname TEXT NOT NULL DEFAULT '',
    ifdescr TEXT NOT NULL DEFAULT '', ifalias TEXT NOT NULL DEFAULT '',
    phys_address TEXT NOT NULL DEFAULT '', ts REAL,
    PRIMARY KEY(device, ifindex)
);
CREATE INDEX IF NOT EXISTS idx_topology_interface_name ON topology_interface_identity(device, ifname);

-- ---- Network Intelligence NI-3: operational events + dependency suppression ---
CREATE TABLE IF NOT EXISTS operational_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_ts REAL NOT NULL, last_ts REAL NOT NULL, event_count INTEGER NOT NULL DEFAULT 1,
    source_type TEXT NOT NULL, source TEXT NOT NULL DEFAULT '', device TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL, severity TEXT NOT NULL DEFAULT 'INFO',
    interface TEXT NOT NULL DEFAULT '', ifindex TEXT NOT NULL DEFAULT '', trap_oid TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL DEFAULT '', dedup_key TEXT NOT NULL,
    suppressed INTEGER NOT NULL DEFAULT 0, suppression_id INTEGER, metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_operational_events_time ON operational_events(last_ts DESC);
CREATE INDEX IF NOT EXISTS idx_operational_events_device ON operational_events(device, last_ts DESC);
CREATE INDEX IF NOT EXISTS idx_operational_events_dedup ON operational_events(dedup_key, last_ts DESC);
CREATE TABLE IF NOT EXISTS operational_suppressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, created_ts REAL NOT NULL, expires_ts REAL NOT NULL,
    active INTEGER NOT NULL DEFAULT 1, root_device TEXT NOT NULL, root_port TEXT NOT NULL DEFAULT '',
    target_device TEXT NOT NULL, parent_event_id INTEGER NOT NULL, reason TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_operational_suppression_target ON operational_suppressions(target_device, active, expires_ts);
CREATE INDEX IF NOT EXISTS idx_operational_suppression_root ON operational_suppressions(root_device, root_port, active);

-- ---- Network Intelligence NI-4: operational alert/report lifecycle --------
CREATE TABLE IF NOT EXISTS operational_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'OPEN', severity TEXT NOT NULL DEFAULT 'WARNING',
    device TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '',
    first_ts REAL NOT NULL, last_ts REAL NOT NULL, event_count INTEGER NOT NULL DEFAULT 1,
    acknowledged_by TEXT NOT NULL DEFAULT '', acknowledged_ts REAL, acknowledge_note TEXT NOT NULL DEFAULT '',
    resolved_by TEXT NOT NULL DEFAULT '', resolved_ts REAL, resolution_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_operational_alert_state ON operational_alerts(state, last_ts DESC);
CREATE INDEX IF NOT EXISTS idx_operational_alert_device ON operational_alerts(device, state, last_ts DESC);
CREATE TABLE IF NOT EXISTS maintenance_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, device TEXT NOT NULL DEFAULT '',
    start_ts REAL NOT NULL, end_ts REAL NOT NULL, reason TEXT NOT NULL DEFAULT '',
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL,
    cancelled_by TEXT NOT NULL DEFAULT '', cancelled_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_maintenance_active ON maintenance_windows(device, start_ts, end_ts, cancelled_ts);
CREATE TABLE IF NOT EXISTS notification_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, alert_id INTEGER, report_run_id INTEGER,
    state TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
    created_ts REAL NOT NULL, next_attempt_ts REAL NOT NULL, last_attempt_ts REAL, sent_ts REAL,
    last_error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_notification_due ON notification_deliveries(state, next_attempt_ts);
CREATE TABLE IF NOT EXISTS report_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    interval_seconds INTEGER NOT NULL, lookback_hours INTEGER NOT NULL DEFAULT 24, next_run_ts REAL NOT NULL,
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_by TEXT NOT NULL DEFAULT '', updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_report_schedule_due ON report_schedules(enabled, next_run_ts);
CREATE TABLE IF NOT EXISTS report_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, schedule_id INTEGER, started_ts REAL NOT NULL, finished_ts REAL NOT NULL,
    status TEXT NOT NULL, lookback_start_ts REAL NOT NULL, lookback_end_ts REAL NOT NULL,
    summary TEXT NOT NULL DEFAULT '{}', delivery_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_report_runs_time ON report_runs(finished_ts DESC);
CREATE TABLE IF NOT EXISTS syslog_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, source TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_syslog_events_ts ON syslog_events(ts);
CREATE TABLE IF NOT EXISTS api_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE, scopes TEXT NOT NULL DEFAULT '[]', role TEXT NOT NULL DEFAULT 'viewer',
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL, last_used_ts REAL,
    disabled INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS digest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, ok INTEGER NOT NULL,
    message TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '{}'
);

-- ---- D.5/4A incident model -------------------------------------------------
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    severity TEXT NOT NULL DEFAULT 'MEDIUM',
    status TEXT NOT NULL DEFAULT 'OPEN',
    tags TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_ts REAL NOT NULL,
    closed_by TEXT,
    closed_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status, created_ts);
CREATE INDEX IF NOT EXISTS idx_incidents_severity ON incidents(severity, created_ts);
CREATE TABLE IF NOT EXISTS incident_bundles (
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    bundle_name TEXT NOT NULL,
    linked_by TEXT NOT NULL DEFAULT '',
    linked_ts REAL NOT NULL,
    PRIMARY KEY (incident_id, bundle_name)
);
CREATE INDEX IF NOT EXISTS idx_incident_bundles_name ON incident_bundles(bundle_name);
CREATE TABLE IF NOT EXISTS incident_evidence_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    linked_by TEXT NOT NULL DEFAULT '',
    linked_ts REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(incident_id, source_type, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_incident_evidence_incident
    ON incident_evidence_links(incident_id, linked_ts);
CREATE INDEX IF NOT EXISTS idx_incident_evidence_source
    ON incident_evidence_links(source_type, source_ref);

-- ---- D.5/4C support-case exports ------------------------------------------
CREATE TABLE IF NOT EXISTS incident_case_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    export_key TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    bundle_names TEXT NOT NULL DEFAULT '[]',
    missing_bundles TEXT NOT NULL DEFAULT '[]',
    bundle_count INTEGER NOT NULL DEFAULT 0,
    size INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    signature_state TEXT NOT NULL DEFAULT 'UNSIGNED',
    signature_algorithm TEXT NOT NULL DEFAULT '',
    signer_fingerprint TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_incident_case_exports_incident
    ON incident_case_exports(incident_id, created_ts);

-- ---- D.5/4E bounded protocol trace evidence --------------------------------
CREATE TABLE IF NOT EXISTS protocol_trace_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_key TEXT NOT NULL UNIQUE,
    device TEXT NOT NULL DEFAULT '',
    protocol TEXT NOT NULL,
    incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_by TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    expires_ts REAL NOT NULL,
    stopped_by TEXT NOT NULL DEFAULT '',
    stopped_ts REAL,
    reason TEXT NOT NULL DEFAULT '',
    max_events INTEGER NOT NULL DEFAULT 500,
    max_bytes INTEGER NOT NULL DEFAULT 1048576,
    event_count INTEGER NOT NULL DEFAULT 0,
    bytes_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_protocol_trace_active
    ON protocol_trace_sessions(device, protocol, status, expires_ts);
CREATE INDEX IF NOT EXISTS idx_protocol_trace_incident
    ON protocol_trace_sessions(incident_id, created_ts);
CREATE TABLE IF NOT EXISTS protocol_trace_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES protocol_trace_sessions(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    ts REAL NOT NULL,
    event_type TEXT NOT NULL,
    operation TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    duration_ms REAL,
    tx_bytes INTEGER NOT NULL DEFAULT 0,
    rx_bytes INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(session_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_protocol_trace_events_session
    ON protocol_trace_events(session_id, seq);

CREATE TABLE IF NOT EXISTS mib_poll_status (
    device  TEXT PRIMARY KEY,
    ts      REAL,
    objects INTEGER NOT NULL DEFAULT 0,
    roots   INTEGER NOT NULL DEFAULT 0,
    error   TEXT NOT NULL DEFAULT ''
);

-- ---- Platform Hardening PH-2: storage / distributed coordination ---------
CREATE TABLE IF NOT EXISTS storage_meta (
    key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '', updated_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cluster_nodes (
    node_id TEXT PRIMARY KEY, hostname TEXT NOT NULL DEFAULT '', pid INTEGER NOT NULL DEFAULT 0,
    started_ts REAL NOT NULL, last_heartbeat_ts REAL NOT NULL, role TEXT NOT NULL DEFAULT 'control-plane'
);
CREATE INDEX IF NOT EXISTS idx_cluster_nodes_heartbeat ON cluster_nodes(last_heartbeat_ts);
CREATE TABLE IF NOT EXISTS distributed_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, queue TEXT NOT NULL DEFAULT 'default',
    kind TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'PENDING',
    available_ts REAL NOT NULL, claimed_by TEXT NOT NULL DEFAULT '', claim_ts REAL, lease_until REAL,
    attempts INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL, updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_distributed_tasks_claim
    ON distributed_tasks(queue, state, available_ts, lease_until, id);

-- ---- Platform Hardening PH-3: structured protocol profiles ----------------
CREATE TABLE IF NOT EXISTS protocol_profiles (
    device TEXT PRIMARY KEY, protocol TEXT NOT NULL DEFAULT 'cli_ssh',
    enabled INTEGER NOT NULL DEFAULT 1, port INTEGER NOT NULL DEFAULT 0,
    path TEXT NOT NULL DEFAULT '', secret_ref TEXT NOT NULL DEFAULT '',
    tls_verify INTEGER NOT NULL DEFAULT 1, ca_file TEXT NOT NULL DEFAULT '',
    allow_cli_fallback INTEGER NOT NULL DEFAULT 0, updated_ts REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_protocol_profiles_protocol
    ON protocol_profiles(protocol, enabled, device);
"""

# Additive column migrations: (table, column, coldef). Applied only if absent.
_MIGRATIONS = [
    ("devices", "snmp_version", "TEXT NOT NULL DEFAULT ''"),   # '', v2c, v3
    ("devices", "snmp_ref", "TEXT"),                            # vault entry
    ("devices", "device_type", "TEXT NOT NULL DEFAULT 'network'"),  # system|network|application
    ("devices", "netflow", "INTEGER NOT NULL DEFAULT 0"),      # collect NetFlow (network devices)
    ("devices", "monitor_ports", "TEXT NOT NULL DEFAULT ''"),  # tcp/udp ports (system devices)
    ("devices", "monitor_urls", "TEXT NOT NULL DEFAULT ''"),   # http(s) endpoints (application devices)
    ("api_tokens", "role", "TEXT NOT NULL DEFAULT 'viewer'"),
    ("incident_case_exports", "signature_state", "TEXT NOT NULL DEFAULT 'UNSIGNED'"),
    ("incident_case_exports", "signature_algorithm", "TEXT NOT NULL DEFAULT ''"),
    ("incident_case_exports", "signer_fingerprint", "TEXT NOT NULL DEFAULT ''"),
    ("l2_neighbors", "chassis_id_subtype", "TEXT NOT NULL DEFAULT ''"),
    ("l2_neighbors", "port_id_subtype", "TEXT NOT NULL DEFAULT ''"),
    ("l2_neighbors", "sys_cap_supported", "TEXT NOT NULL DEFAULT ''"),
    ("l2_neighbors", "sys_cap_enabled", "TEXT NOT NULL DEFAULT ''"),
    ("l2_neighbors", "resolution_state", "TEXT NOT NULL DEFAULT ''"),
    ("l2_neighbors", "resolution_evidence", "TEXT NOT NULL DEFAULT ''"),
    ("operational_events", "alert_id", "INTEGER"),
    ("operational_events", "maintenance_window_id", "INTEGER"),
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
    dialect = "sqlite"
    distributed_capable = False
    schema_revision = "ph3-1"

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
        self._stamp_schema_revision()

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

    def set_ip_neighbors(self, device, entries):
        import time
        now = time.time()
        self.conn.execute("DELETE FROM ip_neighbors WHERE device=?", (device,))
        for e in entries:
            self.conn.execute(
                "INSERT OR REPLACE INTO ip_neighbors "
                "(device,ip,address_family,mac,ifindex,ifdescr,neighbor_type,state,source,ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (device, e.get("ip", ""), e.get("address_family", ""), e.get("mac", ""),
                 e.get("ifindex", ""), e.get("ifdescr", ""), e.get("neighbor_type", ""),
                 e.get("state", ""), e.get("source", ""), now))
        self.conn.commit()

    def get_ip_neighbors(self, device=None):
        if device:
            rows = self.conn.execute(
                "SELECT * FROM ip_neighbors WHERE device=? ORDER BY ip,ifindex", (device,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM ip_neighbors ORDER BY device,ip,ifindex").fetchall()
        return [dict(r) for r in rows]

    def set_vlan_fdb(self, device, entries):
        import time
        now = time.time()
        self.conn.execute("DELETE FROM vlan_fdb WHERE device=?", (device,))
        for e in entries:
            self.conn.execute(
                "INSERT OR REPLACE INTO vlan_fdb "
                "(device,vlan_id,fdb_id,mac,bridge_port,ifindex,ifdescr,status,source,ts) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (device, str(e.get("vlan_id", "") or ""), str(e.get("fdb_id", "") or ""),
                 e.get("mac", ""), str(e.get("bridge_port", "") or ""),
                 str(e.get("ifindex", "") or ""), e.get("ifdescr", ""),
                 e.get("status", ""), e.get("source", ""), now))
        self.conn.commit()

    def get_vlan_fdb(self, device=None):
        if device:
            rows = self.conn.execute(
                "SELECT * FROM vlan_fdb WHERE device=? ORDER BY vlan_id,ifdescr,mac", (device,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM vlan_fdb ORDER BY device,vlan_id,ifdescr,mac").fetchall()
        return [dict(r) for r in rows]

    def set_neighbors(self, device, entries):
        import time
        now = time.time()
        self.conn.execute("DELETE FROM l2_neighbors WHERE device=?", (device,))
        for e in entries:
            self.conn.execute(
                "INSERT OR REPLACE INTO l2_neighbors "
                "(device,protocol,local_port,local_port_num,neighbor_device,sys_name,chassis_id,port_id,port_desc,sys_desc,managed_neighbor,ts,"
                "chassis_id_subtype,port_id_subtype,sys_cap_supported,sys_cap_enabled,resolution_state,resolution_evidence) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (device, e.get("protocol",""), e.get("local_port",""), e.get("local_port_num",""),
                 e.get("neighbor_device",""), e.get("sys_name",""), e.get("chassis_id",""),
                 e.get("port_id",""), e.get("port_desc",""), e.get("sys_desc",""),
                 1 if e.get("managed_neighbor") else 0, now, e.get("chassis_id_subtype",""),
                 e.get("port_id_subtype",""), e.get("sys_cap_supported",""), e.get("sys_cap_enabled",""),
                 e.get("resolution_state",""), e.get("resolution_evidence","")))
        self.conn.commit()

    def get_neighbors(self, device=None):
        if device:
            rows = self.conn.execute("SELECT * FROM l2_neighbors WHERE device=? ORDER BY local_port,sys_name", (device,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM l2_neighbors ORDER BY device,local_port,sys_name").fetchall()
        return [dict(r) for r in rows]

    def set_topology_device_identity(self, device, identity):
        import time
        row = dict(identity or {})
        now = time.time()
        self.conn.execute(
            "INSERT OR REPLACE INTO topology_device_identity "
            "(device,sys_name,chassis_id,chassis_id_subtype,chassis_mac,chassis_serial,chassis_name,chassis_model,sys_cap_supported,sys_cap_enabled,source,ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (device, row.get("sys_name", ""), row.get("chassis_id", ""), row.get("chassis_id_subtype", ""),
             row.get("chassis_mac", ""), row.get("chassis_serial", ""), row.get("chassis_name", ""),
             row.get("chassis_model", ""), row.get("sys_cap_supported", ""), row.get("sys_cap_enabled", ""),
             row.get("source", "SNMP"), now))
        self.conn.commit()

    def get_topology_device_identities(self, device=None):
        if device:
            rows = self.conn.execute("SELECT * FROM topology_device_identity WHERE device=?", (device,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM topology_device_identity ORDER BY device").fetchall()
        return [dict(r) for r in rows]

    def set_topology_interfaces(self, device, rows):
        import time
        now = time.time()
        self.conn.execute("DELETE FROM topology_interface_identity WHERE device=?", (device,))
        for row in rows or []:
            self.conn.execute(
                "INSERT OR REPLACE INTO topology_interface_identity "
                "(device,ifindex,ifname,ifdescr,ifalias,phys_address,ts) VALUES (?,?,?,?,?,?,?)",
                (device, str(row.get("ifindex", "")), row.get("name", ""), row.get("descr", ""),
                 row.get("alias", ""), row.get("phys", ""), now))
        self.conn.commit()

    def get_topology_interfaces(self, device=None):
        if device:
            rows = self.conn.execute("SELECT * FROM topology_interface_identity WHERE device=? ORDER BY ifindex", (device,)).fetchall()
        else:
            rows = self.conn.execute("SELECT * FROM topology_interface_identity ORDER BY device,ifindex").fetchall()
        return [dict(r) for r in rows]

    def record_syslog(self, source, message):
        import time
        self.conn.execute("INSERT INTO syslog_events(ts,source,message) VALUES (?,?,?)", (time.time(), source, message[:8192]))
        self.conn.commit()

    def recent_syslog(self, limit=200):
        return [dict(r) for r in self.conn.execute("SELECT * FROM syslog_events ORDER BY ts DESC LIMIT ?", (int(limit),)).fetchall()]

    def record_digest(self, ok, message, summary):
        import time
        self.conn.execute("INSERT INTO digest_runs(ts,ok,message,summary) VALUES (?,?,?,?)", (time.time(), 1 if ok else 0, message, summary))
        self.conn.commit()

    def latest_digest(self):
        r = self.conn.execute("SELECT * FROM digest_runs ORDER BY ts DESC LIMIT 1").fetchone()
        return dict(r) if r else None

    def set_mib_values(self, device, entries, roots=0, error=""):
        import time
        now = time.time()
        lock = getattr(self.conn, "lock", None)
        if lock:
            lock.acquire()
        try:
            self.conn.execute("DELETE FROM mib_values WHERE device=?", (device,))
            for entry in entries:
                self.conn.execute(
                    "INSERT OR REPLACE INTO mib_values "
                    "(device, oid, name, value, mib_source, ts) VALUES (?,?,?,?,?,?)",
                    (device, entry.get("oid", ""), entry.get("name", ""),
                     str(entry.get("value", "")), entry.get("mib_source", ""), now))
            self.conn.execute(
                "INSERT OR REPLACE INTO mib_poll_status (device, ts, objects, roots, error) "
                "VALUES (?,?,?,?,?)", (device, now, len(entries), int(roots), error or ""))
            self.conn.commit()
        finally:
            if lock:
                lock.release()

    def get_mib_values(self, device, limit=800):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM mib_values WHERE device=? "
            "ORDER BY mib_source, name, oid LIMIT ?", (device, int(limit))).fetchall()]

    def get_mib_poll_status(self, device):
        row = self.conn.execute(
            "SELECT * FROM mib_poll_status WHERE device=?", (device,)).fetchone()
        return dict(row) if row else None

    # ---- NI-3 operational event stream -------------------------------------
    def find_recent_operational_event(self, dedup_key, since_ts):
        row = self.conn.execute(
            "SELECT * FROM operational_events WHERE dedup_key=? AND last_ts>=? ORDER BY last_ts DESC LIMIT 1",
            (dedup_key, float(since_ts))).fetchone()
        return dict(row) if row else None

    def insert_operational_event(self, ts, source_type, source, device, event_type, severity,
                                 interface, ifindex, trap_oid, message, dedup_key, suppressed,
                                 suppression_id, metadata):
        cur = self.conn.execute(
            "INSERT INTO operational_events "
            "(first_ts,last_ts,event_count,source_type,source,device,event_type,severity,interface,ifindex,trap_oid,message,dedup_key,suppressed,suppression_id,metadata) "
            "VALUES (?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (float(ts), float(ts), source_type, source, device, event_type, severity, interface, ifindex, trap_oid,
             message, dedup_key, int(bool(suppressed)), suppression_id, metadata))
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM operational_events WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def touch_operational_event(self, event_id, ts):
        self.conn.execute("UPDATE operational_events SET last_ts=?, event_count=event_count+1 WHERE id=?",
                          (float(ts), int(event_id)))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM operational_events WHERE id=?", (int(event_id),)).fetchone())

    def operational_events(self, limit=200, device=None, include_suppressed=True):
        q = "SELECT * FROM operational_events"; args=[]; where=[]
        if device: where.append("device=?"); args.append(device)
        if not include_suppressed: where.append("suppressed=0")
        if where: q += " WHERE " + " AND ".join(where)
        q += " ORDER BY last_ts DESC LIMIT ?"; args.append(max(1,min(int(limit),2000)))
        return [dict(r) for r in self.conn.execute(q,args).fetchall()]

    def add_operational_suppression(self, created_ts, expires_ts, root_device, root_port, target_device, parent_event_id, reason):
        row = self.conn.execute(
            "SELECT * FROM operational_suppressions WHERE active=1 AND root_device=? AND root_port=? AND target_device=? AND parent_event_id=?",
            (root_device, root_port, target_device, int(parent_event_id))).fetchone()
        if row:
            self.conn.execute("UPDATE operational_suppressions SET expires_ts=? WHERE id=?", (float(expires_ts), row["id"])); self.conn.commit()
            return dict(self.conn.execute("SELECT * FROM operational_suppressions WHERE id=?",(row["id"],)).fetchone())
        cur=self.conn.execute(
            "INSERT INTO operational_suppressions(created_ts,expires_ts,active,root_device,root_port,target_device,parent_event_id,reason) VALUES (?,?,1,?,?,?,?,?)",
            (float(created_ts),float(expires_ts),root_device,root_port,target_device,int(parent_event_id),reason))
        self.conn.commit(); return dict(self.conn.execute("SELECT * FROM operational_suppressions WHERE id=?",(cur.lastrowid,)).fetchone())

    def expire_operational_suppressions(self, now):
        cur=self.conn.execute("UPDATE operational_suppressions SET active=0 WHERE active=1 AND expires_ts<=?",(float(now),)); self.conn.commit(); return cur.rowcount

    def active_operational_suppressions(self, target_device, now):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM operational_suppressions WHERE target_device=? AND active=1 AND expires_ts>? ORDER BY created_ts DESC",
            (target_device,float(now))).fetchall()]

    def clear_operational_suppressions(self, root_device, root_port, now):
        if root_port:
            cur=self.conn.execute("UPDATE operational_suppressions SET active=0, expires_ts=? WHERE active=1 AND root_device=? AND root_port=?",
                                  (float(now),root_device,root_port))
        else:
            cur=self.conn.execute("UPDATE operational_suppressions SET active=0, expires_ts=? WHERE active=1 AND root_device=?",
                                  (float(now),root_device))
        self.conn.commit(); return cur.rowcount

    def operational_suppressions(self, active_only=True, now=None):
        q="SELECT * FROM operational_suppressions"; args=[]
        if active_only:
            q += " WHERE active=1"
            if now is not None: q += " AND expires_ts>?"; args.append(float(now))
        q += " ORDER BY created_ts DESC"
        return [dict(r) for r in self.conn.execute(q,args).fetchall()]

    # ---- NI-4 operational alert lifecycle --------------------------------
    def set_operational_event_lifecycle_refs(self, event_id, alert_id=None, maintenance_window_id=None):
        self.conn.execute("UPDATE operational_events SET alert_id=?, maintenance_window_id=? WHERE id=?",
                          (alert_id, maintenance_window_id, int(event_id)))
        self.conn.commit()

    def operational_alert_for_event(self, event_id):
        row=self.conn.execute("SELECT * FROM operational_alerts WHERE event_id=?",(int(event_id),)).fetchone()
        return dict(row) if row else None

    def create_operational_alert(self, event):
        cur=self.conn.execute(
            "INSERT INTO operational_alerts(event_id,state,severity,device,event_type,message,first_ts,last_ts,event_count) VALUES(?, 'OPEN', ?,?,?,?,?,?,?)",
            (int(event["id"]), event.get("severity") or "WARNING", event.get("device") or "",
             event.get("event_type") or "", event.get("message") or "", float(event.get("first_ts") or event.get("last_ts") or 0),
             float(event.get("last_ts") or event.get("first_ts") or 0), int(event.get("event_count") or 1)))
        self.conn.commit(); return self.get_operational_alert(cur.lastrowid)

    def touch_operational_alert(self, alert_id, event):
        self.conn.execute("UPDATE operational_alerts SET last_ts=?, event_count=? WHERE id=?",
                          (float(event.get("last_ts") or 0), int(event.get("event_count") or 1), int(alert_id)))
        self.conn.commit(); return self.get_operational_alert(alert_id)

    def get_operational_alert(self, alert_id):
        row=self.conn.execute("SELECT * FROM operational_alerts WHERE id=?",(int(alert_id),)).fetchone()
        return dict(row) if row else None

    def list_operational_alerts(self, state=None, device=None, limit=200):
        q="SELECT * FROM operational_alerts"; args=[]; where=[]
        if state: where.append("state=?"); args.append(state)
        if device: where.append("device=?"); args.append(device)
        if where: q += " WHERE " + " AND ".join(where)
        q += " ORDER BY last_ts DESC LIMIT ?"; args.append(int(limit))
        return [dict(r) for r in self.conn.execute(q,args).fetchall()]

    def update_operational_alert_state(self, alert_id, state, actor, note, now):
        if state == "ACKNOWLEDGED":
            self.conn.execute("UPDATE operational_alerts SET state=?, acknowledged_by=?, acknowledged_ts=?, acknowledge_note=? WHERE id=?",
                              (state, actor, float(now), note, int(alert_id)))
        elif state == "RESOLVED":
            self.conn.execute("UPDATE operational_alerts SET state=?, resolved_by=?, resolved_ts=?, resolution_note=? WHERE id=?",
                              (state, actor, float(now), note, int(alert_id)))
        else: raise ValueError("invalid operational alert state")
        self.conn.commit(); return self.get_operational_alert(alert_id)

    def add_maintenance_window(self, name, device, start_ts, end_ts, reason, actor, now):
        cur=self.conn.execute("INSERT INTO maintenance_windows(name,device,start_ts,end_ts,reason,created_by,created_ts) VALUES(?,?,?,?,?,?,?)",
                              (name,device,float(start_ts),float(end_ts),reason,actor,float(now)))
        self.conn.commit(); return dict(self.conn.execute("SELECT * FROM maintenance_windows WHERE id=?",(cur.lastrowid,)).fetchone())

    def active_maintenance_window(self, device, now):
        row=self.conn.execute("SELECT * FROM maintenance_windows WHERE cancelled_ts IS NULL AND start_ts<=? AND end_ts>? AND (device='' OR device=?) ORDER BY CASE WHEN device=? THEN 0 ELSE 1 END, start_ts DESC LIMIT 1",
                              (float(now),float(now),device,device)).fetchone()
        return dict(row) if row else None

    def list_maintenance_windows(self, active_only=False, now=None):
        q="SELECT * FROM maintenance_windows"; args=[]
        if active_only:
            now=float(now if now is not None else __import__('time').time())
            q += " WHERE cancelled_ts IS NULL AND start_ts<=? AND end_ts>?"; args += [now,now]
        q += " ORDER BY start_ts DESC"
        return [dict(r) for r in self.conn.execute(q,args).fetchall()]

    def cancel_maintenance_window(self, window_id, actor, now):
        self.conn.execute("UPDATE maintenance_windows SET cancelled_by=?, cancelled_ts=? WHERE id=? AND cancelled_ts IS NULL",
                          (actor,float(now),int(window_id))); self.conn.commit()
        row=self.conn.execute("SELECT * FROM maintenance_windows WHERE id=?",(int(window_id),)).fetchone()
        return dict(row) if row else None

    def enqueue_notification(self, kind, now, alert_id=None, report_run_id=None):
        cur=self.conn.execute("INSERT INTO notification_deliveries(kind,alert_id,report_run_id,state,attempts,created_ts,next_attempt_ts) VALUES(?,?,?,'PENDING',0,?,?)",
                              (kind,alert_id,report_run_id,float(now),float(now)))
        self.conn.commit(); return dict(self.conn.execute("SELECT * FROM notification_deliveries WHERE id=?",(cur.lastrowid,)).fetchone())

    def due_notifications(self, now, limit=50):
        return [dict(r) for r in self.conn.execute("SELECT * FROM notification_deliveries WHERE state IN ('PENDING','RETRY') AND next_attempt_ts<=? ORDER BY id LIMIT ?",
                                                   (float(now),int(limit))).fetchall()]

    def update_notification(self, delivery_id, state, attempts, now, next_attempt_ts=None, error=""):
        sent=float(now) if state=='SENT' else None
        self.conn.execute("UPDATE notification_deliveries SET state=?, attempts=?, last_attempt_ts=?, next_attempt_ts=?, sent_ts=?, last_error=? WHERE id=?",
                          (state,int(attempts),float(now),float(next_attempt_ts if next_attempt_ts is not None else now),sent,error,int(delivery_id)))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM notification_deliveries WHERE id=?",(int(delivery_id),)).fetchone())

    def list_notifications(self, limit=100):
        return [dict(r) for r in self.conn.execute("SELECT * FROM notification_deliveries ORDER BY id DESC LIMIT ?",(int(limit),)).fetchall()]

    def add_report_schedule(self, name, interval_seconds, lookback_hours, next_run_ts, actor, now):
        cur=self.conn.execute("INSERT INTO report_schedules(name,enabled,interval_seconds,lookback_hours,next_run_ts,created_by,created_ts,updated_by,updated_ts) VALUES(?,1,?,?,?,?,?,?,?)",
                              (name,int(interval_seconds),int(lookback_hours),float(next_run_ts),actor,float(now),actor,float(now)))
        self.conn.commit(); return dict(self.conn.execute("SELECT * FROM report_schedules WHERE id=?",(cur.lastrowid,)).fetchone())

    def list_report_schedules(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM report_schedules ORDER BY id").fetchall()]

    def due_report_schedules(self, now):
        return [dict(r) for r in self.conn.execute("SELECT * FROM report_schedules WHERE enabled=1 AND next_run_ts<=? ORDER BY next_run_ts,id",(float(now),)).fetchall()]

    def update_report_schedule_next(self, schedule_id, next_run_ts, actor, now):
        self.conn.execute("UPDATE report_schedules SET next_run_ts=?, updated_by=?, updated_ts=? WHERE id=?",
                          (float(next_run_ts),actor,float(now),int(schedule_id))); self.conn.commit()

    def set_report_schedule_enabled(self, schedule_id, enabled, actor, now):
        self.conn.execute("UPDATE report_schedules SET enabled=?, updated_by=?, updated_ts=? WHERE id=?",
                          (1 if enabled else 0,actor,float(now),int(schedule_id))); self.conn.commit()

    def create_report_run(self, schedule_id, started_ts, finished_ts, status, lookback_start_ts, lookback_end_ts, summary):
        cur=self.conn.execute("INSERT INTO report_runs(schedule_id,started_ts,finished_ts,status,lookback_start_ts,lookback_end_ts,summary) VALUES(?,?,?,?,?,?,?)",
                              (schedule_id,float(started_ts),float(finished_ts),status,float(lookback_start_ts),float(lookback_end_ts),summary))
        self.conn.commit(); return dict(self.conn.execute("SELECT * FROM report_runs WHERE id=?",(cur.lastrowid,)).fetchone())

    def set_report_delivery(self, run_id, delivery_id):
        self.conn.execute("UPDATE report_runs SET delivery_id=? WHERE id=?",(int(delivery_id),int(run_id))); self.conn.commit()

    def list_report_runs(self, limit=100):
        return [dict(r) for r in self.conn.execute("SELECT * FROM report_runs ORDER BY finished_ts DESC LIMIT ?",(int(limit),)).fetchall()]

    # ---- PH-2 storage / distributed coordination ----------------------
    def _stamp_schema_revision(self):
        import time
        self.conn.execute(
            "INSERT OR REPLACE INTO storage_meta(key,value,updated_ts) VALUES(?,?,?)",
            ("schema_revision", self.schema_revision, time.time()))
        self.conn.commit()

    def storage_status(self):
        row = self.conn.execute(
            "SELECT value,updated_ts FROM storage_meta WHERE key=?",
            ("schema_revision",)).fetchone()
        return {
            "backend": self.dialect,
            "distributed_capable": bool(self.distributed_capable),
            "schema_revision": (row["value"] if row else ""),
            "configured_revision": self.schema_revision,
            "ok": bool(row and row["value"] == self.schema_revision),
        }

    def readiness(self):
        try:
            self.conn.execute("SELECT 1 AS ok").fetchone()
            out = self.storage_status()
            out["reachable"] = True
            return out
        except Exception as exc:
            return {"backend": self.dialect, "distributed_capable": bool(self.distributed_capable),
                    "schema_revision": "", "configured_revision": self.schema_revision,
                    "reachable": False, "ok": False, "error": str(exc)[:300]}

    def register_cluster_node(self, node_id, hostname, pid, now, role="control-plane"):
        # delete+insert is deliberately portable across SQLite/PostgreSQL. The
        # node id is process-unique, so replacing only refreshes our own row.
        self.conn.execute("DELETE FROM cluster_nodes WHERE node_id=?", (node_id,))
        self.conn.execute(
            "INSERT INTO cluster_nodes(node_id,hostname,pid,started_ts,last_heartbeat_ts,role) "
            "VALUES(?,?,?,?,?,?)",
            (node_id, hostname or "", int(pid), float(now), float(now), role or "control-plane"))
        self.conn.commit()

    def heartbeat_cluster_node(self, node_id, now):
        self.conn.execute("UPDATE cluster_nodes SET last_heartbeat_ts=? WHERE node_id=?",
                          (float(now), node_id)); self.conn.commit()

    def list_cluster_nodes(self, since_ts=0):
        rows = self.conn.execute(
            "SELECT * FROM cluster_nodes WHERE last_heartbeat_ts>=? ORDER BY node_id",
            (float(since_ts),)).fetchall()
        return [dict(r) for r in rows]

    def enqueue_distributed_task(self, queue, kind, payload, now, available_ts=None):
        available = float(now if available_ts is None else available_ts)
        cur = self.conn.execute(
            "INSERT INTO distributed_tasks(queue,kind,payload,state,available_ts,created_ts,updated_ts) "
            "VALUES(?,?,?,'PENDING',?,?,?)",
            (queue or "default", kind, payload or "{}", available, float(now), float(now)))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?",
                                      (cur.lastrowid,)).fetchone())

    def claim_distributed_task(self, queue, worker_id, now, lease_seconds=60):
        # SQLite remains a single-node development backend. This process-local
        # lock makes claims atomic among its threads; PostgreSQL overrides this
        # with SELECT ... FOR UPDATE SKIP LOCKED for real multi-node workers.
        lease_until = float(now) + max(5, int(lease_seconds))
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM distributed_tasks WHERE queue=? AND available_ts<=? "
                "AND (state='PENDING' OR (state='CLAIMED' AND lease_until<?)) "
                "ORDER BY id LIMIT 1", (queue or "default", float(now), float(now))).fetchone()
            if not row:
                return None
            attempts = int(row["attempts"] or 0) + 1
            self.conn.execute(
                "UPDATE distributed_tasks SET state='CLAIMED',claimed_by=?,claim_ts=?,lease_until=?,"
                "attempts=?,updated_ts=? WHERE id=?",
                (worker_id, float(now), lease_until, attempts, float(now), int(row["id"])))
            self.conn.commit()
            return dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?",
                                          (int(row["id"]),)).fetchone())

    def finish_distributed_task(self, task_id, worker_id, now, ok=True, result="", error=""):
        state = "DONE" if ok else "FAILED"
        self.conn.execute(
            "UPDATE distributed_tasks SET state=?,result=?,error=?,lease_until=NULL,updated_ts=? "
            "WHERE id=? AND claimed_by=?",
            (state, result or "", error or "", float(now), int(task_id), worker_id))
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone()
        return dict(row) if row else None

    def list_distributed_tasks(self, queue=None, limit=100):
        if queue:
            rows = self.conn.execute(
                "SELECT * FROM distributed_tasks WHERE queue=? ORDER BY id DESC LIMIT ?",
                (queue, int(limit))).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM distributed_tasks ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def try_advisory_lock(self, name):
        # SQLite is intentionally single-node; there is no cross-process HA
        # promise for this backend. Returning True preserves existing behaviour.
        return True

    def advisory_unlock(self, name):
        return True

    def close(self):
        self.conn.close()
