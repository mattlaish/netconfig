import json
import re
import stat
import subprocess
import tomllib
from pathlib import Path

import pytest

from netconfig.cli import build_parser
from netconfig.postgres_backup import (
    PostgresBackupError,
    backup_core_database,
    restore_core_database,
    sha256_file,
)
from netconfig.qualification import runtime_preflight


ROOT = Path(__file__).resolve().parents[1]


def _pg_settings():
    return {
        "core_db_backend": "postgres",
        "pg_host": "db.internal",
        "pg_port": 5432,
        "pg_dbname": "netconfig",
        "pg_user": "svc_netconfig",
        "pg_sslmode": "verify-full",
        "core_db_application_name": "netconfig-q1",
    }


def test_release_version_truth_is_coherent():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = re.search(
        r'__version__\s*=\s*"([^"]+)"',
        (ROOT / "opt/netconfig/netconfig/__init__.py").read_text(encoding="utf-8"),
    ).group(1)
    spec = (ROOT / "packaging/netconfig.spec").read_text(encoding="utf-8")
    rpm_version = re.search(r"^Version:\s*(\S+)", spec, re.M).group(1)
    rpm_release = int(re.search(r"^Release:\s*(\d+)", spec, re.M).group(1))
    assert project["project"]["version"] == package_version == rpm_version == "2.0.0"
    assert rpm_release >= 32


def test_q1_cli_surface_is_present():
    parser = build_parser()
    q = parser.parse_args(["qualify"])
    assert q.cmd == "qualify"
    b = parser.parse_args(["storage", "backup-postgres", "--output", "/tmp/core.dump"])
    assert b.action == "backup-postgres"
    r = parser.parse_args([
        "storage", "restore-postgres", "--input", "/tmp/core.dump",
        "--target-dbname", "netconfig_restore", "--confirm", "RESTORE_DATABASE",
    ])
    assert r.action == "restore-postgres"



def test_restore_cli_uses_recovery_safe_path_without_opening_active_core(tmp_path, monkeypatch, capsys):
    from netconfig import cli

    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps(_pg_settings()), encoding="utf-8")
    dump = tmp_path / "core.dump"
    dump.write_bytes(b"fake")
    monkeypatch.setenv("NETCONFIG_DB_PASSWORD", "recovery-secret")

    called = {}
    def fake_restore(settings, password, backup, **kwargs):
        called.update({"settings": settings, "password": password, "backup": backup, **kwargs})
        return {"restored": True, "target_database": kwargs["target_dbname"], "sha256": "a" * 64}

    monkeypatch.setattr("netconfig.postgres_backup.restore_core_database", fake_restore)
    cli.main([
        "--home", str(home), "storage", "restore-postgres",
        "--input", str(dump), "--target-dbname", "drill",
        "--confirm", "RESTORE_DATABASE", "--sha256", "a" * 64,
    ])
    assert called["password"] == "recovery-secret"
    assert called["target_dbname"] == "drill"
    out = json.loads(capsys.readouterr().out)
    assert out["restored"] is True
    assert "recovery-safe" in out["audit_note"]

def test_postgres_backup_uses_private_pgpass_atomic_output_and_checksum(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}" if name == "pg_dump" else None)
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = list(argv)
        seen["env"] = dict(kwargs["env"])
        pgpass = Path(seen["env"]["PGPASSFILE"])
        assert pgpass.is_file()
        assert stat.S_IMODE(pgpass.stat().st_mode) == 0o600
        assert "super-secret" in pgpass.read_text(encoding="utf-8")
        assert "super-secret" not in " ".join(argv)
        assert seen["env"]["PGSSLMODE"] == "verify-full"
        out = Path(argv[argv.index("--file") + 1])
        out.write_bytes(b"PGDMP\x01q1-test-payload")
        return subprocess.CompletedProcess(argv, 0, "", "")

    output = tmp_path / "core.dump"
    result = backup_core_database(_pg_settings(), "super-secret", str(output), runner=runner)
    assert output.read_bytes().startswith(b"PGDMP")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert result["sha256"] == sha256_file(output)
    assert Path(str(output) + ".sha256").read_text().startswith(result["sha256"])
    assert not Path(seen["env"]["PGPASSFILE"]).exists()


def test_postgres_backup_fails_closed_for_sqlite_existing_output_and_missing_tool(tmp_path, monkeypatch):
    settings = _pg_settings()
    settings["core_db_backend"] = "sqlite"
    with pytest.raises(PostgresBackupError):
        backup_core_database(settings, None, str(tmp_path / "x.dump"))

    output = tmp_path / "exists.dump"
    output.write_bytes(b"x")
    with pytest.raises(PostgresBackupError):
        backup_core_database(_pg_settings(), None, str(output))

    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(PostgresBackupError, match="pg_dump"):
        backup_core_database(_pg_settings(), None, str(tmp_path / "new.dump"))


def test_postgres_restore_requires_integrity_confirmation_and_separate_target(tmp_path, monkeypatch):
    backup = tmp_path / "core.dump"
    backup.write_bytes(b"PGDMP restore")
    digest = sha256_file(backup)
    Path(str(backup) + ".sha256").write_text(f"{digest}  core.dump\n")

    with pytest.raises(PostgresBackupError, match="confirm"):
        restore_core_database(_pg_settings(), "pw", str(backup), target_dbname="drill", confirm="NO")
    with pytest.raises(PostgresBackupError, match="currently configured"):
        restore_core_database(
            _pg_settings(), "pw", str(backup), target_dbname="netconfig", confirm="RESTORE_DATABASE")

    Path(str(backup) + ".sha256").write_text("0" * 64 + "  core.dump\n")
    with pytest.raises(PostgresBackupError, match="mismatch"):
        restore_core_database(
            _pg_settings(), "pw", str(backup), target_dbname="drill", confirm="RESTORE_DATABASE")

    Path(str(backup) + ".sha256").write_text(f"{digest}  core.dump\n")
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}" if name == "pg_restore" else None)
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = list(argv)
        pgpass = Path(kwargs["env"]["PGPASSFILE"])
        assert stat.S_IMODE(pgpass.stat().st_mode) == 0o600
        assert "pw" in pgpass.read_text()
        assert "pw" not in " ".join(argv)
        return subprocess.CompletedProcess(argv, 0, "", "")

    result = restore_core_database(
        _pg_settings(), "pw", str(backup), target_dbname="netconfig_drill",
        confirm="RESTORE_DATABASE", runner=runner)
    assert result["restored"] is True
    assert result["target_database"] == "netconfig_drill"
    assert "--clean" in seen["argv"] and "--exit-on-error" in seen["argv"]


def test_runtime_preflight_only_requires_gnmic_when_configured(monkeypatch):
    class Profiles:
        def __init__(self, rows):
            self.rows = rows
        def list(self):
            return self.rows

    class Manager:
        def __init__(self, rows):
            self.protocol_profiles = Profiles(rows)
        def storage_status(self):
            return {"backend": "sqlite", "reachable": True, "ok": True, "schema_revision": "ph3-1"}

    available = {"ssh": "/usr/bin/ssh", "openssl": "/usr/bin/openssl"}
    monkeypatch.setattr("shutil.which", lambda name: available.get(name))
    report = runtime_preflight(Manager([]))
    assert report["ok"] is True
    gnmi = next(row for row in report["checks"] if row["name"] == "gnmic")
    assert gnmi["required"] is False and gnmi["ok"] is False

    report = runtime_preflight(Manager([{"enabled": True, "protocol": "gnmi"}]))
    assert report["ok"] is False
    assert "gnmic" in report["required_failures"]


def test_systemd_units_retain_q1_hardening_and_postgres_credential_guidance():
    web = (ROOT / "usr/lib/systemd/system/netconfig-web.service").read_text(encoding="utf-8")
    backup = (ROOT / "usr/lib/systemd/system/netconfig-backup.service").read_text(encoding="utf-8")
    for text in (web, backup):
        assert "User=netconfig" in text
        assert "Group=netconfig" in text
        assert "StateDirectory=netconfig" in text
        assert "NoNewPrivileges=true" in text
        assert "ProtectSystem=strict" in text
        assert "PrivateTmp=true" in text
        assert "ReadWritePaths=/var/lib/netconfig" in text
        assert "postgres-core-password" in text


def test_q1_almalinux_qualification_script_requires_explicit_install_switch():
    script = (ROOT / "packaging/q1-qualify-almalinux.sh").read_text(encoding="utf-8")
    assert "--install" in script
    assert "NETCONFIG_Q1_ALLOW_INSTALL" in script
    assert '"almalinux"' in script and "VERSION_ID" in script
    assert "packaging/inspect-rpm.sh" in script
    assert "packaging/smoke-installed.sh" in script



def test_q1_almalinux_static_systemd_verify_uses_staged_root():
    script = (ROOT / "packaging/q1-qualify-almalinux.sh").read_text(encoding="utf-8")
    assert 'VERIFY_ROOT=$(mktemp -d' in script
    assert 'systemd-analyze verify --root="$VERIFY_ROOT"' in script
    assert 'install -m 0755 usr/bin/netconfig "$VERIFY_ROOT/usr/bin/netconfig"' in script


def test_q1_transfer_bundle_keeps_qualification_sources_and_control_paths():
    script = (ROOT / "packaging/prepare-transfer.ps1").read_text(encoding="utf-8")
    assert '"tests"' in script
    assert '".github"' in script
    for name in (
        '".gitattributes"',
        '"README.md"',
        '"API.md"',
        '"TESTING.md"',
        '"TESTING_RESULT_2026-09-12.md"',
        '"pyproject.toml"',
    ):
        assert name in script


def test_q1_source_gate_script_does_not_silently_skip_ruff_or_mypy():
    script = (ROOT / "packaging/q1-source-gates.sh").read_text(encoding="utf-8")
    assert "require_tool ruff" in script
    assert "require_tool mypy" in script
    assert "exit 2" in script
    assert "ruff check" in script
    assert "mypy" in script
