"""Durable progress for explicit, read-only collection and monitoring requests."""
import json
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import monitor
from .users import can

KIND_LABELS = {"collect": "Collect configuration", "snmp": "Poll SNMP",
               "monitor": "Check monitoring", "check": "Check selected devices"}
_CREATE_LOCK = threading.Lock()


def operations_for(manager):
    with _CREATE_LOCK:
        if not hasattr(manager, "_console_operations"):
            manager._console_operations = CollectionOperations(manager)
        return manager._console_operations


class CollectionOperations:
    def __init__(self, manager):
        self.manager = manager
        self.node = manager.settings.get("cluster_node_id") or socket.gethostname()
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="console-collection")
        self._pending = 0
        manager.db.conn.execute(
            "UPDATE collection_tasks SET state='interrupted',updated_ts=? "
            "WHERE node=? AND state IN ('queued','running')", (time.time(), self.node))
        manager.db.conn.commit()

    def get(self, task_id):
        row = self.manager.db.conn.execute(
            "SELECT * FROM collection_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return None
        result = dict(row)
        result["results"] = json.loads(result["results"])
        return result

    def recent(self, owner, admin=False):
        where, params = ("", ()) if admin else ("WHERE owner=?", (owner,))
        rows = self.manager.db.conn.execute(
            f"SELECT id FROM collection_tasks {where} ORDER BY created_ts DESC LIMIT 30", params).fetchall()
        return [self.get(row["id"]) for row in rows]

    def start(self, kind, names, actor, request_key):
        if kind not in KIND_LABELS:
            raise ValueError("Choose a supported collection action.")
        names = sorted(set(names))
        if not names:
            raise ValueError("Select at least one device.")
        with self._lock:
            old = self.manager.db.conn.execute(
                "SELECT id FROM collection_tasks WHERE owner=? AND request_key=?",
                (actor, request_key)).fetchone()
            if old:
                task = self.get(old["id"])
                if task["kind"] != kind or names != sorted(r["device"] for r in task["results"]):
                    raise ValueError("This request was already used for a different operation.")
                return task["id"]
            for name in names:
                dev = self.manager.inv.get(name)
                if not dev:
                    raise ValueError(f"{name}: device no longer exists.")
            if self._pending >= 8:
                raise ValueError("Eight collection tasks are active or waiting. Wait for one to finish.")
            task_id = uuid.uuid4().hex
            results = []
            for name in names:
                dev = self.manager.inv.get(name) or {}
                tab = {"collect": "config", "snmp": "snmp"}.get(kind)
                if tab is None:
                    tab = "monitoring" if monitor.saved_check_targets(dev) else "snmp" if dev.get("snmp_version") else "overview"
                results.append({"device": name, "state": "queued", "ok": None, "message": "", "target_tab": tab})
            now = time.time()
            self.manager.db.conn.execute(
                "INSERT INTO collection_tasks "
                "(id,owner,node,kind,state,created_ts,updated_ts,request_key,results) "
                "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT (owner,request_key) DO NOTHING",
                (task_id, actor, self.node, kind, "queued", now, now, request_key, json.dumps(results)))
            self.manager.db.conn.commit()
            saved = self.manager.db.conn.execute(
                "SELECT id FROM collection_tasks WHERE owner=? AND request_key=?",
                (actor, request_key)).fetchone()["id"]
            if saved != task_id:
                return saved
            self._pending += 1
            self._executor.submit(self._run, task_id)
            return task_id

    def _one(self, kind, name, actor):
        user = self.manager.users.get(actor)
        if not user or user.get("disabled") or not can(user["role"], "collect"):
            return False, "Permission to run checks is no longer available."
        dev = self.manager.inv.get(name)
        if not dev:
            return False, "Device no longer exists."
        if kind == "collect":
            result = self.manager.collect(name)
            return result.ok, result.message
        if kind == "snmp" or (kind == "check" and not monitor.saved_check_targets(dev)):
            if not dev.get("snmp_version"):
                return False, "No SNMP monitoring configured. Edit the device to set up checks."
            result = self.manager.snmp_poll(name, vendor_force=True)
            return bool(result.get("ok")), ("SNMP poll completed." if result.get("ok") else
                                           monitor.safe_check_detail(result.get("error") or "No SNMP response."))
        results = monitor.run_device_checks(self.manager, dev)
        monitor.normalize_results(self.manager, dev, results)
        if not results:
            return False, "No monitoring checks configured. Edit the device to add ports or URLs."
        failed = [r for r in results if r["status"] not in {"open", "valid"} and
                  not (r["kind"] == "http" and monitor.check_availability(
                      "http", r["status"], monitor.saved_check_targets(dev).get(("http", r["target"]))) == "up")]
        return not failed, ("All configured checks passed." if not failed else
                            "; ".join(r.get("detail") or f'{r["target"]}: {r["status"]}' for r in failed))

    def _save(self, task_id, state, results):
        self.manager.db.conn.execute(
            "UPDATE collection_tasks SET state=?,updated_ts=?,results=? WHERE id=?",
            (state, time.time(), json.dumps(results), task_id))
        self.manager.db.conn.commit()

    def _execute_one(self, task, row, results, progress_lock):
        with progress_lock:
            row["state"] = "running"
            self._save(task["id"], "running", results)
        return self._one(task["kind"], row["device"], task["owner"])

    def _run(self, task_id):
        task = self.get(task_id)
        results = task["results"]
        progress_lock = threading.RLock()
        try:
            self._save(task_id, "running", results)
            workers = max(1, min(256, int(self.manager.settings.get("bulk_workers") or 4), len(results)))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="device-check") as pool:
                futures = {pool.submit(self._execute_one, task, row, results, progress_lock): row
                           for row in results}
                for future in as_completed(futures):
                    row = futures[future]
                    try:
                        ok, message = future.result()
                        message = monitor.safe_check_detail(message)
                    except Exception:
                        ok, message = False, "The operation failed. Review the device settings and service log."
                    with progress_lock:
                        row.update(ok=ok, message=message, state="passed" if ok else "failed")
                        self._save(task_id, "running", results)
            state = "passed" if all(r["ok"] for r in results) else (
                "failed" if not any(r["ok"] for r in results) else "partial")
            self._save(task_id, state, results)
            self.manager.db.audit(task["owner"], "collection_task_finished", task_id, state)
        except Exception:
            self._save(task_id, "interrupted", results)
        finally:
            with self._lock:
                self._pending -= 1

    def close(self):
        self._executor.shutdown(wait=True)
