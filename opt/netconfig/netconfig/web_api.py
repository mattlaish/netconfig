"""Bearer API routing extracted from the monolithic web console (PH-1)."""

import json
import urllib.parse
from pathlib import Path

from .apitokens import ApiTokens
from .debug import DebugBundle
from .evidence_signing import signing_status


class WebApiMixin:
    def _api_token(self):
        # Never accept reusable bearer credentials over cleartext LAN HTTP.
        # Loopback is allowed for the documented local reverse-proxy pattern.
        peer = self._client_ip()
        if not self.tls_enabled and peer not in ("127.0.0.1", "::1", "localhost"):
            return None
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return ApiTokens(self.manager.db.conn).verify(auth[7:].strip())

    def _api_json(self, payload, status=200):
        self._send(json.dumps(payload, indent=2, sort_keys=True), status,
                   "application/json; charset=utf-8", [("Cache-Control", "no-store")])

    def _handle_api_post(self, path, form):
        token = self._api_token()
        if not token:
            self._api_json({"error": "invalid_or_missing_bearer_token"}, 401); return True
        actor = "api:" + token["name"]
        def _form_json(name, default=None):
            raw = (form.get(name) or [None])[0]
            if raw in (None, ""):
                return default
            return json.loads(raw)

        def _automation_required_scope(kind):
            return {
                "desired_apply": "desired:write",
                "campaign_wave": "campaign:write",
            }.get(kind, "automation:write")

        if path == "/api/v1/analytics/l3/routes":
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                terminal = str((form.get("terminal") or [""])[0]).lower() in {"1", "true", "yes", "on"}
                value = self.manager.analytics.add_l3_route(
                    device=(form.get("device") or [""])[0],
                    vrf=(form.get("vrf") or ["default"])[0],
                    destination_prefix=(form.get("destination_prefix") or [""])[0],
                    protocol=(form.get("protocol") or [""])[0],
                    next_hop=(form.get("next_hop") or [""])[0],
                    outgoing_interface=(form.get("outgoing_interface") or [""])[0],
                    next_device=(form.get("next_device") or [""])[0],
                    metric=int((form.get("metric") or ["0"])[0] or 0),
                    terminal=terminal, evidence_ref=(form.get("evidence_ref") or [""])[0],
                    actor=actor)
            except Exception as exc:
                self._api_json({"error": "l3_route_observation_failed", "detail": str(exc)}, 400); return True
            self._api_json(value, 201); return True
        if path == "/api/v1/analytics/l3/path/simulate":
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                value = self.manager.analytics.simulate_l3_path(
                    (form.get("source_device") or [""])[0],
                    (form.get("vrf") or ["default"])[0],
                    (form.get("destination_prefix") or [""])[0],
                    actor=actor, max_hops=int((form.get("max_hops") or ["16"])[0] or 16))
            except Exception as exc:
                self._api_json({"error": "l3_path_simulation_failed", "detail": str(exc)}, 400); return True
            self._api_json(value, 201); return True
        if path == "/api/v1/analytics/l3/dependencies/analyze":
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                value = self.manager.analytics.analyze_route_dependencies(
                    (form.get("failed_device") or [""])[0], actor=actor)
            except Exception as exc:
                self._api_json({"error": "route_dependency_analysis_failed", "detail": str(exc)}, 400); return True
            self._api_json(value, 201); return True
        if path == "/api/v1/analytics/refresh":
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                object_id = str((form.get("object_id") or [""])[0]).strip()
                if not object_id or not self.manager.inv.get(object_id):
                    raise ValueError("managed object_id is required")
                value = self.manager.analytics.refresh(object_id, actor=actor)
            except Exception as exc:
                self._api_json({"error": "analytics_refresh_failed", "detail": str(exc)}, 400); return True
            self._api_json(value, 201); return True
        if path == "/api/v1/analytics/impact/simulate":
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                object_id = str((form.get("object_id") or [""])[0]).strip()
                max_depth = int((form.get("max_depth") or ["5"])[0])
                if not object_id or not self.manager.inv.get(object_id):
                    raise ValueError("managed object_id is required")
                value = self.manager.analytics.simulate_impact(object_id, actor=actor, max_depth=max_depth)
            except Exception as exc:
                self._api_json({"error": "impact_simulation_failed", "detail": str(exc)}, 400); return True
            self._api_json(value, 201); return True
        if path.startswith("/api/v1/analytics/insights/") and path.endswith("/state"):
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                insight_id = int(path.split("/")[-2])
                value = self.manager.analytics.set_state(
                    insight_id, (form.get("state") or [""])[0], actor, (form.get("note") or [""])[0])
            except Exception as exc:
                self._api_json({"error": "insight_state_failed", "detail": str(exc)}, 400); return True
            self._api_json(value); return True
        if path == "/api/v1/analytics/expire":
            if "analytics:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "analytics:write+operator"}, 403); return True
            try:
                value = self.manager.analytics.expire_stale(actor=actor, max_age_seconds=int((form.get("max_age_seconds") or ["604800"])[0]))
            except Exception as exc:
                self._api_json({"error": "insight_expire_failed", "detail": str(exc)}, 400); return True
            self._api_json(value); return True
        if path == "/api/v1/automation-requests":
            try:
                intent = _form_json("intent", {}) or {}
                kind = str(intent.get("kind") or "").lower()
                required = _automation_required_scope(kind)
                if "automation:write" not in token["scopes"] or required not in token["scopes"]:
                    self._api_json(
                        {"error": "insufficient_scope", "required": f"automation:write+{required}"}, 403
                    )
                    return True
                if token.get("role") not in {"operator", "approver", "admin"}:
                    self._api_json({"error": "insufficient_role", "required": "operator"}, 403)
                    return True
                rid = self.wf.submit_automation(
                    title=(form.get("title") or [""])[0] or f"Automation {kind}",
                    intent=intent, requested_by=actor,
                )
                item = self.wf.get(rid)
            except Exception as exc:
                self._api_json({"error": "automation_request_submit_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path.startswith("/api/v1/automation-requests/"):
            rest = path[len("/api/v1/automation-requests/"):].strip("/")
            try:
                rid_text, action = rest.split("/", 1)
                rid = int(rid_text)
                cr = self.wf.get(rid)
                if not cr or cr.get("mode") != "automation":
                    self._api_json({"error": "automation_request_not_found"}, 404)
                    return True
                auto = self.wf._automation_request(cr, require_fresh=False)
                required = _automation_required_scope(auto["intent"]["kind"])
                if "automation:write" not in token["scopes"] or required not in token["scopes"]:
                    self._api_json(
                        {"error": "insufficient_scope", "required": f"automation:write+{required}"}, 403
                    )
                    return True
                if action == "approve":
                    if token.get("role") not in {"approver", "admin"}:
                        raise PermissionError("approval requires approver")
                    self.wf.approve(rid, actor)
                    item = self.wf.get(rid)
                elif action == "reject":
                    if token.get("role") not in {"approver", "admin"}:
                        raise PermissionError("rejection requires approver")
                    self.wf.reject(rid, actor, (form.get("note") or [""])[0])
                    item = self.wf.get(rid)
                elif action == "execute":
                    if token.get("role") not in {"approver", "admin"}:
                        raise PermissionError("execution requires approver")
                    item = self.wf.execute(rid, actor)
                elif action == "cancel":
                    if token.get("role") not in {"operator", "approver", "admin"}:
                        raise PermissionError("cancel requires operator")
                    self.wf.cancel(rid, actor)
                    item = self.wf.get(rid)
                else:
                    return False
            except PermissionError as exc:
                self._api_json({"error": "insufficient_role", "detail": str(exc)}, 403)
                return True
            except Exception as exc:
                self._api_json({"error": "automation_request_operation_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/structured-changes":
            self._api_json({
                "error": "approval_required",
                "detail": "submit an automation request, approve it, then execute it",
                "request_endpoint": "/api/v1/automation-requests",
            }, 409)
            return True
        if path.startswith("/api/v1/structured-changes/") and path.endswith("/recover"):
            if "automation:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json(
                    {"error": "insufficient_scope", "required": "automation:write+admin"}, 403
                )
                return True
            try:
                txid = int(path.split("/")[-2])
                item = self.manager.structured_changes.recover(txid, actor=actor)
            except Exception as exc:
                self._api_json({"error": "structured_recovery_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/structured-changes/recovery/mark-interrupted":
            if "automation:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json(
                    {"error": "insufficient_scope", "required": "automation:write+admin"}, 403
                )
                return True
            try:
                item = self.manager.structured_changes.mark_interrupted_for_recovery(
                    actor=actor,
                    stale_seconds=int((form.get("stale_seconds") or [300])[0]),
                )
            except Exception as exc:
                self._api_json({"error": "structured_recovery_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path.startswith("/api/v1/structured-changes/"):
            self._api_json({
                "error": "approval_required",
                "detail": "structured rollback must execute from an approved automation request",
                "request_endpoint": "/api/v1/automation-requests",
            }, 409)
            return True
        if path == "/api/v1/telemetry/subscriptions":
            if "telemetry:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:write"}, 403)
                return True
            try:
                item = self.manager.telemetry.create(
                    name=(form.get("name") or [""])[0],
                    device=(form.get("device") or [""])[0],
                    path=(form.get("path") or [""])[0],
                    mode=(form.get("mode") or ["ON_CHANGE"])[0],
                    sample_interval_ms=int((form.get("sample_interval_ms") or [10_000])[0]),
                    heartbeat_interval_ms=int((form.get("heartbeat_interval_ms") or [0])[0]),
                    window_seconds=int((form.get("window_seconds") or [30])[0]),
                    collection_interval_seconds=int(
                        (form.get("collection_interval_seconds") or [60])[0]
                    ),
                    retention_days=int((form.get("retention_days") or [30])[0]),
                    actor=actor,
                )
            except Exception as exc:
                self._api_json({"error": "telemetry_subscription_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path == "/api/v1/telemetry/run-due":
            if "telemetry:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:write"}, 403)
                return True
            try:
                item = self.manager.telemetry.run_due(
                    actor=actor, limit=int((form.get("limit") or [32])[0])
                )
            except Exception as exc:
                self._api_json({"error": "telemetry_scheduler_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path.startswith("/api/v1/telemetry/subscriptions/"):
            if "telemetry:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:write"}, 403)
                return True
            rest = path[len("/api/v1/telemetry/subscriptions/"):].strip("/")
            try:
                sid_text, action = rest.split("/", 1)
                sid = int(sid_text)
                if action == "update":
                    item = self.manager.telemetry.update(
                        sid,
                        name=(form.get("name") or [""])[0],
                        path=(form.get("path") or [""])[0],
                        mode=(form.get("mode") or ["ON_CHANGE"])[0],
                        sample_interval_ms=int((form.get("sample_interval_ms") or [10_000])[0]),
                        heartbeat_interval_ms=int((form.get("heartbeat_interval_ms") or [0])[0]),
                        window_seconds=int((form.get("window_seconds") or [30])[0]),
                        collection_interval_seconds=int(
                            (form.get("collection_interval_seconds") or [60])[0]
                        ),
                        retention_days=int((form.get("retention_days") or [30])[0]),
                        actor=actor,
                    )
                elif action == "capture":
                    item = self.manager.telemetry.capture_once(sid, actor=actor)
                elif action == "stream-window":
                    raw_duration = (form.get("duration_seconds") or [None])[0]
                    duration = int(raw_duration) if raw_duration not in (None, "") else None
                    item = self.manager.telemetry.capture_window(
                        sid, duration_seconds=duration, actor=actor
                    )
                elif action == "enable":
                    item = self.manager.telemetry.set_enabled(sid, True, actor=actor)
                elif action == "disable":
                    item = self.manager.telemetry.set_enabled(sid, False, actor=actor)
                elif action == "delete":
                    item = self.manager.telemetry.delete(sid, actor=actor)
                else:
                    return False
            except Exception as exc:
                self._api_json({"error": "telemetry_operation_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/desired-states":
            if "desired:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "desired:write"}, 403)
                return True
            try:
                item = self.manager.desired_state.create(
                    name=(form.get("name") or [""])[0],
                    target_kind=(form.get("target_kind") or [""])[0],
                    target_value=(form.get("target_value") or [""])[0],
                    document=_form_json("document", {}),
                    actor=actor,
                    description=(form.get("description") or [""])[0],
                )
            except Exception as exc:
                self._api_json({"error": "desired_state_create_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path.startswith("/api/v1/desired-states/"):
            if "desired:write" not in token["scopes"]:
                self._api_json({"error": "insufficient_scope", "required": "desired:write"}, 403)
                return True
            rest = path[len("/api/v1/desired-states/"):].strip("/")
            try:
                sid_text, action = rest.split("/", 1)
                sid = int(sid_text)
                if action == "update":
                    if token.get("role") not in {"operator", "approver", "admin"}:
                        raise PermissionError("update requires operator")
                    item = self.manager.desired_state.update(
                        sid,
                        document=_form_json("document") if (form.get("document") or [""])[0] else None,
                        description=(form.get("description") or [None])[0],
                        target_kind=(form.get("target_kind") or [None])[0],
                        target_value=(form.get("target_value") or [None])[0],
                        actor=actor,
                    )
                elif action == "publish":
                    if token.get("role") not in {"approver", "admin"}:
                        raise PermissionError("publish requires approver")
                    item = self.manager.desired_state.publish(sid, actor)
                elif action == "apply":
                    self._api_json({
                        "error": "approval_required",
                        "detail": "desired-state apply must execute from an approved automation request",
                        "request_endpoint": "/api/v1/automation-requests",
                    }, 409)
                    return True
                elif action == "clone":
                    item = self.manager.desired_state.clone_revision(
                        sid, actor=actor, name=(form.get("name") or [None])[0]
                    )
                else:
                    return False
            except PermissionError as exc:
                self._api_json({"error": "insufficient_role", "detail": str(exc)}, 403)
                return True
            except Exception as exc:
                self._api_json({"error": "desired_state_operation_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/campaigns":
            if "campaign:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "campaign:write"}, 403)
                return True
            try:
                rollback = str((form.get("rollback_on_failure") or [""])[0]).lower() in {
                    "1", "true", "yes"
                }
                item = self.manager.campaigns.create(
                    name=(form.get("name") or [""])[0],
                    desired_state_id=int((form.get("desired_state_id") or [0])[0]),
                    wave_size=int((form.get("wave_size") or [1])[0]),
                    max_failures=int((form.get("max_failures") or [0])[0]),
                    canary_size=int((form.get("canary_size") or [0])[0]),
                    rollback_on_failure=rollback,
                    actor=actor,
                )
            except Exception as exc:
                self._api_json({"error": "campaign_create_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path.startswith("/api/v1/campaigns/"):
            if "campaign:write" not in token["scopes"]:
                self._api_json({"error": "insufficient_scope", "required": "campaign:write"}, 403)
                return True
            rest = path[len("/api/v1/campaigns/"):].strip("/")
            try:
                cid_text, action = rest.split("/", 1)
                cid = int(cid_text)
                if action in {"start", "pause", "resume", "abort"}:
                    if token.get("role") not in {"operator", "approver", "admin"}:
                        raise PermissionError("operator role required")
                    item = getattr(self.manager.campaigns, action)(cid, actor)
                elif action == "retry":
                    if token.get("role") not in {"operator", "approver", "admin"}:
                        raise PermissionError("operator role required")
                    wave = (form.get("wave") or [None])[0]
                    item = self.manager.campaigns.retry_failed(
                        cid, actor, wave=int(wave) if wave is not None else None
                    )
                elif action == "wave":
                    self._api_json({
                        "error": "approval_required",
                        "detail": "campaign wave execution must execute from an approved automation request",
                        "request_endpoint": "/api/v1/automation-requests",
                    }, 409)
                    return True
                else:
                    return False
            except PermissionError as exc:
                self._api_json({"error": "insufficient_role", "detail": str(exc)}, 403)
                return True
            except Exception as exc:
                self._api_json({"error": "campaign_operation_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/vendor-model-packs":
            if "model:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json({"error": "insufficient_scope", "required": "model:write+admin"}, 403)
                return True
            try:
                item = self.manager.vendor_models.create(
                    name=(form.get("name") or [""])[0],
                    revision=(form.get("revision") or [""])[0],
                    spec=_form_json("spec", {}),
                    actor=actor,
                )
            except Exception as exc:
                self._api_json({"error": "model_pack_create_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path == "/api/v1/model-bindings":
            if "model:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json({"error": "insufficient_scope", "required": "model:write+admin"}, 403)
                return True
            try:
                item = self.manager.vendor_models.bind(
                    (form.get("device") or [""])[0],
                    (form.get("pack") or [""])[0],
                    actor=actor,
                )
            except Exception as exc:
                self._api_json({"error": "model_binding_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path.startswith("/api/v1/model-bindings/") and path.endswith("/delete"):
            if "model:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json({"error": "insufficient_scope", "required": "model:write+admin"}, 403)
                return True
            try:
                device = urllib.parse.unquote(path[len("/api/v1/model-bindings/"):-len("/delete")].strip("/"))
                if not device or "/" in device:
                    return False
                self.manager.vendor_models.unbind(device, actor=actor)
                item = {"device": device, "binding": None}
            except Exception as exc:
                self._api_json({"error": "model_unbind_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path.startswith("/api/v1/vendor-model-packs/"):
            if "model:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json({"error": "insufficient_scope", "required": "model:write+admin"}, 403)
                return True
            rest = path[len("/api/v1/vendor-model-packs/"):].strip("/")
            try:
                name, action = rest.rsplit("/", 1)
                name = urllib.parse.unquote(name)
                if "/" in name or not name:
                    return False
                if action == "enable":
                    item = self.manager.vendor_models.set_enabled(name, True, actor)
                elif action == "disable":
                    item = self.manager.vendor_models.set_enabled(name, False, actor)
                elif action == "delete":
                    self.manager.vendor_models.delete(name, actor)
                    item = {"deleted": name}
                else:
                    return False
            except Exception as exc:
                self._api_json({"error": "model_pack_operation_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/ha/node-state":
            if "ha:write" not in token["scopes"] or token.get("role") != "admin":
                self._api_json({"error": "insufficient_scope", "required": "ha:write+admin"}, 403)
                return True
            try:
                state = (form.get("state") or [""])[0]
                item = self.manager.ha.set_node_state(
                    state=state,
                    actor=actor,
                    node_id=(form.get("node_id") or [""])[0] or None,
                    reason=(form.get("reason") or [""])[0],
                )
            except Exception as exc:
                self._api_json({"error": "ha_node_state_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/ha/drills":
            if "ha:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "ha:write"}, 403)
                return True
            try:
                item = self.manager.ha.record_drill(
                    kind=(form.get("kind") or [""])[0],
                    actor=actor,
                    state=(form.get("state") or [""])[0],
                    detail=_form_json("detail", {}) or {},
                    verification_ref=(form.get("verification_ref") or [""])[0],
                )
            except Exception as exc:
                self._api_json({"error": "ha_drill_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item, 201)
            return True
        if path.startswith("/api/v1/ha/drills/") and path.endswith("/complete"):
            if "ha:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "ha:write"}, 403)
                return True
            try:
                drill_id = int(path.split("/")[-2])
                item = self.manager.ha.complete_drill(
                    drill_id,
                    actor=actor,
                    state=(form.get("state") or [""])[0],
                    detail=_form_json("detail", {}) or {},
                    verification_ref=(form.get("verification_ref") or [""])[0],
                )
            except Exception as exc:
                self._api_json({"error": "ha_drill_complete_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/protocol-profiles":
            if "protocol:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"protocol:write"},403); return True
            try:
                device=(form.get("device") or [""])[0]
                protocol=(form.get("protocol") or [""])[0]
                row=self.manager.protocol_profiles.set(
                    device, protocol,
                    enabled=str((form.get("enabled") or ["1"])[0]).lower() not in {"0","false","no"},
                    port=int((form.get("port") or [0])[0] or 0),
                    path=(form.get("path") or [""])[0],
                    secret_ref=(form.get("secret_ref") or [""])[0],
                    tls_verify=str((form.get("tls_verify") or ["1"])[0]).lower() not in {"0","false","no"},
                    ca_file=(form.get("ca_file") or [""])[0],
                    allow_cli_fallback=str((form.get("allow_cli_fallback") or [""])[0]).lower() in {"1","true","yes"})
            except (ValueError,TypeError) as exc:
                self._api_json({"error":"protocol_profile_failed","detail":str(exc)},400); return True
            self.manager.db.audit(actor,"protocol_profile_set",device,protocol)
            self._api_json(row,201); return True
        if path.startswith("/api/v1/protocol-collect/"):
            if "protocol:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"protocol:write"},403); return True
            device=urllib.parse.unquote(path[len("/api/v1/protocol-collect/"):].strip("/"))
            if not device or "/" in device:
                return False
            result=self.manager.protocol_collect(device)
            payload={"device":result.device,"ok":result.ok,"changed":result.changed,"message":result.message,"version":result.version}
            self._api_json(payload,200 if result.ok else 502); return True
        if path == "/api/v1/debug/bundles":
            if "debug:create" not in token["scopes"]:
                self._api_json({"error": "insufficient_scope", "required": "debug:create"}, 403); return True
            dbg = DebugBundle(self.manager)
            output = (form.get("output") or [None])[0]
            require_signature = str((form.get("require_signature") or [""])[0]).lower() in {"1", "true", "yes", "required"}
            out = dbg.collect(output, require_signature=require_signature)
            self.manager.db.audit(actor, "debug_bundle_create", str(out), "debug:create")
            self._api_json({"bundle": str(out)}, 201)
            return True
        if path == "/api/v1/traces":
            if "trace:capture" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "trace:capture"}, 403); return True
            try:
                item = self.manager.protocol_traces.start(
                    (form.get("device") or [""])[0],
                    (form.get("protocol") or [""])[0],
                    actor=actor, incident_ref=(form.get("incident") or [None])[0],
                    ttl=int((form.get("ttl") or [900])[0]),
                    max_events=int((form.get("max_events") or [500])[0]),
                    max_bytes=int((form.get("max_bytes") or [1048576])[0]),
                    reason=(form.get("reason") or [""])[0])
            except (ValueError, TypeError) as exc:
                self._api_json({"error": "trace_start_failed", "detail": str(exc)}, 400); return True
            self._api_json(item, 201); return True
        if path.startswith("/api/v1/traces/") and path.endswith("/stop"):
            if "trace:capture" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "trace:capture"}, 403); return True
            ref = path[len("/api/v1/traces/"):-5].rstrip("/")
            try:
                item = self.manager.protocol_traces.stop(ref, actor=actor)
            except ValueError as exc:
                self._api_json({"error": "trace_stop_failed", "detail": str(exc)}, 404); return True
            self._api_json(item); return True
        if path.startswith("/api/v1/operational-alerts/"):
            if "alerts:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"alerts:write"},403); return True
            rest=path[len("/api/v1/operational-alerts/"):].strip("/")
            try:
                aid_s, action = rest.split("/",1); aid=int(aid_s)
                if action=="ack":
                    item=self.manager.alert_lifecycle.acknowledge(aid,actor,(form.get("note") or [""])[0])
                elif action=="resolve":
                    item=self.manager.alert_lifecycle.resolve(aid,actor,(form.get("note") or [""])[0])
                else:
                    return False
            except (ValueError,TypeError) as exc:
                self._api_json({"error":"operational_alert_operation_failed","detail":str(exc)},400); return True
            self._api_json(item); return True
        if path == "/api/v1/maintenance-windows":
            if "alerts:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"alerts:write"},403); return True
            try:
                item=self.manager.alert_lifecycle.add_maintenance((form.get("name") or [""])[0],actor,
                    minutes=int((form.get("minutes") or [60])[0]),device=(form.get("device") or [""])[0],reason=(form.get("reason") or [""])[0])
            except (ValueError,TypeError) as exc:
                self._api_json({"error":"maintenance_window_failed","detail":str(exc)},400); return True
            self._api_json(item,201); return True
        if path.startswith("/api/v1/maintenance-windows/") and path.endswith("/cancel"):
            if "alerts:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"alerts:write"},403); return True
            try:
                item=self.manager.alert_lifecycle.cancel_maintenance(int(path.split("/")[-2]),actor)
            except ValueError as exc:
                self._api_json({"error":"maintenance_window_failed","detail":str(exc)},400); return True
            self._api_json(item); return True
        if path == "/api/v1/report-schedules":
            if "reports:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"reports:write"},403); return True
            try:
                item=self.manager.alert_lifecycle.add_report_schedule((form.get("name") or [""])[0],actor,
                    interval_seconds=int((form.get("interval_seconds") or [86400])[0]),lookback_hours=int((form.get("lookback_hours") or [24])[0]))
            except (ValueError,TypeError) as exc:
                self._api_json({"error":"report_schedule_failed","detail":str(exc)},400); return True
            self._api_json(item,201); return True
        if path.startswith("/api/v1/report-schedules/"):
            if "reports:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"reports:write"},403); return True
            rest=path[len("/api/v1/report-schedules/"):].strip("/")
            try:
                sid_s,action=rest.split("/",1); sid=int(sid_s)
                if action=="run":
                    item=self.manager.alert_lifecycle.run_report(schedule_id=sid,actor=actor)
                elif action in {"enable","disable"}:
                    item=self.manager.alert_lifecycle.set_report_schedule_enabled(sid,action=="enable",actor)
                else:
                    return False
            except (ValueError,TypeError) as exc:
                self._api_json({"error":"report_schedule_operation_failed","detail":str(exc)},400); return True
            self._api_json(item); return True
        if path == "/api/v1/incidents":
            if "incident:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "incident:write"}, 403); return True
            try:
                item = self.manager.incidents.create(
                    (form.get("title") or [""])[0],
                    (form.get("description") or [""])[0],
                    (form.get("severity") or ["MEDIUM"])[0],
                    created_by=actor, tags=(form.get("tags") or form.get("tag") or []))
            except ValueError as exc:
                self._api_json({"error": "invalid_incident", "detail": str(exc)}, 400); return True
            self._api_json(item, 201); return True
        prefix = "/api/v1/incidents/"
        if path.startswith(prefix):
            rest = path[len(prefix):]
            if rest.endswith("/exports"):
                if "incident:export" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                    self._api_json({"error": "insufficient_scope", "required": "incident:export"}, 403); return True
                ref = rest[:-8].rstrip("/")
                try:
                    bundles = form.get("bundles") or form.get("bundle") or []
                    require_signature = str((form.get("require_signature") or [""])[0]).lower() in {"1", "true", "yes", "required"}
                    item = self.manager.case_exports.export_case(
                        ref, actor, bundles, (form.get("reason") or [""])[0],
                        require_signature=require_signature)
                except ValueError as exc:
                    code = 404 if "not found" in str(exc) else 400
                    self._api_json({"error": "case_export_failed", "detail": str(exc)}, code); return True
                self._api_json(item, 201); return True
            if "incident:write" not in token["scopes"] or token.get("role") not in {"operator", "approver", "admin"}:
                self._api_json({"error": "insufficient_scope", "required": "incident:write"}, 403); return True
            try:
                if rest.endswith("/status"):
                    ref = rest[:-7].rstrip("/")
                    item = self.manager.incidents.set_status(
                        ref, (form.get("status") or [""])[0], actor,
                        note=(form.get("note") or [""])[0])
                elif rest.endswith("/bundles"):
                    ref = rest[:-8].rstrip("/")
                    item = self.manager.incidents.link_bundle(
                        ref, (form.get("bundle") or [""])[0], actor)
                elif rest.endswith("/evidence"):
                    ref = rest[:-9].rstrip("/")
                    source_type = (form.get("source_type") or form.get("type") or [""])[0]
                    if source_type == "drift":
                        item = self.manager.incidents.link_drift(
                            ref, (form.get("device") or [""])[0], actor,
                            note=(form.get("note") or [""])[0])
                    else:
                        item = self.manager.incidents.link_evidence(
                            ref, source_type, (form.get("source_id") or [""])[0], actor,
                            note=(form.get("note") or [""])[0])
                elif "/evidence/" in rest and rest.endswith("/unlink"):
                    ref, tail = rest.split("/evidence/", 1)
                    link_id = tail[:-7].rstrip("/")
                    item = self.manager.incidents.unlink_evidence(ref.rstrip("/"), int(link_id), actor)
                else:
                    return False
            except ValueError as exc:
                code = 404 if "not found" in str(exc) else 400
                self._api_json({"error": "incident_operation_failed", "detail": str(exc)}, code); return True
            self._api_json(item, 200); return True
        return False

    def _handle_api_get(self, path, query=None):
        query = query or {}
        token = self._api_token()
        if not token:
            self._api_json({"error": "invalid_or_missing_bearer_token"}, 401); return True
        scopes = token["scopes"]
        if path == "/api/v1/sensor-history":
            if "analytics:read" not in scopes and "inventory:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read or inventory:read"},403); return True
            sensor_key = str((query.get("sensor_key") or [""])[0] or "")
            if not sensor_key:
                self._api_json({"error":"sensor_history_query_failed","detail":"sensor_key is required"},400); return True
            try:
                since_raw = (query.get("since") or [None])[0]
                before_raw = (query.get("before") or [None])[0]
                value = self.manager.sensors.history_for(
                    sensor_key,
                    limit=int((query.get("limit") or [200])[0]),
                    since=(float(since_raw) if since_raw not in (None, "") else None),
                    before=(float(before_raw) if before_raw not in (None, "") else None))
            except Exception as exc:
                self._api_json({"error":"sensor_history_query_failed","detail":str(exc)},400); return True
            self._api_json(value); return True
        if path == "/api/v1/sensor-transitions":
            if "analytics:read" not in scopes and "inventory:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read or inventory:read"},403); return True
            try:
                since_raw = (query.get("since") or [None])[0]
                before_raw = (query.get("before") or [None])[0]
                value = self.manager.sensors.transitions(
                    device=(query.get("device") or [None])[0],
                    sensor_type=(query.get("type") or [None])[0],
                    from_status=(query.get("from_status") or query.get("from") or [None])[0],
                    to_status=(query.get("to_status") or query.get("to") or [None])[0],
                    since=(float(since_raw) if since_raw not in (None, "") else None),
                    before=(float(before_raw) if before_raw not in (None, "") else None),
                    limit=int((query.get("limit") or [200])[0]))
            except Exception as exc:
                self._api_json({"error":"sensor_transition_query_failed","detail":str(exc)},400); return True
            self._api_json(value); return True
        if path == "/api/v1/sensors":
            if "analytics:read" not in scopes and "inventory:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read or inventory:read"},403); return True
            try:
                # MC-1: Sensor snapshots are refreshed by collection workflows; GET remains read-only.
                value = self.manager.sensors.list(
                    device=(query.get("device") or [None])[0],
                    sensor_type=(query.get("type") or [None])[0],
                    status=(query.get("status") or [None])[0],
                    limit=int((query.get("limit") or [200])[0]))
            except Exception as exc:
                self._api_json({"error":"sensor_query_failed","detail":str(exc)},400); return True
            self._api_json(value); return True
        if path == "/api/v1/analytics/l3/routes":
            if "analytics:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read"},403); return True
            try:
                value = self.manager.analytics.l3_routes(
                    device=(query.get("device") or [""])[0],
                    vrf=(query.get("vrf") or [""])[0],
                    destination_prefix=(query.get("destination_prefix") or [""])[0],
                    limit=int((query.get("limit") or [250])[0]))
            except Exception as exc:
                self._api_json({"error":"l3_route_query_failed","detail":str(exc)},400); return True
            self._api_json(value); return True
        if path == "/api/v1/analytics/dashboard":
            if "analytics:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read"},403); return True
            self._api_json(self.manager.analytics.dashboard()); return True
        if path == "/api/v1/analytics/jobs":
            if "analytics:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read"},403); return True
            self._api_json(self.manager.analytics.jobs(int((query.get("limit") or [100])[0]))); return True
        if path == "/api/v1/analytics/insights":
            if "analytics:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read"},403); return True
            try:
                value=self.manager.analytics.list(
                    state=(query.get("state") or [""])[0], insight_type=(query.get("type") or [""])[0],
                    severity=(query.get("severity") or [""])[0], object_id=(query.get("object_id") or [""])[0],
                    search=(query.get("search") or [""])[0], limit=int((query.get("limit") or [200])[0]))
            except Exception as exc:
                self._api_json({"error":"analytics_query_failed","detail":str(exc)},400); return True
            self._api_json(value); return True
        if path.startswith("/api/v1/analytics/insights/"):
            if "analytics:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"analytics:read"},403); return True
            rest=path[len("/api/v1/analytics/insights/"):].strip("/")
            if not rest.isdigit():
                return False
            item=self.manager.analytics.get(int(rest))
            if not item:
                self._api_json({"error":"insight_not_found"},404); return True
            self._api_json(item); return True
        if path == "/api/v1/protocol-profiles":
            if "protocol:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"protocol:read"},403); return True
            value=self.manager.protocol_status()
            self.manager.db.audit("api:"+token["name"],"api_read",path,"protocol:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/protocol-capabilities/"):
            if "protocol:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"protocol:read"},403); return True
            device=urllib.parse.unquote(path[len("/api/v1/protocol-capabilities/"):].strip("/"))
            if not device or "/" in device:
                return False
            try:
                value=self.manager.protocol_capabilities(device)
            except ValueError as exc:
                self._api_json({"error":"protocol_profile_invalid","detail":str(exc)},404); return True
            except Exception as exc:
                self._api_json({"error":"protocol_capabilities_failed","detail":str(exc)},502); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"protocol:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/protocol-state/"):
            if "protocol:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"protocol:read"},403); return True
            device=urllib.parse.unquote(path[len("/api/v1/protocol-state/"):].strip("/"))
            if not device or "/" in device:
                return False
            try:
                value=self.manager.protocol_read_state(device)
            except ValueError as exc:
                self._api_json({"error":"protocol_profile_invalid","detail":str(exc)},404); return True
            except Exception as exc:
                self._api_json({"error":"protocol_state_failed","detail":str(exc)},502); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"protocol:read")
            self._api_json(value); return True
        if path == "/api/v1/automation-requests":
            if "automation:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "automation:read"}, 403)
                return True
            items = [item for item in self.wf.list() if item.get("mode") == "automation"]
            self._api_json(items)
            return True
        if path.startswith("/api/v1/automation-requests/"):
            if "automation:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "automation:read"}, 403)
                return True
            rest = path[len("/api/v1/automation-requests/"):].strip("/")
            if not rest.isdigit():
                return False
            item = self.wf.preview(int(rest))
            if not item or item["request"].get("mode") != "automation":
                self._api_json({"error": "automation_request_not_found"}, 404)
                return True
            self._api_json(item)
            return True
        if path == "/api/v1/automation/status":
            if "automation:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "automation:read"}, 403)
                return True
            self._api_json(self.manager.automation_status())
            return True
        if path == "/api/v1/model-bindings":
            if "model:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "model:read"}, 403)
                return True
            self._api_json(self.manager.vendor_models.list_bindings())
            return True
        if path.startswith("/api/v1/model-bindings/"):
            if "model:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "model:read"}, 403)
                return True
            device = urllib.parse.unquote(path[len("/api/v1/model-bindings/"):].strip("/"))
            if not device or "/" in device:
                return False
            try:
                value = self.manager.vendor_models.binding_detail(device)
            except Exception as exc:
                self._api_json({"error": "model_binding_read_failed", "detail": str(exc)}, 404)
                return True
            self._api_json(value)
            return True
        if path.startswith("/api/v1/vendor-model-resources/"):
            if "model:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "model:read"}, 403)
                return True
            device = urllib.parse.unquote(path[len("/api/v1/vendor-model-resources/"):].strip("/"))
            if not device or "/" in device:
                return False
            protocol = (query.get("protocol") or [None])[0]
            try:
                value = self.manager.vendor_models.resources(device, protocol=protocol)
            except Exception as exc:
                self._api_json({"error": "model_resources_read_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/vendor-model-packs":
            if "model:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "model:read"}, 403)
                return True
            self._api_json(self.manager.vendor_models.list())
            return True
        if path.startswith("/api/v1/vendor-model-packs/"):
            if "model:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "model:read"}, 403)
                return True
            name = urllib.parse.unquote(path[len("/api/v1/vendor-model-packs/"):].strip("/"))
            if not name or "/" in name:
                return False
            value = self.manager.vendor_models.get(name)
            if value is None:
                self._api_json({"error": "model_pack_not_found"}, 404)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/structured-changes":
            if "automation:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "automation:read"}, 403)
                return True
            self._api_json(self.manager.structured_changes.list())
            return True
        if path == "/api/v1/structured-changes/interrupted":
            if "automation:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "automation:read"}, 403)
                return True
            self._api_json(self.manager.structured_changes.interrupted())
            return True
        if path.startswith("/api/v1/structured-changes/"):
            if "automation:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "automation:read"}, 403)
                return True
            rest = path[len("/api/v1/structured-changes/"):].strip("/")
            if not rest.isdigit():
                return False
            value = self.manager.structured_changes.get(int(rest))
            if value is None:
                self._api_json({"error": "structured_change_not_found"}, 404)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/telemetry/subscriptions":
            if "telemetry:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:read"}, 403)
                return True
            self._api_json(self.manager.telemetry.list())
            return True
        if path.startswith("/api/v1/telemetry/subscriptions/") and path.endswith("/samples"):
            if "telemetry:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:read"}, 403)
                return True
            try:
                sid = int(path.split("/")[-2])
                value = self.manager.telemetry.samples(sid, 500)
            except Exception as exc:
                self._api_json({"error": "telemetry_read_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(value)
            return True
        if path.startswith("/api/v1/telemetry/subscriptions/") and path.endswith("/points"):
            if "telemetry:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:read"}, 403)
                return True
            try:
                sid = int(path.split("/")[-2])
                value_path = (query.get("value_path") or [None])[0]
                since_ts = float((query.get("since_ts") or [0])[0] or 0)
                limit = int((query.get("limit") or [2000])[0] or 2000)
                value = self.manager.telemetry.points(
                    sid, value_path=value_path, since_ts=since_ts, limit=limit
                )
            except Exception as exc:
                self._api_json({"error": "telemetry_read_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(value)
            return True
        if path.startswith("/api/v1/telemetry/subscriptions/") and path.endswith("/summary"):
            if "telemetry:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "telemetry:read"}, 403)
                return True
            try:
                sid = int(path.split("/")[-2])
                value_path = (query.get("value_path") or [""])[0]
                since_ts = float((query.get("since_ts") or [0])[0] or 0)
                limit = int((query.get("limit") or [20000])[0] or 20000)
                value = self.manager.telemetry.summary(
                    sid, value_path=value_path, since_ts=since_ts, limit=limit
                )
            except Exception as exc:
                self._api_json({"error": "telemetry_summary_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/desired-states":
            if "desired:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "desired:read"}, 403)
                return True
            self._api_json(self.manager.desired_state.list())
            return True
        if path == "/api/v1/desired-state-runs":
            if "desired:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "desired:read"}, 403)
                return True
            self._api_json(self.manager.desired_state.runs())
            return True
        if path.startswith("/api/v1/desired-states/"):
            if "desired:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "desired:read"}, 403)
                return True
            rest = path[len("/api/v1/desired-states/"):].strip("/")
            try:
                if rest.endswith("/plan"):
                    value = self.manager.desired_state.plan(int(rest[:-5].rstrip("/")))
                elif rest.endswith("/evaluate"):
                    value = self.manager.desired_state.evaluate(int(rest[:-9].rstrip("/")))
                elif rest.endswith("/runs"):
                    value = self.manager.desired_state.runs(int(rest[:-5].rstrip("/")))
                elif rest.isdigit():
                    value = self.manager.desired_state.get(int(rest))
                else:
                    return False
            except Exception as exc:
                self._api_json({"error": "desired_state_read_failed", "detail": str(exc)}, 400)
                return True
            if value is None:
                self._api_json({"error": "desired_state_not_found"}, 404)
                return True
            self._api_json(value)
            return True
        if path.startswith("/api/v1/desired-state-runs/"):
            if "desired:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "desired:read"}, 403)
                return True
            rest = path[len("/api/v1/desired-state-runs/"):].strip("/")
            if not rest.isdigit():
                return False
            value = self.manager.desired_state.get_run(int(rest))
            if value is None:
                self._api_json({"error": "desired_state_run_not_found"}, 404)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/campaigns":
            if "campaign:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "campaign:read"}, 403)
                return True
            self._api_json(self.manager.campaigns.list())
            return True
        if path.startswith("/api/v1/campaigns/"):
            if "campaign:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "campaign:read"}, 403)
                return True
            rest = path[len("/api/v1/campaigns/"):].strip("/")
            if not rest.isdigit():
                return False
            value = self.manager.campaigns.get(int(rest))
            if value is None:
                self._api_json({"error": "campaign_not_found"}, 404)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/ha/nodes":
            if "ha:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "ha:read"}, 403)
                return True
            try:
                stale_seconds = int((query.get("stale_seconds") or [86_400])[0] or 86_400)
                value = self.manager.ha.nodes(stale_seconds)
            except Exception as exc:
                self._api_json({"error": "ha_nodes_failed", "detail": str(exc)}, 400)
                return True
            self._api_json(value)
            return True
        if path == "/api/v1/ha/readiness":
            if "ha:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "ha:read"}, 403)
                return True
            self._api_json(self.manager.ha.readiness())
            return True
        if path == "/api/v1/ha/drills":
            if "ha:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "ha:read"}, 403)
                return True
            self._api_json(self.manager.ha.drills())
            return True
        if path == "/api/v1/topology/graph":
            if "topology:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "topology:read"}, 403); return True
            value = self.manager.topology_graph()
            self.manager.db.audit("api:" + token["name"], "api_read", path, "topology:read")
            self._api_json(value); return True
        if path == "/api/v1/topology/identities":
            if "topology:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "topology:read"}, 403); return True
            value = self.manager.topology_identities()
            self.manager.db.audit("api:" + token["name"], "api_read", path, "topology:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/topology/impact/"):
            if "topology:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "topology:read"}, 403); return True
            root = urllib.parse.unquote(path[len("/api/v1/topology/impact/"):].strip("/"))
            if not root or "/" in root:
                return False
            try:
                value = self.manager.downstream_impact(root)
            except ValueError as exc:
                self._api_json({"error": "topology_root_not_found", "detail": str(exc)}, 404); return True
            self.manager.db.audit("api:" + token["name"], "api_read", path, "topology:read")
            self._api_json(value); return True
        if path == "/api/v1/traces":
            if "trace:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "trace:read"}, 403); return True
            value = self.manager.protocol_traces.list(limit=200)
            self.manager.db.audit("api:" + token["name"], "api_read", path, "trace:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/traces/"):
            if "trace:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "trace:read"}, 403); return True
            rest = path[len("/api/v1/traces/"):].strip("/")
            try:
                if rest.endswith("/events"):
                    ref = rest[:-7].rstrip("/")
                    value = self.manager.protocol_traces.events(ref, 1000)
                elif rest and "/" not in rest:
                    value = self.manager.protocol_traces.get(rest)
                    if not value:
                        self._api_json({"error": "trace_not_found"}, 404); return True
                else:
                    return False
            except ValueError as exc:
                self._api_json({"error": "trace_not_found", "detail": str(exc)}, 404); return True
            self.manager.db.audit("api:" + token["name"], "api_read", path, "trace:read")
            self._api_json(value); return True
        if path == "/api/v1/incidents":
            if "incident:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "incident:read"}, 403); return True
            value = self.manager.incidents.list(limit=200)
            self.manager.db.audit("api:" + token["name"], "api_read", path, "incident:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/incidents/"):
            rest = path[len("/api/v1/incidents/"):].strip("/")
            if "/exports/" in rest:
                if "incident:export" not in scopes or token.get("role") not in {"operator", "approver", "admin"}:
                    self._api_json({"error": "insufficient_scope", "required": "incident:export"}, 403); return True
                ref, export_tail = rest.split("/exports/", 1)
                if export_tail.endswith("/verify"):
                    export_key = export_tail[:-7].rstrip("/")
                    if not ref or not export_key or "/" in export_key:
                        return False
                    try:
                        value = self.manager.case_exports.verify_signature(
                            ref, export_key, actor="api:" + token["name"])
                    except ValueError as exc:
                        self._api_json({"error": "case_export_verification_failed", "detail": str(exc)}, 409); return True
                    self._api_json(value); return True
                export_key = export_tail
                if not ref or not export_key or "/" in export_key:
                    return False
                try:
                    item, target = self.manager.case_exports.record_download(
                        ref, export_key, "api:" + token["name"])
                except ValueError as exc:
                    text = str(exc)
                    if "integrity mismatch" in text:
                        self._api_json({"error": "case_export_integrity_mismatch"}, 409); return True
                    if "signature" in text or "signer" in text:
                        self._api_json({"error": "case_export_signature_verification_failed", "detail": text}, 409); return True
                    self._api_json({"error": "case_export_not_found"}, 404); return True
                self._send_file(target, "application/gzip",
                                [("Content-Disposition", f'attachment; filename="{item["filename"]}"'),
                                 ("Cache-Control", "no-store")])
                return True
            if "incident:read" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "incident:read"}, 403); return True
            try:
                if rest.endswith("/timeline"):
                    ref = rest[:-9].rstrip("/")
                    value = self.manager.incidents.timeline(ref, 500)
                elif rest.endswith("/evidence"):
                    ref = rest[:-9].rstrip("/")
                    item = self.manager.incidents.get(ref)
                    if not item:
                        self._api_json({"error": "incident_not_found"}, 404); return True
                    value = self.manager.incidents.evidence_links(item["id"])
                elif rest.endswith("/exports"):
                    ref = rest[:-8].rstrip("/")
                    value = self.manager.case_exports.list_exports(ref, 200)
                elif "/" not in rest and rest:
                    value = self.manager.incidents.get(rest)
                    if not value:
                        self._api_json({"error": "incident_not_found"}, 404); return True
                else:
                    return False
            except ValueError as exc:
                self._api_json({"error": "incident_not_found", "detail": str(exc)}, 404); return True
            self.manager.db.audit("api:" + token["name"], "api_read", path, "incident:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/debug/bundles/"):
            tail = path[len("/api/v1/debug/bundles/"):]
            if tail.endswith("/verify"):
                if "debug:read" not in scopes:
                    self._api_json({"error": "insufficient_scope", "required": "debug:read"}, 403); return True
                name = tail[:-7].rstrip("/")
                if not name or "/" in name:
                    return False
                try:
                    value = DebugBundle(self.manager).verify_bundle(name)
                except ValueError as exc:
                    self._api_json({"error": "debug_bundle_verification_failed", "detail": str(exc)}, 409); return True
                self.manager.db.audit("api:" + token["name"], "debug_bundle_verify", name, "debug:read")
                self._api_json(value); return True
            if "debug:download" not in scopes:
                self._api_json({"error": "insufficient_scope", "required": "debug:download"}, 403); return True
            name = Path(tail).name
            target = DebugBundle(self.manager).get_bundle(name)
            if target is None:
                self._api_json({"error": "bundle_not_found"}, 404); return True
            self.manager.db.audit("api:" + token["name"], "debug_bundle_download", name, "debug:download")
            self._send_file(target, "application/gzip",
                            [("Content-Disposition", f"attachment; filename={name}")])
            return True
        if path == "/api/v1/events":
            if "events:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"events:read"},403); return True
            try:
                include_raw = str((query.get("include_suppressed") or ["true"])[0]).strip().lower()
                include_suppressed = include_raw not in {"0","false","no"}
                value = {
                    "events": self.manager.events.list(
                        limit=int((query.get("limit") or [500])[0]),
                        device=(query.get("device") or [None])[0],
                        include_suppressed=include_suppressed,
                        domain=(query.get("domain") or [None])[0],
                        source_type=(query.get("source_type") or query.get("source") or [None])[0],
                        entity_type=(query.get("entity_type") or [None])[0],
                        status=(query.get("status") or [None])[0]),
                    "suppressions": self.manager.events.suppressions(True),
                }
            except Exception as exc:
                self._api_json({"error":"event_query_failed","detail":str(exc)},400); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"events:read")
            self._api_json(value); return True
        if path.startswith("/api/v1/events/"):
            if "events:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"events:read"},403); return True
            tail = path[len("/api/v1/events/"):].strip("/")
            if not tail.isdigit():
                return False
            event = self.manager.events.get(int(tail))
            if not event:
                self._api_json({"error":"event_not_found"},404); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"events:read")
            self._api_json({"event":event,"related_sensor":self.manager.events.related_sensor(event)}); return True
        if path == "/api/v1/operational-alerts":
            if "alerts:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"alerts:read"},403); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"alerts:read")
            self._api_json({"alerts":self.manager.alert_lifecycle.list(limit=500),"maintenance":self.manager.alert_lifecycle.maintenance(active_only=True),"deliveries":self.manager.alert_lifecycle.notifications(100)}); return True
        if path == "/api/v1/maintenance-windows":
            if "alerts:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"alerts:read"},403); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"alerts:read")
            self._api_json(self.manager.alert_lifecycle.maintenance(False)); return True
        if path == "/api/v1/operational-reports":
            if "reports:read" not in scopes:
                self._api_json({"error":"insufficient_scope","required":"reports:read"},403); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"reports:read")
            self._api_json({"schedules":self.manager.alert_lifecycle.report_schedules(),"runs":self.manager.alert_lifecycle.report_runs(100)}); return True
        routes = {
            "/api/v1/inventory": ("inventory:read", lambda: self.manager.inv.all()),
            "/api/v1/topology": ("topology:read", lambda: self.manager.db.get_neighbors()),
            "/api/v1/endpoints": ("endpoint:read", lambda: {"summary": self.manager.endpoint_summary(), "endpoints": self.manager.endpoint_inventory()}),
            "/api/v1/drift": ("drift:read", lambda: [dict(device=d["name"], **self.manager.store.drift(d["name"])) for d in self.manager.inv.all()]),
            "/api/v1/compliance/latest": ("compliance:read", lambda: self.manager.db.conn.execute("SELECT * FROM compliance_runs ORDER BY id DESC LIMIT 1").fetchone()),
            "/api/v1/audit": ("audit:read", lambda: self.manager.db.recent_audit(200)),
            "/api/v1/digest/latest": ("compliance:read", lambda: self.manager.db.latest_digest()),
            "/api/v1/debug/bundles": ("debug:read", lambda: DebugBundle(self.manager).list_bundles()),
            "/api/v1/debug/signing": ("debug:read", lambda: signing_status(self.manager.settings)),
        }
        item = routes.get(path)
        if not item:
            return False
        scope, fn = item
        if scope not in scopes:
            self._api_json({"error": "insufficient_scope", "required": scope}, 403); return True
        value = fn()
        if hasattr(value, "keys") and not isinstance(value, dict):
            value = dict(value)
        self.manager.db.audit("api:" + token["name"], "api_read", path, scope)
        self._api_json(value if value is not None else {}); return True

