"""Declarative numeric conversion and health rules. Never evaluate expressions."""
from decimal import Decimal, DecimalException
import math

FIELDS = {"scale", "offset", "minimum", "maximum", "warning_above", "critical_above", "warning_below", "critical_below"}


def validate_numeric(raw):
    if raw is None:
        return None
    if not isinstance(raw, dict) or not raw or set(raw) - FIELDS:
        raise ValueError("numeric must be a non-empty object containing supported conversion/threshold fields")
    for key, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value) > 1e12 or not math.isfinite(value):
            raise ValueError(f"numeric.{key} must be a finite number within +/- 1e12")
    if raw.get("scale", 1) <= 0:
        raise ValueError("numeric.scale must be positive")
    if raw.get("minimum", -1e12) > raw.get("maximum", 1e12):
        raise ValueError("numeric minimum must not exceed maximum")
    for direction in ("above", "below"):
        warning, critical = raw.get("warning_" + direction), raw.get("critical_" + direction)
        if warning is not None and critical is not None:
            if (direction == "above" and critical < warning) or (direction == "below" and critical > warning):
                raise ValueError("critical threshold must be beyond the warning threshold")
    if raw.get("warning_below", -1e12) >= raw.get("warning_above", 1e12):
        raise ValueError("lower and upper warning thresholds must not overlap")
    for key, value in raw.items():
        if key.startswith(("warning_", "critical_")) and not raw.get("minimum", -1e12) <= value <= raw.get("maximum", 1e12):
            raise ValueError("thresholds must lie within the numeric measurement range")
    return dict(raw)


def rule_text(rule):
    if not rule:
        return "No numeric health thresholds configured"
    parts = []
    for key, label, sign in (("warning_above", "Warning", ">="), ("critical_above", "Critical", ">="),
                              ("warning_below", "Warning", "<="), ("critical_below", "Critical", "<=")):
        if key in rule:
            parts.append(f"{label} {sign} {rule[key]}")
    return "; ".join(parts) or "Conversion only; no numeric health thresholds configured"


def reading(spec, value, status):
    """Return displayed value/status/note/threshold. Ranges apply AFTER conversion."""
    rule = spec.get("numeric")
    if not rule:
        kind = str(spec.get("sensor_type") or "").rsplit(".", 1)[-1]
        if kind in {"cpu", "memory", "processor_cpu", "vdom_cpu", "vdom_memory"}:
            return value, "UNKNOWN", "No numeric health policy in this profile; update the profile before judging this measurement.", rule_text(None)
        return value, status, "", ""
    policy = rule_text(rule)
    try:
        raw = Decimal(str(value).strip())
        converted = raw * Decimal(str(rule.get("scale", 1))) + Decimal(str(rule.get("offset", 0)))
        if not raw.is_finite() or not converted.is_finite() or abs(converted) > Decimal("1e18"):
            raise ValueError
        if "minimum" in rule and converted < Decimal(str(rule["minimum"])):
            raise ValueError
        if "maximum" in rule and converted > Decimal(str(rule["maximum"])):
            raise ValueError
    except (DecimalException, ValueError, OverflowError):
        return value, "UNKNOWN", "Invalid or out-of-range numeric reading; health could not be assessed.", policy
    text = format(converted, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    text = "0" if converted == 0 else text
    health = "OK"
    thresholds = [key for key in rule if key.startswith(("warning_", "critical_"))]
    if not thresholds:
        health = "UNKNOWN"
    for level in ("warning", "critical"):
        for direction in ("above", "below"):
            key = level + "_" + direction
            if key in rule:
                bound = Decimal(str(rule[key]))
                if (converted >= bound if direction == "above" else converted <= bound):
                    health = level.upper()
    if status == "CRITICAL" or (status == "WARNING" and health == "OK") or status == "UNKNOWN":
        health = status
    return text, health, policy, policy
