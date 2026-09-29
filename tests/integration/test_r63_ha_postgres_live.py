from __future__ import annotations

import os
import time
import uuid

import pytest

from netconfig.postgres_core import PostgresDatabase, postgres_params

pytestmark = pytest.mark.integration


def _params():
    if os.environ.get("NETCONFIG_R63_LIVE_POSTGRES") != "1":
        pytest.skip("requires NETCONFIG_R63_LIVE_POSTGRES=1 and a disposable PostgreSQL qualification database")
    password=os.environ.get("NETCONFIG_TEST_PG_PASSWORD","")
    settings={
        "pg_host":os.environ.get("NETCONFIG_TEST_PG_HOST","127.0.0.1"),
        "pg_port":int(os.environ.get("NETCONFIG_TEST_PG_PORT","5432")),
        "pg_dbname":os.environ.get("NETCONFIG_TEST_PG_DBNAME","netconfig_test"),
        "pg_user":os.environ.get("NETCONFIG_TEST_PG_USER","netconfig"),
        "pg_sslmode":os.environ.get("NETCONFIG_TEST_PG_SSLMODE","prefer"),
        "core_db_application_name":"netconfig-r63-live",
    }
    return postgres_params(settings,password=password)


def test_r63_live_postgres_stale_worker_fencing_and_explicit_replay():
    db1=PostgresDatabase(params=_params()); db2=PostgresDatabase(params=_params())
    queue='r63-'+uuid.uuid4().hex
    try:
        now=time.time()
        task=db1.enqueue_distributed_task(queue,'read-only','{}',now,replay_safe=True)
        first=db1.claim_distributed_task(queue,'worker-a',now,5,instance_id='i-a')
        assert first and first['id']==task['id']
        recovered=db2.recover_expired_distributed_tasks(now+6)
        assert any(r['id']==task['id'] and r['state']=='RECOVERY_REQUIRED' for r in recovered)
        db2.requeue_distributed_task(task['id'],now+7,reason='live replay-safe qualification')
        second=db2.claim_distributed_task(queue,'worker-b',now+8,30,instance_id='i-b')
        assert second['claim_generation']==first['claim_generation']+1
        with pytest.raises(ValueError):
            db1.finish_distributed_task(task['id'],'worker-a',now+9,claim_token=first['claim_token'],claim_generation=first['claim_generation'])
        done=db2.finish_distributed_task(task['id'],'worker-b',now+9,claim_token=second['claim_token'],claim_generation=second['claim_generation'])
        assert done['state']=='DONE'
    finally:
        db1.close(); db2.close()


def test_r63_live_postgres_failure_domain_membership_rows_are_shared():
    db1=PostgresDatabase(params=_params()); db2=PostgresDatabase(params=_params())
    suffix=uuid.uuid4().hex[:8]; now=time.time()
    try:
        db1.register_cluster_node('r63-a-'+suffix,'host-a',1001,now,failure_domain='fd-a',instance_id='ia')
        db2.register_cluster_node('r63-b-'+suffix,'host-b',1002,now,failure_domain='fd-b',instance_id='ib')
        rows=db1.list_cluster_nodes(now-1)
        mine=[r for r in rows if r['node_id'] in {'r63-a-'+suffix,'r63-b-'+suffix}]
        assert {r['failure_domain'] for r in mine}=={'fd-a','fd-b'}
    finally:
        db1.close(); db2.close()


def test_r63_live_postgres_advisory_single_owner_across_sessions():
    db1=PostgresDatabase(params=_params()); db2=PostgresDatabase(params=_params())
    name='r63-lock-'+uuid.uuid4().hex
    try:
        assert db1.try_advisory_lock(name) is True
        assert db2.try_advisory_lock(name) is False
        assert db1.advisory_unlock(name) is True
        assert db2.try_advisory_lock(name) is True
    finally:
        db1.close(); db2.close()
