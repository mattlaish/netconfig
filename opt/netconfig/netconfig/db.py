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

import hashlib
import json
import sqlite3
import threading



def operational_alert_correlation_key(event):
    """Return the stable MC-4 alert-condition identity for one event.

    Kept in the DB layer so additive migrations and the runtime alert lifecycle
    use exactly the same derivation. Sensor-backed events correlate by durable
    Sensor key; all other events use a conservative normalized event identity.
    """
    event = event or {}
    raw_meta = event.get("metadata")
    if isinstance(raw_meta, dict):
        meta = dict(raw_meta)
    else:
        try:
            parsed = json.loads(raw_meta or "{}")
        except Exception:
            parsed = {}
        meta = parsed if isinstance(parsed, dict) else {}
    sensor_key = str(meta.get("sensor_key") or "").strip()
    if sensor_key:
        return "sensor:" + sensor_key[:900]
    basis = "\x1f".join([
        str(event.get("domain") or ""), str(event.get("source_type") or ""),
        str(event.get("device") or ""), str(event.get("entity_type") or ""),
        str(event.get("entity_id") or ""), str(event.get("resource") or ""),
        str(event.get("event_type") or ""),
    ])
    return "event:" + hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest()


def backfill_operational_alert_correlation_keys(conn):
    """Backfill R51/early-R52 alerts without changing alert lifecycle state."""
    rows = conn.execute(
        "SELECT a.id AS alert_id,e.* FROM operational_alerts a "
        "JOIN operational_events e ON e.id=a.event_id "
        "WHERE a.correlation_key IS NULL OR a.correlation_key=''"
    ).fetchall()
    for row in rows:
        event = dict(row)
        key = operational_alert_correlation_key(event)
        if key:
            conn.execute(
                "UPDATE operational_alerts SET correlation_key=? WHERE id=?",
                (key, int(event["alert_id"])))
    return len(rows)

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
    config_collect_command TEXT NOT NULL DEFAULT '',
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


-- ---- sensor history (MC-2) -----------------------------------------------
CREATE TABLE IF NOT EXISTS sensor_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_key TEXT NOT NULL DEFAULT '',
    sensor_type TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    resource TEXT NOT NULL DEFAULT '',
    value TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'UNKNOWN',
    message TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    observed_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sensor_observations_device_time
    ON sensor_observations(device, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_observations_key_time
    ON sensor_observations(sensor_key, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_observations_type_time
    ON sensor_observations(sensor_type, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_observations_resource_time
    ON sensor_observations(resource, observed_at);

CREATE TABLE IF NOT EXISTS sensor_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_key TEXT NOT NULL DEFAULT '',
    sensor_type TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    resource TEXT NOT NULL DEFAULT '',
    previous_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    new_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    previous_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    observed_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_sensor_transitions_device_time
    ON sensor_transitions(device, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_transitions_key_time
    ON sensor_transitions(sensor_key, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_transitions_status_time
    ON sensor_transitions(new_status, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_transitions_type_time
    ON sensor_transitions(sensor_type, observed_at);
CREATE INDEX IF NOT EXISTS idx_sensor_transitions_resource_time
    ON sensor_transitions(resource, observed_at);

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
    suppressed INTEGER NOT NULL DEFAULT 0, suppression_id INTEGER, metadata TEXT NOT NULL DEFAULT '{}',
    domain TEXT NOT NULL DEFAULT 'SYSTEM', entity_type TEXT NOT NULL DEFAULT 'unknown',
    entity_id TEXT NOT NULL DEFAULT '', resource TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'OBSERVED', observed_at REAL NOT NULL DEFAULT 0,
    evidence_ref TEXT NOT NULL DEFAULT ''
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
    correlation_key TEXT NOT NULL DEFAULT '', last_event_id INTEGER,
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
    source_ts REAL NOT NULL DEFAULT 0,
    received_ts REAL NOT NULL DEFAULT 0,
    source_clock_json TEXT NOT NULL DEFAULT '{}',
    note TEXT NOT NULL DEFAULT '',
    UNIQUE(incident_id, source_type, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_incident_evidence_incident
    ON incident_evidence_links(incident_id, linked_ts);
CREATE INDEX IF NOT EXISTS idx_incident_evidence_source
    ON incident_evidence_links(source_type, source_ref);

-- ---- MC-5 durable cross-domain evidence -----------------------------------
CREATE TABLE IF NOT EXISTS change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    actor TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    source_ts REAL NOT NULL,
    received_ts REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_change_events_request_time
    ON change_events(request_id, source_ts, id);
CREATE INDEX IF NOT EXISTS idx_change_events_type_time
    ON change_events(event_type, source_ts, id);
CREATE TABLE IF NOT EXISTS external_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT 'EXTERNAL',
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'INFO',
    entity_type TEXT NOT NULL DEFAULT 'unknown',
    entity_id TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    source_ts REAL NOT NULL,
    received_ts REAL NOT NULL,
    source_clock_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    tenant_id TEXT NOT NULL DEFAULT 'default',
    source_key TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '1',
    payload_sha256 TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    ingest_principal TEXT NOT NULL DEFAULT '',
    ingest_result TEXT NOT NULL DEFAULT '',
    connector_type TEXT NOT NULL DEFAULT '',
    UNIQUE(source_system, source_event_id)
);
CREATE INDEX IF NOT EXISTS idx_external_events_source_time
    ON external_events(source_system, source_ts, id);
CREATE INDEX IF NOT EXISTS idx_external_events_domain_time
    ON external_events(domain, source_ts, id);
CREATE TABLE IF NOT EXISTS external_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    source_key TEXT NOT NULL,
    source_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    ingest_token_id INTEGER REFERENCES api_tokens(id) ON DELETE SET NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    auth_mode TEXT NOT NULL DEFAULT 'BEARER',
    schema_version TEXT NOT NULL DEFAULT '1',
    max_payload_bytes INTEGER NOT NULL DEFAULT 65536,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 120,
    created_by TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_ts REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'CONFIGURED',
    auth_state TEXT NOT NULL DEFAULT 'UNVERIFIED',
    last_event_ts REAL NOT NULL DEFAULT 0,
    last_received_ts REAL NOT NULL DEFAULT 0,
    last_rejected_ts REAL NOT NULL DEFAULT 0,
    last_auth_failure_ts REAL NOT NULL DEFAULT 0,
    last_rate_limited_ts REAL NOT NULL DEFAULT 0,
    received_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    auth_failure_count INTEGER NOT NULL DEFAULT 0,
    rate_limited_count INTEGER NOT NULL DEFAULT 0,
    schema_rejection_count INTEGER NOT NULL DEFAULT 0,
    last_error_class TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    UNIQUE(tenant_id, source_key),
    UNIQUE(tenant_id, ingest_token_id)
);
CREATE INDEX IF NOT EXISTS idx_external_sources_type_status
    ON external_sources(tenant_id, source_type, status);
CREATE TABLE IF NOT EXISTS external_ingest_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    source_id INTEGER NOT NULL REFERENCES external_sources(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    event_id INTEGER NOT NULL REFERENCES external_events(id) ON DELETE CASCADE,
    payload_sha256 TEXT NOT NULL,
    received_ts REAL NOT NULL,
    result TEXT NOT NULL,
    UNIQUE(tenant_id, source_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_external_ingest_receipts_event
    ON external_ingest_receipts(event_id);

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
    started_ts REAL NOT NULL, last_heartbeat_ts REAL NOT NULL, role TEXT NOT NULL DEFAULT 'control-plane',
    state TEXT NOT NULL DEFAULT 'ACTIVE', drain_reason TEXT NOT NULL DEFAULT '',
    failure_domain TEXT NOT NULL DEFAULT '', instance_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cluster_nodes_heartbeat ON cluster_nodes(last_heartbeat_ts);
CREATE TABLE IF NOT EXISTS distributed_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT, queue TEXT NOT NULL DEFAULT 'default',
    kind TEXT NOT NULL, payload TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'PENDING',
    available_ts REAL NOT NULL, claimed_by TEXT NOT NULL DEFAULT '', claim_ts REAL, lease_until REAL,
    attempts INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
    claim_generation INTEGER NOT NULL DEFAULT 0, claim_token TEXT NOT NULL DEFAULT '',
    claimed_instance TEXT NOT NULL DEFAULT '', replay_safe INTEGER NOT NULL DEFAULT 0,
    recovery_reason TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_ts REAL NOT NULL
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

-- ---- PH-4: structured configuration transactions ------------------------
CREATE TABLE IF NOT EXISTS structured_change_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT NOT NULL, protocol TEXT NOT NULL,
    actor TEXT NOT NULL, source_kind TEXT NOT NULL DEFAULT 'manual', source_ref TEXT NOT NULL DEFAULT '',
    approval_ref TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL, resource TEXT NOT NULL DEFAULT '', request_json TEXT NOT NULL DEFAULT '{}',
    state TEXT NOT NULL DEFAULT 'PENDING', changed INTEGER NOT NULL DEFAULT 0,
    pre_hash TEXT NOT NULL DEFAULT '', post_hash TEXT NOT NULL DEFAULT '',
    pre_value_json TEXT NOT NULL DEFAULT '', post_value_json TEXT NOT NULL DEFAULT '',
    reversible INTEGER NOT NULL DEFAULT 0, verification_state TEXT NOT NULL DEFAULT '',
    rollback_state TEXT NOT NULL DEFAULT '', rollback_of_id INTEGER, rollback_transaction_id INTEGER,
    error TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, started_ts REAL NOT NULL DEFAULT 0,
    finished_ts REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_structured_change_transactions_device
    ON structured_change_transactions(device, created_ts);
CREATE INDEX IF NOT EXISTS idx_structured_change_transactions_state
    ON structured_change_transactions(state, created_ts);
CREATE INDEX IF NOT EXISTS idx_structured_change_transactions_idempotency
    ON structured_change_transactions(idempotency_key, state, id);

-- ---- NI-5: streaming telemetry lifecycle --------------------------------
CREATE TABLE IF NOT EXISTS telemetry_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, device TEXT NOT NULL,
    path TEXT NOT NULL, mode TEXT NOT NULL DEFAULT 'ON_CHANGE', encoding TEXT NOT NULL DEFAULT 'json_ietf',
    sample_interval_ms INTEGER NOT NULL DEFAULT 10000, heartbeat_interval_ms INTEGER NOT NULL DEFAULT 0,
    window_seconds INTEGER NOT NULL DEFAULT 30, collection_interval_seconds INTEGER NOT NULL DEFAULT 60,
    retention_days INTEGER NOT NULL DEFAULT 30, next_run_ts REAL NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1, state TEXT NOT NULL DEFAULT 'IDLE',
    last_error TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_ts REAL NOT NULL, last_run_ts REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_telemetry_subscriptions_device
    ON telemetry_subscriptions(device, enabled);
CREATE TABLE IF NOT EXISTS telemetry_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subscription_id INTEGER NOT NULL, device TEXT NOT NULL,
    path TEXT NOT NULL, observed_ts REAL NOT NULL, value_json TEXT NOT NULL, source_ts REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(subscription_id) REFERENCES telemetry_subscriptions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_telemetry_samples_lookup
    ON telemetry_samples(subscription_id, observed_ts);
CREATE TABLE IF NOT EXISTS telemetry_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subscription_id INTEGER NOT NULL, device TEXT NOT NULL,
    path TEXT NOT NULL, value_path TEXT NOT NULL, observed_ts REAL NOT NULL, source_ts REAL NOT NULL DEFAULT 0,
    value_type TEXT NOT NULL, numeric_value REAL, text_value TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(subscription_id) REFERENCES telemetry_subscriptions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_telemetry_points_series
    ON telemetry_points(subscription_id, value_path, observed_ts);

-- ---- VM-1: vendor/model packs --------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_model_packs (
    name TEXT PRIMARY KEY, vendor TEXT NOT NULL, os_family TEXT NOT NULL DEFAULT '',
    revision TEXT NOT NULL, builtin INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1,
    spec_json TEXT NOT NULL, updated_ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS device_model_bindings (
    device TEXT PRIMARY KEY, pack_name TEXT NOT NULL, updated_ts REAL NOT NULL,
    FOREIGN KEY(pack_name) REFERENCES vendor_model_packs(name)
);

-- ---- NA-1: desired state --------------------------------------------------
CREATE TABLE IF NOT EXISTS desired_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '',
    target_kind TEXT NOT NULL, target_value TEXT NOT NULL, document_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'DRAFT', revision INTEGER NOT NULL DEFAULT 1, supersedes_id INTEGER,
    created_by TEXT NOT NULL, created_ts REAL NOT NULL, updated_by TEXT NOT NULL, updated_ts REAL NOT NULL,
    published_by TEXT NOT NULL DEFAULT '', published_ts REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS desired_state_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, desired_state_id INTEGER NOT NULL, actor TEXT NOT NULL,
    mode TEXT NOT NULL, source_kind TEXT NOT NULL DEFAULT 'desired_state', source_ref TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'PENDING', plan_json TEXT NOT NULL DEFAULT '{}',
    changed_count INTEGER NOT NULL DEFAULT 0, noop_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0,
    created_ts REAL NOT NULL, finished_ts REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(desired_state_id) REFERENCES desired_states(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_desired_state_runs_state
    ON desired_state_runs(desired_state_id, created_ts);

-- ---- NA-2: fleet change campaigns ----------------------------------------
CREATE TABLE IF NOT EXISTS fleet_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, desired_state_id INTEGER NOT NULL,
    plan_json TEXT NOT NULL DEFAULT '{}', canary_size INTEGER NOT NULL DEFAULT 0, wave_size INTEGER NOT NULL DEFAULT 1,
    max_failures INTEGER NOT NULL DEFAULT 0, rollback_on_failure INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'DRAFT', current_wave INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL, created_ts REAL NOT NULL, started_ts REAL NOT NULL DEFAULT 0, finished_ts REAL NOT NULL DEFAULT 0,
    FOREIGN KEY(desired_state_id) REFERENCES desired_states(id)
);
CREATE TABLE IF NOT EXISTS fleet_campaign_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id INTEGER NOT NULL, device TEXT NOT NULL,
    wave INTEGER NOT NULL, ordinal INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '', transaction_ids_json TEXT NOT NULL DEFAULT '[]', last_run_id INTEGER, updated_ts REAL NOT NULL,
    UNIQUE(campaign_id, device),
    FOREIGN KEY(campaign_id) REFERENCES fleet_campaigns(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_fleet_campaign_targets_wave
    ON fleet_campaign_targets(campaign_id, wave, state, ordinal);

-- ---- HA-1: recovery/DR evidence ------------------------------------------
CREATE TABLE IF NOT EXISTS recovery_drills (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, actor TEXT NOT NULL, state TEXT NOT NULL,
    node_id TEXT NOT NULL DEFAULT '', verification_ref TEXT NOT NULL DEFAULT '',
    detail_json TEXT NOT NULL DEFAULT '{}', started_ts REAL NOT NULL, finished_ts REAL NOT NULL DEFAULT 0
);

-- ---- NI-6 enterprise analytics workflow ---------------------------------
CREATE TABLE IF NOT EXISTS network_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    insight_type TEXT NOT NULL, object_type TEXT NOT NULL DEFAULT 'DEVICE', object_id TEXT NOT NULL,
    severity TEXT NOT NULL, confidence REAL NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'NEW', evidence_json TEXT NOT NULL DEFAULT '{}',
    affected_json TEXT NOT NULL DEFAULT '[]', fingerprint TEXT NOT NULL UNIQUE,
    first_seen_ts REAL NOT NULL, last_seen_ts REAL NOT NULL, occurrence_count INTEGER NOT NULL DEFAULT 1,
    acknowledged_by TEXT NOT NULL DEFAULT '', acknowledged_ts REAL NOT NULL DEFAULT 0,
    resolved_by TEXT NOT NULL DEFAULT '', resolved_ts REAL NOT NULL DEFAULT 0,
    expired_ts REAL NOT NULL DEFAULT 0, note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_network_insights_state
    ON network_insights(state, insight_type, last_seen_ts);
CREATE INDEX IF NOT EXISTS idx_network_insights_object
    ON network_insights(object_id, insight_type, last_seen_ts);
CREATE TABLE IF NOT EXISTS analytics_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    job_type TEXT NOT NULL, object_id TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL, input_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, finished_ts REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_analytics_jobs_created
    ON analytics_jobs(job_type, created_ts);

-- ---- NI-7 explicit L3/VRF route evidence --------------------------------
CREATE TABLE IF NOT EXISTS l3_route_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    device TEXT NOT NULL, vrf TEXT NOT NULL DEFAULT 'default', destination_prefix TEXT NOT NULL,
    protocol TEXT NOT NULL DEFAULT '', next_hop TEXT NOT NULL DEFAULT '',
    outgoing_interface TEXT NOT NULL DEFAULT '', next_device TEXT NOT NULL DEFAULT '',
    metric INTEGER NOT NULL DEFAULT 0, terminal INTEGER NOT NULL DEFAULT 0,
    evidence_ref TEXT NOT NULL DEFAULT '', actor TEXT NOT NULL DEFAULT '', observed_ts REAL NOT NULL,
    received_ts REAL NOT NULL DEFAULT 0, max_age_seconds INTEGER NOT NULL DEFAULT 0,
    source_kind TEXT NOT NULL DEFAULT 'MANUAL', collection_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_l3_route_lookup
    ON l3_route_observations(device, vrf, destination_prefix, observed_ts);
CREATE INDEX IF NOT EXISTS idx_l3_route_next_device
    ON l3_route_observations(next_device, vrf, destination_prefix, observed_ts);
CREATE INDEX IF NOT EXISTS idx_l3_route_collection
    ON l3_route_observations(device, source_kind, collection_id);
CREATE TABLE IF NOT EXISTS l3_interface_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    device TEXT NOT NULL, vrf TEXT NOT NULL DEFAULT 'default', interface TEXT NOT NULL,
    ip_address TEXT NOT NULL, prefix_length INTEGER NOT NULL DEFAULT 0,
    network_prefix TEXT NOT NULL DEFAULT '', source_kind TEXT NOT NULL DEFAULT 'CLI_COLLECTION',
    collection_id TEXT NOT NULL DEFAULT '', evidence_ref TEXT NOT NULL DEFAULT '',
    observed_ts REAL NOT NULL, received_ts REAL NOT NULL DEFAULT 0,
    max_age_seconds INTEGER NOT NULL DEFAULT 3600
);
CREATE INDEX IF NOT EXISTS idx_l3_interface_device
    ON l3_interface_observations(device, vrf, interface, observed_ts);
CREATE INDEX IF NOT EXISTS idx_l3_interface_ip
    ON l3_interface_observations(vrf, ip_address, observed_ts);
CREATE INDEX IF NOT EXISTS idx_l3_interface_collection
    ON l3_interface_observations(device, source_kind, collection_id);
CREATE TABLE IF NOT EXISTS l3_collection_state (
    device TEXT PRIMARY KEY, collection_id TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'UNKNOWN', route_count INTEGER NOT NULL DEFAULT 0,
    interface_count INTEGER NOT NULL DEFAULT 0, observed_ts REAL NOT NULL DEFAULT 0,
    received_ts REAL NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT ''
);

-- ---- MC-6 service & dependency graph ------------------------------------
CREATE TABLE IF NOT EXISTS service_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    entity_key TEXT NOT NULL, entity_type TEXT NOT NULL, name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '', metadata_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_ts REAL NOT NULL,
    UNIQUE(tenant_id, entity_key)
);
CREATE INDEX IF NOT EXISTS idx_service_entities_type
    ON service_entities(tenant_id, entity_type, name);
CREATE TABLE IF NOT EXISTS service_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    source_key TEXT NOT NULL, target_key TEXT NOT NULL, relationship TEXT NOT NULL,
    evidence_state TEXT NOT NULL, provenance TEXT NOT NULL, evidence_ref TEXT NOT NULL DEFAULT '',
    vrf TEXT NOT NULL DEFAULT '', destination_prefix TEXT NOT NULL DEFAULT '',
    max_age_seconds INTEGER NOT NULL DEFAULT 0, observed_ts REAL NOT NULL DEFAULT 0,
    received_ts REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}', fingerprint TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_service_dependencies_source
    ON service_dependencies(tenant_id, source_key, active, relationship);
CREATE INDEX IF NOT EXISTS idx_service_dependencies_target
    ON service_dependencies(tenant_id, target_key, active, relationship);
CREATE INDEX IF NOT EXISTS idx_service_dependencies_evidence
    ON service_dependencies(tenant_id, evidence_state, observed_ts);

-- ---- MC-7 deterministic correlation hypotheses ----------------------------
CREATE TABLE IF NOT EXISTS correlation_hypotheses (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    hypothesis_key TEXT NOT NULL UNIQUE, hypothesis_type TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '', confidence INTEGER NOT NULL DEFAULT 0,
    confidence_label TEXT NOT NULL DEFAULT 'LOW',
    initiating_source_type TEXT NOT NULL DEFAULT '', initiating_source_ref TEXT NOT NULL DEFAULT '',
    first_evidence_at REAL NOT NULL DEFAULT 0, last_evidence_at REAL NOT NULL DEFAULT 0,
    supporting_json TEXT NOT NULL DEFAULT '[]', contradicting_json TEXT NOT NULL DEFAULT '[]',
    affected_entities_json TEXT NOT NULL DEFAULT '[]',
    rule_id TEXT NOT NULL, rule_version TEXT NOT NULL, evidence_fingerprint TEXT NOT NULL,
    score_breakdown_json TEXT NOT NULL DEFAULT '{}', active INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL, updated_at REAL NOT NULL,
    UNIQUE(incident_id, rule_id, rule_version, hypothesis_key)
);
CREATE INDEX IF NOT EXISTS idx_correlation_hypotheses_incident
    ON correlation_hypotheses(incident_id, active, confidence DESC, hypothesis_type);
CREATE INDEX IF NOT EXISTS idx_correlation_hypotheses_rule
    ON correlation_hypotheses(rule_version, rule_id, active);

-- ---- MC-11 topology-aware change planning --------------------------------
CREATE TABLE IF NOT EXISTS change_planning_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    device TEXT NOT NULL, evidence_kind TEXT NOT NULL, direction TEXT NOT NULL,
    vrf TEXT NOT NULL DEFAULT 'default', source_selector TEXT NOT NULL DEFAULT '*',
    destination_selector TEXT NOT NULL DEFAULT '*', service TEXT NOT NULL DEFAULT 'any',
    state TEXT NOT NULL, evidence_ref TEXT NOT NULL, metadata_json TEXT NOT NULL DEFAULT '{}',
    fingerprint TEXT NOT NULL UNIQUE, observed_ts REAL NOT NULL, max_age_seconds INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_change_planning_evidence_scope
    ON change_planning_evidence(device, direction, vrf, evidence_kind, state);
CREATE TABLE IF NOT EXISTS change_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    plan_key TEXT NOT NULL UNIQUE, source_selector TEXT NOT NULL, destination_selector TEXT NOT NULL,
    vrf TEXT NOT NULL DEFAULT 'default', destination_prefix TEXT NOT NULL DEFAULT '',
    source_prefix TEXT NOT NULL DEFAULT '', service TEXT NOT NULL DEFAULT 'any',
    planning_status TEXT NOT NULL, input_json TEXT NOT NULL DEFAULT '{}', result_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT '', created_ts REAL NOT NULL, updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_change_plans_scope
    ON change_plans(vrf, source_selector, destination_selector, updated_ts);

-- ---- MC-10 correlation production hardening -------------------------------
CREATE TABLE IF NOT EXISTS correlation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL DEFAULT 'default',
    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    run_key TEXT NOT NULL UNIQUE, mode TEXT NOT NULL DEFAULT 'CORRELATE',
    rule_version TEXT NOT NULL, input_fingerprint TEXT NOT NULL,
    result_fingerprint TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'RUNNING',
    replay_of_id INTEGER REFERENCES correlation_runs(id) ON DELETE SET NULL,
    deterministic_match INTEGER NOT NULL DEFAULT 1,
    facts_considered INTEGER NOT NULL DEFAULT 0, hypotheses_count INTEGER NOT NULL DEFAULT 0,
    late_evidence_count INTEGER NOT NULL DEFAULT 0, future_skew_count INTEGER NOT NULL DEFAULT 0,
    out_of_order_count INTEGER NOT NULL DEFAULT 0, dependency_truncated INTEGER NOT NULL DEFAULT 0,
    facts_truncated INTEGER NOT NULL DEFAULT 0, range_start_ts REAL NOT NULL DEFAULT 0,
    range_end_ts REAL NOT NULL DEFAULT 0, queued_ts REAL NOT NULL, started_ts REAL NOT NULL,
    finished_ts REAL NOT NULL DEFAULT 0, duration_ms REAL NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_correlation_runs_incident
    ON correlation_runs(incident_id, started_ts DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_correlation_runs_fingerprint
    ON correlation_runs(incident_id, mode, rule_version, input_fingerprint, state, finished_ts DESC);
CREATE INDEX IF NOT EXISTS idx_correlation_runs_state
    ON correlation_runs(state, started_ts);
"""

# Additive column migrations: (table, column, coldef). Applied only if absent.

def _split_sql_script(script):
    """Split our DDL on semicolons outside strings/comments.

    sqlite3.executescript handles this natively, but PostgreSQL bootstrap needs
    individual statements and the schema contains semicolons inside -- comments.
    """
    out, buf = [], []
    quote = None
    line_comment = False
    i = 0
    while i < len(script):
        ch = script[i]
        nxt = script[i + 1] if i + 1 < len(script) else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
                buf.append(ch)
            i += 1
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                if nxt == quote:
                    buf.append(nxt)
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch == "-" and nxt == "-":
            line_comment = True
            i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _schema_statements(*, indexes=None):
    """Return schema statements split into base DDL and indexes.

    Existing databases may need additive columns before indexes that reference
    those columns can be created. Callers bootstrap tables first, apply
    _MIGRATIONS, then create indexes.
    """
    base, idx = [], []
    for stmt in _split_sql_script(_SCHEMA):
        target = idx if stmt.lstrip().upper().startswith("CREATE INDEX") else base
        target.append(stmt)
    if indexes is True:
        return idx
    if indexes is False:
        return base
    return base + idx


_MIGRATIONS = [
    ("devices", "snmp_version", "TEXT NOT NULL DEFAULT ''"),   # '', v2c, v3
    ("devices", "snmp_ref", "TEXT"),                            # vault entry
    ("devices", "device_type", "TEXT NOT NULL DEFAULT 'network'"),  # system|network|application
    ("devices", "netflow", "INTEGER NOT NULL DEFAULT 0"),      # collect NetFlow (network devices)
    ("devices", "monitor_ports", "TEXT NOT NULL DEFAULT ''"),  # tcp/udp ports (system devices)
    ("devices", "monitor_urls", "TEXT NOT NULL DEFAULT ''"),   # http(s) endpoints (application devices)
    ("devices", "config_collect_command", "TEXT NOT NULL DEFAULT ''"), # bounded read-only CLI config collection override
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
    ("operational_events", "domain", "TEXT NOT NULL DEFAULT 'SYSTEM'"),
    ("operational_events", "entity_type", "TEXT NOT NULL DEFAULT 'unknown'"),
    ("operational_events", "entity_id", "TEXT NOT NULL DEFAULT ''"),
    ("operational_events", "resource", "TEXT NOT NULL DEFAULT ''"),
    ("operational_events", "status", "TEXT NOT NULL DEFAULT 'OBSERVED'"),
    ("operational_events", "observed_at", "REAL NOT NULL DEFAULT 0"),
    ("operational_events", "evidence_ref", "TEXT NOT NULL DEFAULT ''"),
    ("operational_alerts", "correlation_key", "TEXT NOT NULL DEFAULT ''"),
    ("operational_alerts", "last_event_id", "INTEGER"),
    ("incident_evidence_links", "source_ts", "REAL NOT NULL DEFAULT 0"),
    ("incident_evidence_links", "received_ts", "REAL NOT NULL DEFAULT 0"),
    ("incident_evidence_links", "source_clock_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("structured_change_transactions", "approval_ref", "TEXT NOT NULL DEFAULT ''"),
    ("structured_change_transactions", "idempotency_key", "TEXT NOT NULL DEFAULT ''"),
    ("structured_change_transactions", "changed", "INTEGER NOT NULL DEFAULT 0"),
    ("structured_change_transactions", "pre_value_json", "TEXT NOT NULL DEFAULT ''"),
    ("structured_change_transactions", "post_value_json", "TEXT NOT NULL DEFAULT ''"),
    ("structured_change_transactions", "reversible", "INTEGER NOT NULL DEFAULT 0"),
    ("structured_change_transactions", "verification_state", "TEXT NOT NULL DEFAULT ''"),
    ("structured_change_transactions", "rollback_of_id", "INTEGER"),
    ("structured_change_transactions", "rollback_transaction_id", "INTEGER"),
    ("telemetry_subscriptions", "window_seconds", "INTEGER NOT NULL DEFAULT 30"),
    ("telemetry_subscriptions", "collection_interval_seconds", "INTEGER NOT NULL DEFAULT 60"),
    ("telemetry_subscriptions", "retention_days", "INTEGER NOT NULL DEFAULT 30"),
    ("telemetry_subscriptions", "next_run_ts", "REAL NOT NULL DEFAULT 0"),
    ("desired_states", "revision", "INTEGER NOT NULL DEFAULT 1"),
    ("desired_states", "supersedes_id", "INTEGER"),
    ("desired_states", "published_by", "TEXT NOT NULL DEFAULT ''"),
    ("desired_state_runs", "source_kind", "TEXT NOT NULL DEFAULT 'desired_state'"),
    ("desired_state_runs", "source_ref", "TEXT NOT NULL DEFAULT ''"),
    ("desired_state_runs", "changed_count", "INTEGER NOT NULL DEFAULT 0"),
    ("desired_state_runs", "noop_count", "INTEGER NOT NULL DEFAULT 0"),
    ("desired_state_runs", "failure_count", "INTEGER NOT NULL DEFAULT 0"),
    ("fleet_campaigns", "plan_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("fleet_campaigns", "canary_size", "INTEGER NOT NULL DEFAULT 0"),
    ("fleet_campaigns", "rollback_on_failure", "INTEGER NOT NULL DEFAULT 0"),
    ("fleet_campaigns", "current_wave", "INTEGER NOT NULL DEFAULT 0"),
    ("fleet_campaigns", "failure_count", "INTEGER NOT NULL DEFAULT 0"),
    ("fleet_campaign_targets", "attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("fleet_campaign_targets", "last_run_id", "INTEGER"),
    ("recovery_drills", "node_id", "TEXT NOT NULL DEFAULT ''"),
    ("recovery_drills", "verification_ref", "TEXT NOT NULL DEFAULT ''"),
    ("cluster_nodes", "state", "TEXT NOT NULL DEFAULT 'ACTIVE'"),
    ("cluster_nodes", "drain_reason", "TEXT NOT NULL DEFAULT ''"),
    ("cluster_nodes", "failure_domain", "TEXT NOT NULL DEFAULT ''"),
    ("cluster_nodes", "instance_id", "TEXT NOT NULL DEFAULT ''"),
    ("distributed_tasks", "claim_generation", "INTEGER NOT NULL DEFAULT 0"),
    ("distributed_tasks", "claim_token", "TEXT NOT NULL DEFAULT ''"),
    ("distributed_tasks", "claimed_instance", "TEXT NOT NULL DEFAULT ''"),
    ("distributed_tasks", "replay_safe", "INTEGER NOT NULL DEFAULT 0"),
    ("distributed_tasks", "recovery_reason", "TEXT NOT NULL DEFAULT ''"),
    ("l3_route_observations", "received_ts", "REAL NOT NULL DEFAULT 0"),
    ("l3_route_observations", "max_age_seconds", "INTEGER NOT NULL DEFAULT 0"),
    ("l3_route_observations", "source_kind", "TEXT NOT NULL DEFAULT 'MANUAL'"),
    ("l3_route_observations", "collection_id", "TEXT NOT NULL DEFAULT ''"),
    ("external_events", "tenant_id", "TEXT NOT NULL DEFAULT 'default'"),
    ("external_events", "source_key", "TEXT NOT NULL DEFAULT ''"),
    ("external_events", "idempotency_key", "TEXT NOT NULL DEFAULT ''"),
    ("external_events", "schema_version", "TEXT NOT NULL DEFAULT '1'"),
    ("external_events", "payload_sha256", "TEXT NOT NULL DEFAULT ''"),
    ("external_events", "payload_json", "TEXT NOT NULL DEFAULT '{}'"),
    ("external_events", "ingest_principal", "TEXT NOT NULL DEFAULT ''"),
    ("external_events", "ingest_result", "TEXT NOT NULL DEFAULT ''"),
    ("external_events", "connector_type", "TEXT NOT NULL DEFAULT ''"),
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
    schema_revision = "mc11-topology-change-planning-1"

    def __init__(self, path):
        self.path = path
        raw = sqlite3.connect(path, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA foreign_keys=ON")
        raw.execute("PRAGMA busy_timeout=5000")
        # Bootstrap tables first. Existing databases may be missing additive
        # columns referenced by newer indexes, so indexes must come after migrate.
        base_schema = ";\n".join(_schema_statements(indexes=False)) + ";"
        raw.executescript(base_schema)
        self._lock = threading.RLock()
        self.conn = _LockedConn(raw, self._lock)
        self._migrate()
        index_schema = ";\n".join(_schema_statements(indexes=True)) + ";"
        self.conn.executescript(index_schema)
        self.conn.commit()
        self._stamp_schema_revision()

    def _migrate(self):
        for table, col, coldef in _MIGRATIONS:
            cols = {r["name"] for r in
                    self.conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if col not in cols:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
        # MC-3 additive normalization for existing operational-event rows.
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

    def _backfill_incident_evidence_timing(self):
        sources = {
            "audit": ("audit", "ts"),
            "syslog": ("syslog_events", "ts"),
            "collection": ("runs", "ts"),
            "compliance": ("compliance_runs", "ts"),
            "protocol_trace": ("protocol_trace_sessions", "created_ts"),
            "sensor_transition": ("sensor_transitions", "observed_at"),
            "operational_event": ("operational_events", "observed_at"),
            "operational_alert": ("operational_alerts", "first_ts"),
            "change_event": ("change_events", "source_ts"),
            "analytics_insight": ("network_insights", "first_seen_ts"),
            "external_event": ("external_events", "source_ts"),
        }
        for source_type, (table, column) in sources.items():
            self.conn.execute(
                f"UPDATE incident_evidence_links SET source_ts=COALESCE("
                f"(SELECT {column} FROM {table} WHERE CAST({table}.id AS TEXT)=incident_evidence_links.source_ref),"
                "linked_ts) WHERE source_type=? AND source_ts=0",
                (source_type,),
            )
        self.conn.execute(
            "UPDATE incident_evidence_links SET source_ts=linked_ts "
            "WHERE source_type='drift' AND source_ts=0"
        )
        self.conn.execute(
            "UPDATE incident_evidence_links SET received_ts=linked_ts WHERE received_ts=0"
        )

    def record_change_event(self, request_id, event_type, status, actor, summary="",
                            metadata=None, source_ts=None, received_ts=None):
        import time
        source_ts = time.time() if source_ts is None else float(source_ts)
        received_ts = time.time() if received_ts is None else float(received_ts)
        event_type = str(event_type or "").strip().upper()[:64]
        if not event_type:
            raise ValueError("change event type is required")
        payload = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
        if len(payload.encode("utf-8")) > 8192:
            raise ValueError("change event metadata exceeds 8192 bytes")
        cur = self.conn.execute(
            "INSERT INTO change_events(request_id,event_type,status,actor,summary,source_ts,received_ts,metadata_json) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (None if request_id is None else int(request_id), event_type,
             str(status or "")[:64], str(actor or "")[:128],
             str(summary or "").replace("\x00", "")[:1000], source_ts, received_ts, payload),
        )
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM change_events WHERE id=?", (cur.lastrowid,)).fetchone())

    def record_external_event(self, source_system, source_event_id, event_type, *, domain="EXTERNAL",
                              severity="INFO", entity_type="unknown", entity_id="", summary="",
                              source_ts=None, received_ts=None, source_clock=None, metadata=None):
        import time
        source_system = str(source_system or "").strip()[:128]
        source_event_id = str(source_event_id or "").strip()[:256]
        event_type = str(event_type or "").strip()[:128]
        if not source_system or not source_event_id or not event_type:
            raise ValueError("external event source, source_event_id and event_type are required")
        source_ts = time.time() if source_ts is None else float(source_ts)
        received_ts = time.time() if received_ts is None else float(received_ts)
        clock_json = json.dumps(source_clock or {}, sort_keys=True, separators=(",", ":"))
        metadata_json = json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))
        if len(clock_json.encode("utf-8")) > 4096 or len(metadata_json.encode("utf-8")) > 8192:
            raise ValueError("external event metadata exceeds limit")
        self.conn.execute(
            "INSERT OR IGNORE INTO external_events(source_system,source_event_id,domain,event_type,severity,"
            "entity_type,entity_id,summary,source_ts,received_ts,source_clock_json,metadata_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (source_system, source_event_id, str(domain or "EXTERNAL").upper()[:64], event_type,
             str(severity or "INFO").upper()[:32], str(entity_type or "unknown")[:64],
             str(entity_id or "")[:255], str(summary or "").replace("\x00", "")[:1000],
             source_ts, received_ts, clock_json, metadata_json),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM external_events WHERE source_system=? AND source_event_id=?",
            (source_system, source_event_id),
        ).fetchone()
        return dict(row)

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

    def operational_event_by_evidence_ref(self, evidence_ref):
        if not evidence_ref:
            return None
        row = self.conn.execute(
            "SELECT * FROM operational_events WHERE evidence_ref=? ORDER BY id DESC LIMIT 1",
            (str(evidence_ref),)).fetchone()
        return dict(row) if row else None

    def insert_operational_event(self, ts, source_type, source, device, event_type, severity,
                                 interface, ifindex, trap_oid, message, dedup_key, suppressed,
                                 suppression_id, metadata, *, domain="SYSTEM", entity_type="unknown",
                                 entity_id="", resource="", status="OBSERVED", observed_at=None,
                                 evidence_ref=""):
        observed_at = float(ts) if observed_at is None else float(observed_at)
        cur = self.conn.execute(
            "INSERT INTO operational_events "
            "(first_ts,last_ts,event_count,source_type,source,device,event_type,severity,interface,ifindex,trap_oid,message,dedup_key,suppressed,suppression_id,metadata,domain,entity_type,entity_id,resource,status,observed_at,evidence_ref) "
            "VALUES (?,?,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (float(ts), float(ts), source_type, source, device, event_type, severity, interface, ifindex, trap_oid,
             message, dedup_key, int(bool(suppressed)), suppression_id, metadata, domain, entity_type,
             entity_id, resource, status, observed_at, evidence_ref))
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM operational_events WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def touch_operational_event(self, event_id, ts):
        self.conn.execute(
            "UPDATE operational_events SET last_ts=?, observed_at=?, event_count=event_count+1 WHERE id=?",
            (float(ts), float(ts), int(event_id)))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM operational_events WHERE id=?", (int(event_id),)).fetchone())

    def operational_event(self, event_id):
        row = self.conn.execute(
            "SELECT * FROM operational_events WHERE id=?", (int(event_id),)).fetchone()
        return dict(row) if row else None

    def operational_events(self, limit=200, device=None, include_suppressed=True,
                           domain=None, source_type=None, entity_type=None, status=None):
        q = "SELECT * FROM operational_events"; args=[]; where=[]
        if device:
            where.append("device=?"); args.append(device)
        if domain:
            where.append("domain=?"); args.append(str(domain).upper())
        if source_type:
            where.append("source_type=?"); args.append(str(source_type).lower())
        if entity_type:
            where.append("entity_type=?"); args.append(str(entity_type).lower())
        if status:
            where.append("status=?"); args.append(str(status).upper())
        if not include_suppressed:
            where.append("suppressed=0")
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY observed_at DESC,id DESC LIMIT ?"; args.append(max(1,min(int(limit),2000)))
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
            if now is not None:
                q += " AND expires_ts>?"; args.append(float(now))
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

    def create_operational_alert(self, event, correlation_key="", opened_ts=None):
        event_last = float(event.get("last_ts") or event.get("first_ts") or 0)
        alert_last = max(event_last, float(opened_ts)) if opened_ts is not None else event_last
        cur=self.conn.execute(
            "INSERT INTO operational_alerts(event_id,correlation_key,last_event_id,state,severity,device,event_type,message,first_ts,last_ts,event_count) VALUES(?,?,?, 'OPEN', ?,?,?,?,?,?,?)",
            (int(event["id"]), str(correlation_key or ""), int(event["id"]),
             event.get("severity") or "WARNING", event.get("device") or "",
             event.get("event_type") or "", event.get("message") or "",
             float(event.get("first_ts") or event.get("last_ts") or 0),
             alert_last, int(event.get("event_count") or 1)))
        self.conn.commit(); return self.get_operational_alert(cur.lastrowid)

    def active_operational_alert_for_correlation(self, correlation_key):
        if not correlation_key:
            return None
        row=self.conn.execute(
            "SELECT * FROM operational_alerts WHERE correlation_key=? AND state IN ('OPEN','ACKNOWLEDGED') ORDER BY id DESC LIMIT 1",
            (str(correlation_key),)).fetchone()
        return dict(row) if row else None

    def latest_operational_alert_for_correlation(self, correlation_key):
        if not correlation_key:
            return None
        row=self.conn.execute(
            "SELECT * FROM operational_alerts WHERE correlation_key=? ORDER BY id DESC LIMIT 1",
            (str(correlation_key),)).fetchone()
        return dict(row) if row else None

    def reopen_operational_alert(self, alert_id, now):
        self.conn.execute(
            "UPDATE operational_alerts SET state='OPEN', last_ts=?, "
            "acknowledged_by='', acknowledged_ts=NULL, acknowledge_note='', "
            "resolved_by='', resolved_ts=NULL, resolution_note='' WHERE id=?",
            (float(now), int(alert_id)))
        self.conn.commit(); return self.get_operational_alert(alert_id)

    def touch_operational_alert(self, alert_id, event):
        self.conn.execute(
            "UPDATE operational_alerts SET last_ts=?, event_count=CASE WHEN last_event_id=? THEN ? ELSE event_count+? END, last_event_id=?, severity=?, event_type=?, message=? WHERE id=?",
            (float(event.get("last_ts") or 0), int(event.get("id") or 0),
             max(1, int(event.get("event_count") or 1)), max(1, int(event.get("event_count") or 1)),
             int(event.get("id") or 0), event.get("severity") or "WARNING",
             event.get("event_type") or "", event.get("message") or "", int(alert_id)))
        self.conn.commit(); return self.get_operational_alert(alert_id)

    def touch_operational_alert_recovery(self, alert_id, event):
        self.conn.execute(
            "UPDATE operational_alerts SET last_ts=?, last_event_id=?, event_count=event_count+1 WHERE id=?",
            (float(event.get("last_ts") or event.get("observed_at") or 0),
             int(event.get("id") or 0), int(alert_id)))
        self.conn.commit(); return self.get_operational_alert(alert_id)

    def get_operational_alert(self, alert_id):
        row=self.conn.execute("SELECT * FROM operational_alerts WHERE id=?",(int(alert_id),)).fetchone()
        return dict(row) if row else None

    def list_operational_alerts(self, state=None, device=None, limit=200):
        q="SELECT * FROM operational_alerts"; args=[]; where=[]
        if state:
            where.append("state=?"); args.append(state)
        if device:
            where.append("device=?"); args.append(device)
        if where:
            q += " WHERE " + " AND ".join(where)
        q += " ORDER BY last_ts DESC LIMIT ?"; args.append(int(limit))
        return [dict(r) for r in self.conn.execute(q,args).fetchall()]

    def update_operational_alert_state(self, alert_id, state, actor, note, now):
        if state == "ACKNOWLEDGED":
            self.conn.execute("UPDATE operational_alerts SET state=?, acknowledged_by=?, acknowledged_ts=?, acknowledge_note=? WHERE id=?",
                              (state, actor, float(now), note, int(alert_id)))
        elif state == "RESOLVED":
            self.conn.execute("UPDATE operational_alerts SET state=?, resolved_by=?, resolved_ts=?, resolution_note=? WHERE id=?",
                              (state, actor, float(now), note, int(alert_id)))
        else:
            raise ValueError("invalid operational alert state")
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

    def register_cluster_node(self, node_id, hostname, pid, now, role="control-plane",
                              failure_domain="", instance_id=""):
        # A stable node id preserves explicit drain state across restart. R63 also
        # records a process-instance id and an operator-declared failure domain;
        # PostgreSQL node-identity fencing is enforced by HAService/Manager.
        previous = self.conn.execute(
            "SELECT state,drain_reason FROM cluster_nodes WHERE node_id=?", (node_id,)
        ).fetchone()
        state = str(previous["state"] if previous else "ACTIVE")
        reason = str(previous["drain_reason"] if previous else "")
        self.conn.execute("DELETE FROM cluster_nodes WHERE node_id=?", (node_id,))
        self.conn.execute(
            "INSERT INTO cluster_nodes"
            "(node_id,hostname,pid,started_ts,last_heartbeat_ts,role,state,drain_reason,failure_domain,instance_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                node_id, hostname or "", int(pid), float(now), float(now),
                role or "control-plane", state, reason,
                str(failure_domain or "")[:256], str(instance_id or "")[:128],
            ),
        )
        self.conn.commit()

    def heartbeat_cluster_node(self, node_id, now, instance_id=None):
        if instance_id:
            cur = self.conn.execute(
                "UPDATE cluster_nodes SET last_heartbeat_ts=? WHERE node_id=? AND instance_id=?",
                (float(now), node_id, str(instance_id)),
            )
        else:
            cur = self.conn.execute(
                "UPDATE cluster_nodes SET last_heartbeat_ts=? WHERE node_id=?",
                (float(now), node_id),
            )
        self.conn.commit()
        return bool(cur.rowcount)

    def list_cluster_nodes(self, since_ts=0):
        rows = self.conn.execute(
            "SELECT * FROM cluster_nodes WHERE last_heartbeat_ts>=? ORDER BY node_id",
            (float(since_ts),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_cluster_node(self, node_id):
        row = self.conn.execute(
            "SELECT * FROM cluster_nodes WHERE node_id=?", (str(node_id),)
        ).fetchone()
        return dict(row) if row else None

    def set_cluster_node_state(self, node_id, state, reason=""):
        state = str(state or "").upper()
        if state not in {"ACTIVE", "DRAINING", "DRAINED"}:
            raise ValueError("unsupported cluster node state")
        reason = str(reason or "").replace("\x00", "")[:500]
        cur = self.conn.execute(
            "UPDATE cluster_nodes SET state=?,drain_reason=? WHERE node_id=?",
            (state, reason if state != "ACTIVE" else "", str(node_id)),
        )
        self.conn.commit()
        if not cur.rowcount:
            raise ValueError("unknown cluster node")
        return self.get_cluster_node(node_id)

    def enqueue_distributed_task(self, queue, kind, payload, now, available_ts=None, replay_safe=False):
        available = float(now if available_ts is None else available_ts)
        cur = self.conn.execute(
            "INSERT INTO distributed_tasks(queue,kind,payload,state,available_ts,replay_safe,created_ts,updated_ts) "
            "VALUES(?,?,?,'PENDING',?,?,?,?)",
            (queue or "default", kind, payload or "{}", available, int(bool(replay_safe)),
             float(now), float(now)))
        self.conn.commit()
        return dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?",
                                      (cur.lastrowid,)).fetchone())

    @staticmethod
    def _claim_token():
        import secrets
        return secrets.token_hex(24)

    def claim_distributed_task(self, queue, worker_id, now, lease_seconds=60, instance_id=""):
        # R63 never silently replays an expired claim. Expired/partial work must
        # first transition to RECOVERY_REQUIRED and be explicitly reconciled.
        lease_until = float(now) + max(5, int(lease_seconds))
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM distributed_tasks WHERE queue=? AND available_ts<=? AND state='PENDING' "
                "ORDER BY id LIMIT 1", (queue or "default", float(now))).fetchone()
            if not row:
                return None
            attempts = int(row["attempts"] or 0) + 1
            generation = int(row["claim_generation"] or 0) + 1
            token = self._claim_token()
            self.conn.execute(
                "UPDATE distributed_tasks SET state='CLAIMED',claimed_by=?,claimed_instance=?,claim_ts=?,"
                "lease_until=?,attempts=?,claim_generation=?,claim_token=?,recovery_reason='',updated_ts=? "
                "WHERE id=? AND state='PENDING'",
                (worker_id, str(instance_id or "")[:128], float(now), lease_until, attempts, generation,
                 token, float(now), int(row["id"])))
            self.conn.commit()
            return dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?",
                                          (int(row["id"]),)).fetchone())

    def renew_distributed_task(self, task_id, worker_id, claim_token, claim_generation, now, lease_seconds=60):
        lease_until = float(now) + max(5, int(lease_seconds))
        cur = self.conn.execute(
            "UPDATE distributed_tasks SET lease_until=?,updated_ts=? WHERE id=? AND state='CLAIMED' "
            "AND claimed_by=? AND claim_token=? AND claim_generation=? AND lease_until>=?",
            (lease_until, float(now), int(task_id), str(worker_id), str(claim_token),
             int(claim_generation), float(now)))
        self.conn.commit()
        if not cur.rowcount:
            raise ValueError("distributed task lease is stale or no longer owned by this worker")
        return dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone())

    def finish_distributed_task(self, task_id, worker_id, now, ok=True, result="", error="",
                                claim_token=None, claim_generation=None):
        if not claim_token or claim_generation is None:
            raise ValueError("claim_token and claim_generation are required to finish a distributed task")
        state = "DONE" if ok else "FAILED"
        cur = self.conn.execute(
            "UPDATE distributed_tasks SET state=?,result=?,error=?,lease_until=NULL,updated_ts=? "
            "WHERE id=? AND state='CLAIMED' AND claimed_by=? AND claim_token=? "
            "AND claim_generation=? AND lease_until>=?",
            (state, result or "", error or "", float(now), int(task_id), str(worker_id),
             str(claim_token), int(claim_generation), float(now)))
        self.conn.commit()
        if not cur.rowcount:
            raise ValueError("distributed task finish rejected: stale/expired fencing token")
        row = self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone()
        return dict(row) if row else None

    def recover_expired_distributed_tasks(self, now, limit=100):
        limit = min(5000, max(1, int(limit)))
        with self._lock:
            rows = self.conn.execute(
                "SELECT id FROM distributed_tasks WHERE state='CLAIMED' AND lease_until<? ORDER BY id LIMIT ?",
                (float(now), limit)).fetchall()
            ids = [int(r["id"]) for r in rows]
            for task_id in ids:
                self.conn.execute(
                    "UPDATE distributed_tasks SET state='RECOVERY_REQUIRED',lease_until=NULL,"
                    "recovery_reason=?,updated_ts=? WHERE id=? AND state='CLAIMED' AND lease_until<?",
                    ("worker lease expired; automatic replay disabled", float(now), task_id, float(now)))
            self.conn.commit()
        return [dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (i,)).fetchone())
                for i in ids]

    def requeue_distributed_task(self, task_id, now, reason=""):
        row = self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone()
        if not row:
            raise ValueError("unknown distributed task")
        if str(row["state"]) != "RECOVERY_REQUIRED":
            raise ValueError("only RECOVERY_REQUIRED distributed tasks can be requeued")
        if not bool(row["replay_safe"]):
            raise ValueError("distributed task is not declared replay-safe; manual recovery is required")
        cur = self.conn.execute(
            "UPDATE distributed_tasks SET state='PENDING',claimed_by='',claimed_instance='',claim_ts=NULL,"
            "lease_until=NULL,claim_token='',available_ts=?,recovery_reason=?,updated_ts=? "
            "WHERE id=? AND state='RECOVERY_REQUIRED'",
            (float(now), str(reason or "explicit replay approved")[:500], float(now), int(task_id)))
        self.conn.commit()
        if not cur.rowcount:
            raise ValueError("distributed task recovery state changed concurrently")
        return dict(self.conn.execute("SELECT * FROM distributed_tasks WHERE id=?", (int(task_id),)).fetchone())

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
