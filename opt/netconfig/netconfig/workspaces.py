"""Workspace visibility and entry-point policy."""

LABELS = {
    "alerts": "Alerts",
    "incidents": "Incidents",
    "changes": "Changes",
    "security_intake": "External evidence integrations",
}
MODES = ("on", "hidden", "off")


def mode(settings, area):
    value = settings.get(f"workspace_{area}")
    if value in MODES:
        return value
    legacy = settings.get(f"web_{area}_enabled")
    return "hidden" if legacy is False else "on"


def enabled(settings, area):
    return mode(settings, area) != "off"


def pending_approvals(manager):
    row = manager.db.conn.execute(
        "SELECT COUNT(*) AS total FROM change_requests WHERE status='pending'").fetchone()
    return int(row["total"])


def visible(manager, area):
    state = mode(getattr(manager, "settings", {}), area)
    if state != "hidden":
        return state == "on"
    queries = {
        "alerts": ("SELECT 1 FROM operational_alerts WHERE state IN ('OPEN','ACKNOWLEDGED') "
                   "UNION ALL SELECT 1 FROM alerts WHERE state='firing' LIMIT 1"),
        "incidents": "SELECT 1 FROM incidents WHERE status <> 'CLOSED' LIMIT 1",
        "changes": "SELECT 1 FROM change_requests WHERE status='pending' LIMIT 1",
    }
    query = queries.get(area)
    db = getattr(manager, "db", None)
    return bool(query and db and db.conn.execute(query).fetchone())


API_AREAS = {
    "alerts": {"alerts", "operational-alerts", "maintenance-windows", "operational-reports", "report-schedules"},
    "incidents": {"incidents", "operator-workflows"},
    "changes": {"automation", "automation-requests", "change-planning", "structured-changes",
                "desired-states", "desired-state-runs", "campaigns", "operator-workflows"},
    "security_intake": {"external-sources", "external-evidence"},
}


def disabled_api_area(settings, path):
    section = path.removeprefix("/api/v1/").split("/", 1)[0]
    return next((area for area, sections in API_AREAS.items()
                 if section in sections and not enabled(settings, area)), None)


def disabled_web_area(settings, path):
    path = path.strip("/")
    pairs = (
        ("alerts", {"alerts", "op-alerts"}, ("alert-rule-", "op-alert-", "maintenance-", "report-schedule-")),
        ("incidents", {"incident", "incidents"}, ("incident-", "ops-workflow-")),
        ("changes", {"operations", "request", "requests", "automation", "run-adhoc"},
         ("request-", "script-", "ops-structured-", "ops-desired-", "ops-campaign-", "ops-change-", "ops-workflow-")),
        ("security_intake", set(), ("integration-source-",)),
    )
    return next((area for area, pages, prefixes in pairs
                 if (path in pages or path.startswith(prefixes)) and not enabled(settings, area)), None)
