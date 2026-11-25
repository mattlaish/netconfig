"""Shared interaction controls for the operator console."""
WORKFLOW_CSS = """
.workflow-error{border-color:var(--red);color:var(--red);background:var(--red10)}
.workflow-warning{border-color:var(--warn);color:var(--text)}
.workflow-success{border-color:var(--ok);color:var(--text)}
.device-tools{position:sticky;top:69px;z-index:8;background:var(--bg);padding:8px 0}
.device-tools-row,.bulk-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.device-tools label{margin:0;display:flex;gap:6px;align-items:center}
.device-tools input[type=search]{width:160px;margin:0}
.device-tools select{width:auto;max-width:300px;margin:0}
.device-tools .tabbar{position:static;margin:6px 0 0}
.device-card input[data-select-device]{position:relative;z-index:2;width:auto}
.sensor-value[role=link]{cursor:pointer;position:relative;z-index:1}
.bulk-controls select,.bulk-controls input{width:auto;margin:0}
.bulk-controls{margin:10px 0}
progress{width:100%;height:20px}
.form-actions{position:sticky;bottom:0;background:var(--surface);padding:12px 0;display:flex;gap:8px;flex-wrap:wrap;z-index:4}
"""
WORKFLOW_JS = r"""
(function(){
  var user=document.body.dataset.operatorUser || 'console';
  var prefix='netconfig-workflow:'+user+':';
  function read(key,fallback){
    try{return JSON.parse(sessionStorage.getItem(prefix+key)) || fallback;}catch(e){return fallback;}
  }
  function write(key,value){
    try{sessionStorage.setItem(prefix+key,JSON.stringify(value));}catch(e){}
  }
  function notice(form,text){
    var el=form.querySelector('[data-operation-message]');
    if(!el){el=document.createElement('p');el.dataset.operationMessage='';el.setAttribute('role','status');form.appendChild(el);}
    el.textContent=text;
  }
  function deviceState(){
    var box=document.getElementById('devsearch'), status=document.getElementById('devstatus');
    var old=read('devices',{});
    return {query:box?box.value:'',status:status?status.value:'all',scroll:old.scroll||0,
      groups:Array.from(document.querySelectorAll('.devgroup')).map(function(g){return g.open;})};
  }
  function filterDevices(){
    var grid=document.getElementById('devices-grid');
    if(!grid)return;
    var box=document.getElementById('devsearch'), status=document.getElementById('devstatus');
    var terms=(box?box.value:'').trim().toLowerCase().split(/\s+/).filter(Boolean);
    var selected=status?status.value:'all', visible=0;
    grid.querySelectorAll('.devgroup').forEach(function(group){
      var shown=0, cards=group.querySelectorAll('.device-card');
      cards.forEach(function(card){
        var match=terms.every(function(t){return (card.dataset.search||'').indexOf(t)>=0;});
        card.hidden=!match || (selected!=='all' && card.dataset.state!==selected);
        if(!card.hidden)shown++;
        var value=card.querySelector('.sensor-value');
        if(value){value.setAttribute('role','link');value.tabIndex=0;value.title='Open saved monitoring results';}
      });
      group.hidden=!shown;
      if(terms.length || selected!=='all')group.open=shown>0;
      var count=group.querySelector('.devcount');if(count)count.textContent=shown+' / '+cards.length;
      visible+=shown;
    });
    var empty=document.getElementById('devnoresults');if(empty)empty.hidden=visible>0;
    write('devices',deviceState());
    updateSelected();
  }
  function updateSelected(){
    var selected=Array.from(document.querySelectorAll('[data-select-device]:checked'));
    var count=document.getElementById('selected-count');
    if(count)count.textContent=selected.length+' selected';
    var review=document.getElementById('selected-devices');
    if(review){
      review.hidden=selected.length===0;
      var list=review.querySelector('[data-selected-names]');list.textContent='';
      selected.forEach(function(box){var item=document.createElement('li');item.textContent=box.value;list.appendChild(item);});
    }
    var visible=Array.from(document.querySelectorAll('.device-card:not([hidden]) [data-select-device]'));
    var selectAll=document.getElementById('select-visible');
    if(selectAll){
      selectAll.disabled=visible.length===0;
      selectAll.checked=visible.length>0&&visible.every(function(box){return box.checked;});
      selectAll.indeterminate=visible.some(function(box){return box.checked;})&&!selectAll.checked;
    }
  }
  var grid=document.getElementById('devices-grid');
  if(grid){
    var state=read('devices',{}), box=document.getElementById('devsearch'), status=document.getElementById('devstatus');
    if(box){box.value=state.query||'';box.addEventListener('input',filterDevices);}
    if(status){status.value=state.status||'all';status.addEventListener('change',filterDevices);}
    grid.querySelectorAll('.devgroup').forEach(function(g,i){if(state.groups && state.groups[i]!==undefined)g.open=state.groups[i];});
    filterDevices();
    if(state.scroll)requestAnimationFrame(function(){window.scrollTo(0,state.scroll);});
    document.addEventListener('click',function(e){
      var card=e.target.closest('.device-card');
      if(card){
        var saved=deviceState();saved.scroll=window.scrollY;write('devices',saved);
        write('device-return',location.pathname+location.search);
        if(e.target.closest('.sensor-value'))location.href=card.dataset.statusTarget;
      }
    });
    grid.addEventListener('keydown',function(e){
      if((e.key==='Enter'||e.key===' ') && e.target.matches('.sensor-value')){
        e.preventDefault();location.href=e.target.closest('.device-card').dataset.statusTarget;
      }
    });
    document.addEventListener('change',function(e){if(e.target.matches('[data-select-device]'))updateSelected();});
    var selectAll=document.getElementById('select-visible');
    if(selectAll)selectAll.addEventListener('change',function(){
      grid.querySelectorAll('.device-card:not([hidden]) [data-select-device]').forEach(function(c){c.checked=selectAll.checked;});
      updateSelected();
    });
    var refreshing=false;
    async function refreshDevices(){
      if(refreshing||document.hidden)return;
      refreshing=true;
      var hint=document.getElementById('devices-refresh-status');
      try{
        var res=await fetch('/devices-live',{cache:'no-store',credentials:'same-origin',redirect:'manual'});
        if(res.type==='opaqueredirect'){location.reload();return;}
        if(!res.ok)throw Error('refresh failed');
        var checked=new Set(Array.from(grid.querySelectorAll('[data-select-device]:checked')).map(function(c){return c.value;}));
        var groups=Array.from(grid.querySelectorAll('.devgroup')).map(function(g){return g.open;});
        grid.innerHTML=await res.text();
        grid.querySelectorAll('[data-select-device]').forEach(function(c){c.checked=checked.has(c.value);});
        grid.querySelectorAll('.devgroup').forEach(function(g,i){if(groups[i]!==undefined)g.open=groups[i];});
        filterDevices();
        if(hint)hint.textContent='Live · updated '+new Date().toLocaleTimeString();
      }catch(e){if(hint)hint.textContent='Update failed; retrying. Last displayed results remain visible.';}
      finally{refreshing=false;}
    }
    setInterval(refreshDevices,30000);
    document.addEventListener('visibilitychange',function(){if(!document.hidden)refreshDevices();});
  }

  var traffic=document.getElementById('traffic-content');
  if(traffic){
    var trafficKey='traffic:'+location.search, trafficPosition=read(trafficKey,{});
    if(trafficPosition.scroll)requestAnimationFrame(function(){window.scrollTo(0,trafficPosition.scroll);});
    document.addEventListener('click',function(e){
      if(e.target.closest('#traffic-content a'))write(trafficKey,{scroll:window.scrollY});
    });
  }
  var tools=document.querySelector('.device-tools');
  if(tools){
    var bar=document.querySelector('#device-tabs .tabbar');
    if(bar)tools.appendChild(bar);
    tools.querySelectorAll('[data-keep-tab]').forEach(function(a){
      a.addEventListener('click',function(){a.hash=location.hash;});
    });
    var selector=tools.querySelector('[data-device-switch]');
    if(selector)selector.addEventListener('change',function(){
      if(selector.value)location.href='/device?name='+encodeURIComponent(selector.value)+location.hash;
    });
    var deviceSearch=tools.querySelector('[data-device-search]');
    if(selector&&deviceSearch){
      var allDevices=Array.from(selector.options).map(function(option){return {value:option.value,text:option.textContent};});
      deviceSearch.addEventListener('input',function(){
        var query=deviceSearch.value.trim().toLowerCase();
        selector.textContent='';
        var placeholder=document.createElement('option');placeholder.value='';placeholder.textContent='Choose device';selector.appendChild(placeholder);
        allDevices.filter(function(option){return option.text.toLowerCase().includes(query);}).forEach(function(option){
          var el=document.createElement('option');el.value=option.value;el.textContent=option.text;selector.appendChild(el);
        });
      });
    }
    var back=tools.querySelector('[data-device-return]');if(back)back.href=read('device-return','/');
    document.querySelectorAll('a[href^="/device-new?name="]').forEach(function(a){
      a.addEventListener('click',function(){
        var url=new URL(a.href);url.searchParams.set('next',location.pathname+location.search+location.hash);a.href=url.href;
      });
    });
  }
  document.addEventListener('click',async function(e){
    var button=e.target.closest('[data-copy]');if(!button)return;
    var value=button.dataset.copy, old=button.textContent;
    try{
      if(navigator.clipboard && window.isSecureContext)await navigator.clipboard.writeText(value);
      else{
        var area=document.createElement('textarea');area.value=value;document.body.appendChild(area);area.select();
        var copied=document.execCommand('copy');area.remove();if(!copied)throw Error('copy failed');
      }
      button.textContent='Copied';
    }catch(e){button.textContent='Copy unavailable';}
    setTimeout(function(){button.textContent=old;},2000);
  });

  var form=document.getElementById('device_form');
  if(form){
    var appButton=document.querySelector('[data-test-application]');
    function showAppTest(){
      if(appButton)appButton.hidden=!form.querySelector('input[name=device_type][value=application]:checked');
    }
    form.querySelectorAll('input[name=device_type]').forEach(function(c){c.addEventListener('change',showAppTest);});
    showAppTest();
    if(appButton)appButton.addEventListener('click',async function(){
      var output=document.querySelector('[data-application-test-result]');
      appButton.disabled=true;output.textContent='Checking HTTP and TLS…';
      try{
        var body=new URLSearchParams(new FormData(form));body.set('test_application','1');
        var res=await fetch('/device-test',{method:'POST',credentials:'same-origin',body:body});
        var result=await res.json();output.textContent=result.error||result.results.map(function(r){
          return (r.ok?'OK':'Failed')+' '+r.check+': '+r.detail;
        }).join('\n');
      }catch(e){output.textContent='Check failed. Confirm that you are still signed in.';}
      finally{appButton.disabled=false;}
    });
  }
  var dirtyForms=new Set(), leaving=false;
  document.querySelectorAll('#device_form,form[action="/settings-save"]').forEach(function(f){
    if(f.dataset.unsavedInitial==='1')dirtyForms.add(f);
    f.addEventListener('input',function(){dirtyForms.add(f);});
    f.addEventListener('change',function(){dirtyForms.add(f);});
    f.addEventListener('submit',function(e){
      if(!e.defaultPrevented){
        leaving=true;
        if(new URL(f.getAttribute('action')||location.href,location.href).pathname==='/settings-save'){
          var field=f.querySelector('[name=ui_return_to]');
          if(!field){field=document.createElement('input');field.type='hidden';field.name='ui_return_to';f.appendChild(field);}
          var section=f.querySelector('[name=section]');
          field.value='/settings?section='+encodeURIComponent(section?section.value:'general');
        }
      }
      if(!e.defaultPrevented)setTimeout(function(){
        f.querySelectorAll('button').forEach(function(button){button.disabled=true;});
      },0);
    });
  });
  window.addEventListener('beforeunload',function(e){
    if(dirtyForms.size&&!leaving){e.preventDefault();e.returnValue='';}
  });

  var longActions={'/collect':'collect','/snmp-poll':'snmp','/device-monitor-check':'monitor'};
  document.addEventListener('submit',async function(e){
    var f=e.target, path=new URL(f.getAttribute('action')||location.href,location.href).pathname;
    var bulk=f.id==='device-bulk', action=bulk?f.querySelector('[name=action]').value:'';
    if(bulk && !document.querySelector('[data-select-device]:checked')){
      e.preventDefault();notice(f,'Select at least one device.');return;
    }
    var asyncAction=longActions[path]||path==='/collection-start'||path==='/collection-retry'||(bulk&&action==='check');
    if(bulk && action!=='check' && !window.confirm('Apply '+action+' to these devices?\n'+Array.from(document.querySelectorAll('[data-select-device]:checked')).map(function(box){return box.value;}).join('\n'))){
      e.preventDefault();return;
    }
    if(!asyncAction || e.defaultPrevented)return;
    e.preventDefault();
    if(f.dataset.submitting)return;
    f.dataset.submitting='1';
    var buttons=f.querySelectorAll('button'), body=new URLSearchParams(new FormData(f));
    body.set('background','1');
    body.set('return_to',body.get('return_to')||location.pathname+location.search+location.hash);
    var requestKey=f.dataset.requestKey||(window.crypto&&crypto.randomUUID?crypto.randomUUID():String(Date.now())+Math.random().toString(16).slice(2));
    f.dataset.requestKey=requestKey;body.set('request_key',requestKey);
    buttons.forEach(function(b){b.disabled=true;});notice(f,'Starting…');
    try{
      var response=await fetch(f.getAttribute('action')||location.href,{method:'POST',credentials:'same-origin',redirect:'manual',body:body,
        headers:{'X-NetConfig-Operation':'start'}});
      if(response.type==='opaqueredirect'){location.reload();return;}
      var result=await response.json();
      if(!response.ok)throw Error(result.error||'Could not start this operation.');
      leaving=true;location.href=result.location;
    }catch(err){notice(f,err.message);}
    finally{delete f.dataset.submitting;buttons.forEach(function(b){b.disabled=false;});}
  });

  function addCopyButtons(root){
    var nodes=[];
    if(root.matches && root.matches('td'))nodes.push(root);
    if(root.querySelectorAll)nodes=nodes.concat(Array.from(root.querySelectorAll('td,td code')));
    nodes.forEach(function(cell){
      var parent=cell.closest('td');
      if(!parent || parent.dataset.addressCopy)return;
      var value=cell.textContent.trim();
      var mac=/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(value);
      var ipv4=/^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$/.test(value);
      var ipv6=false;
      if(!mac && value.includes(':')){
        try{ipv6=new URL('http://['+value.split('%')[0]+']/').hostname.startsWith('[');}catch(e){}
      }
      if(!mac&&!ipv4&&!ipv6)return;
      parent.dataset.addressCopy='1';
      var button=document.createElement('button');button.type='button';button.className='ghost';
      button.dataset.copy=value;button.textContent='Copy';button.setAttribute('aria-label','Copy '+value);
      parent.appendChild(button);
    });
  }
  addCopyButtons(document);
  var main=document.querySelector('main');
  if(main)new MutationObserver(function(changes){
    changes.forEach(function(change){change.addedNodes.forEach(function(node){
      if(node.nodeType===1 && !node.matches('[data-copy]'))addCopyButtons(node);
    });});
  }).observe(main,{childList:true,subtree:true});

  var saving=document.getElementById('netflow-saving');
  if(saving){
    var savingBusy=false;
    setInterval(async function(){
      if(document.hidden||savingBusy||saving.contains(document.activeElement))return;
      savingBusy=true;
      try{
        var res=await fetch('/netflow-saving-status',{cache:'no-store',credentials:'same-origin',redirect:'manual'});
        if(res.type==='opaqueredirect'){location.reload();return;}
        if(res.ok){
          var doc=new DOMParser().parseFromString(await res.text(),'text/html');
          var fresh=doc.getElementById('netflow-saving');
          if(fresh)saving.replaceChildren(...fresh.childNodes);
        }
      }catch(e){/* A later refresh retries without discarding the current status. */}
      finally{savingBusy=false;}
    },15000);
  }

  var task=document.getElementById('collection-task');
  if(task){
    async function progress(){
      if(document.hidden){setTimeout(progress,2000);return;}
      try{
        var res=await fetch('/collection-status?id='+encodeURIComponent(task.dataset.taskId),
          {cache:'no-store',credentials:'same-origin',redirect:'manual'});
        if(res.type==='opaqueredirect'){location.reload();return;}
        if(!res.ok)throw Error('progress unavailable');
        var data=await res.json(), done=data.results.filter(function(r){return r.ok!==null;}).length;
        var labels={queued:'Waiting to start',running:'Running',passed:'Completed successfully',
          partial:'Completed with failures',failed:'Failed',interrupted:'Interrupted · retry unfinished devices'};
        task.querySelector('[data-task-summary]').className=data.state==='failed'?'workflow-error':data.state==='partial'?'workflow-warning':'';
        task.querySelector('[data-task-summary]').textContent=(labels[data.state]||data.state)+' · '+done+' / '+data.results.length;
        task.querySelector('progress').value=done;
        var rows=task.querySelector('[data-task-rows]');rows.textContent='';
        data.results.forEach(function(r){
          var row=document.createElement('tr'), device=document.createElement('td'), link=document.createElement('a');
          link.href='/device?name='+encodeURIComponent(r.device)+'#tab-'+encodeURIComponent(r.target_tab||'overview');link.textContent=r.device;device.appendChild(link);row.appendChild(device);
          [r.state,r.message].forEach(function(value){var cell=document.createElement('td');cell.textContent=value;row.appendChild(cell);});
          rows.appendChild(row);
        });
        var retry=task.querySelector('[data-retry-failed]');
        if(retry)retry.disabled=['queued','running'].includes(data.state)||data.results.every(function(r){return r.ok===true;});
        if(['queued','running'].includes(data.state))setTimeout(progress,2000);
      }catch(e){task.querySelector('[data-task-summary]').textContent='Progress update failed. Retrying…';setTimeout(progress,5000);}
    }
    progress();
  }
})();
"""
