#!/usr/bin/env python3
"""R61 Scale & Performance Qualification runner.

Local synthetic benchmarks are evidence for harness correctness and comparative
engineering only. Production capacity/latency claims require LIVE_PRODUCTION
hooks on the declared target platform and datastore.
"""
from __future__ import annotations
import argparse, hashlib, json, os, platform, re, shutil, subprocess, sys, time, uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

PASS="PASS"; FAIL="FAIL"; BLOCKED="BLOCKED_ENVIRONMENT"; NOT_RUN="NOT_RUN"
STATUSES={PASS,FAIL,BLOCKED,NOT_RUN}; HOOK_BLOCKED=20; HOOK_NOT_RUN=21
ROOT=Path(__file__).resolve().parents[1]; MAX_LOG_BYTES=64*1024
_SECRET=[re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),re.compile(r"(?i)(password|passwd|secret|token|community|api[_-]?key|authorization)\s*([=:])\s*([^\s,;]+)")]


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
    o=os_release(); names=("python3","pytest","rpm","rpmbuild","dnf","systemctl","getenforce","psql","pg_dump","pg_restore")
    return {"os":{"id":o.get("ID","").lower(),"version_id":o.get("VERSION_ID","")},"kernel":platform.release(),"architecture":platform.machine(),"python":platform.python_version(),"cpu_count":os.cpu_count() or 0,"tools":{n:bool(shutil.which(n)) for n in names}}


@dataclass(frozen=True)
class Gate:
    gate_id:str; area:str; title:str; evidence_class:str; timeout:int=300; builtin:str="hook"; hook_name:str=""; required_tools:tuple[str,...]=(); target_os:bool=False


GATES=(
    Gate("R61-BASE-001","baseline","R61 release identity and closed MC-11 authority","LOCAL_REGRESSION",30,builtin="baseline"),
    Gate("R61-BASE-002","baseline","R61 focused regression","LOCAL_REGRESSION",180,builtin="focused",required_tools=("pytest",)),
    Gate("R61-BASE-003","baseline","Full bounded repository regression","LOCAL_REGRESSION",900,builtin="full",required_tools=("pytest",)),
    Gate("R61-BASE-004","baseline","MC-11 authority regression retained","LOCAL_REGRESSION",180,builtin="mc11",required_tools=("pytest",)),
    Gate("R61-LOCAL-001","scale","Isolated SQLite synthetic capacity/latency smoke benchmark","LOCAL_SYNTHETIC",300,builtin="benchmark"),
    Gate("R61-SCALE-001","scale","Live device and endpoint capacity matrix","LIVE_PRODUCTION",1800,hook_name="device-endpoint-capacity",required_tools=("psql",),target_os=True),
    Gate("R61-SCALE-002","scale","Live topology node/edge and route capacity matrix","LIVE_PRODUCTION",1800,hook_name="topology-route-capacity",required_tools=("psql",),target_os=True),
    Gate("R61-INGEST-001","ingest","Live syslog sustained/burst events per second","LIVE_PRODUCTION",1800,hook_name="syslog-throughput",required_tools=("psql",),target_os=True),
    Gate("R61-INGEST-002","ingest","Live SNMP trap sustained/burst events per second","LIVE_PRODUCTION",1800,hook_name="trap-throughput",required_tools=("psql",),target_os=True),
    Gate("R61-INGEST-003","ingest","Live external evidence sustained/burst events per second","LIVE_PRODUCTION",1800,hook_name="external-evidence-throughput",required_tools=("psql",),target_os=True),
    Gate("R61-FLOW-001","flow","Live NetFlow v5/v9 flow records per second","LIVE_PRODUCTION",1800,hook_name="netflow-throughput",target_os=True),
    Gate("R61-FLOW-002","flow","Live IPFIX v10 flow records per second","LIVE_PRODUCTION",1800,hook_name="ipfix-throughput",target_os=True),
    Gate("R61-CORR-001","correlation","Live incidents/timeline fan-in and correlation runs per minute","LIVE_PRODUCTION",1800,hook_name="correlation-capacity",required_tools=("psql",),target_os=True),
    Gate("R61-CORR-002","correlation","MC-10 bounded overload under production-scale fan-in","LIVE_PRODUCTION",1800,hook_name="bounded-overload",required_tools=("psql",),target_os=True),
    Gate("R61-OPS-001","operators","Concurrent operator/API capacity and API p50/p95/p99","LIVE_PRODUCTION",1800,hook_name="concurrent-operators-api",target_os=True),
    Gate("R61-OPS-002","operators","Key WebUI persisted-data render p50/p95/p99","LIVE_PRODUCTION",1800,hook_name="webui-render-latency",target_os=True),
    Gate("R61-RES-001","resources","CPU RAM database growth ingest lag and queue saturation","LIVE_PRODUCTION",1800,hook_name="resource-growth-lag",required_tools=("psql",),target_os=True),
)


def run(cmd,timeout,env=None):
    started=time.perf_counter()
    try:
        cp=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,timeout=timeout,env={**os.environ,**(env or {})})
        return cp.returncode,cp.stdout or "",cp.stderr or "",time.perf_counter()-started
    except subprocess.TimeoutExpired as exc:
        so=exc.stdout.decode() if isinstance(exc.stdout,bytes) else (exc.stdout or ""); se=exc.stderr.decode() if isinstance(exc.stderr,bytes) else (exc.stderr or "")
        return 124,so,se+f"\nTIMEOUT after {timeout}s\n",time.perf_counter()-started


def write_log(path:Path,text:str)->dict:
    data=redact(text).encode('utf-8','replace')[:MAX_LOG_BYTES]; path.write_bytes(data)
    return {"path":path.name,"bytes":len(data),"sha256":sha256(path)}


def _baseline_check()->tuple[int,str,str,dict]:
    spec=(ROOT/'packaging/netconfig.spec').read_text(); road=(ROOT/'ROADMAP.md').read_text(); mc11=(ROOT/'opt/netconfig/netconfig/change_planning.py').read_text()
    ok=("Release:        61%{?dist}" in spec and "Release 61" in road
        and "do not create mc-12" in road.lower() and "propose" in mc11.lower())
    return (0 if ok else 1,"R61 identity/authority baseline PASS\n" if ok else "R61 identity/authority baseline FAIL\n","",{})


def _builtin(g:Gate,out:Path):
    if g.builtin=='baseline': return _baseline_check()
    if g.builtin=='focused':
        rc,so,se,d=run([sys.executable,'-m','pytest','-q','tests/test_r61_scale_performance.py'],g.timeout); return rc,so,se,{"duration_seconds":round(d,3)}
    if g.builtin=='full':
        rc,so,se,d=run([sys.executable,'qualification/run_bounded_regression.py','--groups','5','--group-timeout','120'],g.timeout); return rc,so,se,{"duration_seconds":round(d,3)}
    if g.builtin=='mc11':
        rc,so,se,d=run([sys.executable,'-m','pytest','-q','tests/test_mc11_topology_change_planning.py'],g.timeout); return rc,so,se,{"duration_seconds":round(d,3)}
    if g.builtin=='benchmark':
        result_path=out/'metrics'/'local-synthetic-smoke.json'; result_path.parent.mkdir(parents=True,exist_ok=True)
        rc,so,se,d=run([sys.executable,'qualification/r61_benchmark.py','--profile','smoke','--output',str(result_path)],g.timeout)
        metrics={"duration_seconds":round(d,3)}
        if result_path.is_file():
            try: metrics["benchmark"]=json.loads(result_path.read_text())
            except Exception: pass
        return rc,so,se,metrics
    raise RuntimeError(g.builtin)


def run_gate(g:Gate,*,env,out,hook_dir,include_local,live):
    result={"gate_id":g.gate_id,"area":g.area,"title":g.title,"evidence_class":g.evidence_class,"status":NOT_RUN,"reason":"","duration_seconds":0.0,"metrics":{},"logs":{}}
    if g.evidence_class.startswith('LOCAL'):
        if not include_local: result['reason']='local evidence not requested'; return result
        missing=[x for x in g.required_tools if not env['tools'].get(x,False)]
        if missing: result['status']=BLOCKED; result['reason']='missing tool(s): '+','.join(missing); return result
        rc,so,se,metrics=_builtin(g,out)
    else:
        if not live: result['reason']='live production evidence not requested'; return result
        if g.target_os and not (env['os']['id']=='almalinux' and env['os']['version_id'].split('.')[0]=='10'):
            result['status']=BLOCKED; result['reason']='requires AlmaLinux 10 production qualification target'; return result
        missing=[x for x in g.required_tools if not env['tools'].get(x,False)]
        if missing: result['status']=BLOCKED; result['reason']='missing tool(s): '+','.join(missing); return result
        hook=(hook_dir/f'{g.hook_name}.sh') if hook_dir else None
        if not hook or not hook.is_file(): result['status']=NOT_RUN; result['reason']='fixed qualification hook not provided'; return result
        if not os.access(hook,os.X_OK): result['status']=NOT_RUN; result['reason']='qualification hook is not executable'; return result
        scratch=out/'scratch'/g.gate_id; scratch.mkdir(parents=True,exist_ok=True); result_file=scratch/'result.json'
        rc,so,se,d=run([str(hook)],g.timeout,{'NETCONFIG_R61_GATE_ID':g.gate_id,'NETCONFIG_R61_RESULT_PATH':str(result_file),'NETCONFIG_R61_REPO_ROOT':str(ROOT)})
        metrics={"duration_seconds":round(d,3)}
        if result_file.is_file() and result_file.stat().st_size<=256*1024:
            try:
                obj=json.loads(result_file.read_text()); metrics['hook_result']=obj if isinstance(obj,dict) else {}
            except Exception: pass
    result['duration_seconds']=float(metrics.pop('duration_seconds',0.0)); result['metrics']=metrics
    logs=out/'logs'; logs.mkdir(parents=True,exist_ok=True); result['logs']={'stdout':write_log(logs/f'{g.gate_id}.stdout.log',so),'stderr':write_log(logs/f'{g.gate_id}.stderr.log',se)}
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
    ap=argparse.ArgumentParser(description='NetConfig R61 Scale & Performance Qualification runner'); ap.add_argument('--output-dir',required=True); ap.add_argument('--include-local',action='store_true'); ap.add_argument('--live',action='store_true'); ap.add_argument('--hook-dir'); ap.add_argument('--gate',action='append')
    a=ap.parse_args(argv); out=Path(a.output_dir).resolve()
    if out.exists() and any(out.iterdir()): ap.error('output directory must be empty')
    out.mkdir(parents=True,exist_ok=True); env=environment_summary(); hook=Path(a.hook_dir).resolve() if a.hook_dir else None
    selected=set(a.gate or []); known={g.gate_id for g in GATES}
    if selected-known: ap.error('unknown gate id(s): '+','.join(sorted(selected-known)))
    gates=[g for g in GATES if not selected or g.gate_id in selected]; started=datetime.now(timezone.utc).isoformat(); rows=[run_gate(g,env=env,out=out,hook_dir=hook,include_local=a.include_local,live=a.live) for g in gates]
    counts={s:sum(1 for r in rows if r['status']==s) for s in sorted(STATUSES)}; live_pass=sum(1 for r in rows if r['evidence_class']=='LIVE_PRODUCTION' and r['status']==PASS)
    campaign={'campaign':'R61 Scale & Performance Qualification','campaign_id':str(uuid.uuid4()),'product_baseline':'2.0.0-61','schema_revision':'mc11-topology-change-planning-1','status':'IMPLEMENTED_TESTING_DEFERRED','started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'environment':env,'status_counts':counts,'live_production_pass_count':live_pass,'production_capacity_claim':bool(live_pass),'release_promotion_performed':False,'gates':rows}
    (out/'campaign.json').write_text(json.dumps(campaign,indent=2,sort_keys=True)+'\n'); (out/'gate-catalog.json').write_text(json.dumps([asdict(g) for g in GATES],indent=2,sort_keys=True)+'\n')
    lines=['# NetConfig R61 Scale & Performance Evidence','',f"- Product: `{campaign['product_baseline']}`",f"- PASS: **{counts[PASS]}**",f"- FAIL: **{counts[FAIL]}**",f"- BLOCKED_ENVIRONMENT: **{counts[BLOCKED]}**",f"- NOT_RUN: **{counts[NOT_RUN]}**",f"- LIVE_PRODUCTION PASS: **{live_pass}**",'', 'LOCAL_SYNTHETIC measurements are engineering evidence only and never establish production capacity. MC-10 hard bounds remain authoritative under overload.','', '| Gate | Class | Status | Title |','|---|---|---|---|']
    for r in rows: lines.append(f"| `{r['gate_id']}` | {r['evidence_class']} | **{r['status']}** | {r['title']} |")
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n'); checksums(out); print(json.dumps(counts,sort_keys=True)); return 1 if counts[FAIL] else 0


if __name__=='__main__': raise SystemExit(main())
