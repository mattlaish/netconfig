#!/usr/bin/env python3
"""NetConfig Q2 Production Qualification Campaign runner.

This runner is intentionally outside the product runtime package.  It executes
repeatable qualification gates against the frozen R59/MC-11 baseline and emits
sanitized, checksummed evidence.  It never promotes NetConfig to TESTED or
RELEASED; release-state decisions remain a separate R68 activity.
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
from typing import Iterable
import uuid

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED_ENVIRONMENT"
NOT_RUN = "NOT_RUN"
STATUSES = {PASS, FAIL, BLOCKED, NOT_RUN}
MAX_LOG_BYTES = 64 * 1024
MAX_RESULT_BYTES = 64 * 1024

# Exit codes reserved for gate hooks.  Any other non-zero value is a real FAIL.
HOOK_BLOCKED = 20
HOOK_NOT_RUN = 21

ROOT = Path(__file__).resolve().parents[1]

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|token|community|api[_-]?key|authorization)\s*([=:])\s*([^\s,;]+)"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
]


def _redact_text(value: str) -> str:
    text = value
    for pattern in _SECRET_PATTERNS:
        if "Bearer" in pattern.pattern:
            text = pattern.sub("Bearer [REDACTED]", text)
        else:
            text = pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", text)
    return text


def _redact(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if re.search(r"(?i)(password|passwd|secret|token|community|api[_-]?key|authorization)", str(key)):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _redact(item)
        return out
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    path = Path("/etc/os-release")
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" not in raw or raw.lstrip().startswith("#"):
            continue
        key, value = raw.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def _tool_presence(names: Iterable[str]) -> dict[str, bool]:
    return {name: bool(shutil.which(name)) for name in names}


def _safe_probe(argv: list[str], timeout: int = 5) -> tuple[int, str]:
    try:
        cp = subprocess.run(argv, check=False, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return cp.returncode, (cp.stdout or cp.stderr or "").strip()[:500]


def environment_summary() -> dict:
    osr = _read_os_release()
    tools = _tool_presence(
        [
            "python3", "pytest", "rpm", "rpmbuild", "rpm2cpio", "cpio", "dnf",
            "systemctl", "systemd-analyze", "getenforce", "pg_dump", "pg_restore",
            "psql", "ssh", "snmpwalk", "logger", "tcpdump", "curl",
        ]
    )
    selinux = "unavailable"
    if tools.get("getenforce"):
        _, out = _safe_probe(["getenforce"])
        selinux = out or "unknown"
    systemd = "unavailable"
    if tools.get("systemctl"):
        _, out = _safe_probe(["systemctl", "is-system-running"])
        systemd = out or "unknown"
    return {
        "os": {"id": osr.get("ID", ""), "version_id": osr.get("VERSION_ID", "")},
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "effective_uid_is_root": hasattr(os, "geteuid") and os.geteuid() == 0,
        "selinux_mode": selinux,
        "systemd_state": systemd,
        "tools": tools,
    }


@dataclass(frozen=True)
class GateSpec:
    gate_id: str
    area: str
    title: str
    evidence_class: str  # LOCAL_REGRESSION or LIVE_PRODUCTION
    timeout_seconds: int = 300
    destructive: bool = False
    builtin: str = "hook"
    hook_name: str = ""
    required_tools: tuple[str, ...] = ()
    required_env: tuple[str, ...] = ()
    required_modules: tuple[str, ...] = ()
    target_os_id: str = ""
    target_os_major: str = ""


GATES: tuple[GateSpec, ...] = (
    GateSpec("Q2-BASE-001", "baseline", "R59 release/schema/authority identity", "LOCAL_REGRESSION", 30, builtin="baseline"),
    GateSpec("Q2-BASE-002", "baseline", "Q2 runner self-test", "LOCAL_REGRESSION", 60, builtin="runner_tests", required_tools=("pytest",)),
    GateSpec("Q2-BASE-003", "baseline", "R59 full repository regression", "LOCAL_REGRESSION", 600, builtin="full_regression", required_tools=("pytest",)),
    GateSpec("Q2-BASE-004", "baseline", "MC-11 focused authority regression", "LOCAL_REGRESSION", 180, builtin="mc11_regression", required_tools=("pytest",)),
    GateSpec("Q2-PLAT-001", "platform", "AlmaLinux 10 clean RPM install", "LIVE_PRODUCTION", 1200, True, hook_name="almalinux-clean-install", required_tools=("rpm", "dnf", "systemctl"), target_os_id="almalinux", target_os_major="10"),
    GateSpec("Q2-PLAT-002", "platform", "RPM supported-baseline upgrade", "LIVE_PRODUCTION", 1200, True, hook_name="rpm-upgrade", required_tools=("rpm", "dnf", "systemctl"), target_os_id="almalinux", target_os_major="10"),
    GateSpec("Q2-PLAT-003", "platform", "RPM rollback to prior working baseline", "LIVE_PRODUCTION", 1200, True, hook_name="rpm-rollback", required_tools=("rpm", "dnf", "systemctl"), target_os_id="almalinux", target_os_major="10"),
    GateSpec("Q2-PLAT-004", "platform", "systemd restart recovery", "LIVE_PRODUCTION", 300, True, hook_name="systemd-restart", required_tools=("systemctl",), target_os_id="almalinux", target_os_major="10"),
    GateSpec("Q2-PLAT-005", "platform", "host reboot recovery", "LIVE_PRODUCTION", 1800, True, hook_name="host-reboot", required_tools=("systemctl",), target_os_id="almalinux", target_os_major="10"),
    GateSpec("Q2-PLAT-006", "platform", "SELinux enforcing operation", "LIVE_PRODUCTION", 300, False, hook_name="selinux-enforcing", required_tools=("getenforce",), target_os_id="almalinux", target_os_major="10"),
    GateSpec("Q2-DB-001", "postgresql", "PostgreSQL SQLite→PostgreSQL migration", "LIVE_PRODUCTION", 900, False, builtin="postgres_migration", required_env=("NETCONFIG_TEST_PG_PASSWORD",), required_modules=("psycopg",)),
    GateSpec("Q2-DB-002", "postgresql", "PostgreSQL backup and restore drill", "LIVE_PRODUCTION", 1200, False, builtin="postgres_backup_restore", required_tools=("pg_dump", "pg_restore"), required_env=("NETCONFIG_TEST_PG_PASSWORD",), required_modules=("psycopg",)),
    GateSpec("Q2-DB-003", "postgresql", "PostgreSQL concurrency and advisory locking", "LIVE_PRODUCTION", 900, False, builtin="postgres_concurrency", required_env=("NETCONFIG_TEST_PG_PASSWORD",), required_modules=("psycopg",)),
    GateSpec("Q2-PROTO-001", "protocol", "Real SNMP collection", "LIVE_PRODUCTION", 300, False, hook_name="real-snmp"),
    GateSpec("Q2-PROTO-002", "protocol", "Real SSH configuration collection", "LIVE_PRODUCTION", 300, False, hook_name="real-ssh", required_tools=("ssh",)),
    GateSpec("Q2-PROTO-003", "protocol", "Real syslog ingestion", "LIVE_PRODUCTION", 300, False, hook_name="real-syslog"),
    GateSpec("Q2-PROTO-004", "protocol", "Real SNMP trap ingestion", "LIVE_PRODUCTION", 300, False, hook_name="real-snmp-trap"),
    GateSpec("Q2-PROTO-005", "protocol", "Real NetFlow/IPFIX ingestion", "LIVE_PRODUCTION", 600, False, hook_name="real-netflow-ipfix"),
    GateSpec("Q2-EXT-001", "external", "Real external evidence connector", "LIVE_PRODUCTION", 600, False, hook_name="external-evidence"),
    GateSpec("Q2-REC-001", "recovery", "Worker restart and deterministic recovery", "LIVE_PRODUCTION", 600, True, hook_name="worker-restart"),
    GateSpec("Q2-REC-002", "recovery", "Clock-skew evidence handling", "LIVE_PRODUCTION", 600, False, hook_name="clock-skew"),
    GateSpec("Q2-REC-003", "recovery", "Late/out-of-order evidence handling", "LIVE_PRODUCTION", 600, False, hook_name="late-out-of-order"),
    GateSpec("Q2-REC-004", "recovery", "Duplicate/replay idempotency", "LIVE_PRODUCTION", 600, False, hook_name="duplicate-replay"),
    GateSpec("Q2-REC-005", "recovery", "Retention with authoritative evidence preserved", "LIVE_PRODUCTION", 900, False, hook_name="retention"),
    GateSpec("Q2-PERF-001", "performance", "Representative API latency", "LIVE_PRODUCTION", 900, False, hook_name="api-latency"),
    GateSpec("Q2-PERF-002", "performance", "Representative WebUI render latency", "LIVE_PRODUCTION", 900, False, hook_name="webui-latency"),
)


def _missing_prerequisites(spec: GateSpec, env: dict) -> list[str]:
    missing: list[str] = []
    for tool in spec.required_tools:
        if not env["tools"].get(tool, bool(shutil.which(tool))):
            missing.append(f"tool:{tool}")
    for name in spec.required_env:
        if not os.environ.get(name):
            missing.append(f"env:{name}")
    for name in spec.required_modules:
        try:
            __import__(name)
        except Exception:
            missing.append(f"python-module:{name}")
    if spec.target_os_id and env["os"]["id"] != spec.target_os_id:
        missing.append(f"os:{spec.target_os_id}")
    if spec.target_os_major:
        current = str(env["os"]["version_id"] or "").split(".", 1)[0]
        if current != spec.target_os_major:
            missing.append(f"os-major:{spec.target_os_major}")
    return missing


def _run_process(argv: list[str], *, timeout: int, extra_env: dict[str, str] | None = None) -> tuple[int, str, str, float]:
    started = time.monotonic()
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    try:
        cp = subprocess.run(
            argv,
            cwd=ROOT,
            env=env,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        rc, stdout, stderr = cp.returncode, cp.stdout or "", cp.stderr or ""
    except subprocess.TimeoutExpired as exc:
        rc = 124
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        stderr += f"\nTIMEOUT after {timeout}s"
    return rc, stdout, stderr, time.monotonic() - started


def _baseline_check() -> tuple[int, str, str, dict]:
    errors: list[str] = []
    spec = (ROOT / "packaging/netconfig.spec").read_text(encoding="utf-8")
    db = (ROOT / "opt/netconfig/netconfig/db.py").read_text(encoding="utf-8")
    planner = (ROOT / "opt/netconfig/netconfig/change_planning.py").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    if not re.search(r"(?m)^Release:\s+59%\{\?dist\}\s*$", spec):
        errors.append("RPM Release is not 59")
    schema = "mc11-topology-change-planning-1"
    if schema not in db or schema not in planner:
        errors.append("MC-11 schema revision not present in DB/planner")
    if "do not create mc-12" not in roadmap.lower():
        errors.append("ROADMAP does not explicitly close MC-12")
    if "What-if is read-only" not in roadmap and "what-if" not in roadmap.lower():
        errors.append("ROADMAP lacks candidate what-if truth")
    tests = (ROOT / "tests/test_mc11_topology_change_planning.py").read_text(encoding="utf-8")
    if "proposed_structured_change" not in tests and "structured_change" not in tests.lower():
        errors.append("MC-11 typed proposal regression evidence missing")
    metrics = {
        "release": "2.0.0-59",
        "schema_revision": schema,
        "roadmap_next": "Q2 Production Qualification Campaign",
        "mc12_defined": False,
    }
    if errors:
        return 1, "", "\n".join(errors), metrics
    return 0, "R59/MC-11 baseline identity and authority boundary: PASS\n", "", metrics


def _builtin_command(spec: GateSpec) -> tuple[list[str] | None, dict]:
    if spec.builtin == "baseline":
        return None, {}
    if spec.builtin == "runner_tests":
        return [sys.executable, "-m", "pytest", "-q", "tests/test_q2_production_qualification.py"], {}
    if spec.builtin == "full_regression":
        return [sys.executable, "qualification/run_bounded_regression.py", "--groups", "5"], {}
    if spec.builtin == "mc11_regression":
        return [sys.executable, "-m", "pytest", "-q", "tests/test_mc11_topology_change_planning.py"], {}
    if spec.builtin == "postgres_migration":
        return [sys.executable, "-m", "pytest", "-q", "tests/integration/test_postgres_core_live.py::test_real_sqlite_to_postgres_migration_repairs_serial_sequence"], {"NETCONFIG_INTEGRATION": "1"}
    if spec.builtin == "postgres_backup_restore":
        return [sys.executable, "-m", "pytest", "-q", "tests/integration/test_postgres_core_live.py::test_real_postgres_backup_restore_drill"], {"NETCONFIG_INTEGRATION": "1", "NETCONFIG_POSTGRES_BACKUP_INTEGRATION": "1"}
    if spec.builtin == "postgres_concurrency":
        return [sys.executable, "-m", "pytest", "-q", "tests/integration/test_postgres_core_live.py::test_real_postgres_core_multinode_claim_leadership_and_heartbeat", "tests/integration/test_postgres_core_live.py::test_real_postgres_core_lock_released_when_session_dies"], {"NETCONFIG_INTEGRATION": "1"}
    raise ValueError(f"unsupported builtin {spec.builtin}")


def _write_log(path: Path, text: str) -> dict:
    raw = _redact_text(text).encode("utf-8", errors="replace")
    truncated = len(raw) > MAX_LOG_BYTES
    if truncated:
        raw = raw[:MAX_LOG_BYTES] + b"\n[TRUNCATED]\n"
    path.write_bytes(raw)
    return {"path": path.name, "bytes": len(raw), "sha256": _sha256(path), "truncated": truncated}


def _run_gate(
    spec: GateSpec,
    *,
    env: dict,
    out_dir: Path,
    hook_dir: Path | None,
    live: bool,
    include_local: bool,
    allow_destructive: bool,
) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    base = {
        "gate_id": spec.gate_id,
        "area": spec.area,
        "title": spec.title,
        "evidence_class": spec.evidence_class,
        "started_at": started_at,
        "status": NOT_RUN,
        "reason": "",
        "duration_seconds": 0.0,
        "destructive": spec.destructive,
        "logs": {},
        "metrics": {},
    }
    if spec.evidence_class == "LOCAL_REGRESSION" and not include_local:
        base["reason"] = "local regression not selected"
        return base
    if spec.evidence_class == "LIVE_PRODUCTION" and not live:
        base["reason"] = "live execution not selected"
        return base
    if spec.destructive and not allow_destructive:
        base["reason"] = "destructive live gate requires --allow-destructive"
        return base

    missing = _missing_prerequisites(spec, env)
    if missing:
        base["status"] = BLOCKED
        base["reason"] = "missing qualification prerequisites: " + ", ".join(missing)
        return base

    stdout = stderr = ""
    metrics: dict = {}
    if spec.builtin != "hook":
        if spec.builtin == "baseline":
            started = time.monotonic()
            rc, stdout, stderr, metrics = _baseline_check()
            duration = time.monotonic() - started
        else:
            argv, builtin_env = _builtin_command(spec)
            assert argv is not None
            rc, stdout, stderr, duration = _run_process(argv, timeout=spec.timeout_seconds, extra_env=builtin_env)
    else:
        if hook_dir is None:
            base["status"] = BLOCKED
            base["reason"] = "NETCONFIG_Q2_HOOK_DIR/--hook-dir not configured"
            return base
        hook = hook_dir / spec.hook_name
        if not hook.is_file() or not os.access(hook, os.X_OK):
            base["status"] = BLOCKED
            base["reason"] = f"required executable hook missing: {spec.hook_name}"
            return base
        scratch = out_dir / "scratch" / spec.gate_id
        scratch.mkdir(parents=True, exist_ok=True)
        result_path = scratch / "result.json"
        extra = {
            "NETCONFIG_Q2_GATE_ID": spec.gate_id,
            "NETCONFIG_Q2_RESULT_PATH": str(result_path),
            "NETCONFIG_Q2_REPO_ROOT": str(ROOT),
        }
        rc, stdout, stderr, duration = _run_process([str(hook)], timeout=spec.timeout_seconds, extra_env=extra)
        if result_path.is_file() and result_path.stat().st_size <= MAX_RESULT_BYTES:
            try:
                parsed = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    metrics = _redact(parsed)
            except (OSError, json.JSONDecodeError):
                pass

    base["duration_seconds"] = round(duration, 3)
    logs = out_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    base["logs"] = {
        "stdout": _write_log(logs / f"{spec.gate_id}.stdout.log", stdout),
        "stderr": _write_log(logs / f"{spec.gate_id}.stderr.log", stderr),
    }
    base["metrics"] = _redact(metrics)
    if rc == 0:
        base["status"] = PASS
    elif rc == HOOK_BLOCKED:
        base["status"] = BLOCKED
        base["reason"] = "qualification hook reported blocked environment"
    elif rc == HOOK_NOT_RUN:
        base["status"] = NOT_RUN
        base["reason"] = "qualification hook reported not run"
    else:
        base["status"] = FAIL
        base["reason"] = f"gate command returned {rc}"
    return base


def _write_checksums(out_dir: Path) -> None:
    checksum = out_dir / "SHA256SUMS"
    rows = []
    for path in sorted(p for p in out_dir.rglob("*") if p.is_file() and p != checksum):
        rows.append(f"{_sha256(path)}  {path.relative_to(out_dir).as_posix()}")
    checksum.write_text("\n".join(rows) + "\n", encoding="utf-8")


def _summary_markdown(campaign: dict) -> str:
    counts = campaign["status_counts"]
    lines = [
        "# NetConfig Q2 Production Qualification Evidence",
        "",
        f"- Campaign ID: `{campaign['campaign_id']}`",
        f"- Product baseline: `{campaign['product_baseline']}`",
        f"- Schema: `{campaign['schema_revision']}`",
        f"- Started: `{campaign['started_at']}`",
        f"- Finished: `{campaign['finished_at']}`",
        f"- PASS: **{counts.get(PASS, 0)}**",
        f"- FAIL: **{counts.get(FAIL, 0)}**",
        f"- BLOCKED_ENVIRONMENT: **{counts.get(BLOCKED, 0)}**",
        f"- NOT_RUN: **{counts.get(NOT_RUN, 0)}**",
        "",
        "This bundle is qualification evidence only. It does not promote the product to TESTED or RELEASED.",
        "Simulation/local regression is labeled separately and never substitutes for LIVE_PRODUCTION evidence.",
        "",
        "| Gate | Class | Status | Title |",
        "|---|---|---|---|",
    ]
    for gate in campaign["gates"]:
        lines.append(f"| `{gate['gate_id']}` | {gate['evidence_class']} | **{gate['status']}** | {gate['title']} |")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NetConfig Q2 production qualification campaign runner")
    parser.add_argument("--output-dir", required=True, help="new/empty evidence directory")
    parser.add_argument("--gate", action="append", default=[], help="gate ID to include; repeatable")
    parser.add_argument("--area", action="append", default=[], help="gate area to include; repeatable")
    parser.add_argument("--include-local", action="store_true", help="run selected LOCAL_REGRESSION gates")
    parser.add_argument("--live", action="store_true", help="run selected LIVE_PRODUCTION gates when prerequisites exist")
    parser.add_argument("--allow-destructive", action="store_true", help="allow install/upgrade/restart/reboot/worker-restart gates")
    parser.add_argument("--hook-dir", help="directory containing executable gate hooks")
    parser.add_argument("--list", action="store_true", help="print gate catalog and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.list:
        print(json.dumps([asdict(g) for g in GATES], indent=2, sort_keys=True))
        return 0

    selected = list(GATES)
    if args.gate:
        wanted = set(args.gate)
        selected = [g for g in selected if g.gate_id in wanted]
        unknown = wanted - {g.gate_id for g in selected}
        if unknown:
            raise SystemExit("unknown gate(s): " + ", ".join(sorted(unknown)))
    if args.area:
        areas = set(args.area)
        selected = [g for g in selected if g.area in areas]
    if not selected:
        raise SystemExit("no gates selected")

    out_dir = Path(args.output_dir).resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"output directory must be empty: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = environment_summary()
    hook_dir_value = args.hook_dir or os.environ.get("NETCONFIG_Q2_HOOK_DIR", "")
    hook_dir = Path(hook_dir_value).resolve() if hook_dir_value else None

    campaign_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc).isoformat()
    gates: list[dict] = []
    for spec in selected:
        gate = _run_gate(
            spec,
            env=env,
            out_dir=out_dir,
            hook_dir=hook_dir,
            live=args.live,
            include_local=args.include_local,
            allow_destructive=args.allow_destructive,
        )
        gates.append(gate)
        gate_path = out_dir / "gates"
        gate_path.mkdir(parents=True, exist_ok=True)
        (gate_path / f"{spec.gate_id}.json").write_text(
            json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    counts = {status: 0 for status in (PASS, FAIL, BLOCKED, NOT_RUN)}
    for gate in gates:
        counts[gate["status"]] += 1
    campaign = {
        "campaign": "Q2 Production Qualification Campaign",
        "campaign_id": campaign_id,
        "product_baseline": "2.0.0-59",
        "schema_revision": "mc11-topology-aware-change-planning-1",
        "product_status": "IMPLEMENTED_TESTING_DEFERRED",
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "runner_version": 1,
        "execution": {
            "include_local": bool(args.include_local),
            "live": bool(args.live),
            "allow_destructive": bool(args.allow_destructive),
            "hook_dir_configured": hook_dir is not None,
        },
        "environment": env,
        "status_counts": counts,
        "gates": gates,
        "release_promotion_performed": False,
    }
    (out_dir / "campaign.json").write_text(json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / "SUMMARY.md").write_text(_summary_markdown(campaign), encoding="utf-8")
    _write_checksums(out_dir)
    print(json.dumps({"campaign_id": campaign_id, "status_counts": counts, "output_dir": str(out_dir)}, indent=2, sort_keys=True))
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    raise SystemExit(main())
