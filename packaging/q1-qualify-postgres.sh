#!/usr/bin/bash
set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$PROJECT_ROOT"

for tool in pytest pg_dump pg_restore; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "Q-1 PostgreSQL qualification requires $tool; gate is NOT_RUN" >&2
        exit 2
    }
done
python3 - <<'PY'
try:
    import psycopg
except Exception as exc:
    raise SystemExit(f"Q-1 PostgreSQL qualification requires psycopg: {exc}")
PY

: "${NETCONFIG_TEST_PG_HOST:=127.0.0.1}"
: "${NETCONFIG_TEST_PG_PORT:=5432}"
: "${NETCONFIG_TEST_PG_DB:=netconfig_test}"
: "${NETCONFIG_TEST_PG_USER:=netconfig}"
if [[ -z ${NETCONFIG_TEST_PG_PASSWORD+x} ]]; then
    echo "NETCONFIG_TEST_PG_PASSWORD must be supplied by the qualification environment" >&2
    exit 2
fi
: "${NETCONFIG_TEST_PG_SSLMODE:=prefer}"

export NETCONFIG_INTEGRATION=1
export NETCONFIG_POSTGRES_BACKUP_INTEGRATION=1
export NETCONFIG_TEST_PG_HOST NETCONFIG_TEST_PG_PORT NETCONFIG_TEST_PG_DB
export NETCONFIG_TEST_PG_USER NETCONFIG_TEST_PG_PASSWORD NETCONFIG_TEST_PG_SSLMODE
pytest -q tests/integration/test_postgres_core_live.py

echo "Q-1 PostgreSQL service-backed qualification: PASS"
