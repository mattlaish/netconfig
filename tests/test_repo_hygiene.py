from pathlib import Path
import subprocess


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
    "packaging/install-rpm.sh",
    "packaging/inspect-rpm.sh",
    "packaging/q1-qualify-almalinux.sh",
    "packaging/q1-qualify-postgres.sh",
    "packaging/q1-source-gates.sh",
    "packaging/smoke-installed.sh",
    "tools/rpm-builder/build.sh",
    "tools/rpm-builder/verify.sh",
    "tools/rpm-builder/rpm_builder.py",
    "tools/rpm-builder/verify_rpm.py",
)


def test_required_raw_source_executables_are_0755():
    for relative in REQUIRED_EXECUTABLES:
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_mode & 0o777 == 0o755, relative


def test_required_git_index_executables_are_100755():
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        import pytest
        pytest.skip("Git metadata unavailable in source archive")
    for relative in REQUIRED_EXECUTABLES:
        result = subprocess.run(
            ["git", "ls-files", "--stage", "--", relative],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        fields = result.stdout.strip().split()
        assert fields and fields[0] == "100755", f"{relative}: {result.stdout.strip()}"


def test_release_51_mc3_canonical_truth_is_consistent():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "opt/netconfig/netconfig/__init__.py").read_text(encoding="utf-8")
    spec = (ROOT / "packaging/netconfig.spec").read_text(encoding="utf-8")
    assert 'version = "2.0.0"' in pyproject
    assert '__version__ = "2.0.0"' in package
    assert "Version:        2.0.0" in spec
    assert "Release:        51%{?dist}" in spec
    for relative in (
        "README.md", "DEVELOPMENT.md", "AI_HANDOFF.md", "ROADMAP.md",
        "SECURITY.md", "API.md", "TESTING.md", "DEV_BASELINE.md",
        "HANDOVER_PROMPT.md", "patch.md", "AGENTS.md", "CLAUDE.md",
        "WEBGUI.md", "packaging/README.md", "opt/netconfig/CREDENTIALS.md",
        "opt/netconfig/INSTALL.md", "opt/netconfig/README.md", "opt/netconfig/WEBGUI.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        canonical = next(line for line in text.splitlines() if line.startswith("> **Canonical project state"))
        assert "2.0.0-51" in canonical, relative
        assert "Release 51" in canonical, relative
        assert "MC-3 Normalized Operational Evidence" in canonical, relative
        assert "NI-7 L3/VRF Path & Route Dependency Intelligence" in canonical, relative
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


def test_release_48_ci_enforces_git_modes_quality_pins_and_almalinux_build():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    quality = (ROOT / "requirements-quality.txt").read_text(encoding="utf-8")
    q1 = (ROOT / "packaging/q1-source-gates.sh").read_text(encoding="utf-8")
    assert "ruff==0.16.7" in quality
    assert "mypy==2.3.1" in quality
    assert "git ls-files --stage" in workflow
    assert "packaging/install-rpm.sh" in workflow
    assert "mode" in workflow and "100755" in workflow
    assert "EXPECTED_RUFF_VERSION=0.16.7" in q1
    assert "EXPECTED_MYPY_VERSION=2.3.1" in q1
    assert "almalinux-10-rpm-build:" in workflow
    assert "3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "5fda3b95a4ea91299a34e894583c3862153e4b97" in workflow


def test_release_48_required_executable_list_matches_ci_contract():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for relative in REQUIRED_EXECUTABLES:
        assert relative in workflow, relative


def test_release_48_installer_accepts_release_48_identity():
    installer = (ROOT / "packaging/install-rpm.sh").read_text(encoding="utf-8")
    alma = (ROOT / "packaging/q1-qualify-almalinux.sh").read_text(encoding="utf-8")
    assert '${RELEASE%%.*} != "48"' in installer
    assert 'expected NetConfig RPM release 48' in installer
    assert '2.0.0-48.*.noarch' in alma
    assert '${RELEASE%%.*} != "37"' not in installer
