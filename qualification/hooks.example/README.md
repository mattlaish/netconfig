# Q2 live hook examples

Copy only the hooks you intend to execute into a separate qualification-host hook directory, make them executable, and replace the fail-closed placeholder with environment-specific validation. Do not point the runner at this example directory as production evidence.

A hook receives:

- `NETCONFIG_Q2_GATE_ID`
- `NETCONFIG_Q2_REPO_ROOT`
- `NETCONFIG_Q2_RESULT_PATH`

Write only non-secret metrics to `NETCONFIG_Q2_RESULT_PATH`. Exit `0` for PASS, `20` for BLOCKED_ENVIRONMENT, `21` for NOT_RUN, and any other non-zero code for FAIL.
