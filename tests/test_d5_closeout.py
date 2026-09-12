import time
from pathlib import Path

from netconfig.manager import Manager
from netconfig import diagnostic_maintenance as dm


def _manager(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.settings.update({
        "debug_bundle_keep": 1,
        "case_export_retention_days": 1,
        "protocol_trace_retention_days": 1,
    })
    return m


def test_diagnostic_maintenance_prunes_bounded_artifacts_and_preserves_metadata(tmp_path):
    m = _manager(tmp_path)
    now = time.time()

    # Debug-bundle count retention keeps newest only.
    root = Path(m.paths.home) / "debug-bundles"
    root.mkdir(parents=True, exist_ok=True)
    old = root / "netconfig-support-20200101-000000.tar.gz"
    new = root / "netconfig-support-20990101-000000.tar.gz"
    old.write_bytes(b"old")
    new.write_bytes(b"new")

    incident = m.incidents.create("retention", severity="LOW", created_by="test")
    case_root = Path(m.paths.home) / "case-exports"
    case_root.mkdir(parents=True, exist_ok=True)
    case = case_root / "netconfig-case-old.tar.gz"
    case.write_bytes(b"case")
    m.db.conn.execute(
        "INSERT INTO incident_case_exports(incident_id,export_key,filename,created_by,created_ts,size,sha256) "
        "VALUES(?,?,?,?,?,?,?)",
        (incident["id"], "CEX-OLD", case.name, "test", now - 3 * 86400, 4, "x"),
    )
    m.db.conn.commit()

    # One old unlinked trace is prunable. Incident-linked evidence is retained.
    # Insert directly so the test does not need an inventory device.
    m.db.conn.execute(
        "INSERT INTO protocol_trace_sessions(trace_key,device,protocol,status,created_ts,expires_ts,stopped_ts) "
        "VALUES(?,?,?,?,?,?,?)",
        ("PTR-OLD", "sw1", "cli_ssh", "STOPPED", now - 3 * 86400, now - 2 * 86400, now - 2 * 86400),
    )
    m.db.conn.execute(
        "INSERT INTO protocol_trace_sessions(trace_key,device,protocol,incident_id,status,created_ts,expires_ts,stopped_ts) "
        "VALUES(?,?,?,?,?,?,?,?)",
        ("PTR-INC", "sw1", "cli_ssh", incident["id"], "STOPPED", now - 3 * 86400,
         now - 2 * 86400, now - 2 * 86400),
    )
    m.db.conn.commit()

    result = dm.run_once(m, actor="test", now=now)
    assert old.name in result["debug_bundles_removed"]
    assert new.exists() and not old.exists()
    assert result["case_exports_removed"] == ["CEX-OLD"]
    assert not case.exists()
    row = m.db.conn.execute("SELECT * FROM incident_case_exports WHERE export_key='CEX-OLD'").fetchone()
    assert row is not None  # durable history remains
    assert result["protocol_traces_removed"] == ["PTR-OLD"]
    assert m.db.conn.execute("SELECT 1 FROM protocol_trace_sessions WHERE trace_key='PTR-OLD'").fetchone() is None
    assert m.db.conn.execute("SELECT 1 FROM protocol_trace_sessions WHERE trace_key='PTR-INC'").fetchone() is not None


def test_diagnostic_maintenance_zero_age_disables_case_and_trace_prune(tmp_path):
    m = _manager(tmp_path)
    m.settings["case_export_retention_days"] = 0
    m.settings["protocol_trace_retention_days"] = 0
    now = time.time()
    incident = m.incidents.create("retain", severity="LOW", created_by="test")
    case_root = Path(m.paths.home) / "case-exports"
    case_root.mkdir(parents=True, exist_ok=True)
    case = case_root / "netconfig-case-retain.tar.gz"
    case.write_bytes(b"case")
    m.db.conn.execute(
        "INSERT INTO incident_case_exports(incident_id,export_key,filename,created_by,created_ts,size,sha256) "
        "VALUES(?,?,?,?,?,?,?)",
        (incident["id"], "CEX-KEEP", case.name, "test", now - 100 * 86400, 4, "x"),
    )
    m.db.conn.execute(
        "INSERT INTO protocol_trace_sessions(trace_key,device,protocol,status,created_ts,expires_ts,stopped_ts) "
        "VALUES(?,?,?,?,?,?,?)",
        ("PTR-KEEP", "sw1", "snmp", "EXPIRED", now - 100 * 86400, now - 99 * 86400, now - 99 * 86400),
    )
    m.db.conn.commit()
    result = dm.run_once(m, actor="test", now=now)
    assert result["case_exports_removed"] == []
    assert result["protocol_traces_removed"] == []
    assert case.exists()
    assert m.db.conn.execute("SELECT 1 FROM protocol_trace_sessions WHERE trace_key='PTR-KEEP'").fetchone()


def test_closeout_cli_and_default_settings_expose_opt_in_maintenance():
    from netconfig.cli import build_parser
    from netconfig import config
    args = build_parser().parse_args(["debug", "maintenance", "--actor", "ops"])
    assert args.action == "maintenance"
    assert args.actor == "ops"
    assert config.DEFAULT_SETTINGS["diagnostic_maintenance_interval"] == 0
    assert config.DEFAULT_SETTINGS["debug_bundle_keep"] == 10
    assert config.DEFAULT_SETTINGS["case_export_retention_days"] == 0
    assert config.DEFAULT_SETTINGS["protocol_trace_retention_days"] == 0
