"""PH-4 completion hardening state/evidence helpers."""
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

class NetconfCommitState:
    COMMIT_REQUESTED="COMMIT_REQUESTED"
    CONFIRM_PENDING="CONFIRM_PENDING"
    CONFIRMED="CONFIRMED"
    CONFIRM_TIMEOUT="CONFIRM_TIMEOUT"
    COMMITTED="COMMITTED"
    ROLLBACK_TRIGGERED="ROLLBACK_TRIGGERED"
    RECOVERY_REQUIRED="RECOVERY_REQUIRED"

@dataclass
class RecoveryEvidence:
    transaction_id: str
    failure_stage: str
    failure_reason: str
    failed_operation: str
    rollback_attempted: bool = False
    rollback_transaction_id: str = ""
    rollback_result: str = ""
    verification_result: str = ""
    operator_identity: str = ""
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def create(cls, **kwargs):
        now=datetime.now(timezone.utc).isoformat()
        kwargs.setdefault("created_at", now)
        return cls(**kwargs)
