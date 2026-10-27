"""FortiView-style NetFlow traffic views for the web console.

Presentation only. Data comes from ``analyze_traffic`` over PostgreSQL history
or the memory fallback; rendering never contacts devices. Every dynamic value is HTML-escaped
(reverse-DNS names and device names are untrusted text). Bars are SVG geometry
with theme classes, so no per-element style attributes are emitted.
"""
from __future__ import annotations

import html
import json
import time
import urllib.parse

from .netflow import analyze_traffic
from .web_ui import _fmt_bps

VIEWS = (("sources", "Sources"), ("destinations", "Destinations"), ("services", "Services"),
         ("conversations", "Conversations"), ("exporters", "Exporters"))
WINDOWS = ((300, "5 min"), (900, "15 min"), (3600, "1 hour"), (21600, "6 hours"), (86400, "24 hours"))
_BUCKET = {300: 60, 900: 60, 3600: 120, 21600: 600, 86400: 1800}
_BAR_W, _BAR_H = 140, 10

TRAFFIC_CSS = """
.nf-toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.nf-toolbar label{margin:0 0 4px}
.nf-toolbar .nf-q{min-width:220px}
.nf-views{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}
.nf-views a{padding:6px 12px;border:1px solid var(--border);border-radius:999px;color:var(--text);text-decoration:none;font-weight:600}
.nf-views a.on{background:var(--solid);border-color:var(--solid);color:#fff}
.nf-status{margin:8px 0 0}
.nf-kpis{margin-bottom:16px}
.nf-chip{display:inline-flex;gap:8px;align-items:center;padding:3px 10px;border-radius:999px;background:var(--ok10);font-weight:600}
.nf-table td.num,.nf-table th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.nf-table td.bar{white-space:nowrap}
.nf-table td.bar svg{vertical-align:middle;margin-right:8px}
.nf-sub{display:block;color:var(--grey);font-size:12px;margin-top:2px}
.nf-legend{display:flex;gap:16px;align-items:center;margin:0 0 8px;color:var(--grey);font-size:13px}
.nf-legend svg{vertical-align:middle;margin-right:6px}
.nf-sent{fill:#2a78d6}.nf-recv{fill:#247a4d}.nf-meter{fill:#7c8c82}.nf-track{fill:var(--line)}
html[data-theme="dark"] .nf-sent{fill:#3987e5}
html[data-theme="dark"] .nf-recv{fill:#3fa56f}
html[data-theme="dark"] .nf-meter{fill:#7f9488}
.nf-chart{width:100%;height:auto;display:block}
.nf-chart .nf-grid{stroke:var(--line);stroke-width:1}
.nf-chart .nf-axis{fill:var(--grey);font-size:11px}
.nf-chart .nf-line{fill:none;stroke:#247a4d;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.nf-chart .nf-area{fill:#247a4d;fill-opacity:.1}
.nf-chart .nf-cross{stroke:var(--grey);stroke-width:1}
.nf-chart .nf-dot{fill:#247a4d;stroke:var(--surface);stroke-width:2}
html[data-theme="dark"] .nf-chart .nf-line{stroke:#3fa56f}
html[data-theme="dark"] .nf-chart .nf-area,html[data-theme="dark"] .nf-chart .nf-dot{fill:#3fa56f}
.nf-chart-wrap{position:relative}
.nf-tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:6px 10px;box-shadow:var(--shadow);font-size:13px;white-space:nowrap}
.nf-tip b{display:block;font-variant-numeric:tabular-nums}
.nf-tip[hidden]{display:none}
"""

TRAFFIC_JS = """
(function(){
  document.querySelectorAll('[data-nf-chart]').forEach(function(wrap){
    var svg=wrap.querySelector('svg'), tip=wrap.querySelector('.nf-tip');
    var cross=svg.querySelector('.nf-cross'), dot=svg.querySelector('.nf-dot');
    var pts=JSON.parse(wrap.getAttribute('data-nf-chart')||'[]');
    if(!pts.length) return;
    var idx=-1;
    function show(i){
      if(i<0||i>=pts.length) return; idx=i; var p=pts[i];
      cross.setAttribute('x1',p[2]); cross.setAttribute('x2',p[2]); cross.removeAttribute('visibility');
      dot.setAttribute('cx',p[2]); dot.setAttribute('cy',p[3]); dot.removeAttribute('visibility');
      tip.textContent='';
      var v=document.createElement('b'); v.textContent=p[1]; tip.appendChild(v);
      tip.appendChild(document.createTextNode(p[0]));
      var box=svg.getBoundingClientRect(), scale=box.width/svg.viewBox.baseVal.width;
      tip.hidden=false;
      var left=p[2]*scale+12; if(left+tip.offsetWidth>box.width) left=p[2]*scale-tip.offsetWidth-12;
      tip.style.left=Math.max(0,left)+'px'; tip.style.top='8px';
    }
    function hide(){ cross.setAttribute('visibility','hidden'); dot.setAttribute('visibility','hidden'); tip.hidden=true; }
    function nearest(clientX){
      var box=svg.getBoundingClientRect(), x=(clientX-box.left)*svg.viewBox.baseVal.width/box.width;
      var best=0, d=1e9; pts.forEach(function(p,i){ var dd=Math.abs(p[2]-x); if(dd<d){d=dd;best=i;} });
      return best;
    }
    svg.addEventListener('pointermove',function(e){ show(nearest(e.clientX)); });
    svg.addEventListener('pointerleave',hide);
    svg.addEventListener('focus',function(){ show(idx<0?pts.length-1:idx); });
    svg.addEventListener('blur',hide);
    svg.addEventListener('keydown',function(e){
      if(e.key==='ArrowLeft'){ show(Math.max(0,idx-1)); e.preventDefault(); }
      if(e.key==='ArrowRight'){ show(Math.min(pts.length-1,idx+1)); e.preventDefault(); }
    });
  });
})();
"""


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def fmt_bytes(n):
    """Decimal units, as FortiGate/FortiView report them (kB / MB / GB)."""
    n = float(n or 0)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.2f} {unit}"
        n /= 1000.0
    return f"{n:.2f} TB"


def _fmt_count(n):
    return f"{int(n or 0):,}"


def _fmt_span(seconds):
    seconds = int(seconds or 0)
    if seconds >= 3600:
        h, m = divmod(seconds // 60, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{max(1, seconds // 60)} min"


def _seg(x, w, h, cls, round_end):
    """One bar segment; only the data-end (right) is rounded, baseline square."""
    if w <= 0:
        return ""
    if not round_end:
        return f'<rect class="{cls}" x="{x:.1f}" y="0" width="{w:.1f}" height="{h}"/>'
    r = min(4.0, h / 2.0, w)
    return (f'<path class="{cls}" d="M{x:.1f} 0H{x + w - r:.1f}A{r:.1f} {r:.1f} 0 0 1 {x + w:.1f} {r:.1f}'
            f'V{h - r:.1f}A{r:.1f} {r:.1f} 0 0 1 {x + w - r:.1f} {h}H{x:.1f}Z"/>')


def split_bar(sent, received, scale_max, title):
    """Sent | 2px surface gap | received, scaled to the table maximum."""
    total = (sent or 0) + (received or 0)
    full = _BAR_W * (total / scale_max) if scale_max else 0
    ws = full * (sent / total) if total else 0
    wr = full - ws
    gap = 2 if ws > 0 and wr > 0 else 0
    parts = _seg(0, max(0, ws - gap / 2), _BAR_H, "nf-sent", wr <= 0) + \
        _seg(ws + gap / 2, max(0, wr - gap / 2), _BAR_H, "nf-recv", True)
    return (f'<svg width="{_BAR_W}" height="{_BAR_H}" viewBox="0 0 {_BAR_W} {_BAR_H}" role="img" '
            f'aria-label="{_e(title)}"><title>{_e(title)}</title>{parts}</svg>')


def meter(value, scale_max, title):
    w = _BAR_W * (value / scale_max) if scale_max else 0
    return (f'<svg width="{_BAR_W}" height="{_BAR_H}" viewBox="0 0 {_BAR_W} {_BAR_H}" role="img" '
            f'aria-label="{_e(title)}"><title>{_e(title)}</title>'
            f'<rect class="nf-track" x="0" y="0" width="{_BAR_W}" height="{_BAR_H}" rx="4"/>'
            f'{_seg(0, w, _BAR_H, "nf-meter", True)}</svg>')


def legend():
    sw = '<svg width="12" height="10" viewBox="0 0 12 10" aria-hidden="true"><rect class="{}" width="12" height="10" rx="2"/></svg>'
    return (f'<div class="nf-legend"><span>{sw.format("nf-sent")}Sent</span>'
            f'<span>{sw.format("nf-recv")}Received</span>'
            '<span>Bars are scaled to the largest row in this table.</span></div>')


def _scope_badge(scope):
    label = {"public": "Internet", "private": "Private", "multicast": "Multicast",
             "loopback": "Loopback"}.get(scope, "Unknown")
    cls = {"public": "b-dim", "private": "b-ok", "multicast": "b-chg"}.get(scope, "b-dim")
    return f'<span class="badge {cls}">{label}</span>'


def _link(base, params, text, **override):
    query = dict(params)
    query.update({k: v for k, v in override.items() if v is not None})
    query = {k: v for k, v in query.items() if v not in ("", None)}
    return f'<a href="{_e(base + "?" + urllib.parse.urlencode(query))}">{text}</a>'


def _who(ip, ident):
    ident = ident or {}
    name = ident.get("device") or ident.get("name") or ""
    head = f'<b>{_e(name)}</b>' if name else '<span class="muted">Unknown host</span>'
    sub = []
    if ident.get("device") and ident.get("name"):
        sub.append(_e(ident["name"]))
    if ident.get("mac"):
        sub.append(f'<code>{_e(ident["mac"])}</code>'
                   + (f' · learned on {_e(ident["learned_on"])}' if ident.get("learned_on") else ""))
    if ident.get("attachment"):
        sub.append("port " + _e(ident["attachment"]))
    return head + "".join(f'<span class="nf-sub">{x}</span>' for x in sub)


def _rate_cell(bps, scale_max):
    return f'<td class="bar">{meter(bps, scale_max, "Average " + _fmt_bps(bps))}{_e(_fmt_bps(bps))}</td>'


def _sessions_cell(n, scale_max):
    return f'<td class="bar">{meter(n, scale_max, f"{n:,} sessions")}{_fmt_count(n)}</td>'


def _bytes_cell(sent, received, scale_max, sent_label="Sent", recv_label="Received"):
    title = f"{sent_label} {fmt_bytes(sent)} · {recv_label} {fmt_bytes(received)}"
    return (f'<td class="bar">{split_bar(sent, received, scale_max, title)}'
            f'{_e(fmt_bytes(sent + received))}'
            f'<span class="nf-sub">{_e(fmt_bytes(sent))} / {_e(fmt_bytes(received))}</span></td>')


def _max(rows, key):
    return max((float(r.get(key) or 0) for r in rows), default=0.0) or 1.0


def sources_table(analysis, base, params, limit=None, drill=True):
    rows = analysis["sources"][:limit] if limit else analysis["sources"]
    ids = analysis.get("identities") or {}
    mb, ms, mr = _max(rows, "bytes"), _max(rows, "sessions"), _max(rows, "avg_bps")
    body = []
    for r in rows:
        ip = _e(r["ip"])
        ip_cell = _link(base, params, ip, view="destinations", q=r["ip"]) if drill else ip
        body.append(
            f'<tr><td>{ip_cell}</td><td>{_who(r["ip"], ids.get(r["ip"]))}</td>'
            + _bytes_cell(r["sent"], r["received"], mb)
            + _sessions_cell(r["sessions"], ms) + _rate_cell(r["avg_bps"], mr)
            + f'<td>{_e(", ".join(r["services"]))}</td></tr>')
    return ('<div class="table-wrap"><table class="nf-table"><tr><th>Source</th><th>Device</th>'
            '<th>Bytes (sent / received)</th><th>Sessions</th><th>Average rate</th><th>Top services</th></tr>'
            + ("".join(body) or '<tr><td colspan=6 class=muted>No local hosts in this period.</td></tr>')
            + '</table></div>')


def destinations_table(analysis, base, params, limit=None, drill=True):
    rows = analysis["destinations"][:limit] if limit else analysis["destinations"]
    ids = analysis.get("identities") or {}
    mb, ms, mr = _max(rows, "bytes"), _max(rows, "sessions"), _max(rows, "avg_bps")
    body = []
    for r in rows:
        ident = ids.get(r["ip"]) or {}
        name = ident.get("device") or ident.get("name")
        label = (f'<b>{_e(name)}</b> <span class="muted">({_e(r["ip"])})</span>' if name else _e(r["ip"]))
        label = _link(base, params, label, view="sources", q=r["ip"]) if drill else label
        svc = r["services"]
        svc_text = svc[0] if r["service_count"] == 1 else f'{r["service_count"]} services: {", ".join(svc)}'
        body.append(
            f'<tr><td>{label} {_scope_badge(r["scope"])}</td><td>{_e(svc_text)}</td>'
            + _bytes_cell(r["sent"], r["received"], mb, "Sent to it", "Received from it")
            + _sessions_cell(r["sessions"], ms) + _rate_cell(r["avg_bps"], mr)
            + f'<td class="num">{_fmt_count(r["peer_count"])}</td></tr>')
    return ('<div class="table-wrap"><table class="nf-table"><tr><th>Destination</th><th>Service</th>'
            '<th>Bytes (sent / received)</th><th>Sessions</th><th>Average rate</th><th class="num">Local hosts</th></tr>'
            + ("".join(body) or '<tr><td colspan=6 class=muted>No destinations in this period.</td></tr>')
            + '</table></div>')


def services_table(analysis, base, params, limit=None, drill=True):
    rows = analysis["services"][:limit] if limit else analysis["services"]
    mb, ms, mr = _max(rows, "bytes"), _max(rows, "sessions"), _max(rows, "avg_bps")
    body = []
    for r in rows:
        name = _e(r["name"])
        cell = _link(base, params, f"<b>{name}</b>", view="sources", q=r["name"]) if drill else f"<b>{name}</b>"
        body.append(
            f'<tr><td>{cell}<span class="nf-sub">{_e(r["label"])}</span></td>'
            f'<td class="bar">{meter(r["bytes"], mb, fmt_bytes(r["bytes"]))}{_e(fmt_bytes(r["bytes"]))}</td>'
            + _sessions_cell(r["sessions"], ms) + _rate_cell(r["avg_bps"], mr)
            + f'<td class="num">{_fmt_count(r["source_count"])}</td>'
            f'<td class="num">{_fmt_count(r["destination_count"])}</td></tr>')
    return ('<div class="table-wrap"><table class="nf-table"><tr><th>Service</th><th>Bytes</th><th>Sessions</th>'
            '<th>Average rate</th><th class="num">Local hosts</th><th class="num">Destinations</th></tr>'
            + ("".join(body) or '<tr><td colspan=6 class=muted>No services in this period.</td></tr>')
            + '</table></div>')


def conversations_table(analysis, base, params):
    rows = analysis["conversations"]
    ids = analysis.get("identities") or {}
    mb, ms = _max(rows, "bytes"), _max(rows, "sessions")
    body = []
    for r in rows:
        li, ri = ids.get(r["local"]) or {}, ids.get(r["remote"]) or {}
        ln = li.get("device") or li.get("name")
        rn = ri.get("device") or ri.get("name")
        local = _link(base, params, _e(r["local"]), view="destinations", q=r["local"])
        remote = _link(base, params, _e(r["remote"]), view="sources", q=r["remote"])
        body.append(
            f'<tr><td>{local}{f"<span class=nf-sub>{_e(ln)}</span>" if ln else ""}</td>'
            f'<td>{remote}{f"<span class=nf-sub>{_e(rn)}</span>" if rn else ""}</td>'
            f'<td>{_e(r["service"])}</td>'
            + _bytes_cell(r["sent"], r["received"], mb) + _sessions_cell(r["sessions"], ms) + '</tr>')
    return ('<div class="table-wrap"><table class="nf-table"><tr><th>Local host</th><th>Remote host</th>'
            '<th>Service</th><th>Bytes (sent / received)</th><th>Sessions</th></tr>'
            + ("".join(body) or '<tr><td colspan=5 class=muted>No conversations in this period.</td></tr>')
            + '</table></div>')


def exporters_table(data, base, params):
    rows = data.get("exporters") or []
    full = set((data.get("analysis") or {}).get("ring_full_exporters") or ())
    mb = _max(rows, "bytes")
    body = []
    for r in rows:
        exp = r["exporter"]
        state = ('<span class="badge b-chg">memory full</span>' if exp in full
                 else '<span class="badge b-ok">ok</span>')
        body.append(
            f'<tr><td>{_link(base, params, _e(exp), exporter=exp, view="sources")}</td>'
            f'<td>{_e(r.get("device") or "") or "<span class=muted>not in inventory</span>"}</td>'
            f'<td class="bar">{meter(r["bytes"], mb, fmt_bytes(r["bytes"]))}{_e(fmt_bytes(r["bytes"]))}</td>'
            f'<td class="num">{_fmt_count(r["flows"])}</td><td class="num">{_fmt_count(r["packet_datagrams"])}</td>'
            f'<td>{state}</td></tr>')
    return ('<div class="table-wrap"><table class="nf-table"><tr><th>Exporter</th><th>Device</th><th>Bytes</th>'
            '<th class="num">Flow records</th><th class="num">Datagrams</th><th>Flow memory</th></tr>'
            + ("".join(body) or '<tr><td colspan=6 class=muted>No exporter sent flows in this period.</td></tr>')
            + '</table></div>')


def kpi_tiles(analysis, compact=False):
    t = analysis["totals"]
    tiles = [
        ("Total traffic", fmt_bytes(t["bytes"]), f'{_fmt_count(t["packets"])} packets'),
        ("Average throughput", _fmt_bps(t["avg_bps"]),
         f'over {_fmt_span(min(analysis["coverage_seconds"], analysis["window_seconds"]))}'),
        ("Peak throughput", _fmt_bps(t["peak_bps"]), f'busiest {_fmt_span(analysis["bucket_seconds"])} interval'),
        ("Sessions", _fmt_count(t["sessions"]), f'{_fmt_count(t["records"])} flow records'),
    ]
    if not compact:
        tiles.append(("Hosts", f'{_fmt_count(t["sources"])} local',
                      f'{_fmt_count(t["destinations"])} remote · {_fmt_count(t["services"])} services'))
    return ('<div class="sensor-grid nf-kpis">' + "".join(
        f'<div class="sensor-card ok"><div class="sensor-head"><span class="sensor-dot"></span>{_e(a)}</div>'
        f'<div class="sensor-value">{_e(b)}</div><div class="sensor-detail">{_e(c)}</div></div>'
        for a, b, c in tiles) + '</div>')


def throughput_chart(analysis, now):
    """Single-series line + 10% area wash; crosshair tooltip; table fallback."""
    bucket = analysis["bucket_seconds"]
    if analysis.get("first_bucket_ts") is None:
        return ('<div class="panel"><h2>Throughput</h2>'
                '<p class="muted">No traffic was recorded in this period.</p></div>')
    start = int(analysis["first_bucket_ts"])
    end = int(now // bucket) * bucket
    by_ts = {r["ts"]: r["bps"] for r in analysis["trend"]}
    series = [(ts, by_ts.get(ts, 0.0)) for ts in range(start, end + bucket, bucket)]
    if len(series) < 2:
        return ('<div class="panel"><h2>Throughput</h2>'
                f'<p class="muted">All recorded traffic so far falls in the current {_e(_fmt_span(bucket))} '
                'interval; the chart appears once a second interval has data.</p></div>')
    W, H, L, R, T, B = 960, 200, 64, 12, 12, 26
    peak = max(v for _, v in series) or 1.0
    # clean round top tick: 1/2/5 x 10^n
    mag = 10 ** (len(str(int(peak))) - 1)
    top = next(m * mag for m in (1, 2, 5, 10) if m * mag >= peak)
    pw, ph = W - L - R, H - T - B

    def xy(i, v):
        return L + pw * i / (len(series) - 1), T + ph * (1 - v / top)

    pts = [xy(i, v) for i, (_ts, v) in enumerate(series)]
    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = line + f" L{pts[-1][0]:.1f} {T + ph:.1f} L{pts[0][0]:.1f} {T + ph:.1f} Z"
    grid = "".join(
        f'<line class="nf-grid" x1="{L}" x2="{W - R}" y1="{T + ph * (1 - f):.1f}" y2="{T + ph * (1 - f):.1f}"/>'
        f'<text class="nf-axis" x="{L - 8}" y="{T + ph * (1 - f) + 4:.1f}" text-anchor="end">{_e(_fmt_bps(top * f))}</text>'
        for f in (0, .5, 1))
    step = max(1, len(series) // 6)
    xlabels = "".join(
        f'<text class="nf-axis" x="{pts[i][0]:.1f}" y="{H - 6}" text-anchor="middle">'
        f'{time.strftime("%H:%M", time.localtime(series[i][0]))}</text>'
        for i in range(0, len(series), step))
    data = [[time.strftime("%H:%M", time.localtime(ts)) + f" · {_fmt_span(bucket)} average",
             _fmt_bps(v), round(x, 1), round(y, 1)] for (ts, v), (x, y) in zip(series, pts, strict=True)]
    table = "".join(f'<tr><td>{time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))}</td>'
                    f'<td class="num">{_e(_fmt_bps(v))}</td></tr>' for ts, v in series if v)
    return (f'<div class="panel"><h2>Throughput</h2>'
            f'<div class="nf-chart-wrap" data-nf-chart="{_e(json.dumps(data))}">'
            f'<svg class="nf-chart" viewBox="0 0 {W} {H}" tabindex="0" role="img" '
            f'aria-label="Throughput over the last {_e(_fmt_span(min(analysis["coverage_seconds"], analysis["window_seconds"])))}">'
            f'{grid}{xlabels}<path class="nf-area" d="{area}"/><path class="nf-line" d="{line}"/>'
            f'<line class="nf-cross" x1="0" x2="0" y1="{T}" y2="{T + ph}" visibility="hidden"/>'
            f'<circle class="nf-dot" r="4" cx="0" cy="0" visibility="hidden"/></svg>'
            f'<div class="nf-tip" hidden></div></div>'
            f'<details><summary>Show as table</summary><div class="table-wrap"><table class="nf-table">'
            f'<tr><th>Interval start</th><th class="num">Average rate</th></tr>{table}</table></div></details></div>')


def _toolbar(params, exporters, view):
    window = int(params.get("window") or 3600)
    wopts = "".join(f'<option value="{w}"{" selected" if w == window else ""}>{_e(t)}</option>' for w, t in WINDOWS)
    eopts = '<option value="">All exporters</option>' + "".join(
        f'<option value="{_e(x["exporter"])}"{" selected" if x["exporter"] == params.get("exporter") else ""}>'
        f'{_e(x["exporter"])}{(" · " + _e(x["device"])) if x.get("device") else ""}</option>' for x in exporters)
    tabs = "".join(
        f'<a href="/traffic?{_e(urllib.parse.urlencode({**{k: v for k, v in params.items() if v}, "view": key}))}"'
        f'{" class=on" if key == view else ""}>{_e(label)}</a>' for key, label in VIEWS)
    return (f'<div class="nf-views">{tabs}</div>'
            '<form method=get action="/traffic" class="nf-toolbar">'
            f'<input type=hidden name=view value="{_e(view)}">'
            f'<div><label>Time range</label><select name=window>{wopts}</select></div>'
            f'<div><label>Exporter</label><select name=exporter>{eopts}</select></div>'
            f'<div class="nf-q"><label>Filter by IP address or service</label>'
            f'<input name=q value="{_e(params.get("q") or "")}" placeholder="e.g. 192.168.2.34 or BitTorrent"></div>'
            '<div><button>Apply</button></div></form>')


def render_traffic_body(handler, q):
    """Body for /traffic (the caller adds the workspace tabs and page shell)."""
    def arg(name, default=""):
        return str((q.get(name) or [default])[0]).strip()
    view = arg("view", "sources")
    view = view if view in dict(VIEWS) else "sources"
    try:
        window = int(arg("window", "3600"))
    except ValueError:
        window = 3600
    window = window if window in dict(WINDOWS) else 3600
    params = {"view": view, "window": str(window), "q": arg("q")[:120], "exporter": arg("exporter")[:64]}
    collector = getattr(handler, "netflow", None)
    now = time.time()
    data = handler.manager.operations_console.traffic(
        collector, window_seconds=window, bucket_seconds=_BUCKET[window], now=now,
        query=params["q"], exporter=params["exporter"] or None, view_limit=50)
    all_exporters = data.get("exporter_choices", data.get("exporters") or [])
    if params["exporter"] and "exporter_choices" not in data:
        unfiltered = handler.manager.operations_console.traffic(
            collector, window_seconds=window, bucket_seconds=_BUCKET[window], now=now, view_limit=1)
        all_exporters = unfiltered.get("exporters") or all_exporters
    a = data["analysis"]
    settings = handler.manager.settings
    st = data.get("collector_status") or {}
    notes = []
    storage = data.get("storage") or {"source": "memory"}
    notes.append(history_notice(storage))
    if (storage.get("status") or {}).get("exporter_error"):
        notes.append('<p class="err">' + _e(storage["status"]["exporter_error"]) + '</p>')
    if not settings.get("netflow_enabled"):
        notes.append('<p class="err">The NetFlow collector is off. Turn it on in '
                     '<a href="/settings?section=netflow">Settings → NetFlow</a> and restart NetConfig.</p>')
    elif not st.get("running"):
        notes.append('<p class="err">The NetFlow collector is not running. Check the port in Settings → NetFlow.</p>')
    else:
        notes.append(f'<p class="muted nf-status">Listening on UDP {_e(st.get("port", ""))} · '
                     f'{_fmt_count(st.get("exporters", 0))} exporter(s) sending this run · '
                     f'selected period: {_e(_fmt_span(window))}.</p>')
        if a.get("ring_full_exporters"):
            notes.append(f'<p class="err">Flow memory is full for {_e(", ".join(a["ring_full_exporters"]))}; '
                         'the selected period may be incomplete. Enable database history or increase “Recent flows kept per device” in '
                         '<a href="/settings?section=netflow">Settings → NetFlow</a> (needs a restart).</p>')
        if not a.get("resolve_names"):
            notes.append('<p class="muted">Host names: turn on “Look up host names (reverse DNS)” in '
                         '<a href="/settings?section=netflow">Settings → NetFlow</a> to show names next to IP addresses.</p>')
    chip = ""
    if params["q"] or params["exporter"]:
        what = " · ".join(x for x in (params["q"] and f'matching “{params["q"]}”',
                                       params["exporter"] and f'exporter {params["exporter"]}') if x)
        chip = (f'<p><span class="nf-chip">Filtered: {_e(what)} '
                f'<a href="/traffic?{_e(urllib.parse.urlencode({"view": view, "window": window}))}">clear</a></span></p>')
    base = "/traffic"
    if view == "sources":
        table = legend() + sources_table(a, base, params)
        title = "Top sources (local hosts)"
    elif view == "destinations":
        table = legend() + destinations_table(a, base, params)
        title = "Top destinations"
    elif view == "services":
        table = services_table(a, base, params)
        title = "Services"
    elif view == "conversations":
        table = legend() + conversations_table(a, base, params)
        title = "Top conversations"
    else:
        table = exporters_table(data, base, params)
        title = "Exporters"
    hint = {"sources": "Select an address to see where it connects.",
            "destinations": "Select a destination to see which local hosts use it.",
            "services": "Select a service to see which local hosts use it."}.get(view, "")
    raw = "".join(
        f'<tr><td>{_e(time.strftime("%H:%M:%S", time.localtime(float(x.get("ts") or 0))))}</td>'
        f'<td>{_e(x.get("exporter"))}</td><td>{_e(x.get("src"))}:{int(x.get("sport") or 0)}</td>'
        f'<td>{_e(x.get("dst"))}:{int(x.get("dport") or 0)}</td><td>{_e(x.get("proto"))}</td>'
        f'<td class="num">{_e(fmt_bytes(x.get("bytes")))}</td></tr>' for x in data["raw_flows"][:100])
    return (f'<style>{TRAFFIC_CSS}</style>'
            f'<div class="panel">{_toolbar(params, all_exporters, view)}{"".join(notes)}{chip}</div>'
            + kpi_tiles(a) + throughput_chart(a, now)
            + f'<div class="panel"><h2>{_e(title)}</h2>'
            + (f'<p class="muted">{_e(hint)}</p>' if hint else "") + table
            + '<p class="muted">Opening this page does '
              'not contact any device. Service names are identified by port, not by inspecting traffic content. '
              'Sessions are estimated from unique address and port pairs. Average rate is total bytes divided by the '
              'period shown.</p></div>'
            + '<details class="panel"><summary><b>Advanced · raw flow records (latest 100)</b></summary>'
              '<div class="table-wrap"><table class="nf-table"><tr><th>Time</th><th>Exporter</th><th>Source</th>'
              '<th>Destination</th><th>Protocol</th><th class="num">Bytes</th></tr>'
            + (raw or '<tr><td colspan=6 class=muted>No flow records in this period.</td></tr>')
            + '</table></div></details>'
            + f'<script>{TRAFFIC_JS}</script>')


def history_notice(storage):
    """Shared English operator status; never expose connection strings/secrets."""
    st = storage.get("status") or {}
    text = ('PostgreSQL flow history · retention 24 hours · includes pending writes.'
            if storage.get("source") == "postgres" else
            'Records are held in memory and cleared when NetConfig restarts.')
    notes = [f'<p class=muted>{_e(text)}</p>']
    if st.get("enabled") and st.get("configured") is False:
        return "".join(notes) + ('<p class=muted>24-hour flow history is not saved: no History PostgreSQL '
                                 'database is set. Add one in <a href="/settings?section=db">Database settings</a> '
                                 'to keep a full day.</p>')
    for key in ("write_error", "read_error", "maintenance_error"):
        if st.get(key):
            notes.append(f'<p class=err>{_e(st[key])}</p>')
    if st.get("enabled"):
        notes.append(f'<p class=muted>Pending: {int(st.get("pending") or 0)} · '
                     f'Saved this run: {int(st.get("written") or 0)}.</p>')
    if st.get("dropped") or st.get("expired"):
        notes.append(f'<p class=err>History is incomplete: {int(st.get("dropped") or 0)} record(s) '
                     f'could not be queued; {int(st.get("expired") or 0)} expired before saving. '
                     'Counters cover this service run; missing records cannot be recovered.</p>')
    if storage.get("truncated"):
        notes.append(f'<p class=err>Results are incomplete: only the newest '
                     f'{int(storage.get("query_limit") or 0)} saved records are included. '
                     'Select a shorter period or one exporter. Older records remain stored for 24 hours.</p>')
    return "".join(notes)


def render_device_traffic(handler, dev, flows, now=None, identities=None):
    """Compact per-exporter view for the device page (top 8 of each view)."""
    now = time.time() if now is None else now
    m = handler.manager
    flows = [f for f in flows if now - 86400 <= float(f.get("ts") or 0) <= now]
    local_ips, host_to_device, arp = set(), {}, {}
    try:
        from .operations_correlation import traffic_host_context, traffic_identities
        host_to_device, arp = traffic_host_context(m)
        local_ips = set(host_to_device) | set(arp)
    except Exception:
        traffic_identities = None
    a = analyze_traffic(flows, window_seconds=86400, now=now, bucket_seconds=300,
                        local_ips=local_ips, limit=8)
    if traffic_identities is not None:
        a["identities"] = traffic_identities(
            a, host_to_device, arp, resolve_names=bool(m.settings.get("netflow_resolve_names")), now=now)
    base = "/traffic"
    params = {"exporter": dev.get("host") or "", "window": "3600"}
    full = (f'<a class="btn ghost" href="/traffic?{_e(urllib.parse.urlencode({"exporter": dev.get("host") or ""}))}">'
            'Open in Traffic Analytics</a>')
    return (f'<style>{TRAFFIC_CSS}</style>' + kpi_tiles(a, compact=True)
            + f'<div class="panel"><h3>Top sources</h3>{legend()}{sources_table(a, base, params, limit=8)}'
            + f'<h3>Top destinations</h3>{destinations_table(a, base, params, limit=8)}'
            + f'<h3>Services</h3>{services_table(a, base, params, limit=8)}<p>{full}</p></div>')
