"""Console shell, navigation and everyday workflow pages.

Holds the page shell (header, collapsible sidebar, phone menu, footer), the
sign-in page (including return-to-page and one-time first-admin setup), the
Devices home, the Add/Edit Device form with an explicit connection test, CSV
device import, global search, paged Audit / Run Log, and shared client-side
enhancements (sortable/filterable tables, tabs). Rendering never contacts
devices; only an explicit "Test connection" request does, and it saves nothing.
All dynamic text is HTML-escaped. Scripts run under the console CSP nonce.
"""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse

from .drivers import get_driver as _get_driver
from .drivers import platforms as _platforms
from .users import MIN_PASSWORD_LENGTH, validate_password
from .users import can as _can
from .web_ui import (
    _CSS, _DASH_JS, _DEVICE_TYPES, _THEME_JS, APP_VERSION, _dtypes, _fmt_ts,
    _is_managed_device, _q,
)


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


# --------------------------------------------------------------------------
# Shared presentation helpers
# --------------------------------------------------------------------------

def time_zone_label(now=None):
    """'CST (UTC+08:00)' for the server's local time zone, shown in the footer."""
    lt = time.localtime(now)
    off = time.strftime("%z", lt) or "+0000"
    return f"{time.strftime('%Z', lt) or 'local time'} (UTC{off[:3]}:{off[3:]})"


def safe_next_path(value):
    """Return a same-site path to continue to after sign-in, or '' if unsafe."""
    value = str(value or "").strip()
    if not value or len(value) > 2000 or not value.startswith("/") or value.startswith("//"):
        return ""
    if any(c in value for c in "\\\r\n\t") or any(ord(c) < 32 for c in value):
        return ""
    parts = urllib.parse.urlsplit(value)
    if parts.scheme or parts.netloc:
        return ""
    if parts.path in ("/login", "/logout", "/setup-admin") or parts.path.startswith("/api/"):
        return ""
    return value


def render_tabs(tabs, tabset_id="tabs"):
    """Server-rendered tabs. Without JavaScript every section is shown in order
    with an anchor bar; with JavaScript one section is shown at a time."""
    tabs = [(key, label, body) for key, label, body in tabs if body]
    if len(tabs) < 2:
        return "".join(body for _k, _l, body in tabs)
    bar = "".join(f'<a href="#tab-{_e(key)}" data-tab="{_e(key)}">{_e(label)}</a>'
                  for key, label, _b in tabs)
    panels = "".join(f'<section class="tab-panel" id="tab-{_e(key)}" data-tab="{_e(key)}">{body}</section>'
                     for key, _l, body in tabs)
    return f'<div class="tabset" id="{_e(tabset_id)}"><nav class="tabbar" aria-label="Sections">{bar}</nav>{panels}</div>'


UX_CSS = """
.account-form{max-width:520px}
[id^="workflow-"]{scroll-margin-top:90px}
.sidebar{padding:12px 12px}
.side-group{margin:0 0 4px}
.side-group>summary{list-style:none;cursor:pointer;display:flex;justify-content:space-between;align-items:center;padding:6px 8px;margin:0;border-radius:8px}
.side-group>summary::-webkit-details-marker{display:none}
.side-group>summary::after{content:"\\25B8";font-size:11px;color:var(--grey);transition:transform .15s}
.side-group[open]>summary::after{transform:rotate(90deg)}
.side-group>summary:hover{background:var(--row-alt)}
.side-group .nav-sidebar{gap:2px;margin:2px 0 8px}
.side-group .nav-sidebar a{padding:7px 12px}
.menu-toggle{display:none}
.top-search{display:flex;align-items:center}
.top-search input{width:260px;padding:7px 12px;margin:0}
.tabbar{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px;position:sticky;top:69px;z-index:5;background:var(--bg);padding:8px 0}
.tabbar a{padding:6px 14px;border:1px solid var(--border);border-radius:999px;color:var(--text);font-weight:600;text-decoration:none}
.tabbar a.on{background:var(--solid);border-color:var(--solid);color:#fff}
.tabs-on .tab-panel{display:none}
.tabs-on .tab-panel.on{display:block}
.tbl-tools{display:flex;gap:10px;align-items:center;margin:0 0 8px}
.tbl-tools input{max-width:320px;margin:0}
.tbl-tools .muted{font-size:13px}
th.sortable{cursor:pointer;user-select:none;white-space:nowrap}
th.sortable::after{content:" \\2195";opacity:.45;font-size:11px}
th.sortable[aria-sort=ascending]::after{content:" \\25B2";opacity:.9}
th.sortable[aria-sort=descending]::after{content:" \\25BC";opacity:.9}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.attention{list-style:none;margin:0;padding:0}
.attention li{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--line)}
.attention li:last-child{border-bottom:none}
.attention .badge{flex:none}
.cred-mode{display:flex;gap:18px;flex-wrap:wrap;margin:6px 0 10px}
.cred-mode label{font-weight:400;color:var(--text)}
.test-result{margin:10px 0 0}
.test-result li{margin:4px 0}
.hint{display:block;color:var(--grey);font-size:12px;font-weight:400;margin-top:2px}
.dash-kpis{margin-bottom:16px}
.pager{display:flex;gap:10px;align-items:center;margin-top:10px}
.setup-box{max-width:460px}
@media(max-width:760px){
  .app-shell{grid-template-rows:auto 1fr}
  .menu-toggle{display:inline-flex;margin:0 0 8px}
  html.js .sidebar:not(.open) .side-groups{display:none}
  .top-search input{width:100%}
  .top-search{order:5;width:100%}
  .tabbar{top:0}
}
"""

UX_JS = r"""
(function(){
  var d=document;
  // Phone menu
  var side=d.getElementById('sidebar'), tog=d.getElementById('menu-toggle');
  if(side&&tog){ tog.addEventListener('click',function(){ var o=side.classList.toggle('open'); tog.setAttribute('aria-expanded',o?'true':'false'); }); }
  // Remember collapsed/expanded sidebar groups
  try{
    var st=JSON.parse(localStorage.getItem('nc-side')||'{}');
    d.querySelectorAll('details.side-group').forEach(function(g){
      var k=g.getAttribute('data-group'); if(!k) return;
      if(k in st && !g.querySelector('a.active')) g.open=!!st[k];
      g.addEventListener('toggle',function(){ st[k]=g.open; try{localStorage.setItem('nc-side',JSON.stringify(st));}catch(e){} });
    });
  }catch(e){}
  // Tabs
  d.querySelectorAll('.tabset').forEach(function(ts){
    var links=ts.querySelectorAll('.tabbar a'), panels=ts.querySelectorAll('.tab-panel');
    if(!links.length) return;
    ts.classList.add('tabs-on');
    function show(key, push){
      var found=false;
      panels.forEach(function(p){ var on=p.getAttribute('data-tab')===key; p.classList.toggle('on',on); if(on) found=true; });
      if(!found){ key=links[0].getAttribute('data-tab'); panels[0].classList.add('on'); }
      links.forEach(function(a){ var on=a.getAttribute('data-tab')===key; a.classList.toggle('on',on); a.setAttribute('aria-current',on?'page':'false'); });
      if(push){ try{ history.replaceState(null,'','#tab-'+key); }catch(e){} }
    }
    links.forEach(function(a){ a.addEventListener('click',function(ev){ ev.preventDefault(); show(a.getAttribute('data-tab'),true); }); });
    var h=(location.hash||'').replace('#tab-','');
    show(h||links[0].getAttribute('data-tab'),false);
  });
  // Sortable + filterable tables
  var UNITS={b:1,kb:1e3,mb:1e6,gb:1e9,tb:1e12,kib:1024,mib:1048576,gib:1073741824,bps:1,kbps:1e3,mbps:1e6,gbps:1e9,k:1e3,m:1e6,g:1e9};
  function key(cell){
    if(!cell) return '';
    var raw=cell.getAttribute('data-sort'); if(raw!==null) { var n=parseFloat(raw); return isNaN(n)?raw.toLowerCase():n; }
    var t=(cell.textContent||'').trim();
    var m=t.match(/^#?(-?[\d,]*\.?\d+)\s*([a-zA-Z]{0,4})\b/);
    if(m && !/^\d{4}-\d\d-\d\d/.test(t) && !/^\d+\.\d+\.\d+/.test(t)){
      var v=parseFloat(m[1].replace(/,/g,'')); var u=(m[2]||'').toLowerCase();
      return v*(UNITS[u]||1);
    }
    return t.toLowerCase();
  }
  d.querySelectorAll('main table').forEach(function(tb){
    if(tb.classList.contains('no-enhance')||tb.querySelector('tr.devrow')) return;
    var rows=Array.prototype.slice.call(tb.rows); if(rows.length<3) return;
    var head=rows[0]; var ths=head.cells; if(!ths.length) return;
    for(var i=0;i<ths.length;i++){ if(ths[i].tagName!=='TH') return; }
    var data=rows.slice(1).filter(function(r){ return r.cells.length===ths.length; });
    if(data.length<2) return;
    var parent=data[0].parentNode;
    Array.prototype.forEach.call(ths,function(th,idx){
      if(!(th.textContent||'').trim()) return;
      th.classList.add('sortable'); th.tabIndex=0; th.setAttribute('aria-sort','none');
      function sort(){
        var dir=th.getAttribute('aria-sort')==='ascending'?'descending':'ascending';
        Array.prototype.forEach.call(ths,function(o){ if(o!==th&&o.classList.contains('sortable')) o.setAttribute('aria-sort','none'); });
        th.setAttribute('aria-sort',dir);
        var sorted=data.slice().sort(function(a,b){
          var x=key(a.cells[idx]), y=key(b.cells[idx]);
          var r=(typeof x==='number'&&typeof y==='number')?x-y:String(x).localeCompare(String(y),undefined,{numeric:true});
          return dir==='ascending'?r:-r;
        });
        sorted.forEach(function(r){ parent.appendChild(r); });
      }
      th.addEventListener('click',sort);
      th.addEventListener('keydown',function(ev){ if(ev.key==='Enter'||ev.key===' '){ ev.preventDefault(); sort(); } });
    });
    if(data.length>=10){
      var tools=d.createElement('div'); tools.className='tbl-tools';
      var inp=d.createElement('input'); inp.type='search'; inp.placeholder='Filter these rows'; inp.setAttribute('aria-label','Filter table rows');
      var cnt=d.createElement('span'); cnt.className='muted';
      tools.appendChild(inp); tools.appendChild(cnt);
      var anchor=tb.parentNode&&tb.parentNode.classList&&tb.parentNode.classList.contains('table-wrap')?tb.parentNode:tb;
      anchor.parentNode.insertBefore(tools,anchor);
      inp.addEventListener('input',function(){
        var q=inp.value.trim().toLowerCase(), shown=0;
        data.forEach(function(r){ var ok=!q||(r.textContent||'').toLowerCase().indexOf(q)>=0; r.hidden=!ok; if(ok) shown++; });
        cnt.textContent=q?(shown+' of '+data.length+' rows'):'';
      });
    }
  });
  // Add/Edit device: credential mode, SNMP fields, connection test
  var form=d.getElementById('device_form');
  if(form){
    function setDisabled(el,off){ if(!el) return; el.hidden=off; el.querySelectorAll('input,select,textarea').forEach(function(c){ c.disabled=off; }); }
    var modes=form.querySelectorAll('input[name=cred_mode]');
    function credMode(){
      var m='saved'; modes.forEach(function(r){ if(r.checked) m=r.value; });
      setDisabled(d.getElementById('cred_saved'), m!=='saved');
      setDisabled(d.getElementById('cred_manual'), m!=='manual');
      snmpFields();
    }
    var ver=form.querySelector('select[name=snmp_version]');
    function snmpFields(){
      var v=ver?ver.value:'';
      var manualOn=!(d.getElementById('cred_manual')||{}).hidden;
      form.querySelectorAll('[data-snmp]').forEach(function(el){
        var need=el.getAttribute('data-snmp');
        var on=manualOn && v!=='' && (need==='any'||need===v);
        setDisabled(el,!on);
      });
    }
    modes.forEach(function(r){ r.addEventListener('change',credMode); });
    if(ver) ver.addEventListener('change',snmpFields);
    if(modes.length) credMode(); else snmpFields();
    var btn=d.getElementById('test_conn'), out=d.getElementById('test_result');
    if(btn&&out){
      btn.addEventListener('click',function(){
        btn.disabled=true; out.textContent='Testing… this can take up to the SSH connect timeout.';
        var body=new URLSearchParams(new FormData(form));
        fetch('/device-test',{method:'POST',body:body,credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'}})
          .then(function(r){ return r.json(); })
          .then(function(j){
            out.textContent='';
            if(j.error){ out.textContent=j.error; return; }
            var ul=d.createElement('ul');
            (j.results||[]).forEach(function(x){
              var li=d.createElement('li'), b=d.createElement('span');
              b.className='badge '+(x.ok?'b-ok':'b-bad'); b.textContent=x.ok?'OK':'Failed';
              li.appendChild(b); li.appendChild(d.createTextNode(' '+x.check+': '+x.detail)); ul.appendChild(li);
            });
            out.appendChild(ul);
          })
          .catch(function(){ out.textContent='The test could not be run. Check that you are still signed in.'; })
          .then(function(){ btn.disabled=false; });
      });
    }
  }
  // CSV import: load a chosen file into the text box
  var file=d.getElementById('csv_file'), area=d.getElementById('csv_text');
  if(file&&area&&window.FileReader){
    file.addEventListener('change',function(){
      var f=file.files&&file.files[0]; if(!f) return;
      if(f.size>1048576){ alert('The file is larger than 1 MB.'); return; }
      var rd=new FileReader(); rd.onload=function(){ area.value=rd.result; }; rd.readAsText(f);
    });
  }
})();
"""

_NAV_DEFAULT_OPEN = {"Overview", "Monitor", "Inventory", "Changes"}


def nav_groups(role):
    admin = []
    if _can(role, "settings"):
        admin.append(("/settings", "Settings"))
    if _can(role, "manage_users"):
        admin.append(("/users", "Users"))
    if _can(role, "manage_devices"):
        admin.append(("/vault", "Vault"))
    admin += [("/audit", "Audit"), ("/mib", "MIB Library"), ("/help", "Help")]
    return [
        ("Overview", [("/dashboard", "Dashboard"), ("/search", "Search")]),
        ("Monitor", [("/alerts", "Alerts"), ("/incidents", "Incidents"), ("/traffic", "Traffic")]),
        ("Inventory", [("/", "Devices"), ("/groups", "Groups"), ("/endpoints", "Endpoints"),
                       ("/topology", "Topology"), ("/topology?view=l3", "Routing topology"), ("/dependencies", "Dependencies")]),
        ("Changes", [("/requests", "Change requests"), ("/operations", "Change workspace"),
                     ("/automation", "Scripts & quick runs"), ("/compliance", "Compliance & drift")]),
        ("Collection", [("/protocols", "Device Collection"), ("/snmp", "SNMP"), ("/runs", "Run Log"),
                        ("/diagnostics", "Diagnostics"), ("/traces", "Protocol Traces")]),
        ("Administration", admin),
    ]


def _nav_active(url, current_path):
    cur = urllib.parse.urlsplit(current_path or "")
    path_only = cur.path or "/"
    if urllib.parse.urlsplit(url).path == "/topology" and path_only == "/topology":
        routing = (urllib.parse.parse_qs(cur.query).get("view") or ["physical"])[0] == "l3"
        return ("view=l3" in url) == routing
    if url == "/requests":
        return path_only == "/requests" or path_only.startswith("/request")
    if url == "/vault":
        return path_only.startswith("/vault")
    if url == "/":
        return path_only in ("/", "/device", "/device-new", "/device-import", "/raw", "/diff")
    return path_only == (urllib.parse.urlsplit(url).path or "/")


def render_nav(groups, current_path):
    out = []
    for title, links in groups:
        if not links:
            continue
        items, active_here = [], False
        for url, label in links:
            on = _nav_active(url, current_path)
            active_here = active_here or on
            items.append(f'<a{" class=\"active\" aria-current=\"page\"" if on else ""} href="{_e(url)}">{_e(label)}</a>')
        is_open = title in _NAV_DEFAULT_OPEN or active_here
        out.append(f'<details class="side-group" data-group="{_e(title)}"{" open" if is_open else ""}>'
                   f'<summary class="sidebar-section-title">{_e(title)}</summary>'
                   f'<nav class="nav-sidebar">{"".join(items)}</nav></details>')
    return "".join(out)


# --------------------------------------------------------------------------
# First-admin setup (no users yet): one-time code from the service log
# --------------------------------------------------------------------------

_SETUP_LOCK = threading.RLock()  # re-entrant: error pages re-render while held
_SETUP = {"hash": "", "expires": 0.0}
SETUP_CODE_FILE = "first-admin-setup-code"
SETUP_CODE_TTL = 24 * 3600


def ensure_setup_code(manager, now=None):
    """Create (or reuse) a one-time setup code while no user exists. The code is
    written to the service log and to a 0600 file in the data directory; only its
    hash is kept in memory. Returns True when setup is available."""
    if manager.users.count() > 0:
        return False
    now = time.time() if now is None else now
    with _SETUP_LOCK:
        if _SETUP["hash"] and _SETUP["expires"] > now:
            return True
        code = "-".join(secrets.token_hex(3) for _ in range(3))
        _SETUP["hash"] = hashlib.sha256(code.encode()).hexdigest()
        _SETUP["expires"] = now + SETUP_CODE_TTL
        path = os.path.join(manager.paths.home, SETUP_CODE_FILE)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{code}\n")
            os.chmod(path, 0o600)
        except OSError:
            pass
        print(f"NetConfig first-time setup code: {code} "
              f"(valid 24 hours; also saved in {SETUP_CODE_FILE} in the data directory)",
              file=sys.stderr, flush=True)
    return True


def _check_setup_code(code, now=None):
    now = time.time() if now is None else now
    digest = hashlib.sha256(str(code or "").strip().lower().encode()).hexdigest()
    return bool(_SETUP["hash"]) and _SETUP["expires"] > now and secrets.compare_digest(digest, _SETUP["hash"])


def _consume_setup_code(manager):
    _SETUP["hash"], _SETUP["expires"] = "", 0.0
    try:
        os.remove(os.path.join(manager.paths.home, SETUP_CODE_FILE))
    except OSError:
        pass


_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,63}$")


# --------------------------------------------------------------------------
# CSV device import
# --------------------------------------------------------------------------

CSV_COLUMNS = ("name", "host", "port", "platform", "type", "tags", "ssh_secret", "enable_secret",
               "snmp_version", "snmp_secret", "netflow", "enabled", "config_command", "notes")
CSV_REQUIRED = ("name", "host")
CSV_MAX_BYTES = 1024 * 1024
CSV_MAX_ROWS = 2000
CSV_TEMPLATE = ("name,host,port,platform,type,tags,ssh_secret,enable_secret,snmp_version,"
                "snmp_secret,netflow,enabled,config_command,notes\n"
                "core-sw1,10.0.0.11,22,cisco_ios,network,core dc1,lab-admins,,v2c,lab-snmp,yes,yes,,Core switch\n"
                "web-01,10.0.1.20,22,generic,system,web,linux-ops,,,,no,yes,,\n")
_TRUE = {"1", "yes", "y", "true", "on"}
_FALSE = {"0", "no", "n", "false", "off", ""}


def parse_device_csv(text, manager):
    """Validate CSV rows for import. Returns (rows, header_error); each row is
    {"line", "values", "errors", "warnings"}. Never writes anything."""
    from .manager import validate_config_collect_command
    text = str(text or "")
    if len(text.encode("utf-8")) > CSV_MAX_BYTES:
        return [], "The CSV is larger than 1 MB."
    reader = csv.reader(io.StringIO(text.lstrip("﻿")))
    try:
        header = next(reader)
    except StopIteration:
        return [], "Paste or choose a CSV file first."
    except csv.Error as exc:
        return [], f"The CSV could not be read: {exc}"
    cols = [h.strip().lower() for h in header]
    missing = [c for c in CSV_REQUIRED if c not in cols]
    if missing:
        return [], "The first row must be a header that includes: " + ", ".join(missing) + "."
    unknown = [c for c in cols if c and c not in CSV_COLUMNS]
    platforms = set(_platforms())
    existing = {d["name"] for d in manager.inv.all()}
    vault_ok = manager.vault_ready()
    secrets_known = set()
    if vault_ok:
        try:
            secrets_known = set(manager.vault.list_secrets().keys())
        except Exception:
            vault_ok = False
    seen, rows = set(), []
    try:
        for idx, raw in enumerate(reader, start=2):
            if not any(str(c).strip() for c in raw):
                continue
            if len(rows) >= CSV_MAX_ROWS:
                return rows, f"Only the first {CSV_MAX_ROWS} rows can be imported at once."
            rec = {c: (raw[i].strip() if i < len(raw) else "") for i, c in enumerate(cols) if c in CSV_COLUMNS}
            errors, warnings = [], []
            name, host = rec.get("name", ""), rec.get("host", "")
            if not name:
                errors.append("name is empty")
            elif len(name) > 128 or any(ord(ch) < 32 for ch in name) or "/" in name:
                errors.append("name is too long or contains invalid characters")
            elif name in existing:
                errors.append("a device with this name already exists")
            elif name in seen:
                errors.append("name appears more than once in this file")
            seen.add(name)
            if not host:
                errors.append("host is empty")
            elif len(host) > 255 or any(ch.isspace() for ch in host):
                errors.append("host is not a valid name or address")
            try:
                port = int(rec.get("port") or 22)
                if not 1 <= port <= 65535:
                    raise ValueError
            except ValueError:
                errors.append("port must be 1-65535")
                port = 22
            platform = rec.get("platform") or "generic"
            if platform not in platforms:
                errors.append(f"unknown platform '{platform}'")
            types = [t for t in re.split(r"[;,\s]+", rec.get("type") or "network") if t]
            bad_types = [t for t in types if t not in ("network", "system", "application")]
            if bad_types:
                errors.append("type must be network, system and/or application")
            snmp_version = (rec.get("snmp_version") or "").lower()
            if snmp_version not in ("", "v2c", "v3"):
                errors.append("snmp_version must be empty, v2c or v3")
            for col in ("ssh_secret", "enable_secret", "snmp_secret"):
                ref = rec.get(col) or ""
                if ref and vault_ok and ref not in secrets_known:
                    errors.append(f"no vault secret named '{ref}' ({col})")
                elif ref and not vault_ok:
                    warnings.append(f"vault is locked, so '{ref}' could not be checked")
            if snmp_version and not rec.get("snmp_secret"):
                warnings.append("SNMP is set but no snmp_secret is given")
            flags = {}
            for col, default in (("netflow", False), ("enabled", True)):
                val = (rec.get(col) or "").lower()
                if val in _TRUE:
                    flags[col] = True
                elif val in _FALSE:
                    flags[col] = default if val == "" else False
                else:
                    errors.append(f"{col} must be yes or no")
                    flags[col] = default
            try:
                cmd = validate_config_collect_command(rec.get("config_command") or "")
            except ValueError as exc:
                errors.append(f"config_command: {exc}")
                cmd = ""
            values = {"name": name, "host": host, "port": port, "platform": platform,
                      "device_type": ",".join(dict.fromkeys(types or ["network"])),
                      "tags": [t for t in re.split(r"[;,\s]+", rec.get("tags") or "") if t],
                      "secret_ref": rec.get("ssh_secret") or None, "enable_ref": rec.get("enable_secret") or None,
                      "snmp_version": snmp_version, "snmp_ref": rec.get("snmp_secret") or None,
                      "netflow": flags["netflow"], "enabled": flags["enabled"],
                      "config_collect_command": cmd, "notes": rec.get("notes") or ""}
            rows.append({"line": idx, "values": values, "errors": errors, "warnings": warnings})
    except csv.Error as exc:
        return rows, f"The CSV could not be read: {exc}"
    note = ("Ignored unknown column(s): " + ", ".join(unknown) + ".") if unknown else ""
    return rows, note


# --------------------------------------------------------------------------
# The mixin
# --------------------------------------------------------------------------

class WebUxMixin:
    """Shell, navigation and everyday workflow pages for the Console."""

    # ---- shell -------------------------------------------------------------
    def _nav(self, sess, current_path=""):
        return render_nav(nav_groups(sess["role"]), current_path)

    def _topright(self, sess):
        vault = ('<span class="vault-open">● vault unlocked</span>' if self.manager.vault_ready()
                 else '<span class="vault-lock">● vault locked</span>')
        if not self.manager.vault_ready() and _can(sess["role"], "unlock_vault"):
            nxt = safe_next_path(getattr(self, "path", "/")) if getattr(self, "command", "GET") == "GET" else "/"
            vault += '<a href="/vault?next=' + _q(nxt or "/") + '">Unlock vault</a>'
        return ('<div class="top-right">'
                '<form method=get action="/search" class="top-search" role="search">'
                '<input type=search name=q placeholder="Search devices, IPs, MACs, alerts" '
                'aria-label="Search devices, IP addresses, MAC addresses, alerts and incidents"></form>'
                f'{vault}'
                f'<a class="who" href="/account" title="Your account"><b>{_e(sess["username"])}</b><span class="role">{_e(sess["role"])}</span></a>'
                '<button type=button id="theme-toggle" class="ghost theme-toggle" aria-label="Toggle color theme" '
                'aria-pressed="false">Dark theme</button>'
                f'<form method=post action="/logout" class="inline-form">{self._csrf_field()}'
                '<button class=ghost>Sign out</button></form></div>')

    def _page(self, title, inner, sess, flash=None):
        from .web_forms import take_feedback
        queued = take_feedback(self, sess)
        flash = flash or queued
        f = f'<div class="flash">{_e(flash)}</div>' if flash else ""
        right = self._topright(sess) if sess else ""
        shell = ""
        if sess:
            shell = ('<aside class="sidebar" id="sidebar">'
                     '<button type=button id="menu-toggle" class="ghost menu-toggle" aria-expanded="false" '
                     'aria-controls="side-groups">Menu</button>'
                     f'<div class="side-groups" id="side-groups">{self._nav(sess, self.path)}</div></aside>')
        return (f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{_e(title)} · NetConfig</title><style>{_CSS}{UX_CSS}</style><script>document.documentElement.classList.add('js');</script>{_THEME_JS}</head><body>
<header><div class="brand"><span class="logo">NC</span><span class="appname">Net<span>Config</span> · Network Configuration</span></div>{right}</header>
<div class="app-shell">{shell}<div class="content-shell"><main><h1>{_e(title)}</h1>{f}{inner}</main><footer class="footer"><span>NetConfig v{APP_VERSION}</span><span>Times shown in {_e(time_zone_label())} · Internal — Restricted</span></footer></div></div><script>{UX_JS}</script></body></html>""")

    # ---- sign-in -----------------------------------------------------------
    def _login_page(self, error=None, status=200):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path or "").query)
        nxt = safe_next_path((q.get("next") or [""])[0])
        head = (f'<!doctype html><html><head><meta charset=utf-8>'
                f'<meta name=viewport content="width=device-width,initial-scale=1">'
                f'<title>Sign in · NetConfig</title><style>{_CSS}{UX_CSS}</style>{_THEME_JS}</head><body>'
                '<div class="login-wrap"><div class="panel login">'
                '<div class="brand">Net<span>Config</span></div>'
                f'<div class="sub">Security Operations · v{APP_VERSION}</div>')
        err = f'<div class="err">{_e(error)}</div>' if error else ""
        if self.manager.users.count() == 0:
            ensure_setup_code(self.manager)
            body = (head + '<h2>First-time setup</h2>'
                    '<p class="muted">No users exist yet. Create the first administrator with the one-time '
                    'setup code. It is printed in the NetConfig service log and saved in '
                    f'<code>{SETUP_CODE_FILE}</code> in the data directory.</p>{err}'
                    '<form method=post action="/setup-admin" class="setup-box">'
                    '<input name=setup_code placeholder="Setup code" autocomplete=off autofocus required>'
                    '<input name=username placeholder="Administrator username" autocomplete=username required>'
                    '<input name=fullname placeholder="Full name (optional)">'
                    f'<input type=password name=password placeholder="Password ({MIN_PASSWORD_LENGTH}+ characters)" '
                    f'autocomplete=new-password minlength={MIN_PASSWORD_LENGTH} required>'
                    '<input type=password name=password2 placeholder="Repeat password" autocomplete=new-password required>'
                    '<button style="width:100%">Create administrator</button></form>'
                    '<p class="muted">Alternatively, on the server: <code>netconfig user add &lt;name&gt; '
                    '--role admin</code></p></div></div></body></html>')
            return self._send(body, status)
        hidden = f'<input type=hidden name=next value="{_e(nxt)}">' if nxt else ""
        body = (head + err + '<form method=post action="/login">' + hidden
                + '<input type=text name=username placeholder="Username" autofocus autocomplete=username>'
                '<input type=password name=password placeholder="Password" autocomplete=current-password>'
                '<button style="width:100%">Sign in</button></form>'
                + ('<p class="muted">Sign in to continue where you left off.</p>' if nxt else "")
                + '<div class="muted" style="text-align:center;margin-top:14px">'
                'Local console · bind 127.0.0.1 · front with WAF for TLS</div></div></div></body></html>')
        return self._send(body, status)

    def _do_setup_admin(self, form):
        from .web import _LOGIN_THROTTLE
        from .web_security_runtime import create_managed_session

        def g(k):
            return str((form.get(k) or [""])[0])
        ip = self._client_ip()
        if self.manager.users.count() > 0:
            return self._redirect("/login")
        retry = _LOGIN_THROTTLE.retry_after(ip, "first-admin-setup")
        if retry:
            return self._send("<!doctype html><html><body><h1>Too many attempts</h1><p>Try again shortly.</p></body></html>",
                              429, headers=[("Retry-After", str(retry))])
        username, pw = g("username").strip(), g("password")
        with _SETUP_LOCK:
            if self.manager.users.count() > 0:
                return self._redirect("/login")
            if not _check_setup_code(g("setup_code")):
                _LOGIN_THROTTLE.failure(ip, "first-admin-setup")
                self.manager.db.audit("(setup)", "first_admin_setup_failure", "console", f"source={ip}")
                return self._login_page(error="The setup code is not valid. Check the service log.", status=400)
            if not _USERNAME_RE.match(username):
                return self._login_page(error="Use a username of letters, digits, '.', '_', '@' or '-'.", status=400)
            if pw != g("password2"):
                return self._login_page(error="The passwords do not match.", status=400)
            try:
                validate_password(pw, username)
                self.manager.users.create(username, pw, role="admin", fullname=g("fullname").strip()[:200])
            except ValueError as exc:
                return self._login_page(error=str(exc), status=400)
            _consume_setup_code(self.manager)
        _LOGIN_THROTTLE.success(ip, "first-admin-setup")
        self.manager.db.audit(username, "first_admin_setup", "console", f"source={ip}")
        token, _rec = create_managed_session(self.manager.users.get(username))
        secure = "; Secure" if (self.manager.settings.get("cookie_secure") or self.tls_enabled) else ""
        return self._redirect("/", headers=[("Set-Cookie", f"ncsid={token}; HttpOnly; SameSite=Strict; Path=/{secure}")])

    # ---- Devices home --------------------------------------------------------
    def _dashboard(self, sess, flash=None):
        m = self.manager
        devices = m.inv.all()
        metas = {d["device"]: d for d in m.store.devices()}
        facts = m.inv.all_facts()
        alerts = {}
        try:
            for a in m.alert_lifecycle.list(limit=2000):
                if a.get("state") in ("OPEN", "ACKNOWLEDGED") and a.get("device"):
                    c = alerts.setdefault(a["device"], [0, 0])
                    c[0] += 1
                    c[1] += 1 if str(a.get("severity") or "").upper() == "CRITICAL" else 0
        except Exception:
            alerts = {}

        def make_row(d):
            managed = _is_managed_device(d)
            meta = metas.get(d["name"], {})
            last = _fmt_ts(meta.get("last_collected")) if managed else "—"
            has_cfg = managed and m.store.current(d["name"]) is not None
            st = (('<span class="badge b-ok">stored</span>' if has_cfg
                   else '<span class="badge b-dim">none</span>') if managed
                  else '<span class="muted">—</span>')
            drift = m.store.drift(d["name"]) if has_cfg else {"baselined": False, "drifted": False}
            if drift["baselined"]:
                st += (' <span class="badge b-bad">drift</span>' if drift["drifted"]
                       else ' <span class="badge b-ok">baseline</span>')
            en = '' if d["enabled"] else ' <span class="badge b-dim">disabled</span>'
            fx = facts.get(d["name"], {}) if managed else {}
            snmp = ""
            if fx:
                snmp = ('<span class="badge b-ok">up</span>' if fx.get("reachable")
                        else '<span class="badge b-bad">unreach</span>')
                if fx.get("sysname"):
                    snmp += f' <span class="muted">{_e(fx["sysname"])}</span>'
            collect_btn = ""
            if managed and _can(sess["role"], "collect"):
                collect_btn = (f'<form method=post action="/collect" style="display:inline">'
                               f'{self._csrf_field()}<input type=hidden name=name value="{_e(d["name"])}">'
                               f'<button style="padding:4px 12px">Collect</button></form>')
            typ = " ".join(f'<span class="badge b-dim">{t.capitalize()}</span>' for t in sorted(_dtypes(d)))
            tags = d.get("tags") or []
            blob = " ".join([d["name"], d["host"]] + [str(t) for t in tags]).lower()
            address = f'{_e(d["host"])}:{d["port"]}' if managed else _e(d["host"])
            platform = _e(d["platform"]) if managed else '<span class="muted">—</span>'
            n_alerts, n_crit = alerts.get(d["name"], (0, 0))
            alert_cell = ('<span class="muted">—</span>' if not n_alerts else
                          f'<a href="/alerts?view=active"><span class="badge {"b-bad" if n_crit else "b-chg"}">'
                          f'{n_alerts} open</span></a>')
            return (f'<tr class="devrow" data-search="{_e(blob)}">'
                    f'<td><a href="/device?name={_q(d["name"])}">{_e(d["name"])}</a>{en}</td>'
                    f'<td class="muted">{address}</td><td>{typ}</td><td>{platform}</td>'
                    f'<td>{st}</td><td>{snmp or "<span class=muted>—</span>"}</td><td>{alert_cell}</td>'
                    f'<td class="muted">{last}</td><td class="right">{collect_btn}</td></tr>')

        thead = ("<table><tr><th>Device</th><th>Address</th><th>Type</th><th>Platform</th>"
                 "<th>Config</th><th>SNMP</th><th>Alerts</th><th>Last collected</th><th></th></tr>")
        by_type = {"network": [], "system": [], "application": []}
        for d in devices:
            for t in _dtypes(d):
                if t in by_type:
                    by_type[t].append(d)
        groups_html = ""
        for t, label in (("network", "Network"), ("system", "System"), ("application", "Application")):
            ds = by_type[t]
            if ds:
                groups_html += (f'<details class="devgroup" open>'
                                f'<summary>{label} · <span class="devcount">{len(ds)}</span></summary>'
                                f'{thead}{"".join(make_row(d) for d in ds)}</table></details>')
        can_manage = _can(sess["role"], "manage_devices")
        if devices:
            search_box = ('<div class="panel" style="padding:10px 14px">'
                          '<input id="devsearch" type="search" autocomplete="off" '
                          'placeholder="Search devices by name, IP address, or tag…" '
                          'style="width:100%;box-sizing:border-box;padding:9px 12px;font-size:15px"></div>')
            listing = groups_html + '<p id="devnoresults" class="muted" hidden>No devices match your search.</p>'
        else:
            search_box = ""
            listing = ('<p class="muted">No devices yet.' + (
                ' Use <b>Add device</b> for one device, or <b>Import CSV</b> to add many at once.'
                if can_manage else ' Ask an approver or administrator to add devices.') + '</p>')
        vault_panel = ""
        if not m.vault_ready() and _can(sess["role"], "unlock_vault"):
            vault_panel = ('<div class="panel"><h2>Vault locked</h2>'
                           '<p class="muted">Device credentials are needed to collect, run jobs, or poll SNMP. '
                           'Unlock for this process:</p>'
                           f'<form method=post action="/unlock-vault" class="row">{self._csrf_field()}'
                           '<input type=password name=master placeholder="Vault master password">'
                           '<div style="flex:0"><button>Unlock</button></div></form></div>')
        actions = []
        if can_manage:
            actions.append('<a class="btn" href="/device-new">+ Add device</a>')
            actions.append('<a class="btn ghost" href="/device-import">Import CSV</a>')
        if _can(sess["role"], "collect"):
            actions.append(f'<form method=post action="/collect" class="inline-form">{self._csrf_field()}'
                           '<input type=hidden name=all value=1><button>Collect all enabled</button></form>')
        header_actions = ('<div style="margin-left:auto;display:flex;gap:10px;flex-wrap:wrap">'
                          + "".join(actions) + '</div>') if actions else ""
        inner = (f'{vault_panel}{search_box}<div class="panel">'
                 '<div style="display:flex;align-items:center;margin-bottom:12px;gap:10px;flex-wrap:wrap">'
                 f'<h2 style="border:none;margin:0">Inventory · {len(devices)} devices</h2>{header_actions}</div>'
                 f'{listing}</div>{_DASH_JS}')
        self._send(self._page("Devices", inner, sess, flash=flash))

    # ---- Audit / Run Log with paging ----------------------------------------
    _PAGE_SIZE = 100

    def _page_number(self, q):
        try:
            return max(1, min(int((q.get("page") or ["1"])[0]), 10000))
        except (TypeError, ValueError):
            return 1

    def _pager(self, base, page, has_more):
        if page == 1 and not has_more:
            return ""
        newer = (f'<a class="btn ghost" href="{base}?page={page - 1}">← Newer</a>' if page > 1 else "")
        older = (f'<a class="btn ghost" href="{base}?page={page + 1}">Older →</a>' if has_more else "")
        return f'<div class="pager">{newer}<span class="muted">Page {page}</span>{older}</div>'

    def _audit_page(self, sess, q=None):
        page = self._page_number(q or {})
        size = self._PAGE_SIZE
        rows_data = self.manager.db.recent_audit(size + 1, offset=(page - 1) * size)
        has_more = len(rows_data) > size
        rows = "".join(
            f'<tr><td class=muted>{_fmt_ts(a["ts"])}</td><td>{_e(a["actor"])}</td>'
            f'<td><span class="badge b-brass">{_e(a["action"])}</span></td>'
            f'<td class=muted>{_e(a["target"])}</td><td class=muted>{_e(a["detail"])}</td></tr>'
            for a in rows_data[:size])
        inner = ('<div class="panel"><table><tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Detail</th></tr>'
                 f'{rows or "<tr><td colspan=5 class=muted>no audit entries</td></tr>"}</table>'
                 f'{self._pager("/audit", page, has_more)}</div>')
        self._send(self._page("Audit Trail", inner, sess))

    def _runs_page(self, sess, q=None):
        page = self._page_number(q or {})
        size = self._PAGE_SIZE
        runs = self.manager.inv.recent_runs(size + 1, offset=(page - 1) * size)
        has_more = len(runs) > size
        rows = ""
        for r in runs[:size]:
            st = '<span class="badge b-ok">ok</span>' if r["ok"] else '<span class="badge b-bad">error</span>'
            ch = '<span class="badge b-chg">changed</span>' if r["changed"] else ""
            rows += (f'<tr><td class="muted">{_fmt_ts(r["ts"])}</td><td>{_e(r["device"])}</td>'
                     f'<td>{st} {ch}</td><td class="muted">{_e(r["message"])}</td></tr>')
        inner = ('<div class="panel"><table><tr><th>Time</th><th>Device</th><th>Result</th><th>Message</th></tr>'
                 f'{rows or "<tr><td class=muted colspan=4>no runs yet</td></tr>"}</table>'
                 f'{self._pager("/runs", page, has_more)}</div>')
        self._send(self._page("Run Log", inner, sess))

    # ---- Global search ---------------------------------------------------------
    # ---- Account (every signed-in user) ---------------------------------------
    def _account_page(self, sess, error=None, status=200):
        u = self.manager.users.get(sess["username"])
        if not u:
            body = ('<div class="panel"><h2>Account</h2><p class="muted">This session is not linked to a '
                    'local user account, so its password cannot be changed here.</p></div>')
            return self._send(self._page("Account", body, sess), status)
        last = u.get("last_login")
        last_txt = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "—"
        err = f'<div class="err">{_e(error)}</div>' if error else ""
        body = (f'<div class="panel"><h2>Your account</h2><table>'
                f'<tr><th>Username</th><td>{_e(u["username"])}</td></tr>'
                f'<tr><th>Role</th><td>{_e(u["role"])}</td></tr>'
                f'<tr><th>Last sign-in</th><td>{_e(last_txt)}</td></tr></table>'
                '<p class="muted">Roles are changed by an administrator on the Users page.</p></div>'
                f'<div class="panel"><h2>Change password</h2>{err}'
                f'<form method=post action="/account-password" class="account-form" autocomplete=off>{self._csrf_field()}'
                '<label>Current password</label><input type=password name=current_password required autocomplete=current-password>'
                f'<label>New password</label><input type=password name=new_password required minlength={MIN_PASSWORD_LENGTH} autocomplete=new-password>'
                '<label>Confirm new password</label><input type=password name=confirm_password required autocomplete=new-password>'
                f'<p class="hint">At least {MIN_PASSWORD_LENGTH} characters. Changing it signs out your other sessions.</p>'
                '<button>Change password</button></form></div>')
        return self._send(self._page("Account", body, sess), status)

    def _do_account_password(self, form, sess):
        from .web import _LOGIN_THROTTLE, _create_managed_session, _SESSIONS, _SESSIONS_LOCK
        username = sess["username"]
        if not self.manager.users.get(username):
            return self._account_page(sess, error="This session has no local user account.", status=400)
        current = (form.get("current_password") or [""])[0]
        new = (form.get("new_password") or [""])[0]
        confirm = (form.get("confirm_password") or [""])[0]
        ip = self._client_ip()
        retry = _LOGIN_THROTTLE.retry_after(ip, username)
        if retry:
            return self._account_page(sess, error=f"Too many failed attempts. Try again in {int(retry)} seconds.", status=429)
        if not self.manager.users.verify(username, current):
            _LOGIN_THROTTLE.failure(ip, username)
            self.manager.db.audit(username, "password_change_failure", "console", f"source={ip}")
            return self._account_page(sess, error="Current password is incorrect.", status=400)
        _LOGIN_THROTTLE.success(ip, username)
        try:
            if new != confirm:
                raise ValueError("The new passwords do not match.")
            if new == current:
                raise ValueError("Choose a password different from the current one.")
            validate_password(new, username)
            self.manager.users.set_password(username, new)
        except ValueError as exc:
            return self._account_page(sess, error=str(exc), status=400)
        self.manager.db.audit(username, "password_change", "console", f"source={ip}")
        # The password change invalidates every session of this user (auth
        # fingerprint); give this browser a fresh one so it stays signed in.
        old_token, _ = self._session()
        token, record = _create_managed_session(self.manager.users.get(username))
        record["operation_feedback"] = {"target": "/account", "message": "Password changed. Other sessions were signed out.",
                                        "expires": time.time() + 120}
        with _SESSIONS_LOCK:
            _SESSIONS.pop(old_token, None)
        secure = "; Secure" if (self.manager.settings.get("cookie_secure") or self.tls_enabled) else ""
        return self._redirect("/account", headers=[("Set-Cookie", f"ncsid={token}; HttpOnly; SameSite=Strict; Path=/{secure}")])

    def _search_page(self, q, sess):
        query = str((q.get("q") or [""])[0]).strip()[:120]
        needle = query.lower()
        m = self.manager
        sections = []
        if len(needle) >= 2:
            devs = [d for d in m.inv.all()
                    if needle in " ".join([d["name"], d.get("host") or "", d.get("platform") or "",
                                            " ".join(map(str, d.get("tags") or [])),
                                            d.get("notes") or ""]).lower()][:50]
            if devs:
                sections.append(("Devices", "<table><tr><th>Device</th><th>Address</th><th>Platform</th><th>Tags</th></tr>" + "".join(
                    f'<tr><td><a href="/device?name={_q(d["name"])}">{_e(d["name"])}</a></td><td>{_e(d["host"])}</td>'
                    f'<td>{_e(d["platform"])}</td><td>{_e(", ".join(map(str, d.get("tags") or [])))}</td></tr>'
                    for d in devs) + "</table>"))
            addr_rows, seen = [], set()
            try:
                for ep in m.endpoint_inventory(query=query)[:50]:
                    ips = list(ep.get("ipv4") or []) + list(ep.get("ipv6") or [])
                    att = ep.get("attachment") or ep.get("observed_location") or {}
                    key = (ep.get("mac") or "", tuple(ips))
                    seen.add(key)
                    addr_rows.append(
                        f'<tr><td>{_e(", ".join(ips)) or "—"}</td><td><code>{_e(ep.get("mac") or "")}</code></td>'
                        f'<td>{_e(att.get("device") or "")} {_e(att.get("ifdescr") or "")}</td>'
                        f'<td>{_e(ep.get("status") or "")}</td></tr>')
            except Exception:
                pass
            for ip, row in m.db.arp_index().items():
                if len(addr_rows) >= 50:
                    break
                mac = row.get("mac") or ""
                if (needle in ip.lower() or needle in mac.lower()) and (mac, (ip,)) not in seen:
                    addr_rows.append(f'<tr><td>{_e(ip)}</td><td><code>{_e(mac)}</code></td>'
                                     f'<td>learned on {_e(row.get("device") or "")}</td><td>ARP</td></tr>')
            if addr_rows:
                sections.append(("IP and MAC addresses",
                                 "<table><tr><th>IP address</th><th>MAC address</th><th>Where</th><th>Source</th></tr>"
                                 + "".join(addr_rows) + "</table>"
                                 + f'<p><a href="/traffic?view=sources&q={_q(query)}">See traffic for “{_e(query)}”</a></p>'))
            try:
                al = [a for a in m.alert_lifecycle.list(limit=1000)
                      if needle in " ".join(str(a.get(k) or "") for k in ("device", "event_type", "message")).lower()][:30]
            except Exception:
                al = []
            if al:
                sections.append(("Alerts", "<table><tr><th>Severity</th><th>State</th><th>Device</th><th>Message</th><th>Last seen</th></tr>" + "".join(
                    f'<tr><td>{_e(a.get("severity"))}</td><td>{_e(a.get("state"))}</td><td>{_e(a.get("device"))}</td>'
                    f'<td><a href="/alerts?view=active">{_e(a.get("message"))}</a></td><td>{_fmt_ts(a.get("last_ts"))}</td></tr>'
                    for a in al) + "</table>"))
            try:
                inc = [i for i in m.incidents.list(limit=500)
                       if needle in " ".join(str(i.get(k) or "") for k in ("incident_key", "title", "summary")).lower()][:30]
            except Exception:
                inc = []
            if inc:
                sections.append(("Incidents", "<table><tr><th>Incident</th><th>Title</th><th>Severity</th><th>Status</th></tr>" + "".join(
                    f'<tr><td><a href="/incident?ref={_q(i["incident_key"])}">{_e(i["incident_key"])}</a></td>'
                    f'<td>{_e(i.get("title"))}</td><td>{_e(i.get("severity"))}</td><td>{_e(i.get("status"))}</td></tr>'
                    for i in inc) + "</table>"))
            groups = [g for g in m.inv.groups() if needle in str(g.get("name") or "").lower()][:30]
            if groups:
                sections.append(("Groups", "<ul>" + "".join(
                    f'<li><a href="/groups">{_e(g["name"])}</a></li>' for g in groups) + "</ul>"))
        form = ('<div class="panel"><form method=get action="/search" class="row">'
                f'<div><label>Search</label><input name=q value="{_e(query)}" autofocus '
                'placeholder="Device name, IP address, MAC address, tag, alert or incident text"></div>'
                '<div style="flex:0;align-self:end"><button>Search</button></div></form>'
                '<p class="muted">Searches saved records only; it does not contact devices.</p></div>')
        if len(needle) < 2:
            results = '<div class="panel"><p class="muted">Type at least two characters.</p></div>' if query else ""
        elif not sections:
            results = f'<div class="panel"><p>No matches for “{_e(query)}”.</p></div>'
        else:
            results = "".join(f'<div class="panel"><h2>{_e(t)}</h2>{b}</div>' for t, b in sections)
        self._send(self._page("Search", form + results, sess))

    # ---- CSV import ----------------------------------------------------------------
    def _device_import_page(self, q, sess, rows=None, text="", note="", status=200):
        if not _can(sess["role"], "manage_devices"):
            return self._send(self._page("Import devices", '<div class="err">Not permitted.</div>', sess), 403)
        if (q.get("template") or [""])[0]:
            return self._send(CSV_TEMPLATE, 200, "text/csv; charset=utf-8",
                              headers=[("Content-Disposition", 'attachment; filename="netconfig-devices.csv"')])
        cols = "".join(f"<code>{c}</code> " for c in CSV_COLUMNS if c not in CSV_REQUIRED)
        intro = ('<div class="panel"><h2>Import devices from CSV</h2>'
                 '<p>Add many devices at once. The first row must be a header. Required columns: '
                 '<code>name</code> and <code>host</code>. Optional: ' + cols + '</p>'
                 '<p class="muted">Credentials are referenced by vault secret name (<code>ssh_secret</code>, '
                 '<code>snmp_secret</code>, <code>enable_secret</code>); passwords are never read from the file. '
                 '<code>type</code> is network, system and/or application; <code>netflow</code> and '
                 '<code>enabled</code> are yes/no. Existing device names are not changed.</p>'
                 '<p><a class="btn ghost" href="/device-import?template=1">Download a template</a></p></div>')
        form = ('<div class="panel"><form method=post action="/device-import">'
                f'{self._csrf_field()}<input type=hidden name=action value=preview>'
                '<label>Choose a CSV file</label><input type=file id=csv_file accept=".csv,text/csv">'
                '<label>…or paste CSV text</label>'
                f'<textarea id=csv_text name=csv rows=10 spellcheck=false>{_e(text)}</textarea>'
                '<button>Check rows</button> <span class="muted">Nothing is saved until you confirm.</span>'
                '</form></div>')
        preview = ""
        if note:
            preview += f'<div class="panel"><p class="err">{_e(note)}</p></div>' if not rows else \
                f'<div class="panel"><p class="muted">{_e(note)}</p></div>'
        if rows:
            ok = [r for r in rows if not r["errors"]]
            body = "".join(
                f'<tr><td>{r["line"]}</td><td>{_e(r["values"]["name"])}</td><td>{_e(r["values"]["host"])}</td>'
                f'<td>{_e(r["values"]["platform"])}</td><td>{_e(r["values"]["device_type"])}</td>'
                f'<td>{"<span class=\"badge b-bad\">will be skipped</span>" if r["errors"] else "<span class=\"badge b-ok\">ready</span>"}</td>'
                f'<td>{_e("; ".join(r["errors"] + r["warnings"]))}</td></tr>' for r in rows)
            confirm = ""
            if ok:
                confirm = ('<form method=post action="/device-import">'
                           f'{self._csrf_field()}<input type=hidden name=action value=create>'
                           f'<textarea name=csv hidden>{_e(text)}</textarea>'
                           f'<button>Add {len(ok)} device{"s" if len(ok) != 1 else ""}</button></form>')
            preview += (f'<div class="panel"><h2>Check result · {len(ok)} ready, {len(rows) - len(ok)} with problems</h2>'
                        '<table><tr><th>Line</th><th>Name</th><th>Host</th><th>Platform</th><th>Type</th>'
                        f'<th>Status</th><th>Details</th></tr>{body}</table>{confirm}</div>')
        return self._send(self._page("Import devices", intro + preview + form, sess), status)

    def _do_device_import(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._send(self._page("Import devices", '<div class="err">Not permitted.</div>', sess), 403)
        text = str((form.get("csv") or [""])[0])
        action = str((form.get("action") or ["preview"])[0])
        rows, note = parse_device_csv(text, self.manager)
        if action != "create" or not rows:
            return self._device_import_page({}, sess, rows=rows, text=text, note=note,
                                            status=200 if rows else 400)
        created = 0
        for r in rows:
            if r["errors"] or self.manager.inv.get(r["values"]["name"]):
                continue
            v = r["values"]
            application_only = set(v["device_type"].split(",")) == {"application"}
            self.manager.inv.upsert(
                name=v["name"], host=v["host"], port=22 if application_only else v["port"],
                platform="generic" if application_only else v["platform"], device_type=v["device_type"],
                secret_ref="" if application_only else v["secret_ref"],
                enable_ref="" if application_only else v["enable_ref"],
                use_key=False, legacy=False, scrub=False, enabled=v["enabled"],
                netflow=False if application_only else v["netflow"], monitor_ports="", monitor_urls="",
                config_collect_command="" if application_only else v["config_collect_command"],
                tags=v["tags"], notes=v["notes"],
                snmp_version="" if application_only else v["snmp_version"],
                snmp_ref="" if application_only else v["snmp_ref"])
            self.manager.db.audit(sess["username"], "device_import", v["name"], v["host"])
            created += 1
        skipped = len(rows) - created
        return self._dashboard(sess, flash=f"Imported {created} device(s)" + (f"; {skipped} skipped." if skipped else "."))

    # ---- Add / edit device -------------------------------------------------------
    def _device_form(self, q, sess, draft=None, flash=None, status=200):
        if not _can(sess["role"], "manage_devices"):
            return self._send(self._page("Device", '<div class="err">Not permitted.</div>', sess), 403)
        name = (q.get("name") or [""])[0]
        d = self.manager.inv.get(name) if name else None
        editing = d is not None
        if draft is not None:
            d = dict(d or {})
            d.setdefault("platform", "generic")
            for k in ("host", "port", "platform", "notes", "monitor_ports", "monitor_urls", "config_collect_command", "snmp_version", "secret_ref", "snmp_ref", "enable_ref"):
                if k in draft:
                    d[k] = draft[k][0]
            d["device_type"] = ",".join(draft.get("device_type", ["network"]))
            d["tags"] = (draft.get("tags", [""])[0]).replace(",", " ").split()
            for k in ("use_key", "legacy", "scrub", "enabled", "netflow"):
                d[k] = bool(draft.get(k))
        title = f"Edit {name}" if editing else "Add device"
        plats = "".join(f'<option value="{p}"{" selected" if d and d["platform"] == p else ""}>{p}</option>'
                        for p in _platforms())
        cur_types = _dtypes(d) if d else {"network"}
        type_checks = "".join(
            f'<label style="font-weight:400;margin-right:16px;display:inline-block">'
            f'<input type=checkbox name=device_type value="{val}" style="width:auto"'
            f'{" checked" if val in cur_types else ""}> {lab}</label>' for val, lab in _DEVICE_TYPES)
        snmp_opts = "".join(
            f'<option value="{val}"{" selected" if d and (d.get("snmp_version") or "") == val else ""}>{lab}</option>'
            for val, lab in (("", "none"), ("v2c", "v2c"), ("v3", "v3")))

        def v(k, default=""):
            return _e(d[k]) if d and d.get(k) is not None else default

        def chk(k):
            return "checked" if d and d.get(k) else ""
        vault_ready = self.manager.vault_ready()
        snmp_sec, ssh_sec = {}, {}
        if d and vault_ready:
            for ref_key, target in (("snmp_ref", snmp_sec), ("secret_ref", ssh_sec)):
                if d.get(ref_key):
                    try:
                        target.update(self.manager.vault.get_secret(d[ref_key]))
                    except KeyError:
                        pass

        def sv(k):
            if draft is not None and k in draft:
                return _e(draft[k][0])
            return _e(snmp_sec.get(k, ""))

        def sset(k):
            return " ✓ set" if snmp_sec.get(k) else ""

        def uv(k):
            field = "ssh_username" if k == "username" else k
            if draft is not None and field in draft:
                return _e(draft[field][0])
            return _e(ssh_sec.get(k, ""))

        def uset(k):
            return " ✓ set" if ssh_sec.get(k) else ""

        def proto_opts(opts, cur):
            return '<option value="">—</option>' + "".join(
                f'<option value="{val}"{" selected" if cur == val else ""}>{lab}</option>' for val, lab in opts)
        auth_opts = proto_opts([("sha", "SHA-1"), ("sha224", "SHA-224"), ("sha256", "SHA-256"),
                                ("sha384", "SHA-384"), ("sha512", "SHA-512"), ("md5", "MD5")],
                               (draft.get("snmp_auth_proto") or [""])[0] if draft is not None else snmp_sec.get("snmp_auth_proto"))
        priv_opts = proto_opts([("aes", "AES-128"), ("aes192", "AES-192"), ("aes256", "AES-256"),
                                ("aes192c", "AES-192-C (Cisco/Reeder)"), ("aes256c", "AES-256-C (Cisco/Reeder)")],
                               (draft.get("snmp_priv_proto") or [""])[0] if draft is not None else snmp_sec.get("snmp_priv_proto"))
        has_saved = False
        if vault_ready:
            try:
                has_saved = bool(self.manager.vault.list_secrets())
            except Exception:
                has_saved = False
        refs = [d.get(k) for k in ("secret_ref", "snmp_ref") if d and d.get(k)] if d else []
        # Entries the form created for this device are "this device's credentials", not shared ones.
        from .web_forms import device_owned_ref
        own = bool(refs) and all(device_owned_ref(r, name) for r in refs)
        mode = "manual" if own else "saved" if refs or (not d and has_saved) else "manual"
        if draft is not None:
            mode = (draft.get("cred_mode") or [mode])[0]
        vault_hint = "" if vault_ready else " <b>Unlock the vault first</b> to store or choose credentials."
        tags = ", ".join(d["tags"]) if d else ""
        entered_name = (draft.get("name") or [name])[0] if draft is not None else name
        name_field = (f'<input name=name value="{_e(entered_name)}" placeholder="e.g. core-sw1">'
                      + (f'<input type=hidden name=orig_name value="{_e(name)}">' if editing else ""))
        selected_platform = (d.get("platform") if d else "generic") or "generic"
        try:
            default_collect_command = _get_driver(selected_platform).config_command or "(none)"
        except Exception:
            default_collect_command = "(unknown platform)"
        collect_override = _e((d.get("config_collect_command") if d else "") or "")
        platform_collect_commands = {}
        for platform_name in _platforms():
            try:
                platform_collect_commands[platform_name] = _get_driver(platform_name).config_command or "(none)"
            except Exception:
                platform_collect_commands[platform_name] = "(unknown)"
        collect_commands_json = json.dumps(platform_collect_commands, sort_keys=True)
        port_val = self.manager.settings.get("netflow_port", 2055)
        host_example = _e((d.get("host") if d else "") or "app.example.com")
        body = f"""<div class="panel"><h2>{_e(title)}</h2>
<form method=post action="/device-save" id=device_form>{self._csrf_field()}
<div class="row">
  <div><label>Name</label>{name_field}</div>
  <div><label id=host_label>Host / IP</label><input name=host value="{v('host')}" placeholder="10.0.0.11"></div>
  <div id=ssh_port_field style="max-width:120px"><label>SSH port</label><input name=port value="{v('port', '22')}"></div>
</div>
<div class="row">
  <div><label>Device type</label><div style="padding-top:6px">{type_checks}</div></div>
  <div id=platform_field><label>Platform</label><select id=platform_select name=platform>{plats}</select></div>
  <div><label>Tags (comma-separated)</label><input name=tags value="{_e(tags)}" placeholder="core, dc1"></div>
</div>
<div id=credentials_section>
<h2 style="margin-top:14px">Credentials</h2>
<p class="muted">Use a saved vault secret (recommended when several devices share a login) or enter credentials for this device; they are stored in the vault, never in the device record.{vault_hint}</p>
<div class="cred-mode" role="radiogroup" aria-label="How to provide credentials">
  <label><input type=radio name=cred_mode value=saved style="width:auto"{" checked" if mode == "saved" else ""}> Use a saved vault secret</label>
  <label><input type=radio name=cred_mode value=manual style="width:auto"{" checked" if mode == "manual" else ""}> Enter credentials for this device</label>
</div>
<div class="row">
  <div><label>SNMP version</label><select name=snmp_version>{snmp_opts}</select></div>
  <div><label style="font-weight:400"><input type=checkbox name=use_key value=1 style="width:auto" {chk('use_key')}> device uses an SSH key (not a password)</label></div>
  <div></div>
</div>
<div id=cred_saved>
<div class="row">
  <div><label>SSH vault secret</label>{self._secret_select('secret_ref', 'secret_ref', d.get('secret_ref') if d else '')}</div>
  <div><label>SNMP vault secret</label>{self._secret_select('snmp_ref', 'snmp_ref', d.get('snmp_ref') if d else '')}</div>
  <div><label>Enable vault secret (optional)</label>{self._secret_select('', 'enable_ref', d.get('enable_ref') if d else '')}</div>
</div>
<div id=secinfo class="muted" style="margin:-2px 0 10px"></div>
</div>
<div id=cred_manual>
<h3>SSH login</h3>
<p class="muted">Credentials entered here are saved separately for this device; shared credentials are not changed. Leave password fields blank to keep this device's previous passwords.</p>
<div class="row">
  <div><label>SSH username{uset('username')}</label><input id=ssh_username name=ssh_username value="{uv('username')}" placeholder="admin" autocomplete=off></div>
  <div><label>SSH password<span id=set_password>{uset('password')}</span></label><input type=password name=ssh_password autocomplete=new-password></div>
  <div><label>Enable password<span id=set_enable_password>{uset('enable_password')}</span><span class=hint>Only for devices with a privileged mode (e.g. Cisco enable)</span></label><input type=password name=enable_password autocomplete=new-password></div>
</div>
<div class="row">
  <div><label>SSH private key path{uset('key_path')}</label><input name=key_path value="{uv('key_path')}" placeholder="/var/lib/netconfig/keys/id_ed25519"></div>
  <div><label>Key passphrase{uset('key_passphrase')}</label><input type=password name=key_passphrase autocomplete=new-password></div>
  <div></div>
</div>
<div data-snmp="any">
<h3>SNMP authentication</h3>
<div class="row">
  <div data-snmp="v2c"><label>v2c community<span id=set_community>{sset('community')}</span></label><input type=password name=community autocomplete=new-password></div>
  <div data-snmp="v3"><label>SNMPv3 username{sset('snmp_user')}</label><input id=snmp_user name=snmp_user value="{sv('snmp_user')}" placeholder="snmp-admin"></div>
  <div data-snmp="any" style="max-width:120px"><label>SNMP port</label><input id=snmp_port name=snmp_port value="{sv('snmp_port')}" placeholder="161"></div>
</div>
<div class="row" data-snmp="v3">
  <div><label>v3 auth protocol</label><select id=snmp_auth_proto name=snmp_auth_proto>{auth_opts}</select></div>
  <div><label>v3 auth password<span id=set_snmp_auth_pass>{sset('snmp_auth_pass')}</span></label><input type=password name=snmp_auth_pass autocomplete=new-password></div>
  <div><label>v3 privacy protocol</label><select id=snmp_priv_proto name=snmp_priv_proto>{priv_opts}</select></div>
  <div><label>v3 privacy password<span id=set_snmp_priv_pass>{sset('snmp_priv_pass')}</span></label><input type=password name=snmp_priv_pass autocomplete=new-password></div>
</div>
</div>
</div>
<h2 style="margin-top:14px">Configuration collection</h2>
<p class="muted">Platform default: <code id=default_collect_command>{_e(default_collect_command)}</code>. If that command does not work on this device, set one read-only alternative. Only one <code>show</code>, <code>display</code>, <code>get</code>, or exact <code>/export</code> command is allowed.</p>
<label>Alternative config collection command <span class="muted">(optional)</span></label>
<input name=config_collect_command value="{collect_override}" placeholder="e.g. show full-configuration">
<div class="test-box">
<button type=button id=test_conn class=ghost>Test connection</button>
<span class="muted">Logs in over SSH and reads the SNMP system name using the values above. Nothing is saved; the first successful SSH test records the device's host key, as the first collection would.</span>
<div id=test_result class="test-result" aria-live=polite></div>
</div>
</div>
<div id=netflow_section{" hidden" if "network" not in cur_types else ""}>
<h2 style="margin-top:14px">NetFlow</h2>
<p class="muted">Receive NetFlow exports from this device. The collector listens on <code>udp/{port_val}</code> (toggle it in Settings → NetFlow). Point this device's flow export at this server's IP on that port.</p>
<label style="font-weight:400"><input type=checkbox name=netflow value=1 style="width:auto" {chk('netflow')}> collect NetFlow from this device</label>
</div>
<div id=portmon_section{" hidden" if "system" not in cur_types else ""}>
<h2 style="margin-top:14px">TCP / UDP ports</h2>
<p class="muted">Monitor port status on this system. List ports as <code>tcp/22, tcp/443, udp/53</code> (bare numbers default to TCP). Status is checked live when you open the device.</p>
<label>Ports to monitor</label>
<input name=monitor_ports value="{_e((d.get('monitor_ports') if d else '') or '')}" placeholder="tcp/22, tcp/80, tcp/443, udp/161">
</div>
<div id=appmon_section{" hidden" if "application" not in cur_types else ""}>
<h2 style="margin-top:14px">REST API / HTTPS</h2>
<p class="muted">Monitor HTTP(S) endpoints for this application — one URL per line, with an optional expected status code. HTTPS URLs also get a TLS certificate check (validity + days to expiry). Examples:<br>
<code>https://{host_example}/</code><br><code>https://{host_example}/api/health 200</code></p>
<label>Endpoints to monitor</label>
<textarea name=monitor_urls placeholder="https://host/&#10;https://host/api/health 200" style="min-height:90px">{_e((d.get('monitor_urls') if d else '') or '')}</textarea>
</div>
<script>
(function(){{
  var boxes=document.querySelectorAll('input[name=device_type]'),
      collectCommands={collect_commands_json},
      platformSelect=document.getElementById('platform_select'),
      defaultCollect=document.getElementById('default_collect_command'),
      nf=document.getElementById('netflow_section'), pm=document.getElementById('portmon_section'),
      am=document.getElementById('appmon_section'), sshPort=document.getElementById('ssh_port_field'),
      platform=document.getElementById('platform_field'), credentials=document.getElementById('credentials_section'),
      managementOptions=document.getElementById('management_options'), hostLabel=document.getElementById('host_label');
  function has(v){{ for(var i=0;i<boxes.length;i++){{ if(boxes[i].value===v&&boxes[i].checked) return true; }} return false; }}
  function toggle(el,on){{ if(!el) return; el.hidden=!on;
    var controls=el.querySelectorAll('input,select,textarea,button');
    for(var i=0;i<controls.length;i++) controls[i].disabled=!on; }}
  function upd(){{
    var managed=has('system')||has('network');
    toggle(nf,has('network')); toggle(pm,has('system')); toggle(am,has('application'));
    toggle(sshPort,managed); toggle(platform,managed); toggle(credentials,managed); toggle(managementOptions,managed);
    if(managed){{ document.querySelectorAll('input[name=cred_mode]').forEach(function(r){{ if(r.checked) r.dispatchEvent(new Event('change')); }}); }}
    if(hostLabel) hostLabel.textContent=managed?'Host / IP':'Primary hostname / FQDN';
    if(platformSelect&&defaultCollect) defaultCollect.textContent=collectCommands[platformSelect.value]||'(unknown)'; }}
  for(var i=0;i<boxes.length;i++) boxes[i].addEventListener('change',upd);
  if(platformSelect) platformSelect.addEventListener('change',upd);
  upd();
}})();
</script>
<script>
(function(){{
  var summ={{}};
  function fill(id,val){{var e=document.getElementById(id); if(e&&val!=null&&val!=='') e.value=val;}}
  function mark(id,on){{var e=document.getElementById('set_'+id); if(e) e.textContent=on?' ✓ set':'';}}
  function render(){{var el=document.getElementById('secinfo'); if(!el) return;
    var parts=[]; if(summ.ssh) parts.push(summ.ssh); if(summ.snmp) parts.push(summ.snmp);
    el.textContent=parts.join('  ·  ');}}
  function load(name,kind){{
    if(!name){{ summ[kind]=''; render(); return; }}
    fetch('/secret-info?name='+encodeURIComponent(name)).then(function(r){{return r.json();}}).then(function(j){{
      if(!j.exists){{ summ[kind]="no vault secret named '"+name+"'"; render(); return; }}
      var f=j.fields||{{}}, s=j.set||{{}};
      if(kind==='ssh'){{
        fill('ssh_username',f.username); mark('password',s.password); mark('enable_password',s.enable_password);
        var b=[]; if(f.username) b.push('user '+f.username); if(s.password) b.push('password set'); if(s.key_path) b.push('SSH key'); if(s.enable_password) b.push('enable set');
        summ.ssh="SSH '"+name+"': "+(b.join(', ')||'no fields');
      }} else {{
        fill('snmp_user',f.snmp_user); fill('snmp_auth_proto',f.snmp_auth_proto); fill('snmp_priv_proto',f.snmp_priv_proto); fill('snmp_port',f.snmp_port);
        mark('community',s.community); mark('snmp_auth_pass',s.snmp_auth_pass); mark('snmp_priv_pass',s.snmp_priv_pass);
        var b2=[]; if(f.snmp_user) b2.push('user '+f.snmp_user); if(f.snmp_auth_proto) b2.push(f.snmp_auth_proto.toUpperCase()+(f.snmp_priv_proto?('/'+f.snmp_priv_proto.toUpperCase()):'')); if(s.community) b2.push('community set'); if(s.snmp_auth_pass) b2.push('auth set'); if(s.snmp_priv_pass) b2.push('priv set');
        summ.snmp="SNMP '"+name+"': "+(b2.join(', ')||'no fields');
      }}
      render();
    }}).catch(function(){{}});
  }}
  var sref=document.getElementById('secret_ref'), nref=document.getElementById('snmp_ref');
  var manual=document.querySelector('input[name=cred_mode][value=manual]:checked');
  if(sref){{ sref.addEventListener('change',function(){{load(sref.value.trim(),'ssh');}}); if(!manual && sref.value.trim()) load(sref.value.trim(),'ssh'); }}
  if(nref){{ nref.addEventListener('change',function(){{load(nref.value.trim(),'snmp');}}); if(!manual && nref.value.trim()) load(nref.value.trim(),'snmp'); }}
}})();
</script>
<label>Notes</label><textarea name=notes style="min-height:60px">{v('notes')}</textarea>
<div style="display:flex;gap:20px;flex-wrap:wrap;margin:6px 0 16px">
  <div id=management_options style="display:flex;gap:20px;flex-wrap:wrap">
    <label style="color:var(--text)"><input type=checkbox name=legacy value=1 style="width:auto" {chk('legacy')}> legacy algorithms<span class=hint>Allow older SSH ciphers/key exchange for devices that cannot use modern ones</span></label>
    <label style="color:var(--text)"><input type=checkbox name=scrub value=1 style="width:auto" {chk('scrub')}> scrub secrets in archive<span class=hint>Remove passwords and keys from saved configuration copies</span></label>
  </div>
  <label style="color:var(--text)"><input type=checkbox name=enabled value=1 style="width:auto" {"checked" if (not editing or d.get('enabled')) else ""}> enabled<span class=hint>Disabled devices are skipped by collect-all and background polling</span></label>
</div>
<button>{"Save changes" if editing else "Add device"}</button>
<a class="btn ghost" href="{('/device?name=' + _q(name)) if editing else '/'}" style="margin-left:8px">Cancel</a>
</form></div>"""
        del_panel = ""
        if editing:
            del_panel = ('<div class="panel"><h2>Danger zone</h2>'
                         '<form method=post action="/device-delete" '
                         'data-confirm="Delete this device and its inventory entry? Archived configs are kept on disk.">'
                         f'{self._csrf_field()}<input type=hidden name=name value="{_e(name)}">'
                         '<button class=danger>Delete device</button></form></div>')
        self._send(self._page(title, body + del_panel, sess, flash=flash), status)

    def _do_device_test(self, form, sess):
        """Explicit, read-only connection test for the Add/Edit form. Saves nothing."""
        def out(payload, status=200):
            return self._send(json.dumps(payload), status, "application/json")
        if not _can(sess["role"], "manage_devices"):
            return out({"error": "Only approvers and administrators can test device connections."}, 403)

        def g(k, default=""):
            return str((form.get(k) or [default])[0])
        host = g("host").strip()
        types = set(form.get("device_type") or ["network"])
        if not host:
            return out({"error": "Enter the host or IP address first."}, 400)
        if not types & {"network", "system"}:
            return out({"error": "Connection tests apply to network and system devices."}, 400)
        try:
            port = int(g("port", "22") or 22)
        except ValueError:
            return out({"error": "SSH port must be a number."}, 400)
        vault_ready = self.manager.vault_ready()

        def from_vault(ref):
            if not ref:
                return None
            if not vault_ready:
                raise ValueError("The vault is locked, so the saved secret cannot be read.")
            try:
                return dict(self.manager.vault.get_secret(ref))
            except KeyError as exc:
                raise ValueError(f"No vault secret named '{ref}'.") from exc
        try:
            manual_ssh = {"username": g("ssh_username").strip(), "password": g("ssh_password"),
                          "key_path": g("key_path").strip(), "key_passphrase": g("key_passphrase")}
            ssh = from_vault(g("secret_ref").strip())
            if not ssh and any(manual_ssh.values()):
                ssh = manual_ssh
            snmp_version = g("snmp_version").strip()
            snmp = None
            if snmp_version in ("v2c", "v3"):
                snmp = from_vault(g("snmp_ref").strip()) or {
                    k: g(k).strip() for k in ("community", "snmp_user", "snmp_auth_proto", "snmp_auth_pass",
                                              "snmp_priv_proto", "snmp_priv_pass", "snmp_port")}
                snmp["version"] = snmp_version
        except ValueError as exc:
            return out({"error": str(exc)}, 400)
        if ssh is None and snmp is None:
            return out({"error": "Choose a saved secret or enter SSH or SNMP credentials to test."}, 400)
        results = self.manager.test_device_connection(
            host, port=port, use_key=bool(form.get("use_key")), legacy=bool(form.get("legacy")),
            ssh=ssh, snmp=snmp)
        self.manager.db.audit(sess["username"], "device_connection_test", host,
                              "; ".join(f'{r["check"]}={"ok" if r["ok"] else "failed"}' for r in results))
        return out({"results": results})
