from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.parse
from pathlib import Path

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig.web import Console, _Server
from netconfig.workflow import Workflow
import netconfig.web as web


def _device(manager, name, host):
    manager.inv.upsert(
        name=name, host=host, port=22, platform="cisco_iosxe", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["r65"], notes="", snmp_version="", snmp_ref=None,
    )


def _manager(tmp_path):
    m = Manager(str(tmp_path / "home"))
    _device(m, "r1", "192.0.2.1")
    _device(m, "fw1", "192.0.2.2")
    _device(m, "r2", "192.0.2.3")
    m.protocol_profiles.set("fw1", "gnmi", path="/", secret_ref="vault-fw1")
    return m


def _seed_paths(m):
    rows = [
        ("r1", "10.2.2.20/32", "fw1", "192.0.2.2", "Gi0/1", False),
        ("fw1", "10.2.2.20/32", "r2", "192.0.2.3", "Gi0/2", False),
        ("r2", "10.2.2.20/32", "", "", "Vlan20", True),
        ("r2", "10.1.1.10/32", "fw1", "192.0.2.2", "Gi0/2", False),
        ("fw1", "10.1.1.10/32", "r1", "192.0.2.1", "Gi0/1", False),
        ("r1", "10.1.1.10/32", "", "", "Vlan10", True),
    ]
    for idx, (dev, prefix, next_device, next_hop, interface, terminal) in enumerate(rows):
        m.analytics.add_l3_route(
            device=dev, vrf="blue", destination_prefix=prefix,
            next_device=next_device, next_hop=next_hop, outgoing_interface=interface,
            protocol="connected" if terminal else "static", terminal=terminal,
            evidence_ref=f"r65-route:{idx}", actor="seed")


def _proposal():
    return {
        "device": "fw1",
        "resource": "interface_enabled",
        "selectors": {"interface": "GigabitEthernet2"},
        "value": True,
    }


def _incident_plan(m):
    incident = m.incidents.create("R65 workflow incident", severity="HIGH", created_by="operator")
    key = incident["incident_key"]
    m.db.audit("sensor", "r65_seed", "fw1", "persisted investigation evidence")
    audit_id = m.db.conn.execute("SELECT MAX(id) AS id FROM audit").fetchone()["id"]
    m.incidents.link_evidence(key, "audit", audit_id, "operator", "r65 seed")
    _seed_paths(m)
    m.change_planning.observe_policy_evidence(
        device="fw1", evidence_kind="FIREWALL", direction="FORWARD", vrf="blue",
        source_selector="r1", destination_selector="r2", service="tcp/443", state="MISSING",
        evidence_ref="r65:fw1:policy", metadata={"proposal": _proposal()}, actor="operator")
    plan = m.change_planning.plan(
        source="r1", destination="r2", vrf="blue",
        destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32",
        service="tcp/443", actor="operator", incident_ref=key)
    return incident, plan


def test_r65_change_plan_persists_incident_context_without_schema_change(tmp_path):
    m = _manager(tmp_path)
    try:
        incident, plan = _incident_plan(m)
        assert plan["input"]["incident_ref"] == incident["incident_key"]
        assert plan["result"]["workflow_context"]["incident_ref"] == incident["incident_key"]
        assert m.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
    finally:
        m.close()


def test_r65_workflow_context_requires_exact_persisted_proposal(tmp_path):
    m = _manager(tmp_path)
    try:
        incident, plan = _incident_plan(m)
        wf = Workflow(m.db, m)
        ctx = {"incident_ref": incident["incident_key"], "plan_id": plan["id"], "proposal_index": 0}
        rid = wf.submit_automation(
            title="R65 exact proposal",
            intent={"kind": "structured_change", **_proposal()},
            requested_by="operator", context=ctx)
        assert wf.automation_context(rid) == ctx
        with pytest.raises(ValueError, match="does not match"):
            wf.submit_automation(
                title="tampered",
                intent={"kind": "structured_change", **{**_proposal(), "value": False}},
                requested_by="operator", context=ctx)
    finally:
        m.close()


def test_r65_end_to_end_persisted_journey_links_post_change_evidence(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        incident, plan = _incident_plan(m)
        wf = Workflow(m.db, m)
        ctx = {"incident_ref": incident["incident_key"], "plan_id": plan["id"], "proposal_index": 0}
        rid = wf.submit_automation(
            title="R65 proposal", intent={"kind": "structured_change", **_proposal()},
            requested_by="operator", context=ctx)
        before = m.operator_workflow.view(incident["incident_key"], plan_id=plan["id"], request_id=rid)
        assert before["selected_request"]["request"]["status"] == "pending"
        assert before["selected_transaction"] is None

        wf.approve(rid, "approver")
        reads = iter([(False, {}), (True, {})])
        monkeypatch.setattr(m.structured_collector, "read_resource_value", lambda *a, **k: next(reads))
        monkeypatch.setattr(m.structured_collector, "gnmi_set_typed", lambda *a, **k: {"rollback": "available"})
        wf.execute(rid, "approver")

        after = m.operator_workflow.view(incident["incident_key"], plan_id=plan["id"], request_id=rid)
        assert after["selected_request"]["request"]["status"] == "executed"
        assert after["selected_transaction"]["state"] == "SUCCEEDED"
        assert after["selected_transaction"]["verification_state"] == "VERIFIED"
        assert after["post_change_evidence"]
        assert after["post_change_evidence"][0]["event"]["request_id"] == rid
        assert after["stages"][-1]["state"] == "COMPLETE"
        assert after["truth"]["approval_bypass"] is False
        assert after["truth"]["page_triggered_polling"] is False
    finally:
        m.close()


def _api_request(server, token, method, path, form=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + token}
    body = ""
    if form is not None:
        body = urllib.parse.urlencode(form)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=headers)
    res = conn.getresponse()
    raw = res.read()
    status = res.status
    conn.close()
    return status, json.loads(raw or b"{}")


def test_r65_read_only_api_requires_incident_analytics_and_automation_scopes(tmp_path):
    m = _manager(tmp_path)
    server = None
    try:
        incident, plan = _incident_plan(m)
        tokens = ApiTokens(m.db.conn)
        _, limited = tokens.create("limited", ["incident:read", "analytics:read"], role="viewer")
        _, reader = tokens.create(
            "r65-reader", ["incident:read", "analytics:read", "automation:read"], role="viewer")
        Console.manager = m
        Console.tls_enabled = False
        server = _Server(("127.0.0.1", 0), Console)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        path = f"/api/v1/operator-workflows/{incident['incident_key']}?plan_id={plan['id']}"
        status, _ = _api_request(server, limited, "GET", path)
        assert status == 403
        status, payload = _api_request(server, reader, "GET", path)
        assert status == 200
        assert payload["schema"] == "r65-operator-workflow-1"
        assert payload["selected_plan"]["id"] == plan["id"]
        assert payload["truth"]["direct_network_write_authority"] is False
    finally:
        if server:
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        m.close()


def _start_console(manager, role="viewer"):
    web._SESSIONS.clear()
    token = "r65-session"
    csrf = "r65-csrf"
    username = "r65-user"
    if not manager.users.exists(username):
        manager.users.create(username, "test-password", role=role)
    web._SESSIONS[token] = {
        "username": username, "role": role, "csrf": csrf,
        "created": time.time(), "last_seen": time.time(),
    }
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, token, csrf


def _web_request(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Cookie": f"ncsid={token}"})
    res = conn.getresponse(); data = res.read(); status = res.status; conn.close()
    return status, data.decode("utf-8", "replace")


def test_r65_web_journey_renders_all_persisted_stages_for_viewer(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    server = None
    try:
        incident, plan = _incident_plan(m)
        # A workflow page must not trigger collection/polling as a side effect.
        monkeypatch.setattr(m, "collect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("polling not allowed")))
        server, thread, token, _csrf = _start_console(m, "viewer")
        status, text = _web_request(
            server, token,
            f"/operations?tab=workflow&incident={incident['incident_key']}&plan={plan['id']}")
        assert status == 200
        for label in ("Incident", "Hypothesis", "Evidence", "Topology Path", "Proposed Change", "Approval", "Structured Change", "Validation"):
            assert label in text
        assert "does not poll devices" in text
        assert "Submit frozen proposal for approval" not in text
    finally:
        if server:
            server.shutdown(); server.server_close(); thread.join(timeout=5); web._SESSIONS.clear()
        m.close()


def test_r65_release_identity_and_no_mc12_contract():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "netconfig.spec").read_text()
    roadmap = (root / "ROADMAP.md").read_text()
    assert "Release:        67.2%{?dist}" in spec
    assert "R65" in roadmap and "R66" in roadmap
    assert "do not create mc-12" in roadmap.lower()


def test_r65_runner_historical_baseline_detects_release66_drift(tmp_path):
    import subprocess, sys
    out = tmp_path / "evidence"
    cp = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "qualification/r65_runner.py"),
         "--output-dir", str(out), "--include-local", "--gate", "R65-BASE-001"],
        cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True,
    )
    assert cp.returncode == 1, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["product_baseline"] == "2.0.0-65"
    assert campaign["gates"][0]["status"] == "FAIL"
    assert campaign["production_operator_workflow_claim"] is False
    assert campaign["all_required_live_operator_gates_selected"] is False
    assert campaign["live_operator_pass_count"] == 0
    assert campaign["release_promotion_performed"] is False


def test_r65_live_gate_without_operator_lab_is_blocked_not_false_pass(tmp_path):
    import subprocess, sys
    out = tmp_path / "live"
    cp = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "qualification/r65_runner.py"),
         "--output-dir", str(out), "--live", "--gate", "R65-OP-010"],
        cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["gates"][0]["status"] in {"BLOCKED_ENVIRONMENT", "NOT_RUN"}
    assert campaign["production_operator_workflow_claim"] is False


def test_r65_runner_fixed_hooks_redaction_and_no_partial_live_claim():
    import importlib.util, sys
    root = Path(__file__).resolve().parents[1]
    source = (root / "qualification/r65_runner.py").read_text()
    assert "--command" not in source
    assert "shell=True" not in source
    assert "LIVE_OPERATOR" in source
    assert "selected_live_ids == required_live_ids" in source
    spec = importlib.util.spec_from_file_location("r65_runner_test", root / "qualification/r65_runner.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    redacted = mod.redact("Bearer abc token=xyz password:secret")
    assert "abc" not in redacted and "xyz" not in redacted and "secret" not in redacted
    assert sum(g.evidence_class == "LIVE_OPERATOR" for g in mod.GATES) == 10


def test_r65_runner_and_wrapper_are_executable():
    root = Path(__file__).resolve().parents[1]
    for relative in ("qualification/r65_runner.py", "packaging/r65-qualify.sh"):
        assert (root / relative).stat().st_mode & 0o777 == 0o755
