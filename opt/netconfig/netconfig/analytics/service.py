"""Enterprise NI-6 analytics service.

This is the product boundary between operator/API surfaces and the NI-6 analyzers.
It persists evidence-backed insights and workflow state, but never performs a
network remediation. Any configuration action remains in the existing approved
Structured Changes / Desired State / Campaign workflow.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict

from .capacity import CapacityAnalyzer
from .failure_risk import FailureRiskAnalyzer
from .health import HealthAnalyzer

_STATES = {"NEW", "ACKNOWLEDGED", "RESOLVED", "EXPIRED"}
_TYPES = {"CAPACITY", "FAILURE_RISK", "DEPENDENCY_IMPACT", "HEALTH"}


def _clean(value, limit=512):
    return str(value or "").replace("\x00", "").strip()[:limit]


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class AnalyticsService:
    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self.capacity_analyzer = CapacityAnalyzer()
        self.failure_analyzer = FailureRiskAnalyzer()
        self.health_analyzer = HealthAnalyzer()

    @staticmethod
    def _decode(row):
        if not row:
            return None
        item = dict(row)
        for key, default in (("evidence_json", {}), ("affected_json", [])):
            try:
                item[key[:-5]] = json.loads(item.get(key) or _json(default))
            except (TypeError, json.JSONDecodeError):
                item[key[:-5]] = default
        item["workflow_routes"] = {
            "structured_change": "/operations?tab=structured",
            "desired_state": "/operations?tab=desired",
            "campaigns": "/operations?tab=campaigns",
        }
        return item

    def _persist(self, insight, *, evidence=None, affected=None, tenant_id="default", object_type="DEVICE", fingerprint_key=None):
        insight_type = _clean(insight.get("type"), 64).upper()
        if insight_type not in _TYPES:
            raise ValueError("unsupported insight type")
        object_id = _clean(insight.get("object_id"), 255)
        if not object_id:
            raise ValueError("insight object_id is required")
        severity = _clean(insight.get("severity") or "INFO", 32).upper()
        confidence = max(0.0, min(1.0, float(insight.get("confidence") or 0.0)))
        summary = _clean(insight.get("summary"), 1000)
        evidence = insight.get("evidence") if evidence is None else evidence
        affected = [] if affected is None else affected
        evidence_text = _json(evidence if evidence is not None else {})
        affected_text = _json(affected)
        # Fingerprint excludes volatile timestamps but includes durable evidence identity.
        fp_basis = _json({
            "tenant": _clean(tenant_id, 128), "type": insight_type,
            "object_type": _clean(object_type, 64).upper(), "object_id": object_id,
            "evidence_key": fingerprint_key if fingerprint_key is not None else evidence,
            "affected": affected if fingerprint_key is None else [],
        })
        fingerprint = hashlib.sha256(fp_basis.encode("utf-8")).hexdigest()
        now = time.time()
        row = self.conn.execute("SELECT * FROM network_insights WHERE fingerprint=?", (fingerprint,)).fetchone()
        if row:
            self.conn.execute(
                "UPDATE network_insights SET severity=?,confidence=?,summary=?,evidence_json=?,affected_json=?,"
                "last_seen_ts=?,occurrence_count=occurrence_count+1 WHERE id=?",
                (severity, confidence, summary, evidence_text, affected_text, now, int(row["id"])),
            )
            self.conn.commit()
            return self.get(int(row["id"]))
        cur = self.conn.execute(
            "INSERT INTO network_insights (tenant_id,insight_type,object_type,object_id,severity,confidence,summary,state,"
            "evidence_json,affected_json,fingerprint,first_seen_ts,last_seen_ts) VALUES (?,?,?,?,?,?,?,'NEW',?,?,?,?,?)",
            (_clean(tenant_id, 128) or "default", insight_type, _clean(object_type, 64).upper() or "DEVICE",
             object_id, severity, confidence, summary, evidence_text, affected_text, fingerprint, now, now),
        )
        self.conn.commit()
        return self.get(cur.lastrowid)

    def get(self, insight_id):
        return self._decode(self.conn.execute("SELECT * FROM network_insights WHERE id=?", (int(insight_id),)).fetchone())

    def list(self, *, state="", insight_type="", severity="", object_id="", search="", limit=200):
        q = "SELECT * FROM network_insights WHERE 1=1"
        args = []
        if state:
            state = _clean(state, 32).upper()
            if state not in _STATES:
                raise ValueError("invalid insight state")
            q += " AND state=?"; args.append(state)
        if insight_type:
            insight_type = _clean(insight_type, 64).upper()
            if insight_type not in _TYPES:
                raise ValueError("invalid insight type")
            q += " AND insight_type=?"; args.append(insight_type)
        if severity:
            q += " AND severity=?"; args.append(_clean(severity, 32).upper())
        if object_id:
            q += " AND object_id=?"; args.append(_clean(object_id, 255))
        if search:
            needle = "%" + _clean(search, 200).replace("%", "") + "%"
            q += " AND (object_id LIKE ? OR summary LIKE ? OR insight_type LIKE ?)"; args += [needle, needle, needle]
        q += " ORDER BY last_seen_ts DESC,id DESC LIMIT ?"; args.append(max(1, min(int(limit), 1000)))
        return [self._decode(r) for r in self.conn.execute(q, tuple(args)).fetchall()]

    def set_state(self, insight_id, state, actor, note=""):
        state = _clean(state, 32).upper()
        if state not in {"ACKNOWLEDGED", "RESOLVED", "EXPIRED"}:
            raise ValueError("insight state must be ACKNOWLEDGED, RESOLVED or EXPIRED")
        row = self.get(insight_id)
        if not row:
            raise ValueError("insight not found")
        now = time.time(); actor = _clean(actor, 128); note = _clean(note, 1000)
        fields = ["state=?", "note=?"]; args = [state, note]
        if state == "ACKNOWLEDGED":
            fields += ["acknowledged_by=?", "acknowledged_ts=?"]; args += [actor, now]
        elif state == "RESOLVED":
            fields += ["resolved_by=?", "resolved_ts=?"]; args += [actor, now]
        else:
            fields += ["expired_ts=?"]; args += [now]
        args.append(int(insight_id))
        self.conn.execute(f"UPDATE network_insights SET {','.join(fields)} WHERE id=?", tuple(args)); self.conn.commit()
        self.db.audit(actor, "analytics_insight_state", f"INSIGHT#{int(insight_id)}", f"state={state};note={note[:300]}")
        return self.get(insight_id)

    def expire_stale(self, actor="system", max_age_seconds=604800, now=None):
        now = time.time() if now is None else float(now)
        cutoff = now - max(60, int(max_age_seconds))
        rows = self.conn.execute("SELECT id FROM network_insights WHERE state IN ('NEW','ACKNOWLEDGED') AND last_seen_ts<?", (cutoff,)).fetchall()
        for row in rows:
            self.conn.execute("UPDATE network_insights SET state='EXPIRED',expired_ts=? WHERE id=?", (now, int(row["id"])))
        self.conn.commit()
        if rows:
            self.db.audit(actor, "analytics_insight_expire", "analytics", f"count={len(rows)};cutoff={cutoff}")
        return {"expired": len(rows), "cutoff": cutoff}

    def _job(self, job_type, object_id, actor, payload, fn):
        now = time.time()
        cur = self.conn.execute(
            "INSERT INTO analytics_jobs (tenant_id,job_type,object_id,actor,status,input_json,created_ts) VALUES ('default',?,?,?,?,?,?)",
            (_clean(job_type,64), _clean(object_id,255), _clean(actor,128), "RUNNING", _json(payload), now),
        ); self.conn.commit(); jid = cur.lastrowid
        try:
            result = fn()
            self.conn.execute("UPDATE analytics_jobs SET status='COMPLETED',result_json=?,finished_ts=? WHERE id=?", (_json(result), time.time(), jid)); self.conn.commit()
            return result
        except Exception as exc:
            self.conn.execute("UPDATE analytics_jobs SET status='FAILED',error=?,finished_ts=? WHERE id=?", (_clean(exc,500), time.time(), jid)); self.conn.commit()
            raise

    def jobs(self, limit=100):
        rows = self.conn.execute("SELECT * FROM analytics_jobs ORDER BY id DESC LIMIT ?", (max(1,min(int(limit),500)),)).fetchall()
        out=[]
        for row in rows:
            item=dict(row)
            for key in ("input_json", "result_json"):
                try:
                    item[key[:-5]] = json.loads(item.get(key) or "{}")
                except json.JSONDecodeError:
                    item[key[:-5]] = {}
            out.append(item)
        return out

    def analyze_capacity(self, object_id, actor="system"):
        object_id = _clean(object_id,255)
        def run():
            rows = self.conn.execute(
                "SELECT * FROM telemetry_points WHERE device=? AND value_type='number' AND numeric_value IS NOT NULL "
                "ORDER BY observed_ts DESC,id DESC LIMIT 200", (object_id,)).fetchall()
            if not rows:
                return {"object_id": object_id, "available": False, "reason": "no numeric telemetry points"}
            latest = dict(rows[0]); series=[dict(r) for r in rows if r["subscription_id"]==latest["subscription_id"] and r["value_path"]==latest["value_path"]]
            prior=[float(r["numeric_value"]) for r in series[1:51] if r["numeric_value"] is not None]
            baseline=sum(prior)/len(prior) if prior else float(latest["numeric_value"])
            trend="stable"
            if prior:
                trend="increasing" if float(latest["numeric_value"])>baseline else ("decreasing" if float(latest["numeric_value"])<baseline else "stable")
            obs=self.capacity_analyzer.analyze(object_id, latest["value_path"], float(latest["numeric_value"]), baseline, trend)
            raw=self.capacity_analyzer.to_insight(obs)
            evidence={"telemetry_point_id": int(latest["id"]), "subscription_id": int(latest["subscription_id"]), "value_path": latest["value_path"], "baseline_sample_count": len(prior), "observation": asdict(obs)}
            saved=self._persist(raw,evidence=evidence,fingerprint_key={"telemetry_point_id":int(latest["id"]),"subscription_id":int(latest["subscription_id"]),"value_path":latest["value_path"]})
            return {"object_id": object_id, "available": True, "insight": saved}
        return self._job("CAPACITY", object_id, actor, {"object_id":object_id}, run)

    def analyze_failure_risk(self, object_id, actor="system"):
        object_id = _clean(object_id,255)
        def run():
            signals=[]
            for ev in self.manager.events.list(250):
                if _clean(ev.get("device"), 255) != object_id:
                    continue
                et=_clean(ev.get("event_type"),64).upper(); sev=_clean(ev.get("severity") or "WARNING",16).upper()
                if "DOWN" in et or "FLAP" in et:
                    signals.append({"signal_type":"LINK_FLAPPING","source_id":f"event:{ev.get('id')}","severity":"CRITICAL" if sev in {"CRITICAL","ERROR","MAJOR"} else "WARNING","observed_at":str(ev.get("last_ts") or ev.get("first_ts") or ""),"metric":et})
                if "ERROR" in et or "DISCARD" in et or "DROP" in et:
                    signals.append({"signal_type":"INTERFACE_ERROR_SPIKE","source_id":f"event:{ev.get('id')}","severity":"WARNING","observed_at":str(ev.get("last_ts") or ""),"metric":et})
            for sub in self.manager.telemetry.list():
                if sub.get("device")==object_id and sub.get("last_error"):
                    signals.append({"signal_type":"TELEMETRY_DEGRADATION","source_id":f"telemetry_subscription:{sub['id']}","severity":"WARNING","observed_at":str(sub.get("updated_ts") or ""),"metric":"collector_health","value":sub.get("last_error")})
            obs=self.failure_analyzer.analyze(tenant_id="default",object_id=object_id,signals=signals[:50])
            raw=self.failure_analyzer.to_insight(obs)
            saved=self._persist(raw,evidence=raw["evidence"],fingerprint_key={"evidence_refs":list(obs.evidence_refs),"state":obs.state})
            return {"object_id":object_id,"signals":len(signals[:50]),"insight":saved}
        return self._job("FAILURE_RISK",object_id,actor,{"object_id":object_id},run)

    def simulate_impact(self, source_object, actor="system", max_depth=5):
        source_object=_clean(source_object,255); max_depth=max(1,min(int(max_depth),16))
        def run():
            impact=self.manager.downstream_impact(source_object,max_depth=max_depth)
            affected=[{"object_type":"DEVICE","object_id":x["device"],"depth":x["depth"],"via":x.get("via","")} for x in impact["devices"]]
            devices={source_object}|{x["device"] for x in impact["devices"]}
            for ep in self.manager.endpoint_inventory():
                att=ep.get("attachment") or {}
                if att.get("device") in devices and ep.get("status")=="ATTACHED":
                    affected.append({"object_type":"ENDPOINT","object_id":ep.get("mac"),"device":att.get("device"),"vlan_id":att.get("vlan_id"),"ifdescr":att.get("ifdescr")})
            evidence={"topology_scope":impact.get("scope"),"edges":impact.get("edges",[]),"root":source_object,"max_depth":max_depth}
            raw={"type":"DEPENDENCY_IMPACT","object_id":source_object,"severity":"WARNING" if affected else "INFO","confidence":0.95 if impact.get("edges") else 0.5,"summary":f"{len(affected)} potentially affected managed objects/endpoints"}
            saved=self._persist(raw,evidence=evidence,affected=affected,fingerprint_key={"edges":impact.get("edges",[]),"affected":affected,"max_depth":max_depth})
            return {"impact":impact,"affected":affected,"insight":saved}
        return self._job("DEPENDENCY_IMPACT",source_object,actor,{"source_object":source_object,"max_depth":max_depth},run)

    def analyze_health(self, object_id, actor="system"):
        object_id=_clean(object_id,255)
        def run():
            active=[x for x in self.list(object_id=object_id,limit=100) if x["state"] in {"NEW","ACKNOWLEDGED"}]
            capacity=100.0; stability=100.0; availability=100.0; errors=100.0; refs=[]
            for item in active:
                refs.append(f"insight:{item['id']}")
                sev=item["severity"].upper(); penalty=40 if sev in {"CRITICAL"} else (20 if sev in {"WARNING","DEGRADED"} else 5)
                if item["insight_type"] == "CAPACITY":
                    capacity = max(0, capacity - penalty)
                elif item["insight_type"] == "FAILURE_RISK":
                    errors = max(0, errors - penalty)
                    stability = max(0, stability - penalty / 2)
                elif item["insight_type"] == "DEPENDENCY_IMPACT":
                    availability = max(0, availability - penalty / 2)
            alerts=self.manager.alert_lifecycle.list(device=object_id,limit=100)
            open_alerts=[a for a in alerts if a.get("state")!="RESOLVED"]
            if open_alerts:
                availability=max(0,availability-min(60,len(open_alerts)*10)); refs += [f"alert:{a['id']}" for a in open_alerts[:20]]
            obs=self.health_analyzer.analyze("default",object_id,availability=availability,stability=stability,capacity=capacity,errors=errors,evidence_refs=refs)
            raw=self.health_analyzer.to_insight(obs); raw["severity"]={"UNKNOWN":"INFO","HEALTHY":"INFO","DEGRADED":"WARNING","CRITICAL":"CRITICAL"}[obs.overall_state]
            saved=self._persist(raw,evidence={"observation":asdict(obs),"source_insights":[x["id"] for x in active],"open_alerts":[a["id"] for a in open_alerts]},fingerprint_key={"state":obs.overall_state,"source_insights":[x["id"] for x in active],"open_alerts":[a["id"] for a in open_alerts]})
            return {"object_id":object_id,"insight":saved}
        return self._job("HEALTH",object_id,actor,{"object_id":object_id},run)

    def refresh(self, object_id, actor="system"):
        results={"capacity":self.analyze_capacity(object_id,actor),"failure_risk":self.analyze_failure_risk(object_id,actor)}
        results["health"]=self.analyze_health(object_id,actor)
        self.db.audit(actor,"analytics_refresh",object_id,"capacity,failure_risk,health")
        return results

    def dashboard(self):
        insights=self.list(limit=500)
        active=[x for x in insights if x["state"] in {"NEW","ACKNOWLEDGED"}]
        counts={"NEW":0,"ACKNOWLEDGED":0,"RESOLVED":0,"EXPIRED":0}
        types={k:0 for k in _TYPES}
        for x in insights:
            counts[x["state"]]=counts.get(x["state"],0)+1; types[x["insight_type"]]=types.get(x["insight_type"],0)+1
        return {"insights_total":len(insights),"active":len(active),"states":counts,"types":types,"health":[x for x in active if x["insight_type"]=="HEALTH"][:50],"recent":insights[:50]}
