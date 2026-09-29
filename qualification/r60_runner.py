#!/usr/bin/env python3
"""R60 Appliance Reliability & Lifecycle Hardening qualification runner.

Produces sanitized checksummed evidence and never promotes release state.  Live
platform/destructive gates use fixed-name hooks; local gates exercise source and
rollback semantics without pretending to be AlmaLinux/systemd/PostgreSQL evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid

PASS="PASS"; FAIL="FAIL"; BLOCKED="BLOCKED_ENVIRONMENT"; NOT_RUN="NOT_RUN"
STATUSES={PASS,FAIL,BLOCKED,NOT_RUN}; HOOK_BLOCKED=20; HOOK_NOT_RUN=21
ROOT=Path(__file__).resolve().parents[1]; MAX_LOG_BYTES=64*1024
_SECRET=[re.compile(r"(?i)(password|passwd|secret|token|community|api[_-]?key|authorization)\s*([=:])\s*([^\s,;]+)"),re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")]


def redact(text:str)->str:
    for p in _SECRET:
        text=p.sub("Bearer [REDACTED]" if "Bearer" in p.pattern else lambda m:f"{m.group(1)}{m.group(2)}[REDACTED]",text)
    return text


def sha256(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def os_release()->dict[str,str]:
    out={}; p=Path('/etc/os-release')
    if p.is_file():
        for raw in p.read_text(encoding='utf-8',errors='replace').splitlines():
            if '=' in raw and not raw.lstrip().startswith('#'):
                k,v=raw.split('=',1); out[k]=v.strip().strip('"')
    return out


def environment_summary()->dict:
    o=os_release(); names=("python3","pytest","rpm","rpmbuild","dnf","systemctl","systemd-analyze","getenforce","pg_dump","pg_restore","psql","flock")
    return {"os":{"id":o.get("ID",""),"version_id":o.get("VERSION_ID","")},"kernel":platform.release(),"architecture":platform.machine(),"python":platform.python_version(),"effective_uid_is_root":hasattr(os,'geteuid') and os.geteuid()==0,"tools":{n:bool(shutil.which(n)) for n in names}}


@dataclass(frozen=True)
class Gate:
    gate_id:str; area:str; title:str; evidence_class:str; timeout:int=300; destructive:bool=False; builtin:str="hook"; hook_name:str=""; required_tools:tuple[str,...]=(); target_os:bool=False


GATES=(
    Gate("R60-BASE-001","baseline","R60 release identity and closed MC-11 authority","LOCAL_REGRESSION",30,builtin="baseline"),
    Gate("R60-BASE-002","baseline","R60 lifecycle focused regression","LOCAL_REGRESSION",120,builtin="focused",required_tools=("pytest",)),
    Gate("R60-BASE-003","baseline","Full bounded repository regression","LOCAL_REGRESSION",900,builtin="full",required_tools=("pytest",)),
    Gate("R60-BASE-004","baseline","MC-11 authority regression retained","LOCAL_REGRESSION",180,builtin="mc11",required_tools=("pytest",)),
    Gate("R60-LIFE-001","lifecycle","AlmaLinux R59 to R60 lifecycle upgrade success","LIVE_PRODUCTION",1200,True,hook_name="r59-to-r60-upgrade",required_tools=("rpm","dnf","systemctl","flock"),target_os=True),
    Gate("R60-LIFE-002","lifecycle","Injected failed upgrade returns to prior working R59 state","LIVE_PRODUCTION",1800,True,hook_name="failed-upgrade-rollback",required_tools=("rpm","dnf","systemctl","flock"),target_os=True),
    Gate("R60-LIFE-003","lifecycle","Configuration secret and certificate preservation","LIVE_PRODUCTION",600,True,hook_name="preservation",required_tools=("rpm","dnf","systemctl"),target_os=True),
    Gate("R60-LIFE-004","lifecycle","Service dependency ordering and restart recovery","LIVE_PRODUCTION",600,True,hook_name="service-ordering-restart",required_tools=("systemctl","systemd-analyze"),target_os=True),
    Gate("R60-LIFE-005","lifecycle","Graceful shutdown and reboot recovery","LIVE_PRODUCTION",1800,True,hook_name="shutdown-reboot",required_tools=("systemctl",),target_os=True),
    Gate("R60-LIFE-006","lifecycle","Crash recovery preserves deterministic state","LIVE_PRODUCTION",900,True,hook_name="crash-recovery",required_tools=("systemctl",),target_os=True),
    Gate("R60-STOR-001","storage","Disk-space preflight and disk-full fail-closed behavior","LIVE_PRODUCTION",900,True,hook_name="disk-full",target_os=True),
    Gate("R60-STOR-002","storage","Log rotation retention and database maintenance under pressure","LIVE_PRODUCTION",900,True,hook_name="log-retention-maintenance",target_os=True),
    Gate("R60-DB-001","postgresql","PostgreSQL pre-upgrade pg_dump and validated separate rollback database","LIVE_PRODUCTION",1200,True,hook_name="postgres-rollback-db",required_tools=("pg_dump","pg_restore"),target_os=True),
    Gate("R60-DB-002","postgresql","PostgreSQL failed migration rollback switches to validated rollback database","LIVE_PRODUCTION",1800,True,hook_name="postgres-failed-migration-rollback",required_tools=("pg_dump","pg_restore","systemctl"),target_os=True),
)


def missing(g:Gate,env:dict)->list[str]:
    out=[]
    for t in g.required_tools:
        if not env['tools'].get(t,bool(shutil.which(t))): out.append(f"tool:{t}")
    if g.target_os:
        if env['os']['id']!='almalinux': out.append('os:almalinux')
        if str(env['os']['version_id']).split('.',1)[0]!='10': out.append('os-major:10')
    return out


def run(argv:list[str],timeout:int,extra:dict|None=None):
    env=os.environ.copy(); env.update(extra or {}); start=time.monotonic()
    try:
        cp=subprocess.run(argv,cwd=ROOT,env=env,text=True,capture_output=True,timeout=timeout,check=False)
        return cp.returncode,cp.stdout or '',cp.stderr or '',time.monotonic()-start
    except subprocess.TimeoutExpired as e:
        so=e.stdout.decode() if isinstance(e.stdout,bytes) else (e.stdout or ''); se=e.stderr.decode() if isinstance(e.stderr,bytes) else (e.stderr or '')
        return 124,so,se+f"\nTIMEOUT after {timeout}s",time.monotonic()-start


def baseline():
    spec=(ROOT/'packaging/netconfig.spec').read_text(); road=(ROOT/'ROADMAP.md').read_text().lower(); db=(ROOT/'opt/netconfig/netconfig/db.py').read_text()
    errs=[]
    if not re.search(r'(?m)^Release:\s+60%\{\?dist\}\s*$',spec): errs.append('RPM Release is not 60')
    if 'mc11-topology-change-planning-1' not in db: errs.append('MC-11 schema revision drifted')
    if 'do not create mc-12' not in road: errs.append('MC-12 closure missing')
    for p in ('opt/netconfig/netconfig/lifecycle.py','packaging/r60-lifecycle-upgrade.sh','tests/test_r60_lifecycle.py'):
        if not (ROOT/p).is_file(): errs.append(f'missing R60 lifecycle component: {p}')
    metrics={'release':'2.0.0-60','schema_revision':'mc11-topology-change-planning-1','status':'IMPLEMENTED_TESTING_DEFERRED','next':'R61 Scale & Performance Qualification','mc12_defined':False}
    return (1,'','\n'.join(errs),metrics) if errs else (0,'R60 lifecycle baseline: PASS\n','',metrics)


def builtin(g:Gate):
    if g.builtin=='focused': return [sys.executable,'-m','pytest','-q','tests/test_r60_lifecycle.py','tests/test_r60_qualification.py']
    if g.builtin=='full': return [sys.executable,'qualification/run_bounded_regression.py','--groups','5']
    if g.builtin=='mc11': return [sys.executable,'-m','pytest','-q','tests/test_mc11_topology_change_planning.py']
    raise ValueError(g.builtin)


def write_log(p:Path,text:str):
    raw=redact(text).encode('utf-8',errors='replace'); truncated=len(raw)>MAX_LOG_BYTES
    if truncated: raw=raw[:MAX_LOG_BYTES]+b'\n[TRUNCATED]\n'
    p.write_bytes(raw); return {'path':p.name,'bytes':len(raw),'sha256':sha256(p),'truncated':truncated}


def run_gate(g:Gate,*,env:dict,out:Path,hook_dir:Path|None,include_local:bool,live:bool,allow_destructive:bool):
    result={'gate_id':g.gate_id,'area':g.area,'title':g.title,'evidence_class':g.evidence_class,'status':NOT_RUN,'reason':'','destructive':g.destructive,'duration_seconds':0.0,'metrics':{},'logs':{}}
    if g.evidence_class=='LOCAL_REGRESSION' and not include_local: result['reason']='local regression not selected'; return result
    if g.evidence_class=='LIVE_PRODUCTION' and not live: result['reason']='live execution not selected'; return result
    if g.destructive and not allow_destructive: result['reason']='destructive live gate requires --allow-destructive'; return result
    miss=missing(g,env)
    if miss: result['status']=BLOCKED; result['reason']='missing qualification prerequisites: '+', '.join(miss); return result
    metrics={}
    if g.builtin=='baseline': start=time.monotonic(); rc,so,se,metrics=baseline(); duration=time.monotonic()-start
    elif g.builtin!='hook': rc,so,se,duration=run(builtin(g),g.timeout)
    else:
        if hook_dir is None: result['status']=BLOCKED; result['reason']='--hook-dir/NETCONFIG_R60_HOOK_DIR not configured'; return result
        hook=hook_dir/g.hook_name
        if not hook.is_file() or not os.access(hook,os.X_OK): result['status']=BLOCKED; result['reason']=f'required executable hook missing: {g.hook_name}'; return result
        scratch=out/'scratch'/g.gate_id; scratch.mkdir(parents=True,exist_ok=True); result_file=scratch/'result.json'
        rc,so,se,duration=run([str(hook)],g.timeout,{'NETCONFIG_R60_GATE_ID':g.gate_id,'NETCONFIG_R60_RESULT_PATH':str(result_file),'NETCONFIG_R60_REPO_ROOT':str(ROOT)})
        if result_file.is_file() and result_file.stat().st_size<=64*1024:
            try:
                obj=json.loads(result_file.read_text()); metrics=obj if isinstance(obj,dict) else {}
            except Exception: metrics={}
    result['duration_seconds']=round(duration,3); logs=out/'logs'; logs.mkdir(parents=True,exist_ok=True)
    result['logs']={'stdout':write_log(logs/f'{g.gate_id}.stdout.log',so),'stderr':write_log(logs/f'{g.gate_id}.stderr.log',se)}; result['metrics']=metrics
    if rc==0: result['status']=PASS
    elif rc==HOOK_BLOCKED: result['status']=BLOCKED; result['reason']='qualification hook reported blocked environment'
    elif rc==HOOK_NOT_RUN: result['status']=NOT_RUN; result['reason']='qualification hook reported not run'
    else: result['status']=FAIL; result['reason']=f'gate command returned {rc}'
    return result


def checksums(out:Path):
    p=out/'SHA256SUMS'; rows=[]
    for f in sorted(x for x in out.rglob('*') if x.is_file() and x!=p): rows.append(f'{sha256(f)}  {f.relative_to(out).as_posix()}')
    p.write_text('\n'.join(rows)+'\n')


def main(argv=None):
    ap=argparse.ArgumentParser(description='NetConfig R60 lifecycle qualification runner'); ap.add_argument('--output-dir',required=True); ap.add_argument('--include-local',action='store_true'); ap.add_argument('--live',action='store_true'); ap.add_argument('--allow-destructive',action='store_true'); ap.add_argument('--hook-dir'); ap.add_argument('--gate',action='append')
    a=ap.parse_args(argv); out=Path(a.output_dir).resolve()
    if out.exists() and any(out.iterdir()): ap.error('output directory must be empty')
    out.mkdir(parents=True,exist_ok=True); env=environment_summary(); hook=Path(a.hook_dir or os.environ.get('NETCONFIG_R60_HOOK_DIR','')).resolve() if (a.hook_dir or os.environ.get('NETCONFIG_R60_HOOK_DIR')) else None
    selected=set(a.gate or []); gates=[g for g in GATES if not selected or g.gate_id in selected]
    if selected-set(g.gate_id for g in GATES): ap.error('unknown gate id(s): '+','.join(sorted(selected-set(g.gate_id for g in GATES))))
    started=datetime.now(timezone.utc).isoformat(); rows=[run_gate(g,env=env,out=out,hook_dir=hook,include_local=a.include_local,live=a.live,allow_destructive=a.allow_destructive) for g in gates]
    counts={s:sum(1 for r in rows if r['status']==s) for s in sorted(STATUSES)}; campaign={'campaign':'R60 Appliance Reliability & Lifecycle Hardening','campaign_id':str(uuid.uuid4()),'product_baseline':'2.0.0-60','schema_revision':'mc11-topology-change-planning-1','status':'IMPLEMENTED_TESTING_DEFERRED','started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'environment':env,'status_counts':counts,'release_promotion_performed':False,'gates':rows}
    (out/'campaign.json').write_text(json.dumps(campaign,indent=2,sort_keys=True)+'\n')
    lines=['# NetConfig R60 Lifecycle Qualification Evidence','',f"- Product: `{campaign['product_baseline']}`",f"- PASS: **{counts[PASS]}**",f"- FAIL: **{counts[FAIL]}**",f"- BLOCKED_ENVIRONMENT: **{counts[BLOCKED]}**",f"- NOT_RUN: **{counts[NOT_RUN]}**",'', 'Local regression never substitutes for live appliance evidence. This runner never promotes TESTED/RELEASED.','', '| Gate | Class | Status | Title |','|---|---|---|---|']
    for r in rows: lines.append(f"| `{r['gate_id']}` | {r['evidence_class']} | **{r['status']}** | {r['title']} |")
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n'); (out/'gate-catalog.json').write_text(json.dumps([asdict(g) for g in GATES],indent=2,sort_keys=True)+'\n'); checksums(out)
    print(json.dumps(counts,sort_keys=True)); return 1 if counts[FAIL] else 0


if __name__=='__main__': raise SystemExit(main())
