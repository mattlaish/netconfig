from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "opt/netconfig"))

from netconfig.lifecycle import (  # noqa: E402
    CONFIRM_RESTORE,
    LifecycleError,
    create_local_snapshot,
    retention_candidates,
    restore_local_snapshot,
    switch_postgres_database,
    verify_live_state,
    verify_local_snapshot,
)


def _home(tmp_path: Path, *, postgres: bool = False) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps({
        "core_db_backend": "postgres" if postgres else "sqlite",
        "pg_dbname": "netconfig_prod" if postgres else "",
    }), encoding="utf-8")
    (home / "inventory.db").write_bytes(b"sqlite-state-v1")
    (home / "credentials.vault").write_bytes(b"encrypted-vault")
    cfg = home / "configs" / "sw1"
    cfg.mkdir(parents=True)
    (cfg / "latest.txt").write_text("hostname sw1\n", encoding="utf-8")
    return home


def _config(tmp_path: Path, home: Path, secret: Path | None = None) -> Path:
    p = tmp_path / "netconfig.default"
    lines = [f"NETCONFIG_HOME={home}"]
    if secret:
        lines.append(f"NETCONFIG_MASTER_FILE={secret}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_r60_snapshot_verify_and_live_state_round_trip(tmp_path):
    home = _home(tmp_path)
    config = _config(tmp_path, home)
    snap = tmp_path / "snap"
    out = create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
    assert out["verified"] is True
    assert verify_local_snapshot(str(snap))["verified"] is True
    assert verify_live_state(str(snap), home=str(home), config_path=str(config))["verified"] is True


def test_r60_snapshot_rejects_symlink_in_state(tmp_path):
    home = _home(tmp_path)
    config = _config(tmp_path, home)
    (home / "escape").symlink_to(tmp_path / "outside")
    with pytest.raises(LifecycleError, match="symbolic links"):
        create_local_snapshot(str(home), str(tmp_path / "snap"), config_path=str(config), min_free_bytes=0)


def test_r60_snapshot_detects_corruption(tmp_path):
    home = _home(tmp_path)
    config = _config(tmp_path, home)
    snap = tmp_path / "snap"
    create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
    (snap / "state" / "inventory.db").write_bytes(b"tampered")
    out = verify_local_snapshot(str(snap))
    assert out["verified"] is False
    assert any("checksum mismatch" in e for e in out["errors"])


def test_r60_external_secret_is_fingerprinted_not_copied(tmp_path):
    home = _home(tmp_path)
    secret = tmp_path / "vault-master"
    secret.write_text("dont-copy-me", encoding="utf-8")
    secret.chmod(0o600)
    config = _config(tmp_path, home, secret)
    snap = tmp_path / "snap"
    create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["external_fingerprints"][0]["sha256"]
    assert manifest["external_fingerprints"][0]["copied"] is False
    assert not any(p.read_bytes() == b"dont-copy-me" for p in snap.rglob("*") if p.is_file())


def test_r60_external_change_fails_preservation_verification(tmp_path):
    home = _home(tmp_path)
    secret = tmp_path / "vault-master"
    secret.write_text("before", encoding="utf-8")
    secret.chmod(0o600)
    config = _config(tmp_path, home, secret)
    snap = tmp_path / "snap"
    create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
    secret.write_text("after", encoding="utf-8")
    out = verify_local_snapshot(str(snap))
    assert out["verified"] is False
    assert any("external preservation fingerprint changed" in e for e in out["errors"])


def test_r60_restore_requires_explicit_confirmation(tmp_path):
    home = _home(tmp_path)
    config = _config(tmp_path, home)
    snap = tmp_path / "snap"
    create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
    with pytest.raises(LifecycleError, match=CONFIRM_RESTORE):
        restore_local_snapshot(str(snap), home=str(home), config_path=str(config), confirm="no")


def test_r60_restore_returns_prior_local_state_and_quarantines_failed_state(tmp_path):
    home = _home(tmp_path)
    config = _config(tmp_path, home)
    snap = tmp_path / "snap"
    create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
    (home / "inventory.db").write_bytes(b"migrated-bad-state")
    (home / "new-from-failed-upgrade").write_text("x", encoding="utf-8")
    out = restore_local_snapshot(str(snap), home=str(home), config_path=str(config), confirm=CONFIRM_RESTORE)
    assert out["restored"] is True
    assert Path(out["quarantine"]).is_dir()
    assert (home / "inventory.db").read_bytes() == b"sqlite-state-v1"
    assert not (home / "new-from-failed-upgrade").exists()
    assert verify_live_state(str(snap), home=str(home), config_path=str(config))["verified"] is True


def test_r60_postgres_switch_is_explicit_and_atomic(tmp_path):
    home = _home(tmp_path, postgres=True)
    with pytest.raises(LifecycleError, match="SWITCH_POSTGRES_ROLLBACK"):
        switch_postgres_database(str(home), "netconfig_rollback", confirm="no")
    out = switch_postgres_database(str(home), "netconfig_rollback", confirm="SWITCH_POSTGRES_ROLLBACK")
    assert out["switched"] is True
    settings = json.loads((home / "settings.json").read_text(encoding="utf-8"))
    assert settings["pg_dbname"] == "netconfig_rollback"
    assert not list(home.glob("*.r60-switch.tmp"))


def test_r60_postgres_switch_rejects_sql_like_name(tmp_path):
    home = _home(tmp_path, postgres=True)
    with pytest.raises(LifecycleError, match="invalid PostgreSQL"):
        switch_postgres_database(str(home), "db;DROP DATABASE x", confirm="SWITCH_POSTGRES_ROLLBACK")


def test_r60_retention_candidates_are_oldest_beyond_keep(tmp_path, monkeypatch):
    home = _home(tmp_path)
    config = _config(tmp_path, home)
    root = tmp_path / "snaps"
    root.mkdir()
    for i in range(4):
        snap = root / f"s{i}"
        create_local_snapshot(str(home), str(snap), config_path=str(config), min_free_bytes=0)
        manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        manifest["created_unix"] = float(i)
        (snap / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    candidates = retention_candidates(str(root), keep=2)
    assert [Path(x).name for x in candidates] == ["s1", "s0"]


def test_r60_cli_lifecycle_does_not_initialize_manager_for_restore(tmp_path):
    source = (ROOT / "opt/netconfig/netconfig/cli.py").read_text(encoding="utf-8")
    main = source[source.index("def main("):]
    assert 'if args.cmd == "lifecycle"' in main
    assert main.index('if args.cmd == "lifecycle"') < main.index("m = Manager(args.home)")


def test_r60_upgrade_wrapper_has_fail_closed_rollback_boundaries():
    path = ROOT / "packaging/r60-lifecycle-upgrade.sh"
    source = path.read_text(encoding="utf-8")
    assert path.stat().st_mode & 0o111
    for token in (
        "--allow-destructive", "flock -n", "systemctl mask --runtime", "dnf downgrade -y",
        "RESTORE_LOCAL_STATE", "verify-live", "RECOVERY_REQUIRED", "ROLLBACK_VERIFIED",
        "SWITCH_POSTGRES_ROLLBACK", "postgres-ready-marker",
    ):
        assert token in source
    assert "eval " not in source
    assert "bash -c" not in source


def test_r60_upgrade_wrapper_only_supports_r59_to_r60():
    source = (ROOT / "packaging/r60-lifecycle-upgrade.sh").read_text(encoding="utf-8")
    assert "${t_rel%%.*} == 60" in source
    assert "${r_rel%%.*} == 59" in source
    assert "supported upgrade source is release 59" in source


def test_r60_historical_wrapper_remains_r59_to_r60_while_current_package_advances():
    spec = (ROOT / "packaging/netconfig.spec").read_text(encoding="utf-8")
    installer = (ROOT / "packaging/install-rpm.sh").read_text(encoding="utf-8")
    assert "Release:        67.2%{?dist}" in spec
    assert "release 67" in installer.lower()
    wrapper = (ROOT / "packaging/r60-lifecycle-upgrade.sh").read_text(encoding="utf-8")
    assert "${t_rel%%.*} == 60" in wrapper
    assert "${r_rel%%.*} == 59" in wrapper


def test_r60_shell_syntax():
    cp = subprocess.run(["bash", "-n", str(ROOT / "packaging/r60-lifecycle-upgrade.sh")], capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr
