#!/usr/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

python3 -m py_compile qualification/q2_runner.py qualification/run_bounded_regression.py
bash -n packaging/q2-qualify.sh
python3 -m pytest -q tests/test_q2_production_qualification.py

for executable in qualification/q2_runner.py qualification/run_bounded_regression.py packaging/q2-qualify.sh packaging/q2-source-gates.sh; do
    if [[ ! -x "$executable" ]]; then
        echo "Q2 qualification executable mode missing: $executable" >&2
        exit 1
    fi
done

if grep -RIl $'\r' qualification packaging/q2-qualify.sh packaging/q2-source-gates.sh | grep .; then
    echo "Q2 qualification CR/CRLF offenders detected" >&2
    exit 1
fi

echo "Q2 qualification source gates: PASS"
