#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1789689600}"
exec python3 "$ROOT/tools/rpm-builder/rpm_builder.py" --repo-root "$ROOT" "$@"
