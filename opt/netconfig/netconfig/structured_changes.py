"""PH-4 structured configuration transaction engine.

Every write originates from an allow-listed VM-1 typed resource.  The engine
creates durable provenance before I/O, performs an exact typed pre-read,
executes one constrained protocol operation, performs exact post-read
verification, and records rollback semantics.  It never accepts arbitrary
NETCONF RPC XML, RESTCONF URLs/bodies, shell commands, or protobuf requests.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import contextmanager

from .structured_protocols import StructuredProtocolError


class StructuredChangeError(RuntimeError):
    pass


_ALLOWED_SOURCES = {"manual", "api", "desired_state", "campaign", "rollback", "remediation"}


_ALLOWED_TRANSITIONS = {
    "PENDING": {"RUNNING", "FAILED", "RECOVERY_REQUIRED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "RECOVERY_REQUIRED"},
    "SUCCEEDED": set(),
    "FAILED": {"RECOVERY_REQUIRED"},
    "RECOVERY_REQUIRED": {"ROLLING_BACK", "RECOVERED"},
    "ROLLING_BACK": {"RECOVERED", "FAILED"},
    "RECOVERED": set(),
}


def _validate_transition(current, target):
    if current == target:
        return
    allowed = _ALLOWED_TRANSITIONS.get(str(current), set())
    if str(target) not in allowed:
        raise StructuredChangeError(
            f"invalid structured transaction transition: {current} -> {target}"
        )


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _hash_value(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _bounded(text, limit=500):
    return str(text or "").replace("\x00", "")[:limit]


class StructuredChangeEngine:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn
        self._lock_guard = threading.Lock()
        self._resource_locks = {}

    @contextmanager
    def _resource_lock(self, device, resource, selectors):
        material = _json({"device": device, "resource": resource, "selectors": selectors})
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        lock_name = f"netconfig:structured-change:{digest}"
        with self._lock_guard:
            local = self._resource_locks.setdefault(digest, threading.RLock())
        if not local.acquire(timeout=10):
            raise StructuredChangeError("timed out waiting for the local structured-resource lock")
        advisory = False
        try:
            advisory = bool(self.manager.db.try_advisory_lock(lock_name))
            if not advisory:
                raise StructuredChangeError("an equivalent structured resource is being changed by another node")
            yield
        finally:
            if advisory:
                try:
                    self.manager.db.advisory_unlock(lock_name)
                except Exception:
                    pass
            local.release()

    @staticmethod
    def _row(row):
        if not row:
            return None
        out = dict(row)
        for src, dst in (("request_json", "request"), ("pre_value_json", "pre_value"),
                         ("post_value_json", "post_value")):
            raw = out.get(src) or ""
            if raw:
                try:
                    out[dst] = json.loads(raw)
                except json.JSONDecodeError:
                    out[dst] = None
            else:
                out[dst] = None
        out["changed"] = bool(out.get("changed"))
        out["reversible"] = bool(out.get("reversible"))
        return out

    def list(self, limit=200, *, device=None, state=None):
        limit = min(5000, max(1, int(limit)))
        where, params = [], []
        if device:
            where.append("device=?"); params.append(str(device))
        if state:
            where.append("state=?"); params.append(str(state))
        sql = "SELECT * FROM structured_change_transactions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_ts DESC LIMIT ?"
        params.append(limit)
        return [self._row(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def get(self, txid):
        return self._row(self.conn.execute(
            "SELECT * FROM structured_change_transactions WHERE id=?", (int(txid),)).fetchone())

    def _existing_idempotent(self, key):
        if not key:
            return None
        row = self.conn.execute(
            "SELECT * FROM structured_change_transactions WHERE idempotency_key=? "
            "ORDER BY id DESC LIMIT 1", (key,)).fetchone()
        if not row:
            return None
        item = self._row(row)
        if item["state"] == "SUCCEEDED":
            return item
        if item["state"] in {"PENDING", "RUNNING"}:
            raise StructuredChangeError("an equivalent structured change is already in progress")
        if item["state"] == "RECOVERY_REQUIRED":
            raise StructuredChangeError(
                "an equivalent structured change has an unresolved interrupted outcome; reconcile it before retry"
            )
        return None

    @staticmethod
    def _idempotency(source_kind, source_ref, device, resource, selectors, explicit=""):
        key = str(explicit or "").strip()
        if key:
            if len(key) > 256 or any(ord(c) < 0x20 for c in key):
                raise StructuredChangeError("invalid structured-change idempotency key")
            return key
        if not source_ref:
            return ""
        material = _json({"source_kind": source_kind, "source_ref": source_ref,
                          "device": device, "resource": resource, "selectors": selectors})
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _write(self, dev, profile, resolved, *, actor, before_value):
        protocol = profile["protocol"]
        if protocol == "restconf":
            return self.manager.structured_collector.restconf_replace_typed(
                dev, profile, resolved=resolved, actor=actor, approved=True)
        if protocol == "gnmi":
            return self.manager.structured_collector.gnmi_set_typed(
                dev, profile, path=resolved["gnmi_path"], value=resolved["value"],
                actor=actor, approved=True, before_value=before_value,
                value_type=resolved.get("value_type", "string"),
                leaf_hint=self.manager.structured_collector._resolved_leaf_name(resolved))
        if protocol == "netconf":
            return self.manager.structured_collector.netconf_edit_typed(
                dev, profile, resolved=resolved, actor=actor, approved=True,
                before_value=before_value)
        raise StructuredChangeError("structured write requires NETCONF, RESTCONF, or gNMI")

    def _compensate(self, dev, profile, resolved, *, actor, before_value):
        rollback_resolved = dict(resolved)
        rollback_resolved["value"] = before_value
        try:
            self._write(dev, profile, rollback_resolved, actor=actor, before_value=None)
            current, _ = self.manager.structured_collector.read_resource_value(dev, profile, rollback_resolved)
            return "restored_preimage" if current == before_value else "FAILED"
        except Exception:
            return "FAILED"

    def execute_resource(self, *, device, resource, selectors, value, actor,
                         approved=False, approval_ref="", source_kind="manual", source_ref="",
                         idempotency_key="", rollback_of_id=None):
        selectors = selectors or {}
        self.manager.ha.require_active_node()
        with self._resource_lock(device, resource, selectors):
            return self._execute_resource_locked(
                device=device, resource=resource, selectors=selectors, value=value, actor=actor,
                approved=approved, approval_ref=approval_ref, source_kind=source_kind,
                source_ref=source_ref, idempotency_key=idempotency_key, rollback_of_id=rollback_of_id,
            )

    def _execute_resource_locked(self, *, device, resource, selectors, value, actor,
                                 approved=False, approval_ref="", source_kind="manual", source_ref="",
                                 idempotency_key="", rollback_of_id=None):
        if not approved:
            raise StructuredChangeError("structured write requires an approved change context")
        approval_ref = _bounded(approval_ref, 256)
        if not approval_ref.startswith("CR#"):
            raise StructuredChangeError(
                "structured write requires a durable approved change-request reference"
            )
        actor = str(actor or "").strip()
        if not actor:
            raise StructuredChangeError("structured write requires an actor")
        source_kind = str(source_kind or "manual").strip().lower()
        if source_kind not in _ALLOWED_SOURCES:
            raise StructuredChangeError("unsupported structured-change source kind")
        dev, profile = self.manager._structured_profile_for(device)
        protocol = profile["protocol"]
        if protocol not in {"netconf", "restconf", "gnmi"}:
            raise StructuredChangeError("structured write requires NETCONF, RESTCONF, or gNMI")
        resolved = self.manager.vendor_models.resolve(
            device, resource, selectors, value, protocol=protocol)
        if resolved.get("sensitive"):
            raise StructuredChangeError("sensitive structured resources are not supported by the PH-4 durable ledger")
        source_ref = _bounded(source_ref, 256)
        idem = self._idempotency(source_kind, source_ref, device, resource,
                                 resolved["selectors"], idempotency_key)
        existing = self._existing_idempotent(idem)
        if existing:
            return existing

        request = {k: resolved[k] for k in (
            "pack", "pack_sha256", "resource", "selectors", "value", "value_type")}
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO structured_change_transactions "
            "(device,protocol,actor,source_kind,source_ref,approval_ref,idempotency_key,operation,resource,"
            "request_json,state,rollback_of_id,created_ts) VALUES (?,?,?,?,?,?,?,?,?,?,? ,?,?)",
            (device, protocol, actor, source_kind, source_ref, approval_ref, idem,
             "replace", resource, _json(request), "PENDING",
             int(rollback_of_id) if rollback_of_id else None, now),
        )
        self.conn.commit()
        txid = cur.lastrowid
        self.manager.db.audit(
            actor, "structured_change_prepare", device,
            f"tx={txid};protocol={protocol};resource={resource};source={source_kind};approval={approval_ref}")
        _validate_transition("PENDING", "RUNNING")
        self.conn.execute(
            "UPDATE structured_change_transactions SET state='RUNNING',started_ts=? WHERE id=?",
            (time.time(), txid))
        self.conn.commit()

        pre_value = None
        try:
            pre_value, _pre_meta = self.manager.structured_collector.read_resource_value(
                dev, profile, resolved)
            pre_json = _json(pre_value)
            pre_hash = _hash_value(pre_value)
            self.conn.execute(
                "UPDATE structured_change_transactions SET pre_hash=?,pre_value_json=?,reversible=1 WHERE id=?",
                (pre_hash, pre_json, txid))
            self.conn.commit()

            if pre_value == resolved["value"]:
                self.conn.execute(
                    "UPDATE structured_change_transactions SET state='SUCCEEDED',changed=0,post_hash=?,"
                    "post_value_json=?,verification_state='ALREADY_COMPLIANT',rollback_state='not_needed',"
                    "finished_ts=? WHERE id=?",
                    (pre_hash, pre_json, time.time(), txid))
                self.conn.commit()
                self.manager.db.audit(
                    actor, "structured_change_complete", device,
                    f"tx={txid};protocol={protocol};resource={resource};state=SUCCEEDED;changed=0")
                return self.get(txid)

            result = self._write(dev, profile, resolved, actor=actor, before_value=pre_value)
            post_value, _post_meta = self.manager.structured_collector.read_resource_value(
                dev, profile, resolved)
            if post_value != resolved["value"]:
                rollback = self._compensate(
                    dev, profile, resolved, actor=actor, before_value=pre_value)
                raise StructuredChangeError(
                    f"exact post-change verification failed; rollback={rollback}")
            post_json = _json(post_value)
            self.conn.execute(
                "UPDATE structured_change_transactions SET state='SUCCEEDED',changed=1,pre_hash=?,post_hash=?,"
                "pre_value_json=?,post_value_json=?,reversible=1,verification_state='VERIFIED',"
                "rollback_state=?,finished_ts=? WHERE id=?",
                (pre_hash, _hash_value(post_value), pre_json, post_json,
                 _bounded(result.get("rollback", "available"), 64), time.time(), txid),
            )
            self.conn.commit()
            self.manager.db.audit(
                actor, "structured_change_complete", device,
                f"tx={txid};protocol={protocol};resource={resource};state=SUCCEEDED;changed=1")
            return self.get(txid)
        except Exception as exc:
            error = type(exc).__name__
            detail = _bounded(exc, 500)
            rollback = "UNKNOWN"
            if "rollback=" in detail:
                rollback = detail.rsplit("rollback=", 1)[-1].split(";", 1)[0][:64]
            _validate_transition("RUNNING", "FAILED")
            self.conn.execute(
                "UPDATE structured_change_transactions SET state='FAILED',verification_state='FAILED',"
                "rollback_state=?,error=?,finished_ts=? WHERE id=?",
                (rollback, f"{error}: {detail}", time.time(), txid),
            )
            self.conn.commit()
            self.manager.db.audit(
                actor, "structured_change_complete", device,
                f"tx={txid};protocol={protocol};resource={resource};state=FAILED;error={error};rollback={rollback}")
            if isinstance(exc, (StructuredProtocolError, StructuredChangeError)):
                raise StructuredChangeError(str(exc)) from exc
            raise StructuredChangeError(f"structured change failed: {error}") from exc

    def interrupted(self, stale_seconds=300):
        cutoff = time.time() - max(30, int(stale_seconds))
        rows = self.conn.execute(
            "SELECT * FROM structured_change_transactions "
            "WHERE state IN ('PENDING','RUNNING') AND created_ts<? ORDER BY created_ts",
            (cutoff,),
        ).fetchall()
        return [self._row(row) for row in rows]

    def mark_interrupted_for_recovery(self, *, actor, stale_seconds=300):
        items = self.interrupted(stale_seconds)
        for item in items:
            state = "FAILED" if item["state"] == "PENDING" else "RECOVERY_REQUIRED"
            error = (
                "interrupted before network I/O could be established"
                if item["state"] == "PENDING"
                else "process interruption left remote write outcome uncertain; operator verification required"
            )
            self.conn.execute(
                "UPDATE structured_change_transactions SET state=?,verification_state='INTERRUPTED',"
                "error=?,finished_ts=? WHERE id=? AND state=?",
                (state, error, time.time(), int(item["id"]), item["state"]),
            )
            self.manager.db.audit(
                actor,
                "structured_change_recovery_mark",
                item["device"],
                f"tx={item['id']};old_state={item['state']};new_state={state}",
            )
        self.conn.commit()
        return [self.get(item["id"]) for item in items]

    def recover(self, txid, *, actor):
        item = self.get(txid)
        if not item:
            raise StructuredChangeError("unknown structured change transaction")
        if item["state"] != "RECOVERY_REQUIRED":
            raise StructuredChangeError("only RECOVERY_REQUIRED transactions can be reconciled")
        request = item.get("request") or {}
        dev, profile = self.manager._structured_profile_for(item["device"])
        resolved = self.manager.vendor_models.resolve(
            item["device"], item["resource"], request.get("selectors") or {},
            request.get("value"), protocol=profile["protocol"],
        )
        if request.get("pack_sha256") and resolved.get("pack_sha256") != request.get("pack_sha256"):
            raise StructuredChangeError(
                "recovery refused because the model-pack mapping changed after the interrupted transaction"
            )
        try:
            current, _meta = self.manager.structured_collector.read_resource_value(
                dev, profile, resolved
            )
        except Exception as exc:
            self.manager.db.audit(
                actor, "structured_change_recovery_read", item["device"],
                f"tx={int(txid)};state=ERROR;type={type(exc).__name__}",
            )
            raise StructuredChangeError(
                f"recovery verification read failed: {type(exc).__name__}"
            ) from exc
        expected = request.get("value")
        pre_value = item.get("pre_value")
        now = time.time()
        if current == expected:
            post_json = _json(current)
            changed = pre_value != current if item.get("pre_value_json") else True
            self.conn.execute(
                "UPDATE structured_change_transactions SET state='SUCCEEDED',changed=?,post_hash=?,"
                "post_value_json=?,reversible=?,verification_state='RECOVERED_VERIFIED',"
                "rollback_state=?,error='',finished_ts=? WHERE id=?",
                (
                    int(bool(changed)), _hash_value(current), post_json,
                    int(bool(item.get("pre_value_json"))),
                    "compensating_preimage_available" if item.get("pre_value_json") else "UNKNOWN",
                    now, int(txid),
                ),
            )
            outcome = "SUCCEEDED"
        elif item.get("pre_value_json") and current == pre_value:
            self.conn.execute(
                "UPDATE structured_change_transactions SET state='FAILED',changed=0,post_hash=?,"
                "post_value_json=?,verification_state='RECOVERED_PREIMAGE',rollback_state='not_needed',"
                "error='interrupted write did not leave the requested value active',finished_ts=? WHERE id=?",
                (_hash_value(current), _json(current), now, int(txid)),
            )
            outcome = "FAILED_PREIMAGE"
        else:
            self.conn.execute(
                "UPDATE structured_change_transactions SET verification_state='RECOVERY_AMBIGUOUS',"
                "error='live value matches neither the intended value nor the recorded pre-image' WHERE id=?",
                (int(txid),),
            )
            outcome = "AMBIGUOUS"
        self.conn.commit()
        self.manager.db.audit(
            actor, "structured_change_recovery_reconcile", item["device"],
            f"tx={int(txid)};outcome={outcome}",
        )
        return self.get(txid)

    def rollback(self, txid, *, actor, approved=False, approval_ref=""):
        original = self.get(txid)
        if not original:
            raise StructuredChangeError("unknown structured change transaction")
        if original["state"] != "SUCCEEDED" or not original["changed"]:
            raise StructuredChangeError("only a successful changed transaction can be rolled back")
        if not original["reversible"] or original.get("pre_value") is None:
            raise StructuredChangeError("transaction has no safe typed pre-image for rollback")
        if original.get("rollback_transaction_id"):
            existing = self.get(original["rollback_transaction_id"])
            if existing and existing["state"] == "SUCCEEDED":
                return existing
        request = original.get("request") or {}
        dev, profile = self.manager._structured_profile_for(original["device"])
        resolved_current = self.manager.vendor_models.resolve(
            original["device"], original["resource"], request.get("selectors") or {},
            request.get("value"), protocol=profile["protocol"])
        current, _ = self.manager.structured_collector.read_resource_value(dev, profile, resolved_current)
        if current != original.get("post_value"):
            raise StructuredChangeError(
                "rollback refused because the live resource no longer matches the original verified post-image")
        rolled = self.execute_resource(
            device=original["device"], resource=original["resource"],
            selectors=request.get("selectors") or {}, value=original["pre_value"],
            actor=actor, approved=approved, approval_ref=approval_ref,
            source_kind="rollback", source_ref=f"TX#{int(txid)}",
            idempotency_key=f"rollback:{int(txid)}", rollback_of_id=int(txid))
        self.conn.execute(
            "UPDATE structured_change_transactions SET rollback_transaction_id=?,rollback_state=? WHERE id=?",
            (rolled["id"], "ROLLED_BACK" if rolled["state"] == "SUCCEEDED" else "ROLLBACK_FAILED", int(txid)))
        self.conn.commit()
        self.manager.db.audit(actor, "structured_change_rollback", original["device"],
                              f"original_tx={txid};rollback_tx={rolled['id']};state={rolled['state']}")
        return rolled
