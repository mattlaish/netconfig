from __future__ import annotations

import http.client
import json
import threading

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig.postgres_core import SERIAL_ID_TABLES, postgres_schema_statements
from netconfig.web import Console, _Server


def _device(manager, name, host):
    manager.inv.upsert(
        name=name, host=host, port=22, platform="cisco_iosxe", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["mc11"], notes="", snmp_version="", snmp_ref=None,
    )


def _manager(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "r1", "192.0.2.1")
    _device(manager, "fw1", "192.0.2.2")
    _device(manager, "r2", "192.0.2.3")
    return manager


def _seed_paths(manager):
    # Forward path to destination endpoint prefix.
    manager.analytics.add_l3_route(
        device="r1", vrf="blue", destination_prefix="10.2.2.20/32",
        next_device="fw1", next_hop="192.0.2.2", outgoing_interface="Gi0/1",
        protocol="ospf", evidence_ref="route:r1:fwd", actor="seed")
    manager.analytics.add_l3_route(
        device="fw1", vrf="blue", destination_prefix="10.2.2.20/32",
        next_device="r2", next_hop="192.0.2.3", outgoing_interface="Gi0/2",
        protocol="static", evidence_ref="route:fw1:fwd", actor="seed")
    manager.analytics.add_l3_route(
        device="r2", vrf="blue", destination_prefix="10.2.2.20/32",
        outgoing_interface="Vlan20", protocol="connected", terminal=True,
        evidence_ref="route:r2:fwd", actor="seed")
    # Return path to source endpoint prefix.
    manager.analytics.add_l3_route(
        device="r2", vrf="blue", destination_prefix="10.1.1.10/32",
        next_device="fw1", next_hop="192.0.2.2", outgoing_interface="Gi0/2",
        protocol="ospf", evidence_ref="route:r2:return", actor="seed")
    manager.analytics.add_l3_route(
        device="fw1", vrf="blue", destination_prefix="10.1.1.10/32",
        next_device="r1", next_hop="192.0.2.1", outgoing_interface="Gi0/1",
        protocol="static", evidence_ref="route:fw1:return", actor="seed")
    manager.analytics.add_l3_route(
        device="r1", vrf="blue", destination_prefix="10.1.1.10/32",
        outgoing_interface="Vlan10", protocol="connected", terminal=True,
        evidence_ref="route:r1:return", actor="seed")


def _seed_endpoint(manager, device, ip, mac, vlan, ifindex):
    manager.db.set_ip_neighbors(device, [{
        "ip": ip, "address_family": "ipv4", "mac": mac, "ifindex": str(ifindex),
        "ifdescr": f"Gi0/{ifindex}", "neighbor_type": "dynamic", "state": "reachable",
        "source": "mc11-test",
    }])
    manager.db.set_vlan_fdb(device, [{
        "vlan_id": str(vlan), "fdb_id": str(vlan), "mac": mac,
        "bridge_port": str(ifindex), "ifindex": str(ifindex), "ifdescr": f"Gi0/{ifindex}",
        "status": "learned", "source": "mc11-test",
    }])


def _proposal():
    return {
        "kind": "structured_change",
        "device": "fw1",
        "resource": "interface_enabled",
        "selectors": {"interface": "GigabitEthernet2"},
        "value": True,
    }


def test_mc11_schema_revision_and_postgres_surface(tmp_path):
    manager = _manager(tmp_path)
    try:
        assert manager.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
        tables = {r["name"] for r in manager.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"change_planning_evidence", "change_plans"} <= tables
        assert {"change_planning_evidence", "change_plans"} <= SERIAL_ID_TABLES
        ddl = "\n".join(postgres_schema_statements())
        assert "CREATE TABLE IF NOT EXISTS change_planning_evidence" in ddl
        assert "CREATE TABLE IF NOT EXISTS change_plans" in ddl
    finally:
        manager.close()


def test_mc11_forward_return_paths_and_endpoint_attachment(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_paths(manager)
        _seed_endpoint(manager, "r1", "10.1.1.10", "aa:bb:cc:dd:ee:01", 10, 10)
        _seed_endpoint(manager, "r2", "10.2.2.20", "aa:bb:cc:dd:ee:02", 20, 20)
        plan = manager.change_planning.plan(
            source="10.1.1.10", destination="10.2.2.20", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32",
            service="tcp/443", actor="alice")
        result = plan["result"]
        assert result["source"]["device"] == "r1"
        assert result["destination"]["device"] == "r2"
        assert [x["device"] for x in result["forward_path"]["hops"]] == ["r1", "fw1", "r2"]
        assert [x["device"] for x in result["return_path"]["hops"]] == ["r2", "fw1", "r1"]
        assert result["forward_path"]["hops"][0]["outgoing_interface"] == "Gi0/1"
        assert result["endpoint_attachment_evidence"]["source"]["vlan_id"] == "10"
    finally:
        manager.close()


def test_mc11_ambiguous_endpoint_fails_closed(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    try:
        monkeypatch.setattr(manager, "endpoint_inventory", lambda query=None: [
            {"mac": "aa", "ipv4": [query], "ipv6": [], "status": "ATTACHED", "attachment": {"device": "r1"}},
            {"mac": "bb", "ipv4": [query], "ipv6": [], "status": "ATTACHED", "attachment": {"device": "r2"}},
        ])
        plan = manager.change_planning.plan(
            source="10.1.1.10", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32", actor="alice")
        result = plan["result"]
        assert result["source"]["status"] == "AMBIGUOUS"
        assert result["forward_path"]["status"] == "UNKNOWN"
        assert result["planning_status"] == "INCOMPLETE_EVIDENCE"
        assert result["proposed_structured_changes"] == []
    finally:
        manager.close()


def test_mc11_policy_gap_exact_change_point_and_why_here(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_paths(manager)
        evidence = manager.change_planning.observe_policy_evidence(
            device="fw1", evidence_kind="FIREWALL", direction="FORWARD", vrf="blue",
            source_selector="r1", destination_selector="r2", service="tcp/443", state="MISSING",
            evidence_ref="firewall:fw1:policy:edge-web", metadata={"proposal": _proposal()}, actor="seed")
        plan = manager.change_planning.plan(
            source="r1", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32",
            service="tcp/443", actor="alice")
        result = plan["result"]
        assert result["planning_status"] == "GAPS_IDENTIFIED"
        assert len(result["configuration_gaps"]) == 1
        gap = result["configuration_gaps"][0]
        assert gap["device"] == "fw1" and gap["path_index"] == 1
        assert gap["evidence_ref"] == evidence["evidence_ref"]
        assert gap["why_here"]["reason"].startswith("persisted policy evidence")
        assert result["exact_change_points"][0]["device"] == "fw1"
        assert result["proposed_structured_changes"] == [_proposal()]
    finally:
        manager.close()


def test_mc11_acl_firewall_nat_pbr_and_routing_policy_evidence_are_supported(tmp_path):
    manager = _manager(tmp_path)
    try:
        for idx, kind in enumerate(("ACL", "FIREWALL", "NAT", "PBR", "ROUTING_POLICY"), start=1):
            row = manager.change_planning.observe_policy_evidence(
                device="fw1", evidence_kind=kind, direction="BOTH", vrf="blue",
                source_selector="*", destination_selector="*", service="any", state="PRESENT",
                evidence_ref=f"policy:{kind}:{idx}", actor="seed")
            assert row["evidence_kind"] == kind
            assert row["fresh"] is True
        assert {x["evidence_kind"] for x in manager.change_planning.evidence(device="fw1")} == {
            "ACL", "FIREWALL", "NAT", "PBR", "ROUTING_POLICY"
        }
    finally:
        manager.close()


def test_mc11_service_dependency_context_is_evidence_scoped(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_paths(manager)
        manager.dependencies.put_entity("svc:web", "SERVICE", "web", metadata={"device": "r2"}, actor="seed")
        manager.dependencies.put_entity("db:orders", "DATABASE", "orders", metadata={"device": "fw1"}, actor="seed")
        manager.dependencies.put_dependency(
            "svc:web", "db:orders", "USES_DATABASE", evidence_state="CONFIGURED",
            provenance="service-catalog", actor="seed")
        plan = manager.change_planning.plan(
            source="r1", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32", actor="alice")
        ctx = plan["result"]["service_dependency_context"]
        assert {x["entity_key"] for x in ctx["entities"]} == {"svc:web", "db:orders"}
        assert len(ctx["dependencies"]) == 1
        assert ctx["dependencies"][0]["relationship"] == "USES_DATABASE"
    finally:
        manager.close()


def test_mc11_candidate_what_if_closes_known_gap_without_mutating_evidence(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_paths(manager)
        manager.change_planning.observe_policy_evidence(
            device="fw1", evidence_kind="ACL", direction="FORWARD", vrf="blue",
            source_selector="r1", destination_selector="r2", service="tcp/443", state="DENY",
            evidence_ref="acl:fw1:101", metadata={"proposal": _proposal()}, actor="seed")
        plan = manager.change_planning.plan(
            source="r1", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32",
            service="tcp/443", actor="alice")
        before = manager.change_planning.evidence(device="fw1")
        what_if = manager.change_planning.what_if(plan["id"], [_proposal()], actor="alice")
        after = manager.change_planning.evidence(device="fw1")
        assert what_if["status"] == "CANDIDATE_CLOSES_ALL_KNOWN_GAPS"
        assert len(what_if["closed_gaps"]) == 1 and what_if["remaining_gaps"] == []
        assert what_if["network_write"] is False and what_if["persisted_evidence_mutated"] is False
        assert before == after
    finally:
        manager.close()


def test_mc11_proposal_schema_rejects_arbitrary_command_payload(tmp_path):
    manager = _manager(tmp_path)
    try:
        with pytest.raises(ValueError, match="unsupported fields"):
            manager.change_planning.observe_policy_evidence(
                device="fw1", evidence_kind="FIREWALL", direction="FORWARD", vrf="blue",
                state="MISSING", evidence_ref="bad:proposal",
                metadata={"proposal": {**_proposal(), "command": "configure terminal"}}, actor="seed")
        with pytest.raises(ValueError, match="structured_change"):
            manager.change_planning.observe_policy_evidence(
                device="fw1", evidence_kind="FIREWALL", direction="FORWARD", vrf="blue",
                state="MISSING", evidence_ref="bad:kind",
                metadata={"proposal": {**_proposal(), "kind": "shell"}}, actor="seed")
    finally:
        manager.close()


def test_mc11_same_evidence_is_deterministic_and_reuses_plan_identity(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_paths(manager)
        first = manager.change_planning.plan(
            source="r1", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32",
            service="tcp/443", actor="alice")
        second = manager.change_planning.plan(
            source="r1", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32",
            service="tcp/443", actor="bob")
        assert first["id"] == second["id"]
        assert first["plan_key"] == second["plan_key"]
        assert first["result"]["evidence_fingerprint"] == second["result"]["evidence_fingerprint"]
        assert len(manager.change_planning.plans()) == 1
    finally:
        manager.close()


def _start_api(manager):
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _api(server, token, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode()
    data = json.loads(raw or "null")
    status = response.status
    conn.close()
    return status, data


def test_mc11_api_scope_boundary_and_plan_readback(tmp_path):
    manager = _manager(tmp_path)
    _seed_paths(manager)
    reader = ApiTokens(manager.db.conn).create(
        "mc11-reader", {"analytics:read"}, created_by="test", role="viewer")[1]
    operator = ApiTokens(manager.db.conn).create(
        "mc11-operator", {"analytics:read", "analytics:write"}, created_by="test", role="operator")[1]
    server, thread = _start_api(manager)
    try:
        status, _ = _api(server, reader, "POST", "/api/v1/change-planning/plans", {
            "source": "r1", "destination": "r2", "vrf": "blue",
            "destination_prefix": "10.2.2.20/32", "source_prefix": "10.1.1.10/32",
        })
        assert status == 403
        status, created = _api(server, operator, "POST", "/api/v1/change-planning/plans", {
            "source": "r1", "destination": "r2", "vrf": "blue",
            "destination_prefix": "10.2.2.20/32", "source_prefix": "10.1.1.10/32",
        })
        assert status == 201
        status, readback = _api(server, reader, "GET", f"/api/v1/change-planning/plans/{created['id']}")
        assert status == 200 and readback["id"] == created["id"]
        assert readback["result"]["authority_boundary"]["network_write"] is False
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()


def test_mc11_api_policy_evidence_and_what_if_are_bounded(tmp_path):
    manager = _manager(tmp_path)
    _seed_paths(manager)
    operator = ApiTokens(manager.db.conn).create(
        "mc11-api", {"analytics:read", "analytics:write"}, created_by="test", role="operator")[1]
    server, thread = _start_api(manager)
    try:
        status, evidence = _api(server, operator, "POST", "/api/v1/change-planning/evidence", {
            "device": "fw1", "evidence_kind": "FIREWALL", "direction": "FORWARD", "vrf": "blue",
            "source_selector": "r1", "destination_selector": "r2", "service": "tcp/443",
            "state": "MISSING", "evidence_ref": "fw:missing",
            "metadata": {"proposal": _proposal()},
        })
        assert status == 201 and evidence["state"] == "MISSING"
        status, plan = _api(server, operator, "POST", "/api/v1/change-planning/plans", {
            "source": "r1", "destination": "r2", "vrf": "blue", "service": "tcp/443",
            "destination_prefix": "10.2.2.20/32", "source_prefix": "10.1.1.10/32",
        })
        assert status == 201 and plan["result"]["planning_status"] == "GAPS_IDENTIFIED"
        status, candidate = _api(
            server, operator, "POST", f"/api/v1/change-planning/plans/{plan['id']}/what-if",
            {"candidate_changes": [_proposal()]})
        assert status == 200
        assert candidate["network_write"] is False
        assert candidate["status"] == "CANDIDATE_CLOSES_ALL_KNOWN_GAPS"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()


def test_mc11_analysis_never_calls_network_or_structured_execution(tmp_path, monkeypatch):
    manager = _manager(tmp_path)
    try:
        _seed_paths(manager)
        manager.change_planning.observe_policy_evidence(
            device="fw1", evidence_kind="PBR", direction="FORWARD", vrf="blue",
            source_selector="r1", destination_selector="r2", service="any", state="MISSING",
            evidence_ref="pbr:missing", metadata={"proposal": _proposal()}, actor="seed")
        monkeypatch.setattr(manager, "run", lambda *a, **k: pytest.fail("planner called arbitrary command path"))
        monkeypatch.setattr(manager, "collect", lambda *a, **k: pytest.fail("planner triggered collection"))
        monkeypatch.setattr(
            manager.structured_changes, "execute_resource",
            lambda *a, **k: pytest.fail("planner executed Structured Change"))
        plan = manager.change_planning.plan(
            source="r1", destination="r2", vrf="blue",
            destination_prefix="10.2.2.20/32", source_prefix="10.1.1.10/32", actor="alice")
        assert plan["result"]["authority_boundary"] == {
            "analysis_only": True, "network_write": False, "arbitrary_command": False,
            "what_if_executes": False, "proposal_requires_existing_structured_change_approval": True,
        }
        assert manager.db.conn.execute("SELECT COUNT(*) AS n FROM structured_change_transactions").fetchone()["n"] == 0
    finally:
        manager.close()
