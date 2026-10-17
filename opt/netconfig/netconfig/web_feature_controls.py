"""Console controls for existing account, collection and evidence operations."""
from __future__ import annotations

import html
import json
import re
import urllib.parse

from . import config
from .debug import DebugBundle, redact
from .evidence_signing import _normalize_fingerprint, signing_status
from .protocoltrace import (
    DEFAULT_MAX_BYTES, DEFAULT_MAX_EVENTS, DEFAULT_TTL, IMPLEMENTED_CAPTURE_PROTOCOLS,
    MAX_BYTES, MAX_EVENTS, MAX_TTL, STATUSES,
)
from .users import MIN_PASSWORD_LENGTH, can, roles, validate_password
from .web_ui import _fmt_ts


def _value(form, key, default=""):
    return str((form.get(key) or [default])[0])


def _escape(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def _json_panel(title, value):
    return (f'<div class="panel"><h2>{_escape(title)}</h2>'
            f'<pre>{_escape(json.dumps(redact(value), indent=2, sort_keys=True, default=str))}</pre></div>')


class WebFeatureControlsMixin:
    def _feature_error(self, sess, title, error, status=400):
        return self._send(self._page(title, f'<div class="err">{_escape(error)}</div>', sess), status)

    def _users_page(self, sess, flash=None):
        if not can(sess["role"], "manage_users"):
            return self._feature_error(sess, "Users", "Admin only.", 403)
        rows = []
        for user in self.manager.users.all():
            username = _escape(user["username"])
            hidden = self._csrf_field() + f'<input type=hidden name=username value="{username}">'
            options = "".join(
                f'<option value="{role}"{" selected" if role == user["role"] else ""}>{role}</option>'
                for role in roles())
            access = '<span class="muted">Current account</span>'
            if user["username"] != sess["username"]:
                action = "enable" if user["disabled"] else "disable"
                access = (
                    f'<form method=post action="/user-access" data-confirm="{action.capitalize()} this user?">'
                    f'{hidden}<button name=action value="{action}" class=ghost>{action.capitalize()}</button></form>'
                    '<form method=post action="/user-access" data-confirm="Delete this user permanently? Audit history is retained.">'
                    f'{hidden}<button name=action value=delete class=danger>Delete</button></form>')
            state = "disabled" if user["disabled"] else "enabled"
            rows.append(
                f'<tr><td><b>{username}</b><br>{_escape(user["fullname"])}</td>'
                f'<td>{state}</td><td>{_fmt_ts(user["last_login"])}</td><td>'
                f'<form method=post action="/user-update">{hidden}'
                f'<select name=role aria-label="Role for {username}">{options}</select>'
                f'<input type=password name=password autocomplete=new-password minlength={MIN_PASSWORD_LENGTH} placeholder="New password (optional, {MIN_PASSWORD_LENGTH}+ characters)">'
                f'<button>Update role / password</button></form>{access}</td></tr>')
        options = "".join(f'<option>{role}</option>' for role in roles())
        inner = (
            '<div class=panel><p>Disable preserves the account; delete removes it. Existing sessions '
            'are rejected on their next request. Your current account and the last enabled admin are protected.</p>'
            '<table><tr><th>User</th><th>Status</th><th>Last login</th><th>Manage</th></tr>'
            + "".join(rows) + '</table></div><div class=panel><h2>Add user</h2>'
            f'<form method=post action="/user-create">{self._csrf_field()}'
            '<label>Username</label><input name=username required>'
            '<label>Full name</label><input name=fullname>'
            f'<label>Role</label><select name=role>{options}</select>'
            f'<label>Password (at least {MIN_PASSWORD_LENGTH} characters)</label><input type=password name=password autocomplete=new-password minlength={MIN_PASSWORD_LENGTH} required>'
            '<button>Create user</button></form></div>')
        return self._send(self._page("Users", inner, sess, flash=flash))

    def _do_user_create(self, form, sess):
        if not can(sess["role"], "manage_users"):
            return self._feature_error(sess, "Users", "Admin only.", 403)
        username = _value(form, "username").strip()
        try:
            if not username:
                raise ValueError("Username required.")
            validate_password(_value(form, "password"), username)
            self.manager.users.create(username, _value(form, "password"),
                                      role=_value(form, "role", "viewer"), fullname=_value(form, "fullname"))
        except ValueError as exc:
            return self._feature_error(sess, "Users", exc)
        self.manager.db.audit(sess["username"], "user_create", username, _value(form, "role", "viewer"))
        return self._users_page(sess, flash=f"User '{username}' created.")

    def _do_user_update(self, form, sess):
        if not can(sess["role"], "manage_users"):
            return self._feature_error(sess, "Users", "Admin only.", 403)
        username = _value(form, "username")
        role, password = _value(form, "role"), _value(form, "password")
        try:
            # Validate before changing anything so a rejected password never
            # leaves a half-applied role change behind.
            if password:
                validate_password(password, username)
            self.manager.users.change_access(username, actor=sess["username"], role=role or None)
            if password:
                self.manager.users.set_password(username, password)
        except ValueError as exc:
            return self._feature_error(sess, "Users", exc)
        self.manager.db.audit(sess["username"], "user_update", username,
                              f"role={role}" + (" pw-reset" if password else ""))
        if password and username == sess["username"]:
            return self._redirect("/login")
        return self._users_page(sess, flash=f"User '{username}' updated.")

    def _do_user_access(self, form, sess):
        if not can(sess["role"], "manage_users"):
            return self._feature_error(sess, "Users", "Admin only.", 403)
        username, action = _value(form, "username"), _value(form, "action")
        try:
            if action not in {"enable", "disable", "delete"}:
                raise ValueError("Unknown user action.")
            self.manager.users.change_access(username, actor=sess["username"],
                                             disabled=action == "disable" if action != "delete" else None,
                                             delete=action == "delete")
        except ValueError as exc:
            return self._feature_error(sess, "Users", exc)
        self.manager.db.audit(sess["username"], f"user_{action}", username, "console")
        return self._users_page(sess, flash=f"User '{username}': {action} completed.")

    def _do_protocol_delete(self, form, sess):
        if not can(sess["role"], "manage_devices"):
            return self._feature_error(sess, "Device Collection", "Not permitted.", 403)
        device = _value(form, "device")
        if not self.manager.inv.get(device) or not self.manager.protocol_profiles.get(device):
            return self._feature_error(sess, "Device Collection", "Collection profile not found.", 404)
        self.manager.protocol_profiles.delete(device)
        self.manager.db.audit(sess["username"], "protocol_profile_delete", device, "console; default collection restored")
        return self._redirect("/protocols?notice=deleted")

    def _protocol_inspection_controls(self, device, sess):
        if not can(sess["role"], "collect"):
            return ""
        opts = "".join(f'<option value="{key}">{label}</option>' for key, label in (
            ("capabilities", "Check supported features"), ("read-state", "Read device state"), ("subscribe-once", "Collect one sample (gNMI)")))
        return (
            '<div class=panel><h2>Inspect structured protocol</h2>'
            '<p class=muted>Reads device information using the saved collection profile and stored credentials. '
            'Opening this page never contacts a device. Subscribe once requires gNMI.</p>'
            f'<form method=post action="/protocol-inspect">{self._csrf_field()}'
            f'<input type=hidden name=device value="{_escape(device)}">'
            f'<label>Operation</label><select name=operation>{opts}</select>'
            '<label>Read path override (optional)</label><input name=path placeholder="Use the saved profile path">'
            '<button>Run read operation</button></form></div>')

    def _do_protocol_inspect(self, form, sess):
        if not can(sess["role"], "collect"):
            return self._feature_error(sess, "Device Collection", "Not permitted.", 403)
        device, operation = _value(form, "device"), _value(form, "operation")
        path = _value(form, "path").strip() or None
        try:
            if operation == "capabilities":
                result = self.manager.protocol_capabilities(device)
            elif operation == "read-state":
                result = self.manager.protocol_read_state(device, path=path)
            elif operation == "subscribe-once":
                result = self.manager.protocol_subscribe_once(device, path=path)
            else:
                raise ValueError("Unsupported read operation.")
        except ValueError as exc:
            return self._feature_error(sess, "Device Collection", exc)
        except Exception:
            return self._feature_error(sess, "Device Collection", "Protocol read failed. Check the saved profile, device and credentials.", 502)
        self.manager.db.audit(sess["username"], "protocol_inspect", device, operation)
        back = f'<a class=btn href="/protocols?device={urllib.parse.quote(device, safe="")}">Back to collection settings</a>'
        return self._send(self._page("Protocol read result", back + _json_panel(operation, result), sess))

    def _evidence_settings_content(self, sess):
        settings = self.manager.settings
        pins = settings.get("evidence_trusted_fingerprints") or []
        if isinstance(pins, str):
            pins = pins.split(",")
        checked = " checked" if settings.get("evidence_signing_required") else ""
        inner = (
            '<div class=panel><h2>Evidence signing policy</h2>'
            '<p>Require signatures on new diagnostic and case-export archives, and configure trusted signer '
            'SHA-256 public-key fingerprints. A valid signature and a trusted signer are separate results.</p>'
            f'<form method=post action="/settings-save">{self._csrf_field()}'
            '<input type=hidden name=section value=evidence>'
            f'<label><input type=checkbox name=evidence_signing_required value=1{checked}> Require evidence signatures</label>'
            '<label>Trusted signer fingerprints (one SHA256 digest per line, or comma-separated)</label>'
            f'<textarea name=evidence_trusted_fingerprints>{_escape(chr(10).join(pins))}</textarea>'
            '<p class=muted>Private signing keys stay in the configured service credential/environment location. '
            'If signing is required and no usable key is available, archive creation fails closed. '
            'NETCONFIG_EVIDENCE_SIGNING_REQUIRED overrides the stored requirement; '
            'NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS adds trust pins.</p>'
            '<button>Save evidence policy</button></form></div>')
        return inner + self._signing_status_panel()

    def _signing_status_panel(self):
        try:
            status = signing_status(self.manager.settings)
        except (ValueError, OSError) as exc:
            status = {"ready": False, "error": str(exc)}
        return _json_panel("Effective signing status", status)

    def _save_evidence_settings(self, form, sess):
        if not can(sess["role"], "settings"):
            return self._feature_error(sess, "Evidence policy", "Admin only.", 403)
        try:
            values = [v for v in re.split(r"[,\s]+", _value(form, "evidence_trusted_fingerprints")) if v]
            if len(values) > 100:
                raise ValueError("At most 100 trusted fingerprints are allowed.")
            # Persist only submitted pins, never copy environment-added pins into settings.json.
            pins = sorted({_normalize_fingerprint(v) for v in values})
            updated = dict(self.manager.settings)
            updated.update(evidence_signing_required=_value(form, "evidence_signing_required") == "1",
                           evidence_trusted_fingerprints=pins)
            config.save_settings(self.manager.paths, updated)
        except (ValueError, OSError) as exc:
            return self._feature_error(sess, "Evidence policy", exc)
        self.manager.settings.update(updated)
        self.manager.db.audit(sess["username"], "evidence_policy_save", "evidence",
                              f"required={int(updated['evidence_signing_required'])};trust_pins={len(pins)}")
        return self._settings_page_v2(sess, q={"section": ["evidence"]}, flash="Evidence signing policy saved.")

    def _do_debug_create(self, form, sess):
        if not can(sess["role"], "settings"):
            return self._feature_error(sess, "Diagnostics", "Admin only.", 403)
        mode = _value(form, "mode", "full")
        require_signature = _value(form, "require_signature") == "1"
        try:
            bundles = DebugBundle(self.manager)
            if mode == "device":
                device = _value(form, "device")
                if not self.manager.inv.get(device):
                    raise ValueError("Select an existing device.")
                out = bundles.device_capture(device, require_signature=require_signature)
            elif mode == "full":
                out = bundles.collect(require_signature=require_signature)
            else:
                raise ValueError("Unknown diagnostic capture mode.")
        except (ValueError, OSError) as exc:
            return self._feature_error(sess, "Diagnostics", exc)
        self.manager.db.audit(sess["username"], "debug_bundle_create", out.name, f"console;mode={mode}")
        return self._redirect("/diagnostics")

    def _do_debug_verify(self, form, sess):
        if not can(sess["role"], "settings"):
            return self._feature_error(sess, "Diagnostics", "Admin only.", 403)
        name = _value(form, "name")
        try:
            result = DebugBundle(self.manager).verify_bundle(name)
        except (ValueError, OSError) as exc:
            return self._feature_error(sess, "Bundle verification", exc, 409)
        self.manager.db.audit(sess["username"], "debug_bundle_verify", name, "console")
        trust = ("Trusted signer." if result.get("trusted") else
                 "Signature is valid, but the signer is NOT trusted by the configured fingerprints.")
        inner = '<a class=btn href="/diagnostics">Back to diagnostics</a>'
        inner += f'<div class=panel><p>{_escape(trust)}</p></div>' + _json_panel("Bundle verification", result)
        return self._send(self._page("Bundle verification", inner, sess))

    def _do_debug_cleanup(self, form, sess):
        if not can(sess["role"], "settings"):
            return self._feature_error(sess, "Diagnostics", "Admin only.", 403)
        try:
            keep = int(_value(form, "keep", "10"))
            if not 1 <= keep <= 10000:
                raise ValueError("Keep count must be 1..10000.")
            removed = DebugBundle(self.manager).cleanup(keep=keep)
        except (ValueError, OSError) as exc:
            return self._feature_error(sess, "Diagnostics", exc)
        self.manager.db.audit(sess["username"], "debug_bundle_cleanup", "debug-bundles", f"keep={keep};removed={len(removed)}")
        inner = '<a class=btn href="/diagnostics">Back to diagnostics</a>'
        inner += _json_panel(f"Removed {len(removed)} old bundle(s)", removed)
        return self._send(self._page("Bundle cleanup", inner, sess))

    def _traces_page(self, q, sess):
        if not can(sess["role"], "view"):
            return self._feature_error(sess, "Protocol Traces", "Not permitted.", 403)
        ref, device = _value(q, "ref"), _value(q, "device")
        status = _value(q, "status")
        store = self.manager.protocol_traces
        inner = '<p>Traces record connection and collection activity, not raw device responses. They observe subsequent normal collection; '
        inner += 'starting a trace does not trigger polling or configuration changes.</p>'
        if ref:
            item = store.get(ref)
            if not item:
                return self._feature_error(sess, "Protocol Traces", "Trace not found.", 404)
            inner += '<a class=btn href="/traces">All traces</a>' + _json_panel("Trace session", item)
            if item["status"] == "ACTIVE" and can(sess["role"], "collect"):
                inner += (f'<form method=post action="/trace-stop">{self._csrf_field()}'
                          f'<input type=hidden name=trace value="{_escape(item["trace_key"])}">'
                          '<button>Stop trace</button></form>')
            inner += _json_panel("Captured events (first 1000)", store.events(ref, limit=1000))
        else:
            try:
                items = store.list(device=device or None, status=status or None, limit=200)
            except ValueError as exc:
                return self._feature_error(sess, "Protocol Traces", exc)
            opts = '<option value="">All states</option>' + "".join(
                f'<option{" selected" if state == status else ""}>{state}</option>' for state in STATUSES)
            inner += (f'<form method=get action="/traces"><label>Device filter</label>'
                      f'<input name=device value="{_escape(device)}"><label>Status</label>'
                      f'<select name=status>{opts}</select><button>Filter</button></form>')
            rows = "".join(
                f'<tr><td><a href="/traces?ref={urllib.parse.quote(item["trace_key"], safe="")}">{_escape(item["trace_key"])}</a></td>'
                f'<td>{_escape(item["device"])}</td><td>{_escape(item["protocol"])}</td>'
                f'<td>{_escape(item["status"])}</td><td>{item["event_count"]}</td>'
                f'<td>{_fmt_ts(item["expires_ts"])}</td></tr>' for item in items)
            inner += ('<div class=panel><h2>Trace sessions (latest 200)</h2><table><tr><th>Trace</th><th>Device</th>'
                      '<th>Protocol</th><th>Status</th><th>Events</th><th>Expires</th></tr>'
                      + (rows or '<tr><td colspan=6>No traces.</td></tr>') + '</table></div>')
            if can(sess["role"], "collect"):
                devices = "".join(f'<option value="{_escape(d["name"])}">{_escape(d["name"])}</option>'
                                  for d in self.manager.inv.all())
                protocols = "".join(f'<option>{protocol}</option>' for protocol in IMPLEMENTED_CAPTURE_PROTOCOLS)
                inner += (
                    '<div class=panel><h2>Start protocol trace</h2>'
                    f'<form method=post action="/trace-start">{self._csrf_field()}'
                    f'<label>Device</label><select name=device required>{devices}</select>'
                    f'<label>Protocol</label><select name=protocol>{protocols}</select>'
                    '<label>Incident reference (optional)</label><input name=incident_ref>'
                    f'<label>Duration (seconds, 30..{MAX_TTL})</label><input type=number name=ttl min=30 max={MAX_TTL} value={DEFAULT_TTL}>'
                    f'<label>Maximum events (1..{MAX_EVENTS})</label><input type=number name=max_events min=1 max={MAX_EVENTS} value={DEFAULT_MAX_EVENTS}>'
                    f'<label>Byte budget (4096..{MAX_BYTES})</label><input type=number name=max_bytes min=4096 max={MAX_BYTES} value={DEFAULT_MAX_BYTES}>'
                    '<label>Reason</label><input name=reason maxlength=1000><button>Start trace</button></form></div>')
        return self._send(self._page("Protocol Traces", inner, sess))

    def _do_trace_start(self, form, sess):
        if not can(sess["role"], "collect"):
            return self._feature_error(sess, "Protocol Traces", "Not permitted.", 403)
        try:
            item = self.manager.protocol_traces.start(
                _value(form, "device"), _value(form, "protocol"), actor=sess["username"],
                incident_ref=_value(form, "incident_ref") or None,
                ttl=int(_value(form, "ttl", str(DEFAULT_TTL))),
                max_events=int(_value(form, "max_events", str(DEFAULT_MAX_EVENTS))),
                max_bytes=int(_value(form, "max_bytes", str(DEFAULT_MAX_BYTES))), reason=_value(form, "reason"))
        except (ValueError, TypeError) as exc:
            return self._feature_error(sess, "Protocol Traces", exc)
        return self._redirect("/traces?ref=" + urllib.parse.quote(item["trace_key"], safe=""))

    def _do_trace_stop(self, form, sess):
        if not can(sess["role"], "collect"):
            return self._feature_error(sess, "Protocol Traces", "Not permitted.", 403)
        try:
            item = self.manager.protocol_traces.stop(_value(form, "trace"), actor=sess["username"])
        except ValueError as exc:
            return self._feature_error(sess, "Protocol Traces", exc, 404)
        return self._redirect("/traces?ref=" + urllib.parse.quote(item["trace_key"], safe=""))
