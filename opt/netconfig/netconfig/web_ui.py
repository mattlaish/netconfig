"""Presentation helpers and static console assets for NetConfig.

PH-1 extracts presentation-only code from the HTTP dispatcher so routing,
security policy, and rendering can be tested independently.
"""

import hashlib
import html
import os
import re
import time
import urllib.parse

from .users import can as _can

_CSS = """
:root{
  --cg-font-sans:"Noto Sans","Noto Sans TC","Segoe UI","Microsoft JhengHei","PingFang TC",Arial,sans-serif;
  --cg-font-mono:"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  --cg-text:#17211c;
  --cg-text-muted:#617067;
  --cg-background:#f6f9f7;
  --cg-surface:#ffffff;
  --cg-border:#dce6e0;
  --cg-green:#247a4d;
  --cg-green-dark:#185c39;
  --cg-green-light:#eaf5ef;
  --cg-danger:#b42318;
  --cg-danger-light:#fdecea;
  --cg-warning:#8a5a00;
  --cg-warning-light:#fff6e5;
  --cg-info:#356b50;
  --cg-info-light:#edf5f0;
  --radius:10px;
  --shadow:0 10px 28px rgba(20, 48, 32, .07);
  --solid:var(--cg-green); --solid-hover:var(--cg-green-dark); --surface:var(--cg-surface);
  --text:var(--cg-text); --row-alt:#f8fbf9; --line:#e7efea; --red:var(--cg-danger);
  --red10:var(--cg-danger-light); --grey:var(--cg-text-muted); --border:var(--cg-border);
  --bg:var(--cg-background); --warn:var(--cg-warning); --warn10:var(--cg-warning-light);
  --ok:var(--cg-green); --ok10:var(--cg-green-light); --navy:var(--cg-green-dark);
  --navy90:var(--cg-info); --navy10:var(--cg-green-light); --font:var(--cg-font-sans); --mono:var(--cg-font-mono);
}
html[data-theme="dark"]{
  color-scheme:dark;
  --cg-text:#e8f2ec; --cg-text-muted:#aebdb3; --cg-background:#0f1712; --cg-surface:#18231d;
  --cg-border:#294035; --cg-green:#4bb57a; --cg-green-dark:#7dd39f; --cg-green-light:#1e3127;
  --cg-danger:#ff8c7d; --cg-danger-light:#432722; --cg-warning:#f0c36a; --cg-warning-light:#44361a;
  --cg-info:#6fb28d; --cg-info-light:#20342a; --shadow:none;
  --solid:#214f35; --solid-hover:#2c6946; --surface:var(--cg-surface); --text:var(--cg-text);
  --row-alt:#15201a; --line:#2a3d33; --red:var(--cg-danger); --red10:var(--cg-danger-light);
  --grey:var(--cg-text-muted); --border:var(--cg-border); --bg:var(--cg-background); --warn:var(--cg-warning);
  --warn10:var(--cg-warning-light); --ok:var(--cg-green-dark); --ok10:var(--cg-green-light);
  --navy:var(--cg-green-dark); --navy90:var(--cg-info); --navy10:var(--cg-green-light);
}
*{box-sizing:border-box;margin:0}
html,body{min-height:100vh}
body{background:var(--bg);color:var(--text);font-family:var(--font);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--navy);text-decoration:none}a:hover{text-decoration:underline}
button,input,select,textarea{font:inherit}
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid var(--cg-green);outline-offset:2px}
::selection{background:var(--cg-green-light);color:var(--cg-green-dark)}
[hidden]{display:none!important}
/* topbar */
header{display:flex;justify-content:space-between;align-items:center;gap:18px;background:var(--surface);border-bottom:1px solid var(--border);padding:14px 22px;position:sticky;top:0;z-index:30}
.brand{display:flex;align-items:center;gap:14px;color:var(--navy);font-weight:700;font-size:16px}
.brand .logo{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;background:var(--solid);color:#fff;border-radius:10px;font-weight:800;font-size:14px;letter-spacing:.04em;box-shadow:var(--shadow)}
.brand .appname{border-left:1px solid var(--border);padding-left:14px}
.brand span{color:var(--navy)}
.top-right{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-left:auto}
.who{color:var(--grey);font-size:13px;display:inline-flex;align-items:center;gap:6px}
.who b{color:var(--navy)}
.role{background:var(--navy10);color:var(--navy);border-radius:999px;padding:2px 8px;font-size:11px;font-weight:700;text-transform:uppercase}
.inline-form{display:inline;margin:0}
/* app shell */
.app-shell{display:grid;grid-template-columns:260px minmax(0,1fr);min-height:calc(100vh - 72px)}
.sidebar{background:var(--surface);border-right:1px solid var(--border);padding:18px 16px;position:sticky;top:69px;height:calc(100vh - 69px);overflow:auto}
.sidebar-section-title{font-size:12px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--grey);margin:4px 8px 10px}
.nav-sidebar{display:flex;flex-direction:column;gap:4px}
.nav-sidebar a{display:block;padding:10px 12px;border-radius:10px;color:var(--cg-text);font-size:14px;font-weight:600;border:1px solid transparent}
.nav-sidebar a:hover{background:var(--cg-green-light);color:var(--cg-green-dark);text-decoration:none}
.nav-sidebar a.active{background:var(--solid);color:#fff;box-shadow:var(--shadow)}
.content-shell{min-width:0;display:flex;flex-direction:column}
main{flex:1;max-width:none;margin:0;padding:24px 26px}
h1{color:var(--navy);font-size:28px;margin:0 0 18px;font-weight:800;letter-spacing:-.02em}
h2{color:var(--navy);font-size:15px;margin:0 0 10px;font-weight:700}
h3{color:var(--navy);font-size:14px;font-weight:700;margin:10px 0 6px}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px;margin-bottom:18px;box-shadow:var(--shadow)}
.sensor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px;margin-top:12px}
.sensor-card{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--grey);border-radius:10px;padding:14px;min-height:116px}
.sensor-card.ok{border-left-color:var(--ok)}.sensor-card.warn{border-left-color:var(--warn)}.sensor-card.bad{border-left-color:var(--red)}.sensor-card.dim{border-left-color:var(--grey)}
.sensor-head{display:flex;align-items:center;gap:8px;color:var(--navy);font-weight:700;font-size:13px;margin-bottom:8px}
.sensor-dot{width:10px;height:10px;border-radius:50%;background:var(--grey);box-shadow:0 0 0 3px rgba(97,112,103,.12);flex:0 0 auto}
.sensor-card.ok .sensor-dot{background:var(--ok);box-shadow:0 0 0 3px var(--ok10)}.sensor-card.warn .sensor-dot{background:var(--warn);box-shadow:0 0 0 3px var(--warn10)}.sensor-card.bad .sensor-dot{background:var(--red);box-shadow:0 0 0 3px var(--red10)}
.sensor-value{font-size:20px;font-weight:800;color:var(--text);line-height:1.2;margin-bottom:6px}.sensor-detail{font-size:12.5px;color:var(--grey)}
.ops-actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.ops-card{border:1px solid var(--border);border-radius:10px;padding:14px;background:var(--surface)}
.ops-card h3{margin-top:0}.ops-card p{margin:6px 0}.ops-advanced{margin-top:12px}
/* tables */
table{width:100%;border-collapse:separate;border-spacing:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;font-size:14px;box-shadow:var(--shadow)}
th,td{text-align:left;padding:9px 12px;vertical-align:top}
th{background:var(--solid);color:#fff;font-weight:600;font-size:13px}
td{border-top:1px solid var(--line)}
tbody tr:nth-child(even) td{background:var(--row-alt)}
/* badges */
.badge{display:inline-block;border-radius:999px;padding:2px 9px;font-size:11.5px;font-weight:700;background:var(--navy10);color:var(--navy);white-space:nowrap}
.b-ok{background:var(--ok10);color:var(--ok)}
.b-bad{background:var(--red10);color:var(--red)}
.b-chg{background:var(--warn10);color:var(--warn)}
.b-dim{background:var(--row-alt);color:var(--grey)}
.b-brass{background:var(--solid);color:#fff}
/* buttons */
button,.btn{display:inline-block;background:var(--solid);color:#fff;border:1px solid var(--solid);border-radius:10px;padding:8px 14px;font-family:var(--font);font-size:14px;font-weight:700;cursor:pointer;text-decoration:none}
button:hover,.btn:hover{background:var(--solid-hover);text-decoration:none}
button.ghost,.btn.ghost{background:var(--surface);border-color:var(--border);color:var(--grey)}
button.ghost:hover,.btn.ghost:hover{background:var(--navy10);color:var(--navy)}
button.danger{background:var(--surface);border-color:var(--red);color:var(--red)}
button.danger:hover{background:var(--red10)}
button:disabled{opacity:.5;cursor:not-allowed}
/* code / diff */
pre{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;overflow:auto;font:12.5px/1.5 var(--mono);color:var(--text);max-height:70vh}
code{background:var(--navy10);padding:1px 6px;border-radius:6px;font-size:.92em}
pre.diff .add{color:var(--ok);background:var(--ok10)}
pre.diff .del{color:var(--red);background:var(--red10)}
pre.diff .hdr{color:var(--navy);font-weight:700}
/* forms */
input,select,textarea{width:100%;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 12px;color:var(--text);font-size:14px;margin-bottom:12px;font-family:var(--font)}
input[type="checkbox"],input[type="radio"]{width:auto;margin:0 6px 0 0;padding:0;vertical-align:middle}
textarea{font-family:var(--mono);font-size:13px;min-height:120px}
input:focus,select:focus,textarea:focus{outline:2px solid var(--cg-green);outline-offset:1px;border-color:var(--cg-green)}
label{display:block;font-size:13px;color:var(--navy);font-weight:700;margin-bottom:4px}
/* notes */
.err{background:var(--red10);border:1px solid var(--red);padding:10px 12px;border-radius:10px;margin-bottom:12px;font-size:14px;color:var(--red)}
.muted{color:var(--grey);font-size:13px}
.right{text-align:right}
.row{display:flex;gap:16px;flex-wrap:wrap}.row>*{flex:1;min-width:220px}
.settings-shell{display:grid;grid-template-columns:220px minmax(0,1fr);gap:18px;align-items:start}
.settings-menu{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:8px;position:sticky;top:12px;box-shadow:var(--shadow)}
.settings-menu a{display:block;padding:10px 12px;border-radius:10px;color:var(--grey);font-size:14px;font-weight:600;margin:2px 0}
.settings-menu a:hover{background:var(--navy10);color:var(--navy);text-decoration:none}
.settings-menu a.active{background:var(--solid);color:#fff}
.settings-content .panel{margin-bottom:0}
.flash{background:var(--navy10);border:1px solid var(--border);padding:10px 14px;border-radius:10px;margin-bottom:14px;color:var(--navy);font-size:14px}
.vault-lock{background:var(--red10);border:1px solid var(--red);padding:6px 12px;border-radius:999px;color:var(--red);font-size:12px}
.vault-open{background:var(--ok10);border:1px solid var(--border);padding:6px 12px;border-radius:999px;color:var(--ok);font-size:12px;font-weight:700}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;background:var(--navy10);color:var(--navy)}
.sev-high{color:var(--red)}.sev-medium{color:var(--warn)}.sev-low{color:var(--grey)}
/* login */
.login-wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;background:var(--bg);padding:24px}
.login{width:420px;max-width:92vw;background:var(--surface);border:1px solid var(--border);border-top:4px solid var(--solid);border-radius:14px;padding:34px 38px;box-shadow:var(--shadow)}
.login .brand{display:flex;justify-content:center;color:var(--navy);font-size:18px;margin-bottom:4px}
.login .sub{text-align:center;color:var(--grey);font-size:12px;margin-bottom:22px;letter-spacing:.04em}
/* footer */
.footer{margin:0;padding:14px 26px;color:var(--grey);font-size:12px;border-top:1px solid var(--border);display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
html[data-theme="dark"] [data-idx],html[data-theme="dark"] [data-idx] svg{background:var(--surface)!important}
html[data-theme="dark"] [data-idx] svg text{fill:var(--grey)!important}
html[data-theme="dark"] [data-idx] svg line{stroke:var(--border)!important}
.theme-toggle{white-space:nowrap}
details>summary{cursor:pointer;color:var(--navy);padding:4px 0}
details[open]>summary{margin-bottom:8px}
#charts{display:grid;grid-template-columns:repeat(2,max-content);gap:12px;justify-content:start;align-items:start}
.graph-card{border:1px solid var(--border);border-radius:10px;padding:10px;background:var(--surface)}
.graph-head{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.graph-title{color:var(--navy)}
.graph-in{color:var(--ok)}
.graph-out{color:var(--warn)}
.graph-in-line{stroke:var(--ok)}.graph-out-line{stroke:var(--warn)}
.graph-remove{margin-left:auto;padding:2px 10px}
.graph-svg{width:380px;height:200px;background:var(--surface);border:1px solid var(--border);border-radius:10px}

/* interactive topology */
.topology-shell{position:relative;min-height:560px;border:1px solid var(--border);border-radius:12px;background:var(--surface);overflow:hidden;touch-action:none}
.topology-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.topology-toolbar .topology-actions{display:flex;gap:8px;flex-wrap:wrap}.topology-toolbar .topology-actions button{width:auto;margin:0}
#topology-canvas{display:block;width:100%;height:560px;min-height:420px;cursor:grab;user-select:none;touch-action:none;background:radial-gradient(circle at 1px 1px,var(--line) 1px,transparent 1px);background-size:22px 22px}
#topology-canvas.is-panning{cursor:grabbing}.topology-node{cursor:grab}.topology-node.dragging{cursor:grabbing}
.topology-node circle{fill:var(--surface);stroke:var(--grey);stroke-width:2.5;vector-effect:non-scaling-stroke}
.topology-node.state-observed circle{stroke:var(--ok)}.topology-node.state-inferred circle{stroke:var(--warn)}.topology-node.state-unknown circle{stroke:var(--grey);stroke-dasharray:5 4}
.topology-node text{fill:var(--text);font-family:var(--font);pointer-events:none}.topology-node .topology-node-name{font-size:13px;font-weight:800}.topology-node .topology-node-sub{font-size:10px;fill:var(--grey)}
.topology-edge{vector-effect:non-scaling-stroke;stroke-width:2}.topology-edge.observed{stroke:var(--ok);opacity:.72}.topology-edge.inferred{stroke:var(--warn);opacity:.65;stroke-dasharray:7 5}
.topology-legend{display:flex;align-items:center;gap:14px;flex-wrap:wrap;color:var(--grey);font-size:12px}.topology-legend span{display:inline-flex;align-items:center;gap:6px}.topology-swatch{display:inline-block;width:24px;border-top:2px solid var(--ok)}.topology-swatch.inferred{border-top-color:var(--warn);border-top-style:dashed}.topology-swatch.unknown{width:12px;height:12px;border:2px dashed var(--grey);border-radius:50%}
.topology-note{margin-top:8px;color:var(--grey);font-size:12px}.topology-evidence-table .badge{min-width:72px;text-align:center}

@media(max-width:980px){
  .app-shell{grid-template-columns:1fr}
  .sidebar{position:static;height:auto;border-right:none;border-bottom:1px solid var(--border);padding:16px}
  .nav-sidebar{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:6px}
  main{padding:20px 16px}.footer{padding:14px 16px}
  .settings-shell{grid-template-columns:1fr}.settings-menu{position:static;display:flex;gap:4px;overflow-x:auto}.settings-menu a{white-space:nowrap}
}
@media(max-width:760px){
  header{padding:12px 16px;flex-wrap:wrap}
  .brand{min-width:0}.brand .appname{overflow-wrap:anywhere}
  .top-right{width:100%}
  .brand .appname{border-left:none;padding-left:0}
  h1{font-size:24px}
  table{display:block;max-width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .help code{white-space:normal!important;overflow-wrap:anywhere;word-break:break-word}
  #charts{grid-template-columns:1fr}.graph-svg{width:100%}
}
@media (prefers-reduced-motion: reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation-duration:0.01ms!important;animation-iteration-count:1!important}}
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

_TOPOLOGY_JS = r"""<script>
(function(){
  var svg=document.getElementById('topology-canvas');
  if(!svg) return;
  var viewport=document.getElementById('topology-viewport');
  var nodeEls=[].slice.call(svg.querySelectorAll('.topology-node'));
  var edgeEls=[].slice.call(svg.querySelectorAll('.topology-edge'));
  var key='netconfig-topology-layout-v1';
  var panX=0, panY=0, zoom=1, drag=null, pan=null;
  function saved(){try{return JSON.parse(localStorage.getItem(key)||'{}')||{};}catch(e){return {};}}
  var layout=saved();
  function pos(el){return {x:parseFloat(el.dataset.x||el.dataset.defaultX||'0'),y:parseFloat(el.dataset.y||el.dataset.defaultY||'0')};}
  function setPos(el,x,y,remember){
    el.dataset.x=String(x); el.dataset.y=String(y);
    el.setAttribute('transform','translate('+x+' '+y+')');
    if(remember){layout[el.dataset.node]={x:x,y:y};try{localStorage.setItem(key,JSON.stringify(layout));}catch(e){}}
  }
  function updateEdges(){
    var by={}; nodeEls.forEach(function(n){by[n.dataset.node]=pos(n);});
    edgeEls.forEach(function(e){var a=by[e.dataset.from],b=by[e.dataset.to];if(!a||!b)return;e.setAttribute('x1',a.x);e.setAttribute('y1',a.y);e.setAttribute('x2',b.x);e.setAttribute('y2',b.y);});
  }
  function setViewport(){viewport.setAttribute('transform','translate('+panX+' '+panY+') scale('+zoom+')');}
  function worldPoint(ev){var pt=svg.createSVGPoint();pt.x=ev.clientX;pt.y=ev.clientY;var ctm=viewport.getScreenCTM();return ctm?pt.matrixTransform(ctm.inverse()):pt;}
  nodeEls.forEach(function(n){
    var st=layout[n.dataset.node];
    var x=st&&isFinite(st.x)?st.x:parseFloat(n.dataset.defaultX||'0');
    var y=st&&isFinite(st.y)?st.y:parseFloat(n.dataset.defaultY||'0');
    setPos(n,x,y,false);
    n.addEventListener('pointerdown',function(ev){ev.preventDefault();ev.stopPropagation();var p=worldPoint(ev),q=pos(n);drag={el:n,dx:q.x-p.x,dy:q.y-p.y,id:ev.pointerId};n.classList.add('dragging');svg.setPointerCapture(ev.pointerId);});
  });
  svg.addEventListener('pointerdown',function(ev){
    if(ev.target.closest&&ev.target.closest('.topology-node')) return;
    ev.preventDefault();pan={id:ev.pointerId,x:ev.clientX,y:ev.clientY,px:panX,py:panY};svg.classList.add('is-panning');svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener('pointermove',function(ev){
    if(drag&&drag.id===ev.pointerId){var p=worldPoint(ev);setPos(drag.el,p.x+drag.dx,p.y+drag.dy,false);updateEdges();return;}
    if(pan&&pan.id===ev.pointerId){panX=pan.px+(ev.clientX-pan.x);panY=pan.py+(ev.clientY-pan.y);setViewport();}
  });
  function finish(ev){
    if(drag&&drag.id===ev.pointerId){var q=pos(drag.el);setPos(drag.el,q.x,q.y,true);drag.el.classList.remove('dragging');drag=null;updateEdges();}
    if(pan&&pan.id===ev.pointerId){pan=null;svg.classList.remove('is-panning');}
    try{svg.releasePointerCapture(ev.pointerId);}catch(e){}
  }
  svg.addEventListener('pointerup',finish);svg.addEventListener('pointercancel',finish);
  svg.addEventListener('wheel',function(ev){ev.preventDefault();var next=Math.max(.45,Math.min(2.5,zoom*(ev.deltaY<0?1.12:.89)));zoom=next;setViewport();},{passive:false});
  var reset=document.getElementById('topology-reset');if(reset)reset.addEventListener('click',function(){layout={};try{localStorage.removeItem(key);}catch(e){}nodeEls.forEach(function(n){setPos(n,parseFloat(n.dataset.defaultX||'0'),parseFloat(n.dataset.defaultY||'0'),false);});panX=0;panY=0;zoom=1;setViewport();updateEdges();});
  var fit=document.getElementById('topology-fit');if(fit)fit.addEventListener('click',function(){panX=0;panY=0;zoom=1;setViewport();});
  setViewport();updateEdges();
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
  color:var(--grey);transition:transform .15s}
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
      if(c) c.textContent=terms.length?(shown+' / '+rows.length):
          rows.length;
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
    function poly(i2,cls){ var dd=''; p.forEach(function(r){ var v=r[i2]||0; dd+=(dd?' L':'M')+X(r[0]).toFixed(1)+' '+Y(v).toFixed(1); });
      svg.appendChild(el('path',{d:dd,fill:'none','class':cls,'stroke-width':2})); }
    poly(1,'graph-in-line'); poly(2,'graph-out-line');
    var last=p[p.length-1];
    card.querySelector('.cin').textContent=fmt(last[1]);
    card.querySelector('.cout').textContent=fmt(last[2]);
  }
  function addChart(idx){
    if(!idx||monitored.indexOf(idx)>=0) return;
    monitored.push(idx);
    var card=document.createElement('div'); card.setAttribute('data-idx',idx); card.className='graph-card';
    var head=document.createElement('div'); head.className='graph-head';
    head.innerHTML='<b class="graph-title">'+descrOf(idx)+'</b><span class="muted">in <b class="cin graph-in">-</b> \u00b7 out <b class="cout graph-out">-</b></span>';
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
            out.append(f'<div class="muted" style="border-left:3px solid var(--warn);'
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



def render_sidebar_nav(links, current_path=""):
    cur = urllib.parse.urlsplit(current_path or "")
    path_only = cur.path or "/"
    tab = urllib.parse.parse_qs(cur.query).get("tab", [""])[0]

    def active(url):
        if url == "/operations?tab=intelligence":
            return path_only == "/operations" and tab == "intelligence"
        if url == "/operations":
            return path_only == "/operations" and tab != "intelligence"
        if url == "/requests":
            return path_only == "/requests" or path_only.startswith("/request")
        if url == "/vault":
            return path_only.startswith("/vault")
        return path_only == (urllib.parse.urlsplit(url).path or "/")

    items = [f'<a{" class=\"active\"" if active(url) else ""} href="{url}">{html.escape(label)}</a>'
             for url, label in links]
    return '<div class="sidebar-section-title">Navigation</div><nav class="nav-sidebar">' + "".join(items) + "</nav>"


def _sensor_card(title, state, value, detail):
    state = state if state in {"ok", "warn", "bad", "dim"} else "dim"
    return (f'<div class="sensor-card {state}"><div class="sensor-head"><span class="sensor-dot"></span>'
            f'{html.escape(str(title))}</div><div class="sensor-value">{html.escape(str(value))}</div>'
            f'<div class="sensor-detail">{html.escape(str(detail))}</div></div>')


def _mib_truth(value):
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "enabled", "enable", "detected", "active", "on"}:
        return True
    if text in {"2", "0", "false", "no", "disabled", "disable", "clear", "normal", "off"}:
        return False
    return None


def render_snmp_health_summary(handler, device, dev, fx):
    """Render operator health from the canonical SensorEngine snapshot only."""
    # MC-1 contract: this renderer is consumption-only.  It must not refresh
    # sensors or read raw collection tables to recompute health semantics.
    sensors = handler.manager.sensors.list(device=device, limit=2000)
    by_type = {}
    for sensor in sensors:
        by_type.setdefault(sensor.get("sensor_type"), []).append(sensor)

    def first(sensor_type):
        rows = by_type.get(sensor_type, [])
        return rows[0] if rows else None

    def card_state(status):
        return {
            "OK": "ok",
            "WARNING": "warn",
            "CRITICAL": "bad",
            "UNKNOWN": "dim",
        }.get(str(status or "UNKNOWN").upper(), "dim")

    def worst_status(rows):
        rank = {"UNKNOWN": 0, "OK": 1, "WARNING": 2, "CRITICAL": 3}
        if not rows:
            return "UNKNOWN"
        return max(
            (str(row.get("status") or "UNKNOWN").upper() for row in rows),
            key=lambda value: rank.get(value, 0),
        )

    def sensor_detail(sensor, fallback=""):
        if not sensor:
            return fallback
        message = str(sensor.get("message") or "").strip()
        if message:
            return message
        updated = sensor.get("updated_at")
        return f'Updated: {_fmt_ts(updated)}' if updated else fallback

    cards = []

    reachability = first("device.reachability")
    if reachability:
        value = str(reachability.get("value") or "").strip().lower()
        if value == "reachable":
            display = "Reachable"
        elif value == "unreachable":
            display = "Unreachable"
        else:
            display = "Unknown"
        cards.append(_sensor_card(
            "Reachability", card_state(reachability.get("status")), display,
            sensor_detail(reachability, "No reachability observation collected")))
    else:
        cards.append(_sensor_card(
            "Reachability", "dim", "No data", "No canonical reachability Sensor available"))

    polling = first("device.polling")
    if polling:
        value = str(polling.get("value") or "").strip().lower()
        display = "Healthy" if value == "healthy" else ("Error" if value == "error" else "Unknown")
        cards.append(_sensor_card(
            "SNMP polling", card_state(polling.get("status")), display,
            sensor_detail(polling, "No poll observation collected")))
    else:
        cards.append(_sensor_card(
            "SNMP polling", "dim", "Not polled", "No canonical polling Sensor available"))

    interface_status = by_type.get("interface.status", [])
    interface_errors = by_type.get("interface.errors", [])
    interface_util = by_type.get("interface.utilization", [])
    if interface_status:
        real_rows = [row for row in interface_status if str(row.get("resource") or "")]
        rows = real_rows or interface_status
        total = len(real_rows)
        if not real_rows and len(interface_status) == 1 and interface_status[0].get("status") == "UNKNOWN":
            total = 0
        ok_count = sum(1 for row in real_rows if row.get("status") == "OK")
        warning_count = sum(1 for row in real_rows if row.get("status") == "WARNING")
        critical_count = sum(1 for row in real_rows if row.get("status") == "CRITICAL")
        unknown_count = sum(1 for row in real_rows if row.get("status") == "UNKNOWN")
        combined = interface_status + interface_errors + interface_util
        state = card_state(worst_status(combined))
        if total:
            value = f"{ok_count}/{total} healthy"
            detail = (f"{warning_count} warning · {critical_count} critical · "
                      f"{unknown_count} unknown")
        else:
            value = "No data"
            detail = sensor_detail(interface_status[0], "No interface evidence collected")
        cards.append(_sensor_card("Interface health", state, value, detail))
    else:
        cards.append(_sensor_card(
            "Interface health", "dim", "No data", "No canonical interface Sensors available"))

    fdb = first("endpoint.fdb_evidence")
    if fdb:
        raw = str(fdb.get("value") or "").strip()
        value = f"{raw} MACs" if raw else "No local evidence"
        cards.append(_sensor_card(
            "FDB / MAC learning", card_state(fdb.get("status")), value,
            sensor_detail(fdb, "No forwarding evidence collected")))
    else:
        cards.append(_sensor_card(
            "FDB / MAC learning", "dim", "No data", "No canonical FDB/MAC Sensor available"))

    l3 = first("endpoint.arp_evidence")
    if l3:
        raw = str(l3.get("value") or "").strip()
        value = f"{raw} entries" if raw else "No local evidence"
        cards.append(_sensor_card(
            "ARP / IP neighbor", card_state(l3.get("status")), value,
            sensor_detail(l3, "No ARP/IP-neighbor evidence collected")))
    else:
        cards.append(_sensor_card(
            "ARP / IP neighbor", "dim", "No data", "No canonical L3 evidence Sensor available"))

    topology = first("topology.neighbor")
    managed = first("topology.managed_neighbor_count")
    unmanaged = first("topology.unmanaged_neighbor_count")
    if topology:
        raw = str(topology.get("value") or "").strip()
        value = f"{raw} observed" if raw else "No local evidence"
        detail_bits = []
        if managed and str(managed.get("value") or "").strip():
            detail_bits.append(f'{managed.get("value")} managed')
        if unmanaged and str(unmanaged.get("value") or "").strip():
            detail_bits.append(f'{unmanaged.get("value")} unmanaged')
        detail = " · ".join(detail_bits) or sensor_detail(topology, "No LLDP/CDP evidence collected")
        cards.append(_sensor_card(
            "Topology neighbors", card_state(topology.get("status")), value, detail))
    else:
        cards.append(_sensor_card(
            "Topology neighbors", "dim", "No data", "No canonical topology Sensor available"))

    loop = first("loop_protection.health")
    if loop:
        message = str(loop.get("message") or "")
        enabled_match = re.search(r"Enabled ports=([^ ]+)", message)
        detected_match = re.search(r"Loop detected=(\d+)", message)
        history_match = re.search(r"Ports with loop history=(\d+)", message)
        last_match = re.search(r"Ports with recorded last event=(\d+)", message)
        detected = int(detected_match.group(1)) if detected_match else None
        if detected is None:
            value = "Loop status available"
        elif detected:
            value = f"Loop detected: {detected}"
        else:
            value = "No loop detected"
        detail_bits = []
        if enabled_match:
            detail_bits.append(f"Enabled ports: {enabled_match.group(1)}")
        if history_match:
            detail_bits.append(f"Ports with loop history: {history_match.group(1)}")
        if last_match:
            detail_bits.append(f"Ports with recorded last event: {last_match.group(1)}")
        cards.append(_sensor_card(
            "Loop Protection", card_state(loop.get("status")), value,
            " · ".join(detail_bits) or sensor_detail(loop, "Mapped Loop Protection evidence")))
    else:
        cards.append(_sensor_card(
            "Loop Protection", "dim", "No mapped data", "No mapped Loop Protection Sensor available"))

    health_panel = ('<div class="panel"><h2>Device health</h2>'
                    '<p class="muted">Status cards are derived from canonical Sensors generated from already-collected DB/cache data only. Opening this page does not add polling or device I/O.</p>'
                    f'<div class="sensor-grid">{"".join(cards)}</div></div>')

    # MC-2: history is read from durable Sensor transitions only.  Rendering the
    # timeline must not trigger collection or mutate Sensor state.
    transitions = handler.manager.sensors.transitions(device=device, limit=12)
    if transitions:
        badge_class = {
            "OK": "b-ok",
            "WARNING": "b-chg",
            "CRITICAL": "b-bad",
            "UNKNOWN": "b-dim",
        }
        rows = []
        for item in transitions:
            previous = str(item.get("previous_status") or "UNKNOWN").upper()
            current = str(item.get("new_status") or "UNKNOWN").upper()
            resource = str(item.get("resource") or "").strip()
            target = html.escape(str(item.get("sensor_type") or "Sensor"))
            if resource:
                target += f' <span class="muted">· {html.escape(resource)}</span>'
            rows.append(
                '<tr>'
                f'<td>{html.escape(_fmt_ts(item.get("observed_at")))}</td>'
                f'<td>{target}</td>'
                f'<td><span class="badge {badge_class.get(previous, "b-dim")}">{html.escape(previous)}</span></td>'
                '<td>→</td>'
                f'<td><span class="badge {badge_class.get(current, "b-dim")}">{html.escape(current)}</span></td>'
                '</tr>'
            )
        history_panel = (
            '<div class="panel"><h2>Recent sensor changes</h2>'
            '<p class="muted">Latest durable Sensor state transitions for this device. UNKNOWN means evidence is unavailable, not a failure verdict.</p>'
            '<div class="table-wrap"><table><thead><tr><th>Time</th><th>Sensor / resource</th>'
            '<th>From</th><th></th><th>To</th></tr></thead><tbody>'
            + ''.join(rows) + '</tbody></table></div></div>'
        )
    else:
        history_panel = (
            '<div class="panel"><h2>Recent sensor changes</h2>'
            '<p class="muted">No Sensor state transitions have been recorded for this device yet.</p></div>'
        )

    return health_panel + history_panel

def render_topology_page(handler, q, sess):
    rows = handler.manager.db.get_neighbors()
    identities = handler.manager.topology_identities()
    graph = handler.manager.topology_graph()
    graph_nodes = graph.get("nodes", [])
    graph_edges = graph.get("edges", [])
    summary = graph.get("summary", {})
    unmanaged = [r for r in rows if r.get("resolution_state") == "UNMANAGED" or (not r.get("managed_neighbor") and not r.get("resolution_state"))]
    ambiguous = [r for r in rows if r.get("resolution_state") == "AMBIGUOUS"]

    # Deterministic initial positions; browser-local drag positions override
    # these without changing topology truth or any persisted network state.
    import math
    positions = {}
    count = max(1, len(graph_nodes))
    for i, node in enumerate(graph_nodes):
        angle = (2 * math.pi * i / count) - math.pi / 2
        positions[node["device"]] = (500 + 340 * math.cos(angle), 310 + 225 * math.sin(angle))

    svg = ['<div class="topology-shell"><svg id="topology-canvas" viewBox="0 0 1000 620" role="img" aria-label="Interactive managed network topology"><g id="topology-viewport">']
    for edge in graph_edges:
        src = edge.get("from", ""); dst = edge.get("to", "")
        if src not in positions or dst not in positions:
            continue
        x1, y1 = positions[src]; x2, y2 = positions[dst]
        kind = "observed" if edge.get("evidence_kind") == "OBSERVED" else "inferred"
        title = (f'{edge.get("evidence_kind", "")} {src} {edge.get("local_port", "")} → '
                 f'{dst} {edge.get("remote_port", "")} · {edge.get("protocol", "")} · '
                 f'{edge.get("evidence", "")}')
        svg.append(
            f'<line class="topology-edge {kind}" data-from="{html.escape(src, quote=True)}" '
            f'data-to="{html.escape(dst, quote=True)}" x1="{x1:.1f}" y1="{y1:.1f}" '
            f'x2="{x2:.1f}" y2="{y2:.1f}"><title>{html.escape(title)}</title></line>')
    for node in graph_nodes:
        name = node.get("device", ""); x, y = positions[name]
        state = str(node.get("state", "UNKNOWN")).lower()
        host = str(node.get("host", "") or "")
        sub = host or str(node.get("sys_name", "") or "") or state.upper()
        title = f'{name} · {host or "no host"} · adjacency {state.upper()}'
        svg.append(
            f'<g class="topology-node state-{html.escape(state)}" tabindex="0" '
            f'data-node="{html.escape(name, quote=True)}" data-default-x="{x:.1f}" data-default-y="{y:.1f}" '
            f'data-x="{x:.1f}" data-y="{y:.1f}" transform="translate({x:.1f} {y:.1f})">'
            f'<title>{html.escape(title)}</title><circle r="48"></circle>'
            f'<text class="topology-node-name" text-anchor="middle" y="-3">{html.escape(name)}</text>'
            f'<text class="topology-node-sub" text-anchor="middle" y="16">{html.escape(sub[:28])}</text></g>')
    svg.append('</g></svg></div>')

    evidence_rows = ''
    for edge in graph_edges:
        observed = edge.get("evidence_kind") == "OBSERVED"
        badge = '<span class="badge b-ok">OBSERVED</span>' if observed else '<span class="badge b-chg">INFERRED</span>'
        evidence_rows += (
            f'<tr><td>{badge}</td><td>{html.escape(edge.get("from", ""))}</td>'
            f'<td>{html.escape(edge.get("local_port", ""))}</td><td>{html.escape(edge.get("to", ""))}</td>'
            f'<td>{html.escape(edge.get("remote_port", ""))}</td><td>{html.escape(edge.get("protocol", ""))}</td>'
            f'<td>{html.escape(edge.get("confidence", ""))}</td><td class="muted">{html.escape(edge.get("evidence", ""))}</td></tr>')

    raw_rows = ''
    for r in rows:
        if r.get("managed_neighbor"):
            state = '<span class="badge b-ok">resolved</span>'
        elif r.get("resolution_state") == "AMBIGUOUS":
            state = '<span class="badge b-bad">AMBIGUOUS</span>'
        else:
            state = '<span class="badge b-bad">UNMANAGED</span>'
        raw_rows += (f'<tr><td>{html.escape(r["device"])}</td><td>{html.escape(r.get("local_port", ""))}</td>'
                     f'<td>{html.escape(r.get("sys_name") or r.get("chassis_id") or "?")}</td>'
                     f'<td>{html.escape(r.get("port_id", ""))}</td><td>{html.escape(r.get("protocol", ""))}</td><td>{state}</td>'
                     f'<td class="muted">{html.escape(r.get("resolution_evidence", ""))}</td></tr>')
    identity_rows = ''
    for r in identities:
        chassis = r.get("chassis_serial") or r.get("chassis_mac") or r.get("chassis_id") or ""
        identity_rows += (f'<tr><td>{html.escape(r.get("device", ""))}</td><td>{html.escape(r.get("sys_name", ""))}</td>'
                          f'<td>{html.escape(chassis)}</td><td>{html.escape(r.get("chassis_model", ""))}</td>'
                          f'<td>{html.escape(r.get("sys_cap_enabled", ""))}</td><td>{len(r.get("interfaces") or [])}</td></tr>')
    root = (q.get("impact_device") or [""])[0].strip()
    root_port = (q.get("impact_port") or [""])[0].strip()
    impact_html = '<p class="muted">Choose a managed root device to inspect observed downstream L2 impact.</p>'
    if root:
        try:
            impact = handler.manager.downstream_impact(root, root_port or None)
            items = ''.join(f'<li>depth {int(x["depth"])} — {html.escape(x["device"])} via {html.escape(x["via"])}</li>' for x in impact["devices"])
            impact_html = (f'<p><b>{impact["device_count"]}</b> downstream managed device(s), '
                           f'<b>{impact["edge_count"]}</b> observed edge(s).</p><ul>{items or "<li>None</li>"}</ul>'
                           f'<p class="muted">Scope: observed managed L2 adjacency only; inferred FDB paths are deliberately excluded.</p>')
        except ValueError as exc:
            impact_html = f'<div class="err">{html.escape(str(exc))}</div>'
    impact_opts = ['<option value="">Select root…</option>']
    for d in handler.manager.inv.all():
        name = d.get("name", "")
        sel = " selected" if name == root else ""
        impact_opts.append(f'<option value="{html.escape(name)}"{sel}>{html.escape(name)}</option>')
    action = ''
    if _can(sess["role"], "collect"):
        action = f'<form method=post action="/topology-discover">{handler._csrf_field()}<button>Discover now</button></form>'
    toolbar = (f'<div class="topology-toolbar"><div><b>{int(summary.get("managed_nodes", 0))}</b> managed nodes · '
               f'<b>{int(summary.get("observed_edges", 0))}</b> observed edges · '
               f'<b>{int(summary.get("inferred_edges", 0))}</b> inferred FDB paths · '
               f'<b>{int(summary.get("unknown_nodes", 0))}</b> without adjacency evidence</div>'
               f'<div class="topology-actions"><button type="button" class="ghost" id="topology-fit">Reset view</button>'
               f'<button type="button" class="ghost" id="topology-reset">Reset layout</button>{action}</div></div>')
    legend = ('<div class="topology-legend"><span><i class="topology-swatch"></i>OBSERVED LLDP/CDP</span>'
              '<span><i class="topology-swatch inferred"></i>INFERRED FDB path</span>'
              '<span><i class="topology-swatch unknown"></i>No adjacency evidence</span></div>'
              '<p class="topology-note">Drag nodes to arrange the canvas. Wheel to zoom; drag empty space to pan. Layout is stored only in this browser and never changes network truth.</p>')
    inner = (f'<div class="panel">{toolbar}{legend}{"".join(svg)}</div>{_TOPOLOGY_JS}'
             f'<div class="panel topology-evidence-table"><h3>Topology evidence</h3><table><tr><th>Evidence</th><th>From</th><th>Local port</th><th>To</th><th>Remote port</th><th>Protocol</th><th>Confidence</th><th>Evidence detail</th></tr>'
             f'{evidence_rows or "<tr><td colspan=8 class=muted>No managed adjacency/path evidence yet. Managed devices still remain visible above.</td></tr>"}</table>'
             f'<p class="muted">FDB matches indicate reachability through a port, not guaranteed direct physical adjacency. Only LLDP/CDP OBSERVED edges are traversed by downstream-impact analysis.</p></div>'
             f'<div class="panel"><h3>Managed identity</h3><table><tr><th>Device</th><th>sysName</th><th>Chassis identity</th><th>Model</th><th>Capabilities</th><th>Interfaces</th></tr>'
             f'{identity_rows or "<tr><td colspan=6 class=muted>No normalized identity collected yet.</td></tr>"}</table></div>'
             f'<div class="panel"><h3>Downstream impact</h3><form method=get action="/topology"><select name=impact_device>{"".join(impact_opts)}</select> '
             f'<input name=impact_port value="{html.escape(root_port)}" placeholder="optional root port"> <button class="ghost">Analyze</button></form>{impact_html}</div>'
             f'<details class="panel"><summary>Raw LLDP/CDP observations · {len(rows)} rows · {len(unmanaged)} unmanaged · {len(ambiguous)} ambiguous</summary>'
             f'<table><tr><th>Device</th><th>Local port</th><th>Neighbour</th><th>Remote port</th><th>Protocol</th><th>State</th><th>Resolution evidence</th></tr>'
             f'{raw_rows or "<tr><td colspan=7 class=muted>No LLDP/CDP neighbours collected yet.</td></tr>"}</table></details>')
    return inner



def render_events_page(handler, q, sess):
        device = (q.get("device") or [""])[0]
        domain = str((q.get("domain") or [""])[0] or "").upper()
        rows = handler.manager.events.list(limit=500, device=device or None, domain=domain or None)
        options = '<option value="">All devices</option>' + ''.join(
            f'<option value="{html.escape(d["name"])}"{" selected" if device==d["name"] else ""}>{html.escape(d["name"])}</option>'
            for d in handler.manager.inv.all())
        domains = ["", "NETWORK", "SECURITY", "APPLICATION", "DATABASE", "STORAGE",
                   "SYSTEM", "CONFIGURATION", "IDENTITY", "EXTERNAL"]
        domain_options = ''.join(
            f'<option value="{html.escape(x)}"{" selected" if domain==x else ""}>{html.escape(x or "All domains")}</option>'
            for x in domains)

        body_rows = ""
        for r in rows:
            sup = '<span class="badge b-dim">suppressed</span>' if r.get("suppressed") else ''
            event_id = int(r.get("id") or 0)
            entity = r.get("entity_id") or r.get("device") or r.get("source") or "-"
            resource = r.get("resource") or r.get("interface") or "-"
            body_rows += (f'<tr><td class=muted>{_fmt_ts(r.get("observed_at") or r.get("last_ts"))}</td>'
                f'<td>{html.escape(r.get("domain", ""))}</td>'
                f'<td>{html.escape(r.get("severity", ""))}</td>'
                f'<td><a href="/events?id={event_id}"><b>{html.escape(r.get("event_type", ""))}</b></a></td>'
                f'<td>{html.escape(r.get("entity_type") or "-")}:{html.escape(str(entity))}</td>'
                f'<td>{html.escape(str(resource))}</td><td>{html.escape(r.get("status") or "-")}</td>'
                f'<td>{r.get("event_count",1)}</td><td>{sup}</td></tr>')

        detail = ""
        event_id_raw = str((q.get("id") or [""])[0] or "")
        if event_id_raw.isdigit():
            event = handler.manager.events.get(int(event_id_raw))
            if event:
                related = handler.manager.events.related_sensor(event)
                related_html = '<span class="muted">No related current Sensor.</span>'
                if related:
                    related_html = (
                        f'<span class="badge {{"OK":"b-ok","WARNING":"b-chg","CRITICAL":"b-bad","UNKNOWN":"b-dim"}}.get(str(related.get("status") or "UNKNOWN").upper(), "b-dim")">'
                        f'{html.escape(str(related.get("status") or "UNKNOWN"))}</span> '
                        f'{html.escape(str(related.get("sensor_type") or ""))}'
                        + (f' · {html.escape(str(related.get("resource") or ""))}' if related.get("resource") else '')
                    )
                detail = (
                    f'<div class="panel"><h2>Event #{int(event["id"])} · {html.escape(str(event.get("event_type") or ""))}</h2>'
                    '<div class="kv-grid">'
                    f'<div><span class="muted">Domain</span><b>{html.escape(str(event.get("domain") or ""))}</b></div>'
                    f'<div><span class="muted">Source</span><b>{html.escape(str(event.get("source_type") or ""))} · {html.escape(str(event.get("source") or "-"))}</b></div>'
                    f'<div><span class="muted">Affected entity</span><b>{html.escape(str(event.get("entity_type") or "unknown"))}:{html.escape(str(event.get("entity_id") or "-"))}</b></div>'
                    f'<div><span class="muted">Resource</span><b>{html.escape(str(event.get("resource") or "-"))}</b></div>'
                    f'<div><span class="muted">Status / severity</span><b>{html.escape(str(event.get("status") or "OBSERVED"))} / {html.escape(str(event.get("severity") or "INFO"))}</b></div>'
                    f'<div><span class="muted">Event time</span><b>{html.escape(_fmt_ts(event.get("observed_at") or event.get("last_ts")))}</b></div>'
                    f'<div><span class="muted">Evidence reference</span><b>{html.escape(str(event.get("evidence_ref") or "-"))}</b></div>'
                    f'<div><span class="muted">Current related Sensor</span><b>{related_html}</b></div>'
                    '</div>'
                    f'<p>{html.escape(str(event.get("message") or ""))}</p></div>'
                )

        suppressions = handler.manager.events.suppressions(True)
        sup_rows = ''.join(f'<tr><td>{html.escape(x.get("root_device", ""))}:{html.escape(x.get("root_port", ""))}</td><td>{html.escape(x.get("target_device", ""))}</td><td>{_fmt_ts(x.get("expires_ts"))}</td><td>{html.escape(x.get("reason", ""))}</td></tr>' for x in suppressions)
        inner = (detail +
                 f'<div class="panel"><h2>Operational Events</h2><p class="muted">MC-3 normalized cross-domain operational evidence. Sensor refreshes create events only for durable state transitions; UNKNOWN remains missing evidence rather than an automatic critical verdict.</p>'
                 f'<form method=get action="/events"><div class="row"><select name=device>{options}</select><select name=domain>{domain_options}</select><button class=ghost>Filter</button></div></form>'
                 f'<div class="table-wrap"><table><tr><th>Observed</th><th>Domain</th><th>Severity</th><th>Event</th><th>Entity</th><th>Resource</th><th>Status</th><th>Count</th><th>State</th></tr>{body_rows or "<tr><td colspan=9 class=muted>No operational events.</td></tr>"}</table></div></div>'
                 f'<div class="panel"><h3>Active dependency suppressions</h3><div class="table-wrap"><table><tr><th>Upstream</th><th>Suppressed device</th><th>Expires</th><th>Reason</th></tr>{sup_rows or "<tr><td colspan=4 class=muted>None.</td></tr>"}</table></div></div>')
        return handler._send(handler._page("Events", inner, sess))


def render_protocols_page(handler, sess, q=None):
    """Task-oriented network-device collection profile presentation.

    This is an advanced per-device setting surface, not a daily operator task.
    """
    q = q or {}
    selected = str((q.get("device") or [""])[0] or "")
    rows = []
    for dev in handler.manager.inv.all():
        prof = handler.manager.protocol_profiles.get(dev["name"]) or {}
        protocol = prof.get("protocol", "cli_ssh")
        enabled = bool(prof.get("enabled"))
        collect = ""
        if sess["role"] in {"operator", "approver", "admin"}:
            collect = (f'<form method=post action="/protocol-collect">{handler._csrf_field()}'
                       f'<input type=hidden name=device value="{html.escape(dev["name"])}">'
                       '<button class=ghost>Collect now</button></form>')
        profile_badge = ('<span class="badge b-ok">configured</span>' if enabled
                         else '<span class="badge b-dim">default</span>')
        device_name = html.escape(dev["name"])
        if dev["name"] == selected:
            device_name = f'<b>{device_name}</b> <span class="badge b-ok">selected</span>'
        rows.append(
            f'<tr><td>{device_name}</td><td><b>{html.escape(protocol)}</b></td>'
            f'<td>{profile_badge}</td><td>{html.escape(str(prof.get("port") or "default"))}</td>'
            f'<td>{"allowed" if prof.get("allow_cli_fallback") else "no"}</td><td>{collect}</td></tr>'
        )
    intro = (
        '<div class=panel><h2>Device collection settings</h2>'
        '<p><b>You normally do not need to change this page.</b> It controls how NetConfig reads structured data from network devices such as switches, routers, and firewalls.</p>'
        '<p class=muted>Use it when onboarding a device, troubleshooting collection, or intentionally enabling NETCONF, RESTCONF, or gNMI. '
        'Normal polling and health views continue to use the configured collection methods automatically. This page does not directly push configuration.</p></div>'
    )
    table = (
        '<div class=panel><h2>Current collection profiles</h2>'
        '<table><tr><th>Network device</th><th>Read protocol</th><th>Profile</th><th>Port</th><th>CLI fallback</th><th>Action</th></tr>'
        + ''.join(rows) + '</table></div>'
    )
    if sess["role"] not in {"operator", "approver", "admin"}:
        return intro + table
    opts = ''.join(
        f'<option value="{html.escape(d["name"])}"{" selected" if d["name"] == selected else ""}>{html.escape(d["name"])}</option>'
        for d in handler.manager.inv.all())
    advanced = (
        '<div class=panel><details><summary><b>Advanced: change a network-device collection profile</b></summary>'
        '<p class=muted style="margin-top:10px">Only change this when the target network device and credentials are already prepared for that protocol.</p>'
        f'<form method=post action="/protocol-save">{handler._csrf_field()}'
        f'<div class=row><div><label>Device</label><select name=device>{opts}</select></div>'
        '<div><label>Protocol</label><select name=protocol><option>cli_ssh</option><option>netconf</option><option>restconf</option><option>gnmi</option></select></div>'
        '<div><label>Port (0 = protocol default)</label><input name=port value="0"></div></div>'
        '<div class=row><div><label>Vault secret ref (blank = device secret)</label><input name=secret_ref></div>'
        '<div><label>RESTCONF / gNMI read path</label><input name=path placeholder="/restconf/data?content=config or /interfaces"></div>'
        '<div><label>CA file</label><input name=ca_file placeholder="/etc/ssl/certs/vendor-ca.pem"></div></div>'
        '<label><input type=checkbox name=tls_verify value=1 checked> Verify TLS</label>'
        '<label><input type=checkbox name=allow_cli_fallback value=1> Explicitly allow CLI fallback</label>'
        '<button>Save collection profile</button></form></details></div>'
    )
    return intro + table + advanced

