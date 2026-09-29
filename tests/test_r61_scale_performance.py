from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qualification'))

import r61_benchmark as bench  # noqa: E402
import r61_runner as runner  # noqa: E402


def test_r61_gate_catalog_covers_approved_capacity_dimensions():
    titles=' '.join(g.title.lower() for g in runner.GATES)
    for token in ('device','endpoint','topology','route','syslog','snmp trap','external evidence','netflow','ipfix','incident','correlation','concurrent operator','webui','cpu','ram','database','ingest lag'):
        assert token in titles


def test_r61_status_model_is_strict():
    assert runner.STATUSES == {'PASS','FAIL','BLOCKED_ENVIRONMENT','NOT_RUN'}


def test_r61_local_and_live_evidence_classes_are_separate():
    assert any(g.evidence_class=='LOCAL_SYNTHETIC' for g in runner.GATES)
    assert any(g.evidence_class=='LIVE_PRODUCTION' for g in runner.GATES)
    assert all(g.evidence_class in {'LOCAL_REGRESSION','LOCAL_SYNTHETIC','LIVE_PRODUCTION'} for g in runner.GATES)


def test_r61_live_scale_gates_are_hook_only():
    live=[g for g in runner.GATES if g.evidence_class=='LIVE_PRODUCTION']
    assert live
    assert all(g.builtin=='hook' and g.hook_name for g in live)


def test_r61_percentiles_are_deterministic():
    values=[1.0,2.0,3.0,4.0,100.0]
    out=bench.latency_summary(values)
    assert out['p50_ms']==3.0
    assert out['p95_ms'] > out['p50_ms']
    assert out['p99_ms'] >= out['p95_ms']


def test_r61_profiles_cover_all_capacity_axes():
    p=bench.PROFILES['smoke']
    assert p.devices > 0 and p.endpoints > p.devices
    assert p.topology_edges > 0 and p.routes > 0
    assert p.syslog_events > 0 and p.trap_events > 0 and p.external_evidence > 0
    assert p.incidents > 0 and p.correlation_runs > 0
    assert p.netflow_records > 0 and p.concurrent_operators > 0
    assert p.overload_links > 2000


def test_r61_netflow_fixture_exercises_real_v5_parser():
    packet=bench._v5_packet(3)
    from netconfig.netflow import NetflowParser
    rows=NetflowParser().parse(packet,'192.0.2.1',now=1.0)
    assert len(rows)==3
    assert rows[0]['proto']=='TCP'
    assert rows[0]['dport']==443


def test_r61_tiny_local_benchmark_is_bounded_and_nonproduction(tmp_path):
    p=bench.Profile(4,8,4,8,10,8,4,3,4,60,4,2,2,5,2100)
    result=bench.run_benchmark(p,tmp_path/'home')
    assert result['evidence_class']=='LOCAL_SYNTHETIC'
    assert result['production_capacity_claim'] is False
    assert result['mc10_overload_probe']['bounded'] is True
    assert result['mc10_overload_probe']['input_links'] > result['mc10_overload_probe']['max_timeline_scan']
    assert result['api_latency']['count']==4
    assert result['webui_dashboard_latency']['count']==2
    assert result['concurrent_operator_api_latency']['count'] >= 2
    assert result['netflow_parser']['ipfix_v10_measured'] is False


def test_r61_benchmark_records_resource_and_db_growth(tmp_path):
    p=bench.Profile(2,4,2,4,4,4,2,2,2,30,2,1,1,2,2100)
    result=bench.run_benchmark(p,tmp_path/'home')
    assert result['resource']['db_tree_after_bytes'] > result['resource']['db_tree_before_bytes']
    assert result['database_counts']['devices']==2
    assert result['database_counts']['l3_route_observations']==4


def test_r61_historical_runner_detects_release_62_baseline_drift(tmp_path):
    out=tmp_path/'evidence'
    cp=subprocess.run([sys.executable,str(ROOT/'qualification/r61_runner.py'),'--output-dir',str(out),'--include-local','--gate','R61-BASE-001'],cwd=ROOT,text=True,capture_output=True)
    assert cp.returncode==1
    campaign=json.loads((out/'campaign.json').read_text())
    assert campaign['status_counts']['FAIL']==1
    assert campaign['release_promotion_performed'] is False
    assert campaign['production_capacity_claim'] is False
    assert campaign['live_production_pass_count']==0


def test_r61_live_gate_without_target_is_not_false_pass(tmp_path):
    out=tmp_path/'live'
    cp=subprocess.run([sys.executable,str(ROOT/'qualification/r61_runner.py'),'--output-dir',str(out),'--live','--gate','R61-SCALE-001'],cwd=ROOT,text=True,capture_output=True)
    assert cp.returncode==0,cp.stdout+cp.stderr
    campaign=json.loads((out/'campaign.json').read_text())
    row=campaign['gates'][0]
    assert row['status'] in {'BLOCKED_ENVIRONMENT','NOT_RUN'}
    assert campaign['live_production_pass_count']==0


def test_r61_runner_redacts_common_secret_patterns():
    text=runner.redact('password=abc token:xyz Authorization: Bearer qwerty')
    assert 'abc' not in text and 'xyz' not in text and 'qwerty' not in text
    assert '[REDACTED]' in text


def test_r61_runner_and_wrapper_modes_are_executable():
    for relative in ('qualification/r61_runner.py','qualification/r61_benchmark.py','packaging/r61-qualify.sh'):
        path=ROOT/relative
        assert path.stat().st_mode & 0o777 == 0o755


def test_r61_runner_has_no_arbitrary_command_argument():
    source=(ROOT/'qualification/r61_runner.py').read_text()
    assert '--command' not in source
    assert 'shell=True' not in source
    assert 'bash -c' not in source


def test_r61_mc10_bounds_remain_authoritative():
    from netconfig.correlation_hardening import CorrelationHardeningService
    bounds=CorrelationHardeningService.bounds()
    assert bounds['max_facts_per_run']==500
    assert bounds['max_incident_timeline_events']==2000
    assert bounds['max_dependency_edges']==1000


def test_r61_history_is_preserved_under_release_63():
    spec=(ROOT/'packaging/netconfig.spec').read_text()
    installer=(ROOT/'packaging/install-rpm.sh').read_text()
    alma=(ROOT/'packaging/q1-qualify-almalinux.sh').read_text()
    assert 'Release:        67.2%{?dist}' in spec
    assert '${RELEASE%%.*} != "67"' in installer
    assert '2.0.0-67.*.noarch' in alma


def test_r61_does_not_create_mc12_or_expand_change_authority():
    roadmap=(ROOT/'ROADMAP.md').read_text().lower()
    assert 'do not create mc-12' in roadmap
    planning=(ROOT/'opt/netconfig/netconfig/change_planning.py').read_text().lower()
    assert 'execute' not in planning[planning.find('class topologychangeplanningservice'):planning.find('class topologychangeplanningservice')+800] or 'does not' in planning
