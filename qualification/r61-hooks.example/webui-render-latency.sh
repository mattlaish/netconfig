#!/usr/bin/bash
set -euo pipefail
# Template only. Copy to a qualification-host hook directory, implement the real
# production workload, review it, then chmod 0755 on the copy.
echo "R61 live gate template is not configured on this host" >&2
exit 20
