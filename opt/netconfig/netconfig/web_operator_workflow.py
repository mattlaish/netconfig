"""Operator navigation, durable read-only collection tasks and setup feedback."""
import html
import json
import re
import urllib.parse
import uuid

from .collection_operations import KIND_LABELS, operations_for
from .users import can
from .web_ux import safe_next_path

RESTART_SETTINGS = {
    "web_bind": "Web bind address", "web_port": "Web port",
    "netflow_enabled": "NetFlow receiver", "netflow_port": "NetFlow port",
    "netflow_max_flows": "Recent flow memory", "netflow_history_enabled": "Flow history",
    "snmp_poll_interval": "SNMP polling schedule", "monitor_poll_interval": "Monitoring schedule",
    "syslog_enabled": "Syslog receiver", "syslog_port": "Syslog port",
    "snmp_trap_enabled": "SNMP trap receiver", "snmp_trap_port": "SNMP trap port",
    "digest_interval": "Digest schedule", "telemetry_scheduler_interval": "Telemetry schedule",
}


def restart_notice(manager):
    applied = getattr(manager, "_console_applied_settings", None)
    if applied is None:
        manager._console_applied_settings = dict(manager.settings)
        return ""
    keys = dict(RESTART_SETTINGS)
    keys["core_db_backend"] = "Core database backend"
    if "postgres" in {applied.get("core_db_backend"), manager.settings.get("core_db_backend")}:
        keys.update({key: label for key, label in (
            ("pg_host", "Core database host"), ("pg_port", "Core database port"),
            ("pg_dbname", "Core database name"), ("pg_user", "Core database user"),
            ("pg_sslmode", "Core database SSL mode"))})
    overrides = getattr(manager, "_console_start_overrides", {})
    changed = [label for key, label in keys.items()
               if key not in overrides and applied.get(key) != manager.settings.get(key)]
    notices = []
    if changed:
        notices.append('<div class="flash workflow-warning" role="status"><b>Saved · restart required</b>'
                       '<div>' + html.escape(", ".join(changed)) +
                       '. The running service is still using its previous values.</div></div>')
    mismatched = [keys[key] + " " + str(value) for key, value in overrides.items()
                  if manager.settings.get(key) != value]
    if mismatched:
        notices.append('<div class="flash workflow-warning" role="status"><b>Service start options override saved settings</b>'
                       '<div>Running with ' + html.escape(", ".join(mismatched)) +
                       '. Update the service start options to apply different saved Web values.</div></div>')
    return "".join(notices)


def feedback_tone(message):
    text = str(message or "").lower()
    if any(word in text for word in ("failed", "not saved", "not permitted", "wrong ", "locked", "interrupted", "could not", "invalid", "denied")):
        return "workflow-error"
    if any(word in text for word in ("partial", "restart required", "out of date")):
        return "workflow-warning"
    return "workflow-success"


class WebWorkflowMixin:
    def _workflow_routes(self, q):
        return {
            "/devices-live": lambda sess: self._dashboard(sess),
            "/collection-tasks": lambda sess: self._collection_tasks_page(sess),
            "/collection-task": lambda sess: self._collection_task_page(q, sess),
            "/collection-status": lambda sess: self._collection_task_page(q, sess, status_only=True),
            "/netflow-saving-status": lambda sess: self._netflow_saving_status(sess),
        }

    def _workflow_posts(self, form, sess):
        return {
            "/collection-start": lambda: self._start_collection(form, sess),
            "/collection-retry": lambda: self._retry_collection(form, sess),
            "/devices-bulk": lambda: self._devices_bulk(form, sess),
        }

    def _operation_reply(self, payload, status=200):
        return self._send(json.dumps(payload), status, "application/json",
                          headers=[("Cache-Control", "no-store")])

    def _start_collection(self, form, sess, kind=None):
        if not can(sess["role"], "collect"):
            return self._operation_reply({"error": "Not permitted to run checks."}, 403)
        kind = kind or (form.get("kind") or ["check"])[0]
        names = form.get("devices") or form.get("name") or []
        if (form.get("all") or [""])[0] == "1":
            names = [d["name"] for d in self.manager.inv.all() if d.get("enabled") and
                     (kind != "collect" or set((d.get("device_type") or "network").split(",")) & {"network", "system"}) and
                     (kind != "snmp" or d.get("snmp_version"))]
        request_key = (form.get("request_key") or [uuid.uuid4().hex])[0]
        if not re.fullmatch(r"[A-Za-z0-9-]{16,80}", request_key):
            return self._operation_reply({"error": "Invalid operation request."}, 400)
        try:
            task_id = operations_for(self.manager).start(kind, names, sess["username"], request_key)
        except ValueError as exc:
            return self._operation_reply({"error": str(exc)}, 400)
        self.manager.db.audit(sess["username"], "collection_task_start", task_id, kind)
        back = safe_next_path((form.get("return_to") or ["/"])[0]) or "/"
        location = "/collection-task?" + urllib.parse.urlencode({"id": task_id, "back": back})
        if self.headers.get("X-NetConfig-Operation") == "start":
            return self._operation_reply({"location": location, "id": task_id}, 202)
        return self._redirect(location)

    def _owned_task(self, task_id, sess):
        task = operations_for(self.manager).get(task_id)
        if not task or (task["owner"] != sess["username"] and sess["role"] != "admin"):
            return None
        return task

    def _retry_collection(self, form, sess):
        task = self._owned_task((form.get("id") or [""])[0], sess)
        if not task:
            return self._send("Not found", 404, "text/plain")
        if task["state"] in {"queued", "running"}:
            return self._operation_reply({"error": "Wait for this task to finish before retrying."}, 409)
        names = [r["device"] for r in task["results"] if r["ok"] is not True]
        return self._start_collection({**form, "devices": names, "kind": [task["kind"]]}, sess)

    def _collection_tasks_page(self, sess):
        tasks = operations_for(self.manager).recent(sess["username"], sess["role"] == "admin")
        rows = "".join(
            f'<tr><td><a href="/collection-task?id={t["id"]}">{html.escape(KIND_LABELS[t["kind"]])}</a></td>'
            f'<td>{html.escape(t["owner"])}</td><td>{html.escape(t["state"])}</td>'
            f'<td>{sum(r["ok"] is not None for r in t["results"])} / {len(t["results"])}</td></tr>'
            for t in tasks)
        return self._send(self._page("Collection tasks",
            '<div class="panel"><p>Open a task to check progress, review each device and retry failures.</p>'
            '<table><tr><th>Task</th><th>Started by</th><th>Status</th><th>Completed</th></tr>' +
            (rows or '<tr><td colspan=4>No tasks yet.</td></tr>') + '</table></div>', sess))

    def _collection_task_page(self, q, sess, status_only=False):
        task = self._owned_task((q.get("id") or [""])[0], sess)
        if not task:
            return self._send("Not found", 404, "text/plain")
        if status_only:
            return self._operation_reply(task)
        back = safe_next_path((q.get("back") or ["/"])[0]) or "/"
        rows = "".join(
            f'<tr><td><a href="/device?name={urllib.parse.quote(r["device"])}#tab-{html.escape(r.get("target_tab", "overview"))}">{html.escape(r["device"])}</a></td>'
            f'<td>{html.escape(r["state"])}</td><td>{html.escape(r["message"])}</td></tr>'
            for r in task["results"])
        retry = ""
        if can(sess["role"], "collect"):
            retry = (f'<form method=post action="/collection-retry">{self._csrf_field()}'
                     f'<input type=hidden name=id value="{task["id"]}">'
                     f'<input type=hidden name=return_to value="{html.escape(back)}">'
                     '<button data-retry-failed>Retry unfinished or failed devices</button></form>')
        done = sum(r["ok"] is not None for r in task["results"])
        body = (f'<div class="panel" id="collection-task" data-task-id="{task["id"]}">'
                f'<p><a class="btn ghost" href="{html.escape(back)}">Return to previous page</a> '
                '<a class="btn ghost" href="/collection-tasks">All collection tasks</a></p>'
                f'<h2>{html.escape(KIND_LABELS[task["kind"]])}</h2>'
                f'<p data-task-summary role=status>{html.escape(task["state"])} · {done} / {len(task["results"])}</p>'
                f'<progress value="{done}" max="{len(task["results"])}"></progress>'
                f'<table><tr><th>Device</th><th>Status</th><th>Result / next action</th></tr>'
                f'<tbody data-task-rows>{rows}</tbody></table>{retry}</div>')
        return self._send(self._page("Collection progress", body, sess))

    def _devices_bulk(self, form, sess):
        action = (form.get("action") or ["check"])[0]
        if action == "check":
            return self._start_collection({**form, "kind": ["check"]}, sess)
        if not can(sess["role"], "manage_devices"):
            return self._send("Not permitted", 403, "text/plain")
        names = sorted(set(form.get("devices") or []))
        if not names or action not in {"enable", "disable", "tags"}:
            return self._operation_reply({"error": "Select devices and a supported action."}, 400)
        tags = (form.get("tags") or [""])[0].replace(",", " ").split()
        if action == "tags" and not tags:
            return self._operation_reply({"error": "Enter at least one tag."}, 400)
        devices = [self.manager.inv.get(name) for name in names]
        if not all(devices):
            return self._operation_reply({"error": "A selected device no longer exists. Reload Devices."}, 409)
        rows = []
        succeeded = 0
        for dev in devices:
            try:
                if action == "tags":
                    self.manager.inv.update_operator_fields(dev["name"], add_tags=tags)
                else:
                    self.manager.inv.update_operator_fields(dev["name"], enabled=action == "enable")
                self.manager.db.audit(sess["username"], "device_bulk_" + action, dev["name"], "")
                result = "Updated"
                succeeded += 1
            except Exception:
                result = "Update failed. Review this device before retrying."
            rows.append(f'<tr><td>{html.escape(dev["name"])}</td><td>{result}</td></tr>')
        return self._send(self._page("Device updates",
            '<div class="panel"><a class="btn" href="/">Return to Devices</a>'
            f'<p class="{("workflow-success" if succeeded == len(devices) else "workflow-warning" if succeeded else "workflow-error")}">'
            f'{succeeded} updated · {len(devices)-succeeded} failed</p>'
            '<table><tr><th>Device</th><th>Result</th></tr>' + "".join(rows) + '</table></div>', sess))

    def _device_tools(self, dev, sess):
        name = dev["name"]
        names = sorted(d["name"] for d in self.manager.inv.all())
        options = "".join(f'<option value="{html.escape(n)}"{" selected" if n == name else ""}>'
                          f'{html.escape(n)}</option>' for n in names)
        pos = names.index(name)
        nav = '<a class="btn ghost" data-device-return href="/">Devices</a> '
        for label, offset in (("Previous", -1), ("Next", 1)):
            index = pos + offset
            if 0 <= index < len(names):
                nav += f'<a class="btn ghost" data-keep-tab href="/device?name={urllib.parse.quote(names[index])}">{label}</a> '
        actions = ""
        if can(sess["role"], "collect"):
            actions += (f'<form method=post action="/collection-start" class="inline-form">'
                        f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(name)}">'
                        '<input type=hidden name=kind value=check><button>Check now</button></form>')
        if can(sess["role"], "collect"):
            kinds = set(re.split(r"[,\s]+", dev.get("device_type") or "network"))
            for path, label in (("/collect", "Collect configuration"), ("/snmp-poll", "Poll SNMP")):
                if (path == "/collect" and not kinds & {"network", "system"}) or (path == "/snmp-poll" and (not kinds & {"network", "system"} or not dev.get("snmp_version"))):
                    continue
                actions += (f'<form method=post action="{path}" class="inline-form">{self._csrf_field()}'
                            f'<input type=hidden name=name value="{html.escape(name)}"><button class=ghost>{label}</button></form>')
        if can(sess["role"], "manage_devices"):
            actions += (f' <a class="btn ghost" data-edit-return href="/device-new?name={urllib.parse.quote(name)}">Edit</a>'
                        f' <a class="btn ghost" href="/device-new?copy={urllib.parse.quote(name)}">Copy device settings</a>')
        return (f'<div class="device-tools"><div class="device-tools-row">{nav}'
                f'<label>Device <input type=search data-device-search placeholder="Find device" aria-label="Find device">'
                f'<select data-device-switch>{options}</select></label>'
                f'<button class=ghost type=button data-copy="{html.escape(dev["host"])}">Copy address</button>'
                f'{actions}</div></div>')

    def _netflow_saving_status(self, sess):
        if not can(sess["role"], "settings"):
            return self._send("Not permitted", 403, "text/plain")
        return self._send(self._netflow_setup())

    def _netflow_setup(self):
        history = getattr(getattr(self, "netflow", None), "history", None)
        st = history.status() if history is not None else {}
        collector = getattr(self, "netflow", None)
        receive = "Receiving is off"
        if collector is not None:
            status = collector.status()
            receive = "Receiver running" if status.get("running") else "Receiver stopped"
        if not history:
            saving = "24-hour saving is off"
        elif st.get("write_error"):
            saving = st["write_error"]
        elif st.get("last_write_ts"):
            from .web_ui import _fmt_ts
            saving = "Saving traffic · last successful write " + _fmt_ts(st["last_write_ts"])
        elif st.get("configured") is False:
            saving = "Set a History database to save traffic for 24 hours."
        else:
            saving = "Waiting for the first successful flow write."
        return ('<div class="panel" id="netflow-saving"><h2>NetFlow setup & saving status</h2>'
                f'<p>{html.escape(receive)}</p><p>{html.escape(saving)}</p>'
                '<p><a class="btn ghost" href="/settings?section=db">Edit History connection</a></p>'
                f'<form method=post action="/history-db-test">{self._csrf_field()}'
                '<input type=hidden name=return_section value=netflow>'
                '<button>Test saved History + NetFlow</button></form>'
                '<p class=muted>Uses the saved History connection and Vault password. Retention is 24 hours.</p></div>')
