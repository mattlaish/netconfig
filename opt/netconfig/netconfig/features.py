"""Optional product areas: a small helper API over ``workspaces``.

``workspaces`` holds the policy (On / Hidden / Off per area, stored as
``workspace_<area>`` in settings, managed in Settings → Features). This module
keeps the older Features names used by tests and integrations and adds the
operator wording for a turned-off area. It has no separate settings, so there is
only one switch per area.
"""
from __future__ import annotations

from . import workspaces

INCIDENTS = "incidents"
SECURITY_INTAKE = "security_intake"
ALERTS = "alerts"
CHANGES = "changes"

LABELS = workspaces.LABELS


def mode(settings, area):
    """"on", "hidden" or "off"."""
    return workspaces.mode(settings or {}, area)


def enabled(settings, area):
    """False only when the area is Off; Hidden areas still work."""
    return workspaces.enabled(settings or {}, area)


def disabled_for_console(settings, path):
    return workspaces.disabled_web_area(settings or {}, path)


def disabled_for_api(settings, path):
    return workspaces.disabled_api_area(settings or {}, path)


def off_message(area):
    return (f"{LABELS[area]} is turned off. Saved records are kept and reappear when it is "
            "turned back on.")
