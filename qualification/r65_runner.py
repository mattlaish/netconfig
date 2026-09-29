#!/usr/bin/env python3
"""R65 Operator Workflow Completion qualification runner.

Local journey evidence proves persisted orchestration and route/API behavior only.
A production operator-workflow claim requires every fixed LIVE_OPERATOR hook to
pass on the designated target with real identities, PostgreSQL, protocols and
Structured Change verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED_ENVIRONMENT"
NOT_RUN = "NOT_RUN"
HOOK_BLOCKED = 20
HOOK_NOT_RUN = 21
ROOT = Path(__file__).resolve().parents[1]
MAX_LOG_BYTES = 64 * 1024
_SECRET = [
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(password|passwd|secret|token|community|api[_-]?key|authorization)\s*([=:])\s*([^\s,;]+)"),
]


def redact(text):
    text = str(text)
    for pattern in _SECRET:
        text = pattern.sub(
            "Bearer [REDACTED]" if "Bearer" in pattern.pattern
            else lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]",
            text,
        )
    return text


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def env_summary():
    release = {}
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for line in os_release.read_text(errors="replace").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                release[key] = value.strip().strip('"')
    tools = {name: bool(shutil.which(name)) for name in ("python3", "pytest", "psql", "systemctl", "curl")}
    return {
        "os": {"id": release.get("ID", ""), "version_id": release.get("VERSION_ID", "")},
        "kernel": platform.release(),
        "python": platform.python_version(),
        "tools": tools,
        "live_operator_opt_in": os.environ.get("NETCONFIG_R65_LIVE_OPERATOR") == "1",
    }


@dataclass(frozen=True)
class Gate:
    gate_id: str
    area: str
    title: str
    evidence_class: str
    builtin: str = "hook"
    hook_name: str = ""
    timeout: int = 600
    required_tools: tuple[str, ...] = ()


GATES = (
    Gate("R65-BASE-001", "baseline", "R65 release/schema/authority identity", "LOCAL_REGRESSION", "baseline", timeout=30),
    Gate("R65-BASE-002", "baseline", "R65 focused operator-workflow regression", "LOCAL_REGRESSION", "focused", timeout=300, required_tools=("pytest",)),
    Gate("R65-BASE-003", "baseline", "Full bounded repository regression", "LOCAL_REGRESSION", "full", timeout=900, required_tools=("pytest",)),
    Gate("R65-BASE-004", "baseline", "MC-11 authority regression retained", "LOCAL_REGRESSION", "mc11", timeout=180, required_tools=("pytest",)),
    Gate("R65-LOCAL-001", "journey", "Persisted Incident-to-validation route/API journey", "LOCAL_WORKFLOW", "journey", timeout=240, required_tools=("pytest",)),
    Gate("R65-OP-001", "browser", "Dashboard Incident Hypothesis Evidence browser continuity", "LIVE_OPERATOR", hook_name="browser-journey"),
    Gate("R65-OP-002", "planning", "Topology/path plan and exact persisted proposal continuity", "LIVE_OPERATOR", hook_name="path-proposal-journey"),
    Gate("R65-OP-003", "approval", "Operator/approver role separation and approval continuity", "LIVE_OPERATOR", hook_name="approval-role-separation"),
    Gate("R65-OP-004", "revalidation", "Frozen snapshot drift rejection before execution", "LIVE_OPERATOR", hook_name="snapshot-revalidation"),
    Gate("R65-OP-005", "execution", "Structured Change exact verification and evidence return", "LIVE_OPERATOR", hook_name="structured-verification"),
    Gate("R65-OP-006", "recovery", "Interrupted Structured Change operator recovery journey", "LIVE_OPERATOR", hook_name="recovery-journey"),
    Gate("R65-OP-007", "rollback", "Approved rollback journey and post-rollback evidence", "LIVE_OPERATOR", hook_name="rollback-journey"),
    Gate("R65-OP-008", "restart", "Persisted journey survives web/node restart", "LIVE_OPERATOR", hook_name="restart-continuity"),
    Gate("R65-OP-009", "concurrency", "Concurrent operators cannot cross-link incident/plan/request/transaction", "LIVE_OPERATOR", hook_name="concurrent-operator-isolation"),
    Gate("R65-OP-010", "acceptance", "Independent operator acceptance of end-to-end workflow", "LIVE_OPERATOR", hook_name="independent-operator-acceptance"),
)


def run(cmd, timeout, env=None):
    started = time.perf_counter()
    try:
        cp = subprocess.run(
            cmd, cwd=ROOT, text=True, capture_output=True, timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        return cp.returncode, cp.stdout or "", cp.stderr or "", time.perf_counter() - started
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return 124, stdout, stderr + f"\nTIMEOUT after {timeout}s\n", time.perf_counter() - started


def write_log(path, text):
    data = redact(text).encode("utf-8", "replace")[:MAX_LOG_BYTES]
    path.write_bytes(data)
    return {"path": path.name, "bytes": len(data), "sha256": sha256(path)}


def builtin(gate):
    if gate.builtin == "baseline":
        spec = (ROOT / "packaging/netconfig.spec").read_text()
        roadmap = (ROOT / "ROADMAP.md").read_text().lower()
        service = (ROOT / "opt/netconfig/netconfig/operator_workflow.py").read_text()
        ok = (
            "Release:        65%{?dist}" in spec
            and "r65" in roadmap
            and "do not create mc-12" in roadmap
            and "r65-operator-workflow-1" in service
            and '"approval_bypass": False' in service
            and '"direct_network_write_authority": False' in service
        )
        return (0 if ok else 1, "R65 operator workflow baseline " + ("PASS\n" if ok else "FAIL\n"), "", 0.0)
    args = [sys.executable, "-m", "pytest", "-q"]
    if gate.builtin == "focused":
        args += ["tests/test_r65_operator_workflow.py"]
    elif gate.builtin == "journey":
        args += ["tests/test_r65_operator_workflow.py", "-k", "workflow or journey or proposal or api"]
    elif gate.builtin == "mc11":
        args += ["tests/test_mc11_topology_change_planning.py"]
    elif gate.builtin == "full":
        return run([sys.executable, "qualification/run_bounded_regression.py", "--groups", "5", "--group-timeout", "150"], gate.timeout)
    else:
        raise RuntimeError(gate.builtin)
    return run(args, gate.timeout)


def gate_result(gate, env, out, hook_dir, include_local, live):
    result = {
        "gate_id": gate.gate_id, "area": gate.area, "title": gate.title,
        "evidence_class": gate.evidence_class, "status": NOT_RUN, "reason": "",
        "duration_seconds": 0.0, "logs": {},
    }
    if gate.evidence_class in {"LOCAL_REGRESSION", "LOCAL_WORKFLOW"}:
        if not include_local:
            result["reason"] = "local evidence not requested"
            return result
        missing = [tool for tool in gate.required_tools if not env["tools"].get(tool)]
        if missing:
            result["status"] = BLOCKED
            result["reason"] = "missing tool(s): " + ",".join(missing)
            return result
        rc, stdout, stderr, duration = builtin(gate)
    else:
        if not live:
            result["reason"] = "live operator evidence not requested"
            return result
        if not env["live_operator_opt_in"]:
            result["status"] = BLOCKED
            result["reason"] = "set NETCONFIG_R65_LIVE_OPERATOR=1 only on the designated operator qualification environment"
            return result
        missing = [tool for tool in gate.required_tools if not env["tools"].get(tool)]
        if missing:
            result["status"] = BLOCKED
            result["reason"] = "missing tool(s): " + ",".join(missing)
            return result
        hook = hook_dir / f"{gate.hook_name}.sh" if hook_dir else None
        if not hook or not hook.is_file():
            result["status"] = BLOCKED
            result["reason"] = "fixed qualification hook not provided"
            return result
        if not os.access(hook, os.X_OK):
            result["status"] = BLOCKED
            result["reason"] = "qualification hook is not executable"
            return result
        metrics = out / "scratch" / gate.gate_id / "result.json"
        metrics.parent.mkdir(parents=True, exist_ok=True)
        rc, stdout, stderr, duration = run(
            [str(hook)], gate.timeout,
            {"NETCONFIG_R65_GATE_ID": gate.gate_id, "NETCONFIG_R65_RESULT_PATH": str(metrics), "NETCONFIG_R65_REPO_ROOT": str(ROOT)},
        )
        if metrics.is_file() and metrics.stat().st_size <= 256 * 1024:
            try:
                result["metrics"] = json.loads(metrics.read_text())
            except Exception:
                result["metrics"] = {}
    result["duration_seconds"] = round(duration, 3)
    logs = out / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    result["logs"] = {
        "stdout": write_log(logs / f"{gate.gate_id}.stdout.log", stdout),
        "stderr": write_log(logs / f"{gate.gate_id}.stderr.log", stderr),
    }
    if rc == 0:
        result["status"] = PASS
    elif rc == HOOK_BLOCKED:
        result["status"] = BLOCKED
        result["reason"] = "qualification hook reported blocked environment"
    elif rc == HOOK_NOT_RUN:
        result["status"] = NOT_RUN
        result["reason"] = "qualification hook reported not run"
    else:
        result["status"] = FAIL
        result["reason"] = f"command exited {rc}"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--hook-dir")
    parser.add_argument("--include-local", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--gate", action="append")
    args = parser.parse_args()
    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = env_summary()
    hooks = Path(args.hook_dir).resolve() if args.hook_dir else None
    selected = [gate for gate in GATES if not args.gate or gate.gate_id in set(args.gate)]
    rows = [gate_result(gate, env, out, hooks, args.include_local, args.live) for gate in selected]
    counts = {status: sum(row["status"] == status for row in rows) for status in (PASS, FAIL, BLOCKED, NOT_RUN)}
    live_rows = [row for row in rows if row["evidence_class"] == "LIVE_OPERATOR"]
    live_pass = sum(row["status"] == PASS for row in live_rows)
    required_live_ids = {gate.gate_id for gate in GATES if gate.evidence_class == "LIVE_OPERATOR"}
    selected_live_ids = {row["gate_id"] for row in live_rows}
    all_required_live_selected = selected_live_ids == required_live_ids
    production_claim = bool(
        all_required_live_selected and live_rows and all(row["status"] == PASS for row in live_rows)
    )
    campaign = {
        "campaign": "R65 Operator Workflow Completion",
        "campaign_id": str(uuid.uuid4()),
        "product_baseline": "2.0.0-65",
        "schema_revision": "mc11-topology-change-planning-1",
        "status": "IMPLEMENTED_TESTING_DEFERRED",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "status_counts": counts,
        "live_operator_pass_count": live_pass,
        "required_live_operator_gate_count": len(required_live_ids),
        "all_required_live_operator_gates_selected": all_required_live_selected,
        "production_operator_workflow_claim": production_claim,
        "release_promotion_performed": False,
        "gates": rows,
    }
    (out / "campaign.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n")
    (out / "gate-catalog.json").write_text(json.dumps([gate.__dict__ for gate in GATES], indent=2, sort_keys=True, default=list) + "\n")
    (out / "SUMMARY.md").write_text(
        "# R65 operator workflow qualification evidence\n\n"
        f"PASS {counts[PASS]} / FAIL {counts[FAIL]} / BLOCKED_ENVIRONMENT {counts[BLOCKED]} / NOT_RUN {counts[NOT_RUN]}\n\n"
        f"LIVE_OPERATOR PASS: {live_pass}\n\n"
        f"Production operator-workflow claim: {str(campaign['production_operator_workflow_claim']).lower()}\n"
    )
    files = [path for path in out.rglob("*") if path.is_file() and path.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(out).as_posix()}\n" for path in sorted(files))
    )
    print(json.dumps(counts, sort_keys=True))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
