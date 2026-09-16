import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'opt', 'netconfig'))

from netconfig.analytics.capacity import CapacityAnalyzer


def test_capacity_warning_from_baseline():
    result = CapacityAnalyzer().analyze('sw1:Gi1/0/1', 'utilization', 85, 30, 'increasing')
    assert result.state == 'WARNING'
    assert result.difference == 55


def test_capacity_insight_has_evidence_only():
    result = CapacityAnalyzer().analyze('sw1:Gi1/0/1', 'utilization', 120, 30)
    insight = CapacityAnalyzer().to_insight(result)
    assert insight['type'] == 'CAPACITY'
    assert 'evidence' in insight
