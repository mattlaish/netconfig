"""
web.py -- Self-hosted web console, stdlib http.server only.

Theme: dark ink / brass, consistent with the suite's "Security Operations" login.
No external CSS/JS -- everything inlined so the console runs air-gapped.

v2 security model:
  * Login is per-user (username + PBKDF2 password), not the vault master. Roles
    (viewer/operator/approver/admin) gate every action, which is what makes the
    change-approval workflow real: a junior can submit but not approve or execute.
  * The credential vault is separate. Talking to devices (collect / run jobs /
    SNMP) needs it unlocked; an admin unlocks it once per process from the console
    (or via $NETCONFIG_MASTER at startup). Its key then lives in memory for the
    process, same threat model as the CLI.
  * http.server speaks PLAIN HTTP; bind 127.0.0.1 and front with the WAF for TLS.
    Sessions are random tokens (HttpOnly, SameSite=Strict) with a per-session
    CSRF token required on every POST.
"""

import html
import http.server
import json
import re
import os
import secrets
import socketserver
import ssl
import sys
import threading
import time
import urllib.parse

from . import compliance as _compliance
from .users import can as _can, roles as _roles
from .workflow import Workflow, Scripts
from .drivers import platforms as _platforms
from . import config as _config
from .security import LoginThrottle, security_headers
from .observability import METRICS, event as _obs_event
from .apitokens import ApiTokens
from .credentials import service_master_password

_CSS = """
:root{
  --navy:#181048; --navy90:#232059; --navy10:#E8E8F0;
  --solid:#181048; --solid-hover:#232059; --surface:#fff; --text:#26282B;
  --row-alt:#FAFBFD; --line:#E6E8EE;
  --red:#C02020; --red10:#F9E9EA; --grey:#595959; --border:#C9CDD6;
  --bg:#F2F3F7; --warn:#8A5A00; --warn10:#FBF3E2; --ok:#1E6641; --ok10:#EAF3EE;
  --radius:8px;
  --font:"Noto Sans","Noto Sans TC","Segoe UI","Microsoft JhengHei","PingFang TC",Arial,sans-serif;
  --mono:ui-monospace,"DejaVu Sans Mono",Menlo,Consolas,monospace;
}
html[data-theme="dark"]{
  color-scheme:dark;
  --navy:#A9B8FF; --navy90:#33447C; --navy10:#252E48;
  --solid:#26376C; --solid-hover:#334A8C; --surface:#171C29; --text:#E8ECF5;
  --row-alt:#1B2231; --line:#30394B;
  --red:#FF858B; --red10:#43262D; --grey:#ADB6C8; --border:#3B4559;
  --bg:#10141E; --warn:#F0C36A; --warn10:#42361F; --ok:#72D6A2; --ok10:#1B3B30;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font);font-size:15px;line-height:1.5}
a{color:var(--navy);text-decoration:none}a:hover{text-decoration:underline}
/* topbar */
header{display:flex;justify-content:space-between;align-items:center;gap:16px;
  background:var(--surface);border-bottom:3px solid var(--red);padding:10px 22px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:14px;color:var(--navy);font-weight:700;font-size:16px}
.brand .logo{display:inline-flex;align-items:center;justify-content:center;
  width:36px;height:36px;background:var(--solid);color:#fff;border-radius:7px;
  font-weight:800;font-size:13px;letter-spacing:.02em}
.brand .appname{border-left:1px solid var(--border);padding-left:14px}
.brand span{color:var(--navy)}
.top-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-left:auto}
.who{color:var(--grey);font-size:13px}
.who b{color:var(--navy)}
.role{background:var(--navy10);color:var(--navy);border-radius:10px;padding:1px 8px;
  font-size:11px;margin-left:4px;font-weight:600;text-transform:uppercase}
/* nav */
nav{background:var(--solid);display:flex;flex-wrap:wrap;padding:0 22px}
nav a{color:#fff;padding:11px 14px;font-size:14px;border-bottom:3px solid transparent}
nav a:hover{background:var(--navy90);border-bottom-color:var(--red);text-decoration:none}
/* layout */
main{max-width:1280px;margin:22px auto;padding:0 22px}
h1{color:var(--navy);font-size:22px;margin:6px 0 14px;font-weight:700}
h2{color:var(--navy);font-size:15px;margin:0 0 10px;font-weight:700}
h3{color:var(--navy);font-size:14px;font-weight:700;margin:10px 0 6px}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px;margin-bottom:18px}
/* tables */
table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);overflow:hidden;font-size:14px}
th,td{text-align:left;padding:9px 12px;vertical-align:top}
th{background:var(--solid);color:#fff;font-weight:600;font-size:13px}
td{border-top:1px solid var(--line)}
tbody tr:nth-child(even) td{background:var(--row-alt)}
/* badges */
.badge{display:inline-block;border-radius:10px;padding:1px 9px;font-size:11.5px;font-weight:600;
  background:var(--navy10);color:var(--navy);white-space:nowrap}
.b-ok{background:var(--ok10);color:var(--ok)}
.b-bad{background:var(--red10);color:var(--red)}
.b-chg{background:var(--warn10);color:var(--warn)}
.b-dim{background:#EDEEF0;color:var(--grey)}
.b-brass{background:var(--solid);color:#fff}
/* buttons */
button,.btn{display:inline-block;background:var(--solid);color:#fff;border:1px solid var(--solid);
  border-radius:6px;padding:8px 14px;font-family:var(--font);font-size:14px;font-weight:600;
  cursor:pointer;text-decoration:none}
button:hover,.btn:hover{background:var(--solid-hover);text-decoration:none}
button.ghost,.btn.ghost{background:var(--surface);border-color:var(--border);color:var(--grey)}
button.ghost:hover,.btn.ghost:hover{background:var(--navy10);color:var(--navy)}
button.danger{background:var(--surface);border-color:var(--red);color:var(--red)}
button.danger:hover{background:var(--red10)}
button:disabled{opacity:.5;cursor:not-allowed}
/* code / diff */
pre{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:14px;overflow:auto;
  font:12.5px/1.5 var(--mono);color:var(--text);max-height:70vh}
code{background:var(--navy10);padding:1px 6px;border-radius:4px;font-size:.92em}
pre.diff .add{color:var(--ok);background:var(--ok10)}
pre.diff .del{color:var(--red);background:var(--red10)}
pre.diff .hdr{color:var(--navy);font-weight:700}
/* forms */
input,select,textarea{width:100%;background:var(--surface);border:1px solid var(--border);border-radius:6px;
  padding:8px 10px;color:var(--text);font-size:14px;margin-bottom:12px;font-family:var(--font)}
textarea{font-family:var(--mono);font-size:13px;min-height:120px}
input:focus,select:focus,textarea:focus{outline:2px solid var(--navy);outline-offset:1px;border-color:var(--navy)}
label{display:block;font-size:13px;color:var(--navy);font-weight:600;margin-bottom:4px}
/* notes */
.err{background:var(--red10);border:1px solid #E7B6B8;padding:9px 12px;border-radius:6px;
  margin-bottom:12px;font-size:14px;color:var(--red)}
.muted{color:var(--grey);font-size:13px}
.right{text-align:right}
.row{display:flex;gap:16px;flex-wrap:wrap}.row>*{flex:1;min-width:220px}
.settings-shell{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;align-items:start}
.settings-menu{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:8px;
  position:sticky;top:12px}
.settings-menu a{display:block;padding:10px 12px;border-radius:6px;color:var(--grey);font-size:14px;
  font-weight:600;margin:2px 0}
.settings-menu a:hover{background:var(--navy10);color:var(--navy);text-decoration:none}
.settings-menu a.active{background:var(--solid);color:#fff}
.settings-content .panel{margin-bottom:0}
@media(max-width:760px){.settings-shell{grid-template-columns:1fr}.settings-menu{position:static;
  display:flex;gap:4px;overflow-x:auto}.settings-menu a{white-space:nowrap}}
.flash{background:var(--navy10);border:1px solid var(--border);padding:10px 14px;border-radius:6px;
  margin-bottom:14px;color:var(--navy);font-size:14px}
.vault-lock{background:var(--red10);border:1px solid #E7B6B8;padding:6px 12px;border-radius:6px;
  color:var(--red);font-size:12px}
.vault-open{color:var(--ok);font-size:12px;font-weight:600}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--navy10);color:var(--navy)}
.sev-high{color:var(--red)}.sev-medium{color:var(--warn)}.sev-low{color:var(--grey)}
/* login */
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg)}
.login{width:420px;max-width:92vw;background:var(--surface);border:1px solid var(--border);
  border-top:4px solid var(--red);border-radius:10px;padding:34px 38px}
.login .brand{display:flex;justify-content:center;color:var(--navy);font-size:18px;margin-bottom:4px}
.login .sub{text-align:center;color:var(--grey);font-size:12px;margin-bottom:22px;letter-spacing:.04em}
/* footer */
.footer{max-width:1280px;margin:26px auto;padding:12px 22px;color:var(--grey);font-size:12px;
  border-top:1px solid var(--border);display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
html[data-theme="dark"] [data-idx],html[data-theme="dark"] [data-idx] svg{
  background:var(--surface)!important}
html[data-theme="dark"] [data-idx] svg text{fill:var(--grey)!important}
html[data-theme="dark"] [data-idx] svg line{stroke:var(--border)!important}
.theme-toggle{white-space:nowrap;padding:5px 11px!important}
"""

_THEME_JS = """<script>
(function(){
  var key='netconfig-theme', root=document.documentElement;
  function preferred(){
    var saved=localStorage.getItem(key);
    if(saved==='dark'||saved==='light') return saved;
    return window.matchMedia&&window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light';
  }
  function paint(theme){
    root.setAttribute('data-theme',theme);
    var b=document.getElementById('theme-toggle');
    if(b){b.textContent=theme==='dark'?'Light theme':'Dark theme';
      b.setAttribute('aria-pressed',theme==='dark'?'true':'false');}
  }
  window.netconfigToggleTheme=function(){
    var next=root.getAttribute('data-theme')==='dark'?'light':'dark';
    localStorage.setItem(key,next); paint(next);
  };
  paint(preferred());
  document.addEventListener('DOMContentLoaded',function(){paint(root.getAttribute('data-theme')||preferred());});
})();
</script>"""

# Dashboard: collapsible per-type device groups + a client-side search that
# filters rows by name / IP / tag. No external libraries; degrades to plain
# collapsed groups when JS is off.
_DASH_JS = """<style>
.devgroup{margin:10px 0;border:1px solid var(--line);border-radius:8px;overflow:hidden}
.devgroup>summary{cursor:pointer;padding:10px 14px;font-weight:600;font-size:16px;
  list-style:none;user-select:none}
.devgroup>summary::-webkit-details-marker{display:none}
.devgroup>summary::before{content:'\\25B8';display:inline-block;width:1em;
  color:var(--muted);transition:transform .15s}
.devgroup[open]>summary::before{transform:rotate(90deg)}
.devgroup>table{margin:0}
</style><script>
(function(){
  var box=document.getElementById('devsearch');
  if(!box) return;
  var groups=[].slice.call(document.querySelectorAll('.devgroup'));
  var noRes=document.getElementById('devnoresults');
  function apply(){
    var q=box.value.trim().toLowerCase();
    var terms=q.split(/\\s+/).filter(Boolean);
    var anyVisible=false;
    groups.forEach(function(g){
      var rows=[].slice.call(g.querySelectorAll('tr.devrow')), shown=0;
      rows.forEach(function(r){
        var hay=r.getAttribute('data-search')||'';
        var match=terms.every(function(t){return hay.indexOf(t)>=0;});
        r.style.display=match?'':'none';
        if(match) shown++;
      });
      if(terms.length===0){ g.style.display=''; g.open=false; }
      else{ g.style.display=shown?'':'none'; g.open=shown>0; }
      if(shown>0) anyVisible=true;
      var c=g.querySelector('.devcount');
      if(c) c.textContent=terms.length?(shown+' / '+rows.length):rows.length;
    });
    if(noRes) noRes.style.display=(terms.length&&!anyVisible)?'':'none';
  }
  box.addEventListener('input',apply);
  apply();
})();
</script>"""

_SESSIONS = {}   # token -> {username, role, csrf, created}; expiry intentionally deferred
_LOGIN_THROTTLE = LoginThrottle()

# Vanilla-JS live line chart: polls /snmp-series and redraws an inline SVG. No
# external libraries. %s = device name (JSON string), %d = refresh seconds.
_GRAPH_JS = """
<script>
(function(){
  var DEV=__DEV__, IV=__IV__, NS='http://www.w3.org/2000/svg';
  var data={}, monitored=[], MODE='live';
  var charts=document.getElementById('charts'),
      addsel=document.getElementById('ifadd'),
      addbtn=document.getElementById('addbtn'),
      modeSel=document.getElementById('ifmode'),
      statusEl=document.getElementById('livestatus');
  charts.style.cssText='display:grid;grid-template-columns:repeat(2,max-content);'
    +'gap:12px;justify-content:start;align-items:start';
  var W=380,H=200,PL=54,PR=12,PT=12,PB=30;
  function fmt(v){ if(v==null) return '-'; var u=['bps','Kbps','Mbps','Gbps'],i=0;
    while(v>=1000&&i<u.length-1){v/=1000;i++;} return (i===0?v.toFixed(0):v.toFixed(1))+' '+u[i]; }
  function hms(t){ var d=new Date(t*1000); function p(n){return (n<10?'0':'')+n;}
    return p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds()); }
  function el(n,a){ var e=document.createElementNS(NS,n); for(var k in a) e.setAttribute(k,a[k]); return e; }
  function descrOf(idx){ return (data[idx]&&data[idx].descr)||idx; }
  function drawChart(idx){
    var card=document.querySelector('[data-idx="'+idx+'"]'); if(!card) return;
    var svg=card.querySelector('svg'); while(svg.firstChild) svg.removeChild(svg.firstChild);
    var d=data[idx];
    if(!d||!d.points.length){ svg.appendChild(el('text',{x:PL,y:H/2,fill:'#595959','font-size':12})).textContent='waiting for samples...'; return; }
    var p=d.points, t0=p[0][0], t1=p[p.length-1][0]; if(t1<=t0) t1=t0+1;
    var mx=1; p.forEach(function(r){ mx=Math.max(mx,r[1]||0,r[2]||0); });
    function X(t){ return PL+(t-t0)/(t1-t0)*(W-PL-PR); }
    function Y(v){ return H-PB-(v/mx)*(H-PT-PB); }
    svg.appendChild(el('line',{x1:PL,y1:PT,x2:PL,y2:H-PB,stroke:'#C9CDD6'}));
    svg.appendChild(el('line',{x1:PL,y1:H-PB,x2:W-PR,y2:H-PB,stroke:'#C9CDD6'}));
    [0,mx/2,mx].forEach(function(v){ var y=Y(v);
      svg.appendChild(el('line',{x1:PL,y1:y,x2:W-PR,y2:y,stroke:'#EEF0F4'}));
      var t=el('text',{x:PL-6,y:y+3,fill:'#595959','font-size':10,'text-anchor':'end'});
      t.textContent=fmt(v); svg.appendChild(t); });
    [0,0.5,1].forEach(function(f,i){ var tt=t0+(t1-t0)*f, x=X(tt);
      svg.appendChild(el('line',{x1:x,y1:H-PB,x2:x,y2:H-PB+4,stroke:'#C9CDD6'}));
      var tl=el('text',{x:x,y:H-PB+15,fill:'#595959','font-size':9,
        'text-anchor': i===0?'start':(i===2?'end':'middle')});
      tl.textContent=hms(tt); svg.appendChild(tl); });
    var xl=el('text',{x:(PL+W-PR)/2,y:H-3,fill:'#8892A0','font-size':9,'text-anchor':'middle'});
    xl.textContent='time'; svg.appendChild(xl);
    function poly(i2,c){ var dd=''; p.forEach(function(r){ var v=r[i2]||0; dd+=(dd?' L':'M')+X(r[0]).toFixed(1)+' '+Y(v).toFixed(1); });
      svg.appendChild(el('path',{d:dd,fill:'none',stroke:c,'stroke-width':2})); }
    poly(1,'#1E6641'); poly(2,'#8A5A00');
    var last=p[p.length-1];
    card.querySelector('.cin').textContent=fmt(last[1]);
    card.querySelector('.cout').textContent=fmt(last[2]);
  }
  function addChart(idx){
    if(!idx||monitored.indexOf(idx)>=0) return;
    monitored.push(idx);
    var card=document.createElement('div'); card.setAttribute('data-idx',idx);
    card.style.cssText='border:1px solid var(--border);border-radius:6px;padding:10px;background:#fff';
    var head=document.createElement('div'); head.style.cssText='display:flex;align-items:center;gap:12px;margin-bottom:6px';
    head.innerHTML='<b style="color:var(--navy)">'+descrOf(idx)+'</b><span class="muted">in <b class="cin" style="color:#1E6641">-</b> \u00b7 out <b class="cout" style="color:#8A5A00">-</b></span>';
    var rm=document.createElement('button'); rm.type='button'; rm.className='ghost'; rm.textContent='\u00d7';
    rm.style.cssText='margin-left:auto;padding:2px 10px'; rm.onclick=function(){ removeChart(idx); };
    head.appendChild(rm); card.appendChild(head);
    var svg=el('svg',{viewBox:'0 0 '+W+' '+H,width:W,height:H});
    svg.setAttribute('style','width:'+W+'px;height:'+H+'px;background:#fff;border:1px solid var(--border);border-radius:6px');
    card.appendChild(svg); charts.appendChild(card);
    drawChart(idx); buildOptions();
  }
  function removeChart(idx){
    var i=monitored.indexOf(idx); if(i>=0) monitored.splice(i,1);
    var card=document.querySelector('[data-idx="'+idx+'"]'); if(card) card.remove();
    buildOptions();
  }
  function buildOptions(){
    var keys=Object.keys(data).filter(function(k){ return monitored.indexOf(k)<0; });
    addsel.innerHTML='';
    keys.forEach(function(k){ var o=document.createElement('option'); o.value=k; o.textContent=descrOf(k); addsel.appendChild(o); });
    addbtn.disabled = keys.length===0;
    document.getElementById('addrow').style.display = keys.length? 'flex':'none';
  }
  function drawAll(){ monitored.forEach(drawChart); }
  function refresh(){
    var url = (MODE==='history')
      ? '/snmp-history?device='+encodeURIComponent(DEV)
      : '/snmp-series?device='+encodeURIComponent(DEV);
    fetch(url).then(function(r){return r.json();}).then(function(j){
      data={}; (j.interfaces||[]).forEach(function(it){ data[it.ifindex]=it; });
      if(!monitored.length){ var k=Object.keys(data)[0]; if(k) addChart(k); }
      drawAll(); buildOptions();
      if(MODE==='history'){
        statusEl.textContent = (j.enabled===false) ? 'history backend not configured'
          : (j.error ? 'history error: '+j.error
             : (j.hours||24)+'h history \u00b7 '+new Date().toLocaleTimeString());
      } else {
        statusEl.textContent='live \u00b7 '+new Date().toLocaleTimeString();
      }
    }).catch(function(){ statusEl.textContent='(waiting for samples)'; });
  }
  addbtn.addEventListener('click',function(){ if(addsel.value) addChart(addsel.value); });
  if(modeSel){ modeSel.addEventListener('change',function(){ MODE=modeSel.value; refresh(); }); }
  var seedEl=document.getElementById('ifseed');
  if(seedEl){ try{ JSON.parse(seedEl.textContent).forEach(function(it){ data[it.ifindex]=it; });
    var k=Object.keys(data)[0]; if(k) addChart(k); }catch(e){} }
  refresh(); setInterval(function(){ if(MODE==='live') refresh(); }, Math.max(IV,3)*1000);
})();
</script>
"""

_STATUS_BADGE = {"pending": "b-chg", "approved": "b-brass", "executed": "b-ok",
                 "rejected": "b-bad", "failed": "b-bad", "cancelled": "b-dim"}


def _fmt_ts(ts):
    if not ts:
        return "\u2014"
    if isinstance(ts, (int, float)):
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    s = str(ts)
    try:
        t = time.strptime(s, "%Y%m%dT%H%M%SZ")
        return time.strftime("%Y-%m-%d %H:%M UTC", t)
    except ValueError:
        return s


def _colorize_diff(diff):
    out = []
    for line in diff.splitlines():
        e = html.escape(line)
        if line.startswith(("+++", "---", "@@")):
            out.append(f'<span class="hdr">{e}</span>')
        elif line.startswith("+"):
            out.append(f'<span class="add">{e}</span>')
        elif line.startswith("-"):
            out.append(f'<span class="del">{e}</span>')
        else:
            out.append(e)
    return "\n".join(out)


def _q(s):
    return urllib.parse.quote(str(s))


def _md_inline(text):
    import re
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+|file:[^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def _render_markdown(md):
    """Tiny stdlib markdown -> HTML for the help page. Handles the subset used in
    the docs: #/##/### headers, * bullets, | tables |, ``` code ```, > notes,
    ---, and inline code/bold/links."""
    lines = md.split("\n")
    out, para, items = [], [], []
    i = 0

    def flush_para():
        if para:
            out.append("<p>" + _md_inline(html.escape(" ".join(para))) + "</p>")
            para.clear()

    def flush_list():
        if items:
            out.append("<ul>" + "".join(
                f"<li>{_md_inline(html.escape(x))}</li>" for x in items) + "</ul>")
            items.clear()

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            flush_para(); flush_list()
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            out.append("<pre>" + html.escape("\n".join(buf)) + "</pre>")
            i += 1
            continue
        if "|" in ln and i + 1 < len(lines) and lines[i + 1].strip() and \
                set(lines[i + 1].strip()) <= set("|-: "):
            flush_para(); flush_list()
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{_md_inline(html.escape(c))}</th>" for c in hdr)
            trs = "".join("<tr>" + "".join(
                f"<td>{_md_inline(html.escape(c))}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><tr>{th}</tr>{trs}</table>")
            continue
        s = ln.strip()
        if not s:
            flush_para(); flush_list()
        elif s.startswith("### "):
            flush_para(); flush_list(); out.append(f"<h3>{_md_inline(html.escape(s[4:]))}</h3>")
        elif s.startswith("## "):
            flush_para(); flush_list()
            out.append(f'<h2 style="margin-top:20px">{_md_inline(html.escape(s[3:]))}</h2>')
        elif s.startswith("# "):
            flush_para(); flush_list(); out.append(f"<h1>{_md_inline(html.escape(s[2:]))}</h1>")
        elif s == "---":
            flush_para(); flush_list()
            out.append('<hr style="border:none;border-top:1px solid var(--line);margin:18px 0">')
        elif s.startswith("* ") or s.startswith("- "):
            flush_para(); items.append(s[2:])
        elif s.startswith("> "):
            flush_para(); flush_list()
            out.append(f'<div class="muted" style="border-left:3px solid var(--brass);'
                       f'padding-left:12px;margin:10px 0">{_md_inline(html.escape(s[2:]))}</div>')
        else:
            para.append(s)
        i += 1
    flush_para(); flush_list()
    return "\n".join(out)


def _load_doc(name):
    """Find a shipped doc (WEBGUI.md, CREDENTIALS.md) next to the install root."""
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(os.path.dirname(here), name),  # /opt/netconfig/<name>
                 os.path.join(here, name),
                 os.path.join(os.getcwd(), name)):
        try:
            with open(cand, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return None


APP_VERSION = "1.0"   # user-facing program version (kept at 1.0 until further notice)

_DEVICE_TYPES = [("system", "System"), ("network", "Network"), ("application", "Application")]


def _dtypes(dev):
    raw = (dev.get("device_type") or "") if dev else ""
    ts = {t for t in re.split(r"[,\s]+", raw) if t in ("system", "network", "application")}
    return ts or {"network"}


def _is_managed_device(dev):
    """True when SSH/config/SNMP management applies to this inventory item."""
    return bool(_dtypes(dev) & {"system", "network"})


def _ok_badge(ok):
    return '<span class="badge b-ok">ok</span>' if ok else '<span class="badge b-bad">fail</span>'


def _fmt_bps(bps):
    if bps is None:
        return "\u2014"
    units = ["bps", "Kbps", "Mbps", "Gbps"]
    v = float(bps)
    for u in units:
        if v < 1000:
            return f"{v:.0f} {u}" if u == "bps" else f"{v:.1f} {u}"
        v /= 1000
    return f"{v:.1f} Tbps"


def _fmt_speed(bits):
    if not bits:
        return "\u2014"
    v = float(bits)
    for u in ["bps", "Kbps", "Mbps", "Gbps"]:
        if v < 1000:
            return f"{v:.0f} {u}"
        v /= 1000
    return f"{v:.0f} Tbps"


def _oper_badge(oper):
    cls = "b-ok" if oper == "up" else ("b-dim" if oper in ("down", "notPresent") else "b-chg")
    return f'<span class="badge {cls}">{html.escape(oper or "?")}</span>'


class Console(http.server.BaseHTTPRequestHandler):
    manager = None
    tls_enabled = False
    netflow = None
    syslog = None
    server_version = "netconfig-console"

    @property
    def wf(self):
        if not hasattr(self.manager, "_wf"):
            self.manager._wf = Workflow(self.manager.db, self.manager)
            self.manager._scripts = Scripts(self.manager.db.conn)
        return self.manager._wf

    @property
    def scripts(self):
        self.wf  # ensure init
        return self.manager._scripts

    # ---- session helpers -------------------------------------------------
    def _session(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "ncsid" and v in _SESSIONS:
                    return v, _SESSIONS[v]
        return None, None

    def _require_auth(self):
        _, sess = self._session()
        if sess is None:
            self._redirect("/login")
            return None
        return sess

    def _send(self, body, status=200, ctype="text/html; charset=utf-8", headers=None):
        self._responded = True
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        nonce = secrets.token_urlsafe(18)
        for h, v in security_headers(tls=self.tls_enabled, csp_nonce=nonce):
            self.send_header(h, v)
        for h, v in (headers or []):
            self.send_header(h, v)
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, loc, headers=None):
        self._responded = True
        self.send_response(303)
        self.send_header("Location", loc)
        nonce = secrets.token_urlsafe(18)
        for h, v in security_headers(tls=self.tls_enabled, csp_nonce=nonce):
            self.send_header(h, v)
        for h, v in (headers or []):
            self.send_header(h, v)
        self.end_headers()

    def _csrf_field(self):
        _, sess = self._session()
        tok = sess["csrf"] if sess else ""
        return f'<input type=hidden name=csrf value="{html.escape(tok)}">'

    def _nav(self, sess):
        role = sess["role"]
        links = [("/", "Devices"), ("/groups", "Groups"), ("/automation", "Automation"),
                 ("/requests", "Change Requests"), ("/compliance", "Compliance"),
                 ("/alerts", "Alerts"), ("/snmp", "SNMP"), ("/topology", "Topology")]
        if _can(role, "manage_devices"):
            links.append(("/vault", "Vault"))
        links += [("/runs", "Run Log"), ("/audit", "Audit")]
        if _can(role, "manage_users"):
            links.append(("/users", "Users"))
        if _can(role, "settings"):
            links.append(("/settings", "Settings"))
        links.append(("/mib", "MIB"))
        links.append(("/help", "Help"))
        return "".join(f'<a href="{u}">{html.escape(t)}</a>' for u, t in links)

    def _topright(self, sess):
        vault = ('<span class="vault-open">\u25cf vault unlocked</span>'
                 if self.manager.vault_ready() else
                 '<span class="vault-lock">\u25cf vault locked</span>')
        return (f'<div class="top-right">{vault}'
                f'<span class="who"><b>{html.escape(sess["username"])}</b>'
                f'<span class="role">{html.escape(sess["role"])}</span></span>'
                f'<button type=button id="theme-toggle" class="ghost theme-toggle" '
                f'onclick="netconfigToggleTheme()" aria-label="Toggle color theme" '
                f'aria-pressed="false">Dark theme</button>'
                f'<form method=post action="/logout" style="display:inline;margin:0">'
                f'{self._csrf_field()}<button class=ghost style="padding:5px 12px">Sign out</button>'
                f'</form></div>')

    def _page(self, title, inner, sess, flash=None):
        f = f'<div class="flash">{html.escape(flash)}</div>' if flash else ""
        nav = f'<nav>{self._nav(sess)}</nav>' if sess else ""
        right = self._topright(sess) if sess else ""
        return f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(title)} \u00b7 NetConfig</title><style>{_CSS}</style>{_THEME_JS}</head><body>
<header><div class="brand"><span class="logo">EH</span>
<span class="appname">Net<span>Config</span> \u00b7 Network Configuration</span></div>{right}</header>
{nav}
<main><h1>{html.escape(title)}</h1>{f}{inner}</main>
<footer class="footer"><span>Evangel Hospital \u64ad\u9053\u91ab\u9662 \u00b7 NetConfig v{APP_VERSION}</span>
<span>Internal \u2014 Restricted</span></footer></body></html>"""

    def _read_post(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return urllib.parse.parse_qs(raw, keep_blank_values=True)

    def _check_csrf(self, form):
        _, sess = self._session()
        if not sess:
            return False
        got = (form.get("csrf") or [""])[0]
        return secrets.compare_digest(got, sess["csrf"])

    def log_message(self, fmt, *args):
        _obs_event("http_access", source_ip=self.client_address[0] if self.client_address else "",
                   method=getattr(self, "command", ""), path=getattr(self, "path", ""),
                   message=(fmt % args if args else fmt))

    def _client_ip(self):
        # Deliberately trust only the actual peer. Reverse proxies should preserve
        # source identity in their own logs unless an explicit trusted-proxy model
        # is added later.
        return self.client_address[0] if self.client_address else "unknown"

    def _health(self, ready=False):
        ok = True
        detail = {"status": "ok"}
        if ready:
            try:
                self.manager.db.conn.execute("SELECT 1").fetchone()
            except Exception:
                ok = False
            detail.update({"status": "ready" if ok else "not-ready",
                           "vault_ready": bool(self.manager.vault_ready())})
        return self._send(json.dumps(detail), 200 if ok else 503,
                          "application/json; charset=utf-8")

    def _metrics(self):
        METRICS.set("netconfig_vault_ready", 1 if self.manager.vault_ready() else 0)
        METRICS.set("netconfig_sessions", len(_SESSIONS))
        return self._send(METRICS.render(), 200, "text/plain; version=0.0.4; charset=utf-8")

    # ---- routing ---------------------------------------------------------
    def _api_token(self):
        # Never accept reusable bearer credentials over cleartext LAN HTTP.
        # Loopback is allowed for the documented local reverse-proxy pattern.
        peer = self._client_ip()
        if not self.tls_enabled and peer not in ("127.0.0.1", "::1", "localhost"):
            return None
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return ApiTokens(self.manager.db.conn).verify(auth[7:].strip())

    def _api_json(self, payload, status=200):
        import json
        self._send(json.dumps(payload, indent=2, sort_keys=True), status,
                   "application/json; charset=utf-8", [("Cache-Control", "no-store")])

    def _handle_api_get(self, path):
        token = self._api_token()
        if not token:
            self._api_json({"error": "invalid_or_missing_bearer_token"}, 401); return True
        scopes = token["scopes"]
        routes = {
            "/api/v1/inventory": ("inventory:read", lambda: self.manager.inv.all()),
            "/api/v1/topology": ("topology:read", lambda: self.manager.db.get_neighbors()),
            "/api/v1/drift": ("drift:read", lambda: [dict(device=d["name"], **self.manager.store.drift(d["name"])) for d in self.manager.inv.all()]),
            "/api/v1/compliance/latest": ("compliance:read", lambda: self.manager.db.conn.execute("SELECT * FROM compliance_runs ORDER BY id DESC LIMIT 1").fetchone()),
            "/api/v1/audit": ("audit:read", lambda: self.manager.db.recent_audit(200)),
            "/api/v1/digest/latest": ("compliance:read", lambda: self.manager.db.latest_digest()),
        }
        item = routes.get(path)
        if not item: return False
        scope, fn = item
        if scope not in scopes:
            self._api_json({"error": "insufficient_scope", "required": scope}, 403); return True
        value = fn()
        if hasattr(value, "keys") and not isinstance(value, dict): value = dict(value)
        self.manager.db.audit("api:" + token["name"], "api_read", path, scope)
        self._api_json(value if value is not None else {}); return True

    def do_GET(self):
        self._responded = False
        try:
            self._route_get()
        except Exception:
            self._server_error()

    def do_POST(self):
        self._responded = False
        try:
            self._route_post()
        except Exception:
            self._server_error()

    def _server_error(self):
        import traceback
        tb = traceback.format_exc()
        try:
            sys.stderr.write("NetConfig 500 on %s %s\n%s\n" % (self.command, self.path, tb))
            sys.stderr.flush()
        except Exception:
            pass
        if getattr(self, "_responded", False):
            return  # a response was already (partly) sent; don't corrupt it
        msg = tb.strip().splitlines()[-1] if tb.strip() else "internal error"
        hint = ""
        low = msg.lower()
        if "readonly" in low or "unable to open database" in low or "permission" in low:
            hint = ("<p>The data directory is not writable by the service. If you ran "
                    "<code>netconfig</code> as root earlier, its files are root-owned. Fix with:"
                    "<br><code>sudo chown -R netconfig:netconfig /var/lib/netconfig</code><br>"
                    "then <code>sudo systemctl restart netconfig-web</code>.</p>")
        body = (f'<!doctype html><html><head><meta charset=utf-8><title>Error</title>'
                f'<style>{_CSS}</style>{_THEME_JS}</head><body><div class="login-wrap"><div class="panel" '
                f'style="max-width:640px"><h2 style="color:var(--bad)">Server error</h2>'
                f'<p class="muted">The request failed. Details:</p>'
                f'<pre>{html.escape(msg)}</pre>{hint}</div></div></body></html>')
        try:
            self._send(body, 500)
        except Exception:
            pass

    def _route_get(self):
        u = urllib.parse.urlparse(self.path)
        if u.path.startswith("/api/v1/") and self._handle_api_get(u.path):
            return
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/healthz":
            return self._health(False)
        if u.path == "/readyz":
            return self._health(True)
        if u.path == "/metrics":
            return self._metrics()
        if u.path == "/login":
            return self._login_page()
        routes = {
            "/": lambda s: self._dashboard(s),
            "/device": lambda s: self._device_page(q, s),
            "/device-new": lambda s: self._device_form(q, s),
            "/raw": lambda s: self._raw(q),
            "/diff": lambda s: self._diff_page(q, s),
            "/groups": lambda s: self._groups_page(s),
            "/automation": lambda s: self._automation_page(s),
            "/requests": lambda s: self._requests_page(s),
            "/request": lambda s: self._request_page(q, s),
            "/compliance": lambda s: self._compliance_page(q, s),
            "/alerts": lambda s: self._alerts_page(q, s),
            "/snmp": lambda s: self._snmp_page(q, s),
            "/topology": lambda s: self._topology_page(s),
            "/snmp-series": lambda s: self._snmp_series(q, s),
            "/snmp-history": lambda s: self._snmp_history(q, s),
            "/secret-info": lambda s: self._secret_info(q, s),
            "/vault": lambda s: self._vault_page(q, s),
            "/settings": lambda s: self._settings_page_v2(s, q=q),
            "/users": lambda s: self._users_page(s),
            "/audit": lambda s: self._audit_page(s),
            "/runs": lambda s: self._runs_page(s),
            "/help": lambda s: self._help_page(s),
            "/mib": lambda s: self._mib_page(q, s),
        }
        h = routes.get(u.path)
        if not h:
            return self._send("not found", 404, "text/plain")
        sess = self._require_auth()
        if sess is None:
            return
        return h(sess)

    def _route_post(self):
        u = urllib.parse.urlparse(self.path)
        if u.path == "/mib-upload":
            return self._do_mib_upload_raw()
        form = self._read_post()
        if u.path == "/login":
            return self._do_login(form)
        if not self._require_auth():
            return
        _, sess = self._session()
        if not self._check_csrf(form):
            return self._send(self._page("Error",
                              '<div class="err">CSRF check failed.</div>', sess), 403)
        handlers = {
            "/logout": lambda: self._do_logout(),
            "/unlock-vault": lambda: self._do_unlock(form, sess),
            "/collect": lambda: self._do_collect(form, sess),
            "/snmp-poll": lambda: self._do_snmp(form, sess),
            "/topology-discover": lambda: self._do_topology_discover(form, sess),
            "/device-save": lambda: self._do_device_save(form, sess),
            "/device-delete": lambda: self._do_device_delete(form, sess),
            "/device-run": lambda: self._do_device_run(form, sess),
            "/group-save": lambda: self._do_group_save(form, sess),
            "/group-delete": lambda: self._do_group_delete(form, sess),
            "/baseline-set": lambda: self._do_baseline(form, sess, True),
            "/baseline-clear": lambda: self._do_baseline(form, sess, False),
            "/request-submit": lambda: self._do_request_submit(form, sess),
            "/request-approve": lambda: self._do_request_action(form, sess, "approve"),
            "/request-reject": lambda: self._do_request_action(form, sess, "reject"),
            "/request-execute": lambda: self._do_request_execute(form, sess),
            "/run-adhoc": lambda: self._do_run_adhoc(form, sess),
            "/script-save": lambda: self._do_script_save(form, sess),
            "/script-delete": lambda: self._do_script_delete(form, sess),
            "/mib-delete": lambda: self._do_mib_delete(form, sess),
            "/compliance-run": lambda: self._do_compliance_run(form, sess),
            "/alert-rule-add": lambda: self._do_alert_rule_add(form, sess),
            "/alert-rule-delete": lambda: self._do_alert_rule_delete(form, sess),
            "/smtp-test": lambda: self._do_smtp_test(form, sess),
            "/oauth-test": lambda: self._do_oauth_test(form, sess),
            "/db-test": lambda: self._do_db_test(form, sess),
            "/vault-create": lambda: self._do_vault_create(form, sess),
            "/vault-secret-save": lambda: self._do_vault_secret_save(form, sess),
            "/vault-secret-delete": lambda: self._do_vault_secret_delete(form, sess),
            "/settings-save": lambda: self._do_settings_save_v2(form, sess),
            "/user-create": lambda: self._do_user_create(form, sess),
            "/user-update": lambda: self._do_user_update(form, sess),
        }
        h = handlers.get(u.path)
        if h:
            return h()
        self._send("not found", 404, "text/plain")

    # ---- auth ------------------------------------------------------------
    def _login_page(self, error=None):
        if self.manager.users.count() == 0:
            body = ('<div class="login-wrap"><div class="panel login">'
                    '<div class="brand">Net<span>Config</span></div>'
                    '<div class="sub">Security Operations \u00b7 v'+APP_VERSION+'</div>'
                    '<div class="err">No users yet. Create the first admin:<br>'
                    '<code>netconfig user add &lt;name&gt; --role admin</code></div></div></div>')
            return self._send(f"<!doctype html><html><head><meta charset=utf-8>"
                              f"<style>{_CSS}</style>{_THEME_JS}</head><body>{body}</body></html>")
        err = f'<div class="err">{html.escape(error)}</div>' if error else ""
        body = f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Sign in \u00b7 NetConfig</title><style>{_CSS}</style>{_THEME_JS}</head><body>
<div class="login-wrap"><div class="panel login">
<div class="brand">Net<span>Config</span></div>
<div class="sub">Security Operations \u00b7 v{APP_VERSION}</div>{err}
<form method=post action="/login">
<input type=text name=username placeholder="Username" autofocus autocomplete=username>
<input type=password name=password placeholder="Password" autocomplete=current-password>
<button style="width:100%">Sign in</button></form>
<div class="muted" style="text-align:center;margin-top:14px">
Local console \u00b7 bind 127.0.0.1 \u00b7 front with WAF for TLS</div>
</div></div></body></html>"""
        self._send(body)

    def _do_login(self, form):
        user = (form.get("username") or [""])[0].strip()
        pw = (form.get("password") or [""])[0]
        ip = self._client_ip()
        retry = _LOGIN_THROTTLE.retry_after(ip, user)
        if retry:
            self.manager.db.audit(user or "(blank)", "login_throttled", "console", f"source={ip}")
            _obs_event("auth_throttled", username=user, source_ip=ip, retry_after=retry)
            return self._send("<!doctype html><html><body><h1>Too many failed attempts</h1><p>Try again shortly.</p></body></html>",
                              429, headers=[("Retry-After", str(retry))])
        u = self.manager.users.verify(user, pw)
        if not u:
            retry = _LOGIN_THROTTLE.failure(ip, user)
            self.manager.db.audit(user or "(blank)", "login_failure", "console", f"source={ip}")
            METRICS.inc("netconfig_auth_failures_total")
            _obs_event("auth_failure", username=user, source_ip=ip)
            return self._login_page(error="Invalid username or password.")
        _LOGIN_THROTTLE.success(ip, user)
        token = secrets.token_urlsafe(32)
        _SESSIONS[token] = {"username": u["username"], "role": u["role"],
                            "csrf": secrets.token_urlsafe(24), "created": time.time()}
        self.manager.db.audit(u["username"], "login", "console", f"source={ip}")
        METRICS.inc("netconfig_logins_total")
        _obs_event("auth_success", username=u["username"], source_ip=ip)
        secure = "; Secure" if (self.manager.settings.get("cookie_secure") or self.tls_enabled) else ""
        self._redirect("/", headers=[
            ("Set-Cookie", f"ncsid={token}; HttpOnly; SameSite=Strict; Path=/{secure}")])

    def _do_logout(self):
        tok, sess = self._session()
        _SESSIONS.pop(tok, None)
        if sess:
            self.manager.db.audit(sess["username"], "logout", "console", f"source={self._client_ip()}")
            _obs_event("auth_logout", username=sess["username"], source_ip=self._client_ip())
        self._redirect("/login", headers=[("Set-Cookie", "ncsid=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/")])

    def _do_unlock(self, form, sess):
        if not _can(sess["role"], "unlock_vault"):
            return self._dashboard(sess, flash="Not permitted to unlock the vault.")
        pw = (form.get("master") or [""])[0]
        try:
            self.manager.unlock_vault(pw)
            self.manager.db.audit(sess["username"], "unlock_vault", "", "")
            return self._dashboard(sess, flash="Vault unlocked for this process.")
        except ValueError:
            return self._dashboard(sess, flash="Wrong master password.")

    # ---- dashboard -------------------------------------------------------
    def _dashboard(self, sess, flash=None):
        m = self.manager
        devices = m.inv.all()
        metas = {d["device"]: d for d in m.store.devices()}
        facts = m.inv.all_facts()
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
                    snmp += f' <span class="muted">{html.escape(fx["sysname"])}</span>'
            collect_btn = ""
            if managed and _can(sess["role"], "collect"):
                collect_btn = (f'<form method=post action="/collect" style="display:inline">'
                               f'{self._csrf_field()}<input type=hidden name=name '
                               f'value="{html.escape(d["name"])}">'
                               f'<button style="padding:4px 12px">Collect</button></form>')
            _typ = " ".join(f'<span class="badge b-dim">{t.capitalize()}</span>'
                            for t in sorted(_dtypes(d)))
            snmp_cell = snmp or '<span class=muted>\u2014</span>'
            tags = d.get("tags") or []
            # name (partial), IP/host, and tags are what the search box matches on
            blob = " ".join([d["name"], d["host"]] + [str(t) for t in tags]).lower()
            address = (f'{html.escape(d["host"])}:{d["port"]}' if managed
                       else html.escape(d["host"]))
            platform = html.escape(d["platform"]) if managed else '<span class="muted">—</span>'
            return f"""<tr class="devrow" data-search="{html.escape(blob, quote=True)}">
<td><a href="/device?name={_q(d['name'])}">{html.escape(d['name'])}</a>{en}</td>
<td class="muted">{address}</td>
<td>{_typ}</td>
<td>{platform}</td>
<td>{st}</td><td>{snmp_cell}</td>
<td class="muted">{last}</td><td class="right">{collect_btn}</td></tr>"""

        _thead = ("<table><tr><th>Device</th><th>Address</th><th>Type</th><th>Platform</th>"
                  "<th>Config</th><th>SNMP</th><th>Last collected</th><th></th></tr>")
        # Group by device type; a device with more than one type appears in each
        # of its groups. Groups are collapsed by default.
        by_type = {"network": [], "system": [], "application": []}
        for d in devices:
            for t in _dtypes(d):
                if t in by_type:
                    by_type[t].append(d)
        groups_html = ""
        for t, label in (("network", "Network"), ("system", "System"),
                         ("application", "Application")):
            ds = by_type[t]
            if not ds:
                continue
            body = _thead + "".join(make_row(d) for d in ds) + "</table>"
            groups_html += (
                f'<details class="devgroup">'
                f'<summary>{label} \u00b7 <span class="devcount">{len(ds)}</span></summary>'
                f'{body}</details>')
        if devices:
            search_box = (
                '<div class="panel" style="padding:10px 14px">'
                '<input id="devsearch" type="search" autocomplete="off" '
                'placeholder="Search devices by name, IP address, or tag\u2026" '
                'style="width:100%;box-sizing:border-box;padding:9px 12px;font-size:15px">'
                '</div>')
            no_results = ('<p id="devnoresults" class="muted" '
                          'style="display:none">No devices match your search.</p>')
            listing = groups_html + no_results
        else:
            search_box = ""
            listing = ('<p class="muted">No devices. Add one with '
                       '<code>netconfig device add</code>.</p>')
        vault_panel = ""
        if not m.vault_ready() and _can(sess["role"], "unlock_vault"):
            vault_panel = (f'<div class="panel"><h2>Vault locked</h2>'
                           f'<p class="muted">Device credentials are needed to collect, '
                           f'run jobs, or poll SNMP. Unlock for this process:</p>'
                           f'<form method=post action="/unlock-vault" class="row">'
                           f'{self._csrf_field()}'
                           f'<input type=password name=master placeholder="Vault master password">'
                           f'<div style="flex:0"><button>Unlock</button></div></form></div>')
        collect_all = ""
        if _can(sess["role"], "collect"):
            collect_all = (f'<form method=post action="/collect" style="margin-left:auto">'
                           f'{self._csrf_field()}<input type=hidden name=all value=1>'
                           f'<button>Collect all enabled</button></form>')
        add_dev = ""
        if _can(sess["role"], "manage_devices"):
            add_dev = ('<a class="btn" href="/device-new" '
                       'style="margin-left:auto">+ Add device</a>')
        header_actions = add_dev + collect_all
        if add_dev and collect_all:
            # keep both on the right, add-device first
            header_actions = (add_dev
                              + collect_all.replace('style="margin-left:auto"', 'style="margin-left:10px"'))
        inner = f"""{vault_panel}{search_box}<div class="panel">
<div style="display:flex;align-items:center;margin-bottom:12px">
<h2 style="border:none;margin:0">Inventory \u00b7 {len(devices)} devices</h2>{header_actions}</div>
{listing}</div>{_DASH_JS}"""
        self._send(self._page("Devices", inner, sess, flash=flash))

    def _device_page(self, q, sess):
        name = (q.get("name") or [""])[0]
        m = self.manager
        dev = m.inv.get(name)
        if not dev:
            return self._send(self._page("Device", '<div class="err">Unknown device.</div>', sess), 404)
        _dt = _dtypes(dev)
        managed = _is_managed_device(dev)
        application_only = _dt == {"application"}
        cur = m.store.current(name) if managed else None
        versions = m.store.versions(name) if managed else []
        cfg_html = f'<pre>{html.escape(cur)}</pre>' if cur else '<p class="muted">No config stored yet.</p>'

        drift = m.store.drift(name) if managed else None
        drift_html = ""
        base = m.store.get_baseline(name) if managed else None
        base_ctrl = ""
        if _can(sess["role"], "manage_devices") and versions:
            if base:
                base_ctrl = (f'<form method=post action="/baseline-clear" style="display:inline">'
                             f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(name)}">'
                             f'<button class=ghost>Clear baseline</button></form>')
            base_ctrl += (f'<form method=post action="/baseline-set" style="display:inline;margin-left:6px">'
                          f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(name)}">'
                          f'<button>Set current as baseline</button></form>')
        if base:
            if drift["drifted"]:
                rem = ""
                if _can(sess["role"], "remediate"):
                    rem = (f'<form method=post action="/request-submit" style="display:inline;margin-left:8px">'
                           f'{self._csrf_field()}'
                           f'<input type=hidden name=title value="Remediate drift on {html.escape(name)}">'
                           f'<input type=hidden name=body value="(replay baseline)">'
                           f'<input type=hidden name=target_kind value="device">'
                           f'<input type=hidden name=target_value value="{html.escape(name)}">'
                           f'<input type=hidden name=mode value="remediate">'
                           f'<button class=danger>Submit remediation request</button></form>')
                drift_html = (f'<div class="panel"><h2>Drift from baseline '
                              f'<span class="badge b-bad">drifted</span></h2>'
                              f'<pre class="diff">{_colorize_diff(drift["diff"])}</pre>{rem}</div>')
            else:
                drift_html = ('<div class="panel"><h2>Baseline '
                              '<span class="badge b-ok">in sync</span></h2>'
                              '<p class="muted">Current config matches the baseline.</p></div>')

        opts = "".join(f'<option value="{html.escape(v["stamp"])}">{html.escape(v["stamp"])}</option>'
                       for v in reversed(versions))
        diff_picker = ""
        if len(versions) >= 2:
            diff_picker = (f'<div class="panel"><h2>Compare versions</h2>'
                           f'<form method=get action="/diff" class="row">'
                           f'<input type=hidden name=name value="{html.escape(name)}">'
                           f'<div><label>Older</label><select name=a>{opts}</select></div>'
                           f'<div><label>Newer</label><select name=b>{opts}</select></div>'
                           f'<div style="flex:0;align-self:end"><button>Diff</button></div>'
                           f'</form></div>')

        vrows = "".join(
            f'<tr><td class="muted">{html.escape(v["stamp"])}</td>'
            f'<td class="muted">{html.escape(v["hash"][:16])}</td>'
            f'<td class="right"><a href="/raw?name={_q(name)}&version={_q(v["stamp"])}" target=_blank>raw</a></td></tr>'
            for v in reversed(versions)) or '<tr><td class="muted" colspan=3>none</td></tr>'

        fx = m.inv.get_facts(name) if managed else None
        snmp_html = ""
        if fx:
            _oid = (fx.get("sysobjectid") or "").strip()
            if _oid:
                _mapping = self.manager.mibindex.resolve_detail(_oid)
                _resolved = _mapping["name"]
                _source = _mapping["source"]
                _source_html = (f' <span class="muted">MIB: {html.escape(_source)}</span>'
                                if _source else "")
                _clean = _resolved.lstrip(".")
                if _resolved and _clean != _oid.lstrip("."):
                    if re.search(r"[A-Za-z][\w-]*\.\d", _resolved):   # name + numeric tail = partial
                        _oid_cell = (f'<b>{html.escape(_resolved)}</b> '
                                     f'<span class="muted">{html.escape(_oid)} \u00b7 upload the '
                                     f'vendor MIB to fully name it</span>{_source_html}')
                    else:                                             # fully named
                        _oid_cell = (f'<b>{html.escape(_resolved)}</b> '
                                     f'<span class="muted">{html.escape(_oid)}</span>{_source_html}')
                else:
                    _oid_cell = (f'<code>{html.escape(_oid)}</code> '
                                 f'<span class="muted">(no MIB match)</span>')
                _oid_row = f'<tr><th>Model (sysObjectID)</th><td>{_oid_cell}</td></tr>'
            else:
                _oid_row = ""
            snmp_html = (f'<table>'
                         f'<tr><th>Reachable</th><td>{"yes" if fx["reachable"] else "no"}</td></tr>'
                         f'<tr><th>sysName</th><td>{html.escape(fx["sysname"])}</td></tr>'
                         f'<tr><th>sysDescr</th><td>{html.escape(fx["sysdescr"])}</td></tr>'
                         f'{_oid_row}'
                         f'<tr><th>Uptime</th><td>{html.escape(fx["uptime"])}</td></tr>'
                         f'<tr><th>Contact</th><td>{html.escape(fx.get("contact", ""))}</td></tr>'
                         f'<tr><th>Location</th><td>{html.escape(fx["location"])}</td></tr>'
                         f'<tr><th>Polled</th><td>{_fmt_ts(fx["last_polled"])}</td></tr></table>')
        snmp_btn = ""
        if _can(sess["role"], "collect") and dev.get("snmp_version"):
            snmp_btn = (f'<form method=post action="/snmp-poll" style="margin-top:10px">'
                        f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(name)}">'
                        f'<button>Poll SNMP</button></form>')

        collect_btn = ""
        if managed and _can(sess["role"], "collect"):
            collect_btn = (f'<form method=post action="/collect" style="margin-top:14px">'
                           f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(name)}">'
                           f'<button>Collect now</button>'
                           f'<a class="btn" style="margin-left:8px" href="/raw?name={_q(name)}" target=_blank>Current raw</a>'
                           f'</form>')
        edit_link = ""
        if _can(sess["role"], "manage_devices"):
            edit_link = (f'<a class="btn ghost" href="/device-new?name={_q(name)}" '
                         f'style="float:right;padding:4px 12px">Edit</a>')
        address = html.escape(dev["host"])
        address_row = (f'<tr><th>Primary hostname</th><td>{address}</td></tr>'
                       if application_only else
                       f'<tr><th>Address</th><td>{address}:{dev["port"]}</td></tr>')
        managed_rows = ""
        if managed:
            managed_rows = (f'<tr><th>Platform</th><td>{html.escape(dev["platform"])}</td></tr>'
                            f'<tr><th>Auth</th><td>{"SSH key" if dev["use_key"] else "password"}'
                            f'{" \u00b7 legacy algos" if dev["legacy"] else ""}'
                            f'{" \u00b7 scrubbed" if dev["scrub"] else ""}</td></tr>'
                            f'<tr><th>SNMP</th><td>{html.escape(dev.get("snmp_version") or "\u2014")}</td></tr>')
        base_html = ('<div style="margin-top:12px">' + base_ctrl + '</div>') if base_ctrl else ""
        meta = (f'<div class="panel"><h2>{html.escape(name)}{edit_link}</h2><table>'
                f'{address_row}<tr><th>Type</th><td>'
                f'{html.escape(", ".join(t.capitalize() for t in sorted(_dt)))}</td></tr>'
                f'{managed_rows}</table>{collect_btn}{base_html}</div>')
        run_panel = ""
        if managed and _can(sess["role"], "execute"):
            run_panel = (f'<div class="panel"><h2>Run command</h2>'
                         f'<p class="muted">Runs a single command on the device now (audited). '
                         f'For config changes across many devices, use a change request.</p>'
                         f'<form method=post action="/device-run" class="row">{self._csrf_field()}'
                         f'<input type=hidden name=name value="{html.escape(name)}">'
                         f'<input name=command placeholder="show version" style="margin:0">'
                         f'<div style="flex:0"><button>Run</button></div></form></div>')
        iface_tbl = self._interface_table(name) if managed else ""
        iface_section = ""
        if iface_tbl:
            iface_section = (f'<h2 style="margin-top:14px">Interfaces</h2>{iface_tbl}')
        snmp_link = (f'<a class="btn ghost" href="/snmp?device={_q(name)}" '
                     f'style="margin-left:8px;padding:4px 12px">SNMP page</a>') if dev.get("snmp_version") else ""
        snmp_panel = ((f'<div class="panel"><h2>SNMP facts</h2>'
                       f'{snmp_html or "<p class=muted>Not polled yet.</p>"}'
                       f'{snmp_btn}{snmp_link}{iface_section}</div>') if managed else "")
        # diff of the two most recent stored versions (green added / red deleted)
        lastchange_html = ""
        if len(versions) >= 2:
            a, b = versions[-2]["stamp"], versions[-1]["stamp"]
            try:
                d_lc = m.store.diff_versions(name, a, b)
            except Exception:
                d_lc = ""
            body_lc = (f'<pre class="diff">{_colorize_diff(d_lc)}</pre>' if d_lc
                       else '<p class="muted">No line changes between the last two saved copies.</p>')
            lastchange_html = (f'<div class="panel"><h2>Changes in last backup</h2>'
                               f'<p class="muted">Difference between the previous saved copy and '
                               f'the current one \u2014 <span style="color:var(--ok)">green = added</span>, '
                               f'<span style="color:var(--red)">red = deleted</span>.</p>{body_lc}</div>')
        elif len(versions) == 1:
            lastchange_html = ('<div class="panel"><h2>Changes in last backup</h2>'
                               '<p class="muted">Only one saved copy so far \u2014 a comparison '
                               'appears once the config changes and a second copy is stored.</p></div>')
        netflow_panel = self._netflow_section(dev) if "network" in _dt else ""
        portmon_panel = self._portmon_section(dev) if "system" in _dt else ""
        appmon_panel = self._appmon_section(dev) if "application" in _dt else ""
        management_panels = ""
        if managed:
            management_panels = (run_panel + drift_html + diff_picker
                                 + f'<div class="panel"><h2>Current configuration</h2>{cfg_html}</div>'
                                 + lastchange_html + snmp_panel
                                 + f'<div class="panel"><h2>Config backups \u00b7 {len(versions)} saved</h2>'
                                   f'<p class="muted">Each snapshot is a saved copy of the running config. '
                                   f'The weekly backup keeps the newest {self.manager.settings.get("backup_keep",5)} per device.</p>'
                                   f'<table><tr><th>Snapshot</th><th>SHA-256</th><th></th></tr>{vrows}</table></div>')
        inner = meta + management_panels + netflow_panel + portmon_panel + appmon_panel
        if "network" in _dt:
            inner += self._arp_section(dev) + self._mac_port_section(dev)
        self._send(self._page(f"Device \u00b7 {name}", inner, sess))

    # ---- device create / edit / delete / run ----------------------------
    def _secret_datalist(self, list_id):
        """A <datalist> of vault secret names when the vault is unlocked."""
        try:
            names = list(self.manager.vault.list_secrets().keys()) if self.manager.vault_ready() else []
        except Exception:
            names = []
        opts = "".join(f'<option value="{html.escape(n)}">' for n in names)
        return f'<datalist id="{list_id}">{opts}</datalist>'

    def _secret_select(self, field_id, name, current, none_label="\u2014 none \u2014"):
        """A <select> of saved vault secret names (like the SNMP-version dropdown).
        Preserves the currently-saved value as an option even if the vault is
        locked, so editing never silently drops a reference."""
        try:
            names = sorted(self.manager.vault.list_secrets().keys()) if self.manager.vault_ready() else []
        except Exception:
            names = []
        cur = (current or "").strip()
        if cur and cur not in names:
            names = [cur] + names
        opts = [f'<option value="">{html.escape(none_label)}</option>']
        for n in names:
            sel = " selected" if n == cur else ""
            opts.append(f'<option value="{html.escape(n)}"{sel}>{html.escape(n)}</option>')
        idattr = f' id="{field_id}"' if field_id else ""
        return f'<select{idattr} name="{name}">{"".join(opts)}</select>'

    def _device_form(self, q, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._send(self._page("Device", '<div class="err">Not permitted.</div>', sess), 403)
        name = (q.get("name") or [""])[0]
        d = self.manager.inv.get(name) if name else None
        editing = d is not None
        title = f"Edit {name}" if editing else "Add device"
        plats = "".join(
            f'<option value="{p}"{" selected" if d and d["platform"]==p else ""}>{p}</option>'
            for p in _platforms())
        cur_types = _dtypes(d) if d else {"network"}
        type_checks = "".join(
            f'<label style="font-weight:400;margin-right:16px;display:inline-block">'
            f'<input type=checkbox name=device_type value="{val}" style="width:auto"'
            f'{" checked" if val in cur_types else ""}> {lab}</label>'
            for val, lab in _DEVICE_TYPES)
        snmp_opts = ""
        for val, lab in (("", "none"), ("v2c", "v2c"), ("v3", "v3")):
            sel = " selected" if d and (d.get("snmp_version") or "") == val else ""
            snmp_opts += f'<option value="{val}"{sel}>{lab}</option>'

        def v(k, default=""):
            return html.escape(str(d[k])) if d and d.get(k) is not None else default

        def chk(k):
            return "checked" if d and d.get(k) else ""
        # prefill SNMP fields from the device's referenced secret (when unlocked)
        snmp_sec = {}
        if d and d.get("snmp_ref") and self.manager.vault_ready():
            try:
                snmp_sec = self.manager.vault.get_secret(d["snmp_ref"])
            except KeyError:
                snmp_sec = {}
        def sv(k):
            return html.escape(str(snmp_sec.get(k, "")))
        def sset(k):
            return " \u2713 set" if snmp_sec.get(k) else ""
        def _proto_opts(opts, cur):
            o = '<option value="">\u2014</option>'
            for val, lab in opts:
                o += f'<option value="{val}"{" selected" if cur == val else ""}>{lab}</option>'
            return o
        auth_opts = _proto_opts([("sha", "SHA-1"), ("sha224", "SHA-224"), ("sha256", "SHA-256"),
                                 ("sha384", "SHA-384"), ("sha512", "SHA-512"), ("md5", "MD5")],
                                snmp_sec.get("snmp_auth_proto"))
        priv_opts = _proto_opts([("aes", "AES-128"), ("aes192", "AES-192"), ("aes256", "AES-256")],
                                snmp_sec.get("snmp_priv_proto"))
        # prefill SSH login fields from the device's SSH secret (when unlocked)
        ssh_sec = {}
        if d and d.get("secret_ref") and self.manager.vault_ready():
            try:
                ssh_sec = self.manager.vault.get_secret(d["secret_ref"])
            except KeyError:
                ssh_sec = {}
        def uv(k):
            return html.escape(str(ssh_sec.get(k, "")))
        def uset(k):
            return " \u2713 set" if ssh_sec.get(k) else ""
        open_manual = " open" if not (d and (d.get('secret_ref') or d.get('snmp_ref'))) else ""
        vault_hint = ("" if self.manager.vault_ready()
                      else ' \u2014 <b>unlock the vault first</b> to store these')
        tags = ", ".join(d["tags"]) if d else ""
        name_field = (f'<input name=name value="{html.escape(name)}">'
                      f'<input type=hidden name=orig_name value="{html.escape(name)}">'
                      if editing else '<input name=name placeholder="e.g. core-sw1" autofocus>')
        body = f"""<div class="panel"><h2>{html.escape(title)}</h2>
<form method=post action="/device-save">{self._csrf_field()}
<div class="row">
  <div><label>Name</label>{name_field}</div>
  <div><label id=host_label>Host / IP</label><input name=host value="{v('host')}" placeholder="10.0.0.11"></div>
  <div id=ssh_port_field style="max-width:120px"><label>SSH port</label><input name=port value="{v('port','22')}"></div>
</div>
<div class="row">
  <div><label>Device type</label><div style="padding-top:6px">{type_checks}</div></div>
  <div id=platform_field><label>Platform</label><select name=platform>{plats}</select></div>
  <div><label>Tags (comma-separated)</label><input name=tags value="{html.escape(tags)}" placeholder="core, dc1"></div>
</div>
<div id=credentials_section>
<h2 style="margin-top:14px">Credentials</h2>
<p class="muted">Point the device at existing vault secrets (recommended). Pick one and its
stored settings appear below — the vault keeps the passwords.{vault_hint}</p>
<div class="row">
  <div><label>SSH vault secret</label>{self._secret_select('secret_ref','secret_ref', d.get('secret_ref') if d else '')}{'' if self.manager.vault_ready() else '<div class=muted>Unlock the vault to choose a saved secret.</div>'}</div>
  <div><label>SNMP vault secret</label>{self._secret_select('snmp_ref','snmp_ref', d.get('snmp_ref') if d else '')}</div>
  <div><label>Enable vault secret (optional)</label>{self._secret_select('','enable_ref', d.get('enable_ref') if d else '')}</div>
</div>
<div id=secinfo class="muted" style="margin:-2px 0 10px"></div>
<div class="row">
  <div><label>SNMP version</label><select name=snmp_version>{snmp_opts}</select></div>
  <div><label style="font-weight:400"><input type=checkbox name=use_key value=1 style="width:auto" {chk('use_key')}> device uses an SSH key (not a password)</label></div>
  <div></div>
</div>
<details style="margin:8px 0"{open_manual}>
<summary style="cursor:pointer;color:var(--navy);font-weight:600">Enter new credentials manually (creates a vault secret for this device)</summary>
<h3>SSH login</h3>
<div class="row">
  <div><label>SSH username{uset('username')}</label><input id=ssh_username name=ssh_username value="{uv('username')}" placeholder="admin"></div>
  <div><label>SSH password<span id=set_password>{uset('password')}</span></label><input type=password name=ssh_password></div>
  <div><label>Enable password<span id=set_enable_password>{uset('enable_password')}</span></label><input type=password name=enable_password placeholder="Cisco enable mode"></div>
</div>
<div class="row">
  <div><label>SSH private key path{uset('key_path')}</label><input name=key_path value="{uv('key_path')}" placeholder="/var/lib/netconfig/keys/id_ed25519"></div>
  <div><label>Key passphrase{uset('key_passphrase')}</label><input type=password name=key_passphrase></div>
  <div></div>
</div>
<h3>SNMP authentication</h3>
<div class="row">
  <div><label>SNMPv3 username{sset('snmp_user')}</label><input id=snmp_user name=snmp_user value="{sv('snmp_user')}" placeholder="snmp-admin"></div>
  <div><label>v2c community<span id=set_community>{sset('community')}</span></label><input type=password name=community></div>
  <div style="max-width:120px"><label>SNMP port</label><input id=snmp_port name=snmp_port value="{sv('snmp_port')}" placeholder="161"></div>
</div>
<div class="row">
  <div><label>v3 auth proto</label><select id=snmp_auth_proto name=snmp_auth_proto>{auth_opts}</select></div>
  <div><label>v3 auth pass<span id=set_snmp_auth_pass>{sset('snmp_auth_pass')}</span></label><input type=password name=snmp_auth_pass></div>
  <div><label>v3 priv proto</label><select id=snmp_priv_proto name=snmp_priv_proto>{priv_opts}</select></div>
  <div><label>v3 priv pass<span id=set_snmp_priv_pass>{sset('snmp_priv_pass')}</span></label><input type=password name=snmp_priv_pass></div>
</div></details>
</div>
<div id=netflow_section style="display:none">
<h2 style="margin-top:14px">NetFlow</h2>
<p class="muted">Receive NetFlow exports from this device. The collector listens on
<code>udp/{self.manager.settings.get("netflow_port", 2055)}</code> (toggle it in Settings \u2192 NetFlow).
Point this device's flow export at this server's IP on that port.</p>
<label style="font-weight:400"><input type=checkbox name=netflow value=1 style="width:auto" {chk('netflow')}> collect NetFlow from this device</label>
</div>
<div id=portmon_section style="display:none">
<h2 style="margin-top:14px">TCP / UDP ports</h2>
<p class="muted">Monitor port status on this system. List ports to check as
<code>tcp/22, tcp/443, udp/53</code> (bare numbers default to TCP). Status is checked
live when you open the device.</p>
<label>Ports to monitor</label>
<input name=monitor_ports value="{html.escape(str((d.get('monitor_ports') if d else '') or ''))}" placeholder="tcp/22, tcp/80, tcp/443, udp/161">
</div>
<div id=appmon_section style="display:none">
<h2 style="margin-top:14px">REST API / HTTPS</h2>
<p class="muted">Monitor HTTP(S) endpoints for this application \u2014 one URL per line, with
an optional expected status code. HTTPS URLs also get a TLS certificate check
(validity + days to expiry). Examples:<br>
<code>https://{html.escape((d.get('host') if d else '') or 'app.example.com')}/</code><br>
<code>https://{html.escape((d.get('host') if d else '') or 'app.example.com')}/api/health 200</code></p>
<label>Endpoints to monitor</label>
<textarea name=monitor_urls placeholder="https://host/&#10;https://host/api/health 200" style="min-height:90px">{html.escape(str((d.get('monitor_urls') if d else '') or ''))}</textarea>
</div>
<script>
(function(){{
  var boxes=document.querySelectorAll('input[name=device_type]'),
      nf=document.getElementById('netflow_section'),
      pm=document.getElementById('portmon_section'),
      am=document.getElementById('appmon_section'),
      sshPort=document.getElementById('ssh_port_field'),
      platform=document.getElementById('platform_field'),
      credentials=document.getElementById('credentials_section'),
      managementOptions=document.getElementById('management_options'),
      hostLabel=document.getElementById('host_label');
  function has(v){{ for(var i=0;i<boxes.length;i++){{ if(boxes[i].value===v&&boxes[i].checked) return true; }} return false; }}
  function toggle(el,on,display){{
    if(!el) return;
    el.style.display=on?(display||'block'):'none';
    var controls=el.querySelectorAll('input,select,textarea,button');
    for(var i=0;i<controls.length;i++) controls[i].disabled=!on;
  }}
  function upd(){{
    var managed=has('system')||has('network');
    toggle(nf,has('network'));
    toggle(pm,has('system'));
    toggle(am,has('application'));
    toggle(sshPort,managed);
    toggle(platform,managed);
    toggle(credentials,managed);
    toggle(managementOptions,managed,'flex');
    if(hostLabel) hostLabel.textContent=managed?'Host / IP':'Primary hostname / FQDN'; }}
  for(var i=0;i<boxes.length;i++) boxes[i].addEventListener('change',upd);
  upd();
}})();
</script>
<script>
(function(){{
  var summ={{}};
  function fill(id,val){{var e=document.getElementById(id); if(e&&val!=null&&val!=='') e.value=val;}}
  function mark(id,on){{var e=document.getElementById('set_'+id); if(e) e.textContent=on?' \u2713 set':'';}}
  function render(){{var el=document.getElementById('secinfo'); if(!el) return;
    var parts=[]; if(summ.ssh) parts.push(summ.ssh); if(summ.snmp) parts.push(summ.snmp);
    el.innerHTML=parts.join(' &nbsp;\u00b7&nbsp; ');}}
  function load(name,kind){{
    if(!name){{ summ[kind]=''; render(); return; }}
    fetch('/secret-info?name='+encodeURIComponent(name)).then(function(r){{return r.json();}}).then(function(j){{
      if(!j.exists){{ summ[kind]='<span style="color:var(--red)">no vault secret named \''+name+'\'</span>'; render(); return; }}
      var f=j.fields||{{}}, s=j.set||{{}};
      if(kind==='ssh'){{
        fill('ssh_username',f.username); mark('password',s.password); mark('enable_password',s.enable_password);
        var b=[]; if(f.username) b.push('user '+f.username); if(s.password) b.push('password set'); if(s.key_path) b.push('SSH key'); if(s.enable_password) b.push('enable set');
        summ.ssh='<b>SSH \''+name+'\':</b> '+(b.join(', ')||'no fields');
      }} else {{
        fill('snmp_user',f.snmp_user); fill('snmp_auth_proto',f.snmp_auth_proto); fill('snmp_priv_proto',f.snmp_priv_proto); fill('snmp_port',f.snmp_port);
        mark('community',s.community); mark('snmp_auth_pass',s.snmp_auth_pass); mark('snmp_priv_pass',s.snmp_priv_pass);
        var b2=[]; if(f.snmp_user) b2.push('user '+f.snmp_user); if(f.snmp_auth_proto) b2.push(f.snmp_auth_proto.toUpperCase()+(f.snmp_priv_proto?('/'+f.snmp_priv_proto.toUpperCase()):'')); if(s.community) b2.push('community set'); if(s.snmp_auth_pass) b2.push('auth set'); if(s.snmp_priv_pass) b2.push('priv set');
        summ.snmp='<b>SNMP \''+name+'\':</b> '+(b2.join(', ')||'no fields');
      }}
      render();
    }}).catch(function(){{}});
  }}
  var sref=document.getElementById('secret_ref'), nref=document.getElementById('snmp_ref');
  if(sref){{ sref.addEventListener('change',function(){{load(sref.value.trim(),'ssh');}}); if(sref.value.trim()) load(sref.value.trim(),'ssh'); }}
  if(nref){{ nref.addEventListener('change',function(){{load(nref.value.trim(),'snmp');}}); if(nref.value.trim()) load(nref.value.trim(),'snmp'); }}
}})();
</script>
<label>Notes</label><textarea name=notes style="min-height:60px">{v('notes')}</textarea>
<div style="display:flex;gap:20px;flex-wrap:wrap;margin:6px 0 16px">
  <div id=management_options style="display:flex;gap:20px;flex-wrap:wrap">
    <label style="color:var(--txt)"><input type=checkbox name=legacy value=1 style="width:auto" {chk('legacy')}> legacy algorithms</label>
    <label style="color:var(--txt)"><input type=checkbox name=scrub value=1 style="width:auto" {chk('scrub')}> scrub secrets in archive</label>
  </div>
  <label style="color:var(--txt)"><input type=checkbox name=enabled value=1 style="width:auto" {"checked" if (not editing or d.get('enabled')) else ""}> enabled</label>
</div>
<button>{"Save changes" if editing else "Add device"}</button>
<a class="btn ghost" href="{('/device?name='+_q(name)) if editing else '/'}" style="margin-left:8px">Cancel</a>
</form></div>"""
        del_panel = ""
        if editing:
            del_panel = (f'<div class="panel"><h2>Danger zone</h2>'
                         f'<form method=post action="/device-delete" '
                         f'onsubmit="return confirm(\'Delete {html.escape(name)} and its inventory entry? '
                         f'Archived configs are kept on disk.\')">'
                         f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(name)}">'
                         f'<button class=danger>Delete device</button></form></div>')
        self._send(self._page(title, body + del_panel, sess))

    def _do_device_save(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._dashboard(sess, flash="Not permitted.")
        g = lambda k, d="": (form.get(k) or [d])[0]
        name = g("name").strip()
        if not name:
            return self._dashboard(sess, flash="Device name required.")
        device_types = [t for t in form.get("device_type", [])
                        if t in ("system", "network", "application")]
        if not device_types:
            device_types = ["network"]
        application_only = set(device_types) == {"application"}
        orig = g("orig_name").strip()
        if orig and orig != name:
            try:
                self.manager.rename_device(orig, name)
            except (KeyError, ValueError) as e:
                return self._dashboard(sess, flash=f"Rename failed: {e}")
        try:
            port = int(g("port", "22") or 22)
        except ValueError:
            port = 22
        tags = [t.strip() for t in g("tags").replace(",", " ").split() if t.strip()]
        snmp_version = "" if application_only else g("snmp_version").strip()
        # advanced explicit vault-secret names (optional)
        adv_ssh = g("secret_ref").strip() or None
        adv_snmp = g("snmp_ref").strip() or None
        enable_ref = g("enable_ref").strip() or None
        # inline SSH login fields -> vault
        ssh_fields = {
            "username": g("ssh_username").strip(),
            "password": g("ssh_password"),
            "enable_password": g("enable_password"),
            "key_path": g("key_path").strip(),
            "key_passphrase": g("key_passphrase"),
        }
        ssh_provided = any(ssh_fields.values())
        # inline SNMP fields -> vault
        snmp_fields = {k: g(k).strip() for k in
                       ("snmp_user", "community", "snmp_auth_proto", "snmp_auth_pass",
                        "snmp_priv_proto", "snmp_priv_pass", "snmp_port")}
        snmp_provided = any(snmp_fields.values())

        secret_ref = adv_ssh
        snmp_ref = adv_snmp
        locked_warn = False
        if not application_only and (ssh_provided or snmp_provided):
            if self.manager.vault_ready():
                # one auto secret per device holds both SSH and SNMP fields
                existing_dev = self.manager.inv.get(name) or {}
                sname = (adv_ssh or adv_snmp or existing_dev.get("secret_ref")
                         or existing_dev.get("snmp_ref") or f"{name}-cred")
                try:
                    merged = dict(self.manager.vault.get_secret(sname))
                except KeyError:
                    merged = {}
                for k, val in {**ssh_fields, **snmp_fields}.items():
                    if val:
                        merged[k] = val
                self.manager.vault.set_secret(sname, **merged)
                if ssh_provided:
                    secret_ref = sname
                if snmp_provided:
                    snmp_ref = sname
            else:
                locked_warn = True
        if application_only:
            # Hidden form controls are not a security boundary. A pure
            # Application entry is an endpoint monitor, never an SSH/SNMP
            # managed device, so discard stale or forged management values.
            port = 22                    # neutral internal placeholder; not displayed
            secret_ref = ""
            snmp_ref = ""
            enable_ref = ""
        self.manager.inv.upsert(
            name=name, host=g("host").strip(), port=port,
            platform="generic" if application_only else (g("platform").strip() or "generic"),
            device_type=",".join(device_types),
            secret_ref=secret_ref,
            enable_ref=enable_ref,
            use_key=False if application_only else bool(form.get("use_key")),
            legacy=False if application_only else bool(form.get("legacy")),
            scrub=False if application_only else bool(form.get("scrub")),
            enabled=bool(form.get("enabled")),
            netflow=False if application_only else bool(form.get("netflow")),
            monitor_ports="" if application_only else g("monitor_ports", ""),
            monitor_urls=g("monitor_urls", ""),
            tags=tags, notes=g("notes"),
            snmp_version=snmp_version, snmp_ref=snmp_ref)
        self.manager.db.audit(sess["username"], "device_save", name, g("host"))
        if locked_warn:
            return self._dashboard(sess, flash=f"Device '{name}' saved, but credentials were "
                                   f"NOT stored \u2014 unlock the vault, then edit the device.")
        return self._redirect(f"/device?name={_q(name)}")

    def _do_device_delete(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._dashboard(sess, flash="Not permitted.")
        name = (form.get("name") or [""])[0]
        self.manager.inv.delete(name)
        self.manager.db.audit(sess["username"], "device_delete", name, "")
        return self._dashboard(sess, flash=f"Device '{name}' deleted.")

    def _do_device_run(self, form, sess):
        if not _can(sess["role"], "execute"):
            return self._device_page({"name": [(form.get("name") or [""])[0]]}, sess)
        name = (form.get("name") or [""])[0]
        cmd = (form.get("command") or [""])[0].strip()
        if not self.manager.vault_ready():
            return self._dashboard(sess, flash="Vault locked \u2014 unlock to run commands.")
        try:
            out = self.manager.run(name, cmd)
        except Exception as e:
            out = f"{type(e).__name__}: {e}"
        self.manager.db.audit(sess["username"], "device_run", name, cmd)
        body = (f'<div class="panel"><h2>{html.escape(name)} \u2014 <code>{html.escape(cmd)}</code></h2>'
                f'<pre>{html.escape(out)}</pre>'
                f'<a class="btn ghost" href="/device?name={_q(name)}">Back to device</a></div>')
        self._send(self._page(f"Run \u00b7 {name}", body, sess))

    # ---- credential vault -----------------------------------------------
    def _vault_page(self, q, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._send(self._page("Vault", '<div class="err">Not permitted.</div>', sess), 403)
        m = self.manager
        if not m.vault.exists():
            body = (f'<div class="panel"><h2>Create the credential vault</h2>'
                    f'<p class="muted">The vault encrypts device credentials (PBKDF2 + '
                    f'ChaCha20-Poly1305). Choose a master password \u2014 it is never stored '
                    f'and cannot be recovered.</p>'
                    f'<form method=post action="/vault-create" class="row">{self._csrf_field()}'
                    f'<input type=password name=master placeholder="Master password">'
                    f'<div style="flex:0"><button>Create vault</button></div></form></div>')
            return self._send(self._page("Vault", body, sess))
        if not m.vault_ready():
            body = (f'<div class="panel"><h2>Vault locked</h2>'
                    f'<p class="muted">Unlock to view and manage credentials.</p>'
                    f'<form method=post action="/unlock-vault" class="row">{self._csrf_field()}'
                    f'<input type=password name=master placeholder="Vault master password">'
                    f'<div style="flex:0"><button>Unlock</button></div></form></div>')
            return self._send(self._page("Vault", body, sess))

        edit = (q.get("edit") or [""])[0]
        secrets_map = m.vault.list_secrets()
        rows = ""
        for nm, present in sorted(secrets_map.items()):
            fields = ", ".join(present)
            rows += (f'<tr><td><b>{html.escape(nm)}</b></td>'
                     f'<td class=muted>{html.escape(fields)}</td>'
                     f'<td class=right><a href="/vault?edit={_q(nm)}">edit</a> \u00b7 '
                     f'<form method=post action="/vault-secret-delete" style="display:inline" '
                     f'onsubmit="return confirm(\'Delete secret {html.escape(nm)}?\')">'
                     f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(nm)}">'
                     f'<button class=ghost style="padding:2px 8px">delete</button></form></td></tr>')
        listing = (f'<div class="panel"><h2>Stored secrets</h2>'
                   f'<p class="muted">Values are never displayed \u2014 only which fields are set. '
                   f'Re-enter a field to change it; leave blank to keep it.</p>'
                   f'<table><tr><th>Name</th><th>Fields present</th><th></th></tr>'
                   f'{rows or "<tr><td colspan=3 class=muted>none yet</td></tr>"}</table></div>')

        ev = m.vault.list_secrets().get(edit, []) if edit else None
        title = f"Edit secret \u00b7 {edit}" if edit else "New secret"
        nm_field = (f'<input name=name value="{html.escape(edit)}" readonly>' if edit
                    else '<input name=name placeholder="e.g. core-creds">')
        has = (lambda f: (" \u2713 set" if ev and f in ev else "")) if edit else (lambda f: "")
        form = f"""<div class="panel"><h2>{html.escape(title)}</h2>
<form method=post action="/vault-secret-save">{self._csrf_field()}
<label>Secret name</label>{nm_field}
<h2 style="margin-top:14px">SSH</h2>
<div class="row">
  <div><label>Username</label><input name=username placeholder="admin"></div>
  <div><label>Password{has('password')}</label><input type=password name=password></div>
  <div><label>Enable password{has('enable_password')}</label><input type=password name=enable_password></div>
</div>
<div class="row">
  <div><label>Private key path{has('key_path')}</label><input name=key_path placeholder="/opt/netconfig/keys/id_ed25519"></div>
  <div><label>Key passphrase{has('key_passphrase')}</label><input type=password name=key_passphrase></div>
</div>
<h2 style="margin-top:14px">SNMP (optional)</h2>
<div class="row">
  <div><label>SNMPv3 username{has('snmp_user')}</label><input name=snmp_user placeholder="snmp-admin"></div>
  <div><label>v2c community{has('community')}</label><input type=password name=community></div>
  <div><label>SNMP port</label><input name=snmp_port placeholder="161"></div>
</div>
<div class="row">
  <div><label>v3 auth proto</label><select name=snmp_auth_proto>
    <option value="">\u2014</option><option value=sha>SHA-1</option><option value=sha224>SHA-224</option>
    <option value=sha256>SHA-256</option><option value=sha384>SHA-384</option>
    <option value=sha512>SHA-512</option><option value=md5>MD5</option></select></div>
  <div><label>v3 auth pass{has('snmp_auth_pass')}</label><input type=password name=snmp_auth_pass></div>
  <div><label>v3 priv proto</label><select name=snmp_priv_proto>
    <option value="">\u2014</option><option value=aes>AES-128</option>
    <option value=aes192>AES-192</option><option value=aes256>AES-256</option></select></div>
  <div><label>v3 priv pass{has('snmp_priv_pass')}</label><input type=password name=snmp_priv_pass></div>
</div>
<button>{"Save changes" if edit else "Create secret"}</button>
{'<a class="btn ghost" href="/vault" style="margin-left:8px">Cancel</a>' if edit else ''}
</form></div>"""
        self._send(self._page("Vault", listing + form, sess))

    def _do_vault_create(self, form, sess):
        if not _can(sess["role"], "unlock_vault"):
            return self._vault_page({}, sess)
        pw = (form.get("master") or [""])[0]
        if not pw:
            return self._vault_page({}, sess)
        if not self.manager.vault.exists():
            self.manager.vault.create(pw)
            self.manager.unlock_vault(pw)
            self.manager.db.audit(sess["username"], "vault_create", "", "")
        return self._redirect("/vault")

    def _do_vault_secret_save(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._vault_page({}, sess)
        if not self.manager.vault_ready():
            return self._dashboard(sess, flash="Vault locked.")
        g = lambda k: (form.get(k) or [""])[0].strip()
        name = g("name")
        if not name:
            return self._redirect("/vault")
        # merge with existing so blank fields keep their current value
        try:
            existing = self.manager.vault.get_secret(name)
        except KeyError:
            existing = {}
        fields = dict(existing)
        for k in ("username", "password", "enable_password", "key_path",
                  "key_passphrase", "community", "snmp_user", "snmp_auth_proto",
                  "snmp_auth_pass", "snmp_priv_proto", "snmp_priv_pass", "snmp_port"):
            val = g(k)
            if val:
                fields[k] = val
        self.manager.vault.set_secret(name, **fields)
        self.manager.db.audit(sess["username"], "vault_secret_save", name,
                              ", ".join(sorted(fields.keys())))
        return self._redirect("/vault")

    def _do_vault_secret_delete(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._vault_page({}, sess)
        if not self.manager.vault_ready():
            return self._dashboard(sess, flash="Vault locked.")
        name = (form.get("name") or [""])[0]
        self.manager.vault.delete_secret(name)
        self.manager.db.audit(sess["username"], "vault_secret_delete", name, "")
        return self._redirect("/vault")

    # ---- settings --------------------------------------------------------
    def _settings_page_v2(self, sess, q=None, flash=None):
        if not _can(sess["role"], "settings"):
            return self._send(self._page("Settings", '<div class="err">Admin only.</div>', sess), 403)
        q = q or {}
        section = (q.get("section") or ["general"])[0]
        sections = (("general", "General & SSH"), ("snmp", "SNMP polling"),
                    ("netflow", "NetFlow"), ("monitoring", "Monitoring"),
                    ("email", "Email & OAuth"), ("db", "Database"))
        if section not in dict(sections):
            section = "general"
        s = self.manager.settings

        def field(key, label, hint=""):
            return (f'<div><label>{html.escape(label)}</label>'
                    f'<input name="{key}" value="{html.escape(str(s.get(key,"")))}">'
                    f'{f"<div class=muted>{hint}</div>" if hint else ""}</div>')

        menu = "".join(
            f'<a href="/settings?section={key}" class="{"active" if key == section else ""}">'
            f'{html.escape(label)}</a>' for key, label in sections)
        form = (f'<form method=post action="/settings-save">{self._csrf_field()}'
                f'<input type=hidden name=section value="{html.escape(section)}">')
        hostkey = "".join(
            f'<option value="{v}"{" selected" if s.get("host_key_policy")==v else ""}>{v}</option>'
            for v in ("accept-new", "yes", "no"))

        if section == "general":
            content = f"""<div class="panel"><h2>General &amp; SSH</h2>
<p class="muted">Console, archive and SSH execution defaults. Bind and port changes apply after restart.</p>
{form}<div class="row">{field("web_bind","Console bind address","127.0.0.1 recommended; front with WAF for TLS")}
{field("web_port","Console port")}</div>
<div class="row">{field("keep_versions","Config copies to keep (manual collects)")}
{field("backup_keep","Config copies to keep (weekly backup)")}</div>
<div class="row">{field("connect_timeout","SSH connect timeout (s)")}
{field("command_timeout","SSH command timeout (s)")}{field("bulk_workers","Bulk concurrent workers")}</div>
<div class="row"><div><label>Host key policy</label><select name=host_key_policy>{hostkey}</select>
<div class=muted>accept-new trusts new hosts once, then pins</div></div>
<div><label>Session recording</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=record_sessions value=1 style="width:auto" {"checked" if s.get("record_sessions") else ""}> record transcripts</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=scrub_sessions value=1 style="width:auto" {"checked" if s.get("scrub_sessions") else ""}> scrub secrets in transcripts</label></div></div>
<button>Save general settings</button></form></div>"""
        elif section == "snmp":
            content = f"""<div class="panel"><h2>SNMP polling</h2>
<p class="muted">Defaults for device polling and live interface history.</p>
{form}<div class="row">{field("snmp_timeout","SNMP timeout (s)")}{field("snmp_port","Default SNMP port")}</div>
<div class="row">{field("snmp_poll_interval","Background poll interval (s)","0 = off; restart the console after changing this value")}
{field("snmp_history_seconds","Live-graph history window (s)")}</div>
<button>Save SNMP settings</button></form></div>"""
        elif section == "netflow":
            content = f"""<div class="panel"><h2>NetFlow</h2>
<p class="muted">UDP flow collector settings. Changes apply after console restart.</p>
{form}<div class="row"><div><label>NetFlow collector</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=netflow_enabled value=1 style="width:auto" {"checked" if s.get("netflow_enabled") else ""}> receive NetFlow</label>
<div class=muted>UDP listener for flow exports from network devices</div></div>
{field("netflow_port","NetFlow UDP port","default 2055")}{field("netflow_max_flows","Recent flows kept per device")}</div>
<button>Save NetFlow settings</button></form></div>"""
        elif section == "monitoring":
            content = f"""<div class="panel"><h2>Monitoring &amp; alerts</h2>
<p class="muted">Background port, HTTP and TLS monitoring schedule and retention.</p>
{form}<div class="row">{field("monitor_poll_interval","Monitor poll interval (s)","0 = off; e.g. 60 enables background polling")}
{field("monitor_history_days","Monitor history retention (days)")}</div>
<h3>Event-driven collection &amp; digest</h3>
<div class="row"><div><label>Syslog change receiver</label><label style="color:var(--txt);font-weight:400"><input type=checkbox name=syslog_enabled value=1 style="width:auto" {"checked" if s.get("syslog_enabled") else ""}> enabled (restart required)</label></div>
{field("syslog_port","Syslog UDP port","default 5514; forward udp/514 if required")}{field("syslog_queue_size","Syslog queue size")}{field("syslog_debounce_seconds","Change debounce (s)")}</div>
<div class="row">{field("digest_interval","Compliance/drift digest interval (s)","0 = off; 86400 = daily; uses configured email")}</div>
<button>Save monitoring settings</button></form></div>"""
        elif section == "monitoring":
            s["syslog_enabled"] = bool(form.get("syslog_enabled"))
        elif section == "email":
            from . import mailer as _mailer
            from . import oauth as _oauth
            smtp_pw_set = o365_secret_set = False
            if self.manager.vault_ready():
                try:
                    smtp_pw_set = bool(self.manager.vault.get_secret(_mailer.SMTP_SECRET).get("password"))
                except Exception:
                    pass
                try:
                    o365_secret_set = bool(self.manager.vault.get_secret(_oauth.O365_SECRET).get("client_secret"))
                except Exception:
                    pass
            content = f"""<div class="panel"><h2>Email &amp; OAuth</h2>
<p class="muted">SMTP delivery and Microsoft 365 OAuth authentication for alert email.</p>
{form}<h3>SMTP</h3><div class="row"><div><label>Send alert email</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=smtp_enabled value=1 style="width:auto" {"checked" if s.get("smtp_enabled") else ""}> enabled</label></div>
{field("smtp_host","SMTP host")}{field("smtp_port","SMTP port","587 STARTTLS / 25 relay")}
<div><label>STARTTLS</label><label style="color:var(--txt);font-weight:400"><input type=checkbox name=smtp_starttls value=1 style="width:auto" {"checked" if s.get("smtp_starttls") else ""}> use STARTTLS</label></div></div>
<div class="row">{field("smtp_from","From address")}{field("smtp_to","To (comma-separated)")}
{field("smtp_user","SMTP username (optional)")}<div><label>SMTP password{" ✓ set" if smtp_pw_set else ""}</label>
<input type=password name=smtp_password placeholder="kept in vault; blank keeps current"></div></div>
<h3>Microsoft 365 OAuth (Entra ID)</h3><div class="row"><div><label>Use O365 OAuth for email</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=o365_enabled value=1 style="width:auto" {"checked" if s.get("o365_enabled") else ""}> enabled</label></div>
{field("o365_tenant","Tenant ID","GUID or domain")}{field("o365_client_id","Client (application) ID")}
<div><label>Client secret{" ✓ set" if o365_secret_set else ""}</label><input type=password name=o365_client_secret placeholder="kept in vault; blank keeps current"></div></div>
<div class="row">{field("o365_authority","Authority")}{field("o365_scope","Scope","e.g. https://outlook.office365.com/.default")}</div>
<button>Save email settings</button>
<button formaction="/smtp-test" formmethod="post" class=ghost style="margin-left:8px">Send test email</button>
<button formaction="/oauth-test" formmethod="post" class=ghost style="margin-left:8px">Test O365 sign-in</button></form></div>"""

        elif section == "db":
            from . import ifhistory as _ifh
            pg_pw_set = False
            if self.manager.vault_ready():
                try:
                    pg_pw_set = bool(self.manager.vault.get_secret(
                        _ifh.VAULT_SECRET).get("password"))
                except Exception:
                    pass
            sslmodes = "".join(
                f'<option value="{v}"{" selected" if s.get("pg_sslmode")==v else ""}>{v}</option>'
                for v in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"))
            content = f"""<div class="panel"><h2>Database</h2>
<p class="muted">Optional PostgreSQL store for long-term interface throughput
history (the SNMP page's 24h graph). When off, live graphs still work from the
built-in SQLite store. Saving a new configuration validates the connection and
creates the <code>{_ifh._TABLE}</code> table if it does not yet exist.</p>
{form}<div class="row"><div><label>Interface history store</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=if_history_enabled value=1 style="width:auto" {"checked" if s.get("if_history_enabled") else ""}> enabled (requires the psycopg driver on the server)</label></div></div>
<div class="row">{field("pg_host","Host","hostname or IP of the PostgreSQL server")}
{field("pg_port","Port","default 5432")}{field("pg_dbname","Database name")}</div>
<div class="row">{field("pg_user","Username")}
<div><label>Password{" ✓ set" if pg_pw_set else ""}</label>
<input type=password name=pg_password placeholder="kept in vault; blank keeps current"></div>
<div><label>SSL mode</label><select name=pg_sslmode>{sslmodes}</select>
<div class=muted>require or stronger for TLS to the DB</div></div></div>
<div class="row">{field("if_history_hours","History retention (hours)","also the default graph window; e.g. 24")}
{field("if_history_bucket_seconds","Downsample bucket (s)","points are averaged into buckets this wide")}</div>
<button>Save database settings</button>
<button formaction="/db-test" formmethod="post" class=ghost style="margin-left:8px">Test connection &amp; create table</button></form></div>"""

        body = (f'<h1>Settings</h1><p class="muted" style="margin-bottom:14px">Stored in '
                f'<code>settings.json</code> in the data directory.</p><div class="settings-shell">'
                f'<aside class="settings-menu" aria-label="Settings sections">{menu}</aside>'
                f'<section class="settings-content">{content}</section></div>')
        self._send(self._page("Settings", body, sess, flash=flash))

    def _settings_page(self, sess, flash=None):
        if not _can(sess["role"], "settings"):
            return self._send(self._page("Settings", '<div class="err">Admin only.</div>', sess), 403)
        s = self.manager.settings
        from . import mailer as _mailer
        _smtp_pw_set = False
        _o365_secret_set = False
        try:
            if self.manager.vault_ready():
                _smtp_pw_set = bool(self.manager.vault.get_secret(_mailer.SMTP_SECRET).get("password"))
        except Exception:
            _smtp_pw_set = False
        try:
            from . import oauth as _oauth
            if self.manager.vault_ready():
                _o365_secret_set = bool(self.manager.vault.get_secret(_oauth.O365_SECRET).get("client_secret"))
        except Exception:
            _o365_secret_set = False
        def field(key, label, hint=""):
            return (f'<div><label>{html.escape(label)}</label>'
                    f'<input name="{key}" value="{html.escape(str(s.get(key,"")))}">'
                    f'{f"<div class=muted>{hint}</div>" if hint else ""}</div>')
        hostkey = "".join(
            f'<option value="{v}"{" selected" if s.get("host_key_policy")==v else ""}>{v}</option>'
            for v in ("accept-new", "yes", "no"))
        body = f"""<div class="panel"><h2>Settings</h2>
<p class="muted">Stored in <code>settings.json</code> in the data directory. Web
bind/port changes take effect on next console restart.</p>
<form method=post action="/settings-save">{self._csrf_field()}
<div class="row">{field("web_bind","Console bind address","127.0.0.1 recommended; front with WAF for TLS")}
{field("web_port","Console port")}</div>
<div class="row">{field("keep_versions","Config copies to keep (manual collects)")}
{field("backup_keep","Config copies to keep (weekly backup)","the weekly job keeps this many per device")}
{field("connect_timeout","SSH connect timeout (s)")}
{field("command_timeout","SSH command timeout (s)")}</div>
<div class="row">{field("bulk_workers","Bulk concurrent workers")}
{field("snmp_timeout","SNMP timeout (s)")}
{field("snmp_port","Default SNMP port")}</div>
<div class="row">{field("snmp_poll_interval","SNMP background poll interval (s)","0 = off; e.g. 15 enables live graphs")}
{field("snmp_history_seconds","Live-graph history window (s)")}</div>
<div class="row"><div><label>NetFlow collector</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=netflow_enabled value=1 style="width:auto" {"checked" if s.get("netflow_enabled") else ""}> receive NetFlow (restart to apply)</label>
<div class=muted>UDP listener for flow exports from network devices</div></div>
{field("netflow_port","NetFlow UDP port","default 2055; change requires restart")}
{field("netflow_max_flows","Recent flows kept per device")}</div>
<h2 style="margin-top:18px">Monitoring &amp; alerts</h2>
<div class="row">{field("monitor_poll_interval","Monitor poll interval (s)","0 = off; e.g. 60 polls port/http/tls in the background")}
{field("monitor_history_days","Monitor history retention (days)")}</div>
<h2 style="margin-top:18px">SMTP (alert email)</h2>
<div class="row"><div><label>Send alert email</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=smtp_enabled value=1 style="width:auto" {"checked" if s.get("smtp_enabled") else ""}> enabled</label></div>
{field("smtp_host","SMTP host")}
{field("smtp_port","SMTP port","587 STARTTLS / 25 relay")}
<div><label>STARTTLS</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=smtp_starttls value=1 style="width:auto" {"checked" if s.get("smtp_starttls") else ""}> use STARTTLS</label></div></div>
<div class="row">{field("smtp_from","From address")}
{field("smtp_to","To (comma-separated)")}
{field("smtp_user","SMTP username (optional)")}
<div><label>SMTP password{" \u2713 set" if _smtp_pw_set else ""}</label><input type=password name=smtp_password placeholder="kept in vault; blank keeps current"></div></div>
<h2 style="margin-top:18px">Microsoft 365 OAuth (Entra ID)</h2>
<p class="muted">Modern auth for Office 365 email (replaces the SMTP password). Register an
app in Entra ID, grant it the mail permission, and enter its details below. When enabled,
alert email authenticates to <code>smtp.office365.com</code> with an OAuth token (XOAUTH2).
The client secret is stored in the vault.</p>
<div class="row"><div><label>Use O365 OAuth for email</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=o365_enabled value=1 style="width:auto" {"checked" if s.get("o365_enabled") else ""}> enabled</label></div>
{field("o365_tenant","Tenant ID","GUID or domain")}
{field("o365_client_id","Client (application) ID")}
<div><label>Client secret{" \u2713 set" if _o365_secret_set else ""}</label><input type=password name=o365_client_secret placeholder="kept in vault; blank keeps current"></div></div>
<div class="row">{field("o365_authority","Authority")}
{field("o365_scope","Scope","e.g. https://outlook.office365.com/.default")}
<div style="align-self:end"><button formaction="/oauth-test" formmethod="post" class=ghost style="width:100%">Test O365 sign-in</button></div></div>
<div class="row"><div><label>Host key policy</label>
<select name=host_key_policy>{hostkey}</select>
<div class=muted>accept-new trusts new hosts once, then pins</div></div>
<div><label>Session recording</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=record_sessions value=1 style="width:auto" {"checked" if s.get("record_sessions") else ""}> record transcripts</label>
<label style="color:var(--txt);font-weight:400"><input type=checkbox name=scrub_sessions value=1 style="width:auto" {"checked" if s.get("scrub_sessions") else ""}> scrub secrets in transcripts</label>
</div></div>
<button>Save settings</button>
<button formaction="/smtp-test" formmethod="post" class=ghost style="margin-left:8px">Send test email</button></form></div>"""
        self._send(self._page("Settings", body, sess, flash=flash))

    def _do_settings_save(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._settings_page(sess, flash="Admin only.")
        s = self.manager.settings
        g = lambda k: (form.get(k) or [""])[0].strip()
        for k in ("web_bind", "host_key_policy"):
            if g(k):
                s[k] = g(k)
        for k in ("web_port", "keep_versions", "connect_timeout", "command_timeout",
                  "bulk_workers", "snmp_port", "snmp_poll_interval", "snmp_history_seconds",
                  "backup_keep", "netflow_port", "netflow_max_flows",
                  "monitor_poll_interval", "monitor_history_days", "smtp_port"):
            if g(k):
                try:
                    s[k] = int(g(k))
                except ValueError:
                    pass
        for k in ("smtp_host", "smtp_user", "smtp_from", "smtp_to",
                  "o365_tenant", "o365_client_id", "o365_authority", "o365_scope"):
            s[k] = g(k)
        s["netflow_enabled"] = bool(form.get("netflow_enabled"))
        s["smtp_enabled"] = bool(form.get("smtp_enabled"))
        s["smtp_starttls"] = bool(form.get("smtp_starttls"))
        s["o365_enabled"] = bool(form.get("o365_enabled"))
        pw = (form.get("smtp_password") or [""])[0]
        if pw:
            from . import mailer as _mailer
            try:
                if self.manager.vault_ready():
                    self.manager.vault.set_secret(_mailer.SMTP_SECRET, password=pw)
            except Exception:
                pass
        osec = (form.get("o365_client_secret") or [""])[0]
        if osec:
            from . import oauth as _oauth
            try:
                if self.manager.vault_ready():
                    self.manager.vault.set_secret(_oauth.O365_SECRET, client_secret=osec)
            except Exception:
                pass
        if g("snmp_timeout"):
            try:
                s["snmp_timeout"] = float(g("snmp_timeout"))
            except ValueError:
                pass
        s["record_sessions"] = bool(form.get("record_sessions"))
        s["scrub_sessions"] = bool(form.get("scrub_sessions"))
        _config.save_settings(self.manager.paths, s)
        self.manager.db.audit(sess["username"], "settings_save", "", "")
        return self._settings_page(sess, flash="Settings saved.")

    def _do_settings_save_v2(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._settings_page_v2(sess, flash="Admin only.")
        s = self.manager.settings
        g = lambda k: (form.get(k) or [""])[0].strip()
        section = g("section") or "general"
        valid_sections = {"general", "snmp", "netflow", "monitoring", "email", "db"}
        if section not in valid_sections:
            section = "general"

        string_keys = {
            "general": ("web_bind", "host_key_policy"),
            "email": ("smtp_host", "smtp_user", "smtp_from", "smtp_to",
                      "o365_tenant", "o365_client_id", "o365_authority", "o365_scope"),
            "db": ("pg_host", "pg_dbname", "pg_user", "pg_sslmode"),
        }.get(section, ())
        for key in string_keys:
            value = g(key)
            if value or section in ("email", "db"):
                s[key] = value

        int_keys = {
            "general": ("web_port", "keep_versions", "backup_keep", "connect_timeout",
                        "command_timeout", "bulk_workers"),
            "snmp": ("snmp_port", "snmp_poll_interval", "snmp_history_seconds"),
            "netflow": ("netflow_port", "netflow_max_flows"),
            "monitoring": ("monitor_poll_interval", "monitor_history_days", "syslog_port", "syslog_queue_size", "syslog_debounce_seconds", "digest_interval"),
            "email": ("smtp_port",),
            "db": ("pg_port", "if_history_hours", "if_history_bucket_seconds"),
        }.get(section, ())
        for key in int_keys:
            if g(key):
                try:
                    s[key] = int(g(key))
                except ValueError:
                    pass

        if section == "snmp" and g("snmp_timeout"):
            try:
                s["snmp_timeout"] = float(g("snmp_timeout"))
            except ValueError:
                pass
        elif section == "general":
            s["record_sessions"] = bool(form.get("record_sessions"))
            s["scrub_sessions"] = bool(form.get("scrub_sessions"))
        elif section == "netflow":
            s["netflow_enabled"] = bool(form.get("netflow_enabled"))
        elif section == "email":
            s["smtp_enabled"] = bool(form.get("smtp_enabled"))
            s["smtp_starttls"] = bool(form.get("smtp_starttls"))
            s["o365_enabled"] = bool(form.get("o365_enabled"))
            pw = (form.get("smtp_password") or [""])[0]
            if pw:
                from . import mailer as _mailer
                try:
                    if self.manager.vault_ready():
                        self.manager.vault.set_secret(_mailer.SMTP_SECRET, password=pw)
                except Exception:
                    pass
            secret = (form.get("o365_client_secret") or [""])[0]
            if secret:
                from . import oauth as _oauth
                try:
                    if self.manager.vault_ready():
                        self.manager.vault.set_secret(_oauth.O365_SECRET, client_secret=secret)
                except Exception:
                    pass
        elif section == "db":
            from . import ifhistory as _ifh
            s["if_history_enabled"] = bool(form.get("if_history_enabled"))
            pw = (form.get("pg_password") or [""])[0]
            if pw:
                try:
                    if self.manager.vault_ready():
                        self.manager.vault.set_secret(_ifh.VAULT_SECRET, password=pw)
                except Exception:
                    pass

        _config.save_settings(self.manager.paths, s)
        self.manager.db.audit(sess["username"], "settings_save", section, "")
        labels = {"general": "General & SSH", "snmp": "SNMP polling",
                  "netflow": "NetFlow", "monitoring": "Monitoring",
                  "email": "Email & OAuth", "db": "Database"}
        flash = f"{labels[section]} settings saved."
        # On a new/changed DB config, validate the connection and create the
        # history table if it is missing, reporting the outcome to the admin.
        if section == "db" and s.get("if_history_enabled"):
            self.manager._ifhist_key = None  # force rebuild with new settings
            backend = self.manager._history_backend()
            if backend is None:
                flash += " History is enabled but no host/database is set."
            else:
                res = backend.ensure_ready()
                if res["ok"]:
                    flash += (" Connected — history table created."
                              if res["created"]
                              else " Connected — history table already present.")
                else:
                    flash += f" Connection failed: {res['error']}"
        return self._settings_page_v2(sess, q={"section": [section]}, flash=flash)

    # ---- SNMP fleet + interface stats -----------------------------------
    def _interface_table(self, device):
        ifs = self.manager.inv.get_interfaces(device)
        if not ifs:
            return ""
        rows = ""
        for i in ifs:
            errs = (i["in_errors"] or 0) + (i["out_errors"] or 0)
            err_cell = (f'<span class="badge b-bad">{errs}</span>' if errs
                        else '<span class=muted>0</span>')
            rows += (f'<tr><td class=muted>{html.escape(str(i["ifindex"]))}</td>'
                     f'<td><b>{html.escape(i["descr"])}</b></td>'
                     f'<td>{_oper_badge(i["oper"])}'
                     f'{"" if i["admin"]=="up" else " <span class=muted>(admin "+html.escape(i["admin"])+")</span>"}</td>'
                     f'<td class=muted>{_fmt_speed(i["speed"])}</td>'
                     f'<td>{_fmt_bps(i["in_bps"])}</td>'
                     f'<td>{_fmt_bps(i["out_bps"])}</td>'
                     f'<td class=muted>{i["in_octets"]:,} / {i["out_octets"]:,}</td>'
                     f'<td>{err_cell}</td></tr>')
        return (f'<table><tr><th>#</th><th>Interface</th><th>Status</th><th>Speed</th>'
                f'<th>In rate</th><th>Out rate</th><th>In/Out octets</th><th>Errors</th></tr>'
                f'{rows}</table>'
                f'<p class="muted" style="margin-top:6px">Rates are computed between the last '
                f'two polls. If the background poller is on (Settings \u2192 SNMP poll interval) '
                f'this table refreshes on every poll \u2014 reload the page to see the latest '
                f'numbers; the live graph above updates on its own. Counters are 32-bit ifTable values.</p>')

    def _snmp_walk_panel(self, device, q):
        root = (q.get("walk") or ["1.3.6.1.2.1.1"])[0].strip() or "1.3.6.1.2.1.1"
        # named shortcuts
        shortcuts = [("System", "1.3.6.1.2.1.1"), ("Interfaces", "1.3.6.1.2.1.2"),
                     ("IF-MIB ext", "1.3.6.1.2.1.31"), ("IP", "1.3.6.1.2.1.4"),
                     ("Full mib-2", "1.3.6.1.2.1"), ("Enterprises", "1.3.6.1.4.1")]
        chips = " ".join(
            f'<a class="btn ghost" style="padding:2px 10px" '
            f'href="/snmp?device={_q(device)}&walk={_q(o)}">{html.escape(n)}</a>'
            for n, o in shortcuts)
        rows = ""
        note = ""
        try:
            data = self.manager.snmp_walk(device, root=root, max_vars=400)
            named = sum(1 for r in data if not re.match(r"^[\d.]+$", r["name"]))
            for r in data:
                is_named = not re.match(r"^[\d.]+$", r["name"])
                nm = (f'<b>{html.escape(r["name"])}</b>' if is_named
                      else f'<span class="muted">{html.escape(r["name"])}</span>')
                rows += (f'<tr><td>{nm}</td><td class="muted"><code>{html.escape(r["oid"])}</code></td>'
                         f'<td>{html.escape(r.get("mib_source", "") or "Unmapped")}</td>'
                         f'<td>{html.escape(r["value"][:200])}</td></tr>')
            note = (f'{len(data)} object(s) walked \u00b7 <b>{named}</b> resolved to names by the '
                    f'uploaded MIBs (raw numeric = no MIB defines that OID yet).')
            if not data:
                note = ('No objects returned. The agent may not expose this subtree, or SNMP '
                        'credentials/reachability need checking.')
        except Exception as e:
            note = f'<span class="err">Walk failed: {html.escape(str(e))}</span>'
        table = (f'<table><tr><th>Resolved name</th><th>Raw OID</th><th>Source MIB</th><th>Value</th></tr>'
                 f'{rows}</table>' if rows else "")
        return (f'<div class="panel"><h2>SNMP data \u2014 walked &amp; named</h2>'
                f'<p class="muted">Everything the agent returns under a subtree, with each OID '
                f'resolved to a name by your uploaded MIBs. This is where MIBs help: raw numbers '
                f'become readable names.</p>'
                f'<div style="margin:6px 0">{chips}</div>'
                f'<form method=get action="/snmp" style="display:flex;gap:8px;max-width:640px;margin:8px 0">'
                f'<input type=hidden name=device value="{html.escape(device)}">'
                f'<input name=walk value="{html.escape(root)}" placeholder="root OID or name, e.g. 1.3.6.1.2.1.1">'
                f'<button class=ghost>Walk</button></form>'
                f'<p class="muted">{note}</p>{table}</div>')

    def _snmp_page(self, q, sess):
        m = self.manager
        device = (q.get("device") or [""])[0]
        if device:
            dev = m.inv.get(device)
            if not dev:
                return self._send(self._page("SNMP", '<div class="err">Unknown device.</div>', sess), 404)
            fx = m.inv.get_facts(device) or {}
            poll_btn = ""
            if _can(sess["role"], "collect") and dev.get("snmp_version"):
                poll_btn = (f'<form method=post action="/snmp-poll" style="margin-bottom:14px">'
                            f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(device)}">'
                            f'<input type=hidden name=back value="snmp">'
                            f'<button>Poll now</button></form>')
            facts_tbl = ""
            if fx:
                raw_oid = (fx.get("sysobjectid") or "").strip()
                oid_map = m.mibindex.resolve_detail(raw_oid) if raw_oid else None
                model = ""
                if oid_map:
                    model = (f'<b>{html.escape(oid_map["name"])}</b><br>'
                             f'<code>{html.escape(raw_oid)}</code>'
                             + (f' <span class="muted">MIB: {html.escape(oid_map["source"])}</span>'
                                if oid_map["source"] else ' <span class="muted">Unmapped</span>'))
                facts_tbl = (f'<table>'
                             f'<tr><th>Reachable</th><td>{"yes" if fx.get("reachable") else "no"}</td>'
                             f'<th>sysName</th><td>{html.escape(fx.get("sysname",""))}</td></tr>'
                             f'<tr><th>Uptime</th><td>{html.escape(fx.get("uptime",""))}</td>'
                             f'<th>Polled</th><td>{_fmt_ts(fx.get("last_polled"))}</td></tr>'
                             f'<tr><th>Descr</th><td colspan=3>{html.escape(fx.get("sysdescr",""))}</td></tr>'
                             f'<tr><th>sysObjectID</th><td colspan=3>{model or "—"}</td></tr>'
                             f'<tr><th>Contact</th><td>{html.escape(fx.get("contact","")) or "—"}</td>'
                             f'<th>Location</th><td>{html.escape(fx.get("location","")) or "—"}</td></tr>'
                             f'<tr><th>Last error</th><td colspan=3>{html.escape(fx.get("error", "")) or "—"}</td></tr>'
                             f'</table>')
            iftbl = self._interface_table(device) or '<p class="muted">No interface data yet \u2014 poll the device.</p>'
            graph = self._live_graph(device) if dev.get("snmp_version") else ""
            walk_panel = self._snmp_walk_panel(device, q) if dev.get("snmp_version") else ""
            vendor_panel = self._vendor_mib_section(device) if dev.get("snmp_version") else ""
            inner = (f'<div class="panel"><h2>{html.escape(device)} \u00b7 SNMP '
                     f'<a class="btn ghost" href="/snmp" style="float:right;padding:4px 12px">All devices</a></h2>'
                     f'{poll_btn}{facts_tbl}</div>'
                     f'{graph}'
                     f'{walk_panel}'
                     f'{vendor_panel}'
                     f'<div class="panel"><h2>Interfaces</h2>{iftbl}</div>')
            if "network" in _dtypes(dev):
                inner += self._arp_section(dev) + self._mac_port_section(dev)
            return self._send(self._page(f"SNMP \u00b7 {device}", inner, sess))

        # fleet view
        facts = m.inv.all_facts()
        counts = m.inv.interface_counts()
        snmp_devs = [d for d in m.inv.all(only_enabled=False) if d.get("snmp_version")]
        rows = ""
        for d in snmp_devs:
            fx = facts.get(d["name"], {})
            reach = ('<span class="badge b-ok">up</span>' if fx.get("reachable")
                     else ('<span class="badge b-bad">unreachable</span>' if fx
                           else '<span class="badge b-dim">not polled</span>'))
            up, tot = counts.get(d["name"], (0, 0))
            ifcell = (f'{up}/{tot} up' if tot else '<span class=muted>\u2014</span>')
            model = (fx.get("sysdescr", "") or "")[:46]
            poll_btn = ""
            if _can(sess["role"], "collect"):
                poll_btn = (f'<form method=post action="/snmp-poll" style="display:inline">'
                            f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(d["name"])}">'
                            f'<input type=hidden name=back value="snmp">'
                            f'<button style="padding:3px 10px">Poll</button></form>')
            rows += (f'<tr><td><a href="/snmp?device={_q(d["name"])}">{html.escape(d["name"])}</a></td>'
                     f'<td class=muted>{html.escape(d.get("snmp_version",""))}</td>'
                     f'<td>{reach}</td>'
                     f'<td>{html.escape(fx.get("sysname",""))}</td>'
                     f'<td class=muted>{html.escape(model)}</td>'
                     f'<td class=muted>{html.escape(fx.get("uptime",""))}</td>'
                     f'<td>{ifcell}</td>'
                     f'<td class=muted>{_fmt_ts(fx.get("last_polled"))}</td>'
                     f'<td class=right>{poll_btn}</td></tr>')
        poll_all = ""
        if _can(sess["role"], "collect") and snmp_devs:
            poll_all = (f'<form method=post action="/snmp-poll" style="margin-left:auto">'
                        f'{self._csrf_field()}<input type=hidden name=all value=1>'
                        f'<button {"disabled" if not m.vault_ready() else ""}>Poll all</button></form>')
        note = ""
        if not m.vault_ready():
            note = '<p class="muted">Vault locked \u2014 unlock (on Devices) to poll SNMP.</p>'
        body = (f'<div class="panel">'
                f'<div style="display:flex;align-items:center;margin-bottom:12px">'
                f'<h2 style="border:none;margin:0">SNMP \u00b7 {len(snmp_devs)} device(s)</h2>{poll_all}</div>'
                f'{note}'
                f'<table><tr><th>Device</th><th>Ver</th><th>Reachable</th><th>sysName</th>'
                f'<th>Model</th><th>Uptime</th><th>Interfaces</th><th>Last poll</th><th></th></tr>'
                f'{rows or "<tr><td colspan=9 class=muted>No SNMP-enabled devices. Set an SNMP version on a device to enable.</td></tr>"}'
                f'</table></div>')
        self._send(self._page("SNMP", body, sess))

    def _secret_info(self, q, sess):
        m = self.manager
        out = {"name": (q.get("name") or [""])[0], "exists": False,
               "ready": m.vault_ready(), "fields": {}, "set": {}}
        if not _can(sess["role"], "manage_devices"):
            return self._send(json.dumps({"error": "forbidden"}), 403, ctype="application/json")
        name = out["name"]
        if name and m.vault_ready():
            try:
                sec = m.vault.get_secret(name)
                out["exists"] = True
                for k in ("username", "snmp_user", "snmp_auth_proto", "snmp_priv_proto", "snmp_port"):
                    if sec.get(k):
                        out["fields"][k] = sec[k]
                for k in ("password", "enable_password", "key_path", "community",
                          "snmp_auth_pass", "snmp_priv_pass"):
                    out["set"][k] = bool(sec.get(k))
            except KeyError:
                pass
        self._send(json.dumps(out), ctype="application/json")

    def _snmp_series(self, q, sess):
        device = (q.get("device") or [""])[0]
        m = self.manager
        window = float(m.settings.get("snmp_history_seconds", 1800))
        series = m.inv.get_samples(device, since=time.time() - window)
        def _idx(k):
            return int(k) if str(k).isdigit() else 0
        interfaces = [{"ifindex": k, "descr": v["descr"], "points": v["points"][-400:]}
                      for k, v in sorted(series.items(), key=lambda kv: _idx(kv[0]))]
        payload = {"device": device, "now": time.time(),
                   "interval": m.settings.get("snmp_poll_interval", 0),
                   "interfaces": interfaces}
        self._send(json.dumps(payload), ctype="application/json")

    def _snmp_history(self, q, sess):
        """24h (configurable) interface throughput from the optional history
        backend. Same JSON shape as _snmp_series so the graph JS is reused;
        `enabled: false` tells the client no backend is configured."""
        device = (q.get("device") or [""])[0]
        m = self.manager
        backend = m._history_backend()
        if backend is None:
            return self._send(json.dumps(
                {"device": device, "enabled": False, "interfaces": []}),
                ctype="application/json")
        hours = float(m.settings.get("if_history_hours", 24) or 24)
        bucket = int(m.settings.get("if_history_bucket_seconds", 60) or 60)
        try:
            series = backend.read(device, hours=hours, bucket_seconds=bucket)
        except Exception as e:
            return self._send(json.dumps(
                {"device": device, "enabled": True, "error": str(e),
                 "interfaces": []}), ctype="application/json")
        # descriptions come from the live SQLite stats so labels stay current
        descrs = {str(i["ifindex"]): i.get("descr", "")
                  for i in m.inv.get_interfaces(device)}

        def _idx(k):
            return int(k) if str(k).isdigit() else 0
        interfaces = [{"ifindex": k, "descr": descrs.get(str(k), k),
                       "points": v["points"][-2000:]}
                      for k, v in sorted(series.items(), key=lambda kv: _idx(kv[0]))]
        payload = {"device": device, "enabled": True, "now": time.time(),
                   "hours": hours, "interfaces": interfaces}
        self._send(json.dumps(payload), ctype="application/json")

    def _live_graph(self, device):
        iv = int(self.manager.settings.get("snmp_poll_interval", 0) or 0)
        refresh = iv if iv > 0 else 5
        poller_note = (f"Updates every {iv}s from the background poller."
                       if iv > 0 else
                       "The background poller is off (Settings \u2192 SNMP poll interval); "
                       "this still refreshes as you poll manually.")
        window = float(self.manager.settings.get("snmp_history_seconds", 1800))
        series = self.manager.inv.get_samples(device, since=time.time() - window)
        def _idx(k):
            return int(k) if str(k).isdigit() else 0
        seed = [{"ifindex": k, "descr": v["descr"], "points": v["points"][-400:]}
                for k, v in sorted(series.items(), key=lambda kv: _idx(kv[0]))]
        seed_json = json.dumps(seed).replace("<", "\\u003c")
        js = _GRAPH_JS.replace("__DEV__", json.dumps(device)).replace("__IV__", str(refresh))
        hist_hours = int(self.manager.settings.get("if_history_hours", 24) or 24)
        mode_ctrl = ""
        if self.manager._history_backend() is not None:
            mode_ctrl = (
                f'<select id=ifmode style="margin:0;flex:0 0 auto">'
                f'<option value="live">Live throughput</option>'
                f'<option value="history">{hist_hours}h history</option></select>')
        return (f'<div class="panel"><h2>Interface throughput '
                f'<span id=livestatus class=muted style="float:right;font-weight:400"></span></h2>'
                f'<div id=charts></div>'
                f'<div id=addrow style="display:flex;gap:8px;align-items:center;margin-top:6px;flex-wrap:wrap">'
                f'{mode_ctrl}'
                f'<select id=ifadd style="margin:0;max-width:300px;flex:0 0 auto"></select>'
                f'<button type=button class=ghost id=addbtn style="padding:6px 12px">+ Add interface</button>'
                f'<span class="muted">Add interfaces to watch \u2014 they tile two per row '
                f'(2\u00d71, then 2\u00d72\u2026); resets when you leave the page.</span></div>'
                f'<p class="muted" style="margin-top:8px">'
                f'<span style="color:var(--ok)">\u25cf inbound</span> \u00b7 '
                f'<span style="color:var(--warn)">\u25cf outbound</span>. {poller_note}</p>'
                f'<script id=ifseed type="application/json">{seed_json}</script>{js}</div>')

    def _help_page(self, sess):
        md = _load_doc("WEBGUI.md")
        if md is None:
            body = ('<div class="panel"><h2>Help</h2>'
                    '<p class="muted">The operator guide (WEBGUI.md) was not found on this '
                    'install. It ships at <code>/opt/netconfig/WEBGUI.md</code>.</p></div>')
            return self._send(self._page("Help", body, sess))
        rendered = _render_markdown(md)
        body = (f'<div class="panel help">{rendered}</div>'
                f'<style>.help h1{{color:var(--brass2);border:none}}'
                f'.help h2{{color:var(--brass);border-bottom:1px solid var(--line);padding-bottom:4px}}'
                f'.help h3{{color:var(--txt)}}.help ul{{margin:6px 0 6px 20px}}'
                f'.help li{{margin:3px 0}}.help p{{margin:8px 0}}'
                f'.help table{{margin:10px 0}}.help code{{white-space:nowrap}}</style>')
        self._send(self._page("Help", body, sess))

    # ---- MIB library -----------------------------------------------------
    def _mib_dir(self):
        return os.path.join(str(self.manager.paths.home), "mibs")

    def _read_multipart(self):
        ctype = self.headers.get("Content-Type", "")
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        fields, files = {}, {}
        m = re.search(r"boundary=(.+)$", ctype)
        if not m:
            return fields, files
        boundary = ("--" + m.group(1).strip('"')).encode()
        for part in body.split(boundary):
            part = part.strip(b"\r\n")
            if not part or part == b"--" or b"\r\n\r\n" not in part:
                continue
            head, val = part.split(b"\r\n\r\n", 1)
            val = val.rstrip(b"\r\n")
            headtxt = head.decode("utf-8", "replace")
            nm = re.search(r'name="([^"]*)"', headtxt)
            if not nm:
                continue
            fn = re.search(r'filename="([^"]*)"', headtxt)
            if fn:
                files.setdefault(nm.group(1), []).append((fn.group(1), val))
            else:
                fields[nm.group(1)] = val.decode("utf-8", "replace")
        return fields, files

    @staticmethod
    def _parse_mib(text):
        mod = ""
        mm = re.search(r"([A-Za-z0-9-]+)\s+DEFINITIONS\s*::=\s*BEGIN", text)
        if mm:
            mod = mm.group(1)
        objs = len(re.findall(r"\bOBJECT-TYPE\b", text))
        nodes = len(re.findall(r"OBJECT\s+IDENTIFIER\s*::=", text))
        imports = len(re.findall(r"\bIMPORTS\b", text))
        return {"module": mod, "objects": objs, "nodes": nodes, "imports": imports}

    def _do_mib_upload_raw(self):
        if not self._require_auth():
            return
        _, sess = self._session()
        if not _can(sess["role"], "manage_devices"):
            return self._send(self._page("MIB", '<div class="err">Not permitted.</div>', sess), 403)
        fields, files = self._read_multipart()
        if not secrets.compare_digest(fields.get("csrf", ""), sess["csrf"]):
            return self._send(self._page("Error", '<div class="err">CSRF check failed.</div>', sess), 403)
        d = self._mib_dir()
        os.makedirs(d, exist_ok=True)
        saved, skipped = [], []
        for fname, content in files.get("mibfile", []):
            if not fname:
                continue
            safe = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(fname))
            if len(content) > 8 * 1024 * 1024:
                skipped.append(safe + " (too large)")
                continue
            with open(os.path.join(d, safe), "wb") as fh:
                fh.write(content)
            saved.append(safe)
        self.manager.db.audit(sess["username"], "mib_upload", ", ".join(saved), "")
        self.manager.rebuild_mibindex()
        return self._redirect("/mib")

    def _do_mib_delete(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._mib_page(sess)
        fn = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename((form.get("name") or [""])[0]))
        try:
            os.remove(os.path.join(self._mib_dir(), fn))
        except OSError:
            pass
        self.manager.db.audit(sess["username"], "mib_delete", fn, "")
        self.manager.rebuild_mibindex()
        return self._redirect("/mib")

    def _mib_page(self, q, sess):
        d = self._mib_dir()
        files = sorted(os.listdir(d)) if os.path.isdir(d) else []
        idx = self.manager.mibindex
        rows = ""
        for fn in files:
            path = os.path.join(d, fn)
            try:
                txt = open(path, encoding="utf-8", errors="replace").read()
                info = self._parse_mib(txt)
                size = os.path.getsize(path)
            except OSError:
                continue
            stats = idx.file_stats.get(fn, {})
            unresolved = stats.get("unresolved_names", [])
            mapping = (f'<span class="badge b-ok">{stats.get("resolved", 0)} resolved</span> '
                       f'<span class="badge b-ok">{stats.get("collectible", 0)} collectible</span> '
                       f'<span class="badge {"b-chg" if stats.get("unresolved", 0) else "b-dim"}">'
                       f'{stats.get("unresolved", 0)} unresolved</span> '
                       f'<span class="badge {"b-chg" if stats.get("conflicts", 0) else "b-dim"}">'
                       f'{stats.get("conflicts", 0)} conflicts</span>')
            if unresolved:
                mapping += (f'<div class="muted" style="margin-top:4px">Missing parents: '
                            f'{html.escape(", ".join(unresolved[:8]))}'
                            f'{" …" if len(unresolved) > 8 else ""}</div>')
            dele = ""
            if _can(sess["role"], "manage_devices"):
                dele = (f'<form method=post action="/mib-delete" style="display:inline" '
                        f'onsubmit="return confirm(\'Delete {html.escape(fn)}?\')">'
                        f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(fn)}">'
                        f'<button class=ghost style="padding:2px 8px">delete</button></form>')
            rows += (f'<tr><td><b>{html.escape(fn)}</b></td>'
                     f'<td>{html.escape(info["module"] or "\u2014")}</td>'
                     f'<td>{info["objects"]} objects, {info["nodes"]} nodes</td>'
                     f'<td>{mapping}</td>'
                     f'<td class=muted>{max(size // 1024, 1)} KB</td>'
                     f'<td class=right>{dele}</td></tr>')
        up = ""
        if _can(sess["role"], "manage_devices"):
            up = (f'<div class="panel"><h2>Upload MIB</h2>'
                  f'<p class="muted">Upload vendor MIB files (.mib / .txt / .my). They are stored '
                  f'under the data directory for reference and OID lookups.</p>'
                  f'<form method=post action="/mib-upload" enctype="multipart/form-data">'
                  f'{self._csrf_field()}'
                  f'<input type=file name=mibfile multiple accept=".mib,.txt,.my,.mib.txt">'
                  f'<button>Upload</button></form></div>')
        n_names = len(idx.name_source)
        n_collectible = len(idx.collection_objects)
        unresolved_total = sum(v.get("unresolved", 0) for v in idx.file_stats.values())
        lookup_q = (q.get("q") or [""])[0].strip()
        lookup_html = ""
        if lookup_q:
            if re.match(r"^[\d.]+$", lookup_q):
                detail = idx.resolve_detail(lookup_q)
                lookup_html = (f'<p style="margin-top:8px"><code>{html.escape(lookup_q)}</code> '
                               f'\u2192 <b>{html.escape(detail["name"])}</b> '
                               f'<span class="muted">Source: '
                               f'{html.escape(detail["source"] or "Unmapped")}</span></p>')
            else:
                detail = idx.lookup_detail(lookup_q)
                oid = detail["oid"]
                lookup_html = (f'<p style="margin-top:8px"><b>{html.escape(lookup_q)}</b> \u2192 '
                               + (f'<code>{html.escape(oid)}</code> <span class="muted">Source: '
                                  f'{html.escape(detail["source"])}</span>' if oid else
                                  '<span class="muted">not found</span>')
                               + '</p>')
        automap = (f'<div class="panel"><h2>Automap index</h2>'
                   f'<p class="muted">Uploaded MIBs are compiled into a global OID\u2194name index '
                   f'(<b>{n_names}</b> uploaded definitions resolved, {unresolved_total} unresolved, '
                   f'{len(idx.conflicts)} conflicts, <b>{n_collectible}</b> vendor OBJECT-TYPE '
                   f'definitions collectible) that resolves names and drives bounded vendor polling '
                   f'automatically \u2014 no per-device selection.</p>'
                   f'<form method=get action="/mib" style="display:flex;gap:8px;max-width:560px">'
                   f'<input name=q placeholder="resolve an OID or name, e.g. 1.3.6.1.2.1.1.1.0 or ifDescr" '
                   f'value="{html.escape(lookup_q)}"><button class=ghost>Look up</button></form>'
                   f'{lookup_html}</div>')
        body = (up + automap
                + f'<div class="panel"><h2>MIB library \u00b7 {len(files)} file(s)</h2>'
                f'<table><tr><th>File</th><th>Module</th><th>Contents</th><th>Mapping</th>'
                f'<th>Size</th><th></th></tr>'
                f'{rows or "<tr><td colspan=6 class=muted>No MIBs uploaded yet.</td></tr>"}</table>'
                f'<p class="muted" style="margin-top:8px">Resolved definitions are used immediately '
                f'in SNMP walk results and sysObjectID model mapping. Unresolved definitions usually '
                f'mean a parent or imported MIB is missing; upload that dependency and the index '
                f'rebuilds automatically.</p></div>')
        self._send(self._page("MIB", body, sess))

    def _netflow_section(self, dev):
        m = self.manager
        port = m.settings.get("netflow_port", 2055)
        col = Console.netflow
        if not m.settings.get("netflow_enabled"):
            status = ('<span class="badge b-dim">collector off</span> \u2014 turn it on in '
                      'Settings \u2192 NetFlow.')
        elif not col:
            status = '<span class="badge b-bad">collector not running</span>'
        else:
            st = col.status()
            status = (f'<span class="badge b-ok">listening udp/{st["port"]}</span> \u00b7 '
                      f'{col.packet_count(dev["host"])} packet(s) received from this device')
        rows = ""
        if col:
            for fl in col.flows_for(dev["host"], limit=50):
                rows += (f'<tr><td class=muted>{time.strftime("%H:%M:%S", time.localtime(fl["ts"]))}</td>'
                         f'<td>{html.escape(fl["src"])}:{fl["sport"]}</td>'
                         f'<td>{html.escape(fl["dst"])}:{fl["dport"]}</td>'
                         f'<td>{html.escape(str(fl["proto"]))}</td>'
                         f'<td class=right>{fl["packets"]}</td><td class=right>{fl["bytes"]}</td></tr>')
        table = (f'<table><tr><th>Time</th><th>Source</th><th>Destination</th><th>Proto</th>'
                 f'<th>Packets</th><th>Bytes</th></tr>{rows}</table>' if rows else
                 f'<p class="muted">No flows received yet. Configure this device to export NetFlow '
                 f'to this server on <code>udp/{port}</code>.</p>')
        offnote = ("" if dev.get("netflow") else
                   '<p class="muted">NetFlow is not enabled for this device \u2014 edit it and tick '
                   '"collect NetFlow from this device".</p>')
        return (f'<div class="panel"><h2>NetFlow</h2>'
                f'<p class="muted">Flows exported by this device, matched by source IP '
                f'<b>{html.escape(dev["host"])}</b>. {status}</p>{offnote}{table}</div>')

    def _portmon_section(self, dev):
        spec = (dev.get("monitor_ports") or "").strip()
        if not spec:
            return ('<div class="panel"><h2>TCP / UDP ports</h2>'
                    '<p class="muted">No ports configured. Edit the device and list ports to '
                    'monitor, e.g. <code>tcp/22, tcp/443, udp/53</code>.</p></div>')
        from . import portmon
        results = portmon.check_ports(dev["host"], spec, timeout=1.5)
        rows = ""
        for r in results:
            st = r["state"]
            cls = ("b-ok" if st == "open" else "b-bad" if st == "closed"
                   else "b-chg" if st in ("filtered", "error") else "b-dim")
            svc = f' <span class="muted">{html.escape(r["service"])}</span>' if r.get("service") else ""
            ms = f'{r["ms"]} ms' if r.get("ms") is not None else "\u2014"
            detail = f' <span class="muted">{html.escape(r.get("detail", ""))}</span>' if r.get("detail") else ""
            rows += (f'<tr><td>{r["proto"].upper()}</td><td>{r["port"]}{svc}</td>'
                     f'<td><span class="badge {cls}">{html.escape(st)}</span>{detail}</td>'
                     f'<td class="muted">{ms}</td></tr>')
        return (f'<div class="panel"><h2>TCP / UDP ports</h2>'
                f'<p class="muted">Live status for <b>{html.escape(dev["host"])}</b> \u2014 reload '
                f'to re-check. UDP is best-effort (shows <code>open|filtered</code> when the port '
                f'is silent).</p>'
                f'<table><tr><th>Proto</th><th>Port</th><th>Status</th><th>Latency</th></tr>'
                f'{rows}</table></div>')

    def _appmon_section(self, dev):
        spec = (dev.get("monitor_urls") or "").strip()
        if not spec:
            return ('<div class="panel"><h2>REST API / HTTPS</h2>'
                    '<p class="muted">No endpoints configured. Edit the device and list HTTP(S) '
                    'URLs to monitor, e.g. <code>https://host/api/health 200</code>.</p></div>')
        from . import appmon
        results = appmon.check_all(spec, dev["host"], timeout=5.0)
        rows = ""
        for r in results:
            status = r.get("status")
            http_badge = (f'<span class="badge {"b-ok" if r.get("ok") else "b-bad"}">'
                          f'{status if status is not None else "down"}</span>')
            if r.get("expect"):
                http_badge += f' <span class="muted">exp {r["expect"]}</span>'
            if r.get("error"):
                http_badge += f' <span class="muted">{html.escape(r["error"][:60])}</span>'
            ms = f'{r["ms"]} ms' if r.get("ms") is not None else "\u2014"
            tls = r.get("tls")
            if not tls:
                tls_cell = '<span class="muted">\u2014</span>'
            elif tls.get("valid"):
                dleft = tls.get("expires_days")
                cls = "b-ok" if (dleft is None or dleft > 14) else "b-chg"
                extra = f' \u00b7 {dleft}d left' if dleft is not None else ""
                tls_cell = (f'<span class="badge {cls}">valid{extra}</span> '
                            f'<span class="muted">{html.escape(tls.get("version",""))}</span>')
            else:
                tls_cell = (f'<span class="badge b-bad">invalid</span> '
                            f'<span class="muted">{html.escape((tls.get("error") or "")[:60])}</span>')
            rows += (f'<tr><td style="word-break:break-all">{html.escape(r["url"])}</td>'
                     f'<td>{http_badge}</td><td class="muted">{ms}</td><td>{tls_cell}</td></tr>')
        return (f'<div class="panel"><h2>REST API / HTTPS</h2>'
                f'<p class="muted">Live endpoint status \u2014 reload to re-check. HTTPS URLs also '
                f'show certificate validity and days to expiry.</p>'
                f'<table><tr><th>Endpoint</th><th>HTTP</th><th>Time</th><th>TLS cert</th></tr>'
                f'{rows}</table></div>')

    def _arp_section(self, dev):
        entries = self.manager.db.get_arp(dev["name"])
        rows = "".join(
            f'<tr><td>{html.escape(e.get("ip", ""))}</td>'
            f'<td><code>{html.escape(e.get("mac", ""))}</code></td>'
            f'<td class="muted">{html.escape(str(e.get("ifindex", "")))}</td>'
            f'<td class="muted">{_fmt_ts(e.get("ts"))}</td></tr>'
            for e in entries)
        table = (f'<table><tr><th>IP address</th><th>MAC address</th>'
                 f'<th>Interface index</th><th>Collected</th></tr>{rows}</table>' if rows else
                 '<p class="muted">No ARP entries collected yet.</p>')
        return (f'<div class="panel"><h2>ARP table · {len(entries)} entries</h2>'
                f'<p class="muted">Auto-collected from IP-MIB during SNMP polling.</p>{table}</div>')

    def _vendor_mib_section(self, device):
        values = self.manager.db.get_mib_values(device)
        status = self.manager.db.get_mib_poll_status(device) or {}
        rows = "".join(
            f'<tr><td>{html.escape(v.get("mib_source", "") or "Uploaded MIB")}</td>'
            f'<td><b>{html.escape(v.get("name", ""))}</b></td>'
            f'<td class="muted"><code>{html.escape(v.get("oid", ""))}</code></td>'
            f'<td>{html.escape(str(v.get("value", ""))[:300])}</td>'
            f'<td class="muted">{_fmt_ts(v.get("ts"))}</td></tr>'
            for v in values)
        if rows:
            content = (f'<table><tr><th>Source MIB</th><th>Resolved name</th><th>Raw OID</th>'
                       f'<th>Value</th><th>Collected</th></tr>{rows}</table>')
        else:
            if status.get("roots", 0):
                content = ('<p class="muted">Matching MIB collection trees were found, but the '
                           'SNMP agent returned no values below them. This usually means those '
                           'modules are not exposed by the device or the SNMP view denies them; '
                           'an uploaded MIB defines names but does not enable data on the agent.'
                           '</p>')
            else:
                content = ('<p class="muted">No collection tree matches this device yet. Upload '
                           'MIB files containing resolved OBJECT-TYPE definitions, then use '
                           '<b>Poll now</b>.</p>')
        error = status.get("error", "")
        error_html = (f'<p class="err">Some roots failed: {html.escape(error)}</p>' if error else "")
        summary = (f'{len(values)} value(s) from {status.get("roots", 0)} bounded root(s)'
                   + (f' · last collection {_fmt_ts(status.get("ts"))}' if status else ''))
        return (f'<div class="panel"><h2>Extended MIB data</h2>'
                f'<p class="muted">Automatically collected from uploaded MIB definitions. '
                f'{summary}. Background vendor walks run no more than once every five minutes '
                f'and keep at most 400 values per device.</p>{error_html}{content}</div>')

    def _mac_port_section(self, dev):
        macs = self.manager.db.get_mac_table(dev["name"])
        arp = self.manager.db.get_arp(dev["name"])
        arp_by_mac = {a["mac"]: a["ip"] for a in arp}
        rows = ""
        for e in macs:
            ip = arp_by_mac.get(e["mac"], "")
            portlbl = e["ifdescr"] or (f'if{e["ifindex"]}' if e["ifindex"] else e["port"])
            rows += (f'<tr><td><code>{html.escape(e["mac"])}</code></td>'
                     f'<td>{html.escape(portlbl)}</td>'
                     f'<td class="muted">{html.escape(ip)}</td></tr>')
        if rows:
            table = (f'<table><tr><th>MAC address</th><th>Port</th><th>IP (from ARP)</th></tr>'
                     f'{rows}</table>')
        else:
            table = ('<p class="muted">No MAC-address-table entries collected yet. Poll this device '
                     'over SNMP (SNMP section) \u2014 the bridge forwarding table (BRIDGE-MIB) and ARP '
                     'table are collected automatically for network devices with SNMP enabled. '
                     'Non-switch devices won\u2019t have a forwarding table.</p>')
        return (f'<div class="panel"><h2>MAC address \u2192 port</h2>'
                f'<p class="muted">Layer-2 forwarding table for this switch \u2014 which MAC is learned '
                f'on which port ({len(macs)} entries, {len(arp)} ARP). Auto-collected on SNMP poll.</p>'
                f'{table}</div>')

    def _diff_page(self, q, sess):
        name = (q.get("name") or [""])[0]
        a = (q.get("a") or [""])[0]
        b = (q.get("b") or [""])[0]
        m = self.manager
        try:
            d = m.store.diff_versions(name, a, b)
        except FileNotFoundError:
            return self._send(self._page("Diff", '<div class="err">Version not found.</div>', sess), 404)
        body = (f'<div class="panel"><h2>{html.escape(name)}: {html.escape(a)} \u2192 {html.escape(b)}</h2>'
                f'<pre class="diff">{_colorize_diff(d) if d else "(identical)"}</pre>'
                f'<a class="btn ghost" href="/device?name={_q(name)}">Back</a></div>')
        self._send(self._page("Compare", body, sess))

    def _raw(self, q):
        name = (q.get("name") or [""])[0]
        version = (q.get("version") or [""])[0]
        m = self.manager
        try:
            text = m.store.read_version(name, version) if version else m.store.current(name)
        except FileNotFoundError:
            return self._send("not found", 404, "text/plain")
        if text is None:
            return self._send("no config", 404, "text/plain")
        self._send(text, ctype="text/plain; charset=utf-8")

    # ---- groups ----------------------------------------------------------
    def _groups_page(self, sess, flash=None):
        m = self.manager
        groups = m.inv.groups()
        all_devs = [d["name"] for d in m.inv.all()]
        rows = ""
        for g in groups:
            del_btn = ""
            if _can(sess["role"], "manage_devices"):
                del_btn = (f'<form method=post action="/group-delete" style="display:inline">'
                           f'{self._csrf_field()}<input type=hidden name=name value="{html.escape(g["name"])}">'
                           f'<button class=ghost style="padding:3px 10px">delete</button></form>')
            rows += (f'<tr><td><b>{html.escape(g["name"])}</b><br>'
                     f'<span class=muted>{html.escape(g["description"])}</span></td>'
                     f'<td>{html.escape(", ".join(g["members"]) or "\u2014")}</td>'
                     f'<td class=right>{del_btn}</td></tr>')
        create = ""
        if _can(sess["role"], "manage_devices"):
            checks = "".join(
                f'<label style="display:inline-flex;gap:6px;align-items:center;margin:0 12px 8px 0;font-size:13px;color:var(--txt)">'
                f'<input type=checkbox name=members value="{html.escape(d)}" style="width:auto;margin:0"> {html.escape(d)}</label>'
                for d in all_devs)
            create = (f'<div class="panel"><h2>New / update group</h2>'
                      f'<form method=post action="/group-save">{self._csrf_field()}'
                      f'<div class="row"><div><label>Group name</label>'
                      f'<input name=name placeholder="e.g. all-h3c-switches"></div>'
                      f'<div><label>Description</label><input name=description></div></div>'
                      f'<label>Members</label><div>{checks or "<span class=muted>no devices</span>"}</div>'
                      f'<button>Save group</button></form></div>')
        inner = (f'<div class="panel"><table><tr><th>Group</th><th>Members</th><th></th></tr>'
                 f'{rows or "<tr><td colspan=3 class=muted>no groups</td></tr>"}</table></div>{create}')
        self._send(self._page("Groups", inner, sess, flash=flash))

    def _do_group_save(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._groups_page(sess, flash="Not permitted.")
        name = (form.get("name") or [""])[0].strip()
        if not name:
            return self._groups_page(sess, flash="Group name required.")
        desc = (form.get("description") or [""])[0]
        members = form.get("members") or []
        self.manager.inv.add_group(name, desc)
        self.manager.inv.set_group_members(name, members)
        self.manager.db.audit(sess["username"], "group_save", name, f"{len(members)} members")
        return self._groups_page(sess, flash=f"Group '{name}' saved with {len(members)} members.")

    def _do_group_delete(self, form, sess):
        if not _can(sess["role"], "manage_devices"):
            return self._groups_page(sess, flash="Not permitted.")
        name = (form.get("name") or [""])[0]
        self.manager.inv.delete_group(name)
        self.manager.db.audit(sess["username"], "group_delete", name, "")
        return self._groups_page(sess, flash=f"Group '{name}' deleted.")

    # ---- automation (submit change request) ------------------------------
    def _automation_page(self, sess, flash=None):
        m = self.manager
        groups = [g["name"] for g in m.inv.groups()]
        gopts = "".join(f'<option value="{html.escape(g)}">{html.escape(g)}</option>' for g in groups)
        target_select = (f'<div class="row"><div><label>Target type</label>'
                         f'<select name=target_kind><option value=group>group</option>'
                         f'<option value=tag>tag</option><option value=device>device(s)</option>'
                         f'<option value=all>all devices</option></select></div>'
                         f'<div><label>Target value</label>'
                         f'<input name=target_value list=grouplist placeholder="group name / tag / device names">'
                         f'<datalist id=grouplist>{gopts}</datalist></div></div>')
        sections = []

        # 1) change request (operator+)
        if _can(sess["role"], "submit"):
            sections.append(
                f'<div class="panel"><h2>New change request</h2>'
                f'<p class="muted">Commands (one per line). Variables: '
                f'<code>${{NodeName}}</code>, <code>${{IP_Address}}</code>, '
                f'<code>${{Platform}}</code>. An approver reviews before it runs.</p>'
                f'<form method=post action="/request-submit">{self._csrf_field()}'
                f'<label>Title</label><input name=title placeholder="e.g. Add NTP to core switches">'
                f'{target_select}<input type=hidden name=mode value=config>'
                f'<label>Commands</label>'
                f'<textarea name=body placeholder="ntp server 10.0.0.254&#10;logging host 10.0.0.9"></textarea>'
                f'<button>Submit for approval</button></form></div>')

        # 2) ad-hoc run (approver/admin) -- no approval, audited
        if _can(sess["role"], "execute"):
            locked = "" if m.vault_ready() else ' <span class="vault-lock">vault locked \u2014 unlock first</span>'
            sections.append(
                f'<div class="panel"><h2>Run now (ad-hoc)</h2>'
                f'<p class="muted">Runs immediately across the target with no approval step '
                f'(your role may execute directly). Use <b>command</b> for read-only show/exec; '
                f'<b>config</b> pushes lines. Everything is audited.{locked}</p>'
                f'<form method=post action="/run-adhoc">{self._csrf_field()}'
                f'{target_select}'
                f'<div class="row"><div style="max-width:180px"><label>Mode</label>'
                f'<select name=mode><option value=command>command (read)</option>'
                f'<option value=config>config (push)</option></select></div>'
                f'<div style="max-width:200px"><label>&nbsp;</label>'
                f'<label style="color:var(--txt);font-weight:400"><input type=checkbox name=save value=1 style="width:auto"> save to startup</label></div></div>'
                f'<label>Commands</label><textarea name=body placeholder="show version"></textarea>'
                f'<button {"disabled" if not m.vault_ready() else ""}>Run now</button></form></div>')

        # 3) saved scripts library (operator+ to author)
        if _can(sess["role"], "author_scripts"):
            srows = ""
            for sc in self.scripts.all():
                srows += (f'<tr><td><b>{html.escape(sc["name"])}</b><br>'
                          f'<span class=muted>{html.escape(sc["description"] or "")}</span></td>'
                          f'<td><pre style="margin:0;max-height:120px">{html.escape(sc["body"])}</pre></td>'
                          f'<td class=right><form method=post action="/script-delete" style="display:inline">'
                          f'{self._csrf_field()}<input type=hidden name=id value="{sc["id"]}">'
                          f'<button class=ghost style="padding:2px 8px">delete</button></form></td></tr>')
            sections.append(
                f'<div class="panel"><h2>Script library</h2>'
                f'<table><tr><th>Name</th><th>Body</th><th></th></tr>'
                f'{srows or "<tr><td colspan=3 class=muted>no saved scripts</td></tr>"}</table>'
                f'<h2 style="margin-top:16px">Save a script</h2>'
                f'<form method=post action="/script-save">{self._csrf_field()}'
                f'<div class="row"><div><label>Name</label><input name=name></div>'
                f'<div><label>Description</label><input name=description></div></div>'
                f'<label>Commands</label><textarea name=body></textarea>'
                f'<button>Save script</button></form></div>')

        if not sections:
            sections.append('<div class="panel"><p class="muted">Your role has no automation actions.</p></div>')
        self._send(self._page("Automation", "".join(sections), sess, flash=flash))

    def _do_run_adhoc(self, form, sess):
        if not _can(sess["role"], "execute"):
            return self._automation_page(sess, flash="Not permitted to run ad-hoc.")
        if not self.manager.vault_ready():
            return self._automation_page(sess, flash="Vault locked \u2014 unlock to run.")
        kind = (form.get("target_kind") or ["group"])[0]
        value = (form.get("target_value") or [""])[0].strip()
        mode = (form.get("mode") or ["command"])[0]
        body = (form.get("body") or [""])[0]
        save = (form.get("save") or [""])[0] == "1"
        devices = self.manager.inv.resolve_target(kind, value, only_enabled=True)
        if not devices:
            return self._automation_page(sess, flash="No devices matched that target.")
        try:
            job = self.wf.run_adhoc(devices=devices, mode=mode, body=body,
                                    run_by=sess["username"], title=f"ad-hoc {mode}", save=save)
        except (ValueError, RuntimeError) as e:
            return self._automation_page(sess, flash=f"Run failed: {e}")
        j = self.wf.get_job(job["id"])
        jr = ""
        for x in j["results"]:
            jr += (f'<tr><td>{html.escape(x["device"])}</td><td>{_ok_badge(x["ok"])}</td>'
                   f'<td><pre style="margin:0;max-height:160px">{html.escape(x["output"][:3000])}</pre></td></tr>')
        body_html = (f'<div class="panel"><h2>Ad-hoc {html.escape(mode)} \u00b7 {html.escape(j["summary"])}</h2>'
                     f'<table><tr><th>Device</th><th>Result</th><th>Output</th></tr>{jr}</table>'
                     f'<a class="btn ghost" href="/automation">Back</a></div>')
        self._send(self._page("Ad-hoc run", body_html, sess))

    def _do_script_save(self, form, sess):
        if not _can(sess["role"], "author_scripts"):
            return self._automation_page(sess, flash="Not permitted.")
        name = (form.get("name") or [""])[0].strip()
        body = (form.get("body") or [""])[0]
        if not name or not body.strip():
            return self._automation_page(sess, flash="Script name and body required.")
        self.scripts.create(name, body, description=(form.get("description") or [""])[0],
                            created_by=sess["username"])
        self.manager.db.audit(sess["username"], "script_save", name, "")
        return self._automation_page(sess, flash=f"Script '{name}' saved.")

    def _do_script_delete(self, form, sess):
        if not _can(sess["role"], "author_scripts"):
            return self._automation_page(sess, flash="Not permitted.")
        sid = int((form.get("id") or ["0"])[0] or 0)
        self.scripts.delete(sid)
        self.manager.db.audit(sess["username"], "script_delete", str(sid), "")
        return self._automation_page(sess, flash="Script deleted.")

    def _do_request_submit(self, form, sess):
        if not _can(sess["role"], "submit"):
            return self._automation_page(sess, flash="Not permitted to submit.")
        title = (form.get("title") or [""])[0].strip() or "(untitled)"
        body = (form.get("body") or [""])[0]
        tk = (form.get("target_kind") or ["group"])[0]
        tv = (form.get("target_value") or [""])[0].strip()
        mode = (form.get("mode") or ["config"])[0]
        rid = self.wf.submit(title=title, body=body, target_kind=tk,
                             target_value=tv, mode=mode, requested_by=sess["username"])
        return self._redirect(f"/request?id={rid}")

    # ---- change requests -------------------------------------------------
    def _requests_page(self, sess, flash=None):
        reqs = self.wf.list()
        rows = ""
        for r in reqs:
            badge = _STATUS_BADGE.get(r["status"], "b-dim")
            rows += (f'<tr><td><a href="/request?id={r["id"]}">CR#{r["id"]}</a></td>'
                     f'<td>{html.escape(r["title"])}</td>'
                     f'<td class=muted>{html.escape(r["mode"])} \u00b7 {html.escape(r["target_kind"])}:{html.escape(r["target_value"])}</td>'
                     f'<td>{html.escape(r["requested_by"])}</td>'
                     f'<td><span class="badge {badge}">{html.escape(r["status"])}</span></td>'
                     f'<td class=muted>{_fmt_ts(r["requested_ts"])}</td></tr>')
        inner = (f'<div class="panel"><table>'
                 f'<tr><th>ID</th><th>Title</th><th>Change</th><th>Requested by</th><th>Status</th><th>When</th></tr>'
                 f'{rows or "<tr><td colspan=6 class=muted>no requests</td></tr>"}</table></div>')
        self._send(self._page("Change Requests", inner, sess, flash=flash))

    def _request_page(self, q, sess):
        rid = int((q.get("id") or ["0"])[0] or 0)
        prev = self.wf.preview(rid)
        if not prev:
            return self._send(self._page("Request", '<div class="err">No such request.</div>', sess), 404)
        cr = prev["request"]
        badge = _STATUS_BADGE.get(cr["status"], "b-dim")
        tgt_rows = ""
        for t in prev["targets"]:
            un = (' <span class="badge b-bad">unresolved: ' + html.escape(", ".join(t["unresolved"])) + '</span>') if t["unresolved"] else ""
            lines = html.escape("\n".join(t["lines"]))
            tgt_rows += (f'<tr><td>{html.escape(t["device"])}{un}</td>'
                         f'<td class=muted>{html.escape(t["host"])}</td>'
                         f'<td><pre style="margin:0;max-height:160px">{lines}</pre></td></tr>')
        detail = (f'<div class="panel"><h2>CR#{cr["id"]} \u00b7 {html.escape(cr["title"])} '
                  f'<span class="badge {badge}">{html.escape(cr["status"])}</span></h2>'
                  f'<table><tr><th>Mode</th><td>{html.escape(cr["mode"])}</td></tr>'
                  f'<tr><th>Target</th><td>{html.escape(cr["target_kind"])}:{html.escape(cr["target_value"])}</td></tr>'
                  f'<tr><th>Requested by</th><td>{html.escape(cr["requested_by"])} \u00b7 {_fmt_ts(cr["requested_ts"])}</td></tr>'
                  + (f'<tr><th>Reviewed by</th><td>{html.escape(cr["reviewed_by"] or "\u2014")} \u00b7 {_fmt_ts(cr["reviewed_ts"])}</td></tr>' if cr["reviewed_by"] else "")
                  + (f'<tr><th>Note</th><td>{html.escape(cr["review_note"])}</td></tr>' if cr["review_note"] else "")
                  + '</table>')
        detail += (f'<h2 style="margin-top:16px">Submitted commands</h2>'
                   f'<pre>{html.escape(cr["body"])}</pre>')
        actions = ""
        if cr["status"] == "pending" and _can(sess["role"], "approve"):
            actions = (f'<form method=post action="/request-approve" style="display:inline">'
                       f'{self._csrf_field()}<input type=hidden name=id value="{cr["id"]}">'
                       f'<button>Approve</button></form> '
                       f'<form method=post action="/request-reject" style="display:inline">'
                       f'{self._csrf_field()}<input type=hidden name=id value="{cr["id"]}">'
                       f'<input name=note placeholder="reason" style="width:200px;display:inline-block;margin:0 6px 0 12px">'
                       f'<button class=danger>Reject</button></form>')
        elif cr["status"] == "approved" and _can(sess["role"], "execute"):
            locked = not self.manager.vault_ready()
            vault_note = "" if not locked else ' <span class="vault-lock">vault locked \u2014 unlock first</span>'
            actions = (f'<form method=post action="/request-execute" style="display:inline">'
                       f'{self._csrf_field()}<input type=hidden name=id value="{cr["id"]}">'
                       f'<label style="display:inline;color:var(--txt)"><input type=checkbox name=save value=1 style="width:auto"> save to startup-config</label> '
                       f'<button {"disabled" if locked else ""}>Execute now</button></form>{vault_note}')
        detail += (f'<div style="margin-top:14px">{actions}</div></div>')
        targets = (f'<div class="panel"><h2>Resolved plan \u00b7 {len(prev["targets"])} device(s)</h2>'
                   f'<table><tr><th>Device</th><th>Address</th><th>Commands to run</th></tr>'
                   f'{tgt_rows or "<tr><td colspan=3 class=muted>no matching devices</td></tr>"}</table></div>')
        job_html = ""
        if cr.get("job_id"):
            job = self.wf.get_job(cr["job_id"])
            if job:
                jr = ""
                for x in job["results"]:
                    jr += (f'<tr><td>{html.escape(x["device"])}</td>'
                           f'<td>{_ok_badge(x["ok"])}</td>'
                           f'<td><pre style="margin:0;max-height:140px">{html.escape(x["output"][:2000])}</pre></td></tr>')
                job_html = (f'<div class="panel"><h2>Execution result \u00b7 {html.escape(job["summary"])}</h2>'
                            f'<table><tr><th>Device</th><th>Result</th><th>Output</th></tr>{jr}</table></div>')
        self._send(self._page(f"CR#{cr['id']}", detail + targets + job_html, sess))

    def _do_request_action(self, form, sess, action):
        if not _can(sess["role"], "approve"):
            return self._requests_page(sess, flash="Not permitted to review requests.")
        rid = int((form.get("id") or ["0"])[0] or 0)
        try:
            if action == "approve":
                self.wf.approve(rid, sess["username"])
            else:
                self.wf.reject(rid, sess["username"], (form.get("note") or [""])[0])
        except ValueError as e:
            return self._requests_page(sess, flash=str(e))
        return self._redirect(f"/request?id={rid}")

    def _do_request_execute(self, form, sess):
        if not _can(sess["role"], "execute"):
            return self._requests_page(sess, flash="Not permitted to execute.")
        rid = int((form.get("id") or ["0"])[0] or 0)
        save = (form.get("save") or [""])[0] == "1"
        if not self.manager.vault_ready():
            return self._request_page({"id": [str(rid)]}, sess)
        try:
            self.wf.execute(rid, sess["username"], save=save)
        except (ValueError, RuntimeError) as e:
            return self._requests_page(sess, flash=f"Execute failed: {e}")
        return self._redirect(f"/request?id={rid}")

    # ---- compliance ------------------------------------------------------
    # ---- alerts ----------------------------------------------------------
    def _alerts_page(self, q, sess, flash=None):
        from . import monitor as _mon
        m = self.manager
        can_manage = _can(sess["role"], "settings")
        firing = m.db.alerts(state="firing", limit=100)
        frows = ""
        for a in firing:
            sev = a["severity"]
            cls = "b-bad" if sev == "high" else "b-chg" if sev == "medium" else "b-dim"
            frows += (f'<tr><td><span class="badge {cls}">{html.escape(sev)}</span></td>'
                      f'<td><a href="/device?name={_q(a["device"])}">{html.escape(a["device"])}</a></td>'
                      f'<td>{html.escape(a["message"])}</td>'
                      f'<td class="muted">{_fmt_ts(a["last_ts"])}</td></tr>')
        firing_panel = (f'<div class="panel"><h2>Firing alerts \u00b7 {len(firing)}</h2>'
                        + (f'<table><tr><th>Severity</th><th>Device</th><th>Detail</th>'
                           f'<th>Since</th></tr>{frows}</table>' if firing else
                           '<p class="muted">No alerts firing. \U0001F7E2</p>') + '</div>')

        recent = [a for a in m.db.alerts(limit=30) if a["state"] == "resolved"][:10]
        rrows = "".join(
            f'<tr><td class="muted">{_fmt_ts(a["last_ts"])}</td><td>{html.escape(a["device"])}</td>'
            f'<td class="muted">{html.escape(a["message"])}</td></tr>' for a in recent)
        recent_panel = (f'<div class="panel"><h2>Recently resolved</h2>'
                        f'<table><tr><th>When</th><th>Device</th><th>Detail</th></tr>'
                        f'{rrows or "<tr><td colspan=3 class=muted>none</td></tr>"}</table></div>')

        rules = m.db.rules()
        rulerows = ""
        for r in rules:
            state = ('<span class="badge b-ok">on</span>' if r["enabled"]
                     else '<span class="badge b-dim">off</span>')
            delbtn = ""
            if can_manage:
                delbtn = (f'<form method=post action="/alert-rule-delete" style="display:inline" '
                          f'onsubmit="return confirm(\'Delete rule?\')">{self._csrf_field()}'
                          f'<input type=hidden name=id value="{r["id"]}">'
                          f'<button class=ghost style="padding:2px 8px">delete</button></form>')
            rulerows += (f'<tr><td>{html.escape(r["name"])}</td>'
                         f'<td>{html.escape(r["device"] or "all")}</td>'
                         f'<td>{html.escape(r["metric"])} {html.escape(r["op"])} '
                         f'{html.escape(r["threshold"])}</td>'
                         f'<td>{html.escape(r["target"] or "any")}</td>'
                         f'<td>{html.escape(r["severity"])}</td><td>{state}</td>'
                         f'<td class=right>{delbtn}</td></tr>')
        rules_panel = (f'<div class="panel"><h2>Alert rules \u00b7 {len(rules)}</h2>'
                       f'<table><tr><th>Name</th><th>Device</th><th>Condition</th><th>Target</th>'
                       f'<th>Severity</th><th>State</th><th></th></tr>'
                       f'{rulerows or "<tr><td colspan=7 class=muted>No rules yet.</td></tr>"}'
                       f'</table></div>')

        create_panel = ""
        if can_manage:
            devopts = '<option value="">all devices</option>' + "".join(
                f'<option value="{html.escape(d["name"])}">{html.escape(d["name"])}</option>'
                for d in m.inv.all())
            metopts = "".join(f'<option value="{v}">{html.escape(lbl)}</option>'
                              for v, lbl in _mon.METRIC_LABELS)
            opts_json = json.dumps(_mon.OPS_BY_METRIC)
            create_panel = (
                f'<div class="panel"><h2>New alert rule</h2>'
                f'<form method=post action="/alert-rule-add">{self._csrf_field()}'
                f'<div class="row">'
                f'<div><label>Name</label><input name=name required placeholder="SSH down on servers"></div>'
                f'<div><label>Device</label><select name=device>{devopts}</select></div>'
                f'<div><label>Severity</label><select name=severity>'
                f'<option value=high>high</option><option value=medium selected>medium</option>'
                f'<option value=low>low</option></select></div></div>'
                f'<div class="row">'
                f'<div><label>Monitor</label><select name=metric id=metric>{metopts}</select></div>'
                f'<div><label>Condition</label><select name=op id=op></select></div>'
                f'<div><label>Threshold</label><input name=threshold id=threshold placeholder="closed / 200 / 14"></div>'
                f'<div><label>Target <span class=muted>(blank = any)</span></label>'
                f'<input name=target placeholder="tcp/22 or https://host/api"></div></div>'
                f'<button>Create rule</button></form>'
                f'<script>(function(){{var OPS={opts_json};'
                f'var mt=document.getElementById("metric"),op=document.getElementById("op"),'
                f'th=document.getElementById("threshold");'
                f'var HINT={{port_state:"open / closed / filtered",http_status:"e.g. 200",'
                f'response_time:"milliseconds",tls_expiry:"days",tls_valid:"invalid"}};'
                f'function upd(){{var ops=OPS[mt.value]||[];op.innerHTML="";'
                f'ops.forEach(function(o){{var e=document.createElement("option");e.value=o;e.textContent=o;op.appendChild(e);}});'
                f'th.placeholder=HINT[mt.value]||"";}}'
                f'mt.addEventListener("change",upd);upd();}})();</script></div>')

        smtp_note = ('<div class="panel"><p class="muted">Configure the SMTP relay in '
                     '<a href="/settings">Settings</a> to receive these alerts by email. '
                     'Enable background polling there too (Monitor poll interval).</p></div>')
        body = firing_panel + create_panel + rules_panel + recent_panel + smtp_note
        self._send(self._page("Alerts", body, sess, flash))

    def _do_alert_rule_add(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._alerts_page({}, sess, flash="Not permitted.")
        g = lambda k, d="": (form.get(k) or [d])[0].strip()
        name = g("name")
        metric = g("metric")
        if not name or metric not in ("port_state","http_status","response_time","tls_expiry","tls_valid"):
            return self._alerts_page({}, sess, flash="Name and a valid monitor are required.")
        self.manager.db.add_rule(name, g("device"), metric, g("target"),
                                 g("op") or "is", g("threshold"), g("severity") or "medium")
        self.manager.db.audit(sess["username"], "alert_rule_add", name, metric)
        return self._redirect("/alerts")

    def _do_alert_rule_delete(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._alerts_page({}, sess, flash="Not permitted.")
        try:
            self.manager.db.delete_rule(int((form.get("id") or ["0"])[0]))
        except ValueError:
            pass
        return self._redirect("/alerts")

    def _do_smtp_test(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._settings_page_v2(sess, q={"section": ["email"]}, flash="Not permitted.")
        from . import mailer
        pw, tok = mailer.resolve_auth(self.manager)
        ok, msg = mailer.send_mail(self.manager.settings,
                                   "NetConfig SMTP test",
                                   "This is a test email from NetConfig alerts.",
                                   password=pw, oauth_token=tok)
        return self._settings_page_v2(
            sess, q={"section": ["email"]},
            flash=("Test email " + ("sent: " if ok else "failed: ") + msg))

    def _do_oauth_test(self, form, sess):
        if not _can(sess["role"], "settings"):
            return self._settings_page_v2(sess, q={"section": ["email"]}, flash="Not permitted.")
        from . import oauth
        secret = None
        try:
            if self.manager.vault_ready():
                secret = self.manager.vault.get_secret(oauth.O365_SECRET).get("client_secret")
        except Exception:
            secret = None
        if not self.manager.vault_ready():
            return self._settings_page_v2(
                sess, q={"section": ["email"]},
                flash="Unlock the vault first (the client secret is stored there).")
        tok, err = oauth.get_token(self.manager.settings, secret, use_cache=False)
        if tok:
            msg = "O365 OAuth OK \u2014 access token acquired from Entra."
        else:
            msg = "O365 OAuth failed: " + (err or "unknown error")
        return self._settings_page_v2(sess, q={"section": ["email"]}, flash=msg)

    def _do_db_test(self, form, sess):
        """Validate the PostgreSQL history connection using the values currently
        on the form (falling back to saved settings / the vault password) and
        create the history table if it is missing."""
        if not _can(sess["role"], "settings"):
            return self._settings_page_v2(sess, q={"section": ["db"]}, flash="Not permitted.")
        from . import ifhistory as _ifh
        g = lambda k: (form.get(k) or [""])[0].strip()
        s = dict(self.manager.settings)
        for k in ("pg_host", "pg_dbname", "pg_user", "pg_sslmode"):
            if g(k):
                s[k] = g(k)
        if g("pg_port"):
            try:
                s["pg_port"] = int(g("pg_port"))
            except ValueError:
                pass
        pw = (form.get("pg_password") or [""])[0] or self.manager._pg_password()
        backend = _ifh.build_backend(s, password=pw)
        if backend is None:
            return self._settings_page_v2(
                sess, q={"section": ["db"]},
                flash="Set at least a host and database name first.")
        res = backend.ensure_ready()
        if res["ok"]:
            msg = ("Connection OK \u2014 history table created."
                   if res["created"]
                   else "Connection OK \u2014 history table already present.")
        else:
            msg = "Connection failed: " + (res["error"] or "unknown error")
        return self._settings_page_v2(sess, q={"section": ["db"]}, flash=msg)

    def _compliance_page(self, q, sess, flash=None):
        standard = (q.get("standard") or [""])[0] or None
        m = self.manager
        stds = _compliance.standards()
        sel = "".join(
            f'<option value="{html.escape(s)}"{" selected" if s==standard else ""}>{html.escape(s)}</option>'
            for s in stds)
        controls = (f'<div class="panel"><h2>Run audit</h2>'
                    f'<form method=post action="/compliance-run" class="row">{self._csrf_field()}'
                    f'<div><label>Standard</label><select name=standard>'
                    f'<option value="">All standards</option>{sel}</select></div>'
                    f'<div style="flex:0;align-self:end"><button>Run compliance audit</button></div>'
                    f'</form><p class="muted" style="margin-top:8px">Audits stored configs '
                    f'(collect devices first). Starter rule packs \u2014 extend for your estate.</p></div>')
        last = m.db.conn.execute(
            "SELECT * FROM compliance_runs ORDER BY ts DESC LIMIT 1").fetchone()
        report_html = ""
        if last:
            rep = json.loads(last["report"])
            t = rep["totals"]
            summary = (f'<div class="panel"><h2>Last audit \u00b7 {html.escape(last["standard"] or "all")} '
                       f'\u00b7 {_fmt_ts(last["ts"])}</h2>'
                       f'<p>Compliant devices: <b>{t["compliant_devices"]}/{t["device_count"]}</b> \u00b7 '
                       f'checks passed <span class="badge b-ok">{t["pass"]}</span> '
                       f'failed <span class="badge b-bad">{t["fail"]}</span> '
                       f'unknown <span class="badge b-dim">{t.get("unknown", 0)}</span></p></div>')
            dev_html = ""
            for dr in rep["devices"]:
                if dr.get("skipped"):
                    dev_html += (f'<div class="panel"><h2>{html.escape(dr["device"])} '
                                 f'<span class="badge b-dim">no config</span></h2></div>')
                    continue
                rrows = ""
                for r in dr["results"]:
                    b = ("b-ok" if r["status"] == "pass" else
                         "b-bad" if r["status"] == "fail" else "b-dim")
                    ev = html.escape(r["evidence"][:80]) if r["evidence"] else ""
                    rem = "" if r["status"] == "pass" else f'<div class="muted" style="margin-top:4px">\u21b3 {html.escape(r["remediation"])}</div>'
                    kind = ('<br><span class="muted">operational evidence \u00b7 not scored</span>'
                            if not r.get("scored", True) else '')
                    rrows += (f'<tr><td><span class="sev-{r["severity"]}">\u25cf</span> {html.escape(r["title"])}<br>'
                              f'<span class=muted>{html.escape(r["id"])} \u00b7 {html.escape(r["refs"])}</span>{kind}{rem}</td>'
                              f'<td class=muted>{ev}</td>'
                              f'<td><span class="badge {b}">{r["status"]}</span></td></tr>')
                dh = ("b-bad" if dr["failed"] else
                      "b-dim" if dr.get("unknown", 0) else "b-ok")
                dev_html += (f'<div class="panel"><h2>{html.escape(dr["device"])} '
                             f'<span class="badge {dh}">{dr["passed"]} pass / {dr["failed"]} fail / '
                             f'{dr.get("unknown", 0)} unknown</span></h2>'
                             f'<table><tr><th>Control</th><th>Evidence</th><th></th></tr>{rrows}</table></div>')
            report_html = summary + dev_html
        self._send(self._page("Compliance", controls + report_html, sess, flash=flash))

    def _do_compliance_run(self, form, sess):
        standard = (form.get("standard") or [""])[0] or None
        m = self.manager
        devices = m.inv.all(only_enabled=False)
        report = _compliance.evaluate_fleet(m.store, devices, standard)
        t = report["totals"]
        m.db.conn.execute(
            "INSERT INTO compliance_runs (ts, standard, run_by, total, passed, failed, report) "
            "VALUES (?,?,?,?,?,?,?)",
            (time.time(), standard or "", sess["username"], t["checks"], t["pass"],
             t["fail"], json.dumps(report)))
        m.db.conn.commit()
        m.db.audit(sess["username"], "compliance_run", standard or "all",
                   f'{t["compliant_devices"]}/{t["device_count"]} compliant')
        return self._redirect("/compliance" + (f"?standard={_q(standard)}" if standard else ""))

    # ---- users -----------------------------------------------------------
    def _users_page(self, sess, flash=None):
        if not _can(sess["role"], "manage_users"):
            return self._send(self._page("Users", '<div class="err">Admin only.</div>', sess), 403)
        m = self.manager
        rows = ""
        for u in m.users.all():
            dis = ' <span class="badge b-dim">disabled</span>' if u["disabled"] else ""
            role_opts = "".join(f'<option value="{r}"{" selected" if r==u["role"] else ""}>{r}</option>' for r in _roles())
            rows += (f'<tr><td><b>{html.escape(u["username"])}</b>{dis}<br>'
                     f'<span class=muted>{html.escape(u["fullname"] or "")}</span></td>'
                     f'<td>{html.escape(u["role"])}</td>'
                     f'<td class=muted>{_fmt_ts(u["last_login"])}</td>'
                     f'<td><form method=post action="/user-update" class="row" style="gap:6px">'
                     f'{self._csrf_field()}<input type=hidden name=username value="{html.escape(u["username"])}">'
                     f'<select name=role style="margin:0;width:auto">{role_opts}</select>'
                     f'<input name=password placeholder="new pw (optional)" style="margin:0;width:140px">'
                     f'<button style="padding:5px 10px">Update</button></form></td></tr>')
        table = (f'<div class="panel"><table><tr><th>User</th><th>Role</th><th>Last login</th><th>Manage</th></tr>{rows}</table></div>')
        ropts = "".join(f'<option value="{r}">{r}</option>' for r in _roles())
        create = (f'<div class="panel"><h2>Add user</h2>'
                  f'<form method=post action="/user-create">{self._csrf_field()}'
                  f'<div class="row"><div><label>Username</label><input name=username></div>'
                  f'<div><label>Full name</label><input name=fullname></div>'
                  f'<div><label>Role</label><select name=role>{ropts}</select></div></div>'
                  f'<label>Password</label><input type=password name=password>'
                  f'<button>Create user</button></form></div>')
        self._send(self._page("Users", table + create, sess, flash=flash))

    def _do_user_create(self, form, sess):
        if not _can(sess["role"], "manage_users"):
            return self._users_page(sess, flash="Admin only.")
        u = (form.get("username") or [""])[0].strip()
        pw = (form.get("password") or [""])[0]
        role = (form.get("role") or ["viewer"])[0]
        fn = (form.get("fullname") or [""])[0]
        try:
            self.manager.users.create(u, pw, role=role, fullname=fn)
            self.manager.db.audit(sess["username"], "user_create", u, role)
            return self._users_page(sess, flash=f"User '{u}' created.")
        except ValueError as e:
            return self._users_page(sess, flash=str(e))

    def _do_user_update(self, form, sess):
        if not _can(sess["role"], "manage_users"):
            return self._users_page(sess, flash="Admin only.")
        u = (form.get("username") or [""])[0]
        role = (form.get("role") or [""])[0]
        pw = (form.get("password") or [""])[0]
        if role:
            self.manager.users.set_role(u, role)
        if pw:
            self.manager.users.set_password(u, pw)
        self.manager.db.audit(sess["username"], "user_update", u,
                              (f"role={role}" if role else "") + (" pw-reset" if pw else ""))
        return self._users_page(sess, flash=f"User '{u}' updated.")

    # ---- audit / runs ----------------------------------------------------
    def _audit_page(self, sess):
        rows = ""
        for a in self.manager.db.recent_audit(300):
            rows += (f'<tr><td class=muted>{_fmt_ts(a["ts"])}</td>'
                     f'<td>{html.escape(a["actor"])}</td>'
                     f'<td><span class="badge b-brass">{html.escape(a["action"])}</span></td>'
                     f'<td class=muted>{html.escape(a["target"])}</td>'
                     f'<td class=muted>{html.escape(a["detail"])}</td></tr>')
        inner = (f'<div class="panel"><table>'
                 f'<tr><th>Time</th><th>Actor</th><th>Action</th><th>Target</th><th>Detail</th></tr>'
                 f'{rows or "<tr><td colspan=5 class=muted>no audit entries</td></tr>"}</table></div>')
        self._send(self._page("Audit Trail", inner, sess))

    def _runs_page(self, sess):
        m = self.manager
        rows = ""
        for r in m.inv.recent_runs(200):
            st = ('<span class="badge b-ok">ok</span>' if r["ok"]
                  else '<span class="badge b-bad">error</span>')
            ch = '<span class="badge b-chg">changed</span>' if r["changed"] else ""
            rows += (f'<tr><td class="muted">{_fmt_ts(r["ts"])}</td>'
                     f'<td>{html.escape(r["device"])}</td><td>{st} {ch}</td>'
                     f'<td class="muted">{html.escape(r["message"])}</td></tr>')
        inner = (f'<div class="panel"><table>'
                 f'<tr><th>Time</th><th>Device</th><th>Result</th><th>Message</th></tr>'
                 f'{rows or "<tr><td class=muted colspan=4>no runs yet</td></tr>"}</table></div>')
        self._send(self._page("Run Log", inner, sess))

    # ---- actions ---------------------------------------------------------
    def _do_collect(self, form, sess):
        if not _can(sess["role"], "collect"):
            return self._dashboard(sess, flash="Not permitted to collect.")
        if not self.manager.vault_ready():
            return self._dashboard(sess, flash="Vault locked \u2014 unlock to collect.")
        m = self.manager
        if (form.get("all") or [""])[0] == "1":
            results = m.collect_all()
            ok = sum(1 for r in results if r.ok)
            ch = sum(1 for r in results if r.changed)
            m.db.audit(sess["username"], "collect_all", "", f"{ok}/{len(results)} ok")
            return self._dashboard(sess, flash=f"Collected {ok}/{len(results)} devices, {ch} changed.")
        name = (form.get("name") or [""])[0]
        r = m.collect(name)
        m.db.audit(sess["username"], "collect", name, r.message)
        return self._dashboard(sess, flash=f"{name}: {r.message}" + (" (changed)" if r.changed else ""))

    def _do_snmp(self, form, sess):
        if not _can(sess["role"], "collect"):
            return self._dashboard(sess, flash="Not permitted.")
        if not self.manager.vault_ready():
            return self._dashboard(sess, flash="Vault locked \u2014 unlock to poll SNMP.")
        if (form.get("all") or [""])[0] == "1":
            res = self.manager.snmp_poll_all(vendor_force=True)
            ok = sum(1 for r in res.values() if r.get("ok"))
            self.manager.db.audit(sess["username"], "snmp_poll_all", "",
                                  f"{ok}/{len(res)} reachable")
            return self._redirect("/snmp")
        name = (form.get("name") or [""])[0]
        res = self.manager.snmp_poll(name, vendor_force=True)
        self.manager.db.audit(sess["username"], "snmp_poll", name,
                              "ok" if res.get("ok") else res.get("error", "fail"))
        if (form.get("back") or [""])[0] == "snmp":
            return self._redirect(f"/snmp?device={_q(name)}")
        return self._redirect(f"/device?name={_q(name)}")

    def _topology_page(self, sess):
        rows = self.manager.db.get_neighbors()
        devices = sorted({r["device"] for r in rows} | {r.get("neighbor_device", "") for r in rows if r.get("neighbor_device")})
        unmanaged = [r for r in rows if not r.get("managed_neighbor")]
        # deterministic circular layout; no client-side dependency.
        import math
        nodes = {}
        count = max(1, len(devices))
        for i, name in enumerate(devices):
            angle = (2 * math.pi * i / count) - math.pi / 2
            nodes[name] = (400 + 270 * math.cos(angle), 300 + 220 * math.sin(angle))
        svg = ['<svg viewBox="0 0 800 600" role="img" aria-label="Network topology" style="width:100%;min-height:480px">']
        for r in rows:
            if not r.get("managed_neighbor") or not r.get("neighbor_device") or r["device"] not in nodes or r["neighbor_device"] not in nodes:
                continue
            x1,y1=nodes[r["device"]]; x2,y2=nodes[r["neighbor_device"]]
            svg.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="currentColor" opacity=".35"/>')
        for name,(x,y) in nodes.items():
            svg.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="34" fill="none" stroke="currentColor"/><text x="{x:.0f}" y="{y+4:.0f}" text-anchor="middle" font-size="12">{html.escape(name)}</text>')
        svg.append('</svg>')
        table = ''
        for r in rows:
            state = '<span class="badge b-ok">managed</span>' if r.get("managed_neighbor") else '<span class="badge b-bad">UNMANAGED</span>'
            table += (f'<tr><td>{html.escape(r["device"])}</td><td>{html.escape(r.get("local_port", ""))}</td>'
                      f'<td>{html.escape(r.get("sys_name") or r.get("chassis_id") or "?")}</td>'
                      f'<td>{html.escape(r.get("port_id", ""))}</td><td>{html.escape(r.get("protocol", ""))}</td><td>{state}</td></tr>')
        action = ''
        if _can(sess["role"], "collect"):
            action = f'<form method=post action="/topology-discover">{self._csrf_field()}<button>Discover now</button></form>'
        inner = (f'<div class="panel"><div class="row"><div><b>{len(rows)}</b> neighbour observations · '
                 f'<b>{len(unmanaged)}</b> unmanaged</div><div>{action}</div></div>{"".join(svg)}</div>'
                 f'<div class="panel"><table><tr><th>Device</th><th>Local port</th><th>Neighbour</th><th>Remote port</th><th>Protocol</th><th>State</th></tr>'
                 f'{table or "<tr><td colspan=6 class=muted>No LLDP/CDP neighbours collected yet.</td></tr>"}</table></div>')
        self._send(self._page("Topology", inner, sess))

    def _do_topology_discover(self, form, sess):
        if not _can(sess["role"], "collect"):
            return self._send(self._page("Topology", '<div class="err">Not permitted.</div>', sess), 403)
        total = unmanaged = 0
        for d in self.manager.inv.all():
            if not d.get("snmp_version") and not d.get("secret_ref"):
                continue
            rows = self.manager.discover_neighbors(d["name"])
            total += len(rows); unmanaged += sum(1 for r in rows if r.get("unmanaged"))
        self.manager.db.audit(sess["username"], "topology_discover", "fleet", f"neighbors={total} unmanaged={unmanaged}")
        return self._redirect("/topology")

    def _do_baseline(self, form, sess, set_it):
        if not _can(sess["role"], "manage_devices"):
            return self._dashboard(sess, flash="Not permitted.")
        name = (form.get("name") or [""])[0]
        if set_it:
            self.manager.store.set_baseline(name)
            self.manager.db.audit(sess["username"], "baseline_set", name, "")
        else:
            self.manager.store.clear_baseline(name)
            self.manager.db.audit(sess["username"], "baseline_clear", name, "")
        return self._redirect(f"/device?name={_q(name)}")


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _snmp_poller(manager, interval, stop):
    """Background thread: while the console runs and the vault is unlocked, poll
    every SNMP-enabled device on an interval so live graphs keep updating without
    anyone clicking. Best-effort -- never dies on a poll error."""
    while not stop.is_set():
        stop.wait(interval)
        if stop.is_set():
            break
        try:
            if manager.vault_ready():
                manager.snmp_poll_all()
        except Exception:
            pass


def _check_writable(manager):
    """Warn loudly if the data dir / DB isn't writable by this process -- the most
    common cause of 'works for reads, dies on the first write' (e.g. unlock)."""
    home = str(manager.paths.home)
    try:
        probe = os.path.join(home, ".write-test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
    except OSError as e:
        print(f"  WARNING: data directory {home} is NOT writable by this user "
              f"({e.__class__.__name__}: {e}).", file=sys.stderr)
        print("           If files here are root-owned (from running the CLI as root), fix with:",
              file=sys.stderr)
        print(f"             sudo chown -R netconfig:netconfig {home}", file=sys.stderr)
        return
    # DB file specifically (WAL needs to write the db + -wal/-shm sidecars)
    try:
        manager.db.audit("system", "startup_write_check", "", "")
    except Exception as e:
        print(f"  WARNING: the database is not writable ({e.__class__.__name__}: {e}). "
              f"Check ownership of {home}/*.db* -- `sudo chown -R netconfig:netconfig {home}`.",
              file=sys.stderr)


def serve(manager, bind="127.0.0.1", port=8778):
    Console.manager = manager
    _check_writable(manager)
    master, master_source = service_master_password()
    if master and manager.vault.exists() and not manager.vault_ready():
        try:
            manager.unlock_vault(master)
            _obs_event("vault_service_unlock", source=master_source)
        except ValueError:
            _obs_event("vault_service_unlock_failed", source=master_source)
    stop = threading.Event()
    interval = int(manager.settings.get("snmp_poll_interval", 0) or 0)
    if interval > 0:
        threading.Thread(target=_snmp_poller, args=(manager, interval, stop),
                         daemon=True).start()
    Console.netflow = None
    if manager.settings.get("netflow_enabled"):
        try:
            from . import netflow as _nf
            col = _nf.Collector(bind="0.0.0.0",
                                port=int(manager.settings.get("netflow_port", 2055)),
                                max_flows=int(manager.settings.get("netflow_max_flows", 500)))
            col.start()
            Console.netflow = col
            print(f"  NetFlow collector: listening on udp/{col.port}")
        except Exception as e:
            print(f"  NetFlow collector NOT started: {e}", file=sys.stderr)
    Console.syslog = None
    if manager.settings.get("syslog_enabled"):
        try:
            from . import syslog_receiver as _syslog
            col = _syslog.Collector(manager,
                bind=manager.settings.get("syslog_bind", "0.0.0.0"),
                port=int(manager.settings.get("syslog_port", 5514)),
                queue_size=int(manager.settings.get("syslog_queue_size", 256)),
                debounce_seconds=int(manager.settings.get("syslog_debounce_seconds", 30)))
            col.start(); Console.syslog = col
            print(f"  Syslog collector: listening on udp/{col.port} (change-triggered collection)")
        except Exception as e:
            print(f"  Syslog collector NOT started: {e}", file=sys.stderr)
    digest_iv = int(manager.settings.get("digest_interval", 0) or 0)
    if digest_iv > 0:
        from . import digest as _digest
        threading.Thread(target=_digest.poller, args=(manager, digest_iv, stop), daemon=True).start()
        print(f"  Compliance/drift digest: every {digest_iv}s")
    mon_iv = int(manager.settings.get("monitor_poll_interval", 0) or 0)
    if mon_iv > 0:
        from . import monitor as _monitor
        threading.Thread(target=_monitor.poller, args=(manager, mon_iv, stop),
                         daemon=True).start()
        print(f"  Monitor poller: every {mon_iv}s (port/http/tls history + alerts)")
    httpd = _Server((bind, port), Console)
    tls_cert = (manager.settings.get("web_tls_cert") or "").strip()
    tls_key = (manager.settings.get("web_tls_key") or "").strip()
    if bool(tls_cert) != bool(tls_key):
        raise RuntimeError("built-in TLS requires both web_tls_cert and web_tls_key")
    scheme = "http"
    if tls_cert and tls_key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tls_cert, tls_key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        Console.tls_enabled = True
        scheme = "https"
    else:
        Console.tls_enabled = False
    print(f"NetConfig console on {scheme}://{bind}:{port}  (Ctrl-C to stop)")
    if interval > 0:
        print(f"  background SNMP poller: every {interval}s (vault must be unlocked)")
    if not Console.tls_enabled and bind not in ("127.0.0.1", "localhost", "::1"):
        print("  WARNING: bound to a non-local address over plain HTTP. "
              "Enable built-in TLS or front this with the WAF, or bind 127.0.0.1.")
    if manager.users.count() == 0:
        print("  No users yet \u2014 create the first admin: netconfig user add <name> --role admin")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    finally:
        stop.set()
        if Console.netflow: Console.netflow.stop()
        if Console.syslog: Console.syslog.stop()
        httpd.shutdown()
