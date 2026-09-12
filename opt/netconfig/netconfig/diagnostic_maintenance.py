"""Bounded diagnostic retention maintenance for D.5 closeout.

Automatic maintenance is opt-in.  It never prunes incident-linked protocol
traces, and case-export metadata is retained even when an old archive is
removed so the incident history continues to show that an export once existed.
"""
from __future__ import annotations

import time
from pathlib import Path


def _bounded_int(value, default, low, high):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(low, min(value, high))


def run_once(manager, actor="scheduler", now=None):
    """Apply configured D.5 retention policies once and return a summary."""
    now = float(time.time() if now is None else now)
    settings = manager.settings
    summary = {
        "debug_bundles_removed": [],
        "case_exports_removed": [],
        "protocol_traces_removed": [],
    }

    # Debug bundles are ephemeral support material. Count retention is bounded.
    keep = _bounded_int(settings.get("debug_bundle_keep", 10), 10, 1, 10000)
    from .debug import DebugBundle
    summary["debug_bundles_removed"] = DebugBundle(manager).cleanup(keep)

    # Case archives may be retired by age, but durable export metadata stays in
    # SQLite. list/get then truthfully report available=false.
    case_days = _bounded_int(settings.get("case_export_retention_days", 0), 0, 0, 36500)
    if case_days > 0:
        cutoff = now - (case_days * 86400.0)
        rows = manager.db.conn.execute(
            "SELECT export_key,filename FROM incident_case_exports WHERE created_ts<? ORDER BY created_ts",
            (cutoff,),
        ).fetchall()
        root = Path(manager.paths.home) / "case-exports"
        for row in rows:
            raw = str(row["filename"] or "")
            safe = Path(raw).name
            if not safe or safe != raw or not safe.endswith(".tar.gz"):
                continue
            target = root / safe
            if target.is_file():
                target.unlink()
                summary["case_exports_removed"].append(row["export_key"])

    # Trace retention deliberately excludes incident-linked sessions. Their
    # reference evidence remains available until an operator explicitly handles
    # incident retention in a future lifecycle policy.
    trace_days = _bounded_int(settings.get("protocol_trace_retention_days", 0), 0, 0, 36500)
    if trace_days > 0:
        cutoff = now - (trace_days * 86400.0)
        rows = manager.db.conn.execute(
            "SELECT id,trace_key FROM protocol_trace_sessions "
            "WHERE incident_id IS NULL AND status<>'ACTIVE' AND created_ts<? ORDER BY created_ts",
            (cutoff,),
        ).fetchall()
        if rows:
            ids = [int(row["id"]) for row in rows]
            marks = ",".join("?" for _ in ids)
            manager.db.conn.execute(
                f"DELETE FROM protocol_trace_sessions WHERE id IN ({marks})", ids)
            manager.db.conn.commit()
            summary["protocol_traces_removed"] = [row["trace_key"] for row in rows]

    detail = (
        f"debug={len(summary['debug_bundles_removed'])};"
        f"case={len(summary['case_exports_removed'])};"
        f"trace={len(summary['protocol_traces_removed'])}"
    )
    manager.db.audit(actor, "diagnostic_retention", "d5", detail)
    return summary


def poller(manager, interval, stop_event):
    """Run retention periodically until the console stop event is set."""
    interval = _bounded_int(interval, 0, 60, 7 * 86400)
    if interval <= 0:
        return
    while not stop_event.wait(interval):
        if not manager.ha.accepts_automation_work():
            continue
        try:
            run_once(manager)
        except Exception as exc:  # maintenance failure must not kill the console
            manager.db.audit("scheduler", "diagnostic_retention_failed", "d5", str(exc)[:500])
