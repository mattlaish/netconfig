"""Settings → Features: Incidents and security-tool intake can be turned off and on."""
import json

import pytest

from test_web_ux import console as _console_fixture
from netconfig import features
from netconfig.apitokens import ApiTokens

console = _console_fixture


def _set(console, **values):
    console.m.settings.update(values)


def _api(console, method, path, raw, form=None):
    code, _, body = console.request(method, path, form, headers={"Authorization": f"Bearer {raw}"})
    return code, json.loads(body)


def test_both_areas_default_to_on():
    assert features.enabled({}, features.INCIDENTS) and features.enabled({}, features.SECURITY_INTAKE)
    assert not features.enabled({features.INCIDENTS: False}, features.INCIDENTS)


def test_settings_features_page_saves_switches_admin_only(console):
    admin = console.session()
    code, _, page = console.request("GET", "/settings?section=features", token=admin)
    assert code == 200 and "Incidents &amp; case tracking" in page and "Security-tool intake" in page
    code, _, page = console.request("POST", "/settings-save", {"csrf": "ux-csrf", "section": "features",
                                    features.SECURITY_INTAKE: "1"}, token=admin)
    assert code == 200 and "Features settings saved" in page
    assert console.m.settings[features.INCIDENTS] is False and console.m.settings[features.SECURITY_INTAKE] is True
    viewer = console.session("viewer", "viewer1")
    console.request("POST", "/settings-save", {"csrf": "ux-csrf", "section": "features",
                    features.INCIDENTS: "1", features.SECURITY_INTAKE: "1"}, token=viewer)
    assert console.m.settings[features.INCIDENTS] is False


def test_incidents_off_hides_and_refuses_everything_but_keeps_data(console):
    m = console.m
    item = m.incidents.create("Core link down", severity="HIGH", created_by="tester")
    admin = console.session()
    _set(console, **{features.INCIDENTS: False})
    _, _, home = console.request("GET", "/", token=admin)
    assert 'href="/incidents"' not in home
    for path in ("/incidents", f"/incident?ref={item['incident_key']}", "/operations?tab=workflow"):
        code, _, page = console.request("GET", path, token=admin)
        assert code == 404 and "is turned off" in page and "/settings?section=features" in page, path
    code, _, _ = console.request("POST", "/incident-create", {"csrf": "ux-csrf", "title": "x", "severity": "LOW"}, token=admin)
    assert code == 404 and len(m.incidents.list()) == 1
    code, _, page = console.request("GET", "/operations", token=admin)
    assert code == 200 and "tab=workflow" not in page
    code, _, dash = console.request("GET", "/dashboard", token=admin)
    assert code == 200 and "/incidents" not in dash
    _, _, found = console.request("GET", "/search?q=Core+link", token=admin)
    assert item["incident_key"] not in found
    _, raw = ApiTokens(m.db.conn).create("inc", ["incident:read", "incident:write"], role="operator")
    code, payload = _api(console, "GET", "/api/v1/incidents", raw)
    assert code == 404 and payload["error"] == "feature_disabled" and payload["feature"] == features.INCIDENTS
    # Turning it back on restores the saved incident.
    _set(console, **{features.INCIDENTS: True})
    code, _, page = console.request("GET", "/incidents", token=admin)
    assert code == 200 and item["incident_key"] in page
    code, payload = _api(console, "GET", "/api/v1/incidents", raw)
    assert code == 200


def test_viewer_sees_no_settings_link_on_turned_off_page(console):
    _set(console, **{features.INCIDENTS: False})
    code, _, page = console.request("GET", "/incidents", token=console.session("viewer", "viewer1"))
    assert code == 404 and "/settings?section=features" not in page


def test_security_intake_off_refuses_ingest_and_source_changes(console):
    m = console.m
    _set(console, **{features.SECURITY_INTAKE: False})
    _, raw = ApiTokens(m.db.conn).create("siem", ["external:ingest", "external:read"], role="operator")
    code, payload = _api(console, "POST", "/api/v1/external-evidence/siem-1/events", raw, {"event": "{}"})
    assert code == 404 and payload["feature"] == features.SECURITY_INTAKE
    code, payload = _api(console, "GET", "/api/v1/external-sources", raw)
    assert code == 404
    admin = console.session()
    code, _, _ = console.request("POST", "/integration-source-save", {"csrf": "ux-csrf", "source_key": "x"}, token=admin)
    assert code == 404
    code, _, page = console.request("GET", "/settings?section=integrations", token=admin)
    assert code == 200 and "is turned off" in page
    # Unauthenticated API callers still get 401, not a feature hint.
    code, _, _ = console.request("GET", "/api/v1/external-sources")
    assert code == 401


def test_incident_cli_refuses_when_off(tmp_path, capsys):
    from netconfig.manager import Manager
    from netconfig import config, cli
    home = tmp_path / "home"
    m = Manager(str(home))
    m.settings[features.INCIDENTS] = False
    config.save_settings(m.paths, m.settings)
    m.close()
    with pytest.raises(SystemExit) as stop:
        cli.main(["--home", str(home), "incident", "list"])
    assert stop.value.code == 2 and "turned off" in capsys.readouterr().err


@pytest.mark.parametrize("path", ["/incidents", "/incident-anything", "/ops-workflow-plan"])
def test_console_prefixes(path):
    assert features.disabled_for_console({features.INCIDENTS: False}, path) == features.INCIDENTS
    assert features.disabled_for_console({}, path) is None
