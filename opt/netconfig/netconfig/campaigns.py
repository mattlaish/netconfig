"""NA-2 staged fleet campaign orchestration over published desired state.

Campaign execution is intentionally serialized per campaign. A stable
campaign/target source reference makes re-entry after process interruption
idempotent at the PH-4 transaction layer. Canary and wave execution are
bounded, approval-gated, and can optionally compensate successful targets in a
failed wave.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import contextmanager


class CampaignError(RuntimeError):
    pass


class CampaignService:
    def __init__(self, manager):
        self.manager = manager
        self.conn = manager.db.conn
        self._guard = threading.Lock()
        self._locks = {}

    @contextmanager
    def _campaign_lock(self, cid):
        key = str(int(cid))
        with self._guard:
            local = self._locks.setdefault(key, threading.RLock())
        if not local.acquire(timeout=10):
            raise CampaignError("timed out waiting for local campaign execution lock")
        lock_name = f"netconfig:campaign:{key}"
        advisory = False
        try:
            advisory = bool(self.manager.db.try_advisory_lock(lock_name))
            if not advisory:
                raise CampaignError("campaign is already being executed by another control-plane node")
            yield
        finally:
            if advisory:
                try:
                    self.manager.db.advisory_unlock(lock_name)
                except Exception:
                    pass
            local.release()

    def create(
        self,
        *,
        name,
        desired_state_id,
        wave_size=1,
        max_failures=0,
        canary_size=0,
        rollback_on_failure=False,
        actor="system",
    ):
        ds = self.manager.desired_state.get(desired_state_id)
        if not ds or ds["state"] != "PUBLISHED":
            raise CampaignError("campaign requires a PUBLISHED desired state")
        name = str(name or "").strip()
        if not name or len(name) > 128:
            raise CampaignError("campaign name is required and must be <=128 characters")
        wave_size = int(wave_size)
        max_failures = int(max_failures)
        canary_size = int(canary_size)
        if wave_size < 1 or wave_size > 500:
            raise CampaignError("campaign wave size must be 1..500")
        if max_failures < 0 or max_failures > wave_size:
            raise CampaignError("campaign max failures must be 0..wave size")
        if canary_size < 0 or canary_size > 100:
            raise CampaignError("campaign canary size must be 0..100")
        plan = self.manager.desired_state.plan(desired_state_id)
        targets = plan["targets"]
        if canary_size > len(targets):
            raise CampaignError("campaign canary size exceeds target count")
        now = time.time()
        try:
            cur = self.conn.execute(
                "INSERT INTO fleet_campaigns "
                "(name,desired_state_id,plan_json,canary_size,wave_size,max_failures,rollback_on_failure,state,"
                "created_by,created_ts) VALUES (?,?,?,?,?,?,?, 'DRAFT', ?,?)",
                (
                    name,
                    int(desired_state_id),
                    json.dumps(plan, sort_keys=True, separators=(",", ":")),
                    canary_size,
                    wave_size,
                    max_failures,
                    int(bool(rollback_on_failure)),
                    actor,
                    now,
                ),
            )
        except Exception as exc:
            raise CampaignError("campaign name already exists or campaign could not be stored") from exc
        cid = cur.lastrowid
        for index, target in enumerate(targets):
            if canary_size and index < canary_size:
                wave = 1
            elif canary_size:
                wave = 2 + ((index - canary_size) // wave_size)
            else:
                wave = 1 + (index // wave_size)
            self.conn.execute(
                "INSERT INTO fleet_campaign_targets "
                "(campaign_id,device,wave,ordinal,state,updated_ts) VALUES (?,?,?,?, 'PENDING', ?)",
                (cid, target["device"], wave, index, now),
            )
        self.conn.commit()
        self.manager.db.audit(
            actor,
            "campaign_create",
            f"CAMPAIGN#{cid}",
            (
                f"desired_state={desired_state_id};targets={len(targets)};wave_size={wave_size};"
                f"canary_size={canary_size};rollback_on_failure={int(bool(rollback_on_failure))}"
            ),
        )
        return self.get(cid)

    def get(self, cid):
        row = self.conn.execute(
            "SELECT * FROM fleet_campaigns WHERE id=?", (int(cid),)
        ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["rollback_on_failure"] = bool(out.get("rollback_on_failure"))
        try:
            out["plan"] = json.loads(out.pop("plan_json"))
        except (TypeError, json.JSONDecodeError):
            out["plan"] = {}
            out.pop("plan_json", None)
        out["targets"] = [
            dict(item)
            for item in self.conn.execute(
                "SELECT * FROM fleet_campaign_targets WHERE campaign_id=? ORDER BY ordinal",
                (int(cid),),
            ).fetchall()
        ]
        return out

    def list(self):
        rows = self.conn.execute(
            "SELECT * FROM fleet_campaigns ORDER BY created_ts DESC"
        ).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["rollback_on_failure"] = bool(item.get("rollback_on_failure"))
            try:
                plan = json.loads(item.pop("plan_json"))
            except (TypeError, json.JSONDecodeError):
                plan = {}
                item.pop("plan_json", None)
            item["plan_sha256"] = hashlib.sha256(
                json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            out.append(item)
        return out

    def start(self, cid, actor):
        self.manager.ha.require_active_node()
        item = self.get(cid)
        if not item or item["state"] != "DRAFT":
            raise CampaignError("only DRAFT campaign can start")
        now = time.time()
        self.conn.execute(
            "UPDATE fleet_campaigns SET state='RUNNING',current_wave=0,failure_count=0,started_ts=? "
            "WHERE id=?",
            (now, int(cid)),
        )
        self.conn.commit()
        self.manager.db.audit(actor, "campaign_start", f"CAMPAIGN#{cid}", item["name"])
        return self.get(cid)

    def pause(self, cid, actor):
        item = self.get(cid)
        if not item or item["state"] != "RUNNING":
            raise CampaignError("only RUNNING campaign can pause")
        self.conn.execute(
            "UPDATE fleet_campaigns SET state='PAUSED' WHERE id=?", (int(cid),)
        )
        self.conn.commit()
        self.manager.db.audit(actor, "campaign_pause", f"CAMPAIGN#{cid}", item["name"])
        return self.get(cid)

    def resume(self, cid, actor):
        self.manager.ha.require_active_node()
        item = self.get(cid)
        if not item or item["state"] != "PAUSED":
            raise CampaignError("only PAUSED campaign can resume")
        unresolved = [
            target for target in item["targets"]
            if target["state"] in {"FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"}
        ]
        if unresolved:
            states = ",".join(sorted({target["state"] for target in unresolved}))
            raise CampaignError(
                "campaign has unresolved failed/rolled-back targets; explicitly retry or abort "
                f"before resume (states={states})"
            )
        self.conn.execute(
            "UPDATE fleet_campaigns SET state='RUNNING' WHERE id=?", (int(cid),)
        )
        self.conn.commit()
        self.manager.db.audit(actor, "campaign_resume", f"CAMPAIGN#{cid}", item["name"])
        return self.get(cid)

    def retry_failed(self, cid, actor, wave=None):
        """Reset a failed wave for an explicit operator-requested retry.

        A failed target and any successful target that was compensatingly rolled
        back are returned to PENDING together.  Attempts are deliberately *not*
        decremented here: the next execution therefore receives a new attempt
        identity.  ROLLBACK_FAILED is fail-closed because remote state is not
        known to have returned to its pre-wave value.
        """
        self.manager.ha.require_active_node()
        item = self.get(cid)
        if not item or item["state"] != "PAUSED":
            raise CampaignError("only PAUSED campaign can retry failed targets")

        if wave is None:
            retryable_waves = sorted({
                int(target["wave"])
                for target in item["targets"]
                if target["state"] in {"FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"}
            })
            if not retryable_waves:
                raise CampaignError("campaign has no failed or rolled-back targets to retry")
            if len(retryable_waves) != 1:
                raise CampaignError("campaign has unresolved targets in multiple waves; specify wave")
            wave = retryable_waves[0]
        else:
            wave = int(wave)
            if wave < 1:
                raise CampaignError("campaign retry wave must be >=1")

        selected = [
            target for target in item["targets"]
            if int(target["wave"]) == wave
            and target["state"] in {"FAILED", "ROLLED_BACK", "ROLLBACK_FAILED"}
        ]
        if not selected:
            raise CampaignError("selected wave has no failed or rolled-back targets to retry")
        unsafe = [target for target in selected if target["state"] == "ROLLBACK_FAILED"]
        if unsafe:
            raise CampaignError(
                "selected wave contains ROLLBACK_FAILED targets with uncertain remote state; "
                "recover those targets before retry"
            )

        now = time.time()
        retry_ids = [int(target["id"]) for target in selected]
        placeholders = ",".join("?" for _ in retry_ids)
        self.conn.execute(
            "UPDATE fleet_campaign_targets SET state='PENDING',last_error='',"
            "transaction_ids_json='[]',last_run_id=NULL,updated_ts=? "
            f"WHERE campaign_id=? AND id IN ({placeholders}) "
            "AND state IN ('FAILED','ROLLED_BACK')",
            (now, int(cid), *retry_ids),
        )
        self.conn.commit()
        self.manager.db.audit(
            actor,
            "campaign_retry",
            f"CAMPAIGN#{cid}",
            f"wave={wave};targets={len(retry_ids)}",
        )
        return self.get(cid)

    def abort(self, cid, actor):
        item = self.get(cid)
        if not item or item["state"] not in {"RUNNING", "PAUSED", "DRAFT"}:
            raise CampaignError("campaign cannot be aborted from current state")
        now = time.time()
        self.conn.execute(
            "UPDATE fleet_campaign_targets SET state='SKIPPED',last_error='campaign aborted',updated_ts=? "
            "WHERE campaign_id=? AND state IN ('PENDING','RUNNING')",
            (now, int(cid)),
        )
        self.conn.execute(
            "UPDATE fleet_campaigns SET state='ABORTED',finished_ts=? WHERE id=?",
            (now, int(cid)),
        )
        self.conn.commit()
        self.manager.db.audit(actor, "campaign_abort", f"CAMPAIGN#{cid}", item["name"])
        return self.get(cid)

    def _recover_interrupted_targets(self, cid):
        # Per-campaign lock guarantees there is no valid concurrent executor here.
        # A RUNNING row therefore represents a prior interrupted process. Stable
        # source refs at desired-state apply make the retry idempotent.
        now = time.time()
        self.conn.execute(
            "UPDATE fleet_campaign_targets SET state='PENDING',"
            "attempts=CASE WHEN attempts>0 THEN attempts-1 ELSE 0 END,"
            "last_error='interrupted; same attempt will be retried idempotently',"
            "updated_ts=? WHERE campaign_id=? AND state='RUNNING'",
            (now, int(cid)),
        )
        self.conn.commit()

    def _rollback_wave(self, targets, *, actor, cid, wave, approval_ref=""):
        results = []
        for target in reversed(targets):
            if target.get("state") != "SUCCEEDED":
                continue
            try:
                txids = json.loads(target.get("transaction_ids_json") or "[]")
            except json.JSONDecodeError:
                txids = []
            target_ok = True
            rollback_ids = []
            for txid in reversed(txids):
                try:
                    rolled = self.manager.structured_changes.rollback(
                        int(txid),
                        actor=actor,
                        approved=True,
                        approval_ref=(approval_ref or f"campaign:{cid}:wave:{wave}") + ":rollback",
                    )
                    rollback_ids.append(rolled["id"])
                except Exception:
                    target_ok = False
            state = "ROLLED_BACK" if target_ok else "ROLLBACK_FAILED"
            self.conn.execute(
                "UPDATE fleet_campaign_targets SET state=?,last_error=?,updated_ts=? WHERE id=?",
                (
                    state,
                    "" if target_ok else "one or more compensating rollbacks failed",
                    time.time(),
                    int(target["id"]),
                ),
            )
            results.append(
                {
                    "target_id": target["id"],
                    "device": target["device"],
                    "state": state,
                    "rollback_transaction_ids": rollback_ids,
                }
            )
        self.conn.commit()
        return results

    def execute_next_wave(self, cid, *, actor, approved=False, approval_ref=""):
        self.manager.ha.require_active_node()
        if not approved or not str(approval_ref or "").startswith("CR#"):
            raise CampaignError(
                "campaign wave execution requires a durable approved change-request reference"
            )
        with self._campaign_lock(cid):
            self._recover_interrupted_targets(cid)
            item = self.get(cid)
            if not item or item["state"] != "RUNNING":
                raise CampaignError("campaign must be RUNNING")
            pending = [target for target in item["targets"] if target["state"] == "PENDING"]
            if not pending:
                now = time.time()
                self.conn.execute(
                    "UPDATE fleet_campaigns SET state='SUCCEEDED',finished_ts=? WHERE id=?",
                    (now, int(cid)),
                )
                self.conn.commit()
                return self.get(cid)

            wave = min(target["wave"] for target in pending)
            targets = [target for target in pending if target["wave"] == wave]
            failures = 0
            completed_targets = []
            for target in targets:
                now = time.time()
                attempt = int(target.get("attempts") or 0) + 1
                self.conn.execute(
                    "UPDATE fleet_campaign_targets SET state='RUNNING',attempts=?,last_error='',"
                    "updated_ts=? WHERE id=? AND state='PENDING'",
                    (attempt, now, int(target["id"])),
                )
                self.conn.commit()
                try:
                    result = self.manager.desired_state.apply(
                        item["desired_state_id"],
                        actor=actor,
                        approved=True,
                        devices=[target["device"]],
                        source_kind="campaign",
                        source_ref=f"CAMPAIGN#{cid}/TARGET#{target['id']}/ATTEMPT#{attempt}",
                        approval_ref=approval_ref or f"campaign:{cid}:wave:{wave}",
                        rollback_on_failure=True,
                    )
                    txids = [
                        result_item["transaction_id"]
                        for result_item in result["results"]
                        if result_item.get("transaction_id") and result_item.get("changed")
                    ]
                    state = "SUCCEEDED" if result["state"] == "SUCCEEDED" else "FAILED"
                    if state == "FAILED":
                        failures += 1
                    self.conn.execute(
                        "UPDATE fleet_campaign_targets SET state=?,last_error=?,transaction_ids_json=?,"
                        "last_run_id=?,updated_ts=? WHERE id=?",
                        (
                            state,
                            "" if state == "SUCCEEDED" else "desired-state apply failed",
                            json.dumps(txids),
                            result.get("run_id"),
                            time.time(),
                            int(target["id"]),
                        ),
                    )
                except Exception as exc:
                    failures += 1
                    self.conn.execute(
                        "UPDATE fleet_campaign_targets SET state='FAILED',last_error=?,updated_ts=? WHERE id=?",
                        (type(exc).__name__, time.time(), int(target["id"])),
                    )
                self.conn.commit()
                refreshed = self.conn.execute(
                    "SELECT * FROM fleet_campaign_targets WHERE id=?", (int(target["id"]),)
                ).fetchone()
                completed_targets.append(dict(refreshed))

            rollback_results = []
            threshold_exceeded = failures > int(item["max_failures"])
            if threshold_exceeded and item.get("rollback_on_failure"):
                rollback_results = self._rollback_wave(
                    completed_targets, actor=actor, cid=int(cid), wave=int(wave),
                    approval_ref=approval_ref,
                )

            current_failures = int(item.get("failure_count") or 0) + failures
            if threshold_exceeded:
                new_state = "PAUSED"
            else:
                remaining = self.conn.execute(
                    "SELECT COUNT(*) AS n FROM fleet_campaign_targets "
                    "WHERE campaign_id=? AND state='PENDING'",
                    (int(cid),),
                ).fetchone()["n"]
                new_state = "RUNNING" if remaining else "SUCCEEDED"
            finished = time.time() if new_state == "SUCCEEDED" else 0
            self.conn.execute(
                "UPDATE fleet_campaigns SET state=?,current_wave=?,failure_count=?,finished_ts=? WHERE id=?",
                (new_state, int(wave), current_failures, finished, int(cid)),
            )
            self.conn.commit()
            self.manager.db.audit(
                actor,
                "campaign_wave",
                f"CAMPAIGN#{cid}",
                (
                    f"wave={wave};failures={failures};failure_count={current_failures};"
                    f"rollback_targets={len(rollback_results)};state={new_state}"
                ),
            )
            out = self.get(cid)
            out["last_wave_rollback"] = rollback_results
            return out
