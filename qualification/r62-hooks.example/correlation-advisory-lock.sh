#!/usr/bin/env bash
set -euo pipefail
# Site-specific live PostgreSQL qualification hook. Replace this body only on the
# controlled qualification target and write bounded JSON to $NETCONFIG_R62_RESULT_PATH.
echo "R62 live PostgreSQL hook is not configured for this environment" >&2
exit 21
