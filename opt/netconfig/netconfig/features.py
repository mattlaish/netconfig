"""Optional product areas an administrator can turn off in Settings → Features.

Turning an area off hides it in the console, refuses its console/API/CLI entry
points and stops new records from being created. Saved records are kept and
reappear when the area is turned back on. Nothing creates incidents or external
evidence in the background, so gating the entry points is sufficient.
"""
from __future__ import annotations

INCIDENTS = "incidents_enabled"
SECURITY_INTAKE = "security_intake_enabled"

LABELS = {
    INCIDENTS: "Incidents & case tracking",
    SECURITY_INTAKE: "Security-tool intake (SIEM, NDR, EDR, WAF…)",
}

DESCRIPTIONS = {
    INCIDENTS: ("Incident records with status, linked evidence, timeline, protocol traces and exportable "
                "case packages, plus the Incident Workflow in Operations."),
    SECURITY_INTAKE: ("Lets security and monitoring tools push events into NetConfig through scoped API "
                      "tokens (Settings → Integrations). Events can be linked to incidents."),
}

# Path prefixes refused while an area is off. Console paths are matched on the
# path only; operations tabs are handled by the operations page itself.
_CONSOLE_PREFIXES = {
    INCIDENTS: ("/incident", "/ops-workflow-"),
    SECURITY_INTAKE: ("/integration-source-",),
}
_API_PREFIXES = {
    INCIDENTS: ("/api/v1/incidents",),
    SECURITY_INTAKE: ("/api/v1/external-evidence", "/api/v1/external-sources"),
}


def enabled(settings, key):
    """Areas default to on; only an explicit false turns one off."""
    return (settings or {}).get(key, True) is not False


def _match(path, prefixes):
    return any(path == p or path.startswith(p) for p in prefixes)


def disabled_for_console(settings, path):
    for key, prefixes in _CONSOLE_PREFIXES.items():
        if not enabled(settings, key) and _match(path, prefixes):
            return key
    return None


def disabled_for_api(settings, path):
    for key, prefixes in _API_PREFIXES.items():
        if not enabled(settings, key) and _match(path, prefixes):
            return key
    return None


def off_message(key):
    return f"{LABELS[key]} is turned off. An administrator can turn it on in Settings → Features."
