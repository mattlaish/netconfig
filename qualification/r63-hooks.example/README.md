# R63 live HA hooks

These names are fixed contracts consumed by `qualification/r63_runner.py`. The examples fail closed with exit 20. Replace them only on a designated multi-node PostgreSQL HA lab. Exit `0` only after the named failure-domain behavior is actually observed; exit `20` for blocked environment and `21` when deliberately not run. Optional machine-readable metrics may be written to `$NETCONFIG_R63_RESULT_PATH`.
