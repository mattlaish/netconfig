#!/usr/bin/env python3
"""R67.1 Release UI / Authority Consolidation Corrective RC runner.

R67.1 is a corrective release-candidate qualification track after UI/authority consolidation. Local/offline evidence can prove
source/artifact consistency but can never establish production release readiness.
A release-candidate qualification claim requires every fixed LIVE_RC gate to be
selected and PASS against one unchanged candidate fingerprint.
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


def candidate_fingerprint():
    manifest = ROOT / "R67_1_SOURCE_MANIFEST.json"
    if manifest.is_file():
        return {"kind": "R67_1_SOURCE_MANIFEST_SHA256", "sha256": sha256(manifest)}
    # Before final freeze, bind evidence to the critical release metadata rather
    # than pretending that an unfinished source manifest exists.
    h = hashlib.sha256()
    for relative in (
        "packaging/netconfig.spec", "ROADMAP.md", "RELEASE_MANIFEST.json",
        "SBOM.spdx.json", "qualification/r67_1_runner.py", "tests/test_r67_1_release_ui_authority_consolidation.py",
    ):
        path = ROOT / relative
        if path.is_file():
            h.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return {"kind": "PRE_FREEZE_CRITICAL_METADATA_SHA256", "sha256": h.hexdigest()}


def env_summary():
    release = {}
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for line in os_release.read_text(errors="replace").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                release[key] = value.strip().strip('"')
    tools = {name: bool(shutil.which(name)) for name in (
        "python3", "pytest", "git", "rpm", "rpmbuild", "dnf", "systemctl", "psql", "curl",
    )}
    return {
        "os": {"id": release.get("ID", ""), "version_id": release.get("VERSION_ID", "")},
        "kernel": platform.release(),
        "python": platform.python_version(),
        "tools": tools,
        "live_rc_opt_in": os.environ.get("NETCONFIG_R67_1_LIVE_RC") == "1",
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
    Gate("R67.1-BASE-001", "baseline", "R67.1 corrective-RC release/schema/authority identity", "LOCAL_REGRESSION", "baseline", timeout=30),
    Gate("R67.1-BASE-002", "baseline", "R67.1 focused authority/UI regression", "LOCAL_REGRESSION", "focused", timeout=300, required_tools=("pytest",)),
    Gate("R67.1-BASE-003", "baseline", "Full bounded repository regression", "LOCAL_REGRESSION", "full", timeout=900, required_tools=("pytest",)),
    Gate("R67.1-BASE-004", "authority", "MC-11 final-slice authority regression retained", "LOCAL_REGRESSION", "mc11", timeout=180, required_tools=("pytest",)),
    Gate("R67.1-LOCAL-001", "metadata", "Release manifest and SPDX SBOM consistency", "LOCAL_ARTIFACT", "metadata", timeout=120, required_tools=("pytest",)),
    Gate("R67.1-LOCAL-002", "package", "Offline RPM reproducibility and verifier regression", "LOCAL_ARTIFACT", "rpm", timeout=300, required_tools=("pytest",)),
    Gate("R67.1-LOCAL-003", "hygiene", "Repository/package hygiene and executable-mode source contract", "LOCAL_ARTIFACT", "hygiene", timeout=180, required_tools=("pytest",)),
    Gate("R67.1-RC-001", "checkout", "Independent clean checkout, Git modes, quality and build", "LIVE_RC", hook_name="clean-checkout-ci"),
    Gate("R67.1-RC-002", "os-package", "AlmaLinux 10 fresh RPM install, systemd and SELinux", "LIVE_RC", hook_name="almalinux-rpm-install"),
    Gate("R67.1-RC-003", "upgrade", "R67 to R67.1 upgrade/restart/config-state preservation", "LIVE_RC", hook_name="r67-r67_1-upgrade"),
    Gate("R67.1-RC-004", "recovery", "Production backup/restore and rollback drill", "LIVE_RC", hook_name="backup-restore-rollback"),
    Gate("R67.1-RC-005", "database", "PostgreSQL migration/concurrency/outage/recovery", "LIVE_RC", hook_name="postgres-production"),
    Gate("R67.1-RC-006", "ha", "Multi-node failure-domain failover and fencing", "LIVE_RC", hook_name="ha-failure-domain"),
    Gate("R67.1-RC-007", "protocols", "Real protocol/vendor device qualification", "LIVE_RC", hook_name="protocol-vendor-devices"),
    Gate("R67.1-RC-008", "scale", "Production scale/performance/resource qualification", "LIVE_RC", hook_name="scale-performance"),
    Gate("R67.1-RC-009", "security", "Independent security/abuse qualification", "LIVE_RC", hook_name="independent-security"),
    Gate("R67.1-RC-010", "operator", "Independent browser/operator workflow acceptance", "LIVE_RC", hook_name="operator-browser-e2e"),
    Gate("R67.1-RC-011", "support", "Independent observability/supportability drill", "LIVE_RC", hook_name="supportability-drill"),
    Gate("R67.1-RC-012", "mc11", "MC-11 approved change, verification and rollback end-to-end", "LIVE_RC", hook_name="mc11-change-e2e"),
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
        release_manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
        sbom = json.loads((ROOT / "SBOM.spdx.json").read_text())
        ok = (
            "Release:        67.1%{?dist}" in spec
            and "r67.1" in roadmap
            and "corrective rc" in roadmap
            and "do not create mc-12" in roadmap
            and release_manifest.get("current_package") == "2.0.0-67.1"
            and release_manifest.get("schema_revision") == "mc11-topology-change-planning-1"
            and release_manifest.get("release_promotion") == "NOT_PERFORMED"
            and sbom.get("spdxVersion") == "SPDX-2.3"
            and sbom.get("name") == "NetConfig 2.0.0-67.1 source SBOM"
        )
        return (0 if ok else 1, "R67.1 corrective-RC baseline " + ("PASS\n" if ok else "FAIL\n"), "", 0.0)
    args = [sys.executable, "-m", "pytest", "-q"]
    if gate.builtin == "focused":
        args += ["tests/test_r67_1_release_ui_authority_consolidation.py"]
    elif gate.builtin == "metadata":
        args += ["tests/test_r67_release_candidate.py", "-k", "manifest or sbom or metadata"]
    elif gate.builtin == "rpm":
        args += ["tests/test_offline_rpm_builder.py", "tests/test_r67_release_candidate.py", "-k", "rpm"]
    elif gate.builtin == "hygiene":
        args += ["tests/test_repo_hygiene.py", "tests/test_r67_1_release_ui_authority_consolidation.py", "-k", "hygiene or executable or ci_contract"]
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
    if gate.evidence_class in {"LOCAL_REGRESSION", "LOCAL_ARTIFACT"}:
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
            result["status"] = BLOCKED
            result["reason"] = "LIVE_RC not requested"
            return result
        if not env["live_rc_opt_in"]:
            result["status"] = BLOCKED
            result["reason"] = "NETCONFIG_R67_1_LIVE_RC=1 not set"
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
            {
                "NETCONFIG_R67_1_GATE_ID": gate.gate_id,
                "NETCONFIG_R67_1_RESULT_PATH": str(metrics),
                "NETCONFIG_R67_1_REPO_ROOT": str(ROOT),
                "NETCONFIG_R67_1_CANDIDATE_SHA256": candidate_fingerprint()["sha256"],
            },
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
    live_rows = [row for row in rows if row["evidence_class"] == "LIVE_RC"]
    live_pass = sum(row["status"] == PASS for row in live_rows)
    required_live_ids = {gate.gate_id for gate in GATES if gate.evidence_class == "LIVE_RC"}
    selected_live_ids = {row["gate_id"] for row in live_rows}
    all_required_live_selected = selected_live_ids == required_live_ids
    rc_qualified = bool(
        all_required_live_selected and live_rows and all(row["status"] == PASS for row in live_rows)
    )
    campaign = {
        "campaign": "R67.1 Release UI / Authority Consolidation Corrective RC",
        "campaign_id": str(uuid.uuid4()),
        "product_baseline": "2.0.0-67.1",
        "schema_revision": "mc11-topology-change-planning-1",
        "status": "IMPLEMENTED_TESTING_DEFERRED",
        "candidate_fingerprint": candidate_fingerprint(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "status_counts": counts,
        "live_rc_pass_count": live_pass,
        "required_live_rc_gate_count": len(required_live_ids),
        "all_required_live_rc_gates_selected": all_required_live_selected,
        "release_candidate_qualified": rc_qualified,
        "production_release_claim": False,
        "release_promotion_performed": False,
        "evidence_invalidation_rule": "Any candidate source/package change requires a new candidate fingerprint and complete rerun; prior RC evidence is not reusable.",
        "gates": rows,
    }
    (out / "campaign.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n")
    (out / "gate-catalog.json").write_text(json.dumps([gate.__dict__ for gate in GATES], indent=2, sort_keys=True, default=list) + "\n")
    (out / "SUMMARY.md").write_text(
        "# R67.1 corrective-RC qualification evidence\n\n"
        f"PASS {counts[PASS]} / FAIL {counts[FAIL]} / BLOCKED_ENVIRONMENT {counts[BLOCKED]} / NOT_RUN {counts[NOT_RUN]}\n\n"
        f"LIVE_RC PASS: {live_pass}/{len(required_live_ids)}\n\n"
        f"Release candidate qualified: {str(rc_qualified).lower()}\n\n"
        "Production release claim: false\n"
    )
    files = [path for path in out.rglob("*") if path.is_file() and path.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.relative_to(out).as_posix()}\n" for path in sorted(files))
    )
    print(json.dumps(counts, sort_keys=True))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
