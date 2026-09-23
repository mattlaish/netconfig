import http.client
import json
import re
import threading
import urllib.parse

from netconfig.manager import Manager
import netconfig.web as web
from netconfig.web import Console, _Server


def _manager(tmp_path):
    m = Manager(str(tmp_path / "home"))
    m.inv.upsert(
        name="sw1",
        host="192.0.2.10",
        port=22,
        platform="cisco_iosxe",
        device_type="network",
        secret_ref="",
        enable_ref="",
        use_key=False,
        legacy=False,
        scrub=True,
        enabled=True,
        tags=["edge"],
        notes="",
        snmp_version="",
        snmp_ref=None,
    )
    m.protocol_profiles.set("sw1", "gnmi", path="/", secret_ref="vault-sw1")
    return m


def _start_console(manager, role="operator"):
    web._SESSIONS.clear()
    token = "ui1-session"
    csrf = "ui1-csrf"
    web._SESSIONS[token] = {
        "username": "ui1tester",
        "role": role,
        "csrf": csrf,
        "created": 1.0,
    }
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, token, csrf


def _request(server, token, method, path, form=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Cookie": f"ncsid={token}"}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form, doseq=True)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    data = response.read()
    headers_out = dict(response.getheaders())
    status = response.status
    conn.close()
    return status, headers_out, data


def _stop(server, thread, manager, close_manager=True):
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    web._SESSIONS.clear()
    if close_manager:
        manager.close()


def test_ui1_viewer_can_read_all_operations_tabs_but_has_no_mutation_forms(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "viewer")
    try:
        expected = {
            "structured": "Structured transaction ledger",
            "telemetry": "Subscriptions",
            "models": "Vendor model packs",
            "desired": "Configuration baselines / templates",
            "campaigns": "Fleet campaigns",
            "ha": "HA readiness",
        }
        for tab, marker in expected.items():
            status, _headers, data = _request(server, token, "GET", f"/operations?tab={tab}")
            text = data.decode()
            assert status == 200
            assert marker in text
            assert ">Operations<" in text
            assert not re.search(r"\son(?:click|submit|change|input|load|error)=", text, flags=re.I)
            assert not re.search(r'\sstyle="', text, flags=re.I)
        status, _headers, data = _request(server, token, "GET", "/operations?tab=models")
        assert status == 200
        assert "Admin model-pack operations" not in data.decode()
    finally:
        _stop(server, thread, manager)


def test_ui1_structured_change_submits_durable_approval_without_network_write(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-structured-submit",
            {
                "csrf": csrf,
                "device": "sw1",
                "resource": "interface_enabled",
                "selectors": json.dumps({"interface": "GigabitEthernet1"}),
                "value": "true",
                "title": "Enable uplink",
            },
        )
        assert status == 303
        assert headers["Location"].startswith("/request?id=")
        requests = manager.db.conn.execute(
            "SELECT * FROM change_requests ORDER BY id DESC"
        ).fetchall()
        assert len(requests) == 1
        request = dict(requests[0])
        assert request["mode"] == "automation"
        assert request["status"] == "pending"
        assert manager.db.conn.execute(
            "SELECT COUNT(*) AS c FROM structured_change_transactions"
        ).fetchone()["c"] == 0

        status, _headers, data = _request(server, token, "GET", headers["Location"])
        text = data.decode()
        assert status == 200
        assert "Frozen submitted intent" in text
        assert "Submitted SHA-256" in text
        assert "CURRENT" in text
        assert "Execute approved automation" not in text
    finally:
        _stop(server, thread, manager)


def test_ui1_csrf_and_viewer_mutation_are_fail_closed(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "viewer")
    try:
        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-desired-create",
            {
                "csrf": csrf,
                "name": "blocked",
                "target_kind": "device",
                "target_value": "sw1",
                "document": json.dumps({"operations": []}),
            },
        )
        assert status == 403
        assert manager.desired_state.list() == []

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-model-bind",
            {"csrf": "wrong", "device": "sw1", "pack": "generic-openconfig"},
        )
        assert status == 403
        assert manager.vendor_models.list_bindings() == []
    finally:
        _stop(server, thread, manager)


def test_ui1_telemetry_create_edit_enable_disable_and_delete(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-telemetry-create",
            {
                "csrf": csrf,
                "name": "if-state",
                "device": "sw1",
                "path": "/interfaces",
                "mode": "ON_CHANGE",
                "sample_interval_ms": "10000",
                "heartbeat_interval_ms": "0",
                "window_seconds": "5",
                "collection_interval_seconds": "30",
                "retention_days": "7",
            },
        )
        assert status == 303
        sub = manager.telemetry.list()[0]
        assert sub["name"] == "if-state"
        sid = sub["id"]

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-telemetry-update",
            {
                "csrf": csrf,
                "sid": str(sid),
                "name": "if-state-updated",
                "path": "/interfaces/interface[name=Ethernet1]",
                "mode": "SAMPLE",
                "sample_interval_ms": "15000",
                "heartbeat_interval_ms": "0",
                "window_seconds": "5",
                "collection_interval_seconds": "45",
                "retention_days": "14",
            },
        )
        assert status == 303
        sub = manager.telemetry.get(sid)
        assert sub["name"] == "if-state-updated"
        assert sub["mode"] == "SAMPLE"
        assert sub["retention_days"] == 14

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-telemetry-action",
            {"csrf": csrf, "sid": str(sid), "action": "disable"},
        )
        assert status == 303
        assert manager.telemetry.get(sid)["enabled"] == 0

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-telemetry-action",
            {"csrf": csrf, "sid": str(sid), "action": "delete"},
        )
        assert status == 303
        assert manager.telemetry.get(sid) is None
    finally:
        _stop(server, thread, manager)


def test_ui1_admin_model_binding_and_ha_node_lifecycle(tmp_path):
    manager = _manager(tmp_path)
    manager.db.heartbeat_cluster_node(manager.cluster_node_id, __import__("time").time())
    server, thread, token, csrf = _start_console(manager, "admin")
    try:
        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-model-bind",
            {"csrf": csrf, "device": "sw1", "pack": "generic-openconfig"},
        )
        assert status == 303
        assert manager.vendor_models.binding("sw1") == "generic-openconfig"

        status, _headers, data = _request(
            server,
            token,
            "GET",
            "/operations?tab=models&device=sw1&protocol=gnmi",
        )
        text = data.decode()
        assert status == 200
        assert "effective model" in text
        assert "interface_description" in text

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-ha-node",
            {
                "csrf": csrf,
                "node_id": manager.cluster_node_id,
                "state": "DRAINING",
                "reason": "maintenance",
            },
        )
        assert status == 303
        assert manager.ha.current_node_state() == "DRAINING"

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-ha-node",
            {
                "csrf": csrf,
                "node_id": manager.cluster_node_id,
                "state": "ACTIVE",
                "reason": "",
            },
        )
        assert status == 303
        assert manager.ha.current_node_state() == "ACTIVE"
    finally:
        _stop(server, thread, manager)


def test_ui1_desired_state_publish_apply_request_and_campaign_wave_request(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, csrf = _start_console(manager, "approver")
    try:
        document = {
            "operations": [
                {
                    "resource": "interface_description",
                    "selectors": {"interface": "GigabitEthernet1"},
                    "value": "managed",
                }
            ]
        }
        status, headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-desired-create",
            {
                "csrf": csrf,
                "name": "edge-state",
                "target_kind": "device",
                "target_value": "sw1",
                "description": "UI-1",
                "document": json.dumps(document),
            },
        )
        assert status == 303
        ds = manager.desired_state.list()[0]
        dsid = ds["id"]

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-desired-publish",
            {"csrf": csrf, "dsid": str(dsid)},
        )
        assert status == 303
        assert manager.desired_state.get(dsid)["state"] == "PUBLISHED"

        status, headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-desired-apply-request",
            {"csrf": csrf, "dsid": str(dsid), "rollback_on_failure": "1"},
        )
        assert status == 303
        assert headers["Location"].startswith("/request?id=")
        cr = manager.db.conn.execute(
            "SELECT * FROM change_requests ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(cr)["target_value"] == "desired_apply"

        status, headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-campaign-create",
            {
                "csrf": csrf,
                "name": "edge-rollout",
                "desired_state_id": str(dsid),
                "wave_size": "1",
                "canary_size": "0",
                "max_failures": "0",
                "rollback_on_failure": "1",
            },
        )
        assert status == 303
        campaign = manager.campaigns.list()[0]
        cid = campaign["id"]

        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-campaign-action",
            {"csrf": csrf, "cid": str(cid), "action": "start"},
        )
        assert status == 303
        assert manager.campaigns.get(cid)["state"] == "RUNNING"

        status, headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-campaign-wave-request",
            {"csrf": csrf, "cid": str(cid)},
        )
        assert status == 303
        assert headers["Location"].startswith("/request?id=")
        cr = manager.db.conn.execute(
            "SELECT * FROM change_requests ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(cr)["target_value"] == "campaign_wave"
    finally:
        _stop(server, thread, manager)


def test_ui1_recovery_admin_boundary_and_drill_detail(tmp_path):
    manager = _manager(tmp_path)
    # Create a synthetic interrupted ledger row without any network I/O.
    now = 1.0
    cur = manager.db.conn.execute(
        "INSERT INTO structured_change_transactions "
        "(device,protocol,actor,source_kind,source_ref,approval_ref,idempotency_key,operation,resource,request_json,state,created_ts,started_ts) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "sw1", "gnmi", "approver", "manual", "", "CR#1", "ui1-stale", "replace",
            "interface_enabled", json.dumps({"resource": "interface_enabled", "selectors": {}, "value": True}),
            "RUNNING", now, now,
        ),
    )
    manager.db.conn.commit()
    txid = cur.lastrowid

    server, thread, token, csrf = _start_console(manager, "operator")
    try:
        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-structured-mark",
            {"csrf": csrf, "stale_seconds": "1"},
        )
        assert status == 403
        assert manager.structured_changes.get(txid)["state"] == "RUNNING"
    finally:
        _stop(server, thread, manager, close_manager=False)

    server, thread, token, csrf = _start_console(manager, "admin")
    try:
        status, _headers, _data = _request(
            server,
            token,
            "POST",
            "/ops-structured-mark",
            {"csrf": csrf, "stale_seconds": "1"},
        )
        assert status == 303
        assert manager.structured_changes.get(txid)["state"] == "RECOVERY_REQUIRED"

        drill = manager.ha.start_drill(
            kind="BACKUP_VERIFY", actor="admin", detail={"artifact": "backup.dump"}, verification_ref="sha256:abc"
        )
        status, _headers, data = _request(
            server,
            token,
            "GET",
            f'/operations?tab=ha&drill={drill["id"]}',
        )
        text = data.decode()
        assert status == 200
        assert "backup.dump" in text
        assert "Complete drill" in text
    finally:
        _stop(server, thread, manager)


def test_ui1_uses_sidebar_navigation_and_neutral_branding(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "operator")
    try:
        status, _headers, data = _request(server, token, "GET", "/protocols")
        text = data.decode()
        assert status == 200
        assert 'class="sidebar"' in text
        assert 'class="nav-sidebar"' in text
        nav = text.split('<nav class="nav-sidebar">', 1)[1].split('</nav>', 1)[0]
        assert '>Collection<' not in nav
        assert 'Device collection settings' in text
        assert 'network devices such as switches, routers, and firewalls' in text
        assert 'Advanced: change a network-device collection profile' in text
        assert '<span class="logo">NC</span>' in text
        assert '<span>NetConfig v' in text
        assert 'NetConfig v' in text
    finally:
        _stop(server, thread, manager)


def test_ui1_intent_automation_tab_is_http_renderable(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "operator")
    try:
        status, _headers, data = _request(server, token, "GET", "/operations?tab=intents")
        text = data.decode()
        assert status == 200
        assert "Automation Requests" in text
        assert "Automation requests" in text
        assert "no automation requests" in text
        assert "Start from the owning workflow" in text
        assert "Server error" not in text
    finally:
        _stop(server, thread, manager)


def test_ui1_operations_overview_is_task_oriented_and_no_duplicate_intelligence_nav(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "operator")
    try:
        status, _headers, data = _request(server, token, "GET", "/operations")
        text = data.decode()
        assert status == 200
        assert "Operations workspace" in text
        assert "Check templates & drift" in text
        assert "Analyze the network" in text
        assert "Controlled changes" in text
        assert "Configuration Baselines / Templates &amp; Drift" in text
        assert "Advanced operations" in text
        # Network Intelligence is an Operations tab, not a duplicate top-level navigation item.
        nav = text.split('<nav class="nav-sidebar">', 1)[1].split('</nav>', 1)[0]
        assert 'Network Intelligence' not in nav
        assert 'href="/operations?tab=intelligence"' in text
    finally:
        _stop(server, thread, manager)


def test_ui1_mib_library_explains_purpose_and_hides_raw_library_by_default(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "operator")
    try:
        status, _headers, data = _request(server, token, "GET", "/mib")
        text = data.decode()
        assert status == 200
        assert "MIB support" in text
        assert "MIB files are dictionaries, not features." in text
        assert "operator-facing health cards" in text
        assert "sensor-grid" in text
        assert "Advanced: MIB library" in text
    finally:
        _stop(server, thread, manager)


def test_ui1_snmp_device_health_cards_use_cached_evidence_without_extra_poll(tmp_path):
    manager = _manager(tmp_path)
    manager.inv.upsert(
        name="sw1", host="192.0.2.10", port=22, platform="cisco_iosxe",
        device_type="network", secret_ref="", enable_ref="", use_key=False,
        legacy=False, scrub=True, enabled=True, tags=["edge"], notes="",
        snmp_version="v3", snmp_ref=None,
    )
    manager.inv.set_facts(
        "sw1", reachable=True, sysname="sw1", sysdescr="test switch",
        sysobjectid="1.3.6.1.4.1.9", uptime="1d", contact="", location="", error="",
    )
    manager.inv.set_interfaces("sw1", [
        {"ifindex": "1", "descr": "Gi1", "admin": "up", "oper": "up", "speed": 1000000000,
         "in_octets": 10, "out_octets": 20, "in_errors": 0, "out_errors": 0}
    ])
    manager.db.set_mac_table("sw1", [
        {"mac": "00:11:22:33:44:55", "port": "1", "ifindex": "1", "ifdescr": "Gi1"}
    ])
    manager.db.set_arp("sw1", [
        {"ip": "192.0.2.55", "mac": "00:11:22:33:44:55", "ifindex": "1"}
    ])
    manager.db.set_neighbors("sw1", [
        {"protocol": "lldp", "local_port": "Gi1", "neighbor_device": "core",
         "sys_name": "core", "managed_neighbor": True}
    ])
    manager.db.set_mib_values("sw1", [
        {"oid": "1.2.3.1", "name": "arubaWiredLoopProtectPortEnable.1", "value": "1", "mib_source": "ARUBA"},
        {"oid": "1.2.3.2", "name": "arubaWiredLoopProtectPortLoopDetected.1", "value": "2", "mib_source": "ARUBA"},
        {"oid": "1.2.3.3", "name": "arubaWiredLoopProtectPortLoopCount.1", "value": "0", "mib_source": "ARUBA"},
        {"oid": "1.2.3.4", "name": "arubaWiredLoopProtectPortLastLoopTime.1", "value": "0", "mib_source": "ARUBA"},
    ], roots=1)
    # MC-1 contract: collection/evidence ingestion refreshes the canonical Sensor
    # snapshot; opening the WebUI must only consume that snapshot.
    manager.sensors.refresh_inventory_health(manager.inv)
    server, thread, token, _csrf = _start_console(manager, "operator")
    try:
        status, _headers, data = _request(server, token, "GET", "/snmp?device=sw1")
        text = data.decode()
        assert status == 200
        assert "Device health" in text
        assert "Opening this page does not add polling or device I/O." in text
        assert "FDB / MAC learning" in text
        assert "ARP / IP neighbor" in text
        assert "Topology neighbors" in text
        assert "Loop Protection" in text
        assert "No loop detected" in text
        assert "Enabled ports: 1" in text
        assert text.index("Device health") < text.index("Advanced SNMP / OID explorer")
    finally:
        _stop(server, thread, manager)


def test_ui1_network_device_edit_shows_netflow_section_server_side(tmp_path):
    manager = _manager(tmp_path)
    server, thread, token, _csrf = _start_console(manager, "admin")
    try:
        status, _headers, data = _request(server, token, "GET", "/device-new?name=sw1")
        text = data.decode()
        assert status == 200
        assert '<div id=netflow_section>' in text
        assert 'collect NetFlow from this device' in text
        assert 'id=netflow_section style="display:none"' not in text
    finally:
        _stop(server, thread, manager)


def test_ui1_nonnetwork_device_edit_keeps_netflow_section_hidden(tmp_path):
    manager = _manager(tmp_path)
    manager.inv.upsert(
        name="app1", host="192.0.2.20", port=22, platform="generic",
        device_type="application", secret_ref="", enable_ref="", use_key=False,
        legacy=False, scrub=True, enabled=True, tags=[], notes="",
        snmp_version="", snmp_ref=None, netflow=False, monitor_ports="", monitor_urls="",
    )
    server, thread, token, _csrf = _start_console(manager, "admin")
    try:
        status, _headers, data = _request(server, token, "GET", "/device-new?name=app1")
        text = data.decode()
        assert status == 200
        assert '<div id=netflow_section hidden>' in text
    finally:
        _stop(server, thread, manager)


def test_ui1_snmp_device_renders_recent_sensor_transition_timeline(tmp_path):
    manager = _manager(tmp_path)
    manager.inv.upsert(
        name="sw-history", host="192.0.2.30", port=22, platform="cisco_iosxe",
        device_type="network", secret_ref="", enable_ref="", use_key=False,
        legacy=False, scrub=True, enabled=True, tags=[], notes="",
        snmp_version="v3", snmp_ref=None,
    )
    manager.inv.set_facts(
        "sw-history", reachable=True, sysname="sw-history", sysdescr="test switch",
        sysobjectid="1.3.6.1.4.1.9", uptime="1d", contact="", location="", error="",
    )
    manager.sensors.upsert(
        "interface.status", device="sw-history", resource="Gi1/0/1",
        value="UP", status="OK", source="test")
    manager.sensors.upsert(
        "interface.status", device="sw-history", resource="Gi1/0/1",
        value="DOWN", status="WARNING", source="test")

    server, thread, token, _csrf = _start_console(manager, "operator")
    try:
        status, _headers, data = _request(server, token, "GET", "/snmp?device=sw-history")
        text = data.decode()
        assert status == 200
        assert "Recent sensor changes" in text
        assert "interface.status" in text
        assert "Gi1/0/1" in text
        assert ">OK<" in text
        assert ">WARNING<" in text
        assert "UNKNOWN means evidence is unavailable, not a failure verdict." in text
    finally:
        _stop(server, thread, manager)
