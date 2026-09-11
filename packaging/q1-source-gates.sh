#!/usr/bin/bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

require_tool() {
    command -v "$1" >/dev/null 2>&1 || {
        echo "Q-1 source gate requires $1; gate is NOT_RUN, not PASS" >&2
        exit 2
    }
}

require_tool python3
require_tool pytest
require_tool ruff
require_tool mypy

python3 - <<'PYVER'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Q-1 source gate requires Python 3.12+; gate is NOT_RUN, not PASS")
try:
    import psycopg  # noqa: F401
except Exception as exc:
    raise SystemExit(f"Q-1 source gate requires psycopg for PostgreSQL type-check boundaries; gate is NOT_RUN: {exc}")
PYVER

ruff check opt/netconfig/netconfig tests
mypy \
  opt/netconfig/netconfig/security.py \
  opt/netconfig/netconfig/credentials.py \
  opt/netconfig/netconfig/configmodel.py \
  opt/netconfig/netconfig/observability.py \
  opt/netconfig/netconfig/protocols.py \
  opt/netconfig/netconfig/storage_backend.py \
  opt/netconfig/netconfig/postgres_core.py \
  opt/netconfig/netconfig/postgres_backup.py \
  opt/netconfig/netconfig/qualification.py
python3 -m compileall -q opt/netconfig/netconfig
python3 -m py_compile usr/bin/netconfig
pytest -q tests/test_qualification_q1.py tests/test_platform_hardening_ph2.py tests/test_platform_hardening_ph3.py
pytest -q
PYTHONPATH=opt/netconfig python3 opt/netconfig/selftest.py

for script in packaging/*.sh; do
    bash -n "$script"
done

if LC_ALL=C grep -rIl $'\r' --include='*.py' --include='*.sh' --include='*.service' \
    --include='*.timer' --include='*.spec' --include='*.toml' --include='*.md' \
    --include='*.yml' --include='*.json' . | grep .; then
    echo "CR/CRLF offenders detected" >&2
    exit 1
fi

echo "Q-1 source gates: PASS"
