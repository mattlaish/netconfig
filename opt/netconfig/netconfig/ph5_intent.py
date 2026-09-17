"""PH-5 Intent / Desired State Automation foundation."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class DesiredStateStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    ARCHIVED = "ARCHIVED"


class IntentStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    PLANNED = "PLANNED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True)
class DesiredStateRevision:
    revision: int
    payload: dict


@dataclass
class DesiredState:
    target: str
    revisions: list[DesiredStateRevision] = field(default_factory=list)
    status: DesiredStateStatus = DesiredStateStatus.DRAFT

    def publish(self):
        self.status = DesiredStateStatus.PUBLISHED


@dataclass
class DriftEvidence:
    target: str
    desired_revision: int
    observed: dict
    compliant: bool
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ChangePlan:
    intent_id: str
    targets: list[str]
    changes: list[dict]
    approval_required: bool = True


def compare_desired(current: dict, desired: dict):
    if current == desired:
        return {"status": "COMPLIANT", "diff": {}}
    return {"status": "DRIFT_DETECTED", "diff": {"current": current, "desired": desired}}
