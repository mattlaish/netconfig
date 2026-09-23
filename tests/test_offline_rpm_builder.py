from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/rpm-builder/rpm_builder.py"
VERIFY = ROOT / "tools/rpm-builder/verify_rpm.py"


def _build(tmp_path: Path, name: str = "netconfig.rpm") -> Path:
    out = tmp_path / name
    subprocess.run(
        [sys.executable, str(BUILDER), "--repo-root", str(ROOT), "--output", str(out)],
        check=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return out


def test_offline_rpm_builder_emits_release_42_and_verifies(tmp_path):
    rpm = _build(tmp_path)
    result = subprocess.run(
        [sys.executable, str(VERIFY), str(rpm), "--repo-root", str(ROOT)],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: RPM structure" in result.stdout
    assert rpm.read_bytes()[:4] == b"\xed\xab\xee\xdb"


def test_offline_rpm_builder_is_reproducible(tmp_path):
    a = _build(tmp_path, "a.rpm")
    b = _build(tmp_path, "b.rpm")
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


def test_offline_rpm_builder_uses_no_third_party_python_imports():
    source = BUILDER.read_text(encoding="utf-8") + VERIFY.read_text(encoding="utf-8")
    for forbidden in ("requests", "rpmfile", "rpmpack", "urllib3", "httpx"):
        assert f"import {forbidden}" not in source
        assert f"from {forbidden}" not in source


def test_offline_rpm_builder_is_not_the_production_qualification_authority():
    readme = (ROOT / "tools/rpm-builder/README.md").read_text(encoding="utf-8")
    assert "does **not** replace the canonical AlmaLinux `rpmbuild` path" in readme
    assert "Do not promote" in readme


def test_offline_rpm_builder_ignores_python_cache_tree(tmp_path):
    cache = ROOT / "opt/netconfig/netconfig/__pycache__/rpm-builder-regression.pyc"
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(b"not-real-bytecode")
    try:
        rpm = _build(tmp_path, "cache-proof.rpm")
        result = subprocess.run(
            [sys.executable, str(VERIFY), str(rpm), "--repo-root", str(ROOT)],
            check=False, cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        cache.unlink(missing_ok=True)
        try:
            cache.parent.rmdir()
        except OSError:
            pass
