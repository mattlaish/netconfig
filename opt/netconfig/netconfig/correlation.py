"""MC-7 deterministic incident correlation and hypothesis engine.

The engine consumes durable incident-linked evidence plus the explicit MC-6
service/dependency graph.  It is deterministic and bounded: time proximity alone
never creates a relationship, INFERRED/UNKNOWN/stale dependency edges are not
trusted by default, and no hypothesis is represented as confirmed causation.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import deque

RULE_SET_VERSION = "mc7-r55-v1"
_MAX_FACTS = 500
_MAX_HYPOTHESES = 25
_MAX_DEP_EDGES = 1000
_MAX_REL_DEPTH = 4
_MAX_REL_NODES = 250
_MAX_RULE_WINDOW_SECONDS = 1800
_MAX_TIMELINE_SCAN = 2000
_SEVERITY = {"DEBUG": 0, "INFO": 0, "NOTICE": 1, "WARNING": 2, "MINOR": 3, "MAJOR": 4, "ERROR": 4, "CRITICAL": 5}


def _clean(value, limit=1000):
    return str(value or "").replace("\x00", "").strip()[:limit]


def _decode(value, default):
    try:
        parsed = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class CorrelationEngine:
    """Bounded deterministic correlation over one incident evidence set."""

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn

    @staticmethod
    def _confidence_label(score):
        score = int(score)
        if score >= 75:
            return "HIGH"
        if score >= 55:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _fact_ref(fact, reason, weight):
        return {
            "source_type": fact["source_type"],
            "source_ref": fact["source_ref"],
            "source_ts": fact["source_ts"],
            "reason": _clean(reason, 500),
            "weight": int(weight),
        }

    def _timeline_facts(self, incident_key, *, start_ts=None, end_ts=None, with_meta=False):
        # Scan the bounded MC-5 timeline ceiling, then select supported facts and
        # apply an optional replay window before the per-run fact bound.  This
        # prevents late-arriving evidence from being silently excluded merely
        # because it was linked after newer evidence.
        timeline = self.manager.incidents.timeline(incident_key, _MAX_TIMELINE_SCAN)
        facts = []
        for item in timeline:
            source_type = _clean(item.get("source_type") or item.get("kind"), 64)
            if source_type not in {
                "sensor_transition", "operational_event", "operational_alert",
                "change_event", "analytics_insight", "external_event",
            }:
                continue
            source_ref = _clean(item.get("source_id"), 255)
            if not source_ref:
                continue
            source_ts = float(item.get("source_ts") or item.get("ts") or 0)
            if start_ts is not None and source_ts < float(start_ts):
                continue
            if end_ts is not None and source_ts > float(end_ts):
                continue
            aliases = set()
            for key in ("device", "entity_id", "resource", "source"):
                value = _clean(item.get(key), 255).lower()
                if value:
                    aliases.add(value)
            fact = {
                "source_type": source_type,
                "source_ref": source_ref,
                "source_ts": source_ts,
                "received_ts": float(item.get("received_ts") or 0),
                "summary": _clean(item.get("summary"), 1000),
                "severity": _clean(item.get("severity"), 32).upper(),
                "status": _clean(item.get("status"), 64).upper(),
                "domain": _clean(item.get("domain"), 64).upper(),
                "event_type": _clean(item.get("event_type"), 128).upper(),
                "sensor_type": _clean(item.get("sensor_type"), 128),
                "aliases": sorted(aliases),
                "signal_class": source_type,
                "degrading": False,
                "healthy": False,
                "details": {},
            }
            if source_type == "sensor_transition":
                new_status = _clean(item.get("status"), 32).upper()
                fact["degrading"] = new_status in {"WARNING", "CRITICAL"}
                fact["healthy"] = new_status == "OK"
                fact["signal_class"] = "sensor"
            elif source_type == "operational_event":
                fact["degrading"] = _SEVERITY.get(fact["severity"], 0) >= 2 and fact["status"] not in {"OK", "RECOVERED", "RESOLVED"}
                fact["healthy"] = fact["status"] in {"OK", "RECOVERED", "RESOLVED"} or fact["event_type"].endswith("RECOVERED")
                fact["signal_class"] = "event:" + (fact["domain"] or "SYSTEM")
            elif source_type == "operational_alert":
                fact["degrading"] = fact["status"] in {"OPEN", "ACKNOWLEDGED"} and _SEVERITY.get(fact["severity"], 0) >= 2
                fact["healthy"] = fact["status"] == "RESOLVED"
                fact["signal_class"] = "alert"
            elif source_type == "change_event":
                fact["signal_class"] = "change"
                row = self.conn.execute(
                    "SELECT metadata_json FROM change_events WHERE id=?",
                    (int(source_ref),),
                ).fetchone() if source_ref.isdigit() else None
                if row:
                    metadata = _decode(row["metadata_json"], {})
                    fact["details"] = {"metadata": metadata}
                    for key in ("device", "object_id", "entity_id"):
                        value = _clean(metadata.get(key), 255).lower()
                        if value:
                            fact["aliases"].append(value)
                    for key in ("affected_devices", "devices", "affected_entities"):
                        values = metadata.get(key)
                        if isinstance(values, list):
                            for value in values[:64]:
                                text = _clean(value, 255).lower()
                                if text:
                                    fact["aliases"].append(text)
                    fact["aliases"] = sorted(set(fact["aliases"]))
            elif source_type == "analytics_insight":
                fact["signal_class"] = "analytics"
                fact["degrading"] = _SEVERITY.get(fact["severity"], 0) >= 2 and fact["status"] in {"NEW", "ACKNOWLEDGED", ""}
                row = self.conn.execute(
                    "SELECT insight_type,evidence_json,affected_json FROM network_insights WHERE id=?",
                    (int(source_ref),),
                ).fetchone() if source_ref.isdigit() else None
                if row:
                    evidence = _decode(row["evidence_json"], {})
                    fact["details"] = {"insight_type": row["insight_type"], "evidence": evidence}
                    fact["event_type"] = str(row["insight_type"] or "").upper()
                    path = evidence.get("path") if isinstance(evidence, dict) else None
                    if isinstance(path, dict):
                        path_status = _clean(path.get("status"), 64).upper()
                        fact["details"]["path_status"] = path_status
                        if path_status == "REACHED_TERMINAL":
                            fact["healthy"] = True
                            fact["degrading"] = False
                        elif path_status:
                            fact["degrading"] = True
            elif source_type == "external_event":
                fact["signal_class"] = "external:" + (fact["domain"] or "EXTERNAL")
                fact["degrading"] = _SEVERITY.get(fact["severity"], 0) >= 2
                fact["healthy"] = fact["status"] in {"OK", "RECOVERED", "RESOLVED", "HEALTHY"}
            facts.append(fact)
        facts.sort(key=lambda x: (x["source_ts"], x["source_type"], x["source_ref"]))
        available = len(facts)
        selected = facts[:_MAX_FACTS]
        meta = {
            "supported_facts_available": available,
            "facts_truncated": available > _MAX_FACTS,
            "timeline_scan_limit": _MAX_TIMELINE_SCAN,
            "timeline_scan_saturated": len(timeline) >= _MAX_TIMELINE_SCAN,
        }
        return (selected, meta) if with_meta else selected

    def _dependency_context(self, now=None):
        now = time.time() if now is None else float(now)
        entities = self.manager.dependencies.entities(limit=_MAX_REL_NODES)
        alias_to_keys = {}
        for entity in entities:
            aliases = {entity["entity_key"].lower(), str(entity.get("name") or "").strip().lower()}
            meta = entity.get("metadata") or {}
            for key in ("device", "object_id", "hostname", "host", "ip", "address", "service", "application"):
                value = _clean(meta.get(key), 255).lower()
                if value:
                    aliases.add(value)
            for alias in aliases:
                if alias:
                    alias_to_keys.setdefault(alias, set()).add(entity["entity_key"])

        adjacency = {}
        edges = self.manager.dependencies.dependencies(limit=_MAX_DEP_EDGES, now=now)
        for edge in edges:
            state = edge.get("evidence_state")
            trusted = state == "CONFIGURED" or (state == "DISCOVERED" and bool(edge.get("fresh")))
            if not trusted or not edge.get("active"):
                continue
            src = edge["source_key"]
            dst = edge["target_key"]
            adjacency.setdefault(src, set()).add(dst)
            adjacency.setdefault(dst, set()).add(src)
        dependency_fingerprint = _sha({
            "aliases": {key: sorted(value) for key, value in sorted(alias_to_keys.items())},
            "adjacency": {key: sorted(value) for key, value in sorted(adjacency.items())},
        })
        return alias_to_keys, adjacency, len(edges) >= _MAX_DEP_EDGES, dependency_fingerprint

    @staticmethod
    def _service_keys(fact, alias_to_keys):
        out = set()
        for alias in fact.get("aliases") or ():
            out.update(alias_to_keys.get(alias, ()))
        return out

    def _related(self, left, right, alias_to_keys, adjacency):
        left_aliases = set(left.get("aliases") or ())
        right_aliases = set(right.get("aliases") or ())
        shared = sorted(left_aliases & right_aliases)
        if shared:
            return True, "same_entity:" + shared[0]
        left_keys = self._service_keys(left, alias_to_keys)
        right_keys = self._service_keys(right, alias_to_keys)
        if not left_keys or not right_keys:
            return False, ""
        overlap = sorted(left_keys & right_keys)
        if overlap:
            return True, "same_service_entity:" + overlap[0]
        queue = deque((key, 0) for key in sorted(left_keys))
        visited = set(left_keys)
        while queue and len(visited) <= _MAX_REL_NODES:
            node, depth = queue.popleft()
            if depth >= _MAX_REL_DEPTH:
                continue
            for nxt in sorted(adjacency.get(node, ())):
                if nxt in right_keys:
                    return True, f"dependency_path:{node}->{nxt}"
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append((nxt, depth + 1))
        return False, ""

    @staticmethod
    def _within(a, b, seconds):
        return abs(float(a["source_ts"]) - float(b["source_ts"])) <= float(seconds)

    @staticmethod
    def _score(supporting, contradicting):
        score = 30 + sum(int(x["weight"]) for x in supporting) - sum(int(x["weight"]) for x in contradicting)
        return max(5, min(95, int(score)))

    def _make_hypothesis(self, incident_id, rule_id, hypothesis_type, cluster_key, summary,
                         initiating, supporting, contradicting, affected):
        supporting = sorted(supporting, key=lambda x: (x["source_ts"], x["source_type"], x["source_ref"], x["reason"]))
        contradicting = sorted(contradicting, key=lambda x: (x["source_ts"], x["source_type"], x["source_ref"], x["reason"]))
        evidence_set = {
            "supporting": [{"source_type": x["source_type"], "source_ref": x["source_ref"]} for x in supporting],
            "contradicting": [{"source_type": x["source_type"], "source_ref": x["source_ref"]} for x in contradicting],
        }
        score = self._score(supporting, contradicting)
        key = _sha({"incident_id": incident_id, "rule_id": rule_id, "rule_version": RULE_SET_VERSION, "cluster": cluster_key})
        timestamps = [x["source_ts"] for x in supporting + contradicting]
        return {
            "hypothesis_key": key,
            "hypothesis_type": hypothesis_type,
            "summary": _clean(summary, 1000),
            "confidence": score,
            "confidence_label": self._confidence_label(score),
            "initiating_source_type": initiating["source_type"],
            "initiating_source_ref": initiating["source_ref"],
            "first_evidence_at": min(timestamps) if timestamps else initiating["source_ts"],
            "last_evidence_at": max(timestamps) if timestamps else initiating["source_ts"],
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "affected_entities": sorted(set(affected))[:64],
            "rule_id": rule_id,
            "rule_version": RULE_SET_VERSION,
            "evidence_fingerprint": _sha(evidence_set),
            "score_breakdown": {
                "base": 30,
                "support": sum(int(x["weight"]) for x in supporting),
                "contradiction": sum(int(x["weight"]) for x in contradicting),
                "formula": "clamp(5,95,base+support-contradiction)",
            },
        }

    def _evaluate(self, incident, facts, alias_to_keys, adjacency):
        hypotheses = []
        degradations = [f for f in facts if f["degrading"]]
        changes = [f for f in facts if f["source_type"] == "change_event"]
        healthy = [f for f in facts if f["healthy"]]

        # Rule 1: a preceding configuration change plus a related degradation.
        for change in changes:
            candidates = []
            for degrade in degradations:
                delta = degrade["source_ts"] - change["source_ts"]
                if delta < 0 or delta > _MAX_RULE_WINDOW_SECONDS:
                    continue
                related, relation = self._related(change, degrade, alias_to_keys, adjacency)
                if related:
                    candidates.append((degrade, relation, delta))
            if not candidates:
                continue
            candidates.sort(key=lambda x: (x[2], x[0]["source_ts"], x[0]["source_type"], x[0]["source_ref"]))
            initiating, relation, _ = candidates[0]
            supporting = [
                self._fact_ref(change, "configuration change preceded related degradation", 24),
                self._fact_ref(initiating, f"degradation is related by {relation}", 28),
            ]
            classes = {initiating["signal_class"]}
            for extra, extra_relation, _ in candidates[1:]:
                if extra["signal_class"] in classes:
                    continue
                supporting.append(self._fact_ref(extra, f"independent related degradation signal via {extra_relation}", 10))
                classes.add(extra["signal_class"])
                if len(classes) >= 3:
                    break
            contradicting = []
            for ok in healthy:
                if not self._within(ok, initiating, 900):
                    continue
                related, ok_relation = self._related(ok, initiating, alias_to_keys, adjacency)
                if related:
                    contradicting.append(self._fact_ref(ok, f"healthy/recovery evidence on related entity via {ok_relation}", 18))
            affected = list(change["aliases"]) + list(initiating["aliases"])
            hypotheses.append(self._make_hypothesis(
                incident["id"], "recent-config-change", "RECENT_CONFIGURATION_CHANGE",
                change["source_ref"],
                "Service degradation is consistent with a recent related configuration change.",
                initiating, supporting, contradicting, affected,
            ))
            if len(hypotheses) >= _MAX_HYPOTHESES:
                return hypotheses

        # Rule 2: explicit degraded L3/path evidence plus related degradation.
        network_bad = [f for f in degradations if f["source_type"] == "analytics_insight" and f["event_type"] in {"L3_PATH", "ROUTE_DEPENDENCY", "HEALTH"}]
        for net in network_bad:
            related_degrades = []
            for degrade in degradations:
                if degrade is net or not self._within(net, degrade, 900):
                    continue
                related, relation = self._related(net, degrade, alias_to_keys, adjacency)
                if related:
                    related_degrades.append((degrade, relation))
            if not related_degrades:
                continue
            related_degrades.sort(key=lambda x: (x[0]["source_ts"], x[0]["source_type"], x[0]["source_ref"]))
            initiating, relation = related_degrades[0]
            supporting = [
                self._fact_ref(net, "explicit network/path evidence is degraded", 28),
                self._fact_ref(initiating, f"related degradation observed via {relation}", 24),
            ]
            contradicting = []
            for ok in healthy:
                if not self._within(ok, net, 900):
                    continue
                related, ok_relation = self._related(ok, net, alias_to_keys, adjacency)
                if related:
                    contradicting.append(self._fact_ref(ok, f"healthy/recovery evidence conflicts via {ok_relation}", 20))
            affected = list(net["aliases"]) + list(initiating["aliases"])
            hypotheses.append(self._make_hypothesis(
                incident["id"], "network-path-degradation", "NETWORK_PATH_DEGRADATION",
                net["source_ref"],
                "Observed service degradation is consistent with degraded network/path evidence.",
                initiating, supporting, contradicting, affected,
            ))
            if len(hypotheses) >= _MAX_HYPOTHESES:
                return hypotheses

        # Rule 3: multiple independent degradation classes on the same/dependent entity.
        used = set()
        for idx, first in enumerate(degradations):
            cluster = [(first, "initiating")]
            classes = {first["signal_class"]}
            for other in degradations[idx + 1:]:
                if not self._within(first, other, 900):
                    continue
                related, relation = self._related(first, other, alias_to_keys, adjacency)
                if not related or other["signal_class"] in classes:
                    continue
                cluster.append((other, relation))
                classes.add(other["signal_class"])
            if len(cluster) < 2:
                continue
            refs = tuple(sorted((f["source_type"], f["source_ref"]) for f, _ in cluster))
            if refs in used:
                continue
            used.add(refs)
            supporting = [self._fact_ref(f, f"independent related degradation signal ({relation})", 16) for f, relation in cluster[:4]]
            contradicting = []
            for ok in healthy:
                if not self._within(ok, first, 900):
                    continue
                related, relation = self._related(ok, first, alias_to_keys, adjacency)
                if related:
                    contradicting.append(self._fact_ref(ok, f"healthy/recovery evidence conflicts via {relation}", 16))
            affected = []
            for f, _ in cluster:
                affected.extend(f["aliases"])
            hypotheses.append(self._make_hypothesis(
                incident["id"], "related-degradation-cluster", "RELATED_ENTITY_DEGRADATION",
                _sha(refs)[:24],
                "Evidence supports a related multi-signal degradation condition; causation is not established.",
                first, supporting, contradicting, affected,
            ))
            if len(hypotheses) >= _MAX_HYPOTHESES:
                break
        return hypotheses

    def _persist(self, incident, hypotheses):
        now = time.time()
        active_keys = set()
        for hypothesis in hypotheses:
            active_keys.add(hypothesis["hypothesis_key"])
            existing = self.conn.execute(
                "SELECT * FROM correlation_hypotheses WHERE incident_id=? AND hypothesis_key=?",
                (incident["id"], hypothesis["hypothesis_key"]),
            ).fetchone()
            payload = (
                hypothesis["hypothesis_type"], hypothesis["summary"], hypothesis["confidence"],
                hypothesis["confidence_label"], hypothesis["initiating_source_type"],
                hypothesis["initiating_source_ref"], hypothesis["first_evidence_at"],
                hypothesis["last_evidence_at"], _canonical(hypothesis["supporting_evidence"]),
                _canonical(hypothesis["contradicting_evidence"]),
                _canonical(hypothesis["affected_entities"]), hypothesis["rule_id"],
                hypothesis["rule_version"], hypothesis["evidence_fingerprint"],
                _canonical(hypothesis["score_breakdown"]),
            )
            if existing:
                current = (
                    existing["hypothesis_type"], existing["summary"], int(existing["confidence"]),
                    existing["confidence_label"], existing["initiating_source_type"],
                    existing["initiating_source_ref"], float(existing["first_evidence_at"]),
                    float(existing["last_evidence_at"]), existing["supporting_json"],
                    existing["contradicting_json"], existing["affected_entities_json"],
                    existing["rule_id"], existing["rule_version"], existing["evidence_fingerprint"],
                    existing["score_breakdown_json"],
                )
                if current != payload or not bool(existing["active"]):
                    self.conn.execute(
                        "UPDATE correlation_hypotheses SET hypothesis_type=?,summary=?,confidence=?,confidence_label=?,"
                        "initiating_source_type=?,initiating_source_ref=?,first_evidence_at=?,last_evidence_at=?,"
                        "supporting_json=?,contradicting_json=?,affected_entities_json=?,rule_id=?,rule_version=?,"
                        "evidence_fingerprint=?,score_breakdown_json=?,active=1,updated_at=? WHERE id=?",
                        payload + (now, int(existing["id"])),
                    )
            else:
                self.conn.execute(
                    "INSERT INTO correlation_hypotheses(tenant_id,incident_id,hypothesis_key,hypothesis_type,summary,"
                    "confidence,confidence_label,initiating_source_type,initiating_source_ref,first_evidence_at,last_evidence_at,"
                    "supporting_json,contradicting_json,affected_entities_json,rule_id,rule_version,evidence_fingerprint,"
                    "score_breakdown_json,active,created_at,updated_at) VALUES('default',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                    (incident["id"], hypothesis["hypothesis_key"]) + payload + (now, now),
                )
        existing_rows = self.conn.execute(
            "SELECT id,hypothesis_key FROM correlation_hypotheses WHERE incident_id=? AND rule_version=? AND active=1",
            (incident["id"], RULE_SET_VERSION),
        ).fetchall()
        for row in existing_rows:
            if row["hypothesis_key"] not in active_keys:
                self.conn.execute(
                    "UPDATE correlation_hypotheses SET active=0,updated_at=? WHERE id=?",
                    (now, int(row["id"])),
                )
        self.conn.commit()

    @staticmethod
    def _row(row):
        if not row:
            return None
        item = dict(row)
        item["active"] = bool(item.get("active"))
        item["confidence"] = int(item.get("confidence") or 0)
        item["supporting_evidence"] = _decode(item.pop("supporting_json", "[]"), [])
        item["contradicting_evidence"] = _decode(item.pop("contradicting_json", "[]"), [])
        item["affected_entities"] = _decode(item.pop("affected_entities_json", "[]"), [])
        item["score_breakdown"] = _decode(item.pop("score_breakdown_json", "{}"), {})
        return item

    def list(self, incident_ref, *, active_only=True, limit=100):
        incident = self.manager.incidents.get(incident_ref)
        if not incident:
            raise ValueError("incident not found")
        q = "SELECT * FROM correlation_hypotheses WHERE incident_id=?"
        args = [incident["id"]]
        if active_only:
            q += " AND active=1"
        q += " ORDER BY confidence DESC,hypothesis_type,hypothesis_key LIMIT ?"
        args.append(max(1, min(int(limit), 500)))
        return [self._row(r) for r in self.conn.execute(q, tuple(args)).fetchall()]

    def _execute(self, incident_ref, *, actor="system", persist=True, start_ts=None, end_ts=None,
                 mode="CORRELATE"):
        incident = self.manager.incidents.get(incident_ref)
        if not incident:
            raise ValueError("incident not found")
        hardening = self.manager.correlation_hardening
        with hardening.incident_guard(incident["id"]):
            facts, fact_meta = self._timeline_facts(
                incident["incident_key"], start_ts=start_ts, end_ts=end_ts, with_meta=True)
            alias_to_keys, adjacency, dependency_truncated, dependency_fingerprint = self._dependency_context()
            diagnostics = hardening.fact_diagnostics(facts)
            input_fingerprint = hardening.input_fingerprint(
                facts, dependency_fingerprint, mode=mode,
                range_start_ts=start_ts or 0, range_end_ts=end_ts or 0)
            run = hardening.begin_run(
                incident["id"], RULE_SET_VERSION, input_fingerprint, mode=mode,
                range_start_ts=start_ts or 0, range_end_ts=end_ts or 0)
            try:
                hypotheses = self._evaluate(incident, facts, alias_to_keys, adjacency)
                hypotheses.sort(key=lambda h: (-h["confidence"], h["hypothesis_type"], h["hypothesis_key"]))
                if persist:
                    self._persist(incident, hypotheses)
                    result_hypotheses = self.list(incident["id"], active_only=True, limit=_MAX_HYPOTHESES)
                else:
                    result_hypotheses = hypotheses[:_MAX_HYPOTHESES]
                result_fingerprint = hardening.result_fingerprint(result_hypotheses)
                run_row = hardening.complete_run(
                    run, result_fingerprint=result_fingerprint, facts_considered=len(facts),
                    hypotheses_count=len(result_hypotheses), diagnostics=diagnostics,
                    dependency_truncated=dependency_truncated,
                    facts_truncated=fact_meta["facts_truncated"] or fact_meta["timeline_scan_saturated"])
            except Exception as exc:
                hardening.fail_run(run, exc)
                raise
        action = "incident_correlate" if persist else "incident_correlation_replay_preview"
        self.db.audit(
            _clean(actor, 128), action, incident["incident_key"],
            f"rule_version={RULE_SET_VERSION};facts={len(facts)};hypotheses={len(result_hypotheses)};"
            f"dependency_truncated={int(dependency_truncated)};facts_truncated={int(fact_meta['facts_truncated'])};"
            f"mode={mode};run={run_row['run_key']}",
        )
        return {
            "incident": incident["incident_key"],
            "mode": mode,
            "rule_version": RULE_SET_VERSION,
            "facts_considered": len(facts),
            "facts_available": int(fact_meta["supported_facts_available"]),
            "hypotheses": result_hypotheses,
            "bounds": {
                "max_facts": _MAX_FACTS,
                "max_hypotheses": _MAX_HYPOTHESES,
                "max_dependency_edges": _MAX_DEP_EDGES,
                "max_relationship_depth": _MAX_REL_DEPTH,
                "max_relationship_nodes": _MAX_REL_NODES,
                "max_rule_time_window_seconds": _MAX_RULE_WINDOW_SECONDS,
                "max_timeline_scan": _MAX_TIMELINE_SCAN,
            },
            "diagnostics": diagnostics,
            "dependency_evidence_truncated": bool(dependency_truncated),
            "fact_evidence_truncated": bool(fact_meta["facts_truncated"] or fact_meta["timeline_scan_saturated"]),
            "input_fingerprint": input_fingerprint,
            "result_fingerprint": result_fingerprint,
            "run": {
                "run_key": run_row["run_key"],
                "state": run_row["state"],
                "replay_of_id": run_row.get("replay_of_id"),
                "duration_ms": run_row.get("duration_ms", 0),
                "deterministic_match": bool(run_row.get("deterministic_match")),
            },
            "causation_confirmed": False,
        }

    def correlate(self, incident_ref, *, actor="system"):
        return self._execute(incident_ref, actor=actor, persist=True, mode="CORRELATE")

    def preview(self, incident_ref, *, start_ts, end_ts, actor="system", mode="REPLAY_PREVIEW"):
        return self._execute(
            incident_ref, actor=actor, persist=False, start_ts=float(start_ts), end_ts=float(end_ts), mode=mode)

