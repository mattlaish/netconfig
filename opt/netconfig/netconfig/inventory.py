"""
inventory.py -- Device inventory + groups over the shared DB connection.

Credentials are never stored here -- only a reference (`secret_ref`) into the
encrypted vault, so the inventory carries no secret material and backs up freely.

v2 adds device groups and a target resolver: bulk automation, compliance runs,
and the approval workflow all describe their target as (kind, value) where kind
is one of device|group|tag|all. `resolve_target` turns that into a device list,
so every feature shares one consistent notion of "which devices".
"""

import contextlib
import json
import time


_FIELDS = ["name", "host", "port", "platform", "device_type", "secret_ref", "enable_ref",
           "use_key", "legacy", "scrub", "enabled", "tags", "notes",
           "snmp_version", "snmp_ref", "netflow", "monitor_ports", "monitor_urls"]


class Inventory:
    def __init__(self, conn):
        self._conn = conn

    # ---- devices ---------------------------------------------------------
    def upsert(self, **kw):
        name = kw["name"]
        now = time.time()
        existing = self.get(name)
        data = {k: kw.get(k) for k in _FIELDS}
        if isinstance(data.get("tags"), (list, tuple)):
            data["tags"] = json.dumps(list(data["tags"]))
        for b in ("use_key", "legacy", "scrub", "enabled", "netflow"):
            if data.get(b) is not None:
                data[b] = int(bool(data[b]))
        if existing:
            merged = dict(existing)
            for k, v in data.items():
                if v is not None:
                    merged[k] = v
            merged["updated"] = now
            if isinstance(merged.get("tags"), (list, tuple)):
                merged["tags"] = json.dumps(list(merged["tags"]))
            for b in ("use_key", "legacy", "scrub", "enabled", "netflow"):
                merged[b] = int(bool(merged.get(b)))
            cols = ", ".join(f"{k}=:{k}" for k in _FIELDS + ["updated"])
            self._conn.execute(f"UPDATE devices SET {cols} WHERE name=:name",
                               {k: merged[k] for k in _FIELDS + ["updated"]})
        else:
            if data.get("host") is None:
                raise ValueError("host is required for a new device")
            if data.get("port") is None:
                data["port"] = 22
            if data.get("platform") is None:
                data["platform"] = "generic"
            if not data.get("device_type"):
                data["device_type"] = "network"
            if not data.get("tags"):
                data["tags"] = "[]"
            if data.get("notes") is None:
                data["notes"] = ""
            if data.get("snmp_version") is None:
                data["snmp_version"] = ""
            if data.get("monitor_ports") is None:
                data["monitor_ports"] = ""
            if data.get("monitor_urls") is None:
                data["monitor_urls"] = ""
            for b in ("use_key", "legacy", "scrub", "netflow"):
                data[b] = int(bool(data.get(b)))
            data["enabled"] = 0 if data.get("enabled") in (0, False) else 1
            data["created"] = now
            data["updated"] = now
            cols = ", ".join(_FIELDS + ["created", "updated"])
            ph = ", ".join(f":{k}" for k in _FIELDS + ["created", "updated"])
            self._conn.execute(f"INSERT INTO devices ({cols}) VALUES ({ph})", data)
        self._conn.commit()

    def get(self, name):
        r = self._conn.execute("SELECT * FROM devices WHERE name=?", (name,)).fetchone()
        return self._row(r) if r else None

    def rename(self, old, new):
        """Rename a device and cascade to all current-state tables. Historical
        rows (job_results, change_requests) keep the old name on purpose."""
        if not self.get(old):
            raise KeyError(old)
        if self.get(new):
            raise ValueError(f"a device named '{new}' already exists")
        lock = getattr(self._conn, "lock", None)
        with (lock if lock is not None else contextlib.nullcontext()):
            for tbl, col in (("devices", "name"), ("device_facts", "device"),
                             ("interface_stats", "device"), ("interface_samples", "device"),
                             ("runs", "device"), ("group_members", "device_name")):
                self._conn.execute(f"UPDATE {tbl} SET {col}=? WHERE {col}=?", (new, old))
            self._conn.commit()

    def delete(self, name):
        self._conn.execute("DELETE FROM devices WHERE name=?", (name,))
        self._conn.execute("DELETE FROM group_members WHERE device_name=?", (name,))
        self._conn.commit()

    def all(self, only_enabled=False):
        q = "SELECT * FROM devices"
        if only_enabled:
            q += " WHERE enabled=1"
        q += " ORDER BY name"
        return [self._row(r) for r in self._conn.execute(q).fetchall()]

    @staticmethod
    def _row(r):
        d = dict(r)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except json.JSONDecodeError:
            d["tags"] = []
        for b in ("use_key", "legacy", "scrub", "enabled", "netflow"):
            d[b] = bool(d.get(b))
        return d

    # ---- groups ----------------------------------------------------------
    def add_group(self, name, description=""):
        self._conn.execute(
            "INSERT OR REPLACE INTO groups (name, description, created) VALUES "
            "(?,?,COALESCE((SELECT created FROM groups WHERE name=?), ?))",
            (name, description, name, time.time()))
        self._conn.commit()

    def delete_group(self, name):
        self._conn.execute("DELETE FROM groups WHERE name=?", (name,))
        self._conn.execute("DELETE FROM group_members WHERE group_name=?", (name,))
        self._conn.commit()

    def groups(self):
        rows = self._conn.execute("SELECT * FROM groups ORDER BY name").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["members"] = self.group_members(d["name"])
            out.append(d)
        return out

    def group_members(self, name):
        rows = self._conn.execute(
            "SELECT device_name FROM group_members WHERE group_name=? ORDER BY device_name",
            (name,)).fetchall()
        return [r["device_name"] for r in rows]

    def set_group_members(self, name, devices):
        self._conn.execute("DELETE FROM group_members WHERE group_name=?", (name,))
        for d in devices:
            self._conn.execute(
                "INSERT OR IGNORE INTO group_members (group_name, device_name) VALUES (?,?)",
                (name, d))
        self._conn.commit()

    def add_to_group(self, name, device):
        self._conn.execute(
            "INSERT OR IGNORE INTO group_members (group_name, device_name) VALUES (?,?)",
            (name, device))
        self._conn.commit()

    # ---- target resolution ----------------------------------------------
    def resolve_target(self, kind, value, only_enabled=True):
        """Return a list of device dicts for a (kind, value) target spec.
        kind: device | group | tag | all."""
        kind = (kind or "all").lower()
        if kind == "all":
            return self.all(only_enabled=only_enabled)
        if kind == "device":
            names = [v.strip() for v in value.replace(",", " ").split() if v.strip()]
            out = []
            for n in names:
                d = self.get(n)
                if d and (d["enabled"] or not only_enabled):
                    out.append(d)
            return out
        if kind == "group":
            names = self.group_members(value)
            out = []
            for n in names:
                d = self.get(n)
                if d and (d["enabled"] or not only_enabled):
                    out.append(d)
            return out
        if kind == "tag":
            out = []
            for d in self.all(only_enabled=only_enabled):
                if value in d["tags"]:
                    out.append(d)
            return out
        raise ValueError(f"unknown target kind {kind!r}")

    # ---- run log ---------------------------------------------------------
    def log_run(self, device, ok, changed=False, message=""):
        self._conn.execute(
            "INSERT INTO runs (device, ts, ok, changed, message) VALUES (?,?,?,?,?)",
            (device, time.time(), int(ok), int(changed), message))
        self._conn.commit()

    def recent_runs(self, limit=100, device=None):
        if device:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE device=? ORDER BY ts DESC LIMIT ?",
                (device, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---- SNMP facts ------------------------------------------------------
    def set_facts(self, device, **f):
        f.setdefault("last_polled", time.time())
        cols = ["reachable", "sysname", "sysdescr", "sysobjectid", "uptime",
                "contact", "location", "last_polled", "error"]
        vals = {c: f.get(c) for c in cols}
        vals["reachable"] = int(bool(vals.get("reachable")))
        for c in ("sysname", "sysdescr", "sysobjectid", "uptime", "contact",
                  "location", "error"):
            if vals.get(c) is None:
                vals[c] = ""
        vals["device"] = device
        placeholders = ", ".join(["device"] + cols)
        binds = ", ".join(f":{c}" for c in ["device"] + cols)
        self._conn.execute(
            f"INSERT OR REPLACE INTO device_facts ({placeholders}) VALUES ({binds})",
            vals)
        self._conn.commit()

    def get_facts(self, device):
        r = self._conn.execute(
            "SELECT * FROM device_facts WHERE device=?", (device,)).fetchone()
        return dict(r) if r else None

    def all_facts(self):
        rows = self._conn.execute("SELECT * FROM device_facts").fetchall()
        return {r["device"]: dict(r) for r in rows}

    # ---- SNMP interface stats -------------------------------------------
    def set_interfaces(self, device, rows, history_seconds=1800):
        """Replace a device's interface samples. Computes in/out bit-rates from
        the previous sample's counters and elapsed time (skips on counter reset
        or wrap, where the delta would be negative). Atomic under the DB lock so
        a concurrent reader never sees the table mid-rebuild."""
        now = time.time()
        written = []
        lock = getattr(self._conn, "lock", None)
        with (lock if lock is not None else contextlib.nullcontext()):
            prior = {r["ifindex"]: r for r in self._conn.execute(
                "SELECT * FROM interface_stats WHERE device=?", (device,)).fetchall()}
            self._conn.execute("DELETE FROM interface_stats WHERE device=?", (device,))
            for r in rows:
                idx = str(r.get("ifindex"))
                in_o = int(r.get("in_octets") or 0)
                out_o = int(r.get("out_octets") or 0)
                in_bps = out_bps = None
                p = prior.get(idx)
                if p and p["ts"]:
                    dt = now - p["ts"]
                    if dt > 0:
                        if in_o >= p["in_octets"]:
                            in_bps = (in_o - p["in_octets"]) * 8.0 / dt
                        if out_o >= p["out_octets"]:
                            out_bps = (out_o - p["out_octets"]) * 8.0 / dt
                self._conn.execute(
                    "INSERT INTO interface_stats (device, ifindex, descr, admin, oper, "
                    "speed, in_octets, out_octets, in_errors, out_errors, in_bps, out_bps, ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (device, idx, r.get("descr", ""), r.get("admin", ""), r.get("oper", ""),
                     int(r.get("speed") or 0), in_o, out_o,
                     int(r.get("in_errors") or 0), int(r.get("out_errors") or 0),
                     in_bps, out_bps, now))
                if in_bps is not None or out_bps is not None:
                    self._conn.execute(
                        "INSERT INTO interface_samples (device, ifindex, ts, in_bps, out_bps) "
                        "VALUES (?,?,?,?,?)", (device, idx, now, in_bps, out_bps))
                    written.append((idx, r.get("descr", ""), in_bps, out_bps, now))
            cutoff = now - float(history_seconds or 1800)
            self._conn.execute("DELETE FROM interface_samples WHERE ts < ?", (cutoff,))
            self._conn.commit()
        # samples that got a computed rate this poll, for an optional long-term
        # history backend (see manager.snmp_poll / ifhistory).
        return written

    def get_samples(self, device, since=None):
        """Return {ifindex: {descr, points: [[ts, in_bps, out_bps], ...]}}."""
        args = [device]
        q = "SELECT * FROM interface_samples WHERE device=?"
        if since is not None:
            q += " AND ts >= ?"
            args.append(since)
        q += " ORDER BY ts"
        descrs = {r["ifindex"]: r["descr"] for r in self._conn.execute(
            "SELECT ifindex, descr FROM interface_stats WHERE device=?", (device,))}
        out = {}
        for r in self._conn.execute(q, args):
            idx = r["ifindex"]
            d = out.setdefault(idx, {"descr": descrs.get(idx, idx), "points": []})
            d["points"].append([r["ts"], r["in_bps"], r["out_bps"]])
        return out

    def get_interfaces(self, device):
        rows = self._conn.execute(
            "SELECT * FROM interface_stats WHERE device=?", (device,)).fetchall()
        def _key(r):
            try:
                return int(r["ifindex"])
            except (ValueError, TypeError):
                return 0
        return [dict(r) for r in sorted(rows, key=_key)]

    def interface_counts(self):
        """Return {device: (up_count, total_count)} for the fleet."""
        out = {}
        for r in self._conn.execute(
                "SELECT device, oper, COUNT(*) c FROM interface_stats GROUP BY device, oper"):
            up, tot = out.get(r["device"], (0, 0))
            tot += r["c"]
            if r["oper"] == "up":
                up += r["c"]
            out[r["device"]] = (up, tot)
        return out
