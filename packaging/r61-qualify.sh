#!/usr/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
usage() {
  cat <<'EOF'
usage: ./packaging/r61-qualify.sh OUTPUT_DIR [--include-local] [--live] [--hook-dir DIR]

Runs the R61 Scale & Performance Qualification evidence runner. Local synthetic
results are not production capacity evidence. Live hooks must use the fixed hook
contract documented in R61_SCALE_PERFORMANCE.md.
EOF
}
[[ $# -ge 1 ]] || { usage; exit 2; }
OUT=$1; shift
exec python3 "$ROOT/qualification/r61_runner.py" --output-dir "$OUT" "$@"
