"""MC-8 Settings / Integrations operator surface."""
from __future__ import annotations

import html
import json

from .apitokens import ApiTokens, VALID_SCOPES
from .external_evidence import SOURCE_TYPES, ExternalEvidenceError
from .users import can as _can


def _fmt_ts(value):
    import datetime
    try:
        ts = float(value or 0)
    except (TypeError, ValueError):
        ts = 0
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _badge(value):
    state = str(value or "UNKNOWN").upper()
    cls = "b-ok" if state in {"CONNECTED", "OK"} else ("b-warn" if state in {"DEGRADED", "FAILED"} else "b-dim")
    return f'<span class="badge {cls}">{html.escape(state)}</span>'


class WebIntegrationsMixin:
    def _integration_settings_content(self, sess, issued_token=""):
        if not _can(sess["role"], "settings"):
            return '<div class="err">Admin only.</div>'
        sources = self.manager.external_evidence.sources(limit=500)
        all_tokens = ApiTokens(self.manager.db.conn).list()
        token_rows = []
        for token in all_tokens:
            try:
                scopes = set(json.loads(token.get("scopes") or "[]"))
            except json.JSONDecodeError:
                scopes = set()
            if "external:ingest" in scopes and not token.get("disabled"):
                token_rows.append(token)
        rows = []
        for source in sources:
            next_enabled = not source["enabled"]
            state_label = "Enable" if next_enabled else "Disable"
            rows.append(
                '<tr>'
                f'<td><b>{html.escape(source["display_name"])}</b><div class=muted><code>{html.escape(source["source_key"])}</code> · {html.escape(source["source_type"])}</div></td>'
                f'<td>{_badge(source["status"])}</td>'
                f'<td>{_fmt_ts(source["last_event_ts"])}</td>'
                f'<td>{int(source["received_count"])}</td>'
                f'<td>{int(source["rejected_count"])}</td>'
                f'<td>{_badge(source["auth_state"])}<div class=muted>{html.escape(source.get("token_name") or "no token")}</div></td>'
                f'<td><form method=post action="/integration-source-state">{self._csrf_field()}'
                f'<input type=hidden name=source_key value="{html.escape(source["source_key"])}">'
                f'<input type=hidden name=enabled value="{1 if next_enabled else 0}"><button class=ghost>{state_label}</button></form></td>'
                '</tr>'
            )
        types = ''.join(f'<option>{html.escape(item)}</option>' for item in SOURCE_TYPES)
        token_opts = ''.join(
            f'<option value="{int(token["id"])}">#{int(token["id"])} · {html.escape(token["name"])}</option>'
            for token in token_rows
        )
        token_select = (
            f'<select name=ingest_token_id required><option value="">Select external:ingest token</option>{token_opts}</select>'
            if token_opts else
            '<select name=ingest_token_id disabled><option>No enabled external:ingest token exists</option></select>'
        )
        api_rows = []
        for token in all_tokens:
            try:
                scopes = ", ".join(sorted(json.loads(token.get("scopes") or "[]")))
            except json.JSONDecodeError:
                scopes = "[invalid scope metadata]"
            revoke = ""
            if not token.get("disabled"):
                revoke = (f'<form method=post action="/api-token-revoke" class="inline-form">{self._csrf_field()}'
                          f'<input type=hidden name=id value="{int(token["id"])}"><button class=ghost>Revoke</button></form>')
            api_rows.append(f'<tr><td>#{int(token["id"])}</td><td>{html.escape(token["name"])}</td><td>{html.escape(token["role"])}</td><td><code>{html.escape(scopes)}</code></td><td>{"revoked" if token.get("disabled") else "active"}</td><td>{_fmt_ts(token.get("last_used_ts"))}</td><td>{revoke}</td></tr>')
        scope_options = ''.join(
            f'<option value="{html.escape(scope)}"{" selected" if scope == "external:ingest" else ""}>{html.escape(scope)}</option>'
            for scope in sorted(VALID_SCOPES)
        )
        issued = ""
        if issued_token:
            issued = (f'<div class="panel"><h2>API token created — copy it now</h2>'
                      f'<p class="muted">Only the SHA-256 hash is stored. This raw token is shown once in this response and is not placed in the URL.</p>'
                      f'<pre>{html.escape(issued_token)}</pre></div>')
        token_panel = (issued + f'<div class="panel"><h2>API bearer tokens</h2>'
                       f'<p class="muted">Admin lifecycle surface for scoped API tokens. Revoke unused tokens; raw token values are never stored.</p>'
                       f'<div class="table-wrap"><table><tr><th>ID</th><th>Name</th><th>Role</th><th>Scopes</th><th>State</th><th>Last used</th><th></th></tr>{"".join(api_rows) or "<tr><td colspan=7 class=muted>No API tokens.</td></tr>"}</table></div>'
                       f'<h3>Create token</h3><form method=post action="/api-token-create">{self._csrf_field()}<div class=row>'
                       f'<div><label>Name</label><input name=name required maxlength=120 placeholder="ndr-primary-ingest"></div>'
                       f'<div><label>Role</label><select name=role><option>viewer</option><option selected>operator</option><option>approver</option><option>admin</option></select></div>'
                       f'<div><label>Scopes</label><select name=scopes multiple size=8 required>{scope_options}</select><div class=muted>Ctrl/Cmd-click for multiple scopes.</div></div></div><button>Create token</button></form></div>')
        return token_panel + f'''<div class="panel"><h2>External evidence integrations</h2>
<p class="muted">MC-8 connectors are inbound, evidence-only integrations. They cannot reconfigure external systems, execute EDR response, run device commands, or bypass Structured Change authority.</p>
<div class="table-wrap"><table><tr><th>Source</th><th>Status</th><th>Last event</th><th>Received</th><th>Rejected</th><th>Authentication</th><th>State</th></tr>{''.join(rows) or '<tr><td colspan=7 class=muted>No external evidence sources configured.</td></tr>'}</table></div></div>
<div class="panel"><h2>Register inbound source</h2>
<p class="muted">Create or select a dedicated bearer token above with <code>external:ingest</code>. NetConfig stores only the token hash in the API-token table and binds the source to that token ID; no connector secret is stored here.</p>
<form method=post action="/integration-source-save">{self._csrf_field()}<div class=row>
<div><label>Source key</label><input name=source_key required placeholder="ndr-primary"></div>
<div><label>Display name</label><input name=display_name required placeholder="Primary NDR"></div>
<div><label>Source type</label><select name=source_type>{types}</select></div></div>
<div class=row><div><label>Ingest token</label>{token_select}</div>
<div><label>Max request/payload bytes</label><input name=max_payload_bytes type=number min=1024 max=262144 value=65536></div>
<div><label>Rate limit / minute</label><input name=rate_limit_per_minute type=number min=1 max=6000 value=120></div></div>
<button{' disabled' if not token_opts else ''}>Register / update source</button></form>
<p class="muted">Push normalized JSON to <code>/api/v1/external-evidence/&lt;source-key&gt;/events</code>. Required event fields: <code>source_event_id</code>, <code>idempotency_key</code>, <code>event_type</code>, and <code>source_ts</code>. Raw payload fields are recursively secret-redacted before persistence.</p></div>'''

    def _do_api_token_create(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._send("forbidden", 403, "text/plain")
        name = (form.get("name") or [""])[0].strip()
        role = (form.get("role") or ["viewer"])[0].strip()
        scopes = [str(item).strip() for item in (form.get("scopes") or []) if str(item).strip()]
        try:
            if not name:
                raise ValueError("token name is required")
            token_id, raw = ApiTokens(self.manager.db.conn).create(
                name, scopes, created_by=sess["username"], role=role)
            self.manager.db.audit(sess["username"], "api_token_create", str(token_id), ",".join(sorted(scopes)))
        except (TypeError, ValueError) as exc:
            return self._settings_page_v2(
                sess, q={"section": ["integrations"]}, flash="API token rejected: " + str(exc))
        return self._settings_page_v2(
            sess, q={"section": ["integrations"], "_issued_token": [raw]},
            flash=f"API token #{token_id} created. Copy the raw value now.")

    def _do_api_token_revoke(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._send("forbidden", 403, "text/plain")
        try:
            token_id = int((form.get("id") or ["0"])[0])
            if token_id <= 0:
                raise ValueError("invalid token id")
            ApiTokens(self.manager.db.conn).revoke(token_id)
            self.manager.db.audit(sess["username"], "api_token_revoke", str(token_id), "web integrations")
        except (TypeError, ValueError) as exc:
            return self._settings_page_v2(
                sess, q={"section": ["integrations"]}, flash="API token revoke rejected: " + str(exc))
        return self._settings_page_v2(
            sess, q={"section": ["integrations"]}, flash=f"API token #{token_id} revoked.")

    def _do_integration_source_save(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._send("forbidden", 403, "text/plain")
        try:
            self.manager.external_evidence.register_source(
                (form.get("source_key") or [""])[0],
                (form.get("source_type") or [""])[0],
                (form.get("display_name") or [""])[0],
                ingest_token_id=(form.get("ingest_token_id") or [""])[0],
                max_payload_bytes=int((form.get("max_payload_bytes") or ["65536"])[0] or 65536),
                rate_limit_per_minute=int((form.get("rate_limit_per_minute") or ["120"])[0] or 120),
                actor=sess["username"],
            )
        except (ExternalEvidenceError, TypeError, ValueError) as exc:
            return self._settings_page_v2(
                sess, q={"section": ["integrations"]}, flash="Integration source rejected: " + str(exc))
        return self._settings_page_v2(
            sess, q={"section": ["integrations"]}, flash="External evidence source saved.")

    def _do_integration_source_state(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._send("forbidden", 403, "text/plain")
        enabled = str((form.get("enabled") or [""])[0]).lower() in {"1", "true", "yes", "on"}
        try:
            self.manager.external_evidence.set_enabled(
                (form.get("source_key") or [""])[0], enabled, actor=sess["username"])
        except ExternalEvidenceError as exc:
            return self._settings_page_v2(
                sess, q={"section": ["integrations"]}, flash="Integration state rejected: " + str(exc))
        return self._settings_page_v2(
            sess, q={"section": ["integrations"]}, flash="External evidence source state updated.")
