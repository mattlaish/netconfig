# R65 LIVE_OPERATOR hooks

These fixed-name hooks are examples only and intentionally non-executable. A designated operator-qualification environment may copy them to a private hook directory, implement each exact journey, mark them executable, and run `packaging/r65-qualify.sh ... --live --hook-dir DIR` with `NETCONFIG_R65_LIVE_OPERATOR=1`.

Exit `0` only with real target evidence, `20` for `BLOCKED_ENVIRONMENT`, and `21` for `NOT_RUN`. Write bounded machine-readable metrics to `$NETCONFIG_R65_RESULT_PATH`. Local/SQLite/simulated evidence must never return a live PASS.
