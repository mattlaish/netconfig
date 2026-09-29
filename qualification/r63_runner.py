#!/usr/bin/env python3
"""R63 HA / Failure-Domain Engineering qualification runner.

Local regression proves fencing semantics only. Production HA claims require all
fixed LIVE_HA hooks to pass on the designated multi-node PostgreSQL environment.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, re, shutil, subprocess, sys, time, uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PASS="PASS"; FAIL="FAIL"; BLOCKED="BLOCKED_ENVIRONMENT"; NOT_RUN="NOT_RUN"
HOOK_BLOCKED=20; HOOK_NOT_RUN=21; ROOT=Path(__file__).resolve().parents[1]; MAX_LOG_BYTES=64*1024
_SECRET=[re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),re.compile(r"(?i)(password|passwd|secret|token|community|api[_-]?key|authorization)\s*([=:])\s*([^\s,;]+)")]

def redact(text):
    text=str(text)
    for p in _SECRET:
        text=p.sub("Bearer [REDACTED]" if "Bearer" in p.pattern else lambda m:f"{m.group(1)}{m.group(2)}[REDACTED]",text)
    return text

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def env_summary():
    rel={}; p=Path('/etc/os-release')
    if p.is_file():
        for line in p.read_text(errors='replace').splitlines():
            if '=' in line and not line.startswith('#'):
                k,v=line.split('=',1); rel[k]=v.strip().strip('"')
    tools={x:bool(shutil.which(x)) for x in ('python3','pytest','psql','systemctl','ip','tc')}
    return {'os':{'id':rel.get('ID',''),'version_id':rel.get('VERSION_ID','')},'kernel':platform.release(),
            'python':platform.python_version(),'tools':tools,
            'live_ha_opt_in':os.environ.get('NETCONFIG_R63_LIVE_HA')=='1'}

@dataclass(frozen=True)
class Gate:
    gate_id:str; area:str; title:str; evidence_class:str; builtin:str='hook'; hook_name:str=''; timeout:int=600; required_tools:tuple[str,...]=()

GATES=(
 Gate('R63-BASE-001','baseline','R63 release/schema/authority identity','LOCAL_REGRESSION','baseline',timeout=30),
 Gate('R63-BASE-002','baseline','R63 HA failure-domain focused regression','LOCAL_REGRESSION','focused',timeout=240,required_tools=('pytest',)),
 Gate('R63-BASE-003','baseline','Full bounded repository regression','LOCAL_REGRESSION','full',timeout=900,required_tools=('pytest',)),
 Gate('R63-BASE-004','baseline','MC-11 authority regression retained','LOCAL_REGRESSION','mc11',timeout=180,required_tools=('pytest',)),
 Gate('R63-HA-001','membership','Two fresh ACTIVE control-plane nodes in distinct declared failure domains','LIVE_HA',hook_name='failure-domain-membership',required_tools=('psql',)),
 Gate('R63-HA-002','leadership','Singleton scheduler leadership and standby takeover','LIVE_HA',hook_name='scheduler-leader-failover',required_tools=('psql',)),
 Gate('R63-HA-003','node-failure','Control-plane process/node loss and clean standby takeover','LIVE_HA',hook_name='node-failover',required_tools=('psql','systemctl')),
 Gate('R63-HA-004','worker-failure','Worker lease expiry fences stale completion and exposes partial job','LIVE_HA',hook_name='worker-lease-fencing',required_tools=('psql',)),
 Gate('R63-HA-005','partial-job','Partial side-effect job enters RECOVERY_REQUIRED with no automatic replay','LIVE_HA',hook_name='partial-job-recovery',required_tools=('psql',)),
 Gate('R63-HA-006','replay','Explicit replay-safe recovery produces one new fenced execution only','LIVE_HA',hook_name='replay-recovery',required_tools=('psql',)),
 Gate('R63-HA-007','database','PostgreSQL primary/service failover and control-plane reconnection','LIVE_HA',hook_name='database-failover',required_tools=('psql',)),
 Gate('R63-HA-008','network-partition','DB network partition fences automation before device-side work','LIVE_HA',hook_name='database-network-partition',required_tools=('psql','ip')),
 Gate('R63-HA-009','stale-lock','Session reconnect invalidates stale advisory ownership before reacquire','LIVE_HA',hook_name='stale-advisory-lock',required_tools=('psql',)),
 Gate('R63-HA-010','split-brain','Control-plane partition cannot produce simultaneous scheduler/device-write ownership','LIVE_HA',hook_name='split-brain-fencing',required_tools=('psql','ip')),
 Gate('R63-HA-011','rejoin','Failed node restart/rejoin preserves node identity and does not duplicate work','LIVE_HA',hook_name='restart-rejoin',required_tools=('psql','systemctl')),
 Gate('R63-HA-012','maintenance','Drain/rolling maintenance transfers singleton work without new work on drained node','LIVE_HA',hook_name='drain-failover',required_tools=('psql','systemctl')),
)

def run(cmd,timeout,env=None):
    t=time.perf_counter()
    try:
        cp=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=timeout,env={**os.environ,**(env or {})})
        return cp.returncode,cp.stdout or '',cp.stderr or '',time.perf_counter()-t
    except subprocess.TimeoutExpired as e:
        so=e.stdout.decode() if isinstance(e.stdout,bytes) else (e.stdout or '')
        se=e.stderr.decode() if isinstance(e.stderr,bytes) else (e.stderr or '')
        return 124,so,se+f'\nTIMEOUT after {timeout}s\n',time.perf_counter()-t

def log(path,text):
    data=redact(text).encode('utf-8','replace')[:MAX_LOG_BYTES]; path.write_bytes(data)
    return {'path':path.name,'bytes':len(data),'sha256':sha256(path)}

def builtin(g):
    if g.builtin=='baseline':
        spec=(ROOT/'packaging/netconfig.spec').read_text(); road=(ROOT/'ROADMAP.md').read_text().lower()
        ha=(ROOT/'opt/netconfig/netconfig/ha.py').read_text(); pg=(ROOT/'opt/netconfig/netconfig/postgres_core.py').read_text()
        db=(ROOT/'opt/netconfig/netconfig/db.py').read_text()
        ok=('Release:        63%{?dist}' in spec and 'r63' in road and 'do not create mc-12' in road and
            'ensure_node_identity_fence' in ha and 'session_generation' in pg and
            'RECOVERY_REQUIRED' in db and 'claim_generation' in db)
        return (0 if ok else 1,'R63 identity/fencing baseline '+('PASS\n' if ok else 'FAIL\n'),'',0.0)
    tests={'focused':'tests/test_r63_ha_failure_domain.py','mc11':'tests/test_mc11_topology_change_planning.py'}
    if g.builtin in tests: return run([sys.executable,'-m','pytest','-q',tests[g.builtin]],g.timeout)
    if g.builtin=='full': return run([sys.executable,'qualification/run_bounded_regression.py','--groups','5','--group-timeout','150'],g.timeout)
    raise RuntimeError(g.builtin)

def gate_result(g,env,out,hook_dir,include_local,live):
    r={'gate_id':g.gate_id,'area':g.area,'title':g.title,'evidence_class':g.evidence_class,
       'status':NOT_RUN,'reason':'','duration_seconds':0.0,'logs':{}}
    if g.evidence_class=='LOCAL_REGRESSION':
        if not include_local: r['reason']='local evidence not requested'; return r
        missing=[x for x in g.required_tools if not env['tools'].get(x)]
        if missing: r['status']=BLOCKED; r['reason']='missing tool(s): '+','.join(missing); return r
        rc,so,se,d=builtin(g)
    else:
        if not live: r['reason']='live HA evidence not requested'; return r
        if not env['live_ha_opt_in']:
            r['status']=BLOCKED; r['reason']='set NETCONFIG_R63_LIVE_HA=1 on the designated multi-node HA qualification environment'; return r
        missing=[x for x in g.required_tools if not env['tools'].get(x)]
        if missing: r['status']=BLOCKED; r['reason']='missing tool(s): '+','.join(missing); return r
        hook=hook_dir/f'{g.hook_name}.sh' if hook_dir else None
        if not hook or not hook.is_file(): r['status']=BLOCKED; r['reason']='fixed qualification hook not provided'; return r
        if not os.access(hook,os.X_OK): r['status']=BLOCKED; r['reason']='qualification hook is not executable'; return r
        result=out/'scratch'/g.gate_id/'result.json'; result.parent.mkdir(parents=True,exist_ok=True)
        rc,so,se,d=run([str(hook)],g.timeout,{'NETCONFIG_R63_GATE_ID':g.gate_id,'NETCONFIG_R63_RESULT_PATH':str(result),'NETCONFIG_R63_REPO_ROOT':str(ROOT)})
        if result.is_file() and result.stat().st_size<=256*1024:
            try: r['metrics']=json.loads(result.read_text())
            except Exception: r['metrics']={}
    r['duration_seconds']=round(d,3); logs=out/'logs'; logs.mkdir(parents=True,exist_ok=True)
    r['logs']={'stdout':log(logs/f'{g.gate_id}.stdout.log',so),'stderr':log(logs/f'{g.gate_id}.stderr.log',se)}
    if rc==0: r['status']=PASS
    elif rc==HOOK_BLOCKED: r['status']=BLOCKED; r['reason']='qualification hook reported blocked environment'
    elif rc==HOOK_NOT_RUN: r['status']=NOT_RUN; r['reason']='qualification hook reported not run'
    else: r['status']=FAIL; r['reason']=f'command exited {rc}'
    return r

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--output-dir',required=True); ap.add_argument('--hook-dir'); ap.add_argument('--include-local',action='store_true'); ap.add_argument('--live',action='store_true'); ap.add_argument('--gate',action='append')
    a=ap.parse_args(); out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    env=env_summary(); hooks=Path(a.hook_dir).resolve() if a.hook_dir else None
    selected=[g for g in GATES if not a.gate or g.gate_id in set(a.gate)]
    rows=[gate_result(g,env,out,hooks,a.include_local,a.live) for g in selected]
    counts={x:sum(r['status']==x for r in rows) for x in (PASS,FAIL,BLOCKED,NOT_RUN)}
    live_rows=[r for r in rows if r['evidence_class']=='LIVE_HA']; live_pass=sum(r['status']==PASS for r in live_rows)
    campaign={'campaign':'R63 HA / Failure-Domain Engineering','campaign_id':str(uuid.uuid4()),
              'product_baseline':'2.0.0-63','schema_revision':'mc11-topology-change-planning-1',
              'status':'IMPLEMENTED_TESTING_DEFERRED','finished_at':datetime.now(timezone.utc).isoformat(),
              'environment':env,'status_counts':counts,'live_ha_pass_count':live_pass,
              'production_ha_claim':bool(live_rows and all(r['status']==PASS for r in live_rows)),
              'release_promotion_performed':False,'gates':rows}
    (out/'campaign.json').write_text(json.dumps(campaign,indent=2,sort_keys=True)+'\n')
    (out/'SUMMARY.md').write_text(f"# R63 HA qualification evidence\n\nPASS {counts[PASS]} / FAIL {counts[FAIL]} / BLOCKED_ENVIRONMENT {counts[BLOCKED]} / NOT_RUN {counts[NOT_RUN]}\n\nLIVE_HA PASS: {live_pass}\n\nProduction HA claim: {str(campaign['production_ha_claim']).lower()}\n")
    files=[p for p in out.rglob('*') if p.is_file() and p.name!='SHA256SUMS']
    (out/'SHA256SUMS').write_text(''.join(f"{sha256(p)}  {p.relative_to(out).as_posix()}\n" for p in sorted(files)))
    print(json.dumps(counts,sort_keys=True)); return 1 if counts[FAIL] else 0
if __name__=='__main__': raise SystemExit(main())
