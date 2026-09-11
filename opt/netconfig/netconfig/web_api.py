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
            if not device or "/" in device: return False
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
                if action=="ack": item=self.manager.alert_lifecycle.acknowledge(aid,actor,(form.get("note") or [""])[0])
                elif action=="resolve": item=self.manager.alert_lifecycle.resolve(aid,actor,(form.get("note") or [""])[0])
                else: return False
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
            try:item=self.manager.alert_lifecycle.cancel_maintenance(int(path.split("/")[-2]),actor)
            except ValueError as exc:self._api_json({"error":"maintenance_window_failed","detail":str(exc)},400); return True
            self._api_json(item); return True
        if path == "/api/v1/report-schedules":
            if "reports:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"reports:write"},403); return True
            try:
                item=self.manager.alert_lifecycle.add_report_schedule((form.get("name") or [""])[0],actor,
                    interval_seconds=int((form.get("interval_seconds") or [86400])[0]),lookback_hours=int((form.get("lookback_hours") or [24])[0]))
            except (ValueError,TypeError) as exc:self._api_json({"error":"report_schedule_failed","detail":str(exc)},400); return True
            self._api_json(item,201); return True
        if path.startswith("/api/v1/report-schedules/"):
            if "reports:write" not in token["scopes"] or token.get("role") not in {"operator","approver","admin"}:
                self._api_json({"error":"insufficient_scope","required":"reports:write"},403); return True
            rest=path[len("/api/v1/report-schedules/"):].strip("/")
            try:
                sid_s,action=rest.split("/",1); sid=int(sid_s)
                if action=="run": item=self.manager.alert_lifecycle.run_report(schedule_id=sid,actor=actor)
                elif action in {"enable","disable"}: item=self.manager.alert_lifecycle.set_report_schedule_enabled(sid,action=="enable",actor)
                else:return False
            except (ValueError,TypeError) as exc:self._api_json({"error":"report_schedule_operation_failed","detail":str(exc)},400); return True
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

    def _handle_api_get(self, path):
        token = self._api_token()
        if not token:
            self._api_json({"error": "invalid_or_missing_bearer_token"}, 401); return True
        scopes = token["scopes"]
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
            if not device or "/" in device: return False
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
            if not device or "/" in device: return False
            try:
                value=self.manager.protocol_read_state(device)
            except ValueError as exc:
                self._api_json({"error":"protocol_profile_invalid","detail":str(exc)},404); return True
            except Exception as exc:
                self._api_json({"error":"protocol_state_failed","detail":str(exc)},502); return True
            self.manager.db.audit("api:"+token["name"],"api_read",path,"protocol:read")
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
            "/api/v1/events": ("events:read", lambda: {"events": self.manager.events.list(500), "suppressions": self.manager.events.suppressions(True)}),
            "/api/v1/drift": ("drift:read", lambda: [dict(device=d["name"], **self.manager.store.drift(d["name"])) for d in self.manager.inv.all()]),
            "/api/v1/compliance/latest": ("compliance:read", lambda: self.manager.db.conn.execute("SELECT * FROM compliance_runs ORDER BY id DESC LIMIT 1").fetchone()),
            "/api/v1/audit": ("audit:read", lambda: self.manager.db.recent_audit(200)),
            "/api/v1/digest/latest": ("compliance:read", lambda: self.manager.db.latest_digest()),
            "/api/v1/debug/bundles": ("debug:read", lambda: DebugBundle(self.manager).list_bundles()),
            "/api/v1/debug/signing": ("debug:read", lambda: signing_status(self.manager.settings)),
        }
        item = routes.get(path)
        if not item: return False
        scope, fn = item
        if scope not in scopes:
            self._api_json({"error": "insufficient_scope", "required": scope}, 403); return True
        value = fn()
        if hasattr(value, "keys") and not isinstance(value, dict): value = dict(value)
        self.manager.db.audit("api:" + token["name"], "api_read", path, scope)
        self._api_json(value if value is not None else {}); return True

