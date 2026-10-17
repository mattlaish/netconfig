"""Operator-facing copy is clear without changing machine-facing controls."""
from html.parser import HTMLParser
import re

import pytest

from test_ui1_web_console import _manager, _request, _start_console, _stop


class VisibleCopy(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
        self.controls = set()
        self.actions = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if attributes.get("name"):
            self.controls.add(attributes["name"])
        if attributes.get("action"):
            self.actions.add(attributes["action"])
        if tag in {"script", "style", "pre", "code"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "pre", "code"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


@pytest.fixture(scope="module")
def wording_console(tmp_path_factory):
    manager = _manager(tmp_path_factory.mktemp("operator-copy"))
    server, thread, token, _csrf = _start_console(manager, "admin")
    yield manager, server, token
    _stop(server, thread, manager)


@pytest.mark.parametrize(("path", "expected"), [
    ("/dashboard", "Analysis service health"),
    ("/events", "Events record changes in monitoring status"),
    ("/alerts?view=active", "Each monitored condition has one alert"),
    ("/settings?section=monitoring", "Alerts & scheduled reports"),
    ("/settings?section=db", "The main database stores NetConfig settings"),
    ("/settings?section=integrations", "Connected tools send monitoring and security records"),
    ("/operations?tab=workflow", "Incident Workflow"),
    ("/operations?tab=intelligence", "Path & Change Planning"),
    ("/operations?tab=structured", "Device change history"),
    ("/operations?tab=models", "Device models"),
    ("/operations?tab=intents", "Choose a change workflow"),
    ("/operations?tab=ha", "Only an administrator can retry"),
    ("/diagnostics", "NetConfig Service Status"),
    ("/dependencies", "Shows dependencies you configured"),
    ("/traces", "Traces record connection and collection activity"),
    ("/snmp", "SNMP vendor profiles"),
    ("/mib", "device health cards"),
    ("/traffic", "Records are held in memory"),
])
def test_console_uses_operator_copy_without_implicit_device_io(wording_console, monkeypatch, path, expected):
    manager, server, token = wording_console

    def forbidden_io(*args, **kwargs):
        raise AssertionError("Rendering must not start device collection")

    monkeypatch.setattr(manager, "collect", forbidden_io)
    status, _headers, data = _request(server, token, "GET", path)
    assert status == 200
    text = data.decode()
    parser = VisibleCopy()
    parser.feed(text)
    visible = " ".join(parser.parts)
    assert expected in visible
    assert not re.search(r"\b(?:MC|NI|PH|VM|NA|UI)-\d+(?:\.\d+)?\b|\bR6\d(?:\.\d+)?\b", visible)
    assert not re.search(r"\b(?:canonical|persisted|bounded|durable|provenance|preflight|bootstrap)\b", visible, re.I)
    if "section=monitoring" in path:
        assert "telemetry_scheduler_interval" in parser.controls
        assert "operational_notifications_enabled" in parser.controls
    if "section=db" in path:
        assert "core_db_backend" in parser.controls
        assert "/settings-save" in parser.actions
