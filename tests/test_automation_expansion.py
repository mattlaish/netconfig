import json

import pytest

from netconfig.manager import Manager
from netconfig.structured_changes import StructuredChangeError
from netconfig.vendor_models import VendorModelError, validate_pack_spec
from netconfig.workflow import Workflow


def _manager(tmp_path):
    home = tmp_path / "home"
    m = Manager(str(home))
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


def _add_edge_devices(m, count=3):
    for i in range(2, count + 2):
        m.inv.upsert(
            name=f"sw{i}",
            host=f"192.0.2.{9 + i}",
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
        m.protocol_profiles.set(f"sw{i}", "gnmi", path="/", secret_ref=f"vault-sw{i}")


def _desired_state(m, *, name="edge-description", target_kind="device", target_value="sw1", operations=None):
    return m.desired_state.create(
        name=name,
        target_kind=target_kind,
        target_value=target_value,
        actor="operator",
        document={
            "operations": operations
            or [
                {
                    "resource": "interface_description",
                    "selectors": {"interface": "GigabitEthernet1"},
                    "value": "WAN uplink",
                }
            ]
        },
    )


def test_vm1_builtin_model_pack_resolves_only_allowlisted_resources(tmp_path):
    m = _manager(tmp_path)
    try:
        assert {x["name"] for x in m.vendor_models.list()} >= {
            "generic-openconfig",
            "cisco-iosxe-openconfig",
            "juniper-junos-openconfig",
            "arista-eos-openconfig",
            "huawei-vrp-openconfig",
        }
        item = m.vendor_models.resolve(
            "sw1",
            "interface_description",
            {"interface": "GigabitEthernet1"},
            "uplink",
        )
        assert item["pack"] == "cisco-iosxe-openconfig"
        assert item["gnmi_path"].endswith("/config/description")
        with pytest.raises(VendorModelError):
            m.vendor_models.resolve("sw1", "arbitrary_rpc", {}, "x")
        with pytest.raises(VendorModelError):
            m.vendor_models.resolve(
                "sw1", "interface_description", {"interface": "Gi1;rm -rf /"}, "x"
            )
    finally:
        m.close()


def test_vm1_custom_pack_rejects_url_and_traversal_passthrough():
    base = {
        "vendor": "example",
        "os_family": "exampleos",
        "resources": {
            "hostname": {
                "value_type": "string",
                "restconf_path": "https://evil.invalid/restconf/data/system/hostname",
                "restconf_json_key": "hostname",
                "gnmi_path": "/system/config/hostname",
                "netconf_container": ["system", "config", "hostname"],
                "netconf_namespace": "urn:example:system",
            }
        },
    }
    with pytest.raises(VendorModelError):
        validate_pack_spec(base)
    base["resources"]["hostname"]["restconf_path"] = "/restconf/data/system/%2e%2e/hostname"
    with pytest.raises(VendorModelError):
        validate_pack_spec(base)


def test_ph4_structured_change_records_durable_transaction(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        reads = iter([(False, {"protocol": "gnmi"}), (True, {"protocol": "gnmi"})])
        monkeypatch.setattr(
            m.structured_collector,
            "read_resource_value",
            lambda *args, **kwargs: next(reads),
        )
        monkeypatch.setattr(
            m.structured_collector,
            "gnmi_set_typed",
            lambda *args, **kwargs: {
                "changed": True,
                "verified": True,
                "rollback": "compensating_preimage_available",
            },
        )
        tx = m.structured_changes.execute_resource(
            device="sw1",
            resource="interface_enabled",
            selectors={"interface": "GigabitEthernet1"},
            value=True,
            actor="approver",
            approved=True,
            approval_ref="CR#1",
            source_kind="desired_state",
            source_ref="DS#1",
        )
        assert tx["state"] == "SUCCEEDED"
        assert tx["protocol"] == "gnmi"
        assert tx["pre_hash"] and tx["post_hash"]
        assert tx["pre_value"] is False
        assert tx["post_value"] is True
        assert tx["source_kind"] == "desired_state"
    finally:
        m.close()


def test_ph4_requires_real_change_request_reference(tmp_path):
    m = _manager(tmp_path)
    try:
        with pytest.raises(StructuredChangeError, match="change-request"):
            m.structured_changes.execute_resource(
                device="sw1",
                resource="interface_enabled",
                selectors={"interface": "GigabitEthernet1"},
                value=True,
                actor="approver",
                approved=True,
                approval_ref="approved-actor:approver",
            )
    finally:
        m.close()


def test_ph4_interrupted_recovery_reconciles_verified_remote_value(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        reads = iter([(False, {}), (True, {})])
        monkeypatch.setattr(m.structured_collector, "read_resource_value", lambda *a, **k: next(reads))
        monkeypatch.setattr(
            m.structured_collector,
            "gnmi_set_typed",
            lambda *a, **k: {"rollback": "compensating_preimage_available"},
        )
        tx = m.structured_changes.execute_resource(
            device="sw1",
            resource="interface_enabled",
            selectors={"interface": "GigabitEthernet1"},
            value=True,
            actor="approver",
            approved=True,
            approval_ref="CR#5",
            source_ref="CR#5",
        )
        m.db.conn.execute(
            "UPDATE structured_change_transactions SET state='RECOVERY_REQUIRED',verification_state='INTERRUPTED' WHERE id=?",
            (tx["id"],),
        )
        m.db.conn.commit()
        monkeypatch.setattr(m.structured_collector, "read_resource_value", lambda *a, **k: (True, {}))
        recovered = m.structured_changes.recover(tx["id"], actor="admin")
        assert recovered["state"] == "SUCCEEDED"
        assert recovered["verification_state"] == "RECOVERED_VERIFIED"
    finally:
        m.close()


def test_automation_request_freezes_structured_plan_and_fails_on_model_change(tmp_path):
    m = _manager(tmp_path)
    try:
        wf = Workflow(m.db, m)
        rid = wf.submit_automation(
            title="enable uplink",
            requested_by="operator",
            intent={
                "kind": "structured_change",
                "device": "sw1",
                "resource": "interface_enabled",
                "selectors": {"interface": "GigabitEthernet1"},
                "value": True,
            },
        )
        preview = wf.preview(rid)
        assert preview["automation"]["snapshot_matches"] is True
        m.vendor_models.bind("sw1", "generic-openconfig", actor="admin")
        with pytest.raises(ValueError, match="plan changed"):
            wf.approve(rid, "approver")
    finally:
        m.close()


def test_automation_request_submit_approve_execute_pipeline(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        wf = Workflow(m.db, m)
        rid = wf.submit_automation(
            title="enable uplink",
            requested_by="operator",
            intent={
                "kind": "structured_change",
                "device": "sw1",
                "resource": "interface_enabled",
                "selectors": {"interface": "GigabitEthernet1"},
                "value": True,
            },
        )
        wf.approve(rid, "approver")
        monkeypatch.setattr(
            m.structured_changes,
            "execute_resource",
            lambda **kwargs: {
                "id": 77,
                "state": "SUCCEEDED",
                "changed": True,
                "device": kwargs["device"],
            },
        )
        job = wf.execute(rid, "approver")
        assert job["ok_count"] == 1
        assert job["fail_count"] == 0
        assert wf.get(rid)["status"] == "executed"
    finally:
        m.close()


def test_na1_desired_state_compiles_publishes_and_applies_via_ph4(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        ds = _desired_state(m)
        plan = m.desired_state.plan(ds["id"])
        assert plan["targets"][0]["operations"][0]["pack"] == "cisco-iosxe-openconfig"
        published = m.desired_state.publish(ds["id"], "approver")
        assert published["state"] == "PUBLISHED"
        monkeypatch.setattr(
            m.structured_changes,
            "execute_resource",
            lambda **kwargs: {"id": 77, "state": "SUCCEEDED", "changed": True},
        )
        run = m.desired_state.apply(
            ds["id"], actor="approver", approved=True, approval_ref="CR#7"
        )
        assert run["state"] == "SUCCEEDED"
        assert run["results"][0]["transaction_id"] == 77
    finally:
        m.close()


def test_na1_rolls_back_prior_device_operations_on_failure(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        ds = _desired_state(
            m,
            name="two-op",
            operations=[
                {
                    "resource": "interface_description",
                    "selectors": {"interface": "GigabitEthernet1"},
                    "value": "one",
                },
                {
                    "resource": "interface_mtu",
                    "selectors": {"interface": "GigabitEthernet1"},
                    "value": 1500,
                },
            ],
        )
        m.desired_state.publish(ds["id"], "approver")
        calls = {"n": 0}

        def execute_resource(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise StructuredChangeError("simulated second operation failure")
            return {"id": 10, "state": "SUCCEEDED", "changed": True}

        monkeypatch.setattr(m.structured_changes, "execute_resource", execute_resource)
        monkeypatch.setattr(
            m.structured_changes,
            "rollback",
            lambda txid, **kwargs: {"id": 99, "state": "SUCCEEDED"},
        )
        run = m.desired_state.apply(
            ds["id"], actor="approver", approved=True, approval_ref="CR#8"
        )
        assert run["state"] == "FAILED"
        failure = next(item for item in run["results"] if not item["ok"])
        assert failure["rollback"] == [
            {"transaction_id": 10, "rollback_transaction_id": 99, "ok": True}
        ]
    finally:
        m.close()


def test_na2_campaign_builds_deterministic_waves_and_pauses_on_failure(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        _add_edge_devices(m, 3)
        ds = _desired_state(
            m,
            name="edge-enabled",
            target_kind="tag",
            target_value="edge",
            operations=[
                {
                    "resource": "interface_enabled",
                    "selectors": {"interface": "GigabitEthernet1"},
                    "value": True,
                }
            ],
        )
        m.desired_state.publish(ds["id"], "approver")
        campaign = m.campaigns.create(
            name="edge-wave",
            desired_state_id=ds["id"],
            wave_size=2,
            max_failures=0,
            actor="operator",
        )
        assert [t["wave"] for t in campaign["targets"]] == [1, 1, 2, 2]
        m.campaigns.start(campaign["id"], "operator")
        calls = {"n": 0}

        def apply(*args, **kwargs):
            calls["n"] += 1
            return {
                "state": "FAILED" if calls["n"] == 1 else "SUCCEEDED",
                "results": [{"transaction_id": calls["n"], "changed": False}],
                "run_id": calls["n"],
            }

        monkeypatch.setattr(m.desired_state, "apply", apply)
        result = m.campaigns.execute_next_wave(
            campaign["id"], actor="approver", approved=True, approval_ref="CR#20"
        )
        assert result["state"] == "PAUSED"
        assert sum(t["state"] == "FAILED" for t in result["targets"]) == 1
        with pytest.raises(Exception, match="unresolved"):
            m.campaigns.resume(campaign["id"], "operator")
    finally:
        m.close()


def test_na2_explicit_retry_advances_attempt_identity(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        ds = _desired_state(
            m,
            name="retry-enabled",
            operations=[
                {
                    "resource": "interface_enabled",
                    "selectors": {"interface": "GigabitEthernet1"},
                    "value": True,
                }
            ],
        )
        m.desired_state.publish(ds["id"], "approver")
        campaign = m.campaigns.create(
            name="retry-campaign",
            desired_state_id=ds["id"],
            max_failures=0,
            actor="operator",
        )
        m.campaigns.start(campaign["id"], "operator")
        refs = []

        def apply(*args, **kwargs):
            refs.append(kwargs["source_ref"])
            success = len(refs) > 1
            return {
                "state": "SUCCEEDED" if success else "FAILED",
                "results": [{"transaction_id": len(refs), "changed": success}],
                "run_id": len(refs),
            }

        monkeypatch.setattr(m.desired_state, "apply", apply)
        first = m.campaigns.execute_next_wave(
            campaign["id"], actor="approver", approved=True, approval_ref="CR#30"
        )
        assert first["state"] == "PAUSED"
        m.campaigns.retry_failed(campaign["id"], "operator")
        m.campaigns.resume(campaign["id"], "operator")
        second = m.campaigns.execute_next_wave(
            campaign["id"], actor="approver", approved=True, approval_ref="CR#31"
        )
        assert second["state"] == "SUCCEEDED"
        assert refs[0].endswith("/ATTEMPT#1")
        assert refs[1].endswith("/ATTEMPT#2")
    finally:
        m.close()


def test_na2_campaign_frozen_plan_rejects_mid_campaign_model_change(tmp_path):
    m = _manager(tmp_path)
    try:
        ds = _desired_state(m, name="frozen-plan")
        m.desired_state.publish(ds["id"], "approver")
        campaign = m.campaigns.create(
            name="frozen-campaign", desired_state_id=ds["id"], actor="operator"
        )
        m.campaigns.start(campaign["id"], "operator")
        m.vendor_models.bind("sw1", "generic-openconfig", actor="admin")
        wf = Workflow(m.db, m)
        with pytest.raises(ValueError, match="plan changed"):
            wf.submit_automation(
                title="wave",
                requested_by="operator",
                intent={"kind": "campaign_wave", "campaign_id": campaign["id"]},
            )
    finally:
        m.close()


def test_ni5_telemetry_persists_bounded_window_samples_and_summary(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        sub = m.telemetry.create(
            name="if-state",
            device="sw1",
            path="/interfaces/interface/state",
            mode="ON_CHANGE",
            actor="operator",
        )
        monkeypatch.setattr(
            m.structured_collector,
            "subscribe_window",
            lambda *args, **kwargs: (
                json.dumps(
                    [
                        {"timestamp": 1_700_000_000_000_000_000, "updates": [{"val": 1}]},
                        {"timestamp": 1_700_000_001_000_000_000, "updates": [{"val": 3}]},
                    ]
                ),
                {"mode": "stream", "window_complete": True},
            ),
        )
        result = m.telemetry.capture_window(sub["id"], duration_seconds=5, actor="operator")
        assert result["records"] == 2
        rows = m.telemetry.samples(sub["id"])
        assert len(rows) == 2
        assert rows[0]["device"] == "sw1"
        summary = m.telemetry.summary(sub["id"], value_path="$.updates[0].val")
        assert summary["numeric_count"] == 2
        assert summary["min"] == 1
        assert summary["max"] == 3
        deleted = m.telemetry.delete(sub["id"], actor="operator")
        assert deleted["deleted"] == sub["id"]
        assert m.telemetry.get(sub["id"]) is None
    finally:
        m.close()


def test_gnmi_typed_set_performs_post_read_verification(tmp_path, monkeypatch):
    m = _manager(tmp_path)
    try:
        dev, profile = m._structured_profile_for("sw1")
        monkeypatch.setattr(
            m.structured_collector,
            "_secret",
            lambda *a, **k: {"username": "u", "password": "p"},
        )
        replies = iter(
            [
                ({"response": "ok"}, 10, {"tls_verify": True, "mtls": False}),
                (
                    {"notification": {"update": {"val": True}}},
                    20,
                    {"tls_verify": True, "mtls": False},
                ),
            ]
        )
        monkeypatch.setattr(m.structured_collector, "_gnmi_run", lambda *a, **k: next(replies))
        out = m.structured_collector.gnmi_set_typed(
            dev,
            profile,
            path="/interfaces/interface[name=GigabitEthernet1]/config/enabled",
            value=True,
            actor="approver",
            approved=True,
        )
        assert out["verified"] is True
        assert out["rollback"] == "not_protocol_native"
    finally:
        m.close()


def test_netconf_typed_config_is_generated_from_model_not_caller_xml(tmp_path):
    m = _manager(tmp_path)
    try:
        resolved = m.vendor_models.resolve(
            "sw1",
            "interface_description",
            {"interface": "GigabitEthernet1"},
            "safe < description",
        )
        payload = m.structured_collector._netconf_typed_config(resolved)
        assert b"GigabitEthernet1" in payload
        assert b"safe &lt; description" in payload
        assert b"<rpc" not in payload
        assert b"<config" not in payload or b"urn:ietf:params:xml:ns:netconf:base:1.0" in payload
    finally:
        m.close()


def test_ha1_drain_refuses_new_automation_and_persists_state(tmp_path):
    m = _manager(tmp_path)
    try:
        drained = m.ha.drain_current_node(actor="admin", reason="maintenance")
        assert drained["state"] == "DRAINING"
        assert m.ha.accepts_automation_work() is False
        with pytest.raises(RuntimeError, match="DRAINING"):
            m.structured_changes.execute_resource(
                device="sw1",
                resource="interface_enabled",
                selectors={"interface": "GigabitEthernet1"},
                value=True,
                actor="approver",
                approved=True,
                approval_ref="CR#90",
            )
        active = m.ha.activate_current_node(actor="admin")
        assert active["state"] == "ACTIVE"
    finally:
        m.close()


def test_ha1_readiness_is_explicitly_not_multi_node_on_sqlite(tmp_path):
    m = _manager(tmp_path)
    try:
        report = m.ha.readiness()
        assert report["backend"] == "sqlite"
        assert report["ready_for_multi_node"] is False
        assert report["automatic_database_failover"] is False
        drill = m.ha.record_drill(
            kind="BACKUP_VERIFY",
            actor="operator",
            state="NOT_RUN",
            detail={"reason": "no production service"},
        )
        assert drill["state"] == "NOT_RUN"
    finally:
        m.close()


def test_new_api_scopes_are_registered():
    from netconfig.apitokens import VALID_SCOPES

    assert {
        "automation:read",
        "automation:write",
        "telemetry:read",
        "telemetry:write",
        "desired:read",
        "desired:write",
        "campaign:read",
        "campaign:write",
        "model:read",
        "model:write",
        "ha:read",
        "ha:write",
    } <= VALID_SCOPES
