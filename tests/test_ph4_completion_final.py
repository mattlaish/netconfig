from opt.netconfig.netconfig.ph4_recovery import NetconfCommitState, RecoveryEvidence

def test_confirm_states_exist():
    assert NetconfCommitState.CONFIRM_PENDING
    assert NetconfCommitState.COMMITTED

def test_recovery_evidence_serializes():
    e=RecoveryEvidence.create(transaction_id="tx", failure_stage="verify", failure_reason="mismatch", failed_operation="commit")
    assert e.to_dict()["transaction_id"] == "tx"
