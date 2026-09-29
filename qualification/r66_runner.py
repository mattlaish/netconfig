#!/usr/bin/env python3
"""R66 Observability / Supportability qualification runner.

Local evidence proves bounded read-only observability/supportability behavior only.
A production supportability claim requires every fixed LIVE_SUPPORT hook to pass
on the designated target with real services, PostgreSQL, collectors and failure injection.
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
        "live_support_opt_in": os.environ.get("NETCONFIG_R66_LIVE_SUPPORT") == "1",
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
    Gate("R66-BASE-001", "baseline", "R66 release/schema/authority identity", "LOCAL_REGRESSION", "baseline", timeout=30),
    Gate("R66-BASE-002", "baseline", "R66 focused supportability regression", "LOCAL_REGRESSION", "focused", timeout=300, required_tools=("pytest",)),
    Gate("R66-BASE-003", "baseline", "Full bounded repository regression", "LOCAL_REGRESSION", "full", timeout=900, required_tools=("pytest",)),
    Gate("R66-BASE-004", "baseline", "MC-11 authority regression retained", "LOCAL_REGRESSION", "mc11", timeout=180, required_tools=("pytest",)),
    Gate("R66-LOCAL-001", "observability", "Read-only health/lag/queue/drop/last-success snapshot", "LOCAL_SUPPORT", "snapshot", timeout=180, required_tools=("pytest",)),
    Gate("R66-LOCAL-002", "support", "Sanitized bounded support-bundle regression", "LOCAL_SUPPORT", "bundle", timeout=180, required_tools=("pytest",)),
    Gate("R66-SUP-001", "health", "Health/readiness/request-correlation under service restart", "LIVE_SUPPORT", hook_name="health-readiness-restart"),
    Gate("R66-SUP-002", "metrics", "Prometheus scrape continuity and bounded cardinality", "LIVE_SUPPORT", hook_name="metrics-scrape-cardinality"),
    Gate("R66-SUP-003", "database", "PostgreSQL outage/recovery telemetry and readiness", "LIVE_SUPPORT", hook_name="postgres-outage-recovery"),
    Gate("R66-SUP-004", "queues", "Distributed queue backlog/lease/recovery visibility", "LIVE_SUPPORT", hook_name="queue-backlog-recovery"),
    Gate("R66-SUP-005", "ingest", "Syslog/trap/external-ingest drops and rejections visible", "LIVE_SUPPORT", hook_name="ingest-drop-rejection"),
    Gate("R66-SUP-006", "connectors", "Connector lag/error/last-success supportability", "LIVE_SUPPORT", hook_name="connector-last-success"),
    Gate("R66-SUP-007", "correlation", "Correlation backlog/latency/failure visibility", "LIVE_SUPPORT", hook_name="correlation-backlog-latency"),
    Gate("R66-SUP-008", "retention", "Disk pressure/retention/log lifecycle visibility", "LIVE_SUPPORT", hook_name="disk-retention-lifecycle"),
    Gate("R66-SUP-009", "bundle", "Independent support-bundle redaction/integrity review", "LIVE_SUPPORT", hook_name="support-bundle-review"),
    Gate("R66-SUP-010", "support", "Independent support drill from alert to root evidence", "LIVE_SUPPORT", hook_name="independent-support-drill"),
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
        service = (ROOT / "opt/netconfig/netconfig/supportability.py").read_text()
        ok = (
            "Release:        66%{?dist}" in spec
            and "r66" in roadmap
            and "do not create mc-12" in roadmap
            and "r66-supportability-1" in service
            and '"network_write_authority": False' in service
            and '"device_polling_performed": False' in service
            and '"qualification_claim": False' in service
        )
        return (0 if ok else 1, "R66 supportability baseline " + ("PASS\n" if ok else "FAIL\n"), "", 0.0)
    args = [sys.executable, "-m", "pytest", "-q"]
    if gate.builtin == "focused":
        args += ["tests/test_r66_supportability.py"]
    elif gate.builtin == "snapshot":
        args += ["tests/test_r66_supportability.py", "-k", "snapshot or queue_lag or collector_drop or metrics"]
    elif gate.builtin == "bundle":
        args += ["tests/test_r66_supportability.py", "-k", "support_bundle"]
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
    if gate.evidence_class in {"LOCAL_REGRESSION", "LOCAL_SUPPORT"}:
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
            result["reason"] = "live support evidence not requested"
            return result
        if not env["live_support_opt_in"]:
            result["status"] = BLOCKED
            result["reason"] = "set NETCONFIG_R66_LIVE_SUPPORT=1 only on the designated supportability qualification environment"
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
            {"NETCONFIG_R66_GATE_ID": gate.gate_id, "NETCONFIG_R66_RESULT_PATH": str(metrics), "NETCONFIG_R66_REPO_ROOT": str(ROOT)},
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
    live_rows = [row for row in rows if row["evidence_class"] == "LIVE_SUPPORT"]
    live_pass = sum(row["status"] == PASS for row in live_rows)
    required_live_ids = {gate.gate_id for gate in GATES if gate.evidence_class == "LIVE_SUPPORT"}
    selected_live_ids = {row["gate_id"] for row in live_rows}
    all_required_live_selected = selected_live_ids == required_live_ids
    production_claim = bool(
        all_required_live_selected and live_rows and all(row["status"] == PASS for row in live_rows)
    )
    campaign = {
        "campaign": "R66 Observability / Supportability",
        "campaign_id": str(uuid.uuid4()),
        "product_baseline": "2.0.0-66",
        "schema_revision": "mc11-topology-change-planning-1",
        "status": "IMPLEMENTED_TESTING_DEFERRED",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "status_counts": counts,
        "live_support_pass_count": live_pass,
        "required_live_support_gate_count": len(required_live_ids),
        "all_required_live_support_gates_selected": all_required_live_selected,
        "production_supportability_claim": production_claim,
        "release_promotion_performed": False,
        "gates": rows,
    }
    (out / "campaign.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n")
    (out / "gate-catalog.json").write_text(json.dumps([gate.__dict__ for gate in GATES], indent=2, sort_keys=True, default=list) + "\n")
    (out / "SUMMARY.md").write_text(
        "# R66 observability / supportability qualification evidence\n\n"
        f"PASS {counts[PASS]} / FAIL {counts[FAIL]} / BLOCKED_ENVIRONMENT {counts[BLOCKED]} / NOT_RUN {counts[NOT_RUN]}\n\n"
        f"LIVE_SUPPORT PASS: {live_pass}\n\n"
        f"Production supportability claim: {str(campaign['production_supportability_claim']).lower()}\n"
    )
    files = [path for path in out.rglob("*") if path.is_file() and path.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(out).as_posix()}\n" for path in sorted(files))
    )
    print(json.dumps(counts, sort_keys=True))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
