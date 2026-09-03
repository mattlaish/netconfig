"""Scheduled compliance/drift digest built from existing archive and mailer."""
import json, time
from . import compliance, mailer


def build(manager):
    devices = manager.inv.all()
    drifted, baselined = [], 0
    for d in devices:
        if "network" not in (d.get("device_type") or "network"): continue
        dr = manager.store.drift(d["name"])
        if dr.get("baselined"): baselined += 1
        if dr.get("drifted"): drifted.append(d["name"])
    report = compliance.evaluate_fleet(manager.store, devices)
    failures = [{"device": d["device"], "failed": d.get("failed",0)} for d in report["devices"] if d.get("failed")]
    body = ["NetConfig scheduled compliance & drift digest", "",
            f"Devices: {len(devices)}", f"Baselined: {baselined}", f"Drifted: {len(drifted)}"]
    if drifted: body.append("Drifted devices: " + ", ".join(drifted))
    body += [f"Compliance failed checks: {report['totals']['fail']}", f"Unknown checks: {report['totals'].get('unknown',0)}"]
    for item in failures[:50]: body.append(f"- {item['device']}: {item['failed']} failed check(s)")
    return {"ts": time.time(), "drifted": drifted, "compliance": report, "body": "\n".join(body)}


def run(manager):
    result = build(manager); pw, tok = mailer.resolve_auth(manager)
    ok, message = mailer.send_mail(manager.settings, "NetConfig compliance & drift digest", result["body"], password=pw, oauth_token=tok)
    manager.db.record_digest(ok, message, json.dumps({"drifted": result["drifted"], "totals": result["compliance"]["totals"]}))
    manager.db.audit("scheduler", "compliance_drift_digest", "email", message)
    return ok, message, result


def poller(manager, interval, stop):
    while not stop.wait(interval):
        try: run(manager)
        except Exception as exc: manager.db.audit("scheduler", "digest_failed", "email", str(exc)[:500])
