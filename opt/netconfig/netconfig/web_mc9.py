"""MC-9 Operations Correlation Console presentation mixin."""

import html
import time
import urllib.parse

from .web_ui import _fmt_ts


def _q(value):
    return urllib.parse.quote(str(value or ""), safe="")


def _badge(value):
    value = str(value or "UNKNOWN").upper()
    css = "b-ok" if value in {"CONNECTED", "CONFIGURED", "OK", "FRESH"} else ("b-bad" if value in {"CRITICAL", "FAILED", "STALE", "UNKNOWN", "DEGRADED"} else "b-chg")
    return f'<span class="badge {css}">{html.escape(value)}</span>'


class WebMC9Mixin:
    @staticmethod
    def _correlation_workspace_tabs(current):
        items = [
            ("dashboard", "/dashboard", "Dashboard"),
            ("alerts", "/alerts?view=active", "Active Alerts"),
            ("events", "/events", "Events"),
            ("incidents", "/incidents", "Incidents"),
            ("maintenance", "/alerts?view=maintenance", "Maintenance"),
            ("traffic", "/traffic", "Traffic Analytics"),
        ]
        return '<div class="tabs">' + ''.join(
            f'<a class="tab {"active" if current == key else ""}" href="{href}">{label}</a>'
            for key, href, label in items) + '</div>'

    def _network_glance(self, data):
        """Network-first summary: device reachability, config changes, compliance,
        approvals, alerts and traffic. Reads saved records only."""
        m = self.manager
        now = time.time()
        devices = m.inv.all()
        facts = m.inv.all_facts()
        polled = [d for d in devices if d.get("snmp_version")]
        # Only recent polls count; an old "reachable" result is not current status.
        interval = int(m.settings.get("snmp_poll_interval") or 0)
        max_age = max(3 * interval, 3600) if interval > 0 else 86400

        def recent(name):
            fx = facts.get(name) or {}
            try:
                return fx if now - float(fx.get("last_polled") or 0) <= max_age else None
            except (TypeError, ValueError):
                return None
        down = [d for d in polled if recent(d["name"]) and not recent(d["name"]).get("reachable")]
        up = sum(1 for d in polled if (recent(d["name"]) or {}).get("reachable"))
        not_polled = len(polled) - up - len(down)
        runs = m.inv.recent_runs(500)
        day = [r for r in runs if float(r.get("ts") or 0) >= now - 86400]
        changes = [r for r in day if r.get("changed")]
        failed = [r for r in day if not r.get("ok")]
        try:
            pending = self.wf.pending()
        except Exception:
            pending = []
        comp = m.db.conn.execute("SELECT * FROM compliance_runs ORDER BY ts DESC LIMIT 1").fetchone()
        comp = dict(comp) if comp else None
        from .web_ux import drift_flags
        drifted = []
        for d in devices[:500]:
            try:
                if drift_flags(m.store, d["name"]).get("drifted"):
                    drifted.append(d["name"])
            except Exception:
                pass
        critical = data.get("critical_alerts") or []

        def _span(seconds):
            return f"{seconds // 3600} h" if seconds >= 3600 else f"{seconds // 60} min"

        def card(state, title, value, detail):
            return (f'<div class="sensor-card {state}"><div class="sensor-head"><span class="sensor-dot"></span>{html.escape(title)}</div>'
                    f'<div class="sensor-value">{value}</div><div class="sensor-detail">{detail}</div></div>')
        cards = ('<div class="sensor-grid dash-kpis">'
                 + card("bad" if down else ("ok" if polled else "dim"), "Devices reachable",
                        f'{up} / {len(polled)}' if polled else f'{len(devices)}',
                        (f'{len(down)} unreachable · {not_polled} not polled in the last {_span(max_age)}' if polled
                         else '<a href="/">no SNMP polling configured</a>'))
                 + card("warn" if changes else "ok", "Config changes (24 h)", len(changes),
                        f'<a href="/runs">{len(failed)} failed collection(s)</a>')
                 + card("bad" if comp and comp.get("failed") else ("ok" if comp else "dim"), "Compliance",
                        (f'{int(comp["failed"])} failed' if comp else "—"),
                        (f'<a href="/compliance">{int(comp.get("passed") or 0)} passed · {_fmt_ts(comp.get("ts"))}</a>' if comp
                         else '<a href="/compliance">not run yet</a>'))
                 + card("warn" if pending else "ok", "Waiting for approval", len(pending),
                        '<a href="/requests">change requests</a>')
                 + card("bad" if critical else ("warn" if data.get("active_incident_count") else "ok"),
                        "Critical alerts", len(critical),
                        f'<a href="/alerts?view=active">open alerts</a> · '
                        f'<a href="/incidents">{int(data.get("active_incident_count") or 0)} active incident(s)</a>')
                 + '</div>')
        items = []
        for d in down[:10]:
            items.append(f'<li><span class="badge b-bad">unreachable</span> <a href="/snmp?device={_q(d["name"])}">{html.escape(d["name"])}</a> '
                         f'<span class="muted">{html.escape((facts.get(d["name"]) or {}).get("error") or "did not answer the last SNMP poll")}</span></li>')
        for r in pending[:10]:
            items.append(f'<li><span class="badge b-chg">approval</span> <a href="/request?id={_q(r.get("id"))}">{html.escape(r.get("title") or "Change request")}</a> '
                         f'<span class="muted">requested by {html.escape(r.get("requested_by") or "")} · {_fmt_ts(r.get("requested_ts"))}</span></li>')
        for a in critical[:10]:
            items.append(f'<li><span class="badge b-bad">critical</span> <a href="/alerts?view=active">{html.escape(a.get("message") or a.get("event_type") or "alert")}</a> '
                         f'<span class="muted">{html.escape(a.get("device") or "")}</span></li>')
        for name in drifted[:10]:
            items.append(f'<li><span class="badge b-chg">drift</span> <a href="/device?name={_q(name)}#tab-config">{html.escape(name)}</a> '
                         '<span class="muted">configuration differs from its baseline</span></li>')
        for r in failed[:10]:
            items.append(f'<li><span class="badge b-bad">failed</span> <a href="/device?name={_q(r.get("device"))}">{html.escape(r.get("device") or "")}</a> '
                         f'<span class="muted">{html.escape((r.get("message") or "")[:160])} · {_fmt_ts(r.get("ts"))}</span></li>')
        attention = ('<div class="panel"><h2>Needs attention</h2>'
                     + (f'<ul class="attention">{"".join(items)}</ul>' if items else
                        '<p><span class="badge b-ok">all clear</span> Nothing needs attention right now.</p>')
                     + '</div>')
        change_rows = "".join(
            f'<tr><td class=muted>{_fmt_ts(r.get("ts"))}</td><td><a href="/device?name={_q(r.get("device"))}#tab-config">{html.escape(r.get("device") or "")}</a></td>'
            f'<td class=muted>{html.escape((r.get("message") or "")[:160])}</td></tr>' for r in changes[:8])
        recent = ('<div class="panel"><h2>Recent configuration changes</h2>'
                  + (f'<table><tr><th>Time</th><th>Device</th><th>Detail</th></tr>{change_rows}</table>' if change_rows
                     else '<p class="muted">No configuration changes were collected in the last 24 hours.</p>')
                  + '<p><a href="/runs">Open the run log</a></p></div>')
        traffic = ""
        if m.settings.get("netflow_enabled") and getattr(self, "netflow", None) is not None:
            try:
                from .web_traffic import fmt_bytes
                t = m.operations_console.traffic(self.netflow, window_seconds=3600, bucket_seconds=300, view_limit=5)
                rows = t["analysis"]["sources"][:5]
                ids = t["analysis"].get("identities") or {}
                body = "".join(
                    f'<tr><td><a href="/traffic?view=destinations&q={_q(r["ip"])}">{html.escape(r["ip"])}</a></td>'
                    f'<td>{html.escape((ids.get(r["ip"]) or {}).get("device") or (ids.get(r["ip"]) or {}).get("name") or "")}</td>'
                    f'<td>{html.escape(fmt_bytes(r["bytes"]))}</td><td>{html.escape(", ".join(r["services"][:2]))}</td></tr>'
                    for r in rows)
                traffic = ('<div class="panel"><h2>Top traffic · last hour</h2>'
                           + (f'<table><tr><th>Local host</th><th>Device</th><th>Bytes</th><th>Top services</th></tr>{body}</table>'
                              if body else '<p class="muted">No flow records in the last hour.</p>')
                           + '<p><a href="/traffic">Open Traffic Analytics</a></p></div>')
            except Exception:
                traffic = ""
        return cards + '<div class="row">' + f'<div>{attention}</div><div>{recent}{traffic}</div></div>'

    def _mc9_dashboard_page(self, sess):
        data = self.manager.operations_console.dashboard()
        health = data.get("correlation_health") or {}
        corr = health.get("correlation") or {}
        bounds = health.get("bounds") or {}
        correlation_health_panel = (
            '<details class="panel"><summary><b>Analysis service health</b></summary>'
            '<p class="muted">Shows recent analysis activity and service limits. Viewing this page does not run checks or change devices.</p>'
            '<div class="sensor-grid">'
            f'<div class="sensor-card {"bad" if corr.get("failed") or corr.get("non_deterministic") else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Correlation runs</div><div class="sensor-value">{int(corr.get("runs") or 0)}</div><div class="sensor-detail">last {int(health.get("window_seconds") or 0)}s</div></div>'
            f'<div class="sensor-card {"warn" if float((corr.get("latency_ms") or {}).get("p95") or 0) > 1000 else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>95th-percentile analysis time</div><div class="sensor-value">{float((corr.get("latency_ms") or {}).get("p95") or 0):.1f} ms</div><div class="sensor-detail">95% of runs finish within this time</div></div>'
            f'<div class="sensor-card {"warn" if int(corr.get("late_evidence") or 0) or int(corr.get("out_of_order") or 0) else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Late / out-of-order</div><div class="sensor-value">{int(corr.get("late_evidence") or 0)} / {int(corr.get("out_of_order") or 0)}</div><div class="sensor-detail">late or reordered records, not device failures</div></div>'
            f'<div class="sensor-card {"warn" if int(corr.get("queue_depth") or 0) else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>In flight / waiting</div><div class="sensor-value">{int(corr.get("inflight") or 0)} / {int(corr.get("queue_depth") or 0)}</div><div class="sensor-detail">maximum wait {float(bounds.get("lock_wait_seconds") or 0):.1f}s</div></div>'
            '</div>'
            f'<p class="muted">Analysis limits: {int(bounds.get("max_facts_per_run") or 0)} facts/run · {int(bounds.get("max_hypotheses_per_run") or 0)} hypotheses/run · dependency depth {int(bounds.get("max_relationship_depth") or 0)} · replay range {int(bounds.get("max_replay_range_seconds") or 0)}s.</p>'
            '</details>'
        )
        incident_rows = []
        for row in data["active_incidents"]:
            inc = row["incident"]; hyp = row.get("current_hypothesis") or {}
            incident_rows.append(
                f'<tr><td><a href="/incident?ref={_q(inc["incident_key"])}"><b>{html.escape(inc["incident_key"])}</b></a> · <a href="/operations?tab=workflow&incident={_q(inc["incident_key"])}">journey</a></td>'
                f'<td>{html.escape(inc.get("title") or "")}</td><td>{html.escape(inc.get("severity") or "")}</td><td>{html.escape(inc.get("status") or "")}</td>'
                f'<td>{html.escape(hyp.get("hypothesis_type") or "No current hypothesis")}</td>'
                f'<td>{int(hyp.get("confidence") or 0)}%</td><td>{html.escape(hyp.get("summary") or "Evidence has not produced an active hypothesis.")}</td></tr>')
        service_rows = ''.join(
            f'<tr><td>{html.escape(x.get("entity_type") or "")}</td><td>{html.escape(x.get("name") or x.get("entity_key") or "")}</td><td><code>{html.escape(x.get("entity_key") or "")}</code></td></tr>'
            for x in data["impacted_services"])
        change_rows = ''.join(
            f'<tr><td><a href="/incident?ref={_q(x["incident"])}">{html.escape(x["incident"])}</a></td><td>{html.escape(x["hypothesis_type"])}</td><td><code>{html.escape(x["source_ref"])}</code></td><td>{html.escape(x["summary"])}</td></tr>'
            for x in data["correlated_changes"])
        dep_rows = ''.join(
            f'<tr><td>{html.escape(x.get("source_key") or "")}</td><td>{html.escape(x.get("relationship") or "")}</td><td>{html.escape(x.get("target_key") or "")}</td><td>{_badge(x.get("console_state"))}</td><td>{html.escape(x.get("evidence_state") or "")}</td></tr>'
            for x in data["unhealthy_dependencies"][:100])
        connector_rows = ''.join(
            f'<tr><td>{html.escape(x.get("display_name") or x.get("source_key") or "")}</td><td>{html.escape(x.get("source_type") or "")}</td><td>{_badge(x.get("status"))}</td><td>{_badge(x.get("auth_state"))}</td><td>{_fmt_ts(x.get("last_event_ts"))}</td></tr>'
            for x in data["connectors"])
        alert_rows = ''.join(
            f'<tr><td>#{x.get("id")}</td><td>{html.escape(x.get("severity") or "")}</td><td>{html.escape(x.get("device") or "-")}</td><td>{html.escape(x.get("event_type") or "")}</td><td>{html.escape(x.get("message") or "")}</td></tr>'
            for x in data["critical_alerts"][:50])

        def section(title, head, rows, note=""):
            if not rows:
                return ""
            return (f'<div class="panel"><h2>{title}</h2>{note}<div class="table-wrap"><table><tr>'
                    + "".join(f"<th>{h}</th>" for h in head) + f'</tr>{rows}</table></div></div>')
        sections = (
            section("Active incidents and current hypotheses",
                    ("Incident", "Title", "Severity", "Status", "Current hypothesis", "Confidence", "Evidence-backed summary"),
                    "".join(incident_rows), '<p class="muted">Correlation is decision support only; causation and root cause remain unconfirmed.</p>')
            + section("Services impacted", ("Type", "Service / entity", "Key"), service_rows)
            + section("Recent changes correlated to active hypotheses", ("Incident", "Hypothesis", "Change evidence", "Summary"), change_rows)
            + section("Critical operational alerts", ("ID", "Severity", "Device", "Event", "Message"), alert_rows)
            + section("Unhealthy dependency evidence", ("Source", "Relationship", "Target", "Console state", "Evidence"), dep_rows,
                      '<p class="muted">UNKNOWN and STALE are evidence states, not proof of service failure.</p>')
            + section("External source health", ("Source", "Type", "Status", "Auth", "Last evidence"), connector_rows))
        if not sections:
            sections = ('<div class="panel"><h2>Incidents &amp; correlation</h2><p class="muted">No active incidents, '
                        'impacted services, unhealthy dependencies or external sources to show. '
                        '<a href="/incidents">Open incidents</a></p></div>')
        body = (self._correlation_workspace_tabs("dashboard") + self._network_glance(data) + sections
                + correlation_health_panel)
        return self._send(self._page("Dashboard", body, sess))

    def _mc9_traffic_page(self, q, sess):
        from .web_traffic import render_traffic_body
        body = self._correlation_workspace_tabs("traffic") + render_traffic_body(self, q)
        return self._send(self._page("Traffic Analytics", body, sess))
