"""Read-only operator explanations for MAC locations, route learning and measurements."""
import html
import urllib.parse

from .users import can
from .network_intelligence import normalize_mac, _port_keys


def e(value):
    return html.escape(str(value if value is not None else ""))


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
                      f'<input type="hidden" name="name" value="{e(name)}"><input type="hidden" name="back" value="routes">'
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


def vendor_measurements_panel(handler, device, q=None):
    from .web_ui import _fmt_ts
    from .sensor import SensorEngine
    m = handler.manager
    facts = m.inv.get_facts(device) or {}
    profile = m.vendor_profiles.match(facts.get("sysobjectid", ""))
    if profile is None:
        return ('<div class="panel"><h2>Vendor profile telemetry</h2><p>No monitoring profile matches this device.</p>'
                '<p>Uploaded MIBs can name and collect OIDs, but do not automatically define CPU, memory, units or health thresholds. '
                'Raw values remain available below; a matching measurement profile is needed before they can be assessed.</p>'
                '<p><a href="/snmp">Review monitoring profiles</a> · <a href="/mib">Review uploaded MIBs</a></p></div>')
    sensors = [r for r in m.sensors.list(device=device, limit=2000)
               if str(r.get("source") or "").startswith(f"vendor-profile:{profile.id}/")]
    head = (f'<div class="panel" id="vendor-measurements"><h2>Vendor profile telemetry</h2><p><b>{e(profile.vendor)} {e(profile.product)}</b> · '
            f'{len(sensors)} monitoring measurement(s).</p>'
            '<p>Health follows the active monitoring profile, not the MIB name. Bundled FortiGate CPU defaults: warning at 80%, critical at 95%; '
            'memory: warning at 80%, critical at 90%. These are adjustable NetConfig defaults, not vendor-certified limits. '
            'Updated rules take effect on the next SNMP poll. Unknown is not a healthy result.</p>')
    if not sensors:
        return head + '<p>No mapped measurements collected yet. Use Poll now above; check raw vendor values and the active profile if the device returns no matching OIDs.</p></div>'
    rows = []
    selected = str(((q or {}).get("measurement") or [""])[0])
    keys = {}
    for item in sensors[:100]:
        key = SensorEngine.sensor_key(item["sensor_type"], device, item.get("resource") or "")
        keys[key] = item
        status = str(item.get("status") or "UNKNOWN").upper()
        rule = item.get("threshold") or "No numeric thresholds saved"
        kind = str(item.get("sensor_type") or "").rsplit(".", 1)[-1]
        if kind in {"cpu", "memory", "processor_cpu", "vdom_cpu", "vdom_memory"} and not item.get("threshold"):
            status = "UNKNOWN"
            rule = "Poll again to apply a profile with health thresholds"
        cls = {"OK": "b-ok", "WARNING": "b-chg", "CRITICAL": "b-bad"}.get(status, "b-dim")
        name = {"cpu": "CPU usage", "memory": "Memory usage", "processor_cpu": "Processor CPU usage",
                "vdom_cpu": "Virtual-domain CPU usage", "vdom_memory": "Virtual-domain memory usage"}.get(kind, kind.replace("_", " ").title())
        value = item.get("value")
        link = '/snmp?' + urllib.parse.urlencode({"device": device, "measurement": key}) + '#measurement-history'
        rows.append(f'<tr><td><b>{e(name)}</b><br>{e(item.get("resource"))}</td><td>{e(value if value is not None else "—")} {e(item.get("unit"))}</td>'
                    f'<td><span class="badge {cls}">{e(status)}</span></td><td>{e(rule)}</td><td>{_fmt_ts(item.get("updated_at"))}</td>'
                    f'<td><a href="{e(link)}">History</a><details><summary>Advanced details</summary><p>{e(item.get("sensor_type"))}<br>{e(item.get("message"))}<br>{e(item.get("source"))}</p></details></td></tr>')
    body = '<div class="table-wrap"><table><tr><th>Measurement</th><th>Value</th><th>Health</th><th>Health rule</th><th>Last evaluated</th><th></th></tr>' + ''.join(rows) + '</table></div>'
    if len(sensors) > 100:
        body += '<p class="muted">Showing the first 100 measurements. Use the Sensors API for the complete set.</p>'
    history = ''
    if selected:
        if selected not in keys:
            history = '<p class="err">This measurement is not in the displayed device profile.</p>'
        else:
            saved = m.sensors.history_for(selected, limit=50)
            observations = saved.get("observations") or []
            history_rows = ''.join(f'<tr><td>{_fmt_ts(r.get("observed_at"))}</td><td>{e(r.get("value"))} {e(r.get("unit"))}</td><td>{e(r.get("status"))}</td></tr>' for r in observations)
            history = ('<div id="measurement-history"><h3>Measurement history</h3><p>Latest 50 saved evaluations; no missing periods are filled in.</p>'
                       '<table><tr><th>Evaluated</th><th>Value</th><th>Health</th></tr>'
                       + (history_rows or '<tr><td colspan="3">No saved history yet. Poll the device first.</td></tr>') + '</table></div>')
    return head + body + history + '</div>'
