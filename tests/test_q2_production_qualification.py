from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "qualification/q2_runner.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("q2_runner", RUNNER)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_q2_catalog_covers_approved_campaign_domains():
    mod = _load_runner()
    areas = {g.area for g in mod.GATES}
    assert {"baseline", "platform", "postgresql", "protocol", "external", "recovery", "performance"} <= areas
    titles = " ".join(g.title.lower() for g in mod.GATES)
    for required in ("almalinux", "rollback", "selinux", "postgresql", "snmp", "ssh", "syslog", "trap", "netflow", "external evidence", "clock-skew", "duplicate", "retention", "api latency", "webui"):
        assert required in titles


def test_q2_only_uses_four_canonical_status_values():
    mod = _load_runner()
    assert mod.STATUSES == {"PASS", "FAIL", "BLOCKED_ENVIRONMENT", "NOT_RUN"}


def test_q2_historical_baseline_detects_r60_release_drift_without_rewriting_q2_truth():
    mod = _load_runner()
    rc, stdout, stderr, metrics = mod._baseline_check()
    assert rc == 1
    assert "RPM Release is not 59" in stderr
    assert stdout == ""
    assert metrics["release"] == "2.0.0-59"
    assert metrics["schema_revision"] == "mc11-topology-change-planning-1"
    assert metrics["mc12_defined"] is False


def test_q2_runner_does_not_expose_arbitrary_shell_command_argument():
    source = RUNNER.read_text(encoding="utf-8")
    assert "--command" not in source
    assert "shell=True" not in source
    assert "NETCONFIG_Q2_HOOK_DIR" in source


def test_q2_runner_does_not_capture_process_environment_in_evidence():
    source = RUNNER.read_text(encoding="utf-8")
    assert '"environment": env' in source
    # Host inventory must be an allow-list, not a dump of os.environ.
    env_func = source[source.index("def environment_summary"):source.index("@dataclass", source.index("def environment_summary"))]
    assert "os.environ" not in env_func
    assert "hostname" not in env_func.lower()


def test_q2_live_gate_without_hook_is_blocked_environment(tmp_path):
    mod = _load_runner()
    spec = next(g for g in mod.GATES if g.gate_id == "Q2-PROTO-001")
    result = mod._run_gate(
        spec,
        env=mod.environment_summary(),
        out_dir=tmp_path,
        hook_dir=None,
        live=True,
        include_local=False,
        allow_destructive=False,
    )
    assert result["status"] == "BLOCKED_ENVIRONMENT"


def test_q2_destructive_gate_is_not_run_without_explicit_authorization(tmp_path):
    mod = _load_runner()
    spec = next(g for g in mod.GATES if g.gate_id == "Q2-REC-001")
    result = mod._run_gate(
        spec,
        env=mod.environment_summary(),
        out_dir=tmp_path,
        hook_dir=tmp_path,
        live=True,
        include_local=False,
        allow_destructive=False,
    )
    assert result["status"] == "NOT_RUN"
    assert "--allow-destructive" in result["reason"]


def test_q2_hook_exit_codes_map_to_truth_states(tmp_path):
    mod = _load_runner()
    spec = next(g for g in mod.GATES if g.gate_id == "Q2-PROTO-001")
    for code, expected in ((0, "PASS"), (20, "BLOCKED_ENVIRONMENT"), (21, "NOT_RUN"), (7, "FAIL")):
        hooks = tmp_path / f"hooks-{code}"
        hooks.mkdir()
        hook = hooks / spec.hook_name
        hook.write_text(f"#!/bin/sh\necho result-{code}\nexit {code}\n", encoding="utf-8")
        hook.chmod(0o755)
        out = tmp_path / f"out-{code}"
        out.mkdir()
        result = mod._run_gate(
            spec,
            env=mod.environment_summary(),
            out_dir=out,
            hook_dir=hooks,
            live=True,
            include_local=False,
            allow_destructive=False,
        )
        assert result["status"] == expected


def test_q2_redacts_secret_assignments_and_bearer_tokens():
    mod = _load_runner()
    text = "password=hunter2 token:abcd community=public Authorization=xyz Bearer abc.def.ghi"
    out = mod._redact_text(text)
    for secret in ("hunter2", "abcd", "public", "xyz", "abc.def.ghi"):
        assert secret not in out
    assert out.count("[REDACTED]") >= 5


def test_q2_runner_emits_checksummed_historical_drift_evidence_on_r60_tree(tmp_path):
    out = tmp_path / "evidence"
    cp = subprocess.run(
        [sys.executable, str(RUNNER), "--output-dir", str(out), "--gate", "Q2-BASE-001", "--include-local"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 1
    campaign = json.loads((out / "campaign.json").read_text(encoding="utf-8"))
    assert campaign["status_counts"]["FAIL"] == 1
    assert campaign["release_promotion_performed"] is False
    assert (out / "SUMMARY.md").is_file()
    assert (out / "SHA256SUMS").is_file()
    assert "campaign.json" in (out / "SHA256SUMS").read_text(encoding="utf-8")


def test_q2_output_directory_must_be_empty(tmp_path):
    out = tmp_path / "evidence"
    out.mkdir()
    (out / "existing").write_text("x", encoding="utf-8")
    cp = subprocess.run(
        [sys.executable, str(RUNNER), "--output-dir", str(out), "--gate", "Q2-BASE-001", "--include-local"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cp.returncode != 0
    assert "must be empty" in cp.stderr


def test_q2_example_hooks_are_non_executable_fail_closed_templates():
    for path in (ROOT / "qualification/hooks.example").iterdir():
        if path.name == "README.md":
            continue
        assert not os.access(path, os.X_OK)
        assert "exit 20" in path.read_text(encoding="utf-8")


def test_q2_wrapper_and_runner_have_required_executable_modes():
    assert RUNNER.stat().st_mode & 0o111
    assert (ROOT / "packaging/q2-qualify.sh").stat().st_mode & 0o111


def test_q2_full_regression_uses_bounded_partition_runner():
    runner = (ROOT / "qualification/run_bounded_regression.py")
    assert runner.is_file()
    assert runner.stat().st_mode & 0o111
    source = RUNNER.read_text(encoding="utf-8")
    assert "qualification/run_bounded_regression.py" in source
