"""HA-1 control-plane HA/DR readiness and recovery evidence foundation.

HA-1 does not implement automatic database failover. It provides a durable,
fail-closed control-plane node lifecycle, scheduler drain semantics, recovery
evidence, and readiness reporting over the PH-2 PostgreSQL coordination layer.
"""
from __future__ import annotations

import json
import time


_NODE_STATES = {"ACTIVE", "DRAINING", "DRAINED"}
_DRILL_KINDS = {"NODE_FAILOVER", "DATABASE_RESTORE", "REBOOT_RECOVERY", "BACKUP_VERIFY"}
_DRILL_STATES = {"STARTED", "PASSED", "FAILED", "NOT_RUN"}


class HAService:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn

    def _fresh_nodes(self, stale_seconds=90):
        stale_seconds = max(30, int(stale_seconds))
        since = time.time() - stale_seconds
        try:
            return self.manager.db.list_cluster_nodes(since)
        except Exception:
            rows = self.conn.execute(
                "SELECT * FROM cluster_nodes WHERE last_heartbeat_ts>=? ORDER BY node_id",
                (since,),
            ).fetchall()
            return [dict(row) for row in rows]

    def nodes(self, stale_seconds=86_400):
        stale_seconds = min(31_536_000, max(30, int(stale_seconds)))
        return self._fresh_nodes(stale_seconds)

    def node(self, node_id=None):
        node_id = str(node_id or self.manager.cluster_node_id)
        try:
            return self.manager.db.get_cluster_node(node_id)
        except Exception:
            row = self.conn.execute(
                "SELECT * FROM cluster_nodes WHERE node_id=?", (node_id,)
            ).fetchone()
            return dict(row) if row else None

    def current_node_state(self):
        item = self.node()
        return str((item or {}).get("state") or "ACTIVE").upper()

    def accepts_automation_work(self):
        return self.current_node_state() == "ACTIVE"

    def require_active_node(self):
        state = self.current_node_state()
        if state != "ACTIVE":
            raise RuntimeError(f"control-plane node is {state}; new automation work is refused")

    def set_node_state(self, *, state, actor, node_id=None, reason=""):
        state = str(state or "").upper()
        if state not in _NODE_STATES:
            raise ValueError("unsupported cluster node state")
        node_id = str(node_id or self.manager.cluster_node_id)
        reason = str(reason or "").replace("\x00", "")[:500]
        if state in {"DRAINING", "DRAINED"} and not reason:
            raise ValueError("draining a control-plane node requires a reason")
        row = self.manager.db.set_cluster_node_state(node_id, state, reason)
        if node_id == self.manager.cluster_node_id and state != "ACTIVE":
            for scheduler in (
                "snmp-poller",
                "compliance-digest",
                "monitor-poller",
                "operational-lifecycle",
                "telemetry-lifecycle",
                "diagnostic-maintenance",
            ):
                try:
                    self.manager.db.advisory_unlock(f"netconfig:scheduler:{scheduler}")
                except Exception:
                    pass
        self.manager.db.audit(
            actor,
            "cluster_node_state",
            node_id,
            f"state={state};reason={reason if state != 'ACTIVE' else ''}",
        )
        return row

    def drain_current_node(self, *, actor, reason, final=False):
        return self.set_node_state(
            state="DRAINED" if final else "DRAINING",
            actor=actor,
            reason=reason,
        )

    def activate_current_node(self, *, actor):
        return self.set_node_state(state="ACTIVE", actor=actor)

    def readiness(self, stale_seconds=90):
        storage = self.manager.storage_status()
        nodes = self._fresh_nodes(stale_seconds)
        backend = storage.get("backend") or getattr(self.manager.db, "dialect", "sqlite")
        active_nodes = [node for node in nodes if str(node.get("state") or "ACTIVE").upper() == "ACTIVE"]
        local = next(
            (node for node in nodes if node.get("node_id") == self.manager.cluster_node_id),
            self.node(),
        )
        issues = []
        if backend != "postgres":
            issues.append("core backend is not PostgreSQL; multi-node HA is unavailable")
        if not getattr(self.manager.db, "distributed_capable", False):
            issues.append("core backend is not distributed-capable")
        if backend == "postgres" and len(active_nodes) < 2:
            issues.append("fewer than two fresh ACTIVE cluster nodes are visible")
        if local and str(local.get("state") or "ACTIVE").upper() != "ACTIVE":
            issues.append(f"local control-plane node is {str(local.get('state')).upper()}")
        return {
            "backend": backend,
            "distributed_capable": bool(getattr(self.manager.db, "distributed_capable", False)),
            "fresh_nodes": nodes,
            "fresh_node_count": len(nodes),
            "fresh_active_node_count": len(active_nodes),
            "local_node": local,
            "accepts_automation_work": self.accepts_automation_work(),
            "ready_for_multi_node": not issues,
            "issues": issues,
            "scheduler_lock_model": (
                "postgresql_advisory_session_lock" if backend == "postgres" else "single_node"
            ),
            "database_backup": (
                "pg_dump_custom_format" if backend == "postgres" else "sqlite_file_backup_external"
            ),
            "automatic_database_failover": False,
            "pitr_managed_by_netconfig": False,
        }

    def start_drill(self, *, kind, actor, detail=None, node_id="", verification_ref=""):
        return self.record_drill(
            kind=kind,
            actor=actor,
            state="STARTED",
            detail=detail,
            node_id=node_id,
            verification_ref=verification_ref,
        )

    def complete_drill(self, drill_id, *, actor, state, detail=None, verification_ref=""):
        state = str(state or "").upper()
        if state not in {"PASSED", "FAILED", "NOT_RUN"}:
            raise ValueError("drill completion state must be PASSED, FAILED, or NOT_RUN")
        current = self.get_drill(drill_id)
        if not current:
            raise ValueError("unknown recovery drill")
        if current["state"] != "STARTED":
            raise ValueError("only STARTED recovery drills can be completed")
        merged = dict(current.get("detail") or {})
        if detail:
            if not isinstance(detail, dict):
                raise ValueError("recovery drill detail must be an object")
            merged.update(detail)
        ref = str(verification_ref or current.get("verification_ref") or "").replace("\x00", "")[:500]
        self.conn.execute(
            "UPDATE recovery_drills SET state=?,detail_json=?,verification_ref=?,finished_ts=? WHERE id=?",
            (state, json.dumps(merged, sort_keys=True), ref, time.time(), int(drill_id)),
        )
        self.conn.commit()
        self.manager.db.audit(
            actor,
            "recovery_drill_complete",
            f"DRILL#{int(drill_id)}",
            f"kind={current['kind']};state={state};verification_ref={ref}",
        )
        return self.get_drill(drill_id)

    def record_drill(
        self,
        *,
        kind,
        actor,
        state,
        detail=None,
        node_id="",
        verification_ref="",
    ):
        kind = str(kind or "").upper()
        state = str(state or "").upper()
        if kind not in _DRILL_KINDS:
            raise ValueError("unsupported recovery drill kind")
        if state not in _DRILL_STATES:
            raise ValueError("unsupported recovery drill state")
        if detail is not None and not isinstance(detail, dict):
            raise ValueError("recovery drill detail must be an object")
        now = time.time()
        node_id = str(node_id or self.manager.cluster_node_id).replace("\x00", "")[:256]
        verification_ref = str(verification_ref or "").replace("\x00", "")[:500]
        cur = self.conn.execute(
            "INSERT INTO recovery_drills "
            "(kind,actor,state,node_id,verification_ref,detail_json,started_ts,finished_ts) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                kind,
                actor,
                state,
                node_id,
                verification_ref,
                json.dumps(detail or {}, sort_keys=True),
                now,
                now if state != "STARTED" else 0,
            ),
        )
        self.conn.commit()
        self.manager.db.audit(
            actor,
            "recovery_drill_record",
            f"DRILL#{cur.lastrowid}",
            f"kind={kind};state={state};verification_ref={verification_ref}",
        )
        return self.get_drill(cur.lastrowid)

    def get_drill(self, drill_id):
        row = self.conn.execute(
            "SELECT * FROM recovery_drills WHERE id=?", (int(drill_id),)
        ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["detail"] = json.loads(out.pop("detail_json"))
        except (TypeError, json.JSONDecodeError):
            out["detail"] = {}
            out.pop("detail_json", None)
        return out

    def drills(self, limit=100):
        limit = min(5000, max(1, int(limit)))
        return [
            self.get_drill(row["id"])
            for row in self.conn.execute(
                "SELECT id FROM recovery_drills ORDER BY started_ts DESC LIMIT ?", (limit,)
            ).fetchall()
        ]
