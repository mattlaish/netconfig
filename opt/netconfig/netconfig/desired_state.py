"""NA-1 declarative desired-state management over PH-4 transactions."""
from __future__ import annotations

import json
import time


class DesiredStateError(RuntimeError):
    pass


class DesiredStateService:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn

    @staticmethod
    def _document(document):
        if not isinstance(document, dict) or set(document) - {"operations"}:
            raise DesiredStateError("desired-state document must contain only operations")
        ops = document.get("operations")
        if not isinstance(ops, list) or not ops or len(ops) > 256:
            raise DesiredStateError("desired-state document requires 1..256 operations")
        clean = []
        for op in ops:
            if not isinstance(op, dict) or set(op) - {"resource", "selectors", "value"}:
                raise DesiredStateError("desired-state operation contains unsupported fields")
            resource = str(op.get("resource") or "").strip()
            if not resource or len(resource) > 128:
                raise DesiredStateError("invalid desired-state resource")
            selectors = op.get("selectors") or {}
            if not isinstance(selectors, dict) or len(selectors) > 8:
                raise DesiredStateError("invalid desired-state selectors")
            clean.append({"resource": resource, "selectors": dict(selectors), "value": op.get("value")})
        return {"operations": clean}

    def create(self, *, name, target_kind, target_value, document, actor, description="",
               revision=1, supersedes_id=None):
        if target_kind not in {"device", "group", "tag"}:
            raise DesiredStateError("unsupported desired-state target kind")
        name = str(name or "").strip()
        if not name or len(name) > 128:
            raise DesiredStateError("desired-state name is required and must be <=128 characters")
        doc = self._document(document)
        now = time.time()
        try:
            cur = self.conn.execute(
                "INSERT INTO desired_states (name,description,target_kind,target_value,document_json,state,revision,"
                "supersedes_id,created_by,created_ts,updated_by,updated_ts) "
                "VALUES (?,?,?,?,?,'DRAFT',?,?,?,?,?,?)",
                (name, str(description or "")[:1024], target_kind, str(target_value)[:256],
                 json.dumps(doc, sort_keys=True), max(1, int(revision)),
                 int(supersedes_id) if supersedes_id else None, actor, now, actor, now),
            )
        except Exception as exc:
            raise DesiredStateError("desired-state name already exists or could not be stored") from exc
        self.conn.commit()
        self.manager.db.audit(actor, "desired_state_create", f"DS#{cur.lastrowid}",
                              f"name={name};revision={max(1,int(revision))}")
        return self.get(cur.lastrowid)

    def get(self, dsid):
        row = self.conn.execute("SELECT * FROM desired_states WHERE id=?", (int(dsid),)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["document"] = json.loads(out.pop("document_json"))
        return out

    def list(self):
        return [self.get(r["id"]) for r in self.conn.execute(
            "SELECT id FROM desired_states ORDER BY name").fetchall()]

    def update(self, dsid, *, document=None, description=None, target_kind=None,
               target_value=None, actor="system"):
        item = self.get(dsid)
        if not item or item["state"] != "DRAFT":
            raise DesiredStateError("only DRAFT desired state can be edited")
        new_kind = target_kind or item["target_kind"]
        if new_kind not in {"device", "group", "tag"}:
            raise DesiredStateError("unsupported desired-state target kind")
        new_doc = self._document(document) if document is not None else item["document"]
        now = time.time()
        self.conn.execute(
            "UPDATE desired_states SET description=?,target_kind=?,target_value=?,document_json=?,"
            "updated_by=?,updated_ts=? WHERE id=?",
            (str(item["description"] if description is None else description)[:1024], new_kind,
             str(item["target_value"] if target_value is None else target_value)[:256],
             json.dumps(new_doc, sort_keys=True), actor, now, int(dsid)))
        self.conn.commit()
        self.manager.db.audit(actor, "desired_state_update", f"DS#{dsid}", item["name"])
        return self.get(dsid)

    def clone_revision(self, dsid, *, actor, name=None):
        item = self.get(dsid)
        if not item:
            raise DesiredStateError("unknown desired state")
        revision = int(item.get("revision") or 1) + 1
        new_name = str(name or f"{item['name']}-r{revision}")
        return self.create(
            name=new_name, target_kind=item["target_kind"], target_value=item["target_value"],
            document=item["document"], actor=actor, description=item.get("description") or "",
            revision=revision, supersedes_id=int(dsid))

    def publish(self, dsid, actor):
        item = self.get(dsid)
        if not item or item["state"] != "DRAFT":
            raise DesiredStateError("only DRAFT desired state can be published")
        self.plan(dsid)  # compile every target/resource before publication
        now = time.time()
        self.conn.execute(
            "UPDATE desired_states SET state='PUBLISHED',published_by=?,published_ts=?,updated_by=?,updated_ts=? WHERE id=?",
            (actor, now, actor, now, int(dsid)))
        if item.get("supersedes_id"):
            self.conn.execute(
                "UPDATE desired_states SET state='SUPERSEDED',updated_by=?,updated_ts=? "
                "WHERE id=? AND state='PUBLISHED'",
                (actor, now, int(item["supersedes_id"])))
        self.conn.commit()
        self.manager.db.audit(actor, "desired_state_publish", f"DS#{dsid}",
                              f"name={item['name']};revision={item.get('revision',1)}")
        return self.get(dsid)

    def plan(self, dsid):
        item = self.get(dsid)
        if not item:
            raise DesiredStateError("unknown desired state")
        devices = self.manager.inv.resolve_target(item["target_kind"], item["target_value"], only_enabled=True)
        devices = sorted(devices, key=lambda d: d["name"])
        if not devices:
            raise DesiredStateError("desired-state target resolves to no enabled devices")
        plan = []
        for dev in devices:
            profile = self.manager.protocol_profiles.get(dev["name"])
            if not profile or not profile.get("enabled") or profile.get("protocol") not in {"netconf", "restconf", "gnmi"}:
                raise DesiredStateError(f"device {dev['name']} has no supported structured write profile")
            ops = []
            for idx, op in enumerate(item["document"]["operations"], 1):
                resolved = self.manager.vendor_models.resolve(
                    dev["name"], op["resource"], op["selectors"], op["value"],
                    protocol=profile["protocol"])
                ops.append({"index": idx, "resource": op["resource"],
                            "selectors": resolved["selectors"], "value": resolved["value"],
                            "pack": resolved["pack"], "pack_sha256": resolved["pack_sha256"],
                            "protocol": profile["protocol"]})
            plan.append({"device": dev["name"], "operations": ops})
        return {"desired_state_id": int(dsid), "name": item["name"],
                "revision": int(item.get("revision") or 1), "targets": plan}

    def evaluate(self, dsid, *, devices=None):
        plan = self.plan(dsid)
        allow = set(devices or ()) if devices is not None else None
        results = []
        for target in plan["targets"]:
            if allow is not None and target["device"] not in allow:
                continue
            dev, profile = self.manager._structured_profile_for(target["device"])
            for op in target["operations"]:
                try:
                    resolved = self.manager.vendor_models.resolve(
                        target["device"], op["resource"], op["selectors"], op["value"],
                        protocol=profile["protocol"])
                    actual, _ = self.manager.structured_collector.read_resource_value(dev, profile, resolved)
                    results.append({"device": target["device"], "index": op["index"],
                                    "resource": op["resource"], "desired": op["value"], "actual": actual,
                                    "state": "COMPLIANT" if actual == op["value"] else "DRIFTED"})
                except Exception as exc:
                    results.append({"device": target["device"], "index": op["index"],
                                    "resource": op["resource"], "state": "ERROR",
                                    "error": type(exc).__name__})
        counts = {state: sum(1 for x in results if x["state"] == state)
                  for state in ("COMPLIANT", "DRIFTED", "ERROR")}
        return {"desired_state_id": int(dsid), "results": results, "counts": counts}

    def apply(self, dsid, *, actor, approved=False, devices=None, source_kind="desired_state",
              source_ref="", approval_ref="", rollback_on_failure=True):
        item = self.get(dsid)
        if not item or item["state"] != "PUBLISHED":
            raise DesiredStateError("desired state must be PUBLISHED before apply")
        if not approved or not str(approval_ref or "").startswith("CR#"):
            raise DesiredStateError(
                "desired-state apply requires a durable approved change-request reference"
            )
        plan = self.plan(dsid)
        if devices is not None:
            allowed = set(devices)
            plan["targets"] = [x for x in plan["targets"] if x["device"] in allowed]
            if not plan["targets"]:
                raise DesiredStateError("requested apply target is outside the published desired-state target set")
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO desired_state_runs (desired_state_id,actor,mode,source_kind,source_ref,state,plan_json,created_ts) "
            "VALUES (?,?,?,?,?,'RUNNING',?,?)",
            (int(dsid), actor, "APPLY", source_kind, str(source_ref or "")[:256],
             json.dumps(plan, sort_keys=True), now),
        )
        self.conn.commit()
        run_id = cur.lastrowid
        stable_prefix = str(source_ref or f"DS#{dsid}/RUN#{run_id}")[:220]
        results = []
        failures = changed = noop = 0
        for target in plan["targets"]:
            device_transactions = []
            for op in target["operations"]:
                op_ref = f"{stable_prefix}/{target['device']}/OP#{op['index']}"
                try:
                    tx = self.manager.structured_changes.execute_resource(
                        device=target["device"],
                        resource=op["resource"],
                        selectors=op["selectors"],
                        value=op["value"],
                        actor=actor,
                        approved=True,
                        approval_ref=approval_ref,
                        source_kind=source_kind,
                        source_ref=op_ref,
                    )
                    if tx.get("changed"):
                        changed += 1
                        device_transactions.append(tx)
                    else:
                        noop += 1
                    results.append(
                        {
                            "device": target["device"],
                            "index": op["index"],
                            "resource": op["resource"],
                            "transaction_id": tx["id"],
                            "changed": bool(tx.get("changed")),
                            "ok": True,
                        }
                    )
                except Exception as exc:
                    failures += 1
                    failure = {
                        "device": target["device"],
                        "index": op["index"],
                        "resource": op["resource"],
                        "ok": False,
                        "error": type(exc).__name__,
                        "rollback": [],
                    }
                    if rollback_on_failure:
                        for prior in reversed(device_transactions):
                            try:
                                rolled = self.manager.structured_changes.rollback(
                                    prior["id"],
                                    actor=actor,
                                    approved=True,
                                    approval_ref=approval_ref + ":rollback_after_failure",
                                )
                                failure["rollback"].append(
                                    {
                                        "transaction_id": prior["id"],
                                        "rollback_transaction_id": rolled["id"],
                                        "ok": rolled.get("state") == "SUCCEEDED",
                                    }
                                )
                            except Exception as rollback_exc:
                                failure["rollback"].append(
                                    {
                                        "transaction_id": prior["id"],
                                        "ok": False,
                                        "error": type(rollback_exc).__name__,
                                    }
                                )
                    results.append(failure)
                    break
        state = "SUCCEEDED" if failures == 0 else "FAILED"
        final_plan = {**plan, "results": results}
        self.conn.execute(
            "UPDATE desired_state_runs SET state=?,plan_json=?,changed_count=?,noop_count=?,failure_count=?,finished_ts=? WHERE id=?",
            (state, json.dumps(final_plan, sort_keys=True), changed, noop, failures, time.time(), run_id))
        self.conn.commit()
        self.manager.db.audit(actor, "desired_state_apply", f"DS#{dsid}",
                              f"run={run_id};state={state};changed={changed};noop={noop};failures={failures}")
        return {"run_id": run_id, "state": state, "results": results,
                "changed_count": changed, "noop_count": noop, "failure_count": failures}
    def get_run(self, run_id):
        row = self.conn.execute(
            "SELECT * FROM desired_state_runs WHERE id=?", (int(run_id),)
        ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["plan"] = json.loads(out.pop("plan_json"))
        except (TypeError, json.JSONDecodeError):
            out["plan"] = {}
            out.pop("plan_json", None)
        return out

    def runs(self, dsid=None, limit=100):
        limit = min(5000, max(1, int(limit)))
        if dsid is None:
            rows = self.conn.execute(
                "SELECT id FROM desired_state_runs ORDER BY created_ts DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id FROM desired_state_runs WHERE desired_state_id=? "
                "ORDER BY created_ts DESC LIMIT ?",
                (int(dsid), limit),
            ).fetchall()
        return [self.get_run(row["id"]) for row in rows]

