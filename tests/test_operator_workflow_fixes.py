"""HTTP regressions for the six operator-workflow defects (no live devices)."""
import copy
import time
from types import SimpleNamespace

import pytest

from test_web_ux import console as _console_fixture, _device, _Console
from test_netflow_history import store as _store_fixture, flow
from test_r65_operator_workflow import _manager, _incident_plan, _proposal
from netconfig import netflow_history as nh
from netconfig import config
from netconfig.workflow import Workflow
from netconfig.web_forms import numeric_value
from netconfig.web_ops import _status
from netconfig.web_workflow_ux import guide, proposal_summary
from netconfig.web import Console

console = _console_fixture
store = _store_fixture


def post(c, path, **fields):
    return c.request("POST", path, {"csrf": "ux-csrf", **fields}, token=c.session())


def vault(m):
    m.vault.create("test-master-password")
    m.unlock_vault("test-master-password")


def device_form(**kw):
    return dict(name="a", orig_name="a", host="192.0.2.1", device_type="network",
                platform="generic", port="22", enabled="1", **kw)


def test_manual_credentials_fork_shared_secrets_and_preserve_blank_passwords(console):
    m = console.m
    vault(m)
    m.vault.set_secret("shared", username="old-user", password="old-password")
    m.vault.set_secret("snmp-shared", community="old-community", snmp_user="old-snmp")
    for name in ("a", "b"):
        _device(m, name, "192.0.2.1", secret_ref="shared", snmp_ref="snmp-shared", snmp_version="v2c")
    code, _, _ = post(console, "/device-save", **device_form(cred_mode="manual", ssh_username="new-user", snmp_user="new-snmp"))
    assert code == 303
    a, b = m.inv.get("a"), m.inv.get("b")
    assert a["secret_ref"] != b["secret_ref"] == "shared"
    assert a["snmp_ref"] != b["snmp_ref"] == "snmp-shared"
    assert m.vault.get_secret(a["secret_ref"]) == {"username": "new-user", "password": "old-password"}
    assert m.vault.get_secret(a["snmp_ref"]) == {"community": "old-community", "snmp_user": "new-snmp"}
    assert m.vault.get_secret("shared")["username"] == "old-user"
    assert m.vault.get_secret("snmp-shared")["snmp_user"] == "old-snmp"


def test_saved_mode_ignores_forged_manual_fields(console):
    vault(console.m)
    console.m.vault.set_secret("shared", username="old", password="old")
    _device(console.m, "a", "192.0.2.1", secret_ref="shared")
    assert post(console, "/device-save", **device_form(cred_mode="saved", secret_ref="shared", ssh_password="forged"))[0] == 303
    assert console.m.vault.get_secret("shared")["password"] == "old"


@pytest.mark.parametrize("invalid", [{"config_collect_command": "delete configuration"}, {"port": "bad"}, {"port": "0"}, {"snmp_port": "65536"}])
def test_validation_precedes_rename_and_secret_writes(console, invalid):
    vault(console.m)
    _device(console.m, "a", "192.0.2.1")
    before = console.m.vault.list_secrets()
    form = device_form(cred_mode="manual", ssh_password="must-not-leak", **({} if "port" in invalid else invalid))
    form.update(invalid, name="renamed", notes="keep these notes")
    code, _, page = post(console, "/device-save", **form)
    assert code == 400 and "Device not saved" in page
    assert console.m.inv.get("a") and not console.m.inv.get("renamed")
    assert console.m.vault.list_secrets() == before
    assert 'value="renamed"' in page and 'name=orig_name value="a"' in page
    assert "keep these notes" in page and "must-not-leak" not in page
    assert 'action="/device-save"' in page


def test_locked_device_secret_is_not_partially_saved(console):
    vault(console.m)
    _device(console.m, "a", "192.0.2.1")
    console.m._vault_unlocked = False
    code, _, page = post(console, "/device-save", **device_form(cred_mode="manual", ssh_password="secret-marker"))
    assert code == 400 and "unlock or create" in page and "secret-marker" not in page
    assert console.m.inv.get("a")["secret_ref"] == ""


@pytest.mark.parametrize("section,key,value", [
    ("netflow", "netflow_port", "abc"), ("netflow", "netflow_port", "65536"),
    ("netflow", "netflow_max_flows", "-1"), ("netflow", "netflow_max_flows", "0"),
    ("general", "bulk_workers", "0"), ("general", "command_timeout", "-1"),
    ("snmp", "snmp_timeout", "nan"), ("snmp", "snmp_timeout", "inf"),
    ("monitoring", "syslog_queue_size", "-1"), ("email", "smtp_port", "1.5"),
    ("db", "pg_port", "-1"), ("db", "if_history_hours", "-1")])
def test_settings_validation_has_no_partial_mutation_and_retains_input(console, section, key, value):
    before = copy.deepcopy(console.m.settings)
    scope = "history" if key == "if_history_hours" else "core"
    code, _, page = post(console, "/settings-save", section=section, db_scope=scope,
                         **{key: value, "web_bind": "192.0.2.99"})
    assert code == 400 and "not saved" in page
    assert console.m.settings == before
    assert f'name="{key}" value="{value}"' in page
    assert "settings saved." not in page


def test_zero_poll_interval_is_valid_and_positive_limits_work():
    assert numeric_value("monitor_poll_interval", "0") == 0
    assert numeric_value("snmp_timeout", "0.25") == 0.25
    assert numeric_value("netflow_port", "65535") == 65535


@pytest.mark.parametrize("field", ["smtp_password", "o365_client_secret"])
def test_locked_vault_email_save_fails_without_echo_or_partial_settings(console, field):
    vault(console.m)
    console.m._vault_unlocked = False
    before = dict(console.m.settings)
    code, _, page = post(console, "/settings-save", section="email", smtp_host="mail.example.test",
                         **{field: "private-marker"})
    assert code == 400 and "Unlock or create" in page and "private-marker" not in page
    assert 'value="mail.example.test"' in page
    assert console.m.settings == before


def test_failed_second_secret_write_restores_first_and_keeps_settings(console, monkeypatch):
    m = console.m
    vault(m)
    m.vault.set_secret("__smtp__", password="before")
    real = m.vault.set_secret
    def fail(name, **fields):
        if name == "__o365__":
            raise OSError("private-marker")
        return real(name, **fields)
    monkeypatch.setattr(m.vault, "set_secret", fail)
    before = dict(m.settings)
    code, _, page = post(console, "/settings-save", section="email", smtp_password="after", o365_client_secret="new")
    assert code == 400 and "not saved" in page and "private-marker" not in page
    assert m.vault.get_secret("__smtp__")["password"] == "before" and m.settings == before


def test_settings_file_failure_does_not_publish_in_memory_settings(console, monkeypatch):
    before = dict(console.m.settings)
    monkeypatch.setattr(config, "save_settings", lambda *a: (_ for _ in ()).throw(OSError("disk-secret")))
    code, _, page = post(console, "/settings-save", section="netflow", netflow_port="9999")
    assert code == 400 and "disk-secret" not in page and console.m.settings == before


@pytest.mark.parametrize("ok", [True, False])
def test_collect_returns_to_device_config_with_result(console, monkeypatch, ok):
    _device(console.m, "a", "192.0.2.1")
    monkeypatch.setattr(console.m, "collect", lambda name: SimpleNamespace(ok=ok, changed=ok, message="collected" if ok else "connection failed"))
    code, headers, _ = post(console, "/collect", name="a")
    assert code == 303 and headers["Location"] == "/device?name=a#tab-config"
    _, _, page = console.request("GET", "/device?name=a", token="ux-admin")
    assert ("collected" if ok else "connection failed") in page
    _, _, page = console.request("GET", "/device?name=a", token="ux-admin")
    assert '<div class="flash">' not in page  # one use, no repeated collection on refresh


@pytest.mark.parametrize("back,target", [("", "/device?name=a#tab-snmp"), ("snmp", "/snmp?device=a")])
def test_snmp_failure_returns_to_original_view_with_reason(console, monkeypatch, back, target):
    _device(console.m, "a", "192.0.2.1", snmp_version="v2c")
    monkeypatch.setattr(console.m, "snmp_poll", lambda *a, **k: {"ok": False, "error": "SNMP timed out"})
    code, headers, _ = post(console, "/snmp-poll", name="a", back=back)
    assert code == 303 and headers["Location"] == target
    _, _, page = console.request("GET", target.split("#")[0], token="ux-admin")
    assert "SNMP poll failed: SNMP timed out" in page


@pytest.mark.parametrize("target,expected", [("/operations?tab=workflow&incident=INC-1&plan=3&request=4&tx=5", "/operations?tab=workflow&incident=INC-1&plan=3&request=4&tx=5"), ("//evil.example", "/vault"), ("https://evil.example", "/vault")])
def test_unlock_preserves_safe_context_only(console, target, expected):
    vault(console.m)
    console.m._vault_unlocked = False
    code, headers, _ = post(console, "/unlock-vault", master="test-master-password", next=target)
    assert code == 303 and headers["Location"] == expected and console.m.vault_ready()


def test_traffic_choices_include_all_senders_and_selected_empty_exporter(console, store):
    now = time.time()
    store.write([flow(now - 10, exporter=f"192.0.2.{i}") for i in range(1, 16)])
    history = nh.FlowHistory(lambda: store)
    collector = SimpleNamespace(history=history, exporters=lambda: {"198.51.100.1": 1}, status=lambda: {"running": True})
    data = console.m.operations_console.traffic(collector, now=now)
    assert len(data["exporters"]) == 12 and len(data["exporter_choices"]) == 16
    filtered = console.m.operations_console.traffic(collector, now=now, exporter="203.0.113.1")
    assert len(filtered["exporter_choices"]) == 17
    assert "192.0.2.1" in {r["exporter"] for r in filtered["exporter_choices"]}
    # DISTINCT lookup is independent of the raw-row cap.
    rows, truncated = store.read(now - 3600, now, limit=1)
    assert truncated and len(rows) == 1 and len(history.exporter_choices(now - 3600, now)) == 15


def test_flow_choice_failure_is_visible_and_sanitized():
    def fail():
        raise OSError("password=do-not-display")
    history = nh.FlowHistory(fail)
    assert history.exporter_choices(time.time() - 60, time.time()) == []
    msg = history.status()["exporter_error"]
    assert "could not be listed" in msg and "do-not-display" not in msg


def test_workflow_summary_roles_advanced_details_and_unlock_context(tmp_path):
    m = _manager(tmp_path)
    m.users.create("tester", "test-password-123", role="admin")
    c = _Console(m)
    try:
        inc, plan = _incident_plan(m)
        url = f'/operations?tab=workflow&incident={inc["incident_key"]}&plan={plan["id"]}'
        code, _, page = c.request("GET", url, token=c.session())
        assert code == 200 and "Next step" in page and "Device to change" in page
        assert "Interface state" in page and "GigabitEthernet2" in page and "Enabled" in page
        assert '<details><summary>Advanced details</summary>' in page
        assert 'href="#workflow-proposals"' in page
        rid = Workflow(m.db, m).submit_automation(title="review this", intent={"kind": "structured_change", **_proposal()}, requested_by="operator",
                 context={"incident_ref": inc["incident_key"], "plan_id": plan["id"], "proposal_index": 0})
        Workflow(m.db, m).approve(rid, "approver")
        vault(m)
        m._vault_unlocked = False
        url += f"&request={rid}"
        code, _, page = c.request("GET", url, token=c.session())
        assert code == 200 and "Unlock and return here" in page and 'action="/unlock-vault"' in page
        unlock_form = page.split('action="/unlock-vault"', 1)[1].split('</form>', 1)[0]
        assert 'name="next" value="/operations?tab=workflow&amp;incident=' in unlock_form
        assert f'&amp;plan={plan["id"]}&amp;request={rid}' in unlock_form
        assert "Apply approved change" in page
        _, _, viewer = c.request("GET", url, token=c.session("viewer", "viewer"))
        assert "Waiting for an approver" in viewer
        assert 'action="/unlock-vault"' not in viewer and 'action="/ops-workflow-execute"' not in viewer
        assert 'b-ok">COMPLETE' in _status("COMPLETE")
    finally:
        c.close()


def test_summary_escapes_device_fields():
    page = proposal_summary({"device": "<script>bad</script>", "resource": "interface_enabled", "selectors": {}, "value": False})
    assert "<script>bad" not in page and "&lt;script&gt;" in page and "Disabled" in page


def test_recovery_guide_does_not_offer_execute():
    view = {"selected_transaction": {"state": "RECOVERY_REQUIRED", "device": "fw1"}}
    page = guide(None, view, {"role": "operator"})
    assert "administrator must check" in page and "Review recovery" in page and "Apply approved" not in page


def test_successful_email_secrets_save_and_blank_fields_preserve_them(console):
    vault(console.m)
    assert post(console, "/settings-save", section="email", smtp_host="mail.example.test", smtp_password="mail-password", o365_client_secret="client-password")[0] == 200
    assert console.m.vault.get_secret("__smtp__")["password"] == "mail-password"
    assert console.m.vault.get_secret("__o365__")["client_secret"] == "client-password"
    assert post(console, "/settings-save", section="email", smtp_host="mail2.example.test")[0] == 200
    assert console.m.vault.get_secret("__smtp__")["password"] == "mail-password"
    assert console.m.settings["smtp_host"] == "mail2.example.test"


def test_existing_device_name_cannot_be_overwritten_by_new_form(console):
    _device(console.m, "a", "192.0.2.1")
    form = device_form()
    form.pop("orig_name")
    form["host"] = "192.0.2.9"
    assert post(console, "/device-save", **form)[0] == 400
    assert console.m.inv.get("a")["host"] == "192.0.2.1"


def test_save_failure_after_rename_reports_actual_partial_state(console, monkeypatch):
    _device(console.m, "a", "192.0.2.1")
    monkeypatch.setattr(console.m.inv, "upsert", lambda **k: (_ for _ in ()).throw(OSError("private-marker")))
    form = device_form()
    form["name"] = "renamed"
    code, _, page = post(console, "/device-save", **form)
    assert code == 200 and "after renaming to" in page and "private-marker" not in page
    assert console.m.inv.get("renamed") and not console.m.inv.get("a")


def test_ambiguous_inventory_commit_does_not_delete_attached_credentials(console, monkeypatch):
    vault(console.m)
    _device(console.m, "a", "192.0.2.1")
    real = console.m.inv.upsert
    def uncertain(**kw):
        real(**kw)
        raise OSError("commit response lost")
    monkeypatch.setattr(console.m.inv, "upsert", uncertain)
    code, _, page = post(console, "/device-save", **device_form(cred_mode="manual", ssh_username="new-user", ssh_password="new-pass"))
    assert code == 200 and "Device save interrupted" in page
    ref = console.m.inv.get("a")["secret_ref"]
    assert console.m.vault.get_secret(ref)["password"] == "new-pass"


def test_wrong_unlock_keeps_destination_and_explains_failure(console):
    vault(console.m)
    console.m._vault_unlocked = False
    target = "/settings?section=email"
    code, headers, _ = post(console, "/unlock-vault", master="wrong-password", next=target)
    assert code == 303 and headers["Location"] == target and not console.m.vault_ready()
    _, _, page = console.request("GET", target, token="ux-admin")
    assert "Wrong master password" in page and "wrong-password" not in page


def test_complete_exporter_dropdown_is_not_the_top_table(console, store, monkeypatch):
    now = time.time()
    store.write([flow(now - 10, exporter=f"192.0.2.{i}") for i in range(1, 16)])
    history = nh.FlowHistory(lambda: store)
    collector = SimpleNamespace(history=history, exporters=lambda: {}, status=lambda: {"running": True, "port": 2055})
    monkeypatch.setattr(Console, "netflow", collector, raising=False)
    code, _, page = console.request("GET", "/traffic?exporter=192.0.2.1", token=console.session())
    assert code == 200
    choices = page.split('select name=exporter>', 1)[1].split('</select>', 1)[0]
    assert choices.count("<option") == 16 and 'value="192.0.2.1" selected' in choices
    assert 'value="192.0.2.15"' in choices


@pytest.mark.parametrize("path,form", [("/device-save", {"name": "forged", "host": "192.0.2.1"}), ("/settings-save", {"section": "netflow", "netflow_port": "9999"}), ("/unlock-vault", {"master": "fake"}), ("/collect", {"name": "a"}), ("/snmp-poll", {"name": "a"})])
def test_changed_post_routes_still_require_csrf(console, path, form):
    before = dict(console.m.settings)
    code, _, _ = console.request("POST", path, form, token=console.session())
    assert code == 403 and console.m.settings == before and not console.m.inv.get("forged")
