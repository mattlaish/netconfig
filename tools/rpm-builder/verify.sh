#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RPM="${1:?usage: verify.sh RPM}"
exec python3 "$ROOT/tools/rpm-builder/verify_rpm.py" "$RPM" --repo-root "$ROOT"
