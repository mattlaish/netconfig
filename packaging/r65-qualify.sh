#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
exec python3 "$ROOT/qualification/r65_runner.py" --output-dir "${1:?usage: r65-qualify.sh OUTPUT_DIR [runner args...]}" "${@:2}"
