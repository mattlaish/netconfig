# R66 LIVE_SUPPORT hooks

These fixed-name hooks are examples only and intentionally non-executable. A designated supportability qualification environment may copy them to a private hook directory, implement each exact drill, mark them executable, and run `packaging/r66-qualify.sh ... --live --hook-dir DIR` with `NETCONFIG_R66_LIVE_SUPPORT=1`.

Exit `0` only with real target evidence, `20` for `BLOCKED_ENVIRONMENT`, and `21` for `NOT_RUN`. Write bounded machine-readable metrics to `$NETCONFIG_R66_RESULT_PATH`. Local/SQLite/simulated evidence must never return a live PASS. Hooks must not emit credentials, bearer tokens, communities, private keys, or raw secret-bearing configuration.
