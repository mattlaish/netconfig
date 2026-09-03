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
