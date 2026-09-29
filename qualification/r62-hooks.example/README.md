# R62 live PostgreSQL hooks

Copy this directory outside the source tree and replace only the fixed hook bodies on the controlled qualification target. Hooks receive `NETCONFIG_R62_GATE_ID`, `NETCONFIG_R62_RESULT_PATH`, and `NETCONFIG_R62_REPO_ROOT`. Exit 0=PASS, 20=BLOCKED_ENVIRONMENT, 21=NOT_RUN, any other code=FAIL. Never place credentials in result JSON or stdout/stderr.
