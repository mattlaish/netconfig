

# PH-5 Intent / Desired State Automation

Status: IMPLEMENTED_TESTING_DEFERRED

Scope: DesiredState, Intent lifecycle, revisions, drift detection, Change Plan generation, PH-4 transaction integration boundary, approval and audit linkage.


# PH-5 API and Operations Surface

Status: IMPLEMENTED_TESTING_DEFERRED

Added PH-5 API helpers, intent workflow surface, and Web Console Intent Automation entry point. Device changes remain delegated to PH-4 transaction workflow.

## NI-6 enterprise product integration

`Web/API -> Manager.analytics -> AnalyticsService -> Capacity/FailureRisk/Health + NI-2 topology truth -> network_insights / analytics_jobs`. The service boundary separates analysis from network execution. Reads are side-effect free; analysis/simulation requires explicit mutation requests. Impact uses `Manager.downstream_impact()` instead of constructing a generic undirected graph, so managed/resolved topology truth remains authoritative.
