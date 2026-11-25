"""Settings → Features: per-area On / Hidden / Off for Incidents and security-tool intake.

The policy lives in ``workspaces``; ``features`` is the helper API over it. These
checks cover what an Off area must refuse end to end and that saved records survive.
"""
import json

import pytest

from test_web_ux import console as _console_fixture
from netconfig import features
from netconfig.apitokens import ApiTokens

console = _console_fixture


def _set(console, **modes):
    console.m.settings.update({f"workspace_{area}": mode for area, mode in modes.items()})


def _api(console, method, path, raw, form=None):
    code, _, body = console.request(method, path, form, headers={"Authorization": f"Bearer {raw}"})
    return code, json.loads(body)


def test_areas_default_to_on_and_features_mirrors_workspaces():
    assert features.mode({}, features.INCIDENTS) == "on"
    assert features.enabled({}, features.SECURITY_INTAKE)
    assert features.enabled({"workspace_incidents": "hidden"}, features.INCIDENTS)
    assert not features.enabled({"workspace_incidents": "off"}, features.INCIDENTS)


def test_settings_features_page_saves_modes_admin_only(console):
    admin = console.session()
    code, _, page = console.request("GET", "/settings?section=features", token=admin)
    assert code == 200 and 'name="workspace_incidents"' in page and 'name="workspace_security_intake"' in page
    form = {"csrf": "ux-csrf", "section": "features", "workspace_alerts": "on", "workspace_changes": "on",
            "workspace_incidents": "off", "workspace_security_intake": "hidden"}
    assert console.request("POST", "/settings-save", form, token=admin)[0] == 200
    assert console.m.settings["workspace_incidents"] == "off"
    viewer = console.session("viewer", "viewer1")
    console.request("POST", "/settings-save", {**form, "workspace_incidents": "on"}, token=viewer)
    assert console.m.settings["workspace_incidents"] == "off"


def test_incidents_off_refuses_everything_but_keeps_data(console):
    m = console.m
    item = m.incidents.create("Core link down", severity="HIGH", created_by="tester")
    admin = console.session()
    _set(console, incidents="off")
    _, _, home = console.request("GET", "/", token=admin)
    assert 'href="/incidents"' not in home
    for path in ("/incidents", f"/incident?ref={item['incident_key']}", "/operations?tab=workflow"):
        code, _, page = console.request("GET", path, token=admin)
        assert code == 403 and "Saved records are kept" in page and "/settings?section=features" in page, path
    code, _, _ = console.request("POST", "/incident-create", {"csrf": "ux-csrf", "title": "x", "severity": "LOW"}, token=admin)
    assert code == 403 and len(m.incidents.list()) == 1
    _, raw = ApiTokens(m.db.conn).create("inc", ["incident:read", "incident:write"], role="operator")
    code, payload = _api(console, "GET", "/api/v1/incidents", raw)
    assert code == 403 and payload["error"] == "workspace_off" and payload["workspace"] == "incidents"
    # Turning it back on restores the saved incident.
    _set(console, incidents="on")
    code, _, page = console.request("GET", "/incidents", token=admin)
    assert code == 200 and item["incident_key"] in page
    assert _api(console, "GET", "/api/v1/incidents", raw)[0] == 200


def test_turned_off_page_has_no_settings_link_for_viewers(console):
    _set(console, incidents="off")
    code, _, page = console.request("GET", "/incidents", token=console.session("viewer", "viewer1"))
    assert code == 403 and "/settings?section=features" not in page and "Ask an administrator" in page


def test_security_intake_off_refuses_ingest_and_source_changes(console):
    m = console.m
    _set(console, security_intake="off")
    _, raw = ApiTokens(m.db.conn).create("siem", ["external:ingest", "external:read"], role="operator")
    code, payload = _api(console, "POST", "/api/v1/external-evidence/siem-1/events", raw, {"event": "{}"})
    assert code == 403 and payload["workspace"] == "security_intake"
    assert _api(console, "GET", "/api/v1/external-sources", raw)[0] == 403
    admin = console.session()
    code, _, _ = console.request("POST", "/integration-source-save", {"csrf": "ux-csrf", "source_key": "x"}, token=admin)
    assert code == 403
    # Unauthenticated API callers still get 401, not a workspace hint.
    assert console.request("GET", "/api/v1/external-sources")[0] == 401


def test_incident_cli_refuses_when_off(tmp_path):
    from netconfig.manager import Manager
    from netconfig import config, cli
    home = tmp_path / "home"
    m = Manager(str(home))
    m.settings["workspace_incidents"] = "off"
    config.save_settings(m.paths, m.settings)
    m.close()
    with pytest.raises(SystemExit) as stop:
        cli.main(["--home", str(home), "incident", "list"])
    assert "workspace is off" in str(stop.value.code)


@pytest.mark.parametrize("path", ["/incidents", "/incident-anything", "/ops-workflow-plan"])
def test_console_prefixes(path):
    assert features.disabled_for_console({"workspace_incidents": "off"}, path) == features.INCIDENTS
    assert features.disabled_for_console({}, path) is None


def test_changes_off_keeps_independent_operations_and_navigation(console):
    _set(console, changes="off", incidents="on")
    admin = console.session()
    for tab in ("overview", "intelligence", "telemetry", "models", "ha"):
        code, _, body = console.request("GET", f"/operations?tab={tab}", token=admin)
        assert code == 200, (tab, body)
        assert 'href="/operations"' in body
        assert 'href="/operations?tab=structured"' not in body
        assert 'action="/ops-change-plan"' not in body
    for tab in ("structured", "desired", "intents", "campaigns", "workflow"):
        code, _, body = console.request("GET", f"/operations?tab={tab}", token=admin)
        assert code == 403 and "Changes is turned off" in body
    code, _, _ = console.request("POST", "/ops-structured-submit", {"csrf": "ux-csrf"}, token=admin)
    assert code == 403
    code, _, _ = console.request("POST", "/ops-analytics-expire", {"csrf": "ux-csrf"}, token=admin)
    assert code == 303
    _set(console, changes="on")
    assert console.request("GET", "/operations?tab=structured", token=admin)[0] == 200
