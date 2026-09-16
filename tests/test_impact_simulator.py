import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'opt', 'netconfig'))
from netconfig.analytics.impact import ImpactSimulator


def test_impact_bounded_cycle_safe():
    result = ImpactSimulator().simulate("t1", "sw1", [
        {"source":"sw1", "target":"sw2"},
        {"source":"sw2", "target":"sw3"},
        {"source":"sw3", "target":"sw1"},
    ])
    assert [x.affected_object for x in result] == ["sw2", "sw3"]


def test_impact_endpoint_evidence_only():
    result = ImpactSimulator().simulate("t1", "sw1", [], [{"device_id":"sw1","id":"ep1"}])
    assert result[0].object_type == "ENDPOINT"
    assert result[0].evidence_refs


def test_impact_has_no_execution_action():
    insight = ImpactSimulator().to_insight("sw1", [])
    assert insight["type"] == "DEPENDENCY_IMPACT"
    assert "action" not in insight
