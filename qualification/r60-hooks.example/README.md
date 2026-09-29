# R60 live qualification hooks

Copy this directory outside the source tree, replace only the fixed-name templates with executable lab-specific scripts, and pass it with `--hook-dir`. Hook exit codes: `0=PASS`, `20=BLOCKED_ENVIRONMENT`, `21=NOT_RUN`, any other non-zero=`FAIL`. Destructive gates additionally require `--allow-destructive`. Hooks may write bounded JSON metrics to `$NETCONFIG_R60_RESULT_PATH`. Never place credentials in hook stdout/stderr or result JSON.
