"""PH-5 Intent API service helpers.

No direct device mutation is performed here; execution must flow through PH-4.
"""
from .ph5_intent import compare_desired


def create_change_plan(intent_id, targets, changes, approval_required=True):
    return {"intent_id": intent_id, "targets": targets, "changes": changes,
            "approval_required": approval_required, "status": "PLANNED"}


def evaluate_drift(current, desired):
    return compare_desired(current, desired)


def submit_intent_for_approval(intent):
    intent["status"] = "APPROVAL_PENDING"
    return intent


def bind_ph4_transaction(plan, transaction_id):
    plan["transaction_id"] = transaction_id
    return plan
