from opt.netconfig.netconfig.ph6_execution import DistributedExecutionTask, TaskStatus


def test_task_claim():
    task = DistributedExecutionTask("t1", "i1", "p1", "tx1", "device1")
    task.claim("worker1", 1)
    assert task.status == TaskStatus.CLAIMED
    assert task.execution_epoch == 1
