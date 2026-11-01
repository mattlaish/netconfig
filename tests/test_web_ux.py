"""Console usability round: navigation, sign-in return, Devices home, dashboard,
device tabs, Add Device form + connection test, CSV import, search, paging and
first-admin setup."""
import http.client
import json
import os
import stat
import threading
import time
import urllib.parse

import pytest

from netconfig.apitokens import ApiTokens  # noqa: F401  (import keeps module graph identical to other web tests)
from netconfig.manager import Manager
import netconfig.web as web
import netconfig.web_ux as web_ux
from netconfig.web import Console, _Server
from netconfig.web_ux import parse_device_csv, safe_next_path


def _device(m, name, host, **kw):
    base = dict(name=name, host=host, port=22, platform="generic", device_type="network", secret_ref="",
                enable_ref="", use_key=False, legacy=False, scrub=True, enabled=True, tags=[], notes="",
                snmp_version="", snmp_ref=None)
    base.update(kw)
    m.inv.upsert(**base)


class _Console:
    def __init__(self, manager):
        self.m = manager
        Console.manager = manager
        Console.tls_enabled = False
        self.server = _Server(("127.0.0.1", 0), Console)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def session(self, role="admin", username="tester"):
        web._SESSIONS["ux-" + role] = {"username": username, "role": role, "csrf": "ux-csrf", "created": 1.0}
        return "ux-" + role

    def request(self, method, path, form=None, token=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=10)
        hdrs = dict(headers or {})
        if token:
            hdrs["Cookie"] = f"ncsid={token}"
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form, doseq=True)
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body=body, headers=hdrs)
        res = conn.getresponse()
        data = res.read().decode("utf-8", "replace")
        out = (res.status, dict(res.getheaders()), data)
        conn.close()
        return out

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        web._SESSIONS.clear()
        self.m.close()


@pytest.fixture
def console(tmp_path):
    web._SESSIONS.clear()
    m = Manager(str(tmp_path / "home"))
    m.users.create("tester", "tester-password-1", role="admin")
    c = _Console(m)
    yield c
    c.close()


# ---- navigation / shell -------------------------------------------------------

def test_sidebar_groups_are_collapsible_and_admin_links_reachable(console):
    status, _h, text = console.request("GET", "/devices-missing", token=console.session())
    status, _h, text = console.request("GET", "/", token=console.session())
    assert status == 200
    assert '<details class="side-group" data-group="Changes" open>' in text
    assert '<details class="side-group" data-group="Administration">' in text   # collapsed by default
    for href in ("/settings", "/users", "/audit", "/help", "/search", "/requests"):
        assert f'href="{href}"' in text
    first_nav = text.split('<nav class="nav-sidebar">', 1)[1].split("</nav>", 1)[0]
    assert ">Collection<" not in first_nav
    assert 'id="menu-toggle"' in text and "Times shown in" in text
    assert 'action="/search"' in text                                             # header search


def test_viewer_sidebar_hides_admin_only_pages(console):
    _s, _h, text = console.request("GET", "/", token=console.session("viewer", "viewer1"))
    assert 'href="/settings"' not in text and 'href="/users"' not in text and 'href="/vault"' not in text


def test_active_group_opens_even_when_collapsed_by_default(console):
    _s, _h, text = console.request("GET", "/runs", token=console.session())
    assert '<details class="side-group" data-group="Collection" open>' in text


# ---- sign-in return -------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("/alerts?view=active", "/alerts?view=active"),
    ("/device?name=sw1#tab-config", "/device?name=sw1#tab-config"),
    ("//evil.example/x", ""), ("https://evil.example/", ""), ("/\\evil", ""),
    ("/login", ""), ("/logout", ""), ("/api/v1/inventory", ""), ("", ""), ("alerts", ""),
])
def test_safe_next_path(value, expected):
    assert safe_next_path(value) == expected


def test_signed_out_get_returns_to_requested_page_after_login(console):
    status, headers, _ = console.request("GET", "/alerts?view=active")
    assert status == 303
    assert headers["Location"] == "/login?next=%2Falerts%3Fview%3Dactive"
    status, _h, page = console.request("GET", headers["Location"])
    assert 'name=next value="/alerts?view=active"' in page
    status, headers, _ = console.request("POST", "/login", {"username": "tester", "password": "tester-password-1",
                                                            "next": "/alerts?view=active"})
    assert status == 303 and headers["Location"] == "/alerts?view=active"


def test_login_ignores_offsite_next(console):
    status, headers, _ = console.request("POST", "/login", {"username": "tester", "password": "tester-password-1",
                                                            "next": "//evil.example/"})
    assert status == 303 and headers["Location"] == "/"


def test_settings_page_has_a_single_heading(console):
    _s, _h, text = console.request("GET", "/settings", token=console.session())
    assert text.count("<h1>Settings</h1>") == 1


# ---- Devices home / device page --------------------------------------------------

def _open_alert(m, device, severity="CRITICAL", message="uplink down"):
    c = m.db.conn
    c.execute("INSERT INTO operational_events(first_ts,last_ts,event_count,source_type,source,device,event_type,"
              "severity,message,dedup_key) VALUES(?,?,?,?,?,?,?,?,?,?)",
              (time.time(), time.time(), 1, "test", "test", device, "LINK_DOWN", severity, message, f"ux-{device}"))
    event_id = c.execute("SELECT max(id) AS id FROM operational_events").fetchone()["id"]
    c.execute("INSERT INTO operational_alerts(event_id,correlation_key,last_event_id,state,severity,device,event_type,"
              "message,first_ts,last_ts,event_count) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
              (event_id, f"ux:{device}", event_id, "OPEN", severity, device, "LINK_DOWN", message,
               time.time(), time.time(), 1))
    c.commit()


def test_devices_home_is_open_and_shows_alert_counts(console):
    m = console.m
    _device(m, "sw1", "192.0.2.10")
    _device(m, "sw2", "192.0.2.11")
    _open_alert(m, "sw1")
    _s, _h, text = console.request("GET", "/", token=console.session())
    assert '<details class="devgroup" open>' in text
    assert "<th>Alerts</th>" in text
    assert 'href="/device-import"' in text and "Import CSV" in text
    row1 = text.split('href="/device?name=sw1"', 1)[1].split("</tr>", 1)[0]
    row2 = text.split('href="/device?name=sw2"', 1)[1].split("</tr>", 1)[0]
    assert '<span class="badge b-bad">1 open</span>' in row1
    assert "open</span>" not in row2


def test_device_page_uses_tabs(console):
    _device(console.m, "sw1", "192.0.2.10")
    _s, _h, text = console.request("GET", "/device?name=sw1", token=console.session())
    assert 'class="tabset" id="device-tabs"' in text
    assert 'data-tab="overview"' in text and 'data-tab="config"' in text and 'data-tab="addresses"' in text


# ---- dashboard -------------------------------------------------------------------

def test_dashboard_is_network_first(console):
    m = console.m
    _device(m, "core-sw1", "192.0.2.250", snmp_version="v2c")
    m.inv.set_facts("core-sw1", reachable=False, sysname="CORE", sysdescr="d", uptime="", sysobjectid="",
                    contact="", location="", error="timeout after 2.0s")
    m.inv.log_run("core-sw1", True, changed=True, message="4 lines changed")
    _s, _h, text = console.request("GET", "/dashboard", token=console.session("viewer", "viewer1"))
    assert _s == 200
    assert "Devices reachable" in text and "0 / 1" in text
    assert "Needs attention" in text and "core-sw1" in text and "timeout after 2.0s" in text
    assert "Recent configuration changes" in text and "4 lines changed" in text
    assert "No active incidents, impacted services" in text                  # empty sections collapsed
    assert '<details class="panel"><summary><b>Analysis service health</b>' in text


# ---- Add Device form and connection test -------------------------------------------

def test_device_form_offers_credential_modes_and_connection_test(console):
    _s, _h, text = console.request("GET", "/device-new", token=console.session())
    assert 'id=device_form' in text
    assert 'name=cred_mode value=saved' in text and 'name=cred_mode value=manual' in text
    assert 'data-snmp="v3"' in text and 'data-snmp="v2c"' in text
    assert 'id=test_conn' in text
    status, _h, _t = console.request("GET", "/device-new", token=console.session("operator", "op1"))
    assert status == 403


def test_device_test_endpoint_is_role_gated_validated_and_audited(console, monkeypatch):
    calls = []

    def fake_test(host, **kw):
        calls.append((host, kw))
        return [{"check": "SSH login", "ok": False, "detail": "Connection refused"}]
    monkeypatch.setattr(console.m, "test_device_connection", fake_test)
    form = {"csrf": "ux-csrf", "host": "192.0.2.5", "port": "22", "device_type": "network",
            "ssh_username": "admin", "ssh_password": "s3cret-value", "snmp_version": ""}
    status, _h, body = console.request("POST", "/device-test", form, token=console.session("operator", "op1"))
    assert status == 403 and "approvers" in json.loads(body)["error"]
    status, _h, body = console.request("POST", "/device-test", dict(form, host=""), token=console.session())
    assert status == 400
    status, _h, body = console.request("POST", "/device-test", form, token=console.session())
    payload = json.loads(body)
    assert status == 200 and payload["results"][0]["check"] == "SSH login"
    assert "s3cret-value" not in body
    assert calls[0][0] == "192.0.2.5" and calls[0][1]["ssh"]["username"] == "admin"
    assert any(a["action"] == "device_connection_test" for a in console.m.db.recent_audit(10))


# SSHTransport spawns ssh via forkpty(); in a threaded test process Python warns about
# forkpty in multi-threaded programs. Console collection already runs this way.
@pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")
def test_connection_test_reports_failures_without_raising(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.settings["connect_timeout"] = 2
    m.settings["snmp_timeout"] = 0.3
    try:
        results = m.test_device_connection(
            "127.0.0.1", port=1, ssh={"username": "admin", "password": "x"},
            snmp={"version": "v2c", "community": "public", "snmp_port": "1"})
    finally:
        m.close()
    assert [r["check"] for r in results] == ["SSH login", "SNMP v2c"]
    assert all(r["ok"] is False and r["detail"] for r in results)
    assert all("x" != r["detail"] for r in results)


# ---- CSV import ----------------------------------------------------------------------

CSV = ("name,host,port,platform,type,tags,ssh_secret,snmp_version,netflow,enabled\n"
       "sw-a,10.0.0.1,22,generic,network,core dc1,,v2c,yes,yes\n"
       "sw-b,,22,generic,network,,,,no,yes\n"
       "sw-c,10.0.0.3,22,not-a-platform,network,,,,no,yes\n"
       "sw-a,10.0.0.4,22,generic,network,,,,no,yes\n"
       "exists,10.0.0.5,22,generic,network,,,,no,yes\n"
       "sw-d,10.0.0.6,99999,generic,network,,needs-vault,,maybe,yes\n")


def test_parse_device_csv_validates_each_row(tmp_path):
    m = Manager(str(tmp_path / "home"))
    try:
        _device(m, "exists", "10.9.9.9")
        rows, note = parse_device_csv(CSV, m)
    finally:
        m.close()
    by_line = {r["line"]: r for r in rows}
    assert not by_line[2]["errors"] and by_line[2]["values"]["tags"] == ["core", "dc1"]
    assert "SNMP is set but no snmp_secret is given" in by_line[2]["warnings"]
    assert "host is empty" in by_line[3]["errors"]
    assert any("unknown platform" in e for e in by_line[4]["errors"])
    assert "name appears more than once in this file" in by_line[5]["errors"]
    assert "a device with this name already exists" in by_line[6]["errors"]
    errs = " ".join(by_line[7]["errors"])
    assert "port must be 1-65535" in errs and "netflow must be yes or no" in errs
    assert "no vault secret named 'needs-vault' (ssh_secret)" in errs       # vault open: unknown name is an error
    assert parse_device_csv("host\n1.2.3.4\n", m)[1].startswith("The first row must be a header")


def test_parse_device_csv_warns_when_vault_is_locked(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    try:
        monkeypatch.setattr(m, "vault_ready", lambda: False)
        rows, _note = parse_device_csv("name,host,ssh_secret\nsw-x,10.0.0.9,lab-admins\n", m)
    finally:
        m.close()
    assert not rows[0]["errors"] and any("vault is locked" in w for w in rows[0]["warnings"])


def test_csv_import_preview_then_create(console):
    _device(console.m, "exists", "10.9.9.9")
    tok = console.session()
    status, _h, text = console.request("POST", "/device-import", {"csrf": "ux-csrf", "action": "preview", "csv": CSV}, token=tok)
    assert status == 200 and "1 ready" in text and "will be skipped" in text
    assert console.m.inv.get("sw-a") is None                          # preview saves nothing
    status, _h, text = console.request("POST", "/device-import", {"csrf": "ux-csrf", "action": "create", "csv": CSV}, token=tok)
    assert status == 200 and "Imported 1 device(s); 5 skipped." in text
    dev = console.m.inv.get("sw-a")
    assert dev and dev["host"] == "10.0.0.1" and dev["netflow"]
    assert console.m.inv.get("sw-c") is None
    assert any(a["action"] == "device_import" and a["target"] == "sw-a" for a in console.m.db.recent_audit(10))


def test_csv_import_is_role_gated_and_csrf_protected(console):
    status, _h, _t = console.request("GET", "/device-import", token=console.session("operator", "op1"))
    assert status == 403
    status, _h, _t = console.request("POST", "/device-import", {"csrf": "wrong", "action": "create", "csv": CSV},
                                     token=console.session())
    assert status == 403 and console.m.inv.get("sw-a") is None
    status, headers, body = console.request("GET", "/device-import?template=1", token=console.session())
    assert status == 200 and headers["Content-Type"].startswith("text/csv") and body.startswith("name,host,")


# ---- search ----------------------------------------------------------------------------

def test_global_search_finds_devices_addresses_and_escapes_input(console):
    m = console.m
    _device(m, "edge-fw", "198.51.100.7", tags=["branch42"])
    m.db.set_arp("edge-fw", [{"ip": "10.20.30.40", "mac": "aa:bb:cc:dd:ee:ff", "ifindex": "3"}])
    tok = console.session("viewer", "viewer1")
    _s, _h, text = console.request("GET", "/search?q=branch42", token=tok)
    assert "edge-fw" in text and "Devices" in text
    _s, _h, text = console.request("GET", "/search?q=aa:bb:cc", token=tok)
    assert "10.20.30.40" in text and "learned on edge-fw" in text
    _s, _h, text = console.request("GET", "/search?q=" + urllib.parse.quote("<script>x</script>"), token=tok)
    assert "<script>x</script>" not in text and "&lt;script&gt;x&lt;/script&gt;" in text
    _s, _h, text = console.request("GET", "/search?q=a", token=tok)
    assert "Type at least two characters" in text


# ---- paging -----------------------------------------------------------------------------

def test_audit_log_pages_instead_of_truncating(console):
    for i in range(230):
        console.m.db.audit("bulk", "test_event", f"t{i}", "")
    tok = console.session()
    _s, _h, page1 = console.request("GET", "/audit", token=tok)
    assert 'href="/audit?page=2">Older' in page1 and "Newer" not in page1
    _s, _h, page3 = console.request("GET", "/audit?page=3", token=tok)
    assert 'href="/audit?page=2">' in page3 and "Older" not in page3
    assert page3.count("test_event") >= 30


# ---- first admin setup -------------------------------------------------------------------

@pytest.fixture
def empty_console(tmp_path):
    web._SESSIONS.clear()
    web_ux._SETUP.update(hash="", expires=0.0)
    m = Manager(str(tmp_path / "home"))
    c = _Console(m)
    yield c
    web_ux._SETUP.update(hash="", expires=0.0)
    c.close()


def test_first_admin_setup_with_one_time_code(empty_console):
    c = empty_console
    status, _h, text = c.request("GET", "/login")
    assert status == 200 and "First-time setup" in text and 'action="/setup-admin"' in text
    path = os.path.join(c.m.paths.home, web_ux.SETUP_CODE_FILE)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    code = open(path, encoding="utf-8").read().strip()
    form = {"setup_code": "wrong-code", "username": "root-admin", "password": "a-long-enough-password",
            "password2": "a-long-enough-password"}
    status, _h, text = c.request("POST", "/setup-admin", form)
    assert status == 400 and c.m.users.count() == 0
    status, _h, text = c.request("POST", "/setup-admin", dict(form, setup_code=code, password2="different-password!"))
    assert status == 400 and "do not match" in text
    status, _h, text = c.request("POST", "/setup-admin", dict(form, setup_code=code, password="short", password2="short"))
    assert status == 400 and c.m.users.count() == 0
    status, headers, _ = c.request("POST", "/setup-admin", dict(form, setup_code=code))
    assert status == 303 and headers["Location"] == "/" and "ncsid=" in headers.get("Set-Cookie", "")
    assert c.m.users.get("root-admin")["role"] == "admin"
    assert not os.path.exists(path)
    # The setup path is closed once a user exists.
    status, headers, _ = c.request("POST", "/setup-admin", dict(form, username="second", setup_code=code))
    assert status == 303 and headers["Location"] == "/login" and c.m.users.count() == 1
    status, _h, text = c.request("GET", "/login")
    assert "First-time setup" not in text


def test_table_enhancement_script_is_served_with_pages(console):
    _s, _h, text = console.request("GET", "/runs", token=console.session())
    assert "th.classList.add('sortable')" in text and "Filter these rows" in text


# ---- account / self-service password -------------------------------------------

def _managed_login(console, username, password):
    code, headers, _ = console.request("POST", "/login", {"username": username, "password": password})
    assert code == 303
    return headers["Set-Cookie"].split("ncsid=", 1)[1].split(";", 1)[0]


def test_viewer_can_change_own_password_and_other_sessions_end(console):
    m = console.m
    m.users.create("vera", "vera-password-1", role="viewer")
    tok = _managed_login(console, "vera", "vera-password-1")
    other = _managed_login(console, "vera", "vera-password-1")
    csrf = web._SESSIONS[tok]["csrf"]
    code, _, page = console.request("GET", "/account", token=tok)
    assert code == 200 and "Change password" in page and 'href="/account"' in page
    code, _, page = console.request("POST", "/account-password", {"csrf": csrf, "current_password": "wrong-password-1",
                                    "new_password": "vera-password-2", "confirm_password": "vera-password-2"}, token=tok)
    assert code == 400 and "Current password is incorrect" in page and "vera-password-2" not in page
    code, _, page = console.request("POST", "/account-password", {"csrf": csrf, "current_password": "vera-password-1",
                                    "new_password": "short", "confirm_password": "short"}, token=tok)
    assert code == 400 and "at least" in page
    code, headers, _ = console.request("POST", "/account-password", {"csrf": csrf, "current_password": "vera-password-1",
                                       "new_password": "vera-password-2", "confirm_password": "vera-password-2"}, token=tok)
    assert code == 303 and headers["Location"].endswith("/account")
    fresh = headers["Set-Cookie"].split("ncsid=", 1)[1].split(";", 1)[0]
    assert m.users.verify("vera", "vera-password-2") and not m.users.verify("vera", "vera-password-1")
    code, _, page = console.request("GET", "/account", token=fresh)
    assert code == 200 and "Password changed" in page
    assert console.request("GET", "/account", token=other)[0] in (302, 303)   # signed out
    assert console.request("GET", "/account", token=tok)[0] in (302, 303)
    assert any(r["action"] == "password_change" for r in m.db.recent_audit(20))


def test_account_password_change_requires_csrf(console):
    console.m.users.create("vera", "vera-password-1", role="viewer")
    tok = _managed_login(console, "vera", "vera-password-1")
    code, _, _ = console.request("POST", "/account-password", {"current_password": "vera-password-1",
                                 "new_password": "vera-password-2", "confirm_password": "vera-password-2"}, token=tok)
    assert code in (400, 403)
    assert console.m.users.verify("vera", "vera-password-1")


# ---- device page never runs live checks; explicit Check now ------------------------

def test_device_page_shows_saved_checks_without_contacting_the_device(console, monkeypatch):
    from netconfig import portmon, appmon
    def boom(*a, **kw):
        raise AssertionError("page render must not contact the device")
    monkeypatch.setattr(portmon, "check_ports", boom)
    monkeypatch.setattr(appmon, "check_all", boom)
    m = console.m
    _device(m, "srv1", "192.0.2.10", device_type="system,application",
            monitor_ports="tcp/22", monitor_urls="https://192.0.2.10/health 200")
    m.db.record_result("srv1", "port", "tcp/22", "open", 3)
    m.db.record_result("srv1", "http", "https://192.0.2.10/health", "200", 41)
    m.db.record_result("srv1", "tls", "https://192.0.2.10/health", "valid", 90)
    code, _, page = console.request("GET", "/device?name=srv1", token=console.session())
    assert code == 200
    assert "tcp/22" in page and "open" in page and "valid · 90d left" in page
    assert "does not contact the device" in page and "Check now" in page
    _, _, viewer_page = console.request("GET", "/device?name=srv1", token=console.session("viewer", "viewer1"))
    assert "Check now" not in viewer_page


def test_check_now_runs_checks_saves_results_and_is_role_gated(console, monkeypatch):
    from netconfig import portmon
    calls = []
    monkeypatch.setattr(portmon, "check_ports", lambda host, spec, timeout=1.5: calls.append(host) or
                        [{"proto": "tcp", "port": 22, "state": "closed", "ms": None}])
    m = console.m
    _device(m, "srv1", "192.0.2.10", device_type="system", monitor_ports="tcp/22")
    code, _, _ = console.request("POST", "/device-monitor-check", {"csrf": "ux-csrf", "name": "srv1"},
                                 token=console.session("viewer", "viewer1"))
    assert code == 303 and calls == []
    code, headers, _ = console.request("POST", "/device-monitor-check", {"csrf": "ux-csrf", "name": "srv1"},
                                       token=console.session())
    assert code == 303 and headers["Location"].endswith("#tab-monitoring") and calls == ["192.0.2.10"]
    assert m.db.result_history("srv1", kind="port")[0]["status"] == "closed"
    assert any(r["action"] == "device_monitor_check" for r in m.db.recent_audit(10))


def test_viewer_cannot_start_a_compliance_audit(console):
    viewer = console.session("viewer", "viewer1")
    _, _, page = console.request("GET", "/compliance", token=viewer)
    assert "Run compliance audit" not in page
    code, _, _ = console.request("POST", "/compliance-run", {"csrf": "ux-csrf"}, token=viewer)
    assert code == 403
    assert console.m.db.conn.execute("SELECT COUNT(*) FROM compliance_runs").fetchone()[0] == 0
    code, _, _ = console.request("POST", "/compliance-run", {"csrf": "ux-csrf"}, token=console.session("operator", "op1"))
    assert code == 303


def test_dashboard_reachability_ignores_old_polls(console):
    import time as _t
    m = console.m
    for name, host in (("fresh", "192.0.2.21"), ("old", "192.0.2.22")):
        _device(m, name, host, snmp_version="v2c")
    m.inv.set_facts("fresh", reachable=True, last_polled=_t.time() - 60)
    m.inv.set_facts("old", reachable=True, last_polled=_t.time() - 3 * 86400)
    _, _, page = console.request("GET", "/dashboard", token=console.session())
    assert "1 / 2" in page and "1 not polled in the last 24 h" in page


def test_devices_home_uses_light_drift_check_not_full_diff(console, monkeypatch):
    m = console.m
    _device(m, "sw1", "192.0.2.31")
    m.store.save("sw1", "hostname sw1\n")
    m.store.set_baseline("sw1")
    m.store.save("sw1", "hostname sw1-changed\n")
    assert m.store.drift_state("sw1") == {"baselined": True, "drifted": True}
    assert m.store.drift("sw1")["drifted"] is True

    def no_full_diff(*a, **kw):
        raise AssertionError("list pages must not build full diffs")
    monkeypatch.setattr(m.store, "drift", no_full_diff)
    for path in ("/", "/dashboard"):
        code, _, page = console.request("GET", path, token=console.session())
        assert code == 200, path
    _, _, home = console.request("GET", "/", token=console.session())
    assert "drift" in home
