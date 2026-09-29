# R64 independent abuse qualification hooks

These fixed-name hooks are templates only and deliberately non-executable in source control. Copy them to a controlled assessor-owned hook directory, implement the documented gate, make only the copied hook executable, and run `packaging/r64-qualify.sh --live --hook-dir ...` with `NETCONFIG_R64_LIVE_ABUSE=1` on the designated target. Exit 0=PASS, 20=BLOCKED_ENVIRONMENT, 21=NOT_RUN, anything else=FAIL. Never place credentials in stdout/stderr or result JSON.
