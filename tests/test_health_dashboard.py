
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'opt', 'netconfig'))
from netconfig.analytics.health import HealthAnalyzer

def test_health_degraded():
    obs = HealthAnalyzer().analyze("t1","sw1", capacity=50, errors=70, evidence_refs=["telemetry:a"])
    assert obs.overall_state == "DEGRADED"

def test_health_insight_no_action():
    obs = HealthAnalyzer().analyze("t1","sw1")
    insight = HealthAnalyzer().to_insight(obs)
    assert insight["type"] == "HEALTH"
    assert "action" not in insight
