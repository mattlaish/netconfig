from opt.netconfig.netconfig.ph6_api import ExecutionRegistry
from opt.netconfig.netconfig.ph6_execution import DistributedExecutionTask, WorkerHeartbeat


def test_execution_registry_claim():
    registry = ExecutionRegistry()
    registry.add_worker(WorkerHeartbeat('w1'))
    registry.add_task(DistributedExecutionTask('t1','i1','p1','tx1','d1'))
    registry.claim_task('t1','w1',1)
    assert registry.tasks['t1'].assigned_worker == 'w1'


def test_leader_epoch_increment():
    registry = ExecutionRegistry()
    assert registry.elect_leader('n1').epoch == 1
    assert registry.elect_leader('n2').epoch == 2
