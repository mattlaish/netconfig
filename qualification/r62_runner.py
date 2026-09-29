#!/usr/bin/env python3
"""R62 PostgreSQL / Concurrency / Recovery qualification runner.

Local regression proves harness and fail-closed semantics only. Production PostgreSQL
claims require explicit LIVE_POSTGRESQL hooks against the declared target.
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
    for p in _SECRET:
        text=p.sub("Bearer [REDACTED]" if "Bearer" in p.pattern else lambda m:f"{m.group(1)}{m.group(2)}[REDACTED]",str(text))
    return text

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def env_summary():
    rel={}
    p=Path('/etc/os-release')
    if p.is_file():
        for line in p.read_text(errors='replace').splitlines():
            if '=' in line and not line.startswith('#'):
                k,v=line.split('=',1); rel[k]=v.strip().strip('"')
    tools={x:bool(shutil.which(x)) for x in ('python3','pytest','psql','pg_dump','pg_restore','systemctl')}
    return {'os':{'id':rel.get('ID',''),'version_id':rel.get('VERSION_ID','')},'kernel':platform.release(),'python':platform.python_version(),'tools':tools,'live_postgres_opt_in':os.environ.get('NETCONFIG_R62_LIVE_POSTGRES')=='1'}

@dataclass(frozen=True)
class Gate:
    gate_id:str; area:str; title:str; evidence_class:str; builtin:str='hook'; hook_name:str=''; timeout:int=600; required_tools:tuple[str,...]=()

GATES=(
 Gate('R62-BASE-001','baseline','R62 identity and closed MC-11 authority','LOCAL_REGRESSION','baseline',timeout=30),
 Gate('R62-BASE-002','baseline','R62 focused hardening regression','LOCAL_REGRESSION','focused',timeout=240,required_tools=('pytest',)),
 Gate('R62-BASE-003','baseline','Full bounded repository regression','LOCAL_REGRESSION','full',timeout=900,required_tools=('pytest',)),
 Gate('R62-BASE-004','baseline','MC-11 authority regression retained','LOCAL_REGRESSION','mc11',timeout=180,required_tools=('pytest',)),
 Gate('R62-PG-001','postgres','Schema migration and MC-11 persistence on real PostgreSQL','LIVE_POSTGRESQL',hook_name='migration-planning-persistence',required_tools=('psql',)),
 Gate('R62-PG-002','concurrency','Concurrent collectors and SKIP LOCKED worker claims','LIVE_POSTGRESQL',hook_name='concurrent-collectors',required_tools=('psql',)),
 Gate('R62-PG-003','concurrency','Concurrent external evidence idempotency','LIVE_POSTGRESQL',hook_name='external-evidence-concurrency',required_tools=('psql',)),
 Gate('R62-PG-004','concurrency','MC-10 correlation advisory-lock exclusion','LIVE_POSTGRESQL',hook_name='correlation-advisory-lock',required_tools=('psql',)),
 Gate('R62-PG-005','concurrency','Structured Change planning approval simulation and concurrent operators','LIVE_POSTGRESQL',hook_name='structured-change-concurrency',required_tools=('psql',)),
 Gate('R62-PG-006','transactions','Transaction rollback atomicity','LIVE_POSTGRESQL',hook_name='transaction-rollback',required_tools=('psql',)),
 Gate('R62-PG-007','transactions','Deadlock and serialization retry bounds','LIVE_POSTGRESQL',hook_name='deadlock-serialization-retry',required_tools=('psql',)),
 Gate('R62-PG-008','transactions','Connection budget/pool exhaustion bounded failure','LIVE_POSTGRESQL',hook_name='connection-budget-exhaustion',required_tools=('psql',)),
 Gate('R62-PG-009','recovery','Database restart recovery with no unknown write replay','LIVE_POSTGRESQL',hook_name='database-restart-recovery',required_tools=('psql',)),
 Gate('R62-PG-010','recovery','Database network interruption recovery with no unknown write replay','LIVE_POSTGRESQL',hook_name='network-interruption-recovery',required_tools=('psql',)),
 Gate('R62-PG-011','recovery','Backup restore and post-restore concurrency','LIVE_POSTGRESQL',hook_name='backup-restore-concurrency',required_tools=('psql','pg_dump','pg_restore')),
 Gate('R62-PG-012','operators','Concurrent persisted-data API operators on PostgreSQL','LIVE_POSTGRESQL',hook_name='concurrent-operators',required_tools=('psql',)),
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

def builtin(g,out):
    if g.builtin=='baseline':
        spec=(ROOT/'packaging/netconfig.spec').read_text(); road=(ROOT/'ROADMAP.md').read_text().lower(); pg=(ROOT/'opt/netconfig/netconfig/postgres_core.py').read_text()
        ok='Release:        62.1%{?dist}' in spec and 'release 62' in road and 'do not create mc-12' in road and 'connection_failure_write_replay' in pg
        return (0 if ok else 1,'R62 identity/resilience baseline '+('PASS\n' if ok else 'FAIL\n'),'',0.0)
    tests={'focused':'tests/test_r62_postgres_hardening.py','mc11':'tests/test_mc11_topology_change_planning.py'}
    if g.builtin in tests: return run([sys.executable,'-m','pytest','-q',tests[g.builtin]],g.timeout)
    if g.builtin=='full': return run([sys.executable,'qualification/run_bounded_regression.py','--groups','5','--group-timeout','140'],g.timeout)
    raise RuntimeError(g.builtin)

def gate_result(g,env,out,hook_dir,include_local,live):
    r={'gate_id':g.gate_id,'area':g.area,'title':g.title,'evidence_class':g.evidence_class,'status':NOT_RUN,'reason':'','duration_seconds':0.0,'logs':{}}
    if g.evidence_class=='LOCAL_REGRESSION':
        if not include_local: r['reason']='local evidence not requested'; return r
        missing=[x for x in g.required_tools if not env['tools'].get(x)]
        if missing: r['status']=BLOCKED; r['reason']='missing tool(s): '+','.join(missing); return r
        rc,so,se,d=builtin(g,out)
    else:
        if not live: r['reason']='live PostgreSQL evidence not requested'; return r
        if not env['live_postgres_opt_in']:
            r['status']=BLOCKED; r['reason']='set NETCONFIG_R62_LIVE_POSTGRES=1 on the designated PostgreSQL qualification target'; return r
        missing=[x for x in g.required_tools if not env['tools'].get(x)]
        if missing: r['status']=BLOCKED; r['reason']='missing tool(s): '+','.join(missing); return r
        hook=hook_dir/f'{g.hook_name}.sh' if hook_dir else None
        if not hook or not hook.is_file(): r['reason']='fixed qualification hook not provided'; return r
        if not os.access(hook,os.X_OK): r['reason']='qualification hook is not executable'; return r
        result=out/'scratch'/g.gate_id/'result.json'; result.parent.mkdir(parents=True,exist_ok=True)
        rc,so,se,d=run([str(hook)],g.timeout,{'NETCONFIG_R62_GATE_ID':g.gate_id,'NETCONFIG_R62_RESULT_PATH':str(result),'NETCONFIG_R62_REPO_ROOT':str(ROOT)})
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
    a=ap.parse_args(); out=Path(a.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True); env=env_summary(); hooks=Path(a.hook_dir).resolve() if a.hook_dir else None
    selected=[g for g in GATES if not a.gate or g.gate_id in set(a.gate)]
    rows=[gate_result(g,env,out,hooks,a.include_local,a.live) for g in selected]
    counts={x:sum(r['status']==x for r in rows) for x in (PASS,FAIL,BLOCKED,NOT_RUN)}; live_pass=sum(r['status']==PASS and r['evidence_class']=='LIVE_POSTGRESQL' for r in rows)
    campaign={'campaign':'R62 PostgreSQL / Concurrency / Recovery Hardening','campaign_id':str(uuid.uuid4()),'product_baseline':'2.0.0-62.1','schema_revision':'mc11-topology-change-planning-1','status':'IMPLEMENTED_TESTING_DEFERRED','finished_at':datetime.now(timezone.utc).isoformat(),'environment':env,'status_counts':counts,'live_postgresql_pass_count':live_pass,'production_postgresql_claim':bool(live_pass and all(r['status']==PASS for r in rows if r['evidence_class']=='LIVE_POSTGRESQL')),'release_promotion_performed':False,'gates':rows}
    (out/'campaign.json').write_text(json.dumps(campaign,indent=2,sort_keys=True)+'\n')
    (out/'SUMMARY.md').write_text(f"# R62 qualification evidence\n\nPASS {counts[PASS]} / FAIL {counts[FAIL]} / BLOCKED_ENVIRONMENT {counts[BLOCKED]} / NOT_RUN {counts[NOT_RUN]}\n\nLIVE_POSTGRESQL PASS: {live_pass}\n")
    print(json.dumps(counts,sort_keys=True)); return 1 if counts[FAIL] else 0
if __name__=='__main__': raise SystemExit(main())
