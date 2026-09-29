# R61 live hook templates

Copy only the hooks you intend to execute into a separate qualification host directory and make those copies executable. These checked-in templates deliberately remain non-executable and return `20` (`BLOCKED_ENVIRONMENT`). Never place credentials in hook output. Each real hook may write bounded JSON to `$NETCONFIG_R61_RESULT_PATH` and must report actual workload size, duration, percentile/resource metrics and target identity.
