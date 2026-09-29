#!/usr/bin/env bash
set -euo pipefail
printf '{"status":"BLOCKED_ENVIRONMENT","reason":"template hook: implement on designated live operator qualification environment"}\n' > "${NETCONFIG_R65_RESULT_PATH:?}"
exit 20
