from netconfig.ph5_api import create_change_plan, evaluate_drift

def test_ph5_api_change_plan():
    p=create_change_plan("i1",["sw1"],[{"vlan":100}])
    assert p["status"]=="PLANNED"

def test_ph5_drift():
    assert evaluate_drift({"a":1},{"a":1})["status"]=="COMPLIANT"
