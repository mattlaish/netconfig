from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'qualification/r60_runner.py'


def load():
    spec=importlib.util.spec_from_file_location('r60_runner',RUNNER); assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod); return mod


def test_r60_catalog_uses_only_truth_states_and_covers_lifecycle_domains():
    m=load(); assert m.STATUSES=={'PASS','FAIL','BLOCKED_ENVIRONMENT','NOT_RUN'}
    titles=' '.join(g.title.lower() for g in m.GATES)
    for token in ('upgrade','failed upgrade','secret','certificate','restart','reboot','crash','disk','log rotation','postgresql'):
        assert token in titles


def test_r60_historical_baseline_detects_current_release_drift_and_preserves_mc11_schema():
    m=load(); rc,so,se,metrics=m.baseline(); assert rc==1; assert "RPM Release is not 60" in se
    assert metrics['release']=='2.0.0-60'; assert metrics['schema_revision']=='mc11-topology-change-planning-1'; assert metrics['mc12_defined'] is False


def test_r60_live_gate_without_lab_is_blocked_or_not_run(tmp_path):
    m=load(); g=next(x for x in m.GATES if x.gate_id=='R60-LIFE-003')
    r=m.run_gate(g,env=m.environment_summary(),out=tmp_path,hook_dir=None,include_local=False,live=True,allow_destructive=True)
    assert r['status']=='BLOCKED_ENVIRONMENT'


def test_r60_destructive_gate_requires_explicit_authorization(tmp_path):
    m=load(); g=next(x for x in m.GATES if x.gate_id=='R60-LIFE-002')
    r=m.run_gate(g,env=m.environment_summary(),out=tmp_path,hook_dir=tmp_path,include_local=False,live=True,allow_destructive=False)
    assert r['status']=='NOT_RUN'; assert '--allow-destructive' in r['reason']


def test_r60_hook_exit_codes_map_to_canonical_states(tmp_path):
    m=load(); g=next(x for x in m.GATES if x.gate_id=='R60-LIFE-003')
    env=m.environment_summary(); env['os']={'id':'almalinux','version_id':'10'}; env['tools'].update({'rpm':True,'dnf':True,'systemctl':True})
    for code,expected in ((0,'PASS'),(20,'BLOCKED_ENVIRONMENT'),(21,'NOT_RUN'),(7,'FAIL')):
        hooks=tmp_path/f'h{code}'; hooks.mkdir(); p=hooks/g.hook_name; p.write_text(f'#!/bin/sh\nexit {code}\n'); p.chmod(0o755)
        out=tmp_path/f'o{code}'; out.mkdir(); r=m.run_gate(g,env=env,out=out,hook_dir=hooks,include_local=False,live=True,allow_destructive=True); assert r['status']==expected


def test_r60_runner_has_no_arbitrary_command_argument_or_shell_true():
    s=RUNNER.read_text(); assert '--command' not in s; assert 'shell=True' not in s; assert 'NETCONFIG_R60_HOOK_DIR' in s


def test_r60_hook_templates_are_non_executable_and_fail_closed():
    for p in (ROOT/'qualification/r60-hooks.example').iterdir():
        if p.name == 'README.md':
            continue
        assert not os.access(p,os.X_OK); assert 'exit 20' in p.read_text()


def test_r60_historical_runner_emits_checksummed_drift_evidence(tmp_path):
    out=tmp_path/'e'; cp=subprocess.run([sys.executable,str(RUNNER),'--output-dir',str(out),'--gate','R60-BASE-001','--include-local'],cwd=ROOT,text=True,capture_output=True)
    assert cp.returncode==1,cp.stdout+cp.stderr
    campaign=json.loads((out/'campaign.json').read_text()); assert campaign['status_counts']['FAIL']==1; assert campaign['release_promotion_performed'] is False
    assert (out/'SHA256SUMS').is_file(); assert 'campaign.json' in (out/'SHA256SUMS').read_text()


def test_r60_wrapper_and_runner_executable_modes():
    for p in (RUNNER,ROOT/'packaging/r60-qualify.sh',ROOT/'packaging/r60-lifecycle-upgrade.sh'):
        assert p.stat().st_mode & 0o111
