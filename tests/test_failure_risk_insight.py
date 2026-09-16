import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opt", "netconfig"))

from netconfig.analytics.failure_risk import FailureRiskAnalyzer


def test_failure_risk_insight_preserves_tenant_and_evidence():
    analyzer = FailureRiskAnalyzer()
    observation = analyzer.analyze(
        tenant_id="tenant-b",
        object_id="edge-7:xe-0/0/3",
        signals=[
            {
                "signal_type": "PACKET_DROP_INCREASE",
                "source_id": "telemetry:drop-7",
                "severity": "WARNING",
                "metric": "packet_drops",
                "value": "12.5",
            },
            {
                "signal_type": "TELEMETRY_DEGRADATION",
                "source_id": "subscription:55",
                "severity": "WARNING",
            },
        ],
    )
    insight = analyzer.to_insight(observation)

    assert insight["tenant_id"] == "tenant-b"
    assert insight["type"] == "FAILURE_RISK"
    assert insight["object_id"] == "edge-7:xe-0/0/3"
    assert set(insight["evidence"]["evidence_refs"]) == {
        "telemetry:drop-7",
        "subscription:55",
    }
