# R67 LIVE_RC hook contract

These fixed-name hooks are examples only. They deliberately return `20` (`BLOCKED_ENVIRONMENT`) until an independent operator replaces each body with a bounded test for the named production gate. R67 accepts live execution only with `NETCONFIG_R67_LIVE_RC=1`; exit `0` means PASS, `20` means BLOCKED_ENVIRONMENT, `21` means NOT_RUN, and any other non-zero exit means FAIL.

Every hook receives `NETCONFIG_R67_GATE_ID`, `NETCONFIG_R67_RESULT_PATH`, `NETCONFIG_R67_REPO_ROOT`, and `NETCONFIG_R67_CANDIDATE_SHA256`. Evidence is valid only for that exact candidate fingerprint. Any source/package change invalidates prior R67 live evidence.
