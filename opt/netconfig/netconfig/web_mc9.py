"""MC-9 Operations Correlation Console presentation mixin."""

import html
import urllib.parse

from .web_ui import _fmt_ts, _fmt_bps


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

    def _mc9_dashboard_page(self, sess):
        data = self.manager.operations_console.dashboard()
        cards = (
            '<div class="sensor-grid">'
            f'<div class="sensor-card {"warn" if data["active_incident_count"] else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Active incidents</div><div class="sensor-value">{data["active_incident_count"]}</div><div class="sensor-detail">open / investigating</div></div>'
            f'<div class="sensor-card {"warn" if data["impacted_services"] else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Services impacted</div><div class="sensor-value">{len(data["impacted_services"])}</div><div class="sensor-detail">evidence-backed entities</div></div>'
            f'<div class="sensor-card {"bad" if data["critical_alerts"] else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Critical alerts</div><div class="sensor-value">{len(data["critical_alerts"])}</div><div class="sensor-detail">open / acknowledged</div></div>'
            f'<div class="sensor-card {"warn" if data["degraded_connectors"] else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>External source health</div><div class="sensor-value">{len(data["degraded_connectors"])}</div><div class="sensor-detail">degraded / failed</div></div>'
            '</div>'
        )
        health = data.get("correlation_health") or {}
        corr = health.get("correlation") or {}
        bounds = health.get("bounds") or {}
        correlation_health_panel = (
            '<div class="panel"><h2>Correlation production health</h2>'
            '<p class="muted">MC-10 self-monitoring is read-only. Local checks do not replace deferred live PostgreSQL, AlmaLinux/systemd/SELinux, external-product, scale, clock-skew or HA qualification.</p>'
            '<div class="sensor-grid">'
            f'<div class="sensor-card {"bad" if corr.get("failed") or corr.get("non_deterministic") else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Correlation runs</div><div class="sensor-value">{int(corr.get("runs") or 0)}</div><div class="sensor-detail">last {int(health.get("window_seconds") or 0)}s</div></div>'
            f'<div class="sensor-card {"warn" if float((corr.get("latency_ms") or {}).get("p95") or 0) > 1000 else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>p95 latency</div><div class="sensor-value">{float((corr.get("latency_ms") or {}).get("p95") or 0):.1f} ms</div><div class="sensor-detail">bounded synchronous execution</div></div>'
            f'<div class="sensor-card {"warn" if int(corr.get("late_evidence") or 0) or int(corr.get("out_of_order") or 0) else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>Late / out-of-order</div><div class="sensor-value">{int(corr.get("late_evidence") or 0)} / {int(corr.get("out_of_order") or 0)}</div><div class="sensor-detail">evidence diagnostics, not failures</div></div>'
            f'<div class="sensor-card {"warn" if int(corr.get("queue_depth") or 0) else "ok"}"><div class="sensor-head"><span class="sensor-dot"></span>In flight / waiting</div><div class="sensor-value">{int(corr.get("inflight") or 0)} / {int(corr.get("queue_depth") or 0)}</div><div class="sensor-detail">lock wait bound {float(bounds.get("lock_wait_seconds") or 0):.1f}s</div></div>'
            '</div>'
            f'<p class="muted">Hard bounds: {int(bounds.get("max_facts_per_run") or 0)} facts/run · {int(bounds.get("max_hypotheses_per_run") or 0)} hypotheses/run · dependency depth {int(bounds.get("max_relationship_depth") or 0)} · replay range {int(bounds.get("max_replay_range_seconds") or 0)}s.</p>'
            '</div>'
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
        body = (self._correlation_workspace_tabs("dashboard") + cards + correlation_health_panel
                + '<div class="panel"><h2>Active incidents and current hypotheses</h2><p class="muted">Correlation is decision support only; causation and root cause remain unconfirmed.</p><div class="table-wrap"><table><tr><th>Incident</th><th>Title</th><th>Severity</th><th>Status</th><th>Current hypothesis</th><th>Confidence</th><th>Evidence-backed summary</th></tr>'
                + (''.join(incident_rows) or '<tr><td colspan=7 class=muted>No active incidents.</td></tr>') + '</table></div></div>'
                + '<div class="panel"><h2>Services impacted</h2><div class="table-wrap"><table><tr><th>Type</th><th>Service / entity</th><th>Key</th></tr>' + (service_rows or '<tr><td colspan=3 class=muted>No impacted service entity is established by active hypotheses.</td></tr>') + '</table></div></div>'
                + '<div class="panel"><h2>Recent changes correlated to active hypotheses</h2><div class="table-wrap"><table><tr><th>Incident</th><th>Hypothesis</th><th>Change evidence</th><th>Summary</th></tr>' + (change_rows or '<tr><td colspan=4 class=muted>No change evidence is currently used by an active hypothesis.</td></tr>') + '</table></div></div>'
                + '<div class="panel"><h2>Critical operational alerts</h2><div class="table-wrap"><table><tr><th>ID</th><th>Severity</th><th>Device</th><th>Event</th><th>Message</th></tr>' + (alert_rows or '<tr><td colspan=5 class=muted>No critical active alert.</td></tr>') + '</table></div></div>'
                + '<div class="panel"><h2>Unhealthy dependency evidence</h2><p class="muted">UNKNOWN and STALE are evidence states, not proof of service failure.</p><div class="table-wrap"><table><tr><th>Source</th><th>Relationship</th><th>Target</th><th>Console state</th><th>Evidence</th></tr>' + (dep_rows or '<tr><td colspan=5 class=muted>No stale, unknown, or inactive dependency evidence.</td></tr>') + '</table></div></div>'
                + '<div class="panel"><h2>External source health</h2><div class="table-wrap"><table><tr><th>Source</th><th>Type</th><th>Status</th><th>Auth</th><th>Last evidence</th></tr>' + (connector_rows or '<tr><td colspan=5 class=muted>No external sources configured.</td></tr>') + '</table></div></div>')
        return self._send(self._page("Operations Correlation Dashboard", body, sess))

    def _mc9_traffic_page(self, q, sess):
        def _num(name, default):
            try:
                return int((q.get(name) or [default])[0])
            except (TypeError, ValueError):
                return default
        window = _num("window", 3600); bucket = _num("bucket", 300)
        data = self.manager.operations_console.traffic(self.netflow, window_seconds=window, bucket_seconds=bucket)
        summary = data["summary"]
        cards = ('<div class="sensor-grid">'
                 f'<div class="sensor-card ok"><div class="sensor-head"><span class="sensor-dot"></span>Flow records</div><div class="sensor-value">{summary["flow_count"]}</div><div class="sensor-detail">bounded ring / selected window</div></div>'
                 f'<div class="sensor-card ok"><div class="sensor-head"><span class="sensor-dot"></span>Observed bytes</div><div class="sensor-value">{html.escape(_fmt_bps(summary["total_bytes"] * 8))}</div><div class="sensor-detail">bit-equivalent total, not sustained rate</div></div>'
                 f'<div class="sensor-card ok"><div class="sensor-head"><span class="sensor-dot"></span>Sources</div><div class="sensor-value">{summary["unique_sources"]}</div><div class="sensor-detail">unique observed IPs</div></div>'
                 f'<div class="sensor-card ok"><div class="sensor-head"><span class="sensor-dot"></span>Exporters</div><div class="sensor-value">{len(data["exporters"])}</div><div class="sensor-detail">with flows in this window</div></div></div>')
        filters = ('<div class="panel"><form method=get action="/traffic"><div class=row>'
                   f'<div><label>Window seconds</label><input name=window value="{data["window_seconds"]}"></div>'
                   f'<div><label>Trend bucket seconds</label><input name=bucket value="{data["bucket_seconds"]}"></div>'
                   '<div style="align-self:end"><button>Apply</button></div></div></form>'
                   '<p class=muted>Read-only analytics over the existing in-memory NetFlow ring. This is not a persistent flow warehouse and page rendering does not poll devices.</p></div>')
        def top_table(title, rows, endpoint=False):
            body=[]
            for x in rows:
                ep=x.get("endpoint") if endpoint else None
                attach=(ep or {}).get("attachment") or {}
                context=(f'{html.escape(ep.get("mac") or "")} · {html.escape(attach.get("device") or "")} {html.escape(attach.get("ifdescr") or "")}' if ep else '—')
                body.append(f'<tr><td>{html.escape(str(x.get("label") or ""))}</td><td>{x.get("bytes",0)}</td><td>{x.get("packets",0)}</td><td>{x.get("flows",0)}</td><td>{context}</td></tr>')
            return f'<div class="panel"><h2>{html.escape(title)}</h2><div class="table-wrap"><table><tr><th>Key</th><th>Bytes</th><th>Packets</th><th>Flows</th><th>Endpoint context</th></tr>{"".join(body) or "<tr><td colspan=5 class=muted>No data in selected window.</td></tr>"}</table></div></div>'
        exporter_rows=''.join(f'<tr><td>{html.escape(x["exporter"])}</td><td>{x["bytes"]}</td><td>{x["packets"]}</td><td>{x["flows"]}</td><td>{x["packet_datagrams"]}</td></tr>' for x in data["exporters"])
        trend_rows=''.join(f'<tr><td>{_fmt_ts(x["bucket_ts"])}</td><td>{x["bytes"]}</td><td>{x["packets"]}</td><td>{x["flows"]}</td></tr>' for x in data["trend"])
        raw=''.join(f'<tr><td>{_fmt_ts(x.get("ts"))}</td><td>{html.escape(x.get("exporter") or "")}</td><td>{html.escape(x.get("src") or "")}</td><td>{html.escape(x.get("dst") or "")}</td><td>{html.escape(x.get("proto") or "")}/{int(x.get("dport") or 0)}</td><td>{int(x.get("bytes") or 0)}</td></tr>' for x in data["raw_flows"][:100])
        body=(self._correlation_workspace_tabs("traffic")+filters+cards
              +top_table("Top sources",summary.get("top_sources") or [],True)
              +top_table("Top destinations",summary.get("top_destinations") or [],True)
              +top_table("Protocols",summary.get("protocols") or [])
              +top_table("Destination ports",summary.get("top_ports") or [])
              +top_table("Conversations",summary.get("conversations") or [])
              +f'<div class="panel"><h2>Exporters</h2><table><tr><th>Exporter</th><th>Bytes</th><th>Packets</th><th>Flows</th><th>Datagrams</th></tr>{exporter_rows or "<tr><td colspan=5 class=muted>No exporter data in selected window.</td></tr>"}</table></div>'
              +f'<div class="panel"><h2>Traffic trend</h2><table><tr><th>Bucket</th><th>Bytes</th><th>Packets</th><th>Flows</th></tr>{trend_rows or "<tr><td colspan=4 class=muted>No trend data.</td></tr>"}</table></div>'
              +f'<details class="panel"><summary><b>Advanced · raw flow records</b></summary><div class="table-wrap"><table><tr><th>Time</th><th>Exporter</th><th>Source</th><th>Destination</th><th>Protocol/port</th><th>Bytes</th></tr>{raw or "<tr><td colspan=6 class=muted>No raw flow records.</td></tr>"}</table></div></details>')
        return self._send(self._page("Traffic Analytics",body,sess))
