import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "opt", "netconfig"))

from netconfig.analytics.failure_risk import FailureRiskAnalyzer


_FORBIDDEN_KEYS = {
    "action",
    "execute",
    "remediate",
    "shutdown",
    "config",
    "command",
    "payload",
}


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def test_insight_has_no_device_execution_or_remediation_surface():
    analyzer = FailureRiskAnalyzer()
    observation = analyzer.analyze(
        tenant_id="tenant-a",
        object_id="sw1:Gi1/0/1",
        signals=[{
            "signal_type": "LINK_FLAPPING",
            "source_id": "event:88",
            "severity": "WARNING",
        }],
    )
    insight = analyzer.to_insight(observation)
    assert not (_FORBIDDEN_KEYS & set(_walk_keys(insight)))


def test_tenant_context_is_not_derived_from_signal_payload():
    analyzer = FailureRiskAnalyzer()
    observation = analyzer.analyze(
        tenant_id="tenant-authoritative",
        object_id="sw1",
        signals=[{
            "signal_type": "TELEMETRY_DEGRADATION",
            "source_id": "subscription:1",
            "severity": "WARNING",
            "tenant_id": "tenant-attacker",
        }],
    )
    assert observation.tenant_id == "tenant-authoritative"
