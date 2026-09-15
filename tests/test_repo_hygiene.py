from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EOL_SUFFIXES = {
    ".py", ".sh", ".service", ".spec", ".timer", ".toml",
    ".yml", ".yaml", ".md", ".txt", ".json", ".conf", ".ini",
}


def test_gitattributes_enforces_lf_for_operational_text():
    text = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for pattern in ("*.py", "*.sh", "*.service", "*.spec", "*.timer"):
        assert f"{pattern}" in text
        line = next(line for line in text.splitlines() if line.startswith(pattern))
        assert "eol=lf" in line


def test_repository_operational_text_has_no_crlf():
    offenders = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or ".pytest_cache" in path.parts:
            continue
        if path.suffix.lower() not in EOL_SUFFIXES and path.name not in {"Dockerfile", "Makefile"}:
            continue
        raw = path.read_bytes()
        if b"\r" in raw:
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


REQUIRED_EXECUTABLES = (
    "usr/bin/netconfig",
    "packaging/build-rpm.sh",
    "packaging/inspect-rpm.sh",
    "packaging/q1-qualify-almalinux.sh",
    "packaging/q1-qualify-postgres.sh",
    "packaging/q1-source-gates.sh",
    "packaging/smoke-installed.sh",
)


def test_required_raw_source_executables_are_0755():
    for relative in REQUIRED_EXECUTABLES:
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_mode & 0o777 == 0o755, relative


def test_release_34_version_truth_is_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "opt/netconfig/netconfig/__init__.py").read_text(encoding="utf-8")
    spec = (ROOT / "packaging/netconfig.spec").read_text(encoding="utf-8")
    assert 'version = "2.0.0"' in pyproject
    assert '__version__ = "2.0.0"' in package
    assert "Version:        2.0.0" in spec
    assert "Release:        34%{?dist}" in spec
    for relative in (
        "README.md", "DEVELOPMENT.md", "AI_HANDOFF.md", "ROADMAP.md",
        "SECURITY.md", "API.md", "TESTING.md", "DEV_BASELINE.md",
        "HANDOVER_PROMPT.md", "patch.md", "AGENTS.md", "CLAUDE.md",
        "WEBGUI.md", "packaging/README.md", "opt/netconfig/CREDENTIALS.md",
        "opt/netconfig/INSTALL.md", "opt/netconfig/README.md", "opt/netconfig/WEBGUI.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        canonical = next(line for line in text.splitlines() if line.startswith("> **Canonical project state"))
        assert "2.0.0-34" in canonical, relative
        assert "UI-1" in canonical, relative
        assert "Release 33 full source baseline as the active implementation source" not in text, relative


def test_no_compound_statement_suite_on_same_line():
    import ast

    source_roots = (ROOT / "opt/netconfig/netconfig", ROOT / "tests")
    offenders = []
    suite_nodes = (
        ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
        ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
    )
    for source_root in source_roots:
        for path in source_root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, suite_nodes) and node.body and node.body[0].lineno == node.lineno:
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
                if isinstance(node, ast.Try):
                    if node.body and node.body[0].lineno == node.lineno:
                        offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
                    for handler in node.handlers:
                        if handler.body and handler.body[0].lineno == handler.lineno:
                            offenders.append(f"{path.relative_to(ROOT)}:{handler.lineno}")
    assert offenders == []
