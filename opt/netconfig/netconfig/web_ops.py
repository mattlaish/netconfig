"""UI-1 unified automation and operations console.

This mixin is intentionally presentation/orchestration only. It never performs
network writes directly. Structured, desired-state and campaign network changes
are submitted through the existing durable change-request workflow and only run
after the normal approval/snapshot revalidation path.
"""
from __future__ import annotations

import html
import json
import time
import urllib.parse


_TABS = (
    ("structured", "Structured Changes"),
    ("telemetry", "Telemetry"),
    ("models", "Model Packs"),
    ("desired", "Desired State"),
    ("intents", "Intent Automation"),
    ("campaigns", "Campaigns"),
    ("intelligence", "Network Intelligence"),
    ("ha", "HA / DR"),
)
_OPERATOR_ROLES = {"operator", "approver", "admin"}
_APPROVER_ROLES = {"approver", "admin"}
_ADMIN_ROLES = {"admin"}


def _e(value):
    return html.escape(str(value if value is not None else ""))


def _pretty(value):
    return html.escape(json.dumps(value, indent=2, sort_keys=True, default=str))


def _status(value):
    value = str(value or "UNKNOWN")
    good = {"SUCCEEDED", "PASSED", "ACTIVE", "PUBLISHED", "IDLE", "COMPLETED"}
    bad = {"FAILED", "RECOVERY_REQUIRED", "ERROR", "ABORTED", "ROLLBACK_FAILED"}
    cls = "b-ok" if value.upper() in good else ("b-bad" if value.upper() in bad else "b-chg")
    return f'<span class="badge {cls}">{_e(value)}</span>'


def _value(form, key, default=""):
    return (form.get(key) or [default])[0]


def _json_input(raw, *, default=None, object_only=False):
    raw = str(raw or "").strip()
    if not raw:
        return {} if object_only else default
    value = json.loads(raw)
    if object_only and not isinstance(value, dict):
        raise ValueError("JSON value must be an object")
    return value


def _sparkline(values, width=360, height=80):
    nums = [float(v) for v in values if v is not None]
    if len(nums) < 2:
        return '<span class="muted">not enough numeric samples</span>'
    lo, hi = min(nums), max(nums)
    span = hi - lo or 1.0
    points = []
    for i, value in enumerate(nums):
        x = (i / (len(nums) - 1)) * (width - 4) + 2
        y = height - 2 - ((value - lo) / span) * (height - 4)
        points.append(f"{x:.1f},{y:.1f}")
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="telemetry trend" '
        f'width="100%" height="{height}"><polyline fill="none" stroke="currentColor" '
        f'stroke-width="2" points="{" ".join(points)}"></polyline></svg>'
    )


class WebOpsMixin:
    """Web-console UI for PH-4/NI-5/VM-1/NA-1/NA-2/HA-1."""

    def _dispatch_ops_post(self, path, form, sess):
        handlers = {
            "/ops-structured-submit": self._do_ops_structured_submit,
            "/ops-structured-rollback": self._do_ops_structured_rollback,
            "/ops-structured-mark": self._do_ops_structured_mark,
            "/ops-structured-recover": self._do_ops_structured_recover,
            "/ops-telemetry-create": self._do_ops_telemetry_create,
            "/ops-telemetry-update": self._do_ops_telemetry_update,
            "/ops-telemetry-action": self._do_ops_telemetry_action,
            "/ops-telemetry-run-due": self._do_ops_telemetry_run_due,
            "/ops-telemetry-prune": self._do_ops_telemetry_prune,
            "/ops-model-create": self._do_ops_model_create,
            "/ops-model-bind": self._do_ops_model_bind,
            "/ops-model-unbind": self._do_ops_model_unbind,
            "/ops-model-action": self._do_ops_model_action,
            "/ops-desired-create": self._do_ops_desired_create,
            "/ops-desired-update": self._do_ops_desired_update,
            "/ops-desired-publish": self._do_ops_desired_publish,
            "/ops-desired-clone": self._do_ops_desired_clone,
            "/ops-desired-apply-request": self._do_ops_desired_apply_request,
            "/ops-campaign-create": self._do_ops_campaign_create,
            "/ops-campaign-action": self._do_ops_campaign_action,
            "/ops-campaign-wave-request": self._do_ops_campaign_wave_request,
            "/ops-analytics-refresh": self._do_ops_analytics_refresh,
            "/ops-analytics-impact": self._do_ops_analytics_impact,
            "/ops-l3-route-observe": self._do_ops_l3_route_observe,
            "/ops-l3-path": self._do_ops_l3_path,
            "/ops-l3-dependencies": self._do_ops_l3_dependencies,
            "/ops-insight-state": self._do_ops_insight_state,
            "/ops-analytics-expire": self._do_ops_analytics_expire,
            "/ops-ha-node": self._do_ops_ha_node,
            "/ops-ha-drill-create": self._do_ops_ha_drill_create,
            "/ops-ha-drill-complete": self._do_ops_ha_drill_complete,
        }
        handler = handlers.get(path)
        if handler is None:
            return False
        handler(form, sess)
        return True

    def _ops_redirect(self, tab, notice=""):
        loc = "/operations?tab=" + urllib.parse.quote(str(tab))
        if notice:
            loc += "&notice=" + urllib.parse.quote(str(notice)[:500])
        return self._redirect(loc)

    def _ops_require(self, sess, roles):
        if sess.get("role") not in roles:
            self._send("forbidden", 403, "text/plain")
            return False
        return True

    def _ops_tabs(self, active):
        out = ['<div class="panel"><div class="row">']
        for key, label in _TABS:
            cls = "btn" if key == active else "btn ghost"
            out.append(f'<a class="{cls}" href="/operations?tab={key}">{_e(label)}</a>')
        out.append("</div></div>")
        return "".join(out)

    def _operations_page(self, q, sess):
        active = str((q.get("tab") or ["structured"])[0] or "structured")
        if active not in {item[0] for item in _TABS}:
            active = "structured"
        notice = str((q.get("notice") or [""])[0] or "")
        renderer = {
            "structured": self._ops_structured,
            "telemetry": self._ops_telemetry,
            "models": self._ops_models,
            "desired": self._ops_desired,
            "campaigns": self._ops_campaigns,
            "intelligence": self._ops_intelligence,
            "ha": self._ops_ha,
        }[active]
        body = self._ops_tabs(active) + renderer(q, sess)
        self._send(self._page("Operations", body, sess, flash=notice or None))

    # ---- PH-4 structured changes ---------------------------------------
    def _ops_structured(self, q, sess):
        device_filter = str((q.get("device") or [""])[0] or "")
        txs = self.manager.structured_changes.list(limit=100, device=device_filter or None)
        rows = []
        for tx in txs:
            rows.append(
                '<tr>'
                f'<td><a href="/operations?tab=structured&tx={int(tx["id"])}">TX#{int(tx["id"])}</a></td>'
                f'<td>{_e(tx.get("device"))}</td><td>{_e(tx.get("protocol"))}</td>'
                f'<td>{_e(tx.get("resource"))}</td><td>{_status(tx.get("state"))}</td>'
                f'<td>{"yes" if tx.get("changed") else "no"}</td><td>{_e(tx.get("approval_ref"))}</td>'
                '</tr>'
            )
        device_opts = ''.join(
            f'<option value="{_e(d["name"])}">{_e(d["name"])}</option>'
            for d in self.manager.inv.all()
        )
        create = ""
        if sess["role"] in _OPERATOR_ROLES:
            create = (
                '<div class="panel"><h2>Request structured change</h2>'
                '<p class="muted">This only creates a durable change request. No device write occurs before approval and execution.</p>'
                f'<form method="post" action="/ops-structured-submit">{self._csrf_field()}'
                '<div class="row"><div><label>Device</label><select name="device">'
                f'{device_opts}</select></div><div><label>Allow-listed resource</label><input name="resource" required></div>'
                '<div><label>Title</label><input name="title" placeholder="Structured configuration change"></div></div>'
                '<label>Selectors JSON</label><textarea name="selectors" placeholder="{&quot;interface&quot;:&quot;GigabitEthernet1&quot;}">{}</textarea>'
                '<label>Typed value JSON (JSON string/number/bool/object)</label><textarea name="value" required>true</textarea>'
                '<button>Submit for approval</button></form></div>'
            )
        detail = ""
        tx_raw = str((q.get("tx") or [""])[0] or "")
        if tx_raw.isdigit():
            tx = self.manager.structured_changes.get(int(tx_raw))
            if tx:
                rollback = ""
                if sess["role"] in _OPERATOR_ROLES and tx.get("state") == "SUCCEEDED" and tx.get("changed") and tx.get("reversible"):
                    rollback = (
                        f'<form method="post" action="/ops-structured-rollback">{self._csrf_field()}'
                        f'<input type="hidden" name="txid" value="{int(tx["id"])}"><button>Request rollback approval</button></form>'
                    )
                recover = ""
                if sess["role"] == "admin" and tx.get("state") == "RECOVERY_REQUIRED":
                    recover = (
                        f'<form method="post" action="/ops-structured-recover">{self._csrf_field()}'
                        f'<input type="hidden" name="txid" value="{int(tx["id"])}"><button class="danger">Reconcile recovery state</button></form>'
                    )
                detail = (
                    f'<div class="panel"><h2>TX#{int(tx["id"])} · {_e(tx.get("resource"))}</h2>'
                    '<table>'
                    f'<tr><th>State</th><td>{_status(tx.get("state"))}</td></tr>'
                    f'<tr><th>Device / protocol</th><td>{_e(tx.get("device"))} · {_e(tx.get("protocol"))}</td></tr>'
                    f'<tr><th>Actor / approval</th><td>{_e(tx.get("actor"))} · {_e(tx.get("approval_ref"))}</td></tr>'
                    f'<tr><th>Source</th><td>{_e(tx.get("source_kind"))} · {_e(tx.get("source_ref"))}</td></tr>'
                    f'<tr><th>Verification</th><td>{_e(tx.get("verification_state"))}</td></tr>'
                    f'<tr><th>Rollback</th><td>{_e(tx.get("rollback_state"))}</td></tr>'
                    f'<tr><th>Error</th><td>{_e(tx.get("error"))}</td></tr></table>'
                    '<div class="row"><div><h3>Requested typed change</h3><pre>' + _pretty(tx.get("request")) + '</pre></div>'
                    '<div><h3>Pre-read</h3><pre>' + _pretty(tx.get("pre_value")) + '</pre></div>'
                    '<div><h3>Post-read</h3><pre>' + _pretty(tx.get("post_value")) + '</pre></div></div>'
                    f'<div class="row"><div>{rollback}</div><div>{recover}</div></div></div>'
                )
        recovery = ""
        if sess["role"] == "admin":
            interrupted = self.manager.structured_changes.interrupted(300)
            items = ''.join(
                f'<tr><td>TX#{int(item["id"])}</td><td>{_e(item.get("device"))}</td><td>{_e(item.get("state"))}</td></tr>'
                for item in interrupted[:30]
            )
            recovery = (
                '<div class="panel"><h2>Interrupted transaction recovery</h2>'
                '<p class="muted">Marking is an administrative recovery intake. It does not replay a remote write.</p>'
                f'<table><tr><th>TX</th><th>Device</th><th>Current state</th></tr>{items or "<tr><td colspan=3 class=muted>no stale running transactions</td></tr>"}</table>'
                f'<form method="post" action="/ops-structured-mark">{self._csrf_field()}'
                '<label>Stale threshold seconds</label><input name="stale_seconds" value="300"><button>Mark interrupted for recovery</button></form></div>'
            )
        table = (
            '<div class="panel"><h2>Structured transaction ledger</h2>'
            f'<table><tr><th>TX</th><th>Device</th><th>Protocol</th><th>Resource</th><th>State</th><th>Changed</th><th>Approval</th></tr>{"".join(rows) or "<tr><td colspan=7 class=muted>no transactions</td></tr>"}</table></div>'
        )
        return create + detail + table + recovery

    def _do_ops_structured_submit(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            intent = {
                "kind": "structured_change",
                "device": str(_value(form, "device")).strip(),
                "resource": str(_value(form, "resource")).strip(),
                "selectors": _json_input(_value(form, "selectors", "{}"), object_only=True),
                "value": _json_input(_value(form, "value"), default=None),
            }
            rid = self.wf.submit_automation(
                title=str(_value(form, "title") or "Structured configuration change").strip(),
                intent=intent,
                requested_by=sess["username"],
            )
        except Exception as exc:
            return self._ops_redirect("structured", f"Request failed: {exc}")
        return self._redirect(f"/request?id={rid}")

    def _do_ops_structured_rollback(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            txid = int(_value(form, "txid", "0"))
            rid = self.wf.submit_automation(
                title=f"Rollback structured transaction TX#{txid}",
                intent={"kind": "structured_rollback", "transaction_id": txid},
                requested_by=sess["username"],
            )
        except Exception as exc:
            return self._ops_redirect("structured", f"Rollback request failed: {exc}")
        return self._redirect(f"/request?id={rid}")

    def _do_ops_structured_mark(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            result = self.manager.structured_changes.mark_interrupted_for_recovery(
                actor=sess["username"], stale_seconds=int(_value(form, "stale_seconds", "300"))
            )
            return self._ops_redirect("structured", f"Recovery intake updated: {result}")
        except Exception as exc:
            return self._ops_redirect("structured", f"Recovery intake failed: {exc}")

    def _do_ops_structured_recover(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            txid = int(_value(form, "txid", "0"))
            item = self.manager.structured_changes.recover(txid, actor=sess["username"])
            return self._ops_redirect("structured", f"TX#{txid} reconciled as {item.get('state')}")
        except Exception as exc:
            return self._ops_redirect("structured", f"Recovery failed: {exc}")

    # ---- NI-5 telemetry -------------------------------------------------
    def _ops_telemetry(self, q, sess):
        subs = self.manager.telemetry.list()
        rows = []
        for sub in subs:
            rows.append(
                '<tr>'
                f'<td><a href="/operations?tab=telemetry&sub={int(sub["id"])}">{_e(sub.get("name"))}</a></td>'
                f'<td>{_e(sub.get("device"))}</td><td><code>{_e(sub.get("path"))}</code></td>'
                f'<td>{_e(sub.get("mode"))}</td><td>{_status(sub.get("state"))}</td>'
                f'<td>{"yes" if sub.get("enabled") else "no"}</td><td>{_e(int(sub.get("collection_interval_seconds") or 0))}s</td>'
                '</tr>'
            )
        create = ""
        if sess["role"] in _OPERATOR_ROLES:
            device_opts = ''.join(
                f'<option value="{_e(d["name"])}">{_e(d["name"])}</option>' for d in self.manager.inv.all()
            )
            create = (
                '<div class="panel"><h2>Create telemetry subscription</h2>'
                f'<form method="post" action="/ops-telemetry-create">{self._csrf_field()}'
                '<div class="row"><div><label>Name</label><input name="name" required></div>'
                f'<div><label>Device</label><select name="device">{device_opts}</select></div>'
                '<div><label>gNMI path</label><input name="path" value="/interfaces" required></div></div>'
                '<div class="row"><div><label>Mode</label><select name="mode"><option>ON_CHANGE</option><option>SAMPLE</option><option>TARGET_DEFINED</option></select></div>'
                '<div><label>Sample ms</label><input name="sample_interval_ms" value="10000"></div>'
                '<div><label>Heartbeat ms</label><input name="heartbeat_interval_ms" value="0"></div></div>'
                '<div class="row"><div><label>Window seconds</label><input name="window_seconds" value="30"></div>'
                '<div><label>Collection interval seconds</label><input name="collection_interval_seconds" value="60"></div>'
                '<div><label>Retention days</label><input name="retention_days" value="30"></div></div>'
                '<button>Create subscription</button></form></div>'
            )
        detail = ""
        raw = str((q.get("sub") or [""])[0] or "")
        if raw.isdigit():
            sub = self.manager.telemetry.get(int(raw))
            if sub:
                points = self.manager.telemetry.points(int(raw), limit=200)
                value_paths = []
                for point in points:
                    path = point.get("value_path")
                    if path and path not in value_paths:
                        value_paths.append(path)
                chosen = str((q.get("value_path") or [value_paths[0] if value_paths else ""])[0] or "")
                summary = None
                trend = []
                if chosen:
                    try:
                        summary = self.manager.telemetry.summary(int(raw), value_path=chosen)
                        trend = [p.get("numeric_value") for p in reversed(self.manager.telemetry.points(int(raw), value_path=chosen, limit=120)) if p.get("numeric_value") is not None]
                    except Exception:
                        summary = None
                samples = self.manager.telemetry.samples(int(raw), 12)
                actions = ""
                edit = ""
                if sess["role"] in _OPERATOR_ROLES:
                    actions = (
                        f'<div class="row"><form method="post" action="/ops-telemetry-action">{self._csrf_field()}<input type="hidden" name="sid" value="{int(raw)}">'
                        f'<button name="action" value="capture">Capture now</button> <button name="action" value="window">Stream window</button> '
                        f'<button name="action" value="{"disable" if sub.get("enabled") else "enable"}">{"Disable" if sub.get("enabled") else "Enable"}</button> '
                        '<button class="danger" name="action" value="delete">Delete</button></form></div>'
                    )
                    edit = (
                        '<h3>Edit subscription</h3>'
                        f'<form method="post" action="/ops-telemetry-update">{self._csrf_field()}<input type="hidden" name="sid" value="{int(raw)}">'
                        f'<div class="row"><div><label>Name</label><input name="name" value="{_e(sub.get("name"))}"></div>'
                        f'<div><label>Path</label><input name="path" value="{_e(sub.get("path"))}"></div>'
                        f'<div><label>Mode</label><input name="mode" value="{_e(sub.get("mode"))}"></div></div>'
                        f'<div class="row"><div><label>Sample ms</label><input name="sample_interval_ms" value="{int(sub.get("sample_interval_ms") or 10000)}"></div>'
                        f'<div><label>Heartbeat ms</label><input name="heartbeat_interval_ms" value="{int(sub.get("heartbeat_interval_ms") or 0)}"></div>'
                        f'<div><label>Window seconds</label><input name="window_seconds" value="{int(sub.get("window_seconds") or 30)}"></div></div>'
                        f'<div class="row"><div><label>Collection interval seconds</label><input name="collection_interval_seconds" value="{int(sub.get("collection_interval_seconds") or 60)}"></div>'
                        f'<div><label>Retention days</label><input name="retention_days" value="{int(sub.get("retention_days") or 30)}"></div></div>'
                        '<button>Save subscription</button></form>'
                    )
                path_opts = ''.join(
                    f'<option value="{_e(path)}" {"selected" if path == chosen else ""}>{_e(path)}</option>' for path in value_paths
                )
                summary_html = '<p class="muted">no scalar points collected yet</p>'
                if summary:
                    summary_html = (
                        '<table><tr><th>Latest</th><th>Min</th><th>Max</th><th>Avg</th><th>Delta</th><th>Rate/s</th></tr>'
                        f'<tr><td>{_e((summary.get("latest") or {}).get("value_text") or summary.get("last_numeric"))}</td>'
                        f'<td>{_e(summary.get("min"))}</td><td>{_e(summary.get("max"))}</td><td>{_e(summary.get("avg"))}</td>'
                        f'<td>{_e(summary.get("delta"))}</td><td>{_e(summary.get("rate_per_second"))}</td></tr></table>'
                        + _sparkline(trend)
                    )
                sample_rows = ''.join(
                    f'<tr><td>{_e(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(s.get("observed_ts") or 0))))}</td>'
                    f'<td><pre>{_e(str(s.get("payload_json") or "")[:2000])}</pre></td></tr>' for s in samples
                )
                detail = (
                    f'<div class="panel"><h2>{_e(sub.get("name"))} · {_status(sub.get("state"))}</h2>'
                    f'<p><b>{_e(sub.get("device"))}</b> · <code>{_e(sub.get("path"))}</code> · {_e(sub.get("mode"))}</p>{actions}{edit}'
                    '<h3>Time-series summary</h3>'
                    f'<form method="get" action="/operations"><input type="hidden" name="tab" value="telemetry"><input type="hidden" name="sub" value="{int(raw)}">'
                    f'<label>Scalar path</label><select name="value_path">{path_opts}</select><button class="ghost">View</button></form>{summary_html}'
                    f'<h3>Recent bounded samples</h3><table><tr><th>Observed</th><th>Payload</th></tr>{sample_rows or "<tr><td colspan=2 class=muted>no samples</td></tr>"}</table></div>'
                )
        maintenance = ""
        if sess["role"] in _OPERATOR_ROLES:
            maintenance = (
                '<div class="panel"><h2>Telemetry maintenance</h2><div class="row">'
                f'<form method="post" action="/ops-telemetry-run-due">{self._csrf_field()}<label>Scheduler batch limit</label><input name="limit" value="32"><button>Run due subscriptions</button></form>'
                f'<form method="post" action="/ops-telemetry-prune">{self._csrf_field()}<p class="muted">Prune samples using each subscription retention policy.</p><button>Run retention prune</button></form>'
                '</div></div>'
            )
        table = f'<div class="panel"><h2>Subscriptions</h2><table><tr><th>Name</th><th>Device</th><th>Path</th><th>Mode</th><th>State</th><th>Enabled</th><th>Interval</th></tr>{"".join(rows) or "<tr><td colspan=7 class=muted>no subscriptions</td></tr>"}</table></div>'
        return create + detail + table + maintenance

    def _telemetry_kwargs(self, form):
        return {
            "name": str(_value(form, "name")).strip(),
            "path": str(_value(form, "path")).strip(),
            "mode": str(_value(form, "mode", "ON_CHANGE")).strip(),
            "sample_interval_ms": int(_value(form, "sample_interval_ms", "10000")),
            "heartbeat_interval_ms": int(_value(form, "heartbeat_interval_ms", "0")),
            "window_seconds": int(_value(form, "window_seconds", "30")),
            "collection_interval_seconds": int(_value(form, "collection_interval_seconds", "60")),
            "retention_days": int(_value(form, "retention_days", "30")),
        }

    def _do_ops_telemetry_create(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            kwargs = self._telemetry_kwargs(form)
            kwargs["device"] = str(_value(form, "device")).strip()
            self.manager.telemetry.create(actor=sess["username"], **kwargs)
            return self._ops_redirect("telemetry", "Telemetry subscription created")
        except Exception as exc:
            return self._ops_redirect("telemetry", f"Create failed: {exc}")

    def _do_ops_telemetry_update(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            sid = int(_value(form, "sid", "0"))
            self.manager.telemetry.update(sid, actor=sess["username"], **self._telemetry_kwargs(form))
            return self._redirect(f"/operations?tab=telemetry&sub={sid}&notice=Subscription+updated")
        except Exception as exc:
            return self._ops_redirect("telemetry", f"Update failed: {exc}")

    def _do_ops_telemetry_action(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            sid = int(_value(form, "sid", "0")); action = str(_value(form, "action"))
            if action == "capture":
                self.manager.telemetry.capture_once(sid, actor=sess["username"])
            elif action == "window":
                self.manager.telemetry.capture_window(sid, actor=sess["username"])
            elif action == "enable":
                self.manager.telemetry.set_enabled(sid, True, actor=sess["username"])
            elif action == "disable":
                self.manager.telemetry.set_enabled(sid, False, actor=sess["username"])
            elif action == "delete":
                self.manager.telemetry.delete(sid, actor=sess["username"])
            else:
                raise ValueError("unsupported telemetry action")
            return self._ops_redirect("telemetry", f"Telemetry action {action} completed")
        except Exception as exc:
            return self._ops_redirect("telemetry", f"Telemetry action failed: {exc}")

    def _do_ops_telemetry_run_due(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            result = self.manager.telemetry.run_due(actor=sess["username"], limit=int(_value(form, "limit", "32")))
            return self._ops_redirect("telemetry", f"Scheduler result: {result}")
        except Exception as exc:
            return self._ops_redirect("telemetry", f"Scheduler failed: {exc}")

    def _do_ops_telemetry_prune(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            result = self.manager.telemetry.prune_expired()
            self.manager.db.audit(sess["username"], "telemetry_retention_prune", "telemetry", json.dumps(result, sort_keys=True))
            return self._ops_redirect("telemetry", f"Retention prune: {result}")
        except Exception as exc:
            return self._ops_redirect("telemetry", f"Retention prune failed: {exc}")

    # ---- VM-1 model packs ----------------------------------------------
    def _ops_models(self, q, sess):
        packs = self.manager.vendor_models.list()
        pack_rows = ''.join(
            f'<tr><td><a href="/operations?tab=models&pack={urllib.parse.quote(str(p["name"]))}">{_e(p.get("name"))}</a></td>'
            f'<td>{_e(p.get("revision"))}</td><td>{_e(p.get("vendor"))}</td><td>{"yes" if p.get("enabled") else "no"}</td>'
            f'<td><code>{_e(str(p.get("spec_sha256") or "")[:16])}</code></td></tr>' for p in packs
        )
        bindings = self.manager.vendor_models.list_bindings()
        bind_rows = ''.join(
            f'<tr><td><a href="/operations?tab=models&device={urllib.parse.quote(str(b["device"]))}">{_e(b.get("device"))}</a></td><td>{_e(b.get("pack_name"))}</td></tr>'
            for b in bindings
        )
        detail = ""
        pack_name = str((q.get("pack") or [""])[0] or "")
        if pack_name:
            item = self.manager.vendor_models.get(pack_name)
            if item:
                detail = f'<div class="panel"><h2>{_e(pack_name)}</h2><pre>{_pretty(item)}</pre></div>'
        device_name = str((q.get("device") or [""])[0] or "")
        if device_name:
            protocol = str((q.get("protocol") or [""])[0] or "") or None
            try:
                binding = self.manager.vendor_models.binding_detail(device_name)
                resources = self.manager.vendor_models.resources(device_name, protocol=protocol)
                detail += (
                    f'<div class="panel"><h2>{_e(device_name)} effective model</h2><pre>{_pretty(binding)}</pre>'
                    '<form method="get" action="/operations"><input type="hidden" name="tab" value="models">'
                    f'<input type="hidden" name="device" value="{_e(device_name)}"><label>Protocol filter</label><select name="protocol">'
                    '<option value="">all</option><option>netconf</option><option>restconf</option><option>gnmi</option></select><button class="ghost">Filter</button></form>'
                    f'<h3>Allow-listed resources</h3><pre>{_pretty(resources)}</pre></div>'
                )
            except Exception as exc:
                detail += f'<div class="err">{_e(exc)}</div>'
        admin = ""
        if sess["role"] == "admin":
            devices = ''.join(f'<option value="{_e(d["name"])}">{_e(d["name"])}</option>' for d in self.manager.inv.all())
            pack_opts = ''.join(f'<option value="{_e(p["name"])}">{_e(p["name"])}</option>' for p in packs if p.get("enabled"))
            admin = (
                '<div class="panel"><h2>Admin model-pack operations</h2>'
                f'<form method="post" action="/ops-model-create">{self._csrf_field()}<div class="row"><div><label>Name</label><input name="name"></div><div><label>Revision</label><input name="revision" value="1"></div></div>'
                '<label>Pack specification JSON</label><textarea name="spec" required>{"vendor":"example","os_family":"example","resources":{}}</textarea><button>Create validated custom pack</button></form>'
                '<hr><div class="row">'
                f'<form method="post" action="/ops-model-bind">{self._csrf_field()}<label>Device</label><select name="device">{devices}</select><label>Pack</label><select name="pack">{pack_opts}</select><button>Bind</button></form>'
                f'<form method="post" action="/ops-model-unbind">{self._csrf_field()}<label>Device</label><select name="device">{devices}</select><button class="ghost">Remove explicit binding</button></form>'
                '</div><h3>Pack lifecycle</h3>'
                f'<form method="post" action="/ops-model-action">{self._csrf_field()}<label>Pack</label><select name="pack">{pack_opts}</select>'
                '<button name="action" value="enable">Enable</button> <button name="action" value="disable">Disable</button> <button class="danger" name="action" value="delete">Delete custom pack</button></form></div>'
            )
        return (
            detail + admin + '<div class="panel"><h2>Vendor model packs</h2><table><tr><th>Name</th><th>Revision</th><th>Vendor</th><th>Enabled</th><th>SHA</th></tr>'
            f'{pack_rows}</table><h3>Explicit device bindings</h3><table><tr><th>Device</th><th>Pack</th></tr>{bind_rows or "<tr><td colspan=2 class=muted>no explicit bindings; inference is used</td></tr>"}</table></div>'
        )

    def _do_ops_model_create(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            self.manager.vendor_models.create(name=_value(form, "name"), revision=_value(form, "revision"), spec=_json_input(_value(form, "spec"), object_only=True), actor=sess["username"])
            return self._ops_redirect("models", "Model pack created")
        except Exception as exc:
            return self._ops_redirect("models", f"Model pack create failed: {exc}")

    def _do_ops_model_bind(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            self.manager.vendor_models.bind(_value(form, "device"), _value(form, "pack"), actor=sess["username"])
            return self._ops_redirect("models", "Device model binding updated")
        except Exception as exc:
            return self._ops_redirect("models", f"Binding failed: {exc}")

    def _do_ops_model_unbind(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            self.manager.vendor_models.unbind(_value(form, "device"), actor=sess["username"])
            return self._ops_redirect("models", "Explicit device binding removed")
        except Exception as exc:
            return self._ops_redirect("models", f"Unbind failed: {exc}")

    def _do_ops_model_action(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            name = _value(form, "pack"); action = _value(form, "action")
            if action == "enable":
                self.manager.vendor_models.set_enabled(name, True, sess["username"])
            elif action == "disable":
                self.manager.vendor_models.set_enabled(name, False, sess["username"])
            elif action == "delete":
                self.manager.vendor_models.delete(name, sess["username"])
            else:
                raise ValueError("unsupported model-pack action")
            return self._ops_redirect("models", f"Model pack {action} completed")
        except Exception as exc:
            return self._ops_redirect("models", f"Model pack action failed: {exc}")

    # ---- NA-1 desired state --------------------------------------------
    def _ops_desired(self, q, sess):
        items = self.manager.desired_state.list()
        rows = ''.join(
            f'<tr><td><a href="/operations?tab=desired&ds={int(item["id"])}">DS#{int(item["id"])} · {_e(item.get("name"))}</a></td>'
            f'<td>{_e(item.get("revision"))}</td><td>{_e(item.get("target_kind"))}:{_e(item.get("target_value"))}</td><td>{_status(item.get("state"))}</td></tr>'
            for item in items
        )
        create = ""
        if sess["role"] in _OPERATOR_ROLES:
            create = (
                '<div class="panel"><h2>Create desired-state draft</h2>'
                f'<form method="post" action="/ops-desired-create">{self._csrf_field()}<div class="row"><div><label>Name</label><input name="name"></div>'
                '<div><label>Target kind</label><select name="target_kind"><option>device</option><option>group</option><option>tag</option></select></div>'
                '<div><label>Target value</label><input name="target_value"></div></div><label>Description</label><input name="description">'
                '<label>Document JSON</label><textarea name="document" required>{"operations":[{"resource":"interface_description","selectors":{"interface":"GigabitEthernet1"},"value":"managed by NetConfig"}]}</textarea>'
                '<button>Create draft</button></form></div>'
            )
        detail = ""
        raw = str((q.get("ds") or [""])[0] or "")
        if raw.isdigit():
            ds = self.manager.desired_state.get(int(raw))
            if ds:
                try:
                    plan = self.manager.desired_state.plan(int(raw))
                except Exception as exc:
                    plan = {"error": str(exc)}
                try:
                    evaluation = self.manager.desired_state.evaluate(int(raw))
                except Exception as exc:
                    evaluation = {"error": str(exc)}
                runs = self.manager.desired_state.runs(int(raw), 30)
                actions = ""
                if sess["role"] in _OPERATOR_ROLES:
                    if ds.get("state") == "DRAFT":
                        actions += (
                            f'<form method="post" action="/ops-desired-update">{self._csrf_field()}<input type="hidden" name="dsid" value="{int(raw)}">'
                            f'<label>Description</label><input name="description" value="{_e(ds.get("description"))}">'
                            f'<label>Target kind</label><input name="target_kind" value="{_e(ds.get("target_kind"))}"><label>Target value</label><input name="target_value" value="{_e(ds.get("target_value"))}">'
                            f'<label>Document JSON</label><textarea name="document">{_e(json.dumps(ds.get("document") or {}, indent=2, sort_keys=True))}</textarea><button>Save draft</button></form>'
                        )
                    actions += (
                        f'<form method="post" action="/ops-desired-clone">{self._csrf_field()}<input type="hidden" name="dsid" value="{int(raw)}">'
                        '<label>New revision name (optional)</label><input name="name"><button class="ghost">Clone revision</button></form>'
                    )
                    if ds.get("state") == "PUBLISHED":
                        actions += (
                            f'<form method="post" action="/ops-desired-apply-request">{self._csrf_field()}<input type="hidden" name="dsid" value="{int(raw)}">'
                            '<label><input type="checkbox" name="rollback_on_failure" value="1" checked> compensating rollback on failure</label><button>Request apply approval</button></form>'
                        )
                if sess["role"] in _APPROVER_ROLES and ds.get("state") == "DRAFT":
                    actions += f'<form method="post" action="/ops-desired-publish">{self._csrf_field()}<input type="hidden" name="dsid" value="{int(raw)}"><button>Publish revision</button></form>'
                run_rows = ''.join(
                    f'<tr><td><a href="/operations?tab=desired&ds={int(raw)}&run={int(run["id"])}">RUN#{int(run["id"])}</a></td><td>{_status(run.get("state"))}</td><td>{_e(run.get("actor"))}</td><td>{_e(run.get("error"))}</td></tr>'
                    for run in runs
                )
                run_detail = ""
                run_raw = str((q.get("run") or [""])[0] or "")
                if run_raw.isdigit():
                    run = self.manager.desired_state.get_run(int(run_raw))
                    if run and int(run.get("desired_state_id") or 0) == int(raw):
                        run_detail = f'<h3>RUN#{int(run_raw)} evidence</h3><pre>{_pretty(run)}</pre>'
                detail = (
                    f'<div class="panel"><h2>DS#{int(raw)} · {_e(ds.get("name"))} · {_status(ds.get("state"))}</h2>{actions}'
                    '<div class="row"><div><h3>Plan</h3><pre>' + _pretty(plan) + '</pre></div><div><h3>Drift evaluation</h3><pre>' + _pretty(evaluation) + '</pre></div></div>'
                    f'<h3>Run history</h3><table><tr><th>Run</th><th>State</th><th>Actor</th><th>Error</th></tr>{run_rows or "<tr><td colspan=4 class=muted>no runs</td></tr>"}</table>{run_detail}</div>'
                )
        return create + detail + f'<div class="panel"><h2>Desired states</h2><table><tr><th>Name</th><th>Revision</th><th>Target</th><th>State</th></tr>{rows or "<tr><td colspan=4 class=muted>no desired states</td></tr>"}</table></div>'

    def _do_ops_desired_create(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            item = self.manager.desired_state.create(name=_value(form, "name"), target_kind=_value(form, "target_kind"), target_value=_value(form, "target_value"), document=_json_input(_value(form, "document"), object_only=True), actor=sess["username"], description=_value(form, "description"))
            return self._redirect(f'/operations?tab=desired&ds={int(item["id"])}')
        except Exception as exc:
            return self._ops_redirect("desired", f"Create failed: {exc}")

    def _do_ops_desired_update(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            dsid = int(_value(form, "dsid", "0"))
            self.manager.desired_state.update(dsid, document=_json_input(_value(form, "document"), object_only=True), description=_value(form, "description"), target_kind=_value(form, "target_kind"), target_value=_value(form, "target_value"), actor=sess["username"])
            return self._redirect(f"/operations?tab=desired&ds={dsid}&notice=Draft+updated")
        except Exception as exc:
            return self._ops_redirect("desired", f"Update failed: {exc}")

    def _do_ops_desired_publish(self, form, sess):
        if not self._ops_require(sess, _APPROVER_ROLES):
            return
        try:
            dsid = int(_value(form, "dsid", "0")); self.manager.desired_state.publish(dsid, sess["username"])
            return self._redirect(f"/operations?tab=desired&ds={dsid}&notice=Revision+published")
        except Exception as exc:
            return self._ops_redirect("desired", f"Publish failed: {exc}")

    def _do_ops_desired_clone(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            item = self.manager.desired_state.clone_revision(int(_value(form, "dsid", "0")), actor=sess["username"], name=_value(form, "name") or None)
            return self._redirect(f'/operations?tab=desired&ds={int(item["id"])}&notice=Revision+cloned')
        except Exception as exc:
            return self._ops_redirect("desired", f"Clone failed: {exc}")

    def _do_ops_desired_apply_request(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            dsid = int(_value(form, "dsid", "0"))
            rid = self.wf.submit_automation(title=f"Apply desired state DS#{dsid}", intent={"kind": "desired_apply", "desired_state_id": dsid, "rollback_on_failure": bool(_value(form, "rollback_on_failure"))}, requested_by=sess["username"])
            return self._redirect(f"/request?id={rid}")
        except Exception as exc:
            return self._ops_redirect("desired", f"Apply request failed: {exc}")

    # ---- NA-2 campaigns -------------------------------------------------
    def _ops_campaigns(self, q, sess):
        campaigns = self.manager.campaigns.list()
        rows = ''.join(
            f'<tr><td><a href="/operations?tab=campaigns&campaign={int(item["id"])}">CAM#{int(item["id"])} · {_e(item.get("name"))}</a></td><td>DS#{_e(item.get("desired_state_id"))}</td><td>{_status(item.get("state"))}</td><td>{_e(item.get("current_wave"))}</td><td>{_e(item.get("failure_count"))}</td></tr>'
            for item in campaigns
        )
        create = ""
        if sess["role"] in _OPERATOR_ROLES:
            states = [item for item in self.manager.desired_state.list() if item.get("state") == "PUBLISHED"]
            ds_opts = ''.join(f'<option value="{int(item["id"])}">DS#{int(item["id"])} · {_e(item.get("name"))}</option>' for item in states)
            create = (
                '<div class="panel"><h2>Create fleet campaign</h2>'
                f'<form method="post" action="/ops-campaign-create">{self._csrf_field()}<div class="row"><div><label>Name</label><input name="name"></div><div><label>Published desired state</label><select name="desired_state_id">{ds_opts}</select></div></div>'
                '<div class="row"><div><label>Wave size</label><input name="wave_size" value="1"></div><div><label>Canary size</label><input name="canary_size" value="0"></div><div><label>Max failures</label><input name="max_failures" value="0"></div></div>'
                '<label><input type="checkbox" name="rollback_on_failure" value="1" checked> rollback completed targets in a failed wave</label><button>Create campaign</button></form></div>'
            )
        detail = ""
        raw = str((q.get("campaign") or [""])[0] or "")
        if raw.isdigit():
            item = self.manager.campaigns.get(int(raw))
            if item:
                actions = ""
                if sess["role"] in _OPERATOR_ROLES:
                    for action in ("start", "pause", "resume", "retry", "abort"):
                        if action == "retry":
                            actions += f'<form method="post" action="/ops-campaign-action">{self._csrf_field()}<input type="hidden" name="cid" value="{int(raw)}"><input type="hidden" name="action" value="retry"><label>Retry wave (blank=failed targets)</label><input name="wave"><button class="ghost">Retry failed</button></form>'
                        else:
                            actions += f'<form method="post" action="/ops-campaign-action">{self._csrf_field()}<input type="hidden" name="cid" value="{int(raw)}"><button name="action" value="{action}">{action.title()}</button></form>'
                    if item.get("state") == "RUNNING" and any(t.get("state") == "PENDING" for t in item.get("targets", [])):
                        actions += f'<form method="post" action="/ops-campaign-wave-request">{self._csrf_field()}<input type="hidden" name="cid" value="{int(raw)}"><button>Request next wave approval</button></form>'
                target_rows = ''.join(
                    f'<tr><td>{_e(t.get("ordinal"))}</td><td>{_e(t.get("device"))}</td><td>{_e(t.get("wave"))}</td><td>{_status(t.get("state"))}</td><td>{_e(t.get("attempt"))}</td><td>{_e(t.get("transaction_id"))}</td><td>{_e(t.get("desired_run_id"))}</td><td>{_e(t.get("error"))}</td></tr>'
                    for t in item.get("targets", [])
                )
                detail = (
                    f'<div class="panel"><h2>CAM#{int(raw)} · {_e(item.get("name"))} · {_status(item.get("state"))}</h2>{actions}'
                    f'<h3>Frozen plan</h3><pre>{_pretty(item.get("plan"))}</pre>'
                    f'<h3>Target progress</h3><table><tr><th>#</th><th>Device</th><th>Wave</th><th>State</th><th>Attempt</th><th>TX</th><th>RUN</th><th>Error</th></tr>{target_rows}</table></div>'
                )
        return create + detail + f'<div class="panel"><h2>Fleet campaigns</h2><table><tr><th>Campaign</th><th>Desired state</th><th>State</th><th>Wave</th><th>Failures</th></tr>{rows or "<tr><td colspan=5 class=muted>no campaigns</td></tr>"}</table></div>'

    def _do_ops_campaign_create(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            item = self.manager.campaigns.create(name=_value(form, "name"), desired_state_id=int(_value(form, "desired_state_id", "0")), wave_size=int(_value(form, "wave_size", "1")), canary_size=int(_value(form, "canary_size", "0")), max_failures=int(_value(form, "max_failures", "0")), rollback_on_failure=bool(_value(form, "rollback_on_failure")), actor=sess["username"])
            return self._redirect(f'/operations?tab=campaigns&campaign={int(item["id"])}')
        except Exception as exc:
            return self._ops_redirect("campaigns", f"Campaign create failed: {exc}")

    def _do_ops_campaign_action(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            cid = int(_value(form, "cid", "0")); action = str(_value(form, "action"))
            if action in {"start", "pause", "resume", "abort"}:
                getattr(self.manager.campaigns, action)(cid, sess["username"])
            elif action == "retry":
                raw_wave = str(_value(form, "wave", "")).strip(); self.manager.campaigns.retry_failed(cid, sess["username"], wave=int(raw_wave) if raw_wave else None)
            else:
                raise ValueError("unsupported campaign action")
            return self._redirect(f"/operations?tab=campaigns&campaign={cid}&notice=Campaign+updated")
        except Exception as exc:
            return self._ops_redirect("campaigns", f"Campaign action failed: {exc}")

    def _do_ops_campaign_wave_request(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            cid = int(_value(form, "cid", "0"))
            rid = self.wf.submit_automation(title=f"Execute campaign CAM#{cid} next wave", intent={"kind": "campaign_wave", "campaign_id": cid}, requested_by=sess["username"])
            return self._redirect(f"/request?id={rid}")
        except Exception as exc:
            return self._ops_redirect("campaigns", f"Wave approval request failed: {exc}")

    # ---- NI-6 enterprise network intelligence ---------------------------
    def _ops_intelligence(self, q, sess):
        state_filter = str((q.get("state") or [""])[0] or "").upper()
        type_filter = str((q.get("type") or [""])[0] or "").upper()
        object_filter = str((q.get("object_id") or [""])[0] or "")
        search = str((q.get("search") or [""])[0] or "")
        try:
            insights = self.manager.analytics.list(
                state=state_filter, insight_type=type_filter, object_id=object_filter,
                search=search, limit=250)
        except ValueError:
            insights = self.manager.analytics.list(limit=250)
            state_filter = type_filter = object_filter = search = ""
        dashboard = self.manager.analytics.dashboard()
        devices = self.manager.inv.all()
        device_opts = ''.join(
            f'<option value="{_e(d["name"])}">{_e(d["name"])}</option>' for d in devices
        )
        forms = ""
        if sess["role"] in _OPERATOR_ROLES:
            forms = (
                '<div class="row"><div class="panel"><h2>Refresh analytics</h2>'
                '<p class="muted">Generate durable Capacity, Failure Risk and Health insights from current evidence. This does not change network state.</p>'
                f'<form method="post" action="/ops-analytics-refresh">{self._csrf_field()}'
                f'<label>Managed object</label><select name="object_id">{device_opts}</select>'
                '<button>Analyze and persist</button></form></div>'
                '<div class="panel"><h2>Impact simulation</h2>'
                '<p class="muted">Traverses only resolved managed L2 adjacency and correlated endpoint evidence. Simulation only.</p>'
                f'<form method="post" action="/ops-analytics-impact">{self._csrf_field()}'
                f'<label>Managed root</label><select name="object_id">{device_opts}</select>'
                '<label>Max depth (1-16)</label><input name="max_depth" value="5">'
                '<button>Simulate impact</button></form></div></div>'
                '<div class="panel"><h2>Lifecycle housekeeping</h2>'
                f'<form method="post" action="/ops-analytics-expire">{self._csrf_field()}'
                '<label>Expire unseen NEW/ACKNOWLEDGED insights older than seconds</label>'
                '<input name="max_age_seconds" value="604800"><button class="ghost">Expire stale insights</button></form></div>'
            )
        routes = self.manager.analytics.l3_routes(limit=100)
        route_rows = ''.join(
            '<tr>'
            f'<td>{int(r["id"])}</td><td>{_e(r.get("device"))}</td><td>{_e(r.get("vrf"))}</td>'
            f'<td>{_e(r.get("destination_prefix"))}</td><td>{_e(r.get("next_hop"))}</td>'
            f'<td>{_e(r.get("next_device"))}</td><td>{"yes" if r.get("terminal") else "no"}</td></tr>'
            for r in routes
        ) or '<tr><td colspan="7" class="muted">No explicit L3 route observations.</td></tr>'
        l3_panel = (
            '<div class="panel"><h2>NI-7 · L3/VRF path intelligence</h2>'
            '<p class="muted">Explicit route evidence only. No next-hop IP inference, no VRF crossing, no arbitrary ECMP choice, and no network mutation.</p>'
        )
        if sess["role"] in _OPERATOR_ROLES:
            l3_panel += (
                '<div class="row"><div><h3>Record route evidence</h3>'
                f'<form method="post" action="/ops-l3-route-observe">{self._csrf_field()}'
                f'<label>Device</label><select name="device">{device_opts}</select>'
                '<label>VRF</label><input name="vrf" value="default">'
                '<label>Destination prefix</label><input name="destination_prefix" placeholder="10.0.0.0/24">'
                '<label>Protocol</label><input name="protocol" placeholder="static / ospf / bgp">'
                '<label>Next hop</label><input name="next_hop">'
                '<label>Outgoing interface</label><input name="outgoing_interface">'
                f'<label>Explicit managed next device</label><select name="next_device"><option value="">unresolved / none</option>{device_opts}</select>'
                '<label>Metric</label><input name="metric" value="0">'
                '<label><input type="checkbox" name="terminal" value="1"> Explicit terminal route</label>'
                '<label>Evidence reference</label><input name="evidence_ref" placeholder="collector/source reference">'
                '<button>Persist route evidence</button></form></div>'
                '<div><h3>Simulate L3 path</h3>'
                f'<form method="post" action="/ops-l3-path">{self._csrf_field()}'
                f'<label>Source device</label><select name="source_device">{device_opts}</select>'
                '<label>VRF</label><input name="vrf" value="default">'
                '<label>Destination prefix</label><input name="destination_prefix">'
                '<label>Max hops (1-64)</label><input name="max_hops" value="16">'
                '<button>Simulate and persist insight</button></form>'
                '<h3>Route dependency candidates</h3>'
                f'<form method="post" action="/ops-l3-dependencies">{self._csrf_field()}'
                f'<label>Failed / unavailable managed device</label><select name="failed_device">{device_opts}</select>'
                '<button>Analyze dependency candidates</button></form></div></div>'
            )
        l3_panel += (
            '<h3>Recent route evidence</h3><table><tr><th>ID</th><th>Device</th><th>VRF</th><th>Destination</th><th>Next hop</th><th>Next device</th><th>Terminal</th></tr>'
            + route_rows + '</table></div>'
        )
        summary = (
            '<div class="panel"><h2>Operational intelligence health</h2>'
            f'<div class="row"><div><b>{int(dashboard.get("active",0))}</b><br><span class="muted">active insights</span></div>'
            f'<div><b>{int(dashboard.get("states",{}).get("NEW",0))}</b><br><span class="muted">new</span></div>'
            f'<div><b>{int(dashboard.get("states",{}).get("ACKNOWLEDGED",0))}</b><br><span class="muted">acknowledged</span></div>'
            f'<div><b>{int(dashboard.get("types",{}).get("HEALTH",0))}</b><br><span class="muted">health observations</span></div></div>'
            '<p class="muted">Insights are evidence and recommendations only. Any configuration action must use the existing approved Structured Changes, Desired State or Campaign workflow.</p></div>'
        )
        filter_form = (
            '<div class="panel"><h2>Insight search</h2><form method="get" action="/operations">'
            '<input type="hidden" name="tab" value="intelligence"><div class="row">'
            f'<div><label>State</label><select name="state"><option value="">all</option>{self._ops_select_options(["NEW","ACKNOWLEDGED","RESOLVED","EXPIRED"], state_filter)}</select></div>'
            f'<div><label>Type</label><select name="type"><option value="">all</option>{self._ops_select_options(["CAPACITY","FAILURE_RISK","DEPENDENCY_IMPACT","HEALTH","L3_PATH","ROUTE_DEPENDENCY"], type_filter)}</select></div>'
            f'<div><label>Object</label><input name="object_id" value="{_e(object_filter)}"></div>'
            f'<div><label>Search</label><input name="search" value="{_e(search)}"></div></div>'
            '<button class="ghost">Filter</button></form></div>'
        )
        rows = ''.join(
            '<tr>'
            f'<td><a href="/operations?tab=intelligence&insight={int(x["id"])}">INSIGHT#{int(x["id"])}</a></td>'
            f'<td>{_e(x.get("insight_type"))}</td><td>{_e(x.get("object_id"))}</td>'
            f'<td>{_status(x.get("severity"))}</td><td>{_status(x.get("state"))}</td>'
            f'<td>{float(x.get("confidence") or 0):.2f}</td><td>{_e(x.get("summary"))}</td></tr>'
            for x in insights
        ) or '<tr><td colspan="7" class="muted">No persisted analytics insights match this filter.</td></tr>'
        ledger = (
            '<div class="panel"><h2>Persisted insights</h2><table><tr><th>Insight</th><th>Type</th><th>Object</th><th>Severity</th><th>Lifecycle</th><th>Confidence</th><th>Summary</th></tr>'
            + rows + '</table></div>'
        )
        detail = ""
        raw = str((q.get("insight") or [""])[0] or "")
        if raw.isdigit():
            item = self.manager.analytics.get(int(raw))
            if item:
                affected = ''.join(
                    f'<tr><td>{_e(a.get("object_type"))}</td><td>{_e(a.get("object_id"))}</td><td>{_e(a.get("device"))}</td><td>{_e(a.get("depth"))}</td></tr>'
                    for a in (item.get("affected") or [])
                ) or '<tr><td colspan="4" class="muted">No affected-object records.</td></tr>'
                lifecycle = ""
                if sess["role"] in _OPERATOR_ROLES and item.get("state") not in {"RESOLVED","EXPIRED"}:
                    lifecycle = (
                        f'<form method="post" action="/ops-insight-state">{self._csrf_field()}<input type="hidden" name="insight_id" value="{int(item["id"])}">'
                        '<label>Lifecycle</label><select name="state"><option>ACKNOWLEDGED</option><option>RESOLVED</option><option>EXPIRED</option></select>'
                        '<label>Operator note</label><input name="note"><button>Update lifecycle</button></form>'
                    )
                objq = urllib.parse.quote(str(item.get("object_id") or ""))
                drill = (
                    '<div class="row">'
                    f'<a class="btn ghost" href="/topology?device={objq}">Topology evidence</a>'
                    f'<a class="btn ghost" href="/endpoints?device={objq}">Endpoint evidence</a>'
                    f'<a class="btn ghost" href="/events?device={objq}">Event evidence</a>'
                    '<a class="btn ghost" href="/operations?tab=telemetry">Telemetry evidence</a></div>'
                )
                workflow = (
                    '<div class="panel"><h3>Action boundary</h3><p class="muted">Analytics cannot execute remediation. Continue only through an approved existing workflow.</p>'
                    '<div class="row"><a class="btn" href="/operations?tab=structured">Structured Change</a>'
                    '<a class="btn ghost" href="/operations?tab=desired">Desired State</a>'
                    '<a class="btn ghost" href="/operations?tab=campaigns">Campaign</a></div></div>'
                )
                detail = (
                    f'<div class="panel"><h2>INSIGHT#{int(item["id"])} · {_e(item.get("insight_type"))} · {_status(item.get("state"))}</h2>'
                    f'<p><b>{_e(item.get("object_id"))}</b> — {_e(item.get("summary"))}</p>{drill}{lifecycle}'
                    '<h3>Evidence</h3><pre>' + _pretty(item.get("evidence")) + '</pre>'
                    '<h3>Affected objects</h3><table><tr><th>Type</th><th>Object</th><th>Attached device</th><th>Depth</th></tr>' + affected + '</table></div>' + workflow
                )
        jobs = self.manager.analytics.jobs(30)
        job_rows = ''.join(
            f'<tr><td>{int(j["id"])}</td><td>{_e(j.get("job_type"))}</td><td>{_e(j.get("object_id"))}</td><td>{_status(j.get("status"))}</td><td>{_e(j.get("actor"))}</td></tr>'
            for j in jobs
        ) or '<tr><td colspan="5" class="muted">No analytics jobs yet.</td></tr>'
        job_panel = '<div class="panel"><h2>Analytics execution history</h2><table><tr><th>Job</th><th>Analyzer</th><th>Object</th><th>Status</th><th>Actor</th></tr>' + job_rows + '</table></div>'
        return summary + forms + l3_panel + filter_form + detail + ledger + job_panel

    @staticmethod
    def _ops_select_options(values, selected=""):
        return ''.join(f'<option value="{_e(value)}"{" selected" if value == selected else ""}>{_e(value)}</option>' for value in values)

    def _do_ops_analytics_refresh(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            object_id = _value(form, "object_id").strip()
            if not self.manager.inv.get(object_id):
                raise ValueError("managed object not found")
            result = self.manager.analytics.refresh(object_id, actor=sess["username"])
            hid = ((result.get("health") or {}).get("insight") or {}).get("id")
            loc = "/operations?tab=intelligence&notice=Analytics+refreshed"
            if hid:
                loc += f"&insight={int(hid)}"
            return self._redirect(loc)
        except Exception as exc:
            return self._ops_redirect("intelligence", f"Analytics refresh failed: {exc}")

    def _do_ops_analytics_impact(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            object_id = _value(form, "object_id").strip()
            if not self.manager.inv.get(object_id):
                raise ValueError("managed object not found")
            result = self.manager.analytics.simulate_impact(
                object_id, actor=sess["username"], max_depth=int(_value(form, "max_depth", "5")))
            iid = (result.get("insight") or {}).get("id")
            return self._redirect(f"/operations?tab=intelligence&insight={int(iid)}&notice=Impact+simulation+stored")
        except Exception as exc:
            return self._ops_redirect("intelligence", f"Impact simulation failed: {exc}")

    def _do_ops_l3_route_observe(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            item = self.manager.analytics.add_l3_route(
                device=_value(form, "device"), vrf=_value(form, "vrf", "default"),
                destination_prefix=_value(form, "destination_prefix"),
                protocol=_value(form, "protocol"), next_hop=_value(form, "next_hop"),
                outgoing_interface=_value(form, "outgoing_interface"),
                next_device=_value(form, "next_device"), metric=int(_value(form, "metric", "0") or 0),
                terminal=bool(_value(form, "terminal")), evidence_ref=_value(form, "evidence_ref"),
                actor=sess["username"])
            return self._ops_redirect("intelligence", f"Route evidence #{int(item['id'])} stored")
        except Exception as exc:
            return self._ops_redirect("intelligence", f"Route evidence failed: {exc}")

    def _do_ops_l3_path(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            result = self.manager.analytics.simulate_l3_path(
                _value(form, "source_device"), _value(form, "vrf", "default"),
                _value(form, "destination_prefix"), actor=sess["username"],
                max_hops=int(_value(form, "max_hops", "16") or 16))
            iid = (result.get("insight") or {}).get("id")
            return self._redirect(
                f"/operations?tab=intelligence&insight={int(iid)}&notice=L3+path+simulation+stored")
        except Exception as exc:
            return self._ops_redirect("intelligence", f"L3 path simulation failed: {exc}")

    def _do_ops_l3_dependencies(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            result = self.manager.analytics.analyze_route_dependencies(
                _value(form, "failed_device"), actor=sess["username"])
            candidates = result.get("candidates") or []
            if candidates:
                iid = int(candidates[0]["id"])
                return self._redirect(
                    f"/operations?tab=intelligence&insight={iid}&notice=Route+dependency+candidates+stored")
            return self._ops_redirect("intelligence", "No explicit route dependency candidates found")
        except Exception as exc:
            return self._ops_redirect("intelligence", f"Route dependency analysis failed: {exc}")

    def _do_ops_insight_state(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            iid = int(_value(form, "insight_id", "0"))
            item = self.manager.analytics.set_state(iid, _value(form, "state"), sess["username"], _value(form, "note"))
            return self._redirect(f"/operations?tab=intelligence&insight={iid}&notice=Insight+state+updated")
        except Exception as exc:
            return self._ops_redirect("intelligence", f"Insight lifecycle update failed: {exc}")

    def _do_ops_analytics_expire(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            result = self.manager.analytics.expire_stale(
                actor=sess["username"], max_age_seconds=int(_value(form, "max_age_seconds", "604800")))
            return self._ops_redirect("intelligence", f"Expired {int(result['expired'])} stale insights")
        except Exception as exc:
            return self._ops_redirect("intelligence", f"Insight expiry failed: {exc}")

    # ---- HA-1 -----------------------------------------------------------
    def _ops_ha(self, q, sess):
        stale = int((q.get("stale_seconds") or [86400])[0] or 86400)
        readiness = self.manager.ha.readiness()
        nodes = self.manager.ha.nodes(stale)
        node_rows = ''.join(
            f'<tr><td>{_e(n.get("node_id"))}</td><td>{_status(n.get("state") or "ACTIVE")}</td><td>{_e(n.get("hostname"))}</td><td>{_e(n.get("pid"))}</td><td>{_e(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(float(n.get("last_heartbeat_ts") or 0))))}</td><td>{_e(n.get("drain_reason"))}</td></tr>'
            for n in nodes
        )
        drills = self.manager.ha.drills(100)
        drill_rows = ''.join(
            f'<tr><td><a href="/operations?tab=ha&drill={int(d["id"])}">DRILL#{int(d["id"])}</a></td><td>{_e(d.get("kind"))}</td><td>{_status(d.get("state"))}</td><td>{_e(d.get("node_id"))}</td><td>{_e(d.get("verification_ref"))}</td></tr>' for d in drills
        )
        admin = ""
        if sess["role"] == "admin":
            node_opts = ''.join(f'<option value="{_e(n.get("node_id"))}">{_e(n.get("node_id"))}</option>' for n in nodes)
            admin = (
                '<div class="panel"><h2>Cluster node lifecycle</h2>'
                f'<form method="post" action="/ops-ha-node">{self._csrf_field()}<div class="row"><div><label>Node</label><select name="node_id">{node_opts}</select></div>'
                '<div><label>State</label><select name="state"><option>ACTIVE</option><option>DRAINING</option><option>DRAINED</option></select></div><div><label>Drain reason</label><input name="reason"></div></div><button>Apply node state</button></form></div>'
            )
        drill_form = ""
        if sess["role"] in _OPERATOR_ROLES:
            drill_form = (
                '<div class="panel"><h2>Recovery / qualification evidence</h2>'
                f'<form method="post" action="/ops-ha-drill-create">{self._csrf_field()}<div class="row"><div><label>Kind</label><select name="kind"><option>NODE_FAILOVER</option><option>DATABASE_RESTORE</option><option>REBOOT_RECOVERY</option><option>BACKUP_VERIFY</option></select></div>'
                '<div><label>State</label><select name="state"><option>STARTED</option><option>PASSED</option><option>FAILED</option><option>NOT_RUN</option></select></div><div><label>Verification ref</label><input name="verification_ref"></div></div>'
                '<label>Evidence JSON</label><textarea name="detail">{}</textarea><button>Record drill evidence</button></form></div>'
            )
        detail = ""
        raw = str((q.get("drill") or [""])[0] or "")
        if raw.isdigit():
            drill = self.manager.ha.get_drill(int(raw))
            if drill:
                complete = ""
                if sess["role"] in _OPERATOR_ROLES and drill.get("state") == "STARTED":
                    complete = (
                        f'<form method="post" action="/ops-ha-drill-complete">{self._csrf_field()}<input type="hidden" name="drill_id" value="{int(raw)}">'
                        '<label>Completion state</label><select name="state"><option>PASSED</option><option>FAILED</option><option>NOT_RUN</option></select><label>Verification ref</label><input name="verification_ref">'
                        '<label>Additional evidence JSON</label><textarea name="detail">{}</textarea><button>Complete drill</button></form>'
                    )
                detail = f'<div class="panel"><h2>DRILL#{int(raw)} · {_e(drill.get("kind"))} · {_status(drill.get("state"))}</h2><pre>{_pretty(drill)}</pre>{complete}</div>'
        return (
            f'<div class="panel"><h2>HA readiness</h2><pre>{_pretty(readiness)}</pre></div>' + admin + drill_form + detail +
            '<div class="panel"><h2>Cluster nodes</h2><form method="get" action="/operations"><input type="hidden" name="tab" value="ha"><label>Heartbeat history window seconds</label>'
            f'<input name="stale_seconds" value="{stale}"><button class="ghost">Refresh</button></form><table><tr><th>Node</th><th>State</th><th>Host</th><th>PID</th><th>Last heartbeat</th><th>Reason</th></tr>{node_rows or "<tr><td colspan=6 class=muted>no cluster-node records</td></tr>"}</table></div>'
            f'<div class="panel"><h2>Recovery drills</h2><table><tr><th>Drill</th><th>Kind</th><th>State</th><th>Node</th><th>Verification</th></tr>{drill_rows or "<tr><td colspan=5 class=muted>no recovery drill evidence</td></tr>"}</table></div>'
        )

    def _do_ops_ha_node(self, form, sess):
        if not self._ops_require(sess, _ADMIN_ROLES):
            return
        try:
            self.manager.ha.set_node_state(state=_value(form, "state"), actor=sess["username"], node_id=_value(form, "node_id") or None, reason=_value(form, "reason"))
            return self._ops_redirect("ha", "Cluster node state updated")
        except Exception as exc:
            return self._ops_redirect("ha", f"Node-state update failed: {exc}")

    def _do_ops_ha_drill_create(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            self.manager.ha.record_drill(kind=_value(form, "kind"), actor=sess["username"], state=_value(form, "state"), detail=_json_input(_value(form, "detail", "{}"), object_only=True), verification_ref=_value(form, "verification_ref"))
            return self._ops_redirect("ha", "Recovery drill evidence recorded")
        except Exception as exc:
            return self._ops_redirect("ha", f"Drill record failed: {exc}")

    def _do_ops_ha_drill_complete(self, form, sess):
        if not self._ops_require(sess, _OPERATOR_ROLES):
            return
        try:
            did = int(_value(form, "drill_id", "0"))
            self.manager.ha.complete_drill(did, actor=sess["username"], state=_value(form, "state"), detail=_json_input(_value(form, "detail", "{}"), object_only=True), verification_ref=_value(form, "verification_ref"))
            return self._redirect(f"/operations?tab=ha&drill={did}&notice=Drill+completed")
        except Exception as exc:
            return self._ops_redirect("ha", f"Drill completion failed: {exc}")

    # ---- automation approval rendering ---------------------------------
    def _ops_request_detail(self, prev, sess):
        cr = prev["request"]
        auto = prev["automation"]
        badge = "b-ok" if auto.get("snapshot_matches") else "b-bad"
        action = ""
        if cr["status"] == "pending" and sess["role"] in _APPROVER_ROLES:
            action = (
                f'<form method="post" action="/request-approve">{self._csrf_field()}<input type="hidden" name="id" value="{int(cr["id"])}"><button>Approve frozen automation</button></form> '
                f'<form method="post" action="/request-reject">{self._csrf_field()}<input type="hidden" name="id" value="{int(cr["id"])}"><input name="note" placeholder="reason"><button class="danger">Reject</button></form>'
            )
        elif cr["status"] == "approved" and sess["role"] in _APPROVER_ROLES:
            action = f'<form method="post" action="/request-execute">{self._csrf_field()}<input type="hidden" name="id" value="{int(cr["id"])}"><button>Execute approved automation</button></form>'
        return (
            f'<div class="panel"><h2>CR#{int(cr["id"])} · {_e(cr.get("title"))} · {_status(cr.get("status"))}</h2>'
            f'<p>Automation kind: <b>{_e((auto.get("intent") or {}).get("kind"))}</b></p>'
            f'<p>Snapshot integrity: <span class="badge {badge}">{"CURRENT" if auto.get("snapshot_matches") else "DRIFTED — re-submit required"}</span></p>'
            f'<table><tr><th>Submitted SHA-256</th><td><code>{_e(auto.get("snapshot_sha256"))}</code></td></tr>'
            f'<tr><th>Current SHA-256</th><td><code>{_e(auto.get("snapshot_current_sha256"))}</code></td></tr></table>'
            '<div class="row"><div><h3>Frozen submitted intent</h3><pre>' + _pretty(auto.get("submitted_snapshot")) + '</pre></div>'
            '<div><h3>Current resolved intent</h3><pre>' + _pretty(auto.get("current_snapshot")) + '</pre></div></div>'
            f'<div>{action}</div></div>'
        )
