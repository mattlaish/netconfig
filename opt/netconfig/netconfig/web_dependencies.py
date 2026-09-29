"""MC-6 operator WebUI for the Service & Dependency Graph."""
from __future__ import annotations

import html
import urllib.parse

from .dependencies import EVIDENCE_STATES, ENTITY_TYPES, RELATIONSHIPS
from .users import can as _can


def _q(value):
    return urllib.parse.quote(str(value or ""), safe="")


def _badge(state):
    state = str(state or "UNKNOWN").upper()
    cls = "b-ok" if state in {"CONFIGURED", "DISCOVERED", "FRESH"} else ("b-warn" if state in {"INFERRED", "STALE"} else "b-dim")
    return f'<span class="badge {cls}">{html.escape(state)}</span>'


class WebDependenciesMixin:
    def _dependencies_page(self, q, sess):
        root = (q.get("root") or [""])[0]
        depth = max(0, min(int((q.get("depth") or ["4"])[0] or 4), 8))
        include_inferred = (q.get("include_inferred") or [""])[0] in {"1", "true", "yes", "on"}
        entities = self.manager.dependencies.entities(limit=500)
        all_edges = self.manager.dependencies.dependencies(limit=1000)
        graph = None
        error = ""
        if root:
            try:
                graph = self.manager.dependencies.graph(root, max_depth=depth, max_nodes=150,
                                                          include_inferred=include_inferred)
            except ValueError as exc:
                error = str(exc)

        options = ['<option value="">Select service entity</option>']
        for item in entities:
            selected = " selected" if item["entity_key"] == root else ""
            options.append(f'<option value="{html.escape(item["entity_key"])}"{selected}>{html.escape(item["name"])} · {html.escape(item["entity_type"])}</option>')
        checked = " checked" if include_inferred else ""
        inner = [
            '<div class="panel"><h2>Service &amp; Dependency Graph</h2>',
            '<p class="muted">MC-6 uses explicit configured/discovered evidence. INFERRED candidates require opt-in; UNKNOWN means insufficient evidence and is never traversed. Rendering reads persisted evidence only and performs no device polling.</p>',
            '<form method=get action="/dependencies"><div class=row>',
            f'<div><label>Root entity</label><select name=root>{"".join(options)}</select></div>',
            f'<div><label>Traversal depth</label><input name=depth type=number min=0 max=8 value="{depth}"></div>',
            f'<div><label>&nbsp;</label><label style="font-weight:400"><input type=checkbox name=include_inferred value=1{checked}> include INFERRED candidates</label></div>',
            '<div style="flex:0"><label>&nbsp;</label><button>View graph</button></div></div></form></div>'
        ]
        if error:
            inner.append(f'<div class="err">{html.escape(error)}</div>')
        if graph:
            summary = graph["summary"]
            inner.append('<div class="panel"><h2>Dependency traversal</h2>')
            inner.append(f'<p><b>{summary["nodes"]}</b> nodes · <b>{summary["edges"]}</b> evidence edges · <b>{summary["cycle_edges"]}</b> cycle edge(s)</p>')
            if graph.get("truncated"):
                inner.append(f'<div class="warn">Traversal bounded at {html.escape(graph.get("truncation_reason") or "limit")}.</div>')
            chain = []
            for node in graph["nodes"]:
                chain.append(f'<div style="margin-left:{min(int(node["depth"]),8)*22}px"><span class="muted">{"↳ " if node["depth"] else ""}</span><b>{html.escape(node["name"])}</b> <span class="badge b-dim">{html.escape(node["entity_type"])}</span></div>')
            inner.append('<div style="margin:12px 0">' + ''.join(chain) + '</div>')
            rows = []
            for edge in graph["edges"]:
                status = _badge(edge["evidence_state"]) + ' ' + _badge(edge["freshness"])
                traversal = 'yes' if edge.get("traversed") else html.escape(edge.get("exclusion_reason") or 'no')
                scope = ''
                if edge.get("vrf") or edge.get("destination_prefix"):
                    scope = f'{html.escape(edge.get("vrf") or "default")} · {html.escape(edge.get("destination_prefix") or "")}'
                rows.append(f'<tr><td><code>{html.escape(edge["source_key"])}</code></td><td>{html.escape(edge["relationship"])}</td><td><code>{html.escape(edge["target_key"])}</code></td><td>{status}</td><td>{html.escape(edge["provenance"])}</td><td>{html.escape(edge.get("evidence_ref") or "—")}</td><td>{scope or "—"}</td><td>{traversal}</td></tr>')
            inner.append('<div class="table-wrap"><table><tr><th>Source</th><th>Relationship</th><th>Target</th><th>Evidence</th><th>Provenance</th><th>Reference</th><th>Network scope</th><th>Traversed</th></tr>' + (''.join(rows) or '<tr><td colspan=8 class=muted>No outgoing dependency evidence.</td></tr>') + '</table></div></div>')

            src = (q.get("source_device") or [""])[0]
            prefix = (q.get("destination_prefix") or [""])[0]
            vrf = (q.get("vrf") or ["default"])[0] or "default"
            overlay = None
            if src and prefix:
                try:
                    overlay = self.manager.dependencies.network_overlay(root, src, vrf, prefix)
                except ValueError as exc:
                    inner.append(f'<div class="err">Network overlay: {html.escape(str(exc))}</div>')
            devices = self.manager.inv.all()
            dopts = ['<option value="">Select managed device</option>'] + [f'<option value="{html.escape(d["name"])}"{" selected" if d["name"]==src else ""}>{html.escape(d["name"])}</option>' for d in devices]
            inner.append('<div class="panel"><h2>Network path overlay</h2><p class="muted">Uses persisted NI-7 route evidence only. VRF scope is preserved; ambiguous paths fail closed; next-hop IP alone never creates a managed node.</p><form method=get action="/dependencies">'
                         f'<input type=hidden name=root value="{html.escape(root)}"><input type=hidden name=depth value="{depth}">'
                         f'<div class=row><div><label>Source device</label><select name=source_device>{"".join(dopts)}</select></div><div><label>VRF</label><input name=vrf value="{html.escape(vrf)}"></div><div><label>Destination prefix</label><input name=destination_prefix value="{html.escape(prefix)}" placeholder="10.20.0.0/16"></div><div style="flex:0"><label>&nbsp;</label><button>Overlay path</button></div></div></form>')
            if overlay:
                p = overlay["path"]
                inner.append(f'<p>Status {_badge(p["status"])} · {html.escape(p["stop_reason"])}</p>')
                hops = ''.join(f'<tr><td>{h["depth"]}</td><td>{html.escape(h["device"])}</td><td>{html.escape(h.get("outgoing_interface") or "—")}</td><td>{html.escape(h.get("next_device") or "—")}</td><td>{html.escape(h.get("next_hop") or "—")}</td></tr>' for h in p["hops"])
                inner.append('<div class="table-wrap"><table><tr><th>Hop</th><th>Managed device</th><th>Interface</th><th>Explicit next device</th><th>Next-hop IP (evidence only)</th></tr>' + (hops or '<tr><td colspan=5 class=muted>No resolved hops.</td></tr>') + '</table></div>')
            inner.append('</div>')

        rows = []
        for edge in all_edges:
            rows.append(f'<tr><td><code>{html.escape(edge["source_key"])}</code></td><td>{html.escape(edge["relationship"])}</td><td><code>{html.escape(edge["target_key"])}</code></td><td>{_badge(edge["evidence_state"])} {_badge(edge["freshness"])}</td><td>{html.escape(edge["provenance"])}</td></tr>')
        inner.append('<div class="panel"><h2>Dependency evidence inventory</h2><div class="table-wrap"><table><tr><th>Source</th><th>Relationship</th><th>Target</th><th>State</th><th>Provenance</th></tr>' + (''.join(rows) or '<tr><td colspan=5 class=muted>No dependency evidence configured.</td></tr>') + '</table></div></div>')

        if _can(sess["role"], "manage_dependencies"):
            types = ''.join(f'<option>{x}</option>' for x in ENTITY_TYPES)
            rels = ''.join(f'<option>{x}</option>' for x in RELATIONSHIPS)
            states = ''.join(f'<option>{x}</option>' for x in EVIDENCE_STATES)
            entity_opts = ''.join(f'<option value="{html.escape(e["entity_key"])}">{html.escape(e["name"])} · {html.escape(e["entity_key"])}</option>' for e in entities)
            inner.append(f'''<div class="panel"><h2>Configure dependency model</h2><p class="muted">This changes NetConfig's dependency inventory only; it does not configure network/application infrastructure.</p>
<div class=row><form method=post action="/dependency-entity-save" style="flex:1">{self._csrf_field()}<h3>Entity</h3><label>Stable key</label><input name=entity_key required placeholder="service:payment-api"><label>Type</label><select name=entity_type>{types}</select><label>Name</label><input name=name required><label>Description</label><input name=description><button style="margin-top:10px">Save entity</button></form>
<form method=post action="/dependency-edge-save" style="flex:1">{self._csrf_field()}<h3>Dependency evidence</h3><label>Source</label><select name=source_key>{entity_opts}</select><label>Relationship</label><select name=relationship>{rels}</select><label>Target</label><select name=target_key>{entity_opts}</select><label>Evidence state</label><select name=evidence_state>{states}</select><label>Provenance</label><input name=provenance required placeholder="operator / CMDB / discovery"><label>Evidence reference</label><input name=evidence_ref placeholder="ticket:123 / lldp:42"><label>Freshness max age (s)</label><input name=max_age_seconds type=number min=60 placeholder="3600"><button style="margin-top:10px">Save dependency</button></form></div></div>''')
        self._send(self._page("Dependencies", ''.join(inner), sess))

    def _do_dependency_entity_save(self, form, sess):
        if not _can(sess["role"], "manage_dependencies"):
            return self._send("forbidden", 403, "text/plain")
        try:
            item = self.manager.dependencies.put_entity(
                (form.get("entity_key") or [""])[0], (form.get("entity_type") or [""])[0],
                (form.get("name") or [""])[0], description=(form.get("description") or [""])[0],
                actor=sess["username"])
        except ValueError as exc:
            return self._send(self._page("Dependencies", f'<div class="err">{html.escape(str(exc))}</div>', sess), 400)
        return self._redirect('/dependencies?root=' + _q(item["entity_key"]))

    def _do_dependency_edge_save(self, form, sess):
        if not _can(sess["role"], "manage_dependencies"):
            return self._send("forbidden", 403, "text/plain")
        raw_age = (form.get("max_age_seconds") or [""])[0]
        try:
            item = self.manager.dependencies.put_dependency(
                (form.get("source_key") or [""])[0], (form.get("target_key") or [""])[0],
                (form.get("relationship") or [""])[0],
                evidence_state=(form.get("evidence_state") or [""])[0],
                provenance=(form.get("provenance") or [""])[0],
                evidence_ref=(form.get("evidence_ref") or [""])[0],
                max_age_seconds=None if not raw_age else int(raw_age), actor=sess["username"])
        except (ValueError, TypeError) as exc:
            return self._send(self._page("Dependencies", f'<div class="err">{html.escape(str(exc))}</div>', sess), 400)
        return self._redirect('/dependencies?root=' + _q(item["source_key"]))
