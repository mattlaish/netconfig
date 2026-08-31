"""
workflow.py -- Change-approval workflow and job execution.

The safety story for a hospital network: a junior engineer cannot push config
straight to a switch. They submit a *change request* (what commands, against which
targets). A senior (approver/admin) reviews the exact resolved commands in the
console and approves or rejects. Only an approved request can be executed, and
execution records a job with per-device results. Every transition is written to
the append-only audit trail, so "who requested / approved / executed / affected"
is always answerable.

This module owns the request/job/script tables via the shared connection and
calls Manager.bulk() to do the actual pushing. It never bypasses the manager's
vault gating.
"""

import json
import time

from . import automation as _auto
from .drivers import get_driver


class Scripts:
    """Reusable command templates (the body a request is built from)."""

    def __init__(self, conn):
        self._conn = conn

    def create(self, name, body, description="", platform="", created_by=""):
        cur = self._conn.execute(
            "INSERT INTO scripts (name, description, body, platform, created_by, "
            "created_ts) VALUES (?,?,?,?,?,?)",
            (name, description, body, platform, created_by, time.time()))
        self._conn.commit()
        return cur.lastrowid

    def update(self, sid, **fields):
        allowed = {"name", "description", "body", "platform"}
        sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not sets:
            return
        cols = ", ".join(f"{k}=?" for k in sets)
        self._conn.execute(f"UPDATE scripts SET {cols} WHERE id=?",
                           list(sets.values()) + [sid])
        self._conn.commit()

    def delete(self, sid):
        self._conn.execute("DELETE FROM scripts WHERE id=?", (sid,))
        self._conn.commit()

    def get(self, sid):
        r = self._conn.execute("SELECT * FROM scripts WHERE id=?", (sid,)).fetchone()
        return dict(r) if r else None

    def all(self):
        return [dict(r) for r in self._conn.execute(
            "SELECT * FROM scripts ORDER BY name").fetchall()]


class Workflow:
    def __init__(self, db, manager):
        self.db = db
        self.conn = db.conn
        self.m = manager

    # ---- change requests -------------------------------------------------
    def submit(self, *, title, body, target_kind, target_value, mode,
               requested_by):
        cur = self.conn.execute(
            "INSERT INTO change_requests (title, body, target_kind, target_value, "
            "mode, requested_by, requested_ts, status) "
            "VALUES (?,?,?,?,?,?,?, 'pending')",
            (title, body, target_kind, target_value, mode, requested_by, time.time()))
        self.conn.commit()
        rid = cur.lastrowid
        self.db.audit(requested_by, "submit_request", f"CR#{rid}",
                      f"{mode} on {target_kind}:{target_value} — {title}")
        return rid

    def get(self, rid):
        r = self.conn.execute(
            "SELECT * FROM change_requests WHERE id=?", (rid,)).fetchone()
        return dict(r) if r else None

    def list(self, status=None):
        if status:
            rows = self.conn.execute(
                "SELECT * FROM change_requests WHERE status=? ORDER BY requested_ts DESC",
                (status,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM change_requests ORDER BY requested_ts DESC").fetchall()
        return [dict(r) for r in rows]

    def pending(self):
        return self.list("pending")

    def preview(self, rid):
        """Resolve the request body per target device (what will actually run),
        so an approver reviews concrete commands, not just the template."""
        cr = self.get(rid)
        if not cr:
            return None
        devices = self.m.inv.resolve_target(cr["target_kind"], cr["target_value"],
                                             only_enabled=True)
        out = []
        for d in devices:
            if cr["mode"] == "remediate":
                base = self.m.store.baseline_text(d["name"])
                current = self.m.store.current(d["name"])
                if not base:
                    lines = ["(no baseline set!)"]
                elif current is None:
                    lines = ["(no collected current config; execution will fetch live state)"]
                else:
                    plan = get_driver(d["platform"]).remediation_plan(base, current)
                    lines = plan["commands"] or ["(stored current already matches baseline)"]
                unresolved = []
            else:
                text, unresolved = _auto.substitute(cr["body"], d)
                lines = _auto.commands(text)
            out.append({"device": d["name"], "host": d["host"],
                        "platform": d["platform"], "lines": lines,
                        "unresolved": unresolved})
        return {"request": cr, "targets": out}

    def approve(self, rid, approver):
        cr = self.get(rid)
        if not cr or cr["status"] != "pending":
            raise ValueError("request is not pending")
        self.conn.execute(
            "UPDATE change_requests SET status='approved', reviewed_by=?, "
            "reviewed_ts=? WHERE id=?", (approver, time.time(), rid))
        self.conn.commit()
        self.db.audit(approver, "approve_request", f"CR#{rid}", cr["title"])

    def reject(self, rid, approver, note=""):
        cr = self.get(rid)
        if not cr or cr["status"] != "pending":
            raise ValueError("request is not pending")
        self.conn.execute(
            "UPDATE change_requests SET status='rejected', reviewed_by=?, "
            "reviewed_ts=?, review_note=? WHERE id=?",
            (approver, time.time(), note, rid))
        self.conn.commit()
        self.db.audit(approver, "reject_request", f"CR#{rid}", note or cr["title"])

    def cancel(self, rid, actor):
        cr = self.get(rid)
        if not cr or cr["status"] not in ("pending", "approved"):
            raise ValueError("request cannot be cancelled")
        self.conn.execute("UPDATE change_requests SET status='cancelled' WHERE id=?",
                          (rid,))
        self.conn.commit()
        self.db.audit(actor, "cancel_request", f"CR#{rid}", cr["title"])

    # ---- execution -------------------------------------------------------
    def execute(self, rid, executor, save=False):
        """Execute an approved request. Records a job + per-device results and
        flips the request to executed/failed. Returns the job dict."""
        cr = self.get(rid)
        if not cr:
            raise ValueError("no such request")
        if cr["status"] != "approved":
            raise ValueError(f"request status is {cr['status']!r}, not approved")
        devices = self.m.inv.resolve_target(cr["target_kind"], cr["target_value"],
                                            only_enabled=True)
        job_id = self._start_job(cr, executor)
        affected = ", ".join(d["name"] for d in devices)
        self.db.audit(executor, "execute_request", f"CR#{rid}",
                      f"job#{job_id} on [{affected}]")
        results = self.m.bulk(devices, mode=cr["mode"], body=cr["body"], save=save)
        ok = sum(1 for r in results if r["ok"])
        fail = len(results) - ok
        self._finish_job(job_id, results, ok, fail)
        status = "executed" if fail == 0 else "failed"
        self.conn.execute(
            "UPDATE change_requests SET status=?, job_id=? WHERE id=?",
            (status, job_id, rid))
        self.conn.commit()
        # per-device audit so 'which devices were affected' is explicit
        for r in results:
            self.db.audit(executor, "device_change",
                          f"CR#{rid}/{r['device']}",
                          "ok" if r["ok"] else "FAILED")
        return self.get_job(job_id)

    def run_adhoc(self, *, devices, mode, body, run_by, title="", save=False,
                  extra_vars=None):
        """Execute a job outside the approval flow (e.g. an admin read-only
        'show' across a group, or a collect). Still audited and recorded."""
        job_id = self._start_job(
            {"mode": mode, "title": title or f"ad-hoc {mode}"}, run_by, request_id=None)
        results = self.m.bulk(devices, mode=mode, body=body, save=save,
                              extra_vars=extra_vars)
        ok = sum(1 for r in results if r["ok"])
        self._finish_job(job_id, results, ok, len(results) - ok)
        self.db.audit(run_by, f"adhoc_{mode}", f"job#{job_id}",
                      ", ".join(d["name"] for d in devices))
        return self.get_job(job_id)

    # ---- jobs ------------------------------------------------------------
    def _start_job(self, cr, run_by, request_id="__cr__"):
        rid = cr.get("id") if request_id == "__cr__" else request_id
        cur = self.conn.execute(
            "INSERT INTO jobs (request_id, kind, title, run_by, started_ts) "
            "VALUES (?,?,?,?,?)",
            (rid, cr["mode"], cr.get("title", ""), run_by, time.time()))
        self.conn.commit()
        return cur.lastrowid

    def _finish_job(self, job_id, results, ok, fail):
        for r in results:
            self.conn.execute(
                "INSERT INTO job_results (job_id, device, ok, changed, output, ts) "
                "VALUES (?,?,?,?,?,?)",
                (job_id, r["device"], int(r["ok"]), int(r.get("changed", False)),
                 r["output"], time.time()))
        self.conn.execute(
            "UPDATE jobs SET finished_ts=?, ok_count=?, fail_count=?, summary=? "
            "WHERE id=?",
            (time.time(), ok, fail, f"{ok} ok, {fail} failed", job_id))
        self.conn.commit()

    def get_job(self, job_id):
        j = self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not j:
            return None
        d = dict(j)
        d["results"] = [dict(r) for r in self.conn.execute(
            "SELECT * FROM job_results WHERE job_id=? ORDER BY device", (job_id,))]
        return d

    def jobs(self, limit=100):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM jobs ORDER BY started_ts DESC LIMIT ?", (limit,))]
