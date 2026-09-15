from opt.netconfig.netconfig.ph5_intent import *

def test_ph5_foundation():
    d=DesiredState("switch-1")
    d.publish()
    assert d.status == DesiredStateStatus.PUBLISHED
    assert compare_desired({}, {"x":1})["status"]=="DRIFT_DETECTED"
