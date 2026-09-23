"""Sensor normalization and evidence-generation layer.

Sensors are derived only from already-persisted NetConfig evidence.  This module
must never cause device I/O, broaden a walk, or shorten a polling interval.
"""
from __future__ import annotations

import time


_SENSOR_STATUSES = {"OK", "WARNING", "CRITICAL", "UNKNOWN"}
_INTERFACE_SENSOR_TYPES = (
    "interface.status",
    "interface.utilization",
    "interface.errors",
    "interface.discards",
)
_TOPOLOGY_SENSOR_TYPES = (
    "topology.neighbor",
    "topology.managed_neighbor_count",
    "topology.unmanaged_neighbor_count",
)

_SENSOR_VALUE_THRESHOLDS = {
    "interface.utilization": {
        "WARNING": 80,
        "CRITICAL": 95,
    },
}

_SENSOR_OBSERVATION_RETENTION_SECONDS = 30 * 24 * 60 * 60
_SENSOR_TRANSITION_RETENTION_SECONDS = 180 * 24 * 60 * 60
_SENSOR_HISTORY_PRUNE_INTERVAL_SECONDS = 60 * 60


def _mib_truth(value):
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "enabled", "enable", "detected", "active", "on"}:
        return True
    if text in {"2", "0", "false", "no", "disabled", "disable", "clear", "normal", "off"}:
        return False
    return None




class SensorHistoryRecorder:
    """Persist sensor observations and meaningful state transitions.

    MC-2 history is derived from already-persisted evidence only.  Recording is
    best-effort: a history write failure must never block the canonical current
    Sensor snapshot.
    """

    def __init__(self, conn):
        self.conn = conn
        self._last_prune = 0.0

    @staticmethod
    def key(sensor_type, device, resource):
        return "|".join((str(sensor_type or ""), str(device or ""), str(resource or "")))

    def _status_for_value(self, sensor_type, value, current_status):
        """Normalize numeric Sensors into the same threshold severity used by UI/API."""
        thresholds = _SENSOR_VALUE_THRESHOLDS.get(sensor_type)
        if not thresholds:
            return current_status
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return current_status
        if numeric >= thresholds["CRITICAL"]:
            return "CRITICAL"
        if numeric >= thresholds["WARNING"]:
            return "WARNING"
        return "OK"

    @staticmethod
    def _transition_reason(previous_status, new_status):
        previous_status = str(previous_status or "UNKNOWN").upper()
        new_status = str(new_status or "UNKNOWN").upper()
        if previous_status == "UNKNOWN" and new_status != "UNKNOWN":
            return "evidence_recovered"
        if previous_status != "UNKNOWN" and new_status == "UNKNOWN":
            return "evidence_lost"
        rank = {"UNKNOWN": 0, "OK": 1, "WARNING": 2, "CRITICAL": 3}
        if rank.get(new_status, 0) > rank.get(previous_status, 0):
            return "severity_increased"
        if rank.get(new_status, 0) < rank.get(previous_status, 0):
            return "severity_recovered"
        return "status_change"

    @staticmethod
    def _meaningful_transition(previous_status, new_status):
        return str(previous_status or "UNKNOWN").upper() != str(new_status or "UNKNOWN").upper()

    def _prune_history(self, now):
        if now - self._last_prune < _SENSOR_HISTORY_PRUNE_INTERVAL_SECONDS:
            return
        self.conn.execute(
            "DELETE FROM sensor_observations WHERE observed_at<?",
            (now - _SENSOR_OBSERVATION_RETENTION_SECONDS,))
        self.conn.execute(
            "DELETE FROM sensor_transitions WHERE observed_at<?",
            (now - _SENSOR_TRANSITION_RETENTION_SECONDS,))
        self._last_prune = now

    def record(self, previous, current):
        """Record one observation and, when severity changed, one transition.

        Restart duplicate protection comes from comparing against the persisted
        current Sensor row before it is updated.  Reconstructing SensorEngine on
        the same database therefore does not create a duplicate transition for
        an unchanged state.
        """
        try:
            now = time.time()
            self._prune_history(now)
            sensor_type = str(current.get("sensor_type") or "")
            device = str(current.get("device") or "")
            resource = str(current.get("resource") or "")
            key = self.key(sensor_type, device, resource)
            status = str(current.get("status") or "UNKNOWN").upper()
            value = str(current.get("value") or "")
            unit = str(current.get("unit") or "")
            message = str(current.get("message") or "")
            source = str(current.get("source") or "")

            self.conn.execute(
                "INSERT INTO sensor_observations("
                "sensor_key,sensor_type,device,resource,value,unit,status,message,source,"
                "observed_at,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, sensor_type, device, resource, value, unit, status, message, source,
                 now, "{}", now))

            if previous:
                old_status = str(previous.get("status") or "UNKNOWN").upper()
                old_value = str(previous.get("value") or "")
                if self._meaningful_transition(old_status, status):
                    import json
                    metadata = json.dumps({
                        "reason": self._transition_reason(old_status, status),
                        "generator": "SensorEngine",
                    }, sort_keys=True, separators=(",", ":"))
                    self.conn.execute(
                        "INSERT INTO sensor_transitions("
                        "sensor_key,sensor_type,device,resource,previous_status,new_status,"
                        "previous_value,new_value,source,observed_at,metadata_json,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, sensor_type, device, resource, old_status, status,
                         old_value, value, source, now, metadata, now))
            self.conn.commit()
        except Exception:
            # The current Sensor row is already committed by SensorEngine.upsert().
            # History is diagnostic evidence and must fail independently.
            try:
                self.conn.rollback()
            except Exception:
                pass


class SensorEngine:
    """Normalize existing observations into a stable sensor contract."""

    def __init__(self, conn):
        self.conn = conn
        if getattr(conn, "dialect", "sqlite") == "postgres":
            id_column = "id BIGSERIAL PRIMARY KEY"
            timestamp_type = "DOUBLE PRECISION"
        else:
            id_column = "id INTEGER PRIMARY KEY AUTOINCREMENT"
            timestamp_type = "REAL"
        self.conn.execute(f"""
        CREATE TABLE IF NOT EXISTS sensors (
          {id_column},
          sensor_type TEXT NOT NULL,
          device TEXT NOT NULL DEFAULT '',
          resource TEXT NOT NULL DEFAULT '',
          value TEXT NOT NULL DEFAULT '',
          unit TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'UNKNOWN',
          message TEXT NOT NULL DEFAULT '',
          threshold TEXT NOT NULL DEFAULT '',
          source TEXT NOT NULL DEFAULT '',
          updated_at {timestamp_type} NOT NULL
        )
        """)
        self.conn.commit()
        self.history = SensorHistoryRecorder(conn)

    def upsert(self, sensor_type, device="", resource="", value="",
               unit="", status="UNKNOWN", message="", threshold="",
               source=""):
        status = str(status or "UNKNOWN").upper()
        status = self.history._status_for_value(sensor_type, value, status)
        if status not in _SENSOR_STATUSES:
            raise ValueError(f"unsupported sensor status: {status}")
        row = self.conn.execute(
            "SELECT * FROM sensors WHERE sensor_type=? AND device=? AND resource=?",
            (sensor_type, device, resource)).fetchone()
        previous = dict(row) if row else None
        now = time.time()
        if row:
            self.conn.execute(
                "UPDATE sensors SET value=?,unit=?,status=?,message=?,threshold=?,"
                "source=?,updated_at=? WHERE id=?",
                (str(value), unit, status, message, threshold, source, now, row[0]))
        else:
            self.conn.execute(
                "INSERT INTO sensors(sensor_type,device,resource,value,unit,status,"
                "message,threshold,source,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (sensor_type, device, resource, str(value), unit, status, message,
                 threshold, source, now))
        self.conn.commit()
        self.history.record(previous, {
            "sensor_type": sensor_type,
            "device": device,
            "resource": resource,
            "value": str(value),
            "unit": unit,
            "status": status,
            "message": message,
            "source": source,
        })

    def list(self, device=None, sensor_type=None, status=None, limit=200):
        clauses = []
        args = []
        if device:
            clauses.append("device=?")
            args.append(device)
        if sensor_type:
            clauses.append("sensor_type=?")
            args.append(sensor_type)
        if status:
            status = str(status).upper()
            if status not in _SENSOR_STATUSES:
                raise ValueError(f"unsupported sensor status: {status}")
            clauses.append("status=?")
            args.append(status)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(max(1, min(int(limit), 2000)))
        rows = self.conn.execute(
            "SELECT * FROM sensors" + where + " ORDER BY id DESC LIMIT ?",
            tuple(args)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def sensor_key(sensor_type, device="", resource=""):
        return SensorHistoryRecorder.key(sensor_type, device, resource)

    def history_for(self, sensor_key, limit=200, since=None, before=None):
        """Return bounded observation + transition history for one stable Sensor key."""
        limit = max(1, min(int(limit), 2000))
        obs_sql = "SELECT * FROM sensor_observations WHERE sensor_key=?"
        tr_sql = "SELECT * FROM sensor_transitions WHERE sensor_key=?"
        obs_args = [sensor_key]
        tr_args = [sensor_key]
        if since is not None:
            obs_sql += " AND observed_at>=?"
            tr_sql += " AND observed_at>=?"
            obs_args.append(float(since))
            tr_args.append(float(since))
        if before is not None:
            obs_sql += " AND observed_at<?"
            tr_sql += " AND observed_at<?"
            obs_args.append(float(before))
            tr_args.append(float(before))
        obs_sql += " ORDER BY observed_at DESC,id DESC LIMIT ?"
        tr_sql += " ORDER BY observed_at DESC,id DESC LIMIT ?"
        obs_args.append(limit)
        tr_args.append(limit)
        observations = [dict(row) for row in self.conn.execute(obs_sql, tuple(obs_args)).fetchall()]
        transitions = [dict(row) for row in self.conn.execute(tr_sql, tuple(tr_args)).fetchall()]
        return {
            "sensor_key": sensor_key,
            "observations": observations,
            "transitions": transitions,
        }

    def latest_transition_id(self):
        row = self.conn.execute("SELECT COALESCE(MAX(id),0) AS id FROM sensor_transitions").fetchone()
        return int(row["id"] if row else 0)

    def transitions_after_id(self, after_id, device=None, limit=5000):
        """Return durable transitions created after a captured high-water mark.

        This is used by MC-3 to bridge only transitions created by the current
        refresh.  It is DB-only and never performs device I/O.
        """
        clauses = ["id>?"]
        args = [int(after_id or 0)]
        if device is not None:
            clauses.append("device=?")
            args.append(str(device))
        args.append(max(1, min(int(limit), 10000)))
        rows = self.conn.execute(
            "SELECT * FROM sensor_transitions WHERE " + " AND ".join(clauses) +
            " ORDER BY id ASC LIMIT ?", tuple(args)).fetchall()
        return [dict(row) for row in rows]

    def transitions(self, device=None, sensor_type=None, from_status=None,
                    to_status=None, since=None, before=None, limit=200):
        """Return bounded Sensor transitions for API/UI investigation."""
        clauses = []
        args = []
        if device:
            clauses.append("device=?")
            args.append(device)
        if sensor_type:
            clauses.append("sensor_type=?")
            args.append(sensor_type)
        if from_status:
            from_status = str(from_status).upper()
            if from_status not in _SENSOR_STATUSES:
                raise ValueError(f"unsupported previous sensor status: {from_status}")
            clauses.append("previous_status=?")
            args.append(from_status)
        if to_status:
            to_status = str(to_status).upper()
            if to_status not in _SENSOR_STATUSES:
                raise ValueError(f"unsupported new sensor status: {to_status}")
            clauses.append("new_status=?")
            args.append(to_status)
        if since is not None:
            clauses.append("observed_at>=?")
            args.append(float(since))
        if before is not None:
            clauses.append("observed_at<?")
            args.append(float(before))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        args.append(max(1, min(int(limit), 2000)))
        rows = self.conn.execute(
            "SELECT * FROM sensor_transitions" + where +
            " ORDER BY observed_at DESC,id DESC LIMIT ?", tuple(args)).fetchall()
        return [dict(row) for row in rows]

    def _query(self, sql, params=()):
        """Return persisted evidence rows; missing legacy tables mean no evidence."""
        try:
            return [dict(row) for row in self.conn.execute(sql, params).fetchall()]
        except Exception:
            return None

    def _delete_types(self, device, sensor_types):
        for sensor_type in sensor_types:
            self.conn.execute(
                "DELETE FROM sensors WHERE device=? AND sensor_type=?",
                (device, sensor_type))
        self.conn.commit()

    def _prune_resources(self, device, sensor_types, active_resources):
        """Delete stale current-state rows only after active Sensors were upserted.

        This preserves the prior current row long enough for MC-2 transition
        comparison while retaining MC-1's stale-resource cleanup behavior.
        """
        active = {str(item) for item in active_resources}
        for sensor_type in sensor_types:
            rows = self.conn.execute(
                "SELECT id,resource FROM sensors WHERE device=? AND sensor_type=?",
                (device, sensor_type)).fetchall()
            for row in rows:
                if str(row["resource"] or "") not in active:
                    self.conn.execute("DELETE FROM sensors WHERE id=?", (row["id"],))
        self.conn.commit()

    def _refresh_device_state(self, device):
        rows = self._query("SELECT * FROM device_facts WHERE device=?", (device,))
        fact = rows[0] if rows else None
        if not fact:
            self.upsert(
                "device.reachability", device=device, status="UNKNOWN",
                message="No reachability observation collected", source="device_facts")
            self.upsert(
                "device.polling", device=device, status="UNKNOWN",
                message="Device has not been polled", source="device_facts")
            return

        reachable = bool(fact.get("reachable"))
        error = str(fact.get("error") or "").strip()
        self.upsert(
            "device.reachability", device=device,
            value="reachable" if reachable else "unreachable",
            status="OK" if reachable else "CRITICAL",
            message="Latest persisted reachability observation",
            source="device_facts")
        self.upsert(
            "device.polling", device=device,
            value="error" if error else "healthy",
            status="WARNING" if error else "OK",
            message=error[:240] if error else "Latest persisted poll completed without an error",
            source="device_facts")

    def refresh_interface_health(self, device):
        """Generate interface sensors from persisted interface_stats only."""
        rows = self._query(
            "SELECT * FROM interface_stats WHERE device=? ORDER BY ifindex", (device,))
        if not rows:
            self._delete_types(device, _INTERFACE_SENSOR_TYPES)
            for sensor_type, message in (
                ("interface.status", "No interface status evidence collected"),
                ("interface.utilization", "No interface rate/capacity evidence collected"),
                ("interface.errors", "No interface error-counter evidence collected"),
                ("interface.discards", "Discard counters are not persisted in current interface evidence"),
            ):
                self.upsert(sensor_type, device=device, status="UNKNOWN",
                            message=message, source="interface_stats")
            return self.list(device=device)

        active_resources = {str(row.get("ifindex") or "") for row in rows}
        for row in rows:
            ifindex = str(row.get("ifindex") or "")
            descr = str(row.get("descr") or ifindex)
            admin = str(row.get("admin") or "").lower()
            oper = str(row.get("oper") or "").lower()
            if oper == "up":
                status = "OK"
                state_value = "UP"
            elif admin == "down" and oper in {"down", ""}:
                status = "OK"
                state_value = "DOWN"
            elif oper:
                status = "WARNING"
                state_value = oper.upper()
            else:
                status = "UNKNOWN"
                state_value = ""
            self.upsert(
                "interface.status", device=device, resource=ifindex,
                value=state_value, status=status,
                message=f"{descr}: admin={admin or 'unknown'} oper={oper or 'unknown'}",
                source="interface_stats")

            speed = int(row.get("speed") or 0)
            in_bps = row.get("in_bps")
            out_bps = row.get("out_bps")
            if speed > 0 and (in_bps is not None or out_bps is not None):
                peak_bps = max(float(in_bps or 0.0), float(out_bps or 0.0))
                utilization = (peak_bps / float(speed)) * 100.0
                if utilization >= 95.0:
                    util_status = "CRITICAL"
                elif utilization >= 80.0:
                    util_status = "WARNING"
                else:
                    util_status = "OK"
                self.upsert(
                    "interface.utilization", device=device, resource=ifindex,
                    value=f"{utilization:.2f}", unit="%", status=util_status,
                    message=f"{descr}: max persisted in/out rate against interface speed",
                    threshold="warning=80%;critical=95%", source="interface_stats")
            else:
                self.upsert(
                    "interface.utilization", device=device, resource=ifindex,
                    value="", unit="%", status="UNKNOWN",
                    message=f"{descr}: no rate/capacity evidence available",
                    threshold="warning=80%;critical=95%", source="interface_stats")

            error_count = int(row.get("in_errors") or 0) + int(row.get("out_errors") or 0)
            self.upsert(
                "interface.errors", device=device, resource=ifindex,
                value=str(error_count), unit="count",
                status="WARNING" if error_count else "OK",
                message=f"{descr}: persisted cumulative in/out error counters",
                source="interface_stats")
            self.upsert(
                "interface.discards", device=device, resource=ifindex,
                value="", unit="count", status="UNKNOWN",
                message=f"{descr}: discard counters are not persisted in current interface evidence",
                source="interface_stats")
        self._prune_resources(device, _INTERFACE_SENSOR_TYPES, active_resources)
        return self.list(device=device)

    def refresh_topology_health(self, device):
        """Generate topology sensors from persisted LLDP/CDP normalization only."""
        rows = self._query(
            "SELECT * FROM l2_neighbors WHERE device=? ORDER BY local_port,sys_name", (device,))
        if not rows:
            for sensor_type in _TOPOLOGY_SENSOR_TYPES:
                self.upsert(
                    sensor_type, device=device, value="", status="UNKNOWN",
                    message="No LLDP/CDP topology evidence collected",
                    source="l2_neighbors")
            return self.list(device=device)

        managed = sum(1 for row in rows if row.get("managed_neighbor"))
        unmanaged = len(rows) - managed
        self.upsert(
            "topology.neighbor", device=device, value=str(len(rows)), unit="count",
            status="WARNING" if unmanaged else "OK",
            message=f"Observed neighbors={len(rows)} managed={managed} unmanaged={unmanaged}",
            source="l2_neighbors")
        self.upsert(
            "topology.managed_neighbor_count", device=device, value=str(managed), unit="count",
            status="OK", message=f"Managed LLDP/CDP neighbors={managed}", source="l2_neighbors")
        self.upsert(
            "topology.unmanaged_neighbor_count", device=device, value=str(unmanaged), unit="count",
            status="WARNING" if unmanaged else "OK",
            message=f"Unmanaged LLDP/CDP neighbors={unmanaged}", source="l2_neighbors")
        return self.list(device=device)

    def refresh_mib_summary(self, device):
        """Map only known semantic MIB families; unknown raw OIDs stay raw/advanced."""
        rows = self._query(
            "SELECT * FROM mib_values WHERE device=? ORDER BY name,oid", (device,))
        loop_values = [
            row for row in (rows or [])
            if "loopprotect" in str(row.get("name") or "").lower()
        ]
        if not loop_values:
            self.conn.execute(
                "DELETE FROM sensors WHERE device=? AND sensor_type='loop_protection.health'",
                (device,))
            self.conn.commit()
            return self.list(device=device)

        enabled_ports = set()
        enabled_known = False
        detected_ports = set()
        historical_ports = set()
        last_event_ports = set()
        for item in loop_values:
            name = str(item.get("name") or "").lower()
            raw = item.get("value")
            port_key = name.rsplit(".", 1)[-1] if "." in name else name
            if "portenable" in name:
                truth = _mib_truth(raw)
                if truth is not None:
                    enabled_known = True
                    if truth:
                        enabled_ports.add(port_key)
            if "loopdetected" in name and _mib_truth(raw) is True:
                detected_ports.add(port_key)
            if "loopcount" in name:
                try:
                    if int(str(raw).strip()) > 0:
                        historical_ports.add(port_key)
                except ValueError:
                    pass
            if "lastlooptime" in name:
                try:
                    if int(str(raw).strip()) > 0:
                        last_event_ports.add(port_key)
                except ValueError:
                    pass
        affected_ports = detected_ports | historical_ports
        status = "CRITICAL" if detected_ports else ("WARNING" if affected_ports else "OK")
        value = "loop_detected" if detected_ports else "healthy"
        enabled_text = str(len(enabled_ports)) if enabled_known else "unknown"
        self.upsert(
            "loop_protection.health", device=device, value=value, status=status,
            message=(f"Enabled ports={enabled_text} Loop detected={len(detected_ports)} "
                     f"Ports with loop history={len(affected_ports)} "
                     f"Ports with recorded last event={len(last_event_ports)}"),
            source="mib_values:loopprotect")
        return self.list(device=device)

    def refresh_endpoint_evidence(self, device=""):
        """Summarize persisted L2/L3 endpoint evidence without treating absence as failure."""
        where = " WHERE device=?" if device else ""
        params = (device,) if device else ()
        ip_rows = self._query("SELECT ip FROM ip_neighbors" + where, params)
        arp_rows = self._query("SELECT ip FROM arp_entries" + where, params)
        fdb_rows = self._query("SELECT mac FROM vlan_fdb" + where, params)
        mac_rows = self._query("SELECT mac FROM mac_table" + where, params)
        l3_count = len(ip_rows or []) + len(arp_rows or [])
        l2_count = len(fdb_rows or []) + len(mac_rows or [])
        self.upsert(
            "endpoint.arp_evidence", device=device,
            value=str(l3_count) if l3_count else "", unit="count",
            status="OK" if l3_count else "UNKNOWN",
            message=(f"Persisted ARP/IP-neighbor evidence entries={l3_count}" if l3_count
                     else "No L3 IP neighbor evidence collected; this is not a failure verdict"),
            source="ip_neighbors+arp_entries")
        self.upsert(
            "endpoint.fdb_evidence", device=device,
            value=str(l2_count) if l2_count else "", unit="count",
            status="OK" if l2_count else "UNKNOWN",
            message=(f"Persisted FDB/MAC evidence entries={l2_count}" if l2_count
                     else "No FDB/MAC evidence collected"),
            source="vlan_fdb+mac_table")
        return self.list(device=device or None)

    def refresh_device_health(self, device):
        self._refresh_device_state(device)
        self.refresh_interface_health(device)
        self.refresh_topology_health(device)
        self.refresh_mib_summary(device)
        self.refresh_endpoint_evidence(device)
        return self.list(device=device)

    def refresh_sensor_set(self, inventory=None):
        """Generate the normalized set from existing DB/cache evidence only."""
        if inventory is not None:
            try:
                if hasattr(inventory, "all"):
                    devices = inventory.all()
                else:
                    devices = inventory.list()
            except Exception:
                devices = []
            for item in devices:
                name = item.get("name") or item.get("id") or ""
                if name:
                    self.refresh_device_health(name)
        else:
            rows = self._query("SELECT name FROM devices ORDER BY name") or []
            for row in rows:
                if row.get("name"):
                    self.refresh_device_health(row["name"])
        self.refresh_endpoint_evidence("")
        return self.list()

    def refresh_static_health(self):
        """Backward-compatible aggregate endpoint-evidence refresh."""
        return self.refresh_endpoint_evidence("")

    def refresh_inventory_health(self, inventory):
        """Backward-compatible entrypoint for API/UI callers."""
        return self.refresh_sensor_set(inventory)
