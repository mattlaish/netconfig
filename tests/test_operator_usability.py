"""HTTP and persistence regressions for the approved 7+6 operator workflow."""
import json
import threading
import time
import uuid
from types import SimpleNamespace

from test_web_ux import console as console_fixture, _device
from netconfig import appmon, monitor, web
from netconfig.collection_operations import operations_for, CollectionOperations

console = console_fixture


def task_result(console, task_id):
    code, _, body = console.request("GET", "/collection-status?id=" + task_id, token=console.session())
    assert code == 200, body
    return json.loads(body)


def wait_task(console, task_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = task_result(console, task_id)
        if result["state"] not in {"queued", "running"}:
            return result
        time.sleep(.02)
    raise AssertionError("collection task did not finish")


def test_failed_http_tls_reasons_survive_storage_sensors_and_page(console, monkeypatch):
    _device(console.m, "web", "192.0.2.10", device_type="application", monitor_urls="https://app.example/health 200")
    monkeypatch.setattr(appmon, "check_all", lambda *a, **kw: [{
        "url": "https://app.example/health", "status": None, "ok": False,
        "error": "connection timed out https://user:password@app.example/?token=private",
        "tls": {"valid": False, "error": "unable to get local issuer certificate <bad>"},
    }])
    token = console.session()
    assert console.request("POST", "/device-monitor-check",
                           {"csrf": "ux-csrf", "name": "web"}, token=token)[0] == 303
    history = console.m.db.result_history("web")
    assert any("issuer certificate" in r["detail"] for r in history)
    assert "private" not in str(history) and "user:password" not in str(history)
    sensors = console.m.db.conn.execute("SELECT message FROM sensors WHERE device='web'").fetchall()
    assert any("issuer certificate" in row["message"] for row in sensors)
    code, _, page = console.request("GET", "/device?name=web", token=token)
    assert code == 200 and "issuer certificate &lt;bad&gt;" in page
    assert "server certificate chain" in page


def test_application_form_test_uses_unsaved_values_without_saving_results(console, monkeypatch):
    calls = []
    def checked(spec, host, **kwargs):
        calls.append((spec, host))
        return [{"url": spec, "ok": False, "status": 503, "expect": 200,
                 "tls": {"valid": False, "error": "certificate has expired"}}]
    monkeypatch.setattr(appmon, "check_all", checked)
    code, _, body = console.request("POST", "/device-test", {
        "csrf": "ux-csrf", "host": "app.example", "device_type": ["application"],
        "monitor_urls": "https://app.example/health 200", "test_application": "1",
    }, token=console.session())
    result = json.loads(body)
    assert code == 200 and calls == [("https://app.example/health 200", "app.example")]
    assert len(result["results"]) == 2 and not any(r["ok"] for r in result["results"])
    assert console.m.db.conn.execute("SELECT COUNT(*) FROM monitor_results").fetchone()[0] == 0
    assert console.m.inv.all() == []
    assert console.request("POST", "/device-test", {"csrf": "ux-csrf", "host": "app.example"},
                           token=console.session("viewer", "viewer1"))[0] == 403


def test_collection_returns_progress_before_devices_finish_and_retries_only_failures(console, monkeypatch):
    _device(console.m, "good", "192.0.2.11")
    _device(console.m, "bad", "192.0.2.12")
    release = threading.Event()
    calls = []
    fail = {"bad": True}
    def collect(name):
        calls.append(name)
        release.wait(10)
        return SimpleNamespace(ok=not fail.get(name), message="failed to collect" if fail.get(name) else "Collected")
    monkeypatch.setattr(console.m, "collect", collect)
    form = {"csrf": "ux-csrf", "devices": ["good", "bad"], "background": "1",
            "request_key": uuid.uuid4().hex}
    headers = {"X-NetConfig-Operation": "start"}
    try:
        code, _, body = console.request("POST", "/collect", form, token=console.session(), headers=headers)
        assert code == 202, body
        task_id = json.loads(body)["id"]
        assert task_result(console, task_id)["state"] in {"queued", "running"}
        code, _, repeated = console.request("POST", "/collect", form, token=console.session(), headers=headers)
        assert code == 202 and json.loads(repeated)["id"] == task_id
    finally:
        release.set()
    result = wait_task(console, task_id)
    assert result["state"] == "partial" and sorted(calls) == ["bad", "good"]
    assert all(row["target_tab"] == "config" for row in result["results"])
    code, _, page = console.request("GET", "/collection-task?id=" + task_id, token=console.session())
    assert code == 200 and "/device?name=bad#tab-config" in page

    fail["bad"] = False
    code, _, body = console.request("POST", "/collection-retry", {
        "csrf": "ux-csrf", "id": task_id,
    }, token=console.session(), headers=headers)
    assert code == 202
    retried = wait_task(console, json.loads(body)["id"])
    assert retried["state"] == "passed" and calls.count("good") == 1 and calls.count("bad") == 2


def test_collection_permission_csrf_and_owner_checks(console, monkeypatch):
    _device(console.m, "sw", "192.0.2.13")
    monkeypatch.setattr(console.m, "collect", lambda name: SimpleNamespace(ok=True, message="Done"))
    form = {"csrf": "ux-csrf", "name": "sw", "kind": "collect"}
    assert console.request("POST", "/collection-start", form,
                           token=console.session("viewer", "viewer1"))[0] == 403
    assert console.request("POST", "/collection-start", {**form, "csrf": "wrong"},
                           token=console.session())[0] == 403
    assert console.m.db.conn.execute("SELECT COUNT(*) FROM collection_tasks").fetchone()[0] == 0
    code, headers, _ = console.request("POST", "/collection-start", form, token=console.session())
    assert code == 303
    task_id = headers["Location"].split("id=", 1)[1].split("&", 1)[0]
    wait_task(console, task_id)
    assert console.request("GET", "/collection-status?id=" + task_id,
                           token=console.session("operator", "another"))[0] == 404


def test_unfinished_task_is_preserved_as_interrupted_after_service_recovery(console):
    _device(console.m, "sw", "192.0.2.14")
    service = operations_for(console.m)
    task_id = uuid.uuid4().hex
    console.m.db.conn.execute(
        "INSERT INTO collection_tasks VALUES (?,?,?,?,?,?,?,?,?)",
        (task_id, "tester", service.node, "collect", "running", time.time(), time.time(),
         uuid.uuid4().hex, json.dumps([{"device": "sw", "state": "running", "ok": None, "message": ""}])))
    console.m.db.conn.commit()
    recovered = CollectionOperations(console.m)
    try:
        assert recovered.get(task_id)["state"] == "interrupted"
        assert recovered.get(task_id)["results"][0]["ok"] is None
    finally:
        recovered.close()


def test_devices_live_is_passive_and_preserves_saved_check_timestamp(console):
    _device(console.m, "mail", "192.0.2.15", device_type="system", monitor_ports="tcp/25")
    console.m.db.record_result("mail", "port", "tcp/25", "open", 2)
    token, record = web._create_managed_session(console.m.users.get("tester"))
    record["last_seen"] -= 60
    previous = record["last_seen"]
    code, _, body = console.request("GET", "/devices-live", token=token)
    assert code == 200 and 'data-state="up"' in body and "Last checked" in body
    assert "#tab-monitoring" in body and "data-select-device" in body
    assert record["last_seen"] == previous


def test_batch_changes_require_manage_permission_and_report_each_device(console):
    for name in ("a", "b"):
        _device(console.m, name, "192.0.2.16", tags=["old"])
    form = {"csrf": "ux-csrf", "devices": ["a", "b"], "action": "tags", "tags": "branch, critical"}
    assert console.request("POST", "/devices-bulk", form,
                           token=console.session("operator", "op1"))[0] == 403
    code, _, body = console.request("POST", "/devices-bulk", form, token=console.session())
    assert code == 200 and "Updated" in body
    assert console.m.inv.get("a")["tags"] == ["old", "branch", "critical"]
    assert console.request("POST", "/devices-bulk", {**form, "action": "disable"}, token=console.session())[0] == 200
    assert not console.m.inv.get("a")["enabled"] and not console.m.inv.get("b")["enabled"]
    code, _, _ = console.request("POST", "/devices-bulk", {**form, "action": "enable",
                                                           "devices": ["a", "missing"]}, token=console.session())
    assert code == 409 and not console.m.inv.get("a")["enabled"]


def test_copy_device_retargets_http_and_does_not_reuse_saved_credentials(console):
    _device(console.m, "source", "old.example", device_type="application",
            monitor_urls="https://old.example/health 200\nhttps://external.example/status 204",
            secret_ref="source-secret", snmp_ref="source-snmp")
    code, _, form = console.request("GET", "/device-new?copy=source", token=console.session())
    assert code == 200 and 'name=copy_from value="source"' in form
    assert 'value="source-secret" selected' not in form
    code, headers, _ = console.request("POST", "/device-save", {
        "csrf": "ux-csrf", "name": "copy", "copy_from": "source", "host": "  new.example  ",
        "device_type": ["application"], "enabled": "1",
        "monitor_urls": "https://old.example/health 200\nhttps://external.example/status 204",
    }, token=console.session())
    assert code == 303 and "/device?" in headers["Location"]
    dev = console.m.inv.get("copy")
    assert "https://new.example/health 200" in dev["monitor_urls"]
    assert "https://external.example/status 204" in dev["monitor_urls"]
    assert not any(dev.get(key) for key in ("secret_ref", "snmp_ref", "enable_ref"))
    assert console.m.store.versions("copy") == []


def test_copy_url_validation_is_reported_in_form(console):
    _device(console.m, "source", "old.example", device_type="application")
    code, _, page = console.request("POST", "/device-save", {
        "csrf": "ux-csrf", "name": "copy", "copy_from": "source", "host": "[broken",
        "device_type": ["application"], "enabled": "1",
    }, token=console.session())
    assert code == 400 and "Device not saved" in page
    assert console.m.inv.get("copy") is None


def test_save_destinations_preserve_return_context_and_refuse_external_redirects(console):
    _device(console.m, "mail", "192.0.2.17", device_type="system")
    base = {"csrf": "ux-csrf", "name": "mail", "orig_name": "mail", "host": "192.0.2.17",
            "device_type": ["system"], "port": "22", "platform": "generic", "enabled": "1"}
    code, headers, _ = console.request("POST", "/device-save", {**base, "save_action": "return",
        "return_to": "/device?name=mail#tab-monitoring"}, token=console.session())
    assert code == 303 and headers["Location"] == "/device?name=mail#tab-monitoring"
    code, headers, _ = console.request("POST", "/device-save", {**base, "save_action": "stay"},
                                       token=console.session())
    assert code == 303 and headers["Location"].startswith("/device-new?name=mail")
    code, headers, _ = console.request("POST", "/device-save", {**base, "return_to": "https://evil.example"},
                                       token=console.session())
    assert code == 303 and headers["Location"] == "/device?name=mail"


def test_save_and_check_now_uses_durable_monitoring_task(console, monkeypatch):
    monkeypatch.setattr(monitor, "run_device_checks", lambda *args: [
        {"kind": "port", "target": "tcp/25", "status": "open", "value": 1}])
    code, headers, _ = console.request("POST", "/device-save", {
        "csrf": "ux-csrf", "name": "mail", "host": "192.0.2.18", "device_type": ["system"],
        "platform": "generic", "enabled": "1", "monitor_ports": "tcp/25", "save_action": "check",
    }, token=console.session())
    assert code == 303 and headers["Location"].startswith("/collection-task?")
    task_id = headers["Location"].split("id=",1)[1].split("&",1)[0]
    assert wait_task(console, task_id)["state"] == "passed"


def test_saved_restart_settings_show_pending_but_live_settings_do_not(console):
    token = console.session()
    assert console.request("GET", "/settings?section=netflow", token=token)[0] == 200
    code, _, body = console.request("POST", "/settings-save", {
        "csrf": "ux-csrf", "section": "netflow", "netflow_enabled": "1",
        "netflow_history_enabled": "1", "netflow_port": "2056", "netflow_max_flows": "10000",
    }, token=token)
    assert code == 200 and "Saved · restart required" in body
    assert "NetFlow port" in body
    assert "Test saved History + NetFlow" in body and "Edit History connection" in body


def test_device_navigation_contains_context_switch_and_copy_controls(console):
    _device(console.m, "a", "192.0.2.19", snmp_version="v2c")
    _device(console.m, "b", "192.0.2.20", snmp_version="v2c")
    code, _, body = console.request("GET", "/device?name=a", token=console.session())
    assert code == 200 and "data-device-switch" in body and "data-keep-tab" in body
    assert "Copy device settings" in body and "data-edit-return" in body
    assert 'data-copy="192.0.2.19"' in body
    assert "Collect configuration" in body and "Poll SNMP" in body



def test_netflow_test_and_browser_save_return_to_canonical_settings_page(console):
    token = console.session()
    code, headers, _ = console.request("POST", "/settings-save", {
        "csrf": "ux-csrf", "section": "netflow", "netflow_port": "2056",
        "netflow_max_flows": "10000", "ui_return_to": "/settings?section=netflow",
    }, token=token)
    assert code == 303 and headers["Location"] == "/settings?section=netflow"
    assert "settings saved" in console.request("GET", headers["Location"], token=token)[2]
    code, headers, _ = console.request("POST", "/history-db-test", {
        "csrf": "ux-csrf", "return_section": "netflow",
    }, token=token)
    assert code == 303 and headers["Location"] == "/settings?section=netflow"
    body = console.request("GET", headers["Location"], token=token)[2]
    assert "Set and save History PostgreSQL" in body



def test_secret_values_in_json_headers_and_urls_are_removed_from_diagnostics():
    detail = monitor.safe_check_detail(
        """{"password": "json-value", "snmp_auth_pass": "snmp-value"} Authorization: Bearer header-value
        failed https://user:url-password@example.com/path?token=query-value""")
    for value in ("json-value", "snmp-value", "header-value", "url-password", "query-value"):
        assert value not in detail
    assert "https://example.com" in detail


def test_simultaneous_tag_additions_preserve_other_fields(console):
    from concurrent.futures import ThreadPoolExecutor
    _device(console.m, "sw", "192.0.2.30", tags=["original"])
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda tag: console.m.inv.update_operator_fields("sw", add_tags=[tag]),
                      ["a", "b", "c", "d"]))
    dev = console.m.inv.get("sw")
    assert set(dev["tags"]) == {"original", "a", "b", "c", "d"}
    assert dev["host"] == "192.0.2.30" and dev["platform"] == "generic"


def test_disabled_devices_allow_explicit_checks_but_are_excluded_from_collect_all(console, monkeypatch):
    _device(console.m, "disabled", "192.0.2.31", enabled=False)
    _device(console.m, "enabled", "192.0.2.32")
    calls = []
    def collect(name):
        calls.append(name)
        return SimpleNamespace(ok=True, message="Collected")
    monkeypatch.setattr(console.m, "collect", collect)
    headers = {"X-NetConfig-Operation": "start"}
    code, _, body = console.request("POST", "/collect", {
        "csrf": "ux-csrf", "background": "1", "name": "disabled",
    }, token=console.session(), headers=headers)
    assert code == 202 and wait_task(console, json.loads(body)["id"])["state"] == "passed"
    code, _, body = console.request("POST", "/collect", {
        "csrf": "ux-csrf", "background": "1", "all": "1",
    }, token=console.session(), headers=headers)
    assert code == 202 and wait_task(console, json.loads(body)["id"])["state"] == "passed"
    assert calls == ["disabled", "enabled"]


def test_start_option_overrides_are_distinguished_from_pending_restart(console):
    from netconfig.web_operator_workflow import restart_notice
    m = console.m
    m._console_applied_settings = dict(m.settings)
    m._console_start_overrides = {"web_port": 9000}
    body = restart_notice(m)
    assert "start options override" in body and "9000" in body
    assert "restart required" not in body
    m.settings["web_port"] = 9000
    assert restart_notice(m) == ""



def test_copy_application_test_uses_same_new_target_as_save(console, monkeypatch):
    _device(console.m, "source", "old.example", device_type="application",
            monitor_urls="https://old.example/health 200")
    checked = []
    def probe(spec, host, **kwargs):
        checked.append(spec)
        return [{"url": "https://new.example/health", "ok": True, "status": 200}]
    monkeypatch.setattr(appmon, "check_all", probe)
    code, _, body = console.request("POST", "/device-test", {
        "csrf": "ux-csrf", "device_type": ["application"], "copy_from": "source",
        "host": "new.example", "monitor_urls": "https://old.example/health 200",
    }, token=console.session())
    assert code == 200 and checked == ["https://new.example/health 200"]
    assert "HTTP https://new.example/health" in json.loads(body)["results"][0]["check"]
    assert console.m.inv.get("new.example") is None



def test_manual_udp_ambiguity_remains_unknown_in_normalized_sensors(console, monkeypatch):
    from netconfig import portmon
    _device(console.m, "udp", "192.0.2.33", device_type="system", monitor_ports="udp/53")
    monkeypatch.setattr(portmon, "check_ports", lambda *args, **kw: [
        {"proto": "udp", "port": 53, "state": "open|filtered", "ms": None}])
    code, _, _ = console.request("POST", "/device-monitor-check", {
        "csrf": "ux-csrf", "name": "udp",
    }, token=console.session())
    assert code == 303
    row = console.m.db.conn.execute(
        "SELECT status,message FROM sensors WHERE device='udp' AND sensor_type='service.port_state'").fetchone()
    assert row["status"] == "UNKNOWN" and "no UDP reply" in row["message"]
    assert console.m.alert_lifecycle.list() == []


def test_history_test_denies_viewer_before_accessing_database_password(console, monkeypatch):
    def forbidden():
        raise AssertionError("Unauthorized History test accessed the password")
    monkeypatch.setattr(console.m, "_pg_password", forbidden)
    code, _, body = console.request("POST", "/history-db-test",
        {"csrf": "ux-csrf", "return_section": "netflow"},
        token=console.session("viewer", "viewer"))
    assert code == 403 and "Server error" not in body
