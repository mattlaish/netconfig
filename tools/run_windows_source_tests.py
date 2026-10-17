"""Root-anchored local tests; Windows PTY/SSH always fails closed."""
from __future__ import annotations

import json
import os
from pathlib import Path
import runpy
import sys
import types


def _install_windows_pty_guard() -> None:
    if os.name != "nt":
        return

    def unavailable(*args, **kwargs):
        raise RuntimeError("POSIX PTY/SSH requires the live AlmaLinux qualification host")

    pty = types.ModuleType("pty")
    pty.fork = unavailable
    sys.modules["pty"] = pty


def main(args: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if args is None else args)
    root = Path(__file__).resolve().parents[1]
    source = root / "opt" / "netconfig"
    if not (root / "pyproject.toml").is_file() or not (source / "netconfig" / "__init__.py").is_file():
        raise SystemExit("Runner is not inside a complete NetConfig source tree; refusing caller-cwd fallback")
    os.chdir(root)
    dependencies = os.environ.get("NETCONFIG_TEST_DEPENDENCIES", "")
    if dependencies:
        dependency_path = Path(dependencies).expanduser().resolve()
        if not dependency_path.is_dir():
            raise SystemExit("NETCONFIG_TEST_DEPENDENCIES must name an existing test-dependency directory")
        sys.path.insert(0, str(dependency_path))
    # Keep the actual source ahead of optional external test dependencies.
    sys.path.insert(0, str(source))
    if args == ["--print-root"]:
        print(json.dumps({"root": str(root), "cwd": str(Path.cwd()), "python_source": str(source)}))
        return 0
    _install_windows_pty_guard()
    if os.name == "nt":
        print("Windows source-only testing: real POSIX PTY/SSH is blocked, not simulated.", file=sys.stderr)
    if args == ["--selftest"]:
        runpy.run_path(str(source / "selftest.py"), run_name="__main__")
        return 0
    try:
        import pytest
    except ImportError as exc:
        raise SystemExit("Install pytest in this Python environment or set NETCONFIG_TEST_DEPENDENCIES") from exc
    return pytest.main(["-c", str(root / "pyproject.toml"), "--rootdir", str(root), *args])


if __name__ == "__main__":
    raise SystemExit(main())
