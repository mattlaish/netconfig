"""Background monitor engine: runs per-device checks, records history, and
evaluates alert rules, opening/resolving alerts and sending email on change.

Metrics an alert rule can target (kind -> what is compared):
  port_state    (port)  status  is/is_not  open|closed|filtered
  http_status   (http)  value   ==/!=/>/</>=/<=  <code>   (down => always breach)
  response_time (http)  value   >/<   <milliseconds>
  tls_expiry    (tls)   value   </<=/>  <days>
  tls_valid     (tls)   status  is   valid|invalid
"""
import re
import time

from . import portmon, appmon, mailer
from .workspaces import enabled as workspace_enabled

_METRIC_KIND = {
    "port_state": "port",
    "http_status": "http",
    "response_time": "http",
    "tls_expiry": "tls",
    "tls_valid": "tls",
}

METRIC_LABELS = [
    ("port_state", "Port state (system)"),
    ("http_status", "HTTP status (application)"),
    ("response_time", "Response time ms (application)"),
    ("tls_expiry", "TLS days to expiry (application)"),
    ("tls_valid", "TLS certificate valid (application)"),
]

OPS_BY_METRIC = {
    "port_state": ["is", "is_not"],
    "http_status": ["==", "!=", ">", "<", ">=", "<="],
    "response_time": [">", "<", ">=", "<="],
    "tls_expiry": ["<", "<=", ">", ">="],
    "tls_valid": ["is"],
}


def _types(dev):
    raw = dev.get("device_type") or ""
    ts = {t for t in re.split(r"[,\s]+", raw) if t}
    return ts or {"network"}


def saved_check_targets(dev):
    """Use the same targets as the background and on-demand checks."""
    types = _types(dev)
    targets = {}
    if "system" in types:
        targets.update({("port", f"{proto}/{port}"): None
                        for proto, port in portmon.parse_ports(dev.get("monitor_ports"))})
    if "application" in types:
        targets.update({("http", url): expected for url, expected in
                        appmon.parse_targets(dev.get("monitor_urls"), dev["host"])})
    return targets


def check_availability(kind, status, expected=None):
    if kind == "port":
        if status == "open":
            return "up"
        if status == "open|filtered":
            return "unknown"
        return "down" if status in {"closed", "filtered", "error"} else "unknown"
    if status == "down":
        return "down"
    if str(status).isdigit():
        code = int(status)
        ok = code == expected if expected is not None else 200 <= code < 400
        return "up" if ok else "down"
    return "unknown"


def status_max_age(interval):
    seconds = int(interval or 0)
    return max(3600, 3 * seconds) if seconds > 0 else 86400


def status_is_current(timestamp, interval, now=None):
    now = time.time() if now is None else now
    try:
        return 0 <= now - float(timestamp) <= status_max_age(interval)
    except (ValueError, TypeError):
        return False


def snmp_availability(facts, settings, now=None):
    if not facts:
        return "not polled"
    if not status_is_current(facts.get("last_polled"), settings.get("snmp_poll_interval"), now):
        return "out of date"
    return "up" if facts.get("reachable") else "unreachable"


def saved_availability(manager, dev, now, rows=None):
    targets = saved_check_targets(dev)
    if rows is None:
        rows = manager.db.latest_monitor_results(dev["name"], targets)
    interval = int(manager.settings.get("monitor_poll_interval") or 0)
    counts = dict(up=0, down=0, unknown=0)
    for key, expected in targets.items():
        row = rows.get(key)
        if row and status_is_current(row["ts"], interval, now):
            state = check_availability(key[0], row["status"], expected)
        else:
            state = "unknown"
        counts[state] += 1
    return counts


def safe_check_detail(text):
    """Keep a bounded diagnostic while removing URL credentials and secret values."""
    from urllib.parse import urlsplit
    from .scrub import scrub
    def url_host(match):
        try:
            parsed = urlsplit(match.group(0))
            return parsed.scheme + "://" + (parsed.hostname or "[host]")
        except ValueError:
            return "[URL]"
    text = re.sub(r"https?://[^\s<>\"']+", url_host, str(text or ""))
    text = re.sub(r"(?i)\bauthorization\s*:\s*(?:Bearer|Basic)\s+\S+",
                  "authorization=[redacted]", text)
    text = re.sub(r"""(?i)\b(password|community|token|secret|authorization|snmp_auth_pass|snmp_priv_pass|key_passphrase|enable_password)["']?\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
                  r"\1=[redacted]", text)
    text, _ = scrub(text)
    return text[:1500]


def endpoint_detail(result, tls=False):
    evidence = result.get("tls") or {} if tls else result
    error = evidence.get("error") or evidence.get("handshake_error")
    if error:
        detail = safe_check_detail(error)
        low = detail.lower()
        if "issuer" in low or "self-signed" in low:
            detail += " Check the server certificate chain and the monitor's trusted CA certificates."
        elif "expired" in low:
            detail += " Renew the server certificate."
        elif "hostname" in low or "not valid for" in low:
            detail += " Check the URL hostname and certificate names."
        elif "timed out" in low or "timeout" in low:
            detail += " Check reachability, firewall rules and server response time."
        return detail
    if not tls and not result.get("ok"):
        return f'HTTP {result.get("status") or "unavailable"}; expected {result.get("expect") or "200–399"}.'
    return ""


def run_device_checks(manager, dev):
    """Run the checks appropriate to the device's type(s) and record history.
    Returns a list of result dicts: {kind, target, status, value}."""
    out = []
    types = _types(dev)
    host = dev["host"]
    if "system" in types and (dev.get("monitor_ports") or "").strip():
        for c in portmon.check_ports(host, dev["monitor_ports"], timeout=1.5):
            tgt = f'{c["proto"]}/{c["port"]}'
            detail = (f"{tgt}: no UDP reply; the port may be open or filtered. Use an application-level check to confirm."
                      if c["state"] == "open|filtered" else "")
            out.append({"kind": "port", "target": tgt, "status": c["state"],
                        "value": c.get("ms"), "detail": detail})
    if "application" in types:
        spec = (dev.get("monitor_urls") or "").strip() or f"https://{host}/"
        for r in appmon.check_all(spec, host, timeout=5.0):
            code = r.get("status")
            out.append({"kind": "http", "target": r["url"],
                        "status": str(code) if code is not None else "down",
                        "value": r.get("ms"), "detail": endpoint_detail(r)})
            tls = r.get("tls")
            if tls:
                out.append({"kind": "tls", "target": r["url"],
                            "status": "valid" if tls.get("valid") else "invalid",
                            "value": tls.get("expires_days"), "detail": endpoint_detail(r, tls=True)})
    for r in out:
        manager.db.record_result(dev["name"], r["kind"], r["target"], r["status"],
                                 r.get("value"), detail=r.get("detail", ""))
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _breach(rule, result):
    """Does this result breach the rule? Returns (breached, evidence)."""
    metric = rule["metric"]
    op = rule["op"]
    thr = rule["threshold"]
    status = result["status"]
    val = result.get("value")
    if metric == "port_state":
        actual = status
        hit = (actual == thr) if op == "is" else (actual != thr)
        return hit, f"{result['target']} is {actual}"
    if metric == "tls_valid":
        hit = (status == "invalid") if thr == "invalid" else (status != "valid")
        return (status == "invalid"), f"cert {status}"
    if metric == "http_status":
        if status == "down":
            return True, "endpoint down"
        a = _num(status)
        t = _num(thr)
        if a is None or t is None:
            return False, ""
        hit = _cmp(a, op, t)
        return hit, f"HTTP {int(a)}"
    if metric in ("response_time", "tls_expiry"):
        a = _num(val)
        t = _num(thr)
        if a is None or t is None:
            return False, ""
        unit = "ms" if metric == "response_time" else "d"
        return _cmp(a, op, t), f"{result['target']} = {int(a)}{unit}"
    return False, ""


def _cmp(a, op, b):
    return {"==": a == b, "!=": a != b, ">": a > b, "<": a < b,
            ">=": a >= b, "<=": a <= b}.get(op, False)




def _sensor_status_for_metric(manager, dev, metric, result):
    """Map one legacy monitor observation into the canonical Sensor status.

    Existing alert rules remain threshold inputs during MC-4 migration, but
    the authoritative alert lifecycle is operational_events -> operational_alerts.
    """
    rules = [r for r in manager.db.rules(enabled_only=True)
             if r["metric"] == metric
             and (not r["device"] or r["device"] == dev["name"])
             and (not r["target"] or r["target"] == result["target"])]
    breached = []
    for rule in rules:
        hit, _ = _breach(rule, result)
        if hit:
            breached.append(rule)
    if breached:
        rank = {"low": 1, "medium": 2, "warning": 2, "high": 3,
                "major": 3, "critical": 3}
        highest = max(rank.get(str(r.get("severity") or "medium").lower(), 2)
                      for r in breached)
        return "CRITICAL" if highest >= 3 else "WARNING", breached

    status = str(result.get("status") or "").lower()
    value = result.get("value")
    if metric == "port_state":
        if status == "open|filtered":
            return "UNKNOWN", []
        return ("OK" if status == "open" else "CRITICAL"), []
    if metric == "http_status":
        if status == "down":
            return "CRITICAL", []
        code = _num(status)
        if code is None:
            return "UNKNOWN", []
        if code >= 500:
            return "CRITICAL", []
        if code >= 400:
            return "WARNING", []
        return "OK", []
    if metric == "tls_valid":
        if not status:
            return "UNKNOWN", []
        return ("OK" if status == "valid" else "CRITICAL"), []
    if metric in {"response_time", "tls_expiry"}:
        return ("OK" if _num(value) is not None else "UNKNOWN"), []
    return "UNKNOWN", []


def _monitor_sensor_specs(manager, dev, results):
    specs = []
    for result in results:
        kind = result.get("kind")
        target = str(result.get("target") or "")
        metrics = []
        if kind == "port":
            metrics = [("port_state", "service.port_state", result.get("status"), "")]
        elif kind == "http":
            metrics = [
                ("http_status", "application.http_status", result.get("status"), "http"),
                ("response_time", "application.response_time", result.get("value"), "ms"),
            ]
        elif kind == "tls":
            metrics = [
                ("tls_valid", "application.tls_valid", result.get("status"), ""),
                ("tls_expiry", "application.tls_expiry", result.get("value"), "days"),
            ]
        for metric, sensor_type, value, unit in metrics:
            status, breached = _sensor_status_for_metric(manager, dev, metric, result)
            threshold = "; ".join(
                f'{r["metric"]} {r["op"]} {r["threshold"]}' for r in breached[:4])
            message = f'{metric} {status.lower()} for {target}'
            if result.get("detail"):
                message += ": " + result["detail"]
            specs.append({
                "metric": metric, "sensor_type": sensor_type, "device": dev["name"],
                "resource": target, "value": "" if value is None else value,
                "unit": unit, "status": status, "message": message,
                "threshold": threshold, "source": "monitor_results",
            })
    return specs


def normalize_results(manager, dev, results):
    """Persist monitor observations as Sensors and bridge only state changes.

    The function performs no network I/O. First-seen WARNING/CRITICAL evidence is
    emitted once so an already-broken service is visible immediately; later
    observations rely on durable Sensor transitions.
    """
    before = manager.sensors.latest_transition_id()
    initial_events = []
    for spec in _monitor_sensor_specs(manager, dev, results):
        previous = manager.db.conn.execute(
            "SELECT * FROM sensors WHERE sensor_type=? AND device=? AND resource=?",
            (spec["sensor_type"], spec["device"], spec["resource"])).fetchone()
        manager.sensors.upsert(
            spec["sensor_type"], device=spec["device"], resource=spec["resource"],
            value=spec["value"], unit=spec["unit"], status=spec["status"],
            message=spec["message"], threshold=spec["threshold"], source=spec["source"])
        if previous is None and spec["status"] in {"WARNING", "CRITICAL"}:
            sensor_key = manager.sensors.sensor_key(
                spec["sensor_type"], spec["device"], spec["resource"])
            event = manager.events.record(
                source_type="sensor_transition", source="monitor_results",
                device=spec["device"], event_type=f'{spec["sensor_type"]}.{spec["status"].lower()}',
                severity=spec["status"], message=spec["message"],
                metadata={"sensor_key": sensor_key, "sensor_type": spec["sensor_type"],
                          "previous_status": "UNKNOWN", "new_status": spec["status"],
                          "transition_reason": "initial_bad_state"},
                domain="APPLICATION" if spec["sensor_type"].startswith("application.") else "SYSTEM",
                entity_type="application" if spec["sensor_type"].startswith("application.") else "service",
                entity_id=spec["resource"], resource=spec["resource"], status=spec["status"])
            initial_events.append(event)
    bridged = list(initial_events)
    for transition in manager.sensors.transitions_after_id(before, device=dev["name"]):
        event = manager.events.record_sensor_transition(transition)
        if event is not None:
            bridged.append(event)
    manager.alert_lifecycle.reconcile_sensor_conditions(device=dev["name"])
    return bridged

def evaluate_alerts(manager, dev, results):
    """Apply enabled rules to this device's fresh results; open/resolve alerts.
    Returns a list of newly-opened alert dicts (for notification)."""
    if not workspace_enabled(getattr(manager, "settings", {}), "alerts"):
        return []
    db = manager.db
    rules = [r for r in db.rules(enabled_only=True)
             if not r["device"] or r["device"] == dev["name"]]
    newly = []
    for rule in rules:
        kind = _METRIC_KIND.get(rule["metric"])
        matches = [r for r in results if r["kind"] == kind
                   and (not rule["target"] or rule["target"] == r["target"])]
        for res in matches:
            breached, evidence = _breach(rule, res)
            existing = db.firing_alert(rule["id"], dev["name"], res["target"])
            if breached and not existing:
                msg = (f'{rule["name"]}: {dev["name"]} {res["target"]} \u2014 {evidence} '
                       f'({rule["metric"]} {rule["op"]} {rule["threshold"]})')
                aid = db.open_alert(rule["id"], rule["name"], dev["name"], res["target"],
                                    rule["metric"], rule["severity"], msg)
                newly.append({"id": aid, "device": dev["name"], "target": res["target"],
                              "severity": rule["severity"], "message": msg})
                db.audit("monitor", "alert_firing", dev["name"], msg)
            elif breached and existing:
                db.touch_alert(existing["id"])
            elif not breached and existing:
                db.resolve_alert(existing["id"])
                db.audit("monitor", "alert_resolved", dev["name"],
                         f'{rule["name"]}: {res["target"]}')
    return newly


def notify(manager, newly):
    """Email newly-opened alerts if SMTP is enabled."""
    if not newly or not workspace_enabled(manager.settings, "alerts") or not manager.settings.get("smtp_enabled"):
        return
    password = None
    try:
        if manager.vault_ready():
            password = manager.vault.get_secret(mailer.SMTP_SECRET).get("password")
    except Exception:
        password = None
    lines = [f'[{a["severity"].upper()}] {a["message"]}' for a in newly]
    subject = f"NetConfig: {len(newly)} alert(s) firing"
    mailer.send_mail(manager.settings, subject, "\n".join(lines), password=password)


def poll_once(manager):
    """One pass over enabled devices using the MC-4 canonical alert plane.

    Legacy ``alerts`` rows remain readable as historical compatibility data, but
    new monitor observations now flow through Sensor -> Event -> Operational Alert.
    Existing ``alert_rules`` remain threshold inputs.
    """
    checks = 0
    events = []
    for dev in manager.inv.all(only_enabled=True):
        try:
            results = run_device_checks(manager, dev)
        except Exception:
            continue
        checks += len(results)
        events.extend(normalize_results(manager, dev, results))
    return checks, events


def poller(manager, interval, stop):
    """Background loop. Prunes history beyond the retention window each pass."""
    retain = float(manager.settings.get("monitor_history_days", 7)) * 86400
    while not stop.is_set():
        try:
            if not manager.scheduler_leader("monitor-poller"):
                stop.wait(interval)
                continue
            poll_once(manager)
            manager.db.prune_results(time.time() - retain)
        except Exception:
            pass
        stop.wait(interval)
