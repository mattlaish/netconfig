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


def run_device_checks(manager, dev):
    """Run the checks appropriate to the device's type(s) and record history.
    Returns a list of result dicts: {kind, target, status, value}."""
    out = []
    types = _types(dev)
    host = dev["host"]
    if "system" in types and (dev.get("monitor_ports") or "").strip():
        for c in portmon.check_ports(host, dev["monitor_ports"], timeout=1.5):
            tgt = f'{c["proto"]}/{c["port"]}'
            out.append({"kind": "port", "target": tgt, "status": c["state"],
                        "value": c.get("ms")})
    if "application" in types:
        spec = (dev.get("monitor_urls") or "").strip() or f"https://{host}/"
        for r in appmon.check_all(spec, host, timeout=5.0):
            code = r.get("status")
            out.append({"kind": "http", "target": r["url"],
                        "status": str(code) if code is not None else "down",
                        "value": r.get("ms")})
            tls = r.get("tls")
            if tls:
                out.append({"kind": "tls", "target": r["url"],
                            "status": "valid" if tls.get("valid") else "invalid",
                            "value": tls.get("expires_days")})
    for r in out:
        manager.db.record_result(dev["name"], r["kind"], r["target"], r["status"], r.get("value"))
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


def evaluate_alerts(manager, dev, results):
    """Apply enabled rules to this device's fresh results; open/resolve alerts.
    Returns a list of newly-opened alert dicts (for notification)."""
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
    if not newly or not manager.settings.get("smtp_enabled"):
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
    """One full pass over all enabled devices. Returns (checks, new_alerts)."""
    checks = 0
    opened = []
    for dev in manager.inv.all(only_enabled=True):
        try:
            results = run_device_checks(manager, dev)
        except Exception:
            continue
        checks += len(results)
        opened.extend(evaluate_alerts(manager, dev, results))
    if opened:
        try:
            notify(manager, opened)
        except Exception:
            pass
    return checks, opened


def poller(manager, interval, stop):
    """Background loop. Prunes history beyond the retention window each pass."""
    retain = float(manager.settings.get("monitor_history_days", 7)) * 86400
    while not stop.is_set():
        try:
            poll_once(manager)
            manager.db.prune_results(time.time() - retain)
        except Exception:
            pass
        stop.wait(interval)
