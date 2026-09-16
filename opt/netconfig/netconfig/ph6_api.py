"""PH-6 Distributed Execution API service helpers."""
from .ph6_execution import DistributedExecutionTask, ExecutionLeader, WorkerHeartbeat


class ExecutionRegistry:
    def __init__(self):
        self.tasks = {}
        self.workers = {}
        self.leader = None

    def add_task(self, task: DistributedExecutionTask):
        self.tasks[task.task_id] = task
        return task

    def add_worker(self, worker: WorkerHeartbeat):
        self.workers[worker.worker_id] = worker
        return worker

    def claim_task(self, task_id: str, worker_id: str, epoch: int):
        task = self.tasks[task_id]
        task.claim(worker_id, epoch)
        return task

    def elect_leader(self, node_id: str):
        epoch = 1 if self.leader is None else self.leader.epoch + 1
        self.leader = ExecutionLeader(node_id=node_id, epoch=epoch)
        return self.leader
