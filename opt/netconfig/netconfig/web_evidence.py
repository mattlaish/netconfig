"""Read-only operator explanations for MAC locations, route learning and measurements."""
import csv
import html
import io
import math
import time
import urllib.parse

from .users import can
from .network_intelligence import normalize_mac, _port_keys


def e(value):
    return html.escape(str(value if value is not None else ""))


def _csv_cell(value):
    text = str(value if value is not None else "").replace("\x00", "")
    # Quoting alone does not prevent spreadsheet formula evaluation.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        text = "'" + text
    return text


def endpoints_csv(endpoints):
    """Export the existing filtered evidence, never infer a physical attachment.

    One row per IP (or a blank IP for MAC-only evidence); extra locations stay
    separate from the single likely location, so ambiguity is not lost in Excel.
    """
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["IP", "MAC", "Likely switch", "Likely port", "VLAN", "Result", "Confidence",
                     "Direct connection proven", "IP mapping fresh", "Candidate locations",
                     "Transit observations", "Outdated observations"])
    for endpoint in endpoints:
        status = endpoint.get("status") or "UNRESOLVED"
        location = ((endpoint.get("attachment") or endpoint.get("observed_location") or {})
                    if status in {"CANDIDATE", "ATTACHED"} else {})
        port = location.get("ifdescr") or location.get("ifindex") or location.get("bridge_port") or ""
        observations = (endpoint.get("evidence_chain") or {}).get("fdb_candidates") or []
        groups = {"candidate": set(), "transit": set(), "outdated": set()}
        for observation in observations:
            observed_port = (observation.get("ifdescr") or observation.get("ifindex")
                             or observation.get("bridge_port") or "?")
            label = f'{observation.get("device") or "?"}: {observed_port}'
            if observation.get("vlan_id"):
                label += f' (VLAN {observation["vlan_id"]})'
            group = ("outdated" if not observation.get("fresh")
                     else "transit" if observation.get("transit") else "candidate")
            groups[group].add(label)
        freshness = endpoint.get("ip_mapping_fresh")
        values = [endpoint.get("mac", ""), location.get("device", ""), port, location.get("vlan_id", ""),
                  status, endpoint.get("confidence", "NONE"),
                  "Yes" if endpoint.get("direct_connection_proven") else "No",
                  "Unknown" if freshness is None else "Yes" if freshness else "No",
                  *["; ".join(sorted(groups[group])) for group in ("candidate", "transit", "outdated")]]
        ips = list(dict.fromkeys((endpoint.get("ipv4") or []) + (endpoint.get("ipv6") or []))) or [""]
        for ip in ips:
            writer.writerow([_csv_cell(value) for value in [ip, *values]])
    return "\ufeff" + stream.getvalue()


def mac_observation(endpoint, device, entry):
    ports = _port_keys({**entry, "bridge_port": entry.get("port", "")})
    matches = [r for r in (endpoint.get("evidence_chain") or {}).get("fdb_candidates", [])
               if r.get("device") == device and ports & _port_keys(r)]
    if not matches:
        return "Observed; location not classified"
    fresh = [r for r in matches if r.get("fresh")]
    if not fresh:
        return "Outdated observation"
    if any(r.get("transit") for r in fresh):
        return "Forwarded via known neighbor"
    if endpoint.get("status") == "AMBIGUOUS":
        return "Multiple possible locations"
    return "Candidate location; not proven direct"


def mac_port_section(handler, dev):
    m = handler.manager
    macs = m.db.get_mac_table(dev["name"])
    arp = m.db.get_arp(dev["name"])
    endpoints = {r["mac"]: r for r in m.endpoint_inventory(device=dev["name"])}
    arp_by_mac = {normalize_mac(a["mac"]): a["ip"] for a in arp}
    rows = []
    for entry in macs:
        mac = normalize_mac(entry["mac"])
        endpoint = endpoints.get(mac, {})
        ips = list(endpoint.get("ipv4") or []) + list(endpoint.get("ipv6") or [])
        ip = ", ".join(ips) or arp_by_mac.get(mac, "")
        port = entry.get("ifdescr") or (f'if{entry["ifindex"]}' if entry.get("ifindex") else entry.get("port"))
        kind = mac_observation(endpoint, dev["name"], entry)
        rows.append(f'<tr><td><code>{e(entry["mac"])}</code></td><td>{e(port)}</td><td>{e(ip)}</td><td>{e(kind)}</td></tr>')
    table = ('<div class="table-wrap"><table><tr><th>MAC address</th><th>Observed port</th><th>IP (ARP / neighbor evidence)</th><th>Location evidence</th></tr>'
             + ''.join(rows) + '</table></div>') if rows else '<p class="muted">No forwarding entries collected. Poll this network device over SNMP to collect its MAC table.</p>'
    return ('<div class="panel"><h2>MAC address → port</h2><p class="muted">'
            + str(len(macs)) + ' learned MAC entries. A forwarding table shows where a MAC was observed, not whether the endpoint is physically plugged into that port. '
            'An unmanaged switch or bridge may be hidden downstream. Neighbor-facing observations are shown separately; no direct connection is asserted.</p>'
            + table + '<p><a href="/endpoints?' + e(urllib.parse.urlencode({"device": dev["name"]})) + '">Review all location candidates and evidence</a></p></div>')


def route_learning_panel(handler, sess, *, device=None, summary=None, include_stale=False):
    from .web_ui import _fmt_ts
    m = handler.manager
    states = [m.l3_collection_status(device)] if device else m.l3_collection_status()
    rows = []
    for state in states:
        name = state["device"]
        label = state.get("display_status") or state.get("status") or "UNKNOWN"
        cls = "b-ok" if label == "OK" else "b-bad" if label == "ERROR" else "b-chg" if label == "STALE" else "b-dim"
        action = ''
        if state.get("route_collection_available", state.get("supports_cli_collection")) and can(sess["role"], "collect"):
            action = (f'<form method="post" action="/collect">{handler._csrf_field()}'
                      f'<input type="hidden" name="name" value="{e(name)}"><input type="hidden" name="back" value="{"device-routes" if device else "routes"}">'
                      '<button>Collect config + routes</button></form>')
        reason = state.get("error") or state.get("action_hint") or ""
        rows.append(f'<tr><td><a href="/device?name={urllib.parse.quote(name, safe="")}">{e(name)}</a></td>'
                    f'<td><span class="badge {cls}">{e(label.replace("_", " ").capitalize())}</span></td>'
                    f'<td>{e(state.get("platform"))}</td><td>{int(state.get("interface_count") or 0)}</td><td>{int(state.get("route_count") or 0)}</td>'
                    f'<td>{_fmt_ts(state.get("observed_ts"))}</td><td>{e(reason)}</td><td>{action}</td></tr>')
    stale = int((summary or {}).get("stale_routes_excluded") or 0)
    warning = (f'<p class="err">{stale} outdated route observation(s) are hidden; they were not deleted. '
               '<a href="/topology?view=l3&amp;include_stale=1">Show outdated route evidence</a> or collect again.</p>') if stale and not include_stale else ''
    locked = ''
    if not m.vault_ready() and can(sess["role"], "unlock_vault"):
        locked = '<p class="err">Vault locked. <a href="/vault?next=%2Ftopology%3Fview%3Dl3">Unlock and return to routing topology</a> before collecting.</p>'
    return ('<div class="panel" id="route-learning"><h3>Route learning status</h3>'
            '<p>Normal CLI configuration collection also reads routes and interface IP addresses on supported Network devices. SNMP Poll and opening this page do not refresh routes. '
            'Route observations become outdated after one hour; old data is never silently presented as current.</p>' + locked + warning
            + '<div class="table-wrap"><table><tr><th>Device</th><th>Collection status</th><th>Platform</th><th>Interfaces</th><th>Routes</th><th>Last successful collection</th><th>What to do / error</th><th></th></tr>'
            + (''.join(rows) or '<tr><td colspan="8">No Network devices configured. Add a supported router, switch or firewall first.</td></tr>')
            + '</table></div><p><a href="/topology?view=l3">Open routing topology (Layer 3)</a> · <a href="/topology?view=combined">Open physical + routing view</a></p></div>')


_TELEMETRY_NAMES = {
    "cpu": "CPU usage", "memory": "Memory usage",
    "processor_cpu": "Processor CPU usage", "vdom_cpu": "Virtual-domain CPU usage",
    "vdom_memory": "Virtual-domain memory usage", "vdom_sessions": "Virtual-domain sessions",
    "sessions": "Sessions", "session_rate": "Session rate", "vpn_up": "VPN up",
    "vpn_tunnel": "VPN tunnel", "security_db": "Security database", "firmware": "Firmware",
}
_STATUS_RANK = {"UNKNOWN": 0, "OK": 1, "WARNING": 2, "CRITICAL": 3}


def _number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _measurement_kind(item):
    return str(item.get("sensor_type") or "").rsplit(".", 1)[-1]


def _measurement_name(item):
    kind = _measurement_kind(item)
    return _TELEMETRY_NAMES.get(kind, kind.replace("_", " ").title() or "Measurement")


def _chart_group(item):
    """Return (stable key, title, display unit) for useful numeric telemetry."""
    kind = _measurement_kind(item)
    resource = str(item.get("resource") or "")
    resource_lower = resource.lower()
    if kind in {"cpu", "processor_cpu", "vdom_cpu"}:
        return "cpu", "CPU usage", "%"
    if kind in {"memory", "vdom_memory"}:
        return "memory", "Memory usage", "%"
    if kind in {"sessions", "vdom_sessions"}:
        return "sessions", "Sessions", "sessions"
    if kind == "session_rate":
        return "session-rate", "Session rate", str(item.get("unit") or "sessions/s")
    if kind == "vpn_up":
        return "vpn-up", "VPN tunnels up", str(item.get("unit") or "tunnels")
    if kind == "vpn_tunnel":
        return "vpn-tunnel", "VPN tunnel status", "state"
    if ("disk" in kind or "filesystem" in kind or "storage_usage" in kind
            or any(word in resource_lower for word in ("disk usage", "filesystem usage"))):
        return "disk", "Disk usage", str(item.get("unit") or "%")
    if kind == "hardware" and "temperature" in resource_lower:
        return "temperature", "Hardware temperature", "°C"
    if kind == "hardware" and ("fan" in resource_lower or "speed" in resource_lower):
        return "fan-speed", "Fan speed", "RPM"
    if (_number(item.get("value")) is not None
            and (str(item.get("unit") or "").strip() or str(item.get("threshold") or "").strip())):
        sensor_type = str(item.get("sensor_type") or "measurement")
        return "metric-" + sensor_type, _measurement_name(item), str(item.get("unit") or "")
    return None


def _chart_value(item, value):
    if _measurement_kind(item) == "vpn_tunnel":
        state = str(value or "").strip().lower()
        if state == "up":
            return 1.0
        if state == "down":
            return 0.0
        return None
    return _number(value)


def _series_label(item):
    kind = _measurement_kind(item)
    resource = str(item.get("resource") or "").strip()
    if kind in {"cpu", "memory", "sessions"}:
        return "Overall"
    if kind.startswith("vdom_"):
        return f"VDOM {resource or 'default'}"
    if resource:
        return resource
    return _measurement_name(item)


def _status_class(status):
    return {"OK": "ok", "WARNING": "warn", "CRITICAL": "bad"}.get(
        str(status or "UNKNOWN").upper(), "dim")


def _history_for_chart_sensors(manager, device, sensors, selected="", limit=60):
    from .sensor import SensorEngine
    keyed = {}
    for item in sensors:
        key = SensorEngine.sensor_key(item["sensor_type"], device, item.get("resource") or "")
        keyed[key] = item
    wanted = [key for key, item in keyed.items() if _chart_group(item)]
    if selected and selected in keyed and selected not in wanted:
        wanted.append(selected)
    if hasattr(manager.sensors, "history_for_many"):
        history = manager.sensors.history_for_many(wanted, limit=limit)
    else:
        history = {key: manager.sensors.history_for(key, limit=limit).get("observations", [])
                   for key in wanted}
    return keyed, history


def _chart_groups(device, sensors, histories):
    from .sensor import SensorEngine
    groups = {}
    for item in sensors:
        group = _chart_group(item)
        if group is None:
            continue
        key, title, unit = group
        sensor_key = SensorEngine.sensor_key(
            item["sensor_type"], device, item.get("resource") or "")
        observations = histories.get(sensor_key) or []
        points = []
        for row in reversed(observations):
            value = _chart_value(item, row.get("value"))
            ts = _number(row.get("observed_at"))
            if value is not None and ts is not None:
                points.append((ts, value))
        if not points:
            current = _chart_value(item, item.get("value"))
            updated = _number(item.get("updated_at")) or time.time()
            if current is not None:
                points = [(updated, current)]
        if not points:
            continue
        slot = groups.setdefault(key, {"key": key, "title": title, "unit": unit, "series": []})
        slot["series"].append({"label": _series_label(item), "item": item, "points": points})
    order = {"vpn-tunnel": 0, "vpn-up": 1, "cpu": 2, "memory": 3,
             "disk": 4, "temperature": 5, "sessions": 6, "session-rate": 7,
             "fan-speed": 8}
    return sorted(groups.values(), key=lambda row: (order.get(row["key"], 99), row["title"]))


def _svg_path_segments(points, x_of, y_of):
    if not points:
        return []
    gaps = [points[i][0] - points[i - 1][0] for i in range(1, len(points))
            if points[i][0] > points[i - 1][0]]
    gap_limit = None
    if gaps:
        ordered = sorted(gaps)
        median = ordered[len(ordered) // 2]
        gap_limit = max(180.0, median * 2.5)
    paths, current = [], []
    for index, (ts, value) in enumerate(points):
        if index and gap_limit is not None and ts - points[index - 1][0] > gap_limit:
            if current:
                paths.append(current)
            current = []
        current.append((x_of(ts), y_of(value)))
    if current:
        paths.append(current)
    return paths


def _render_telemetry_chart(group, compact=False):
    width, height = (660, 210) if compact else (720, 230)
    left, right, top, bottom = 52, 18, 20, 34
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [value for series in group["series"] for _ts, value in series["points"]]
    times = [ts for series in group["series"] for ts, _value in series["points"]]
    if not values or not times:
        return ""
    unit = group["unit"]
    if unit == "%":
        low, high = 0.0, 100.0
    elif unit == "state":
        low, high = 0.0, 1.0
    elif unit == "°C":
        low = max(0.0, min(values) - 5.0)
        high = max(values) + 5.0
    else:
        low = 0.0 if min(values) >= 0 else min(values)
        high = max(values)
    if high <= low:
        high = low + max(1.0, abs(low) * 0.1)
    t_min, t_max = min(times), max(times)
    if t_max <= t_min:
        t_min -= 30.0
        t_max += 30.0

    def x_of(ts):
        return left + ((ts - t_min) / (t_max - t_min)) * plot_w

    def y_of(value):
        return top + (1.0 - ((value - low) / (high - low))) * plot_h

    grid = []
    grid_steps = range(2) if unit == "state" else range(5)
    grid_divisor = 1.0 if unit == "state" else 4.0
    for step in grid_steps:
        y = top + (plot_h * step / grid_divisor)
        value = high - ((high - low) * step / grid_divisor)
        label = ("Up" if value >= 0.5 else "Down") if unit == "state" else (
            f"{value:.0f}" if abs(value) >= 10 or value.is_integer() else f"{value:.1f}")
        grid.append(f'<line class="telemetry-grid-line" x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}"/>'
                    f'<text class="telemetry-axis" x="{left-7}" y="{y+4:.1f}" text-anchor="end">{e(label)}</text>')
    start_label = time.strftime("%H:%M", time.localtime(t_min))
    end_label = time.strftime("%H:%M", time.localtime(t_max))
    paths, legends = [], []
    for index, series in enumerate(group["series"][:14]):
        color = index % 14
        segments = _svg_path_segments(series["points"], x_of, y_of)
        for segment in segments:
            command = " ".join(("M" if point_index == 0 else "L") + f"{x:.1f},{y:.1f}"
                               for point_index, (x, y) in enumerate(segment))
            paths.append(f'<path class="telemetry-line telemetry-stroke-{color}" d="{command}"/>')
        last_ts, last_value = series["points"][-1]
        paths.append(f'<circle class="telemetry-fill-{color}" cx="{x_of(last_ts):.1f}" cy="{y_of(last_value):.1f}" r="3"/>')
        item = series["item"]
        shown = ("Up" if last_value >= 0.5 else "Down") if unit == "state" else f"{last_value:g}{(' ' + unit) if unit else ''}"
        legends.append(f'<span><i class="telemetry-swatch telemetry-fill-{color}"></i>'
                       f'<b>{e(series["label"])}</b> {e(shown)} '
                       f'<small class="badge b-{"ok" if _status_class(item.get("status")) == "ok" else "chg" if _status_class(item.get("status")) == "warn" else "bad" if _status_class(item.get("status")) == "bad" else "dim"}">{e(str(item.get("status") or "UNKNOWN").upper())}</small></span>')
    worst = max((_STATUS_RANK.get(str(s["item"].get("status") or "UNKNOWN").upper(), 0)
                 for s in group["series"]), default=0)
    card_state = {1: "ok", 2: "warn", 3: "bad"}.get(worst, "dim")
    chart = (f'<article class="telemetry-chart-card {card_state}" data-telemetry-group="{e(group["key"])}" '
             f'data-series-count="{len(group["series"])}"><div class="telemetry-chart-head">'
             f'<div><h3>{e(group["title"])}</h3><p>Latest {max(len(s["points"]) for s in group["series"])} saved poll(s) · gaps are not filled</p></div>'
             f'<span class="badge b-{"ok" if card_state == "ok" else "chg" if card_state == "warn" else "bad" if card_state == "bad" else "dim"}">{len(group["series"])} channel(s)</span></div>'
             f'<svg class="telemetry-svg" viewBox="0 0 {width} {height}" role="img" aria-label="{e(group["title"])} trend">'
             + ''.join(grid) + ''.join(paths)
             + f'<text class="telemetry-axis" x="{left}" y="{height-8}">{e(start_label)}</text>'
             f'<text class="telemetry-axis" x="{width-right}" y="{height-8}" text-anchor="end">{e(end_label)}</text>'
             f'<text class="telemetry-axis" x="{width-right}" y="{top+12}" text-anchor="end">{e(unit)}</text></svg>'
             f'<div class="telemetry-legend">{"".join(legends)}</div></article>')
    return chart


def _render_status_groups(sensors):
    groups = {}
    for item in sensors:
        if _chart_group(item):
            continue
        kind = _measurement_kind(item)
        groups.setdefault(kind, []).append(item)
    cards = []
    for kind, items in sorted(groups.items()):
        worst = max((_STATUS_RANK.get(str(item.get("status") or "UNKNOWN").upper(), 0)
                     for item in items), default=0)
        state = {1: "ok", 2: "warn", 3: "bad"}.get(worst, "dim")
        if kind == "vpn_tunnel":
            healthy = sum(1 for item in items if str(item.get("value") or "").lower() == "up")
            value = f"{healthy}/{len(items)} up"
        elif len(items) == 1:
            value = str(items[0].get("value") or "—")
        else:
            healthy = sum(1 for item in items if str(item.get("status") or "").upper() == "OK")
            value = f"{healthy}/{len(items)} healthy"
        details = ", ".join(filter(None, (str(item.get("resource") or "") for item in items[:4])))
        if len(items) > 4:
            details += f" +{len(items)-4} more"
        cards.append(f'<div class="sensor-card {state}"><div class="sensor-head"><span class="sensor-dot"></span>{e(_measurement_name(items[0]))}</div>'
                     f'<div class="sensor-value">{e(value)}</div><div class="sensor-detail">{e(details or "Latest SNMP value")}</div></div>')
    return ('<h3>Current status</h3><div class="sensor-grid telemetry-status-grid">' + ''.join(cards) + '</div>') if cards else ""


def _measurement_detail_table(device, sensors):
    from .web_ui import _fmt_ts
    rows = []
    for item in sensors[:100]:
        status = str(item.get("status") or "UNKNOWN").upper()
        rule = item.get("threshold") or "No numeric thresholds saved"
        kind = _measurement_kind(item)
        if kind in {"cpu", "memory", "processor_cpu", "vdom_cpu", "vdom_memory"} and not item.get("threshold"):
            status = "UNKNOWN"
            rule = "Poll again to apply a profile with health thresholds"
        cls = {"OK": "b-ok", "WARNING": "b-chg", "CRITICAL": "b-bad"}.get(status, "b-dim")
        rows.append(f'<tr><td><b>{e(_measurement_name(item))}</b><br>{e(item.get("resource"))}</td>'
                    f'<td>{e(item.get("value") if item.get("value") is not None else "—")} {e(item.get("unit"))}</td>'
                    f'<td><span class="badge {cls}">{e(status)}</span></td><td>{e(rule)}</td>'
                    f'<td>{_fmt_ts(item.get("updated_at"))}</td><td><code>{e(item.get("sensor_type"))}</code><br>{e(item.get("message"))}</td></tr>')
    limited = '<p class="muted">Showing the first 100 measurements. Use the Sensors API for the complete set.</p>' if len(sensors) > 100 else ""
    return ('<details class="telemetry-details"><summary><b>Advanced measurement details · '
            f'{len(sensors)}</b></summary><div class="table-wrap"><table><tr><th>Measurement</th><th>Value</th>'
            '<th>Health</th><th>Health rule</th><th>Last evaluated</th><th>Source details</th></tr>'
            + ''.join(rows) + '</table></div>' + limited + '</details>')


def _vendor_measurement_data(handler, device, selected=""):
    m = handler.manager
    if not hasattr(m, "vendor_profiles") or not hasattr(m, "sensors"):
        return None, [], {}, {}, []
    facts = m.inv.get_facts(device) or {}
    profile = m.vendor_profiles.match(facts.get("sysobjectid", ""))
    if profile is None:
        return None, [], {}, {}, []
    sensors = [row for row in m.sensors.list(device=device, limit=2000)
               if str(row.get("source") or "").startswith(f"vendor-profile:{profile.id}/")]
    keyed, histories = _history_for_chart_sensors(m, device, sensors, selected=selected)
    return profile, sensors, keyed, histories, _chart_groups(device, sensors, histories)


def vendor_measurements_overview_content(handler, device):
    profile, sensors, _keyed, _histories, groups = _vendor_measurement_data(handler, device)
    if profile is None or not sensors or not groups:
        return ""
    dev = handler.manager.inv.get(device) or {}
    device_types = set(str(dev.get("device_type") or "network").replace(",", " ").split())
    by_key = {group["key"]: group for group in groups}
    selected_groups = []
    if "network" in device_types:
        vpn = by_key.get("vpn-tunnel") or by_key.get("vpn-up")
        selected_groups = [group for group in (vpn, by_key.get("cpu"), by_key.get("memory")) if group]
    elif "system" in device_types:
        selected_groups = [by_key[key] for key in ("cpu", "memory", "disk", "temperature") if key in by_key]
    if not selected_groups:
        selected_groups = groups[:4]
    charts = ''.join(_render_telemetry_chart(group, compact=True) for group in selected_groups)
    return (f'<div class="telemetry-panel-head">'
            f'<div><h2>Monitoring trends</h2><p class="muted">Key SNMP measurements from the latest saved polls. Opening this page does not poll the device.</p></div>'
            f'<a class="btn ghost" href="/snmp?device={urllib.parse.quote(device, safe="") }#vendor-measurements">Open all SNMP monitoring</a></div>'
            f'<div class="telemetry-grid telemetry-overview-grid">{charts}</div>'
            '<p class="muted" data-monitoring-refresh-status>Auto-update reads newly saved monitoring values only; it does not poll the device.</p>')


def vendor_measurements_overview(handler, device):
    content = vendor_measurements_overview_content(handler, device)
    if not content:
        return ""
    interval = int(handler.manager.settings.get("snmp_poll_interval") or 15)
    interval = max(5, min(interval, 60))
    url = "/device-monitoring-trends?" + urllib.parse.urlencode({"name": device})
    script = r"""
(function(){
  var root=document.getElementById('monitoring-trends');
  if(!root) return;
  var delay=Number(root.getAttribute('data-refresh-seconds')||15)*1000, timer=null, busy=false;
  function schedule(){ clearTimeout(timer); timer=setTimeout(update,delay); }
  function stamp(){
    var el=root.querySelector('[data-monitoring-refresh-status]');
    if(el) el.textContent='Updated from saved monitoring data at '+new Date().toLocaleTimeString()+'. No device poll was started.';
  }
  function update(){
    if(!document.body.contains(root)) return;
    var panel=root.closest('.tab-panel');
    if(document.hidden||(panel&&panel.hidden)){ schedule(); return; }
    if(busy){ schedule(); return; }
    busy=true;
    fetch(root.getAttribute('data-refresh-url'),{credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'NetConfig'}})
      .then(function(r){
        if(r.redirected){ window.location.reload(); return ''; }
        if(!r.ok) throw new Error('refresh failed');
        return r.text();
      })
      .then(function(markup){ if(markup.trim()){ root.innerHTML=markup; stamp(); } })
      .catch(function(){ var el=root.querySelector('[data-monitoring-refresh-status]'); if(el) el.textContent='Auto-update will retry; the last saved graph remains visible.'; })
      .finally(function(){ busy=false; schedule(); });
  }
  document.addEventListener('visibilitychange',function(){ if(!document.hidden){ clearTimeout(timer); update(); } });
  schedule();
})();
"""
    return (f'<div class="panel" id="monitoring-trends" data-refresh-url="{e(url)}" '
            f'data-refresh-seconds="{interval}">{content}</div><script>{script}</script>')


def vendor_measurements_panel(handler, device, q=None):
    from .web_ui import _fmt_ts
    selected = str(((q or {}).get("measurement") or [""])[0])
    profile, sensors, keyed, histories, groups = _vendor_measurement_data(handler, device, selected)
    if profile is None:
        return ('<div class="panel"><h2>Vendor monitoring</h2><p>No monitoring profile matches this device.</p>'
                '<p>Uploaded MIBs can name and collect OIDs, but do not automatically define CPU, memory, units or health thresholds. '
                'Raw values remain available below; a matching measurement profile is needed before they can be assessed.</p>'
                '<p><a href="/snmp">Review monitoring profiles</a> · <a href="/mib">Review uploaded MIBs</a></p></div>')
    head = (f'<div class="panel" id="vendor-measurements"><h2>Vendor monitoring</h2><p><b>{e(profile.vendor)} {e(profile.product)}</b> · '
            f'{len(sensors)} monitoring measurement(s), grouped into operational trends and status.</p>'
            '<p>Health follows the active monitoring profile, not the MIB name. '
            + ('Bundled FortiGate CPU defaults: warning at 80%, critical at 95%; memory: warning at 80%, critical at 90%. '
               'These are adjustable NetConfig defaults, not vendor-certified limits. '
               if profile.id == "fortinet.fortigate" else 'Each measurement shows the health rule its profile defines. ')
            + 'Updated rules take effect on the next SNMP poll. Unknown is not a healthy result.</p>')
    if not sensors:
        return head + '<p>No mapped measurements collected yet. Use Poll now above; check raw vendor values and the active profile if the device returns no matching OIDs.</p></div>'
    charts = ''.join(_render_telemetry_chart(group) for group in groups)
    trends = ('<h3>Monitoring trends</h3><p class="muted">Numeric measurements are grouped by purpose. CPU cores and related virtual-domain values share a chart instead of becoming separate rows.</p>'
              f'<div class="telemetry-grid">{charts}</div>') if charts else '<p class="muted">No numeric trend data has been saved yet.</p>'
    status = _render_status_groups(sensors)
    history = ""
    if selected:
        if selected not in keyed:
            history = '<p class="err">This measurement is not in the displayed device profile.</p>'
        else:
            observations = (histories.get(selected) or [])[:50]
            history_rows = ''.join(f'<tr><td>{_fmt_ts(row.get("observed_at"))}</td><td>{e(row.get("value"))} {e(row.get("unit"))}</td><td>{e(row.get("status"))}</td></tr>' for row in observations)
            history = ('<details id="measurement-history" class="telemetry-details" open><summary><b>Measurement history · raw saved values</b></summary>'
                       '<p>Latest 50 saved evaluations; no missing periods are filled in. The trend above is the primary view.</p>'
                       '<div class="table-wrap"><table><tr><th>Evaluated</th><th>Value</th><th>Health</th></tr>'
                       + (history_rows or '<tr><td colspan="3">No saved history yet. Poll the device first.</td></tr>') + '</table></div></details>')
    return head + trends + status + _measurement_detail_table(device, sensors) + history + '</div>'
