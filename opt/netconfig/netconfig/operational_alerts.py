"""NI-4 operational alert lifecycle, maintenance, delivery retry and reports.

This layer consumes NI-3 normalized operational events.  It does not parse traps,
copy raw packets, or infer new topology.  Only unsuppressed events at/above the
configured severity threshold can become operational alerts.  Maintenance windows
suppress alert creation without deleting the underlying event evidence.
"""
from __future__ import annotations

import json
import time

from . import mailer
from .db import operational_alert_correlation_key

_ALERT_STATES = {"OPEN", "ACKNOWLEDGED", "RESOLVED"}
_SEVERITY_RANK = {
    "DEBUG": 0, "INFO": 1, "NOTICE": 2, "WARNING": 3,
    "MINOR": 4, "MAJOR": 5, "ERROR": 5, "CRITICAL": 6,
}


def _clean(value, limit=1024):
    return str(value or "").replace("\x00", "")[:limit]


def _event_metadata(event):
    raw = event.get("metadata") if event else None
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(raw or "{}")
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _correlation_key(event):
    return operational_alert_correlation_key(event)


def _is_recovery(event):
    meta = _event_metadata(event)
    if str(event.get("source_type") or "").lower() == "sensor_transition":
        return str(meta.get("new_status") or event.get("status") or "").upper() == "OK"
    return str(event.get("status") or "").upper() in {"RECOVERED", "RESOLVED"}


class OperationalAlertLifecycle:
    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db

    def _threshold_rank(self):
        name = str(self.manager.settings.get("operational_alert_min_severity", "WARNING") or "WARNING").upper()
        return _SEVERITY_RANK.get(name, _SEVERITY_RANK["WARNING"])

    def _qualifies(self, event):
        if int(event.get("suppressed") or 0):
            return False
        return _SEVERITY_RANK.get(str(event.get("severity") or "INFO").upper(), 1) >= self._threshold_rank()

    def active_maintenance(self, device, now=None):
        now = time.time() if now is None else float(now)
        return self.db.active_maintenance_window(_clean(device, 255), now)

    def reconcile_sensor_conditions(self, device=None, now=None):
        """Reconcile persistent firing Sensors without inventing transitions.

        Manual resolution of a still-firing Sensor reopens the same alert
        lifecycle on the next Sensor refresh. Events observed during maintenance
        are re-evaluated after maintenance ends. The method is DB-only and does
        not poll devices.
        """
        now = time.time() if now is None else float(now)
        sensors = self.manager.sensors.list(device=device, limit=2000)
        firing = [s for s in sensors if str(s.get("status") or "").upper() in {"WARNING", "CRITICAL"}]
        if not firing:
            return []

        # Build one bounded latest-event map once; do not execute one query per
        # Sensor. Sensor events carry the durable sensor_key in metadata.
        events = self.db.operational_events(
            limit=5000, device=device, include_suppressed=True, source_type="sensor_transition")
        latest_event = {}
        for event in events:
            meta = _event_metadata(event)
            sensor_key = str(meta.get("sensor_key") or "")
            if sensor_key and sensor_key not in latest_event:
                latest_event[sensor_key] = event

        changed = []
        for sensor in firing:
            sensor_key = self.manager.sensors.sensor_key(
                sensor.get("sensor_type") or "", sensor.get("device") or "",
                sensor.get("resource") or "")
            correlation_key = "sensor:" + sensor_key[:900]
            if self.db.active_operational_alert_for_correlation(correlation_key):
                continue
            sensor_device = str(sensor.get("device") or "")
            if self.active_maintenance(sensor_device, now):
                continue
            if self.db.active_operational_suppressions(sensor_device, now):
                continue

            previous = self.db.latest_operational_alert_for_correlation(correlation_key)
            if (previous and previous.get("state") == "RESOLVED" and
                    str(previous.get("resolved_by") or "") != "sensor-recovery"):
                row = self.db.reopen_operational_alert(previous["id"], now)
                self.db.audit("sensor-reconcile", "operational_alert_reopen", str(row["id"]),
                              f'{row.get("device","")} persistent Sensor condition')
                if self._alert_notifications_enabled():
                    self.db.enqueue_notification("ALERT_OPEN", now, alert_id=row["id"])
                changed.append(row)
                continue

            # A transition/initial-bad event that occurred during maintenance has
            # durable evidence but no alert. Re-evaluate that same event after the
            # window ends rather than manufacturing a fake Sensor transition.
            event = latest_event.get(sensor_key)
            if not event or int(event.get("suppressed") or 0):
                continue
            if str(event.get("status") or "").upper() not in {"WARNING", "CRITICAL"}:
                continue
            row = self.observe_event(event, now=now)
            if row and not row.get("maintenance_suppressed"):
                changed.append(row)
        return changed

    def observe_event(self, event, now=None):
        """Attach the canonical MC-4 alert lifecycle to normalized evidence.

        One Sensor condition owns at most one active alert. Severity escalation
        touches that alert; an OK recovery transition resolves it automatically.
        Maintenance/dependency suppression still prevents alert creation while
        preserving the event evidence.
        """
        if not event or not event.get("id"):
            return None
        now = float(event.get("last_ts") or time.time()) if now is None else float(now)
        existing = self.db.operational_alert_for_event(event["id"])
        if existing:
            row = self.db.touch_operational_alert(existing["id"], event)
            self.db.set_operational_event_lifecycle_refs(event["id"], alert_id=row["id"])
            return row

        key = _correlation_key(event)
        active = self.db.active_operational_alert_for_correlation(key)
        if _is_recovery(event):
            if not active:
                return None
            self.db.touch_operational_alert_recovery(active["id"], event)
            row = self.db.update_operational_alert_state(
                active["id"], "RESOLVED", "sensor-recovery",
                _clean(event.get("message") or "automatic recovery", 1024), now)
            self.db.set_operational_event_lifecycle_refs(event["id"], alert_id=row["id"])
            self.db.audit("sensor-recovery", "operational_alert_auto_resolve", str(row["id"]),
                          f'{row.get("device","")} {event.get("event_type","")}')
            if self._alert_notifications_enabled():
                self.db.enqueue_notification("ALERT_RESOLVED", now, alert_id=row["id"])
            return row

        if active:
            row = self.db.touch_operational_alert(active["id"], event)
            self.db.set_operational_event_lifecycle_refs(event["id"], alert_id=row["id"])
            return row
        if not self._qualifies(event):
            return None
        maint = self.active_maintenance(event.get("device") or "", now)
        if maint:
            self.db.set_operational_event_lifecycle_refs(event["id"], maintenance_window_id=maint["id"])
            return {"maintenance_suppressed": True, "maintenance_window_id": maint["id"]}
        alert = self.db.create_operational_alert(event, correlation_key=key, opened_ts=now)
        self.db.set_operational_event_lifecycle_refs(event["id"], alert_id=alert["id"])
        self.db.audit("operational-events", "operational_alert_open", str(alert["id"]),
                      f'{alert.get("device","")} {alert.get("event_type","")}')
        if self._alert_notifications_enabled():
            self.db.enqueue_notification("ALERT_OPEN", now, alert_id=alert["id"])
        return alert

    def _alert_notifications_enabled(self):
        # MC-4 preserves the old monitor SMTP behaviour while the dedicated
        # operational-notification toggle remains available.
        return bool(self.manager.settings.get("operational_notifications_enabled")
                    or self.manager.settings.get("smtp_enabled"))

    def get(self, alert_id):
        return self.db.get_operational_alert(int(alert_id))

    def list(self, state=None, device=None, limit=200):
        if state:
            state = str(state).upper()
            if state not in _ALERT_STATES:
                raise ValueError("invalid alert state")
        return self.db.list_operational_alerts(state=state, device=device, limit=limit)

    def acknowledge(self, alert_id, actor, note="", now=None):
        now = time.time() if now is None else float(now)
        row = self.get(alert_id)
        if not row:
            raise ValueError("operational alert not found")
        if row["state"] == "RESOLVED":
            raise ValueError("resolved alert cannot be acknowledged")
        if row["state"] == "ACKNOWLEDGED":
            return row
        out = self.db.update_operational_alert_state(alert_id, "ACKNOWLEDGED", _clean(actor,128), _clean(note,1024), now)
        self.db.audit(actor, "operational_alert_ack", str(alert_id), _clean(note,500))
        return out

    def resolve(self, alert_id, actor, note="", now=None):
        now = time.time() if now is None else float(now)
        row = self.get(alert_id)
        if not row:
            raise ValueError("operational alert not found")
        if row["state"] == "RESOLVED":
            return row
        out = self.db.update_operational_alert_state(alert_id, "RESOLVED", _clean(actor,128), _clean(note,1024), now)
        self.db.audit(actor, "operational_alert_resolve", str(alert_id), _clean(note,500))
        if self._alert_notifications_enabled():
            self.db.enqueue_notification("ALERT_RESOLVED", now, alert_id=int(alert_id))
        return out

    def add_maintenance(self, name, actor, *, minutes=60, device="", reason="", start_ts=None, now=None):
        now = time.time() if now is None else float(now)
        start = now if start_ts is None else float(start_ts)
        minutes = int(minutes)
        if not _clean(name, 160):
            raise ValueError("maintenance name is required")
        if minutes < 1 or minutes > 43200:
            raise ValueError("maintenance duration must be 1..43200 minutes")
        if device and not self.manager.inv.get(device):
            raise ValueError("maintenance device not found")
        row = self.db.add_maintenance_window(_clean(name,160), _clean(device,255), start,
                                             start + minutes * 60, _clean(reason,1024),
                                             _clean(actor,128), now)
        self.db.audit(actor, "maintenance_window_add", str(row["id"]),
                      f'{row["name"]} device={row["device"] or "all"}')
        return row

    def maintenance(self, active_only=False, now=None):
        return self.db.list_maintenance_windows(active_only=active_only, now=now)

    def cancel_maintenance(self, window_id, actor, now=None):
        now = time.time() if now is None else float(now)
        row = self.db.cancel_maintenance_window(window_id, _clean(actor,128), now)
        if not row:
            raise ValueError("maintenance window not found")
        self.db.audit(actor, "maintenance_window_cancel", str(window_id), row.get("name") or "")
        self.reconcile_sensor_conditions(device=(row.get("device") or None), now=now)
        return row

    def add_report_schedule(self, name, actor, *, interval_seconds=86400, lookback_hours=24,
                            first_run_ts=None, now=None):
        now = time.time() if now is None else float(now)
        interval_seconds = int(interval_seconds)
        lookback_hours = int(lookback_hours)
        if not _clean(name,160):
            raise ValueError("report schedule name is required")
        if interval_seconds < 300 or interval_seconds > 2678400:
            raise ValueError("report interval must be 300..2678400 seconds")
        if lookback_hours < 1 or lookback_hours > 8760:
            raise ValueError("report lookback must be 1..8760 hours")
        first = now + interval_seconds if first_run_ts is None else float(first_run_ts)
        row = self.db.add_report_schedule(_clean(name,160), interval_seconds, lookback_hours,
                                          first, _clean(actor,128), now)
        self.db.audit(actor, "operational_report_schedule_add", str(row["id"]), row["name"])
        return row

    def report_schedules(self):
        return self.db.list_report_schedules()

    def set_report_schedule_enabled(self, schedule_id, enabled, actor, now=None):
        now = time.time() if now is None else float(now)
        self.db.set_report_schedule_enabled(schedule_id, enabled, _clean(actor,128), now)
        self.db.audit(actor, "operational_report_schedule_state", str(schedule_id), "enabled" if enabled else "disabled")
        rows = [x for x in self.db.list_report_schedules() if x["id"] == int(schedule_id)]
        if not rows:
            raise ValueError("report schedule not found")
        return rows[0]

    def _summary(self, start_ts, end_ts):
        ev = self.db.conn.execute(
            "SELECT severity,event_type,suppressed,COUNT(*) AS rows,SUM(event_count) AS observations FROM operational_events WHERE last_ts>=? AND last_ts<=? GROUP BY severity,event_type,suppressed",
            (float(start_ts), float(end_ts))).fetchall()
        alerts = self.db.conn.execute(
            "SELECT state,severity,COUNT(*) AS count FROM operational_alerts WHERE last_ts>=? AND last_ts<=? GROUP BY state,severity",
            (float(start_ts), float(end_ts))).fetchall()
        return {
            "window": {"start_ts": float(start_ts), "end_ts": float(end_ts)},
            "events": [dict(r) for r in ev],
            "alerts": [dict(r) for r in alerts],
            "active_maintenance": len(self.db.list_maintenance_windows(active_only=True, now=end_ts)),
            "active_dependency_suppressions": len(self.db.operational_suppressions(active_only=True, now=end_ts)),
        }

    def run_report(self, *, schedule_id=None, lookback_hours=None, now=None, actor="scheduler"):
        now = time.time() if now is None else float(now)
        schedule = None
        if schedule_id is not None:
            schedule = next((x for x in self.db.list_report_schedules() if x["id"] == int(schedule_id)), None)
            if not schedule:
                raise ValueError("report schedule not found")
        hours = int(lookback_hours if lookback_hours is not None else (schedule["lookback_hours"] if schedule else 24))
        if hours < 1 or hours > 8760:
            raise ValueError("report lookback must be 1..8760 hours")
        start = now - hours * 3600
        summary = self._summary(start, now)
        run = self.db.create_report_run(schedule["id"] if schedule else None, now, now, "COMPLETE",
                                        start, now, json.dumps(summary, sort_keys=True, separators=(",", ":")))
        self.db.audit(actor, "operational_report_run", str(run["id"]), f"lookback_hours={hours}")
        if self.manager.settings.get("operational_notifications_enabled"):
            delivery = self.db.enqueue_notification("REPORT", now, report_run_id=run["id"])
            self.db.set_report_delivery(run["id"], delivery["id"])
            run["delivery_id"] = delivery["id"]
        return self._decode_run(run)

    def _decode_run(self, run):
        out = dict(run)
        try:
            out["summary"] = json.loads(out.get("summary") or "{}")
        except Exception:
            out["summary"] = {}
        return out

    def report_runs(self, limit=100):
        return [self._decode_run(x) for x in self.db.list_report_runs(limit)]

    def run_due_reports(self, now=None):
        now = time.time() if now is None else float(now)
        out = []
        for schedule in self.db.due_report_schedules(now):
            try:
                out.append(self.run_report(schedule_id=schedule["id"], now=now, actor="scheduler"))
            finally:
                nxt = max(now, float(schedule.get("next_run_ts") or now)) + int(schedule["interval_seconds"])
                self.db.update_report_schedule_next(schedule["id"], nxt, "scheduler", now)
        return out

    def _delivery_message(self, row):
        kind = row["kind"]
        if kind in {"ALERT_OPEN", "ALERT_RESOLVED"}:
            alert = self.get(row.get("alert_id"))
            if not alert:
                raise ValueError("alert missing for delivery")
            subject = f'NetConfig {kind.replace("_", " ").title()}: {alert["device"] or alert["event_type"]}'
            body = (f'Alert #{alert["id"]}\nState: {alert["state"]}\nSeverity: {alert["severity"]}\n'
                    f'Device: {alert["device"]}\nEvent: {alert["event_type"]}\nMessage: {alert["message"]}\n')
            return subject, body
        if kind == "REPORT":
            run = next((x for x in self.report_runs(500) if x["id"] == int(row.get("report_run_id") or 0)), None)
            if not run:
                raise ValueError("report run missing for delivery")
            subject = f'NetConfig operational report #{run["id"]}'
            body = json.dumps(run["summary"], indent=2, sort_keys=True)
            return subject, body
        raise ValueError("unknown delivery kind")

    def process_notifications(self, now=None, limit=50):
        now = time.time() if now is None else float(now)
        if not self.manager.settings.get("operational_notifications_enabled"):
            return []
        max_attempts = max(1, int(self.manager.settings.get("operational_notification_max_attempts", 5)))
        base = max(1, int(self.manager.settings.get("operational_notification_backoff_base_seconds", 60)))
        cap = max(base, int(self.manager.settings.get("operational_notification_backoff_max_seconds", 3600)))
        password, oauth_token = mailer.resolve_auth(self.manager)
        out = []
        for row in self.db.due_notifications(now, limit):
            attempts = int(row.get("attempts") or 0) + 1
            try:
                subject, body = self._delivery_message(row)
                ok, msg = mailer.send_mail(self.manager.settings, subject, body,
                                           password=password, oauth_token=oauth_token)
            except Exception as exc:
                ok, msg = False, f"{type(exc).__name__}: {exc}"
            if ok:
                updated = self.db.update_notification(row["id"], "SENT", attempts, now, error="")
            elif attempts >= max_attempts:
                updated = self.db.update_notification(row["id"], "FAILED", attempts, now, error=_clean(msg,500))
            else:
                delay = min(cap, base * (2 ** (attempts - 1)))
                updated = self.db.update_notification(row["id"], "RETRY", attempts, now,
                                                      next_attempt_ts=now + delay, error=_clean(msg,500))
            out.append(updated)
        return out

    def notifications(self, limit=100):
        return self.db.list_notifications(limit)

    def tick(self, now=None):
        now = time.time() if now is None else float(now)
        return {"reports": self.run_due_reports(now), "deliveries": self.process_notifications(now)}


def poller(manager, interval, stop):
    interval = max(30, int(interval))
    while not stop.is_set():
        try:
            if manager.scheduler_leader("operational-lifecycle"):
                manager.alert_lifecycle.tick()
        except Exception as exc:
            manager.db.audit("scheduler", "operational_lifecycle_failed", "ni4", str(exc)[:500])
        stop.wait(interval)
