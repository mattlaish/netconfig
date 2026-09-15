"""PH-6 Distributed Execution / HA foundation.

Provides framework objects for execution ownership, worker heartbeat,
fencing and recovery coordination. It intentionally does not bypass PH-4
transaction controls.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class WorkerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    DRAINED = "DRAINED"
    FAILED = "FAILED"


@dataclass
class DistributedExecutionTask:
    task_id: str
    intent_id: str
    change_plan_id: str
    transaction_id: str
    target_device: str
    status: TaskStatus = TaskStatus.QUEUED
    assigned_worker: Optional[str] = None
    execution_epoch: int = 0
    retry_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def claim(self, worker_id: str, epoch: int) -> None:
        if self.status != TaskStatus.QUEUED:
            raise ValueError("task is not claimable")
        self.assigned_worker = worker_id
        self.execution_epoch = epoch
        self.status = TaskStatus.CLAIMED


@dataclass
class WorkerHeartbeat:
    worker_id: str
    status: WorkerStatus = WorkerStatus.ACTIVE
    execution_epoch: int = 0
    last_seen: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ExecutionLeader:
    node_id: str
    epoch: int = 1
    acquired_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RecoveryRecord:
    task_id: str
    reason: str
    previous_worker: Optional[str]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class RecoveryCoordinator:
    def recover(self, task: DistributedExecutionTask, reason: str) -> RecoveryRecord:
        task.status = TaskStatus.RECOVERY_REQUIRED
        return RecoveryRecord(task.task_id, reason, task.assigned_worker)
