"""Tool caches must never enter the SBOM / release manifest.

Running the linter (CI does) previously added .ruff_cache files to the SBOM and
made the release-metadata drift check fail.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("release_metadata", ROOT / "tools/release_metadata.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tool_caches_are_excluded_from_release_metadata():
    tool = _tool()
    for cache in (".ruff_cache", ".pytest_cache", ".mypy_cache", "__pycache__"):
        assert cache in tool.EXCLUDE_PARTS
    probe = ROOT / ".ruff_cache" / "probe-metadata-exclusion"
    probe.parent.mkdir(exist_ok=True)
    probe.write_text("cache", encoding="utf-8")
    try:
        names = [str(p) for p in tool.source_files()]
        assert not any(".ruff_cache" in n for n in names)
    finally:
        probe.unlink()
