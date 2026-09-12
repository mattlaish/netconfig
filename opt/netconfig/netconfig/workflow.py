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

import hashlib
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

    @staticmethod
    def _automation_body(payload):
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _automation_hash(cls, snapshot):
        return hashlib.sha256(cls._automation_body(snapshot).encode("utf-8")).hexdigest()

    def _normalize_automation_intent(self, intent):
        if not isinstance(intent, dict):
            raise ValueError("automation intent must be an object")
        kind = str(intent.get("kind") or "").strip().lower()
        allowed = {
            "structured_change": {"kind", "device", "resource", "selectors", "value"},
            "desired_apply": {"kind", "desired_state_id", "rollback_on_failure"},
            "campaign_wave": {"kind", "campaign_id"},
            "structured_rollback": {"kind", "transaction_id"},
        }
        if kind not in allowed or set(intent) - allowed[kind]:
            raise ValueError("unsupported automation intent or fields")
        if kind == "structured_change":
            device = str(intent.get("device") or "").strip()
            resource = str(intent.get("resource") or "").strip()
            selectors = intent.get("selectors") or {}
            if not device or not resource or not isinstance(selectors, dict):
                raise ValueError("structured change requires device/resource/selectors")
            if len(selectors) > 8:
                raise ValueError("structured change has too many selectors")
            return {"kind": kind, "device": device, "resource": resource,
                    "selectors": dict(selectors), "value": intent.get("value")}
        if kind == "desired_apply":
            return {
                "kind": kind,
                "desired_state_id": int(intent.get("desired_state_id") or 0),
                "rollback_on_failure": bool(intent.get("rollback_on_failure", True)),
            }
        if kind == "campaign_wave":
            return {"kind": kind, "campaign_id": int(intent.get("campaign_id") or 0)}
        return {"kind": kind, "transaction_id": int(intent.get("transaction_id") or 0)}

    def _automation_snapshot(self, intent):
        kind = intent["kind"]
        if kind == "structured_change":
            dev, profile = self.m._structured_profile_for(intent["device"])
            resolved = self.m.vendor_models.resolve(
                intent["device"], intent["resource"], intent["selectors"], intent.get("value"),
                protocol=profile["protocol"],
            )
            return {
                "kind": kind, "device": dev["name"], "protocol": profile["protocol"],
                "pack": resolved["pack"], "pack_sha256": resolved["pack_sha256"],
                "resource": resolved["resource"], "selectors": resolved["selectors"],
                "value": resolved["value"], "value_type": resolved["value_type"],
            }
        if kind == "desired_apply":
            dsid = int(intent["desired_state_id"])
            item = self.m.desired_state.get(dsid)
            if not item or item["state"] != "PUBLISHED":
                raise ValueError("automation request requires a PUBLISHED desired state")
            plan = self.m.desired_state.plan(dsid)
            return {
                "kind": kind, "desired_state_id": dsid, "name": item["name"],
                "revision": int(item.get("revision") or 1),
                "published_ts": float(item.get("published_ts") or 0),
                "rollback_on_failure": bool(intent.get("rollback_on_failure", True)),
                "plan": plan,
            }
        if kind == "campaign_wave":
            cid = int(intent["campaign_id"])
            item = self.m.campaigns.get(cid)
            if not item or item["state"] != "RUNNING":
                raise ValueError("automation request requires a RUNNING campaign")
            pending = [target for target in item["targets"] if target["state"] == "PENDING"]
            if not pending:
                raise ValueError("campaign has no pending wave")
            wave = min(int(target["wave"]) for target in pending)
            targets = [
                {"target_id": int(target["id"]), "device": target["device"],
                 "ordinal": int(target["ordinal"])}
                for target in pending if int(target["wave"]) == wave
            ]
            ds = self.m.desired_state.get(item["desired_state_id"]) or {}
            current_plan = self.m.desired_state.plan(item["desired_state_id"])
            frozen_plan = item.get("plan") or {}
            wave_devices = {target["device"] for target in targets}
            current_targets = [
                target for target in current_plan.get("targets", []) if target["device"] in wave_devices
            ]
            frozen_targets = [
                target for target in frozen_plan.get("targets", []) if target["device"] in wave_devices
            ]
            if {target["device"] for target in current_targets} != wave_devices:
                raise ValueError(
                    "campaign target no longer belongs to the published desired-state target set; create a new campaign"
                )
            if self._automation_hash({"targets": current_targets}) != self._automation_hash({"targets": frozen_targets}):
                raise ValueError(
                    "campaign structured plan changed after campaign creation; create a new campaign"
                )
            plan = {
                "desired_state_id": int(item["desired_state_id"]),
                "name": frozen_plan.get("name") or ds.get("name") or "",
                "revision": int(frozen_plan.get("revision") or ds.get("revision") or 0),
                "targets": frozen_targets,
            }
            return {
                "kind": kind, "campaign_id": cid, "campaign": item["name"],
                "wave": wave, "targets": targets,
                "desired_state_id": int(item["desired_state_id"]),
                "desired_state_revision": int(ds.get("revision") or 0),
                "plan": plan,
            }
        txid = int(intent["transaction_id"])
        tx = self.m.structured_changes.get(txid)
        if not tx or tx["state"] != "SUCCEEDED" or not tx.get("changed"):
            raise ValueError("rollback request requires a successful changed structured transaction")
        if not tx.get("reversible") or tx.get("pre_value") is None:
            raise ValueError("rollback request requires a transaction with a safe typed pre-image")
        return {
            "kind": kind, "transaction_id": txid, "device": tx["device"],
            "resource": tx["resource"], "post_hash": tx.get("post_hash") or "",
            "pre_hash": tx.get("pre_hash") or "", "reversible": bool(tx.get("reversible")),
        }

    def submit_automation(self, *, title, intent, requested_by):
        normalized = self._normalize_automation_intent(intent)
        snapshot = self._automation_snapshot(normalized)
        payload = {
            "schema": 1,
            "intent": normalized,
            "snapshot": snapshot,
            "snapshot_sha256": self._automation_hash(snapshot),
        }
        rid = self.submit(
            title=title, body=self._automation_body(payload),
            target_kind="automation", target_value=normalized["kind"],
            mode="automation", requested_by=requested_by,
        )
        self.db.audit(requested_by, "submit_automation_request", f"CR#{rid}",
                      f"kind={normalized['kind']};snapshot={payload['snapshot_sha256']}")
        return rid

    def _automation_request(self, cr, *, require_fresh=False):
        if cr.get("mode") != "automation":
            raise ValueError("request is not an automation request")
        try:
            payload = json.loads(cr.get("body") or "")
        except json.JSONDecodeError as exc:
            raise ValueError("automation request body is malformed") from exc
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            raise ValueError("unsupported automation request schema")
        intent = self._normalize_automation_intent(payload.get("intent") or {})
        submitted_snapshot = payload.get("snapshot")
        submitted_hash = str(payload.get("snapshot_sha256") or "")
        if not isinstance(submitted_snapshot, dict) or submitted_hash != self._automation_hash(submitted_snapshot):
            raise ValueError("automation request snapshot integrity check failed")
        current_snapshot = self._automation_snapshot(intent)
        current_hash = self._automation_hash(current_snapshot)
        fresh = current_hash == submitted_hash
        if require_fresh and not fresh:
            raise ValueError("automation request plan changed after submission; submit a new request")
        return {
            "intent": intent, "submitted_snapshot": submitted_snapshot,
            "current_snapshot": current_snapshot, "snapshot_sha256": submitted_hash,
            "snapshot_current_sha256": current_hash, "snapshot_matches": fresh,
        }

    def preview(self, rid):
        """Resolve the exact reviewed plan without executing it."""
        cr = self.get(rid)
        if not cr:
            return None
        if cr["mode"] == "automation":
            auto = self._automation_request(cr, require_fresh=False)
            return {"request": cr, "targets": [], "automation": auto}
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
        if cr.get("mode") == "automation":
            self._automation_request(cr, require_fresh=True)
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
        """Execute an approved request with exact-plan revalidation."""
        cr = self.get(rid)
        if not cr:
            raise ValueError("no such request")
        if cr["status"] != "approved":
            raise ValueError(f"request status is {cr['status']!r}, not approved")
        if cr.get("mode") == "automation":
            return self._execute_automation(cr, executor)
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
        for r in results:
            self.db.audit(executor, "device_change",
                          f"CR#{rid}/{r['device']}",
                          "ok" if r["ok"] else "FAILED")
        return self.get_job(job_id)

    def _execute_automation(self, cr, executor):
        rid = int(cr["id"])
        auto = self._automation_request(cr, require_fresh=True)
        intent = auto["intent"]
        kind = intent["kind"]
        job_id = self._start_job(cr, executor)
        results = []
        try:
            if kind == "structured_change":
                tx = self.m.structured_changes.execute_resource(
                    device=intent["device"], resource=intent["resource"],
                    selectors=intent["selectors"], value=intent.get("value"),
                    actor=executor, approved=True, approval_ref=f"CR#{rid}",
                    source_kind="manual", source_ref=f"CR#{rid}",
                )
                results = [{
                    "device": intent["device"], "ok": tx["state"] == "SUCCEEDED",
                    "changed": bool(tx.get("changed")),
                    "output": f"structured transaction #{tx['id']} state={tx['state']}",
                }]
            elif kind == "structured_rollback":
                tx = self.m.structured_changes.rollback(
                    intent["transaction_id"], actor=executor, approved=True,
                    approval_ref=f"CR#{rid}",
                )
                results = [{
                    "device": tx["device"], "ok": tx["state"] == "SUCCEEDED",
                    "changed": bool(tx.get("changed")),
                    "output": f"rollback transaction #{tx['id']} state={tx['state']}",
                }]
            elif kind == "desired_apply":
                applied = self.m.desired_state.apply(
                    intent["desired_state_id"], actor=executor, approved=True,
                    source_kind="desired_state", source_ref=f"CR#{rid}",
                    approval_ref=f"CR#{rid}",
                    rollback_on_failure=bool(intent.get("rollback_on_failure", True)),
                )
                grouped = {}
                for item in applied["results"]:
                    device = item["device"]
                    slot = grouped.setdefault(device, {"ok": True, "changed": False, "items": []})
                    slot["ok"] = slot["ok"] and bool(item.get("ok"))
                    slot["changed"] = slot["changed"] or bool(item.get("changed"))
                    slot["items"].append(item)
                results = [
                    {"device": device, "ok": data["ok"], "changed": data["changed"],
                     "output": json.dumps(data["items"], sort_keys=True)}
                    for device, data in sorted(grouped.items())
                ]
            elif kind == "campaign_wave":
                campaign = self.m.campaigns.execute_next_wave(
                    intent["campaign_id"], actor=executor, approved=True,
                    approval_ref=f"CR#{rid}",
                )
                wave = int(auto["submitted_snapshot"]["wave"])
                targets = [t for t in campaign["targets"] if int(t["wave"]) == wave]
                results = [
                    {"device": target["device"],
                     "ok": target["state"] == "SUCCEEDED",
                     "changed": target["state"] == "SUCCEEDED",
                     "output": f"campaign_target_state={target['state']};wave={wave}"}
                    for target in targets
                ]
            else:
                raise ValueError("unsupported automation intent")
        except Exception as exc:
            if not results:
                device = str(auto["submitted_snapshot"].get("device") or "automation")
                results = [{"device": device, "ok": False, "changed": False,
                            "output": f"{type(exc).__name__}: {str(exc)[:500]}"}]
        ok = sum(1 for result in results if result["ok"])
        fail = len(results) - ok
        self._finish_job(job_id, results, ok, fail)
        status = "executed" if fail == 0 else "failed"
        self.conn.execute(
            "UPDATE change_requests SET status=?,job_id=? WHERE id=?",
            (status, job_id, rid),
        )
        self.conn.commit()
        self.db.audit(executor, "execute_automation_request", f"CR#{rid}",
                      f"kind={kind};job={job_id};ok={ok};fail={fail}")
        for result in results:
            self.db.audit(executor, "device_change", f"CR#{rid}/{result['device']}",
                          "ok" if result["ok"] else "FAILED")
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
