"""Prevent local tests from silently following the chat's launch folder."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_windows_source_tests.py"


def test_foreign_cwd_resolves_owning_source_tree(tmp_path):
    env = dict(os.environ)
    env.pop("NETCONFIG_TEST_DEPENDENCIES", None)
    result = subprocess.run([sys.executable, str(RUNNER), "--print-root"], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    paths = json.loads(result.stdout)
    assert Path(paths["root"]) == ROOT
    assert Path(paths["cwd"]) == ROOT
    assert Path(paths["python_source"]) == ROOT / "opt" / "netconfig"


def test_detached_runner_refuses_caller_cwd_fallback(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    detached = tools / RUNNER.name
    shutil.copyfile(RUNNER, detached)
    result = subprocess.run([sys.executable, str(detached), "--print-root"], cwd=ROOT,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
    assert "refusing caller-cwd fallback" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows-only fail-closed import guard")
def test_windows_pty_guard_never_simulates_ssh(monkeypatch):
    namespace = runpy.run_path(str(RUNNER))
    with monkeypatch.context() as context:
        context.setitem(sys.modules, "pty", None)
        namespace["_install_windows_pty_guard"]()
        with pytest.raises(RuntimeError, match="live AlmaLinux"):
            sys.modules["pty"].fork()
