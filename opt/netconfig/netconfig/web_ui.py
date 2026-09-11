"""Presentation helpers and static console assets for NetConfig.

PH-1 extracts presentation-only code from the HTTP dispatcher so routing,
security policy, and rendering can be tested independently.
"""

import hashlib
import html
import json
import os
import re
import time
import urllib.parse

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
[hidden]{display:none!important}
#charts{display:grid;grid-template-columns:repeat(2,max-content);gap:12px;justify-content:start;align-items:start}
.graph-card{border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--surface)}
.graph-head{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.graph-title{color:var(--navy)}
.graph-in{color:var(--ok)}
.graph-out{color:var(--warn)}
.graph-remove{margin-left:auto;padding:2px 10px}
.graph-svg{width:380px;height:200px;background:var(--surface);border:1px solid var(--border);border-radius:6px}
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
  function toggleTheme(){
    var next=root.getAttribute('data-theme')==='dark'?'light':'dark';
    localStorage.setItem(key,next); paint(next);
  }
  window.netconfigToggleTheme=toggleTheme;
  paint(preferred());
  document.addEventListener('DOMContentLoaded',function(){
    paint(root.getAttribute('data-theme')||preferred());
    var b=document.getElementById('theme-toggle');
    if(b) b.addEventListener('click',toggleTheme);
    document.addEventListener('submit',function(ev){
      var form=ev.target&&ev.target.closest?ev.target.closest('form[data-confirm]'):null;
      if(form&&!window.confirm(form.getAttribute('data-confirm')||'Confirm this action?')) ev.preventDefault();
    });
  });
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
        r.hidden=!match;
        if(match) shown++;
      });
      if(terms.length===0){ g.hidden=false; g.open=false; }
      else{ g.hidden=!shown; g.open=shown>0; }
      if(shown>0) anyVisible=true;
      var c=g.querySelector('.devcount');
      if(c) c.textContent=terms.length?(shown+' / '+rows.length):rows.length;
    });
    if(noRes) noRes.hidden=!(terms.length&&!anyVisible);
  }
  box.addEventListener('input',apply);
  apply();
})();
</script>"""

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
    rm.classList.add('graph-remove'); rm.onclick=function(){ removeChart(idx); };
    head.appendChild(rm); card.appendChild(head);
    var svg=el('svg',{viewBox:'0 0 '+W+' '+H,width:W,height:H,'class':'graph-svg'});
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
    document.getElementById('addrow').hidden = keys.length===0;
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


def apply_csp_nonce(document, nonce):
    """Prepare a rendered HTML document for strict CSP enforcement.

    Server-rendered ``style=`` attributes are converted to deterministic utility
    classes and emitted in one nonce-authorized style block. Every first-party
    ``script`` and ``style`` element receives the same per-response nonce. This
    lets the enforced policy reject inline event handlers and arbitrary style
    attributes while preserving the legacy console's visual output.
    """
    if not isinstance(document, str):
        return document
    safe_nonce = html.escape(str(nonce), quote=True)
    styles = {}

    def style_attr(match):
        full = match.group(0)
        style = html.unescape(match.group(1)).strip()
        if not style:
            return full.replace(match.group(0), "")
        class_name = "phs-" + hashlib.sha256(style.encode("utf-8")).hexdigest()[:12]
        styles[class_name] = style
        without = re.sub(r'\sstyle="[^"]*"', '', full, count=1, flags=re.IGNORECASE)
        quoted = re.search(r'\bclass="([^"]*)"', without, flags=re.IGNORECASE)
        if quoted:
            old = quoted.group(0)
            value = quoted.group(1).strip()
            return without.replace(old, f'class="{value} {class_name}"', 1)
        single = re.search(r"\bclass='([^']*)'", without, flags=re.IGNORECASE)
        if single:
            old = single.group(0)
            value = single.group(1).strip()
            return without.replace(old, f"class='{value} {class_name}'", 1)
        unquoted = re.search(r'\bclass=([^\s>]+)', without, flags=re.IGNORECASE)
        if unquoted:
            old = unquoted.group(0)
            value = unquoted.group(1).strip()
            return without.replace(old, f'class="{value} {class_name}"', 1)
        pos = without.rfind('>')
        return without[:pos] + f' class="{class_name}"' + without[pos:]

    # Match only actual start tags with a double-quoted style attribute. Script
    # contents do not contain literal style attributes after PH-1 JS cleanup.
    document = re.sub(r'<[^!/?][^<>]*?\sstyle="([^"]*)"[^<>]*?>', style_attr,
                      document, flags=re.IGNORECASE)
    if styles:
        css = ''.join(f'.{name}{{{decl}}}' for name, decl in sorted(styles.items()))
        block = f'<style nonce="{safe_nonce}" id="netconfig-rendered-styles">{css}</style>'
        if '</head>' in document.lower():
            document = re.sub(r'</head>', block + '</head>', document, count=1, flags=re.IGNORECASE)
        else:
            document = block + document
    document = re.sub(r'<script(?![^>]*\bnonce=)', f'<script nonce="{safe_nonce}"', document,
                      flags=re.IGNORECASE)
    document = re.sub(r'<style(?![^>]*\bnonce=)', f'<style nonce="{safe_nonce}"', document,
                      flags=re.IGNORECASE)
    return document


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



def render_protocols_page(handler, sess):
    """PH-3 structured-protocol profile table/form presentation."""
    rows=[]
    for dev in handler.manager.inv.all():
        prof=handler.manager.protocol_profiles.get(dev["name"]) or {}
        collect = ""
        if sess["role"] in {"operator","approver","admin"}:
            collect=(f'<form method=post action="/protocol-collect">{handler._csrf_field()}'
                     f'<input type=hidden name=device value="{html.escape(dev["name"])}">'
                     '<button class=ghost>Collect</button></form>')
        rows.append(f'<tr><td>{html.escape(dev["name"])}</td><td>{html.escape(prof.get("protocol","cli_ssh"))}</td>'
                    f'<td>{"yes" if prof.get("enabled") else "no"}</td><td>{html.escape(str(prof.get("port") or ""))}</td>'
                    f'<td>{"yes" if prof.get("allow_cli_fallback") else "no"}</td><td>{collect}</td></tr>')
    table=('<div class=panel><h2>Profiles</h2><table><tr><th>Device</th><th>Protocol</th><th>Enabled</th>'
           '<th>Port</th><th>CLI fallback</th><th>Action</th></tr>'+''.join(rows)+'</table></div>')
    if sess["role"] not in {"operator","approver","admin"}:
        return table
    opts=''.join(f'<option value="{html.escape(d["name"])}">{html.escape(d["name"])}</option>' for d in handler.manager.inv.all())
    form=(f'<div class=panel><h2>Set structured protocol profile</h2><form method=post action="/protocol-save">{handler._csrf_field()}'
          f'<div class=row><div><label>Device</label><select name=device>{opts}</select></div>'
          '<div><label>Protocol</label><select name=protocol><option>cli_ssh</option><option>netconf</option><option>restconf</option><option>gnmi</option></select></div>'
          '<div><label>Port (0=default)</label><input name=port value="0"></div></div>'
          '<div class=row><div><label>Vault secret ref (blank=device secret)</label><input name=secret_ref></div>'
          '<div><label>RESTCONF / gNMI read path</label><input name=path placeholder="/restconf/data?content=config or /interfaces"></div>'
          '<div><label>CA file</label><input name=ca_file placeholder="/etc/ssl/certs/vendor-ca.pem"></div></div>'
          '<label><input type=checkbox name=tls_verify value=1 checked> Verify TLS</label>'
          '<label><input type=checkbox name=allow_cli_fallback value=1> Explicitly allow CLI fallback</label>'
          '<button>Save profile</button></form></div>')
    return table+form
