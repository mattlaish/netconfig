import os
import subprocess
import sys
from pathlib import Path


def test_legacy_selftest_still_passes():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / "opt" / "netconfig")
    entry = [str(root / "opt" / "netconfig" / "selftest.py")]
    if os.name == "nt":
        entry = [str(root / "tools" / "run_windows_source_tests.py"), "--selftest"]
    cp = subprocess.run(
        [sys.executable, *entry],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert cp.returncode == 0, cp.stdout + "\n" + cp.stderr
