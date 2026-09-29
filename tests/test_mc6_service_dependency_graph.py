import http.client
import json
import threading
import time
import urllib.parse

import pytest

from netconfig.apitokens import ApiTokens
from netconfig.dependencies import ENTITY_TYPES, EVIDENCE_STATES, RELATIONSHIPS
from netconfig.manager import Manager
from netconfig.postgres_core import postgres_schema_statements
import netconfig.web as web
from netconfig.web import Console, _Server


def _device(manager, name, host):
    manager.inv.upsert(
        name=name, host=host, port=22, platform="cisco_iosxe", device_type="network",
        secret_ref="", enable_ref="", use_key=False, legacy=False, scrub=True,
        enabled=True, tags=["mc6"], notes="", snmp_version="", snmp_ref=None,
    )


def _manager(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    _device(manager, "r1", "192.0.2.1")
    _device(manager, "r2", "192.0.2.2")
    _device(manager, "r3", "192.0.2.3")
    return manager


def _seed_entities(manager):
    items = [
        ("service:payment", "SERVICE", "Payment API"),
        ("application:app01", "APPLICATION", "APP01"),
        ("database:db01", "DATABASE", "DB01"),
        ("storage:san01", "STORAGE", "SAN01"),
        ("lb:edge", "LOAD_BALANCER", "Edge LB"),
        ("dns:corp", "DNS", "Corporate DNS"),
        ("vm:app01", "VM", "APP01 VM"),
        ("hypervisor:hv01", "HYPERVISOR", "HV01"),
    ]
    for key, kind, name in items:
        manager.dependencies.put_entity(key, kind, name, actor="seed")
    return items


def test_mc6_schema_revision_and_additive_tables(tmp_path):
    manager = _manager(tmp_path)
    try:
        assert manager.db.storage_status()["schema_revision"] == "mc11-topology-change-planning-1"
        tables = {r["name"] for r in manager.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"service_entities", "service_dependencies"} <= tables
        pg = "\n".join(postgres_schema_statements()).lower()
        assert "create table if not exists service_entities" in pg
        assert "create table if not exists service_dependencies" in pg
    finally:
        manager.close()


def test_mc6_all_required_entity_and_relationship_types_are_supported(tmp_path):
    manager = _manager(tmp_path)
    try:
        items = _seed_entities(manager)
        assert {x[1] for x in items} == set(ENTITY_TYPES)
        entities = manager.dependencies.entities(limit=100)
        assert {x["entity_type"] for x in entities} == set(ENTITY_TYPES)
        # Exercise every relationship without relying on temporal correlation.
        keys = [x[0] for x in items]
        for index, relationship in enumerate(RELATIONSHIPS):
            target = keys[(index + 1) % len(keys)]
            source = keys[index % len(keys)]
            dep = manager.dependencies.put_dependency(
                source, target, relationship, evidence_state="CONFIGURED",
                provenance="operator:test", actor="alice")
            assert dep["relationship"] == relationship
            assert dep["freshness"] == "CONFIGURED"
    finally:
        manager.close()


def test_mc6_freshness_unknown_and_inferred_fail_closed_by_default(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_entities(manager)
        now = time.time()
        manager.dependencies.put_dependency(
            "service:payment", "application:app01", "DEPENDS_ON",
            evidence_state="DISCOVERED", provenance="cmdb", evidence_ref="cmdb:1",
            observed_ts=now - 7200, max_age_seconds=300, actor="seed")
        manager.dependencies.put_dependency(
            "service:payment", "database:db01", "USES_DATABASE",
            evidence_state="INFERRED", provenance="flow-map", evidence_ref="flow:42",
            observed_ts=now, max_age_seconds=3600, actor="seed")
        manager.dependencies.put_dependency(
            "service:payment", "dns:corp", "USES_DNS",
            evidence_state="UNKNOWN", provenance="inventory-gap", actor="seed")

        graph = manager.dependencies.graph("service:payment", now=now)
        assert len(graph["nodes"]) == 1
        by_state = {x["evidence_state"]: x for x in graph["edges"]}
        assert by_state["DISCOVERED"]["freshness"] == "STALE"
        assert by_state["DISCOVERED"]["traversed"] is False
        assert by_state["INFERRED"]["exclusion_reason"] == "INFERRED_REQUIRES_OPT_IN"
        assert by_state["UNKNOWN"]["exclusion_reason"] == "UNKNOWN"
        assert graph["semantics"]["unknown_is_failure"] is False

        opt_in = manager.dependencies.graph(
            "service:payment", include_inferred=True, now=now)
        assert {n["entity_key"] for n in opt_in["nodes"]} == {
            "service:payment", "database:db01"}
    finally:
        manager.close()


def test_mc6_bounded_traversal_and_cycle_safety(tmp_path):
    manager = _manager(tmp_path)
    try:
        for i in range(8):
            manager.dependencies.put_entity(f"service:n{i}", "SERVICE", f"N{i}", actor="seed")
        for i in range(7):
            manager.dependencies.put_dependency(
                f"service:n{i}", f"service:n{i+1}", "DEPENDS_ON",
                evidence_state="CONFIGURED", provenance="test", actor="seed")
        manager.dependencies.put_dependency(
            "service:n4", "service:n1", "DEPENDS_ON",
            evidence_state="CONFIGURED", provenance="cycle-test", actor="seed")

        graph = manager.dependencies.graph("service:n0", max_depth=8, max_nodes=6)
        assert len(graph["nodes"]) <= 6
        assert graph["truncated"] is True
        assert graph["truncation_reason"] == "max_nodes"
        assert graph["summary"]["cycle_edges"] >= 1
        with pytest.raises(ValueError, match="max_depth"):
            manager.dependencies.graph("service:n0", max_depth=9)
        with pytest.raises(ValueError, match="max_nodes"):
            manager.dependencies.graph("service:n0", max_nodes=251)
    finally:
        manager.close()


def test_mc6_impact_reuses_impact_simulator_and_preserves_service_types(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_entities(manager)
        manager.dependencies.put_dependency(
            "service:payment", "application:app01", "DEPENDS_ON",
            evidence_state="CONFIGURED", provenance="operator", actor="seed")
        manager.dependencies.put_dependency(
            "application:app01", "database:db01", "USES_DATABASE",
            evidence_state="DISCOVERED", provenance="cmdb", evidence_ref="cmdb:app-db",
            max_age_seconds=3600, actor="seed")
        impact = manager.dependencies.impact("service:payment")
        affected = {x["affected_object"]: x for x in impact["affected"]}
        assert affected["application:app01"]["object_type"] == "APPLICATION"
        assert affected["application:app01"]["relationship"] == "DEPENDS_ON"
        assert affected["database:db01"]["object_type"] == "DATABASE"
        assert affected["database:db01"]["relationship"] == "USES_DATABASE"
        assert affected["database:db01"]["evidence_refs"] == ("cmdb:app-db",)
    finally:
        manager.close()


def test_mc6_network_overlay_preserves_vrf_and_fails_closed_on_ambiguity(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.dependencies.put_entity("service:payment", "SERVICE", "Payment API", actor="seed")
        manager.analytics.add_l3_route(
            device="r1", vrf="blue", destination_prefix="10.20.0.0/16",
            next_hop="192.0.2.2", next_device="r2", actor="seed")
        manager.analytics.add_l3_route(
            device="r2", vrf="blue", destination_prefix="10.20.0.0/16",
            terminal=True, outgoing_interface="Gi0/2", actor="seed")
        # Same prefix in red must not leak into blue.
        manager.analytics.add_l3_route(
            device="r1", vrf="red", destination_prefix="10.20.0.0/16",
            next_hop="192.0.2.3", next_device="r3", actor="seed")
        overlay = manager.dependencies.network_overlay(
            "service:payment", "r1", "blue", "10.20.0.0/16")
        assert overlay["path"]["status"] == "REACHED_TERMINAL"
        assert [x["device"] for x in overlay["path"]["hops"]] == ["r1", "r2"]
        assert {n["label"] for n in overlay["nodes"] if n["kind"] == "NETWORK_DEVICE"} == {"r1", "r2"}
        assert overlay["device_io_performed"] is False

        manager.analytics.add_l3_route(
            device="r1", vrf="amber", destination_prefix="198.51.100.0/24",
            next_hop="192.0.2.2", next_device="r2", actor="seed")
        manager.analytics.add_l3_route(
            device="r1", vrf="amber", destination_prefix="198.51.100.0/24",
            next_hop="192.0.2.3", next_device="r3", actor="seed")
        ambiguous = manager.dependencies.network_overlay(
            "service:payment", "r1", "amber", "198.51.100.0/24")
        assert ambiguous["path"]["status"] == "AMBIGUOUS"
        assert ambiguous["overlay_complete"] is False
        # No next-hop IP is promoted into a managed-device node.
        assert all(n["label"] not in {"192.0.2.2", "192.0.2.3"} for n in ambiguous["nodes"])
    finally:
        manager.close()


def test_mc6_validation_prevents_cross_tenant_temporal_and_invalid_route_scope(tmp_path):
    manager = _manager(tmp_path)
    try:
        _seed_entities(manager)
        with pytest.raises(ValueError, match="tenant scope"):
            manager.dependencies.entities(tenant_id="other")
        with pytest.raises(ValueError, match="evidence_ref"):
            manager.dependencies.put_dependency(
                "service:payment", "application:app01", "DEPENDS_ON",
                evidence_state="DISCOVERED", provenance="temporal-only", actor="seed")
        with pytest.raises(ValueError, match="VRF"):
            manager.dependencies.put_dependency(
                "service:payment", "application:app01", "DEPENDS_ON",
                evidence_state="CONFIGURED", provenance="operator", vrf="blue", actor="seed")
        assert set(EVIDENCE_STATES) == {"CONFIGURED", "DISCOVERED", "INFERRED", "UNKNOWN"}
    finally:
        manager.close()


def _start(manager):
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
    status = response.status
    conn.close()
    return status, json.loads(raw or "null")


def test_mc6_api_scope_boundary_and_bounded_graph_query(tmp_path):
    manager = _manager(tmp_path)
    reader = ApiTokens(manager.db.conn).create(
        "mc6-reader", {"analytics:read"}, role="viewer")[1]
    operator = ApiTokens(manager.db.conn).create(
        "mc6-operator", {"analytics:read", "analytics:write"}, role="operator")[1]
    server, thread = _start(manager)
    try:
        status, _ = _api(server, reader, "POST", "/api/v1/dependencies/entities", {
            "entity_key": "service:payment", "entity_type": "SERVICE", "name": "Payment API"})
        assert status == 403
        for key, kind, name in [
            ("service:payment", "SERVICE", "Payment API"),
            ("application:app01", "APPLICATION", "APP01")]:
            status, body = _api(server, operator, "POST", "/api/v1/dependencies/entities", {
                "entity_key": key, "entity_type": kind, "name": name})
            assert status == 201 and body["entity_key"] == key
        status, edge = _api(server, operator, "POST", "/api/v1/dependencies/edges", {
            "source_key": "service:payment", "target_key": "application:app01",
            "relationship": "DEPENDS_ON", "evidence_state": "CONFIGURED",
            "provenance": "api:test"})
        assert status == 201 and edge["freshness"] == "CONFIGURED"
        status, graph = _api(server, reader, "GET",
                             "/api/v1/dependencies/graph/service%3Apayment?max_depth=3&max_nodes=20")
        assert status == 200 and graph["summary"]["nodes"] == 2
        status, body = _api(server, reader, "GET",
                            "/api/v1/dependencies/graph/service%3Apayment?max_depth=99")
        assert status == 400 and "max_depth" in body["detail"]
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5); manager.close()


def _web_request(server, token, path):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    conn.request("GET", path, headers={"Cookie": f"ncsid={token}"})
    response = conn.getresponse(); data = response.read().decode(); status = response.status
    conn.close(); return status, data


def test_mc6_web_view_distinguishes_evidence_and_viewer_has_no_write_forms(tmp_path):
    manager = _manager(tmp_path)
    _seed_entities(manager)
    manager.dependencies.put_dependency(
        "service:payment", "application:app01", "DEPENDS_ON",
        evidence_state="CONFIGURED", provenance="operator", actor="seed")
    manager.dependencies.put_dependency(
        "service:payment", "database:db01", "USES_DATABASE",
        evidence_state="INFERRED", provenance="candidate", evidence_ref="candidate:1",
        max_age_seconds=3600, actor="seed")
    manager.dependencies.put_dependency(
        "service:payment", "dns:corp", "USES_DNS",
        evidence_state="UNKNOWN", provenance="missing-discovery", actor="seed")
    web._SESSIONS.clear()
    token = "mc6-viewer"
    web._SESSIONS[token] = {"username": "viewer", "role": "viewer", "csrf": "x", "created": 1.0}
    server, thread = _start(manager)
    try:
        status, text = _web_request(server, token, "/dependencies?root=service%3Apayment")
        assert status == 200
        assert "Service &amp; Dependency Graph" in text
        assert "CONFIGURED" in text and "INFERRED" in text and "UNKNOWN" in text
        assert "UNKNOWN means insufficient evidence" in text
        assert 'action="/dependency-entity-save"' not in text
        assert 'action="/dependency-edge-save"' not in text
        assert "performs no device polling" in text
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        web._SESSIONS.clear(); manager.close()
