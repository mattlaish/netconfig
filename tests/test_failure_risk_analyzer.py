import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opt", "netconfig"))

from netconfig.analytics.failure_risk import FailureRiskAnalyzer


def test_single_warning_signal_creates_warning_observation():
    observation = FailureRiskAnalyzer().analyze(
        tenant_id="tenant-a",
        object_id="sw1:Gi1/0/1",
        signals=[{
            "signal_type": "INTERFACE_ERROR_SPIKE",
            "source_id": "event:101",
            "severity": "WARNING",
            "metric": "ifInErrors",
            "value": "42",
        }],
    )
    assert observation.tenant_id == "tenant-a"
    assert observation.state == "WARNING"
    assert observation.severity == "WARNING"
    assert observation.evidence_refs == ("event:101",)


def test_correlated_critical_signals_create_critical_risk():
    observation = FailureRiskAnalyzer().analyze(
        tenant_id="tenant-a",
        object_id="sw1:Gi1/0/1",
        signals=[
            {
                "signal_type": "LINK_FLAPPING",
                "source_id": "event:201",
                "severity": "CRITICAL",
            },
            {
                "signal_type": "TEMPERATURE_ANOMALY",
                "source_id": "telemetry:301",
                "severity": "CRITICAL",
            },
        ],
    )
    assert observation.state == "CRITICAL"
    assert observation.confidence >= 0.75
    assert set(observation.evidence_refs) == {"event:201", "telemetry:301"}


def test_no_signals_is_normal_and_does_not_invent_evidence():
    observation = FailureRiskAnalyzer().analyze(
        tenant_id="tenant-a",
        object_id="sw1",
        signals=[],
    )
    assert observation.state == "NORMAL"
    assert observation.severity == "INFO"
    assert observation.evidence_refs == ()
    assert observation.signals == ()


def test_unknown_signal_type_fails_closed():
    with pytest.raises(ValueError, match="unsupported failure-risk signal type"):
        FailureRiskAnalyzer().analyze(
            tenant_id="tenant-a",
            object_id="sw1",
            signals=[{
                "signal_type": "ARBITRARY_OPERATOR_PAYLOAD",
                "source_id": "event:999",
                "severity": "WARNING",
            }],
        )
