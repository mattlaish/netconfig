"""R65 persisted operator-journey read model.

This module does not create a second change/approval engine.  It composes the
existing Incident, MC-7/MC-11, Automation Request and Structured Change stores
into one bounded persisted-data-first journey.  Mutations remain owned by those
existing services.
"""
from __future__ import annotations

import json

from .workflow import Workflow


_STAGE_ORDER = (
    "incident",
    "hypothesis",
    "evidence",
    "topology_path",
    "proposed_change",
    "approval",
    "structured_change",
    "validation",
)


def _bounded(value, limit=256):
    return str(value or "").replace("\x00", "").strip()[:limit]


class OperatorWorkflowService:
    """Read-only R65 journey aggregation over existing authoritative stores."""

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self.workflow = Workflow(manager.db, manager)

    def _plans(self, incident_key, limit=100):
        out = []
        for item in self.manager.change_planning.plans(limit=max(1, min(int(limit), 500))):
            if _bounded((item.get("input") or {}).get("incident_ref"), 64) == incident_key:
                out.append(item)
        return out

    def _requests(self, incident_key, plan_id=None, limit=200):
        out = []
        for req in self.workflow.list():
            if req.get("mode") != "automation":
                continue
            try:
                ctx = self.workflow.automation_context(int(req["id"]))
            except ValueError:
                continue
            if ctx.get("incident_ref") != incident_key:
                continue
            if plan_id is not None and int(ctx.get("plan_id") or 0) != int(plan_id):
                continue
            out.append({"request": req, "context": ctx})
            if len(out) >= max(1, min(int(limit), 500)):
                break
        return out

    def _transactions(self, request_id, limit=100):
        approval = f"CR#{int(request_id)}"
        return [
            item for item in self.manager.structured_changes.list(limit=max(1, min(int(limit), 5000)))
            if item.get("approval_ref") == approval or item.get("source_ref") == approval
        ]

    def _post_change_evidence(self, incident, request_id=None, limit=100):
        rows = []
        for link in self.manager.incidents.evidence_links(incident["id"]):
            if link.get("source_type") != "change_event":
                continue
            row = self.conn.execute(
                "SELECT * FROM change_events WHERE id=?", (int(link["source_ref"]),)
            ).fetchone()
            if not row:
                continue
            event = dict(row)
            try:
                event["metadata"] = json.loads(event.pop("metadata_json", "{}") or "{}")
            except (TypeError, json.JSONDecodeError):
                event["metadata"] = {}
            if request_id is not None and int(event.get("request_id") or 0) != int(request_id):
                continue
            rows.append({"link": link, "event": event})
            if len(rows) >= max(1, min(int(limit), 500)):
                break
        return rows

    @staticmethod
    def _stage(key, state, summary, **extra):
        return {"key": key, "state": state, "summary": _bounded(summary, 500), **extra}

    def view(self, incident_ref, *, plan_id=None, request_id=None, transaction_id=None):
        incident = self.manager.incidents.get(incident_ref)
        if not incident:
            raise ValueError("incident not found")
        incident_key = incident["incident_key"]
        investigation = self.manager.operations_console.incident(incident_key, timeline_limit=500)
        hypothesis = investigation.get("current_hypothesis")
        evidence_count = int((investigation.get("impact") or {}).get("evidence_count") or 0)
        if not evidence_count:
            evidence_count = len(investigation.get("timeline") or [])

        plans = self._plans(incident_key)
        selected_plan = None
        if plan_id is not None:
            selected_plan = next((p for p in plans if int(p["id"]) == int(plan_id)), None)
            if selected_plan is None:
                raise ValueError("change plan is not linked to this incident workflow")
        elif plans:
            selected_plan = plans[0]
        proposals = list(((selected_plan or {}).get("result") or {}).get("proposed_structured_changes") or [])

        requests = self._requests(incident_key, int(selected_plan["id"]) if selected_plan else None)
        selected_request = None
        if request_id is not None:
            selected_request = next((r for r in requests if int(r["request"]["id"]) == int(request_id)), None)
            if selected_request is None:
                raise ValueError("automation request is not linked to this incident workflow")
        elif requests:
            selected_request = requests[0]

        txs = self._transactions(selected_request["request"]["id"]) if selected_request else []
        selected_tx = None
        if transaction_id is not None:
            selected_tx = next((tx for tx in txs if int(tx["id"]) == int(transaction_id)), None)
            if selected_tx is None:
                raise ValueError("structured transaction is not linked to this workflow request")
        elif txs:
            selected_tx = txs[0]

        post = self._post_change_evidence(
            incident, int(selected_request["request"]["id"]) if selected_request else None)

        stages = []
        stages.append(self._stage(
            "incident", "COMPLETE", f"{incident_key} · {incident.get('status')}", incident=incident_key))
        stages.append(self._stage(
            "hypothesis", "COMPLETE" if hypothesis else "ACTION_REQUIRED",
            (hypothesis or {}).get("summary") or "No active deterministic hypothesis; correlate persisted evidence first.",
            hypothesis_key=(hypothesis or {}).get("hypothesis_key") or ""))
        stages.append(self._stage(
            "evidence", "COMPLETE" if evidence_count else "ACTION_REQUIRED",
            f"{evidence_count} persisted investigation evidence/timeline item(s).", count=evidence_count))
        if selected_plan:
            stages.append(self._stage(
                "topology_path", "COMPLETE",
                f"PLAN#{selected_plan['id']} · {selected_plan.get('planning_status')}", plan_id=int(selected_plan["id"])))
        else:
            stages.append(self._stage(
                "topology_path", "ACTION_REQUIRED",
                "No incident-linked MC-11 path/change plan has been persisted."))
        if selected_plan and proposals:
            stages.append(self._stage(
                "proposed_change", "COMPLETE", f"{len(proposals)} schema-bounded proposal(s) available.", count=len(proposals)))
        elif selected_plan and selected_plan.get("planning_status") == "NO_EVIDENCE_BACKED_GAP":
            stages.append(self._stage(
                "proposed_change", "NO_CHANGE_REQUIRED", "The persisted plan has no evidence-backed configuration gap."))
        else:
            stages.append(self._stage(
                "proposed_change", "WAITING" if not selected_plan else "ACTION_REQUIRED",
                "No schema-bounded Structured Change proposal is currently available."))

        req = (selected_request or {}).get("request") or {}
        if req:
            req_state = str(req.get("status") or "").upper()
            stage_state = {
                "PENDING": "ACTION_REQUIRED", "APPROVED": "COMPLETE", "EXECUTED": "COMPLETE",
                "FAILED": "FAILED", "REJECTED": "REJECTED", "CANCELLED": "CANCELLED",
            }.get(req_state, req_state or "WAITING")
            stages.append(self._stage(
                "approval", stage_state, f"CR#{req['id']} · {req.get('status')}", request_id=int(req["id"])))
        else:
            stages.append(self._stage(
                "approval", "WAITING" if not proposals else "ACTION_REQUIRED",
                "No Automation Request has been submitted from this plan proposal."))

        if selected_tx:
            tx_state = str(selected_tx.get("state") or "")
            stages.append(self._stage(
                "structured_change", tx_state or "WAITING",
                f"TX#{selected_tx['id']} · {tx_state}", transaction_id=int(selected_tx["id"])))
        else:
            stages.append(self._stage(
                "structured_change", "WAITING" if not req or req.get("status") != "executed" else "ACTION_REQUIRED",
                "No linked Structured Change transaction has been recorded."))

        if selected_tx and selected_tx.get("state") == "RECOVERY_REQUIRED":
            validation_state = "RECOVERY_REQUIRED"
            validation_summary = "Remote write outcome is uncertain; operator recovery/verification is required."
        elif selected_tx and selected_tx.get("state") == "FAILED":
            validation_state = "FAILED"
            validation_summary = f"Structured Change failed; verification={selected_tx.get('verification_state') or 'FAILED'}."
        elif selected_tx and selected_tx.get("state") == "SUCCEEDED":
            verified = selected_tx.get("verification_state") in {"VERIFIED", "ALREADY_COMPLIANT"}
            if verified and post:
                validation_state = "COMPLETE"
                validation_summary = (
                    f"Post-change verification={selected_tx.get('verification_state')}; "
                    f"{len(post)} linked change-event evidence item(s) returned to the Incident."
                )
            elif verified:
                validation_state = "ACTION_REQUIRED"
                validation_summary = "Structured Change verified but post-change Incident evidence is not linked yet."
            else:
                validation_state = "ACTION_REQUIRED"
                validation_summary = "Structured Change completed without a terminal verification state."
        else:
            validation_state = "WAITING"
            validation_summary = "Validation waits for an approved Structured Change execution."
        stages.append(self._stage("validation", validation_state, validation_summary, evidence_count=len(post)))

        return {
            "schema": "r65-operator-workflow-1",
            "incident": incident,
            "investigation": investigation,
            "selected_plan": selected_plan,
            "plans": plans[:100],
            "proposals": proposals[:32],
            "selected_request": selected_request,
            "requests": requests[:200],
            "selected_transaction": selected_tx,
            "transactions": txs[:100],
            "post_change_evidence": post[:100],
            "stages": stages,
            "stage_order": list(_STAGE_ORDER),
            "truth": {
                "persisted_data_only": True,
                "page_triggered_polling": False,
                "candidate_what_if_executes": False,
                "approval_bypass": False,
                "direct_network_write_authority": False,
                "root_cause_confirmed": False,
            },
        }
