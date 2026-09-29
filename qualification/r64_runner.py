#!/usr/bin/env python3
"""R64 Security Hardening & Independent Abuse Testing qualification runner.

Local abuse/regression evidence proves bounded code behavior only. A production
security claim requires every fixed LIVE_ABUSE hook to pass in the designated
independent target environment.
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
    tools={x:bool(shutil.which(x)) for x in ('python3','pytest','psql','systemctl','ip','curl')}
    return {'os':{'id':rel.get('ID',''),'version_id':rel.get('VERSION_ID','')},'kernel':platform.release(),
            'python':platform.python_version(),'tools':tools,
            'live_abuse_opt_in':os.environ.get('NETCONFIG_R64_LIVE_ABUSE')=='1'}

@dataclass(frozen=True)
class Gate:
    gate_id:str; area:str; title:str; evidence_class:str; builtin:str='hook'; hook_name:str=''; timeout:int=600; required_tools:tuple[str,...]=()

GATES=(
 Gate('R64-BASE-001','baseline','R64 release/schema/authority identity','LOCAL_REGRESSION','baseline',timeout=30),
 Gate('R64-BASE-002','baseline','R64 focused security abuse regression','LOCAL_REGRESSION','focused',timeout=300,required_tools=('pytest',)),
 Gate('R64-BASE-003','baseline','Full bounded repository regression','LOCAL_REGRESSION','full',timeout=900,required_tools=('pytest',)),
 Gate('R64-BASE-004','baseline','MC-11 authority regression retained','LOCAL_REGRESSION','mc11',timeout=180,required_tools=('pytest',)),
 Gate('R64-LOCAL-001','web','Session RBAC CSRF and request-framing abuse suite','LOCAL_ABUSE','web',timeout=180,required_tools=('pytest',)),
 Gate('R64-LOCAL-002','egress','OAuth redirect SSRF and endpoint validation abuse suite','LOCAL_ABUSE','oauth',timeout=180,required_tools=('pytest',)),
 Gate('R64-LOCAL-003','parser','Hostile archive evidence and parser abuse suite','LOCAL_ABUSE','archive',timeout=180,required_tools=('pytest',)),
 Gate('R64-ABUSE-001','authz','Unauthenticated RBAC and object-boundary abuse','LIVE_ABUSE',hook_name='authz-object-boundary'),
 Gate('R64-ABUSE-002','session','CSRF session revocation and secure-cookie abuse','LIVE_ABUSE',hook_name='session-csrf-revocation'),
 Gate('R64-ABUSE-003','token','API-token scope revoke and replay abuse','LIVE_ABUSE',hook_name='api-token-boundary'),
 Gate('R64-ABUSE-004','evidence','Hostile external-evidence oversize and rate corpus','LIVE_ABUSE',hook_name='external-evidence-abuse'),
 Gate('R64-ABUSE-005','egress','RESTCONF SSH OAuth SSRF injection and egress abuse','LIVE_ABUSE',hook_name='egress-transport-abuse'),
 Gate('R64-ABUSE-006','web','XSS CSP headers request-smuggling and body exhaustion','LIVE_ABUSE',hook_name='web-input-exhaustion'),
 Gate('R64-ABUSE-007','parser','Archive parser bomb special-file and traversal corpus','LIVE_ABUSE',hook_name='archive-parser-abuse'),
 Gate('R64-ABUSE-008','secrets','Evidence support-bundle secret leakage and redaction','LIVE_ABUSE',hook_name='secret-leakage-redaction'),
 Gate('R64-ABUSE-009','mc11','MC-11 arbitrary-command proposal and what-if nonexecution abuse','LIVE_ABUSE',hook_name='mc11-nonexecution-abuse'),
 Gate('R64-ABUSE-010','os','RPM permissions SELinux and service-account abuse','LIVE_ABUSE',hook_name='os-rpm-confinement',required_tools=('systemctl',)),
 Gate('R64-ABUSE-011','resource','Concurrency resource exhaustion and slow-client abuse','LIVE_ABUSE',hook_name='resource-exhaustion-abuse'),
 Gate('R64-ABUSE-012','independent','Independent assessor consolidated abuse sign-off','LIVE_ABUSE',hook_name='independent-abuse-signoff'),
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
        web=(ROOT/'opt/netconfig/netconfig/web.py').read_text(); oauth=(ROOT/'opt/netconfig/netconfig/oauth.py').read_text(); ev=(ROOT/'opt/netconfig/netconfig/evidence_signing.py').read_text()
        ok=('Release:        64%{?dist}' in spec and 'r64' in road and 'do not create mc-12' in road and
            '_session_for(self)' in web and 'PUBLIC_CLOUD_AUTHORITY' in oauth and 'for member in tar' in ev)
        return (0 if ok else 1,'R64 security baseline '+('PASS\n' if ok else 'FAIL\n'),'',0.0)
    args=[sys.executable,'-m','pytest','-q']
    if g.builtin=='focused': args+=['tests/test_r64_security_abuse.py']
    elif g.builtin=='mc11': args+=['tests/test_mc11_topology_change_planning.py']
    elif g.builtin=='web': args+=['tests/test_r64_security_abuse.py','-k','session or throttle or form or content_length or multipart or server_error']
    elif g.builtin=='oauth': args+=['tests/test_r64_security_abuse.py','-k','oauth']
    elif g.builtin=='archive': args+=['tests/test_r64_security_abuse.py','-k','archive']
    elif g.builtin=='full': return run([sys.executable,'qualification/run_bounded_regression.py','--groups','5','--group-timeout','150'],g.timeout)
    else: raise RuntimeError(g.builtin)
    return run(args,g.timeout)

def gate_result(g,env,out,hook_dir,include_local,live):
    r={'gate_id':g.gate_id,'area':g.area,'title':g.title,'evidence_class':g.evidence_class,'status':NOT_RUN,'reason':'','duration_seconds':0.0,'logs':{}}
    if g.evidence_class in {'LOCAL_REGRESSION','LOCAL_ABUSE'}:
        if not include_local: r['reason']='local evidence not requested'; return r
        missing=[x for x in g.required_tools if not env['tools'].get(x)]
        if missing: r['status']=BLOCKED; r['reason']='missing tool(s): '+','.join(missing); return r
        rc,so,se,d=builtin(g)
    else:
        if not live: r['reason']='live abuse evidence not requested'; return r
        if not env['live_abuse_opt_in']:
            r['status']=BLOCKED; r['reason']='set NETCONFIG_R64_LIVE_ABUSE=1 only on the designated independent abuse qualification environment'; return r
        missing=[x for x in g.required_tools if not env['tools'].get(x)]
        if missing: r['status']=BLOCKED; r['reason']='missing tool(s): '+','.join(missing); return r
        hook=hook_dir/f'{g.hook_name}.sh' if hook_dir else None
        if not hook or not hook.is_file(): r['status']=BLOCKED; r['reason']='fixed qualification hook not provided'; return r
        if not os.access(hook,os.X_OK): r['status']=BLOCKED; r['reason']='qualification hook is not executable'; return r
        result=out/'scratch'/g.gate_id/'result.json'; result.parent.mkdir(parents=True,exist_ok=True)
        rc,so,se,d=run([str(hook)],g.timeout,{'NETCONFIG_R64_GATE_ID':g.gate_id,'NETCONFIG_R64_RESULT_PATH':str(result),'NETCONFIG_R64_REPO_ROOT':str(ROOT)})
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
    live_rows=[r for r in rows if r['evidence_class']=='LIVE_ABUSE']; live_pass=sum(r['status']==PASS for r in live_rows)
    campaign={'campaign':'R64 Security Hardening & Independent Abuse Testing','campaign_id':str(uuid.uuid4()),'product_baseline':'2.0.0-64','schema_revision':'mc11-topology-change-planning-1','status':'IMPLEMENTED_TESTING_DEFERRED','finished_at':datetime.now(timezone.utc).isoformat(),'environment':env,'status_counts':counts,'live_abuse_pass_count':live_pass,'production_security_claim':bool(live_rows and all(r['status']==PASS for r in live_rows)),'release_promotion_performed':False,'gates':rows}
    (out/'campaign.json').write_text(json.dumps(campaign,indent=2,sort_keys=True)+'\n')
    (out/'gate-catalog.json').write_text(json.dumps([g.__dict__ for g in GATES],indent=2,sort_keys=True,default=list)+'\n')
    (out/'SUMMARY.md').write_text(f"# R64 security abuse qualification evidence\n\nPASS {counts[PASS]} / FAIL {counts[FAIL]} / BLOCKED_ENVIRONMENT {counts[BLOCKED]} / NOT_RUN {counts[NOT_RUN]}\n\nLIVE_ABUSE PASS: {live_pass}\n\nProduction security claim: {str(campaign['production_security_claim']).lower()}\n")
    files=[p for p in out.rglob('*') if p.is_file() and p.name!='SHA256SUMS']
    (out/'SHA256SUMS').write_text(''.join(f"{sha256(p)}  {p.relative_to(out).as_posix()}\n" for p in sorted(files)))
    print(json.dumps(counts,sort_keys=True)); return 1 if counts[FAIL] else 0
if __name__=='__main__': raise SystemExit(main())
