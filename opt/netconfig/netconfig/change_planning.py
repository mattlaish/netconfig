"""MC-11 topology-aware change planning.

The planner consumes persisted topology, endpoint, L3/VRF, dependency and
policy evidence.  It can identify evidence-backed configuration gaps and emit
Structured Change *proposals*, but it has no network execution authority.
Candidate-state what-if analysis is in-memory/read-only with respect to network
and evidence tables.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict


EVIDENCE_KINDS = ("ACL", "FIREWALL", "NAT", "PBR", "ROUTING_POLICY")
DIRECTIONS = ("FORWARD", "RETURN", "BOTH")
EVIDENCE_STATES = ("ALLOW", "DENY", "MISSING", "PRESENT", "UNKNOWN", "TRANSLATE", "STEER")
_GAP_STATES = {"DENY", "MISSING"}
_GOOD_STATES = {"ALLOW", "PRESENT", "TRANSLATE", "STEER"}
_RESOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


def _clean(value, limit=512):
    return str(value or "").replace("\x00", "").strip()[:limit]


def _json(value, limit=65536):
    raw = json.dumps(value if value is not None else {}, sort_keys=True,
                     separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) > limit:
        raise ValueError(f"JSON payload exceeds {limit} bytes")
    return raw


def _decode(value, default):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(default)) else default
    except (TypeError, json.JSONDecodeError):
        return default


def _sha(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class TopologyChangePlanningService:
    """Evidence-backed MC-11 planning service with no execution surface."""

    schema_revision = "mc11-topology-change-planning-1"

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self._plan_lock_guard = threading.Lock()
        self._plan_locks = {}

    @contextmanager
    def _persistence_lock(self, plan_key):
        """Serialize one deterministic plan identity locally and across PostgreSQL nodes."""
        with self._plan_lock_guard:
            local = self._plan_locks.setdefault(str(plan_key), threading.RLock())
        if not local.acquire(timeout=5.0):
            raise RuntimeError("change planning persistence is busy")
        lock_name = f"r62:change-plan:{plan_key}"
        advisory = False
        try:
            if getattr(self.db, "dialect", "sqlite") == "postgres":
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    if self.db.try_advisory_lock(lock_name):
                        advisory = True
                        break
                    time.sleep(0.05)
                if not advisory:
                    raise RuntimeError("change planning PostgreSQL advisory lock is busy")
            yield
        finally:
            if advisory:
                try:
                    self.db.advisory_unlock(lock_name)
                except Exception:
                    pass
            local.release()

    @staticmethod
    def _normalize_proposal(value, *, expected_device=""):
        if value in (None, {}, ""):
            return None
        if not isinstance(value, dict):
            raise ValueError("proposal must be an object")
        allowed = {"kind", "device", "resource", "selectors", "value"}
        if set(value) - allowed:
            raise ValueError("proposal contains unsupported fields")
        kind = _clean(value.get("kind") or "structured_change", 64).lower()
        if kind != "structured_change":
            raise ValueError("proposal kind must be structured_change")
        device = _clean(value.get("device") or expected_device, 255)
        if not device or (expected_device and device != expected_device):
            raise ValueError("proposal device must match evidence device")
        resource = _clean(value.get("resource"), 128)
        if not resource or not _RESOURCE_RE.fullmatch(resource):
            raise ValueError("proposal resource is invalid")
        selectors = value.get("selectors") or {}
        if not isinstance(selectors, dict) or len(selectors) > 8:
            raise ValueError("proposal selectors must be an object with at most 8 entries")
        normalized_selectors = {}
        for key, item in selectors.items():
            k = _clean(key, 128)
            if not k or not _RESOURCE_RE.fullmatch(k):
                raise ValueError("proposal selector key is invalid")
            if isinstance(item, (dict, list, tuple, set)):
                raise ValueError("proposal selector values must be scalar")
            normalized_selectors[k] = item
        return {
            "kind": "structured_change",
            "device": device,
            "resource": resource,
            "selectors": normalized_selectors,
            "value": value.get("value"),
        }

    @classmethod
    def _row_evidence(cls, row):
        if not row:
            return None
        item = dict(row)
        item["metadata"] = _decode(item.pop("metadata_json", "{}"), {})
        item["proposal"] = cls._normalize_proposal(
            item["metadata"].get("proposal"), expected_device=item.get("device", ""))
        now = time.time()
        observed = float(item.get("observed_ts") or 0)
        max_age = int(item.get("max_age_seconds") or 0)
        if max_age <= 0:
            item["freshness"] = "CONFIGURED"
            item["fresh"] = True
        else:
            age = max(0.0, now - observed) if observed else None
            item["age_seconds"] = age
            item["fresh"] = bool(observed and age <= max_age)
            item["freshness"] = "FRESH" if item["fresh"] else "STALE"
        return item

    @staticmethod
    def _row_plan(row):
        if not row:
            return None
        item = dict(row)
        item["input"] = _decode(item.pop("input_json", "{}"), {})
        item["result"] = _decode(item.pop("result_json", "{}"), {})
        return item

    def observe_policy_evidence(
        self, *, device, evidence_kind, direction="BOTH", vrf="default",
        source_selector="*", destination_selector="*", service="any", state="UNKNOWN",
        evidence_ref, metadata=None, observed_ts=None, max_age_seconds=0, actor="system",
    ):
        device = _clean(device, 255)
        if not device or not self.manager.inv.get(device):
            raise ValueError("policy evidence device must be a managed inventory object")
        evidence_kind = _clean(evidence_kind, 64).upper()
        direction = _clean(direction, 16).upper()
        state = _clean(state, 32).upper()
        if evidence_kind not in EVIDENCE_KINDS:
            raise ValueError("unsupported policy evidence kind")
        if direction not in DIRECTIONS:
            raise ValueError("direction must be FORWARD, RETURN or BOTH")
        if state not in EVIDENCE_STATES:
            raise ValueError("unsupported policy evidence state")
        vrf = _clean(vrf or "default", 128) or "default"
        source_selector = _clean(source_selector or "*", 255) or "*"
        destination_selector = _clean(destination_selector or "*", 255) or "*"
        service = _clean(service or "any", 255) or "any"
        evidence_ref = _clean(evidence_ref, 512)
        if not evidence_ref:
            raise ValueError("evidence_ref is required")
        metadata = dict(metadata or {})
        proposal = self._normalize_proposal(metadata.get("proposal"), expected_device=device)
        if proposal is not None:
            metadata["proposal"] = proposal
        observed = time.time() if observed_ts is None else float(observed_ts)
        max_age = int(max_age_seconds or 0)
        if max_age < 0 or max_age > 2592000:
            raise ValueError("max_age_seconds must be between 0 and 2592000")
        fp_data = {
            "device": device, "kind": evidence_kind, "direction": direction, "vrf": vrf,
            "source": source_selector, "destination": destination_selector,
            "service": service, "state": state, "evidence_ref": evidence_ref,
        }
        fingerprint = _sha(fp_data)
        now = time.time()
        row = self.conn.execute(
            "SELECT id FROM change_planning_evidence WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        if row:
            eid = int(row["id"])
            self.conn.execute(
                "UPDATE change_planning_evidence SET metadata_json=?,observed_ts=?,max_age_seconds=?,"
                "updated_ts=? WHERE id=?",
                (_json(metadata), observed, max_age, now, eid),
            )
            action = "change_planning_evidence_refresh"
        else:
            cur = self.conn.execute(
                "INSERT INTO change_planning_evidence "
                "(tenant_id,device,evidence_kind,direction,vrf,source_selector,destination_selector,service,state,"
                "evidence_ref,metadata_json,fingerprint,observed_ts,max_age_seconds,created_by,created_ts,updated_ts) "
                "VALUES ('default',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (device, evidence_kind, direction, vrf, source_selector, destination_selector,
                 service, state, evidence_ref, _json(metadata), fingerprint, observed,
                 max_age, _clean(actor, 128), now, now),
            )
            eid = int(cur.lastrowid)
            action = "change_planning_evidence_create"
        self.conn.commit()
        self.db.audit(actor, action, f"PLANNING_EVIDENCE#{eid}",
                      f"device={device};kind={evidence_kind};direction={direction};state={state}")
        return self.get_evidence(eid)

    def get_evidence(self, evidence_id):
        row = self.conn.execute(
            "SELECT * FROM change_planning_evidence WHERE id=?", (int(evidence_id),)
        ).fetchone()
        return self._row_evidence(row)

    def evidence(self, *, device="", direction="", vrf="", limit=1000):
        q = "SELECT * FROM change_planning_evidence WHERE tenant_id='default'"
        args = []
        if device:
            q += " AND device=?"; args.append(_clean(device, 255))
        if direction:
            d = _clean(direction, 16).upper()
            if d not in DIRECTIONS:
                raise ValueError("invalid direction")
            q += " AND direction IN (?, 'BOTH')"; args.append(d)
        if vrf:
            q += " AND vrf=?"; args.append(_clean(vrf, 128))
        q += " ORDER BY device,evidence_kind,id LIMIT ?"
        args.append(max(1, min(int(limit), 2000)))
        return [self._row_evidence(r) for r in self.conn.execute(q, tuple(args)).fetchall()]

    def _resolve_selector(self, selector):
        selector = _clean(selector, 255)
        if not selector:
            return {"selector": selector, "status": "UNKNOWN", "reason": "selector is empty"}
        if self.manager.inv.get(selector):
            return {
                "selector": selector, "status": "RESOLVED", "kind": "DEVICE", "device": selector,
                "evidence_refs": [f"inventory:{selector}"], "attachment": None,
            }
        rows = self.manager.endpoint_inventory(query=selector)
        exact = []
        needle = selector.lower()
        for row in rows:
            values = {str(row.get("mac") or "").lower()}
            values |= {str(x).lower() for x in (row.get("ipv4") or [])}
            values |= {str(x).lower() for x in (row.get("ipv6") or [])}
            if needle in values:
                exact.append(row)
        candidates = exact or rows
        attached = [r for r in candidates if r.get("attachment") and r.get("status") == "ATTACHED"]
        devices = sorted({str(r["attachment"].get("device") or "") for r in attached if r["attachment"].get("device")})
        if len(attached) == 1 and len(devices) == 1:
            row = attached[0]
            attachment = dict(row.get("attachment") or {})
            refs = [f"endpoint:{row.get('mac') or selector}"]
            for item in (row.get("evidence_chain") or {}).get("ip_neighbors", []):
                refs.append("ip-neighbor:" + ":".join([
                    str(item.get("device") or ""), str(item.get("ip") or ""),
                    str(item.get("ifindex") or ""),
                ]))
            for item in (row.get("evidence_chain") or {}).get("fdb_candidates", []):
                refs.append("fdb:" + ":".join([
                    str(item.get("device") or ""), str(item.get("ifindex") or ""),
                    str(item.get("vlan_id") or ""),
                ]))
            return {
                "selector": selector, "status": "RESOLVED", "kind": "ENDPOINT",
                "device": devices[0], "attachment": attachment,
                "endpoint": {k: row.get(k) for k in ("mac", "ipv4", "ipv6", "confidence")},
                "evidence_refs": sorted(set(refs)),
            }
        if len(devices) > 1 or len(attached) > 1:
            return {
                "selector": selector, "status": "AMBIGUOUS", "kind": "ENDPOINT",
                "devices": devices, "candidate_count": len(attached),
                "reason": "endpoint attachment is not unique",
            }
        return {
            "selector": selector, "status": "UNKNOWN", "kind": "ENDPOINT",
            "candidate_count": len(candidates), "reason": "no unique attached endpoint evidence",
        }

    @staticmethod
    def _host_prefix(selector):
        try:
            ip = ipaddress.ip_address(str(selector))
        except ValueError:
            return ""
        return f"{ip}/{32 if ip.version == 4 else 128}"

    def _simulate_path(self, source_device, vrf, prefix, max_hops):
        if not source_device or not prefix:
            return {
                "source_device": source_device, "vrf": vrf, "destination_prefix": prefix,
                "status": "UNKNOWN", "hops": [], "route_ids": [],
                "stop_reason": "source device or destination prefix is unresolved", "confidence": 0.0,
            }
        rows = self.manager.analytics.l3_routes(vrf=vrf, destination_prefix=prefix, limit=1000)
        managed = [d["name"] for d in self.manager.inv.all()]
        obs = self.manager.analytics.l3_analyzer.simulate(
            source_device, vrf, prefix, rows, managed, max_hops=max_hops)
        return asdict(obs)

    def _service_context(self, path_devices):
        devices = set(path_devices)
        entities = []
        keys = set()
        for entity in self.manager.dependencies.entities(limit=1000):
            metadata = entity.get("metadata") or {}
            meta_devices = metadata.get("devices") if isinstance(metadata.get("devices"), list) else []
            matches = (
                entity.get("entity_key") in devices or entity.get("name") in devices or
                metadata.get("device") in devices or bool(devices.intersection({str(x) for x in meta_devices}))
            )
            if matches:
                entities.append(entity)
                keys.add(entity["entity_key"])
        edges = []
        if keys:
            for edge in self.manager.dependencies.dependencies(limit=2000):
                if edge.get("source_key") in keys or edge.get("target_key") in keys:
                    edges.append(edge)
        return {"entities": entities[:250], "dependencies": edges[:1000], "truncated": len(edges) > 1000}

    @staticmethod
    def _selector_match(pattern, actual):
        pattern = str(pattern or "*")
        actual = str(actual or "")
        return pattern in {"*", "any", "ANY"} or pattern == actual

    def _relevant_policy(self, *, direction, vrf, source, destination, service, path_devices):
        path_pos = {device: idx for idx, device in enumerate(path_devices)}
        out = []
        for item in self.evidence(direction=direction, vrf=vrf, limit=2000):
            if item.get("device") not in path_pos:
                continue
            if not self._selector_match(item.get("source_selector"), source):
                continue
            if not self._selector_match(item.get("destination_selector"), destination):
                continue
            if not self._selector_match(item.get("service"), service):
                continue
            row = dict(item)
            row["path_index"] = path_pos[row["device"]]
            if not row.get("fresh"):
                row["effective_state"] = "UNKNOWN"
            else:
                row["effective_state"] = row.get("state")
            out.append(row)
        return sorted(out, key=lambda x: (int(x.get("path_index") or 0), x.get("evidence_kind", ""), int(x.get("id") or 0)))

    @staticmethod
    def _proposal_fingerprint(proposal):
        return _sha(proposal) if proposal else ""

    def _gaps(self, policy_rows, direction):
        gaps = []
        unknown = []
        for row in policy_rows:
            state = str(row.get("effective_state") or "UNKNOWN").upper()
            base = {
                "direction": direction, "device": row.get("device"),
                "path_index": row.get("path_index"), "evidence_kind": row.get("evidence_kind"),
                "state": state, "evidence_ref": row.get("evidence_ref"),
                "why_here": {
                    "reason": "persisted policy evidence applies at this path device",
                    "device": row.get("device"), "path_index": row.get("path_index"),
                    "vrf": row.get("vrf"), "source_selector": row.get("source_selector"),
                    "destination_selector": row.get("destination_selector"), "service": row.get("service"),
                    "evidence_ref": row.get("evidence_ref"),
                },
                "proposed_change": row.get("proposal"),
            }
            if state in _GAP_STATES:
                base["gap_status"] = "CONFIGURATION_GAP"
                gaps.append(base)
            elif state not in _GOOD_STATES:
                base["gap_status"] = "UNKNOWN"
                unknown.append(base)
        return gaps, unknown

    def plan(self, *, source, destination, vrf="default", destination_prefix="", source_prefix="",
             service="any", actor="system", max_hops=16, incident_ref=""):
        source = _clean(source, 255)
        destination = _clean(destination, 255)
        vrf = _clean(vrf or "default", 128) or "default"
        service = _clean(service or "any", 255) or "any"
        destination_prefix = _clean(destination_prefix, 255)
        source_prefix = _clean(source_prefix, 255) or self._host_prefix(source)
        max_hops = max(1, min(int(max_hops), 64))
        incident_ref = _clean(incident_ref, 64)
        if incident_ref:
            incident = self.manager.incidents.get(incident_ref)
            if not incident:
                raise ValueError("incident workflow context not found")
            incident_ref = incident["incident_key"]
        src = self._resolve_selector(source)
        dst = self._resolve_selector(destination)
        if not destination_prefix:
            destination_prefix = self._host_prefix(destination)
        forward = self._simulate_path(src.get("device", ""), vrf, destination_prefix, max_hops)
        return_path = self._simulate_path(dst.get("device", ""), vrf, source_prefix, max_hops)
        forward_devices = [h["device"] for h in forward.get("hops", [])]
        return_devices = [h["device"] for h in return_path.get("hops", [])]
        path_devices = list(dict.fromkeys(forward_devices + return_devices))
        f_policy = self._relevant_policy(
            direction="FORWARD", vrf=vrf, source=source, destination=destination,
            service=service, path_devices=forward_devices)
        r_policy = self._relevant_policy(
            direction="RETURN", vrf=vrf, source=destination, destination=source,
            service=service, path_devices=return_devices)
        f_gaps, f_unknown = self._gaps(f_policy, "FORWARD")
        r_gaps, r_unknown = self._gaps(r_policy, "RETURN")
        gaps = f_gaps + r_gaps
        unknown = f_unknown + r_unknown
        change_points = [
            {
                "direction": g["direction"], "device": g["device"], "path_index": g["path_index"],
                "evidence_kind": g["evidence_kind"], "evidence_ref": g["evidence_ref"],
                "why_here": g["why_here"],
            }
            for g in gaps
        ]
        proposals = [g["proposed_change"] for g in gaps if g.get("proposed_change")]
        # Preserve order but deduplicate identical proposals.
        seen = set(); unique_proposals = []
        for proposal in proposals:
            fp = self._proposal_fingerprint(proposal)
            if fp and fp not in seen:
                seen.add(fp); unique_proposals.append(proposal)
        dependencies = self._service_context(path_devices)
        result = {
            "schema_revision": self.schema_revision,
            "authority_boundary": {
                "analysis_only": True,
                "network_write": False,
                "arbitrary_command": False,
                "what_if_executes": False,
                "proposal_requires_existing_structured_change_approval": True,
            },
            "source": src, "destination": dst, "vrf": vrf, "service": service,
            "workflow_context": {"incident_ref": incident_ref} if incident_ref else {},
            "forward_path": forward, "return_path": return_path,
            "path_devices": path_devices,
            "endpoint_attachment_evidence": {
                "source": src.get("attachment"), "destination": dst.get("attachment"),
                "source_refs": src.get("evidence_refs", []), "destination_refs": dst.get("evidence_refs", []),
            },
            "service_dependency_context": dependencies,
            "policy_evidence": {"forward": f_policy, "return": r_policy},
            "configuration_gaps": gaps,
            "unknown_policy_evidence": unknown,
            "exact_change_points": change_points,
            "proposed_structured_changes": unique_proposals,
            "planning_status": (
                "GAPS_IDENTIFIED" if gaps else
                "INCOMPLETE_EVIDENCE" if (src.get("status") != "RESOLVED" or dst.get("status") != "RESOLVED" or
                                          forward.get("status") != "REACHED_TERMINAL" or
                                          return_path.get("status") != "REACHED_TERMINAL" or unknown)
                else "NO_EVIDENCE_BACKED_GAP"
            ),
        }
        evidence_identity = {
            "forward_route_ids": forward.get("route_ids", []),
            "return_route_ids": return_path.get("route_ids", []),
            "policy_ids": [x["id"] for x in f_policy + r_policy],
            "dependency_ids": [x["id"] for x in dependencies.get("dependencies", [])],
            "source_refs": src.get("evidence_refs", []), "destination_refs": dst.get("evidence_refs", []),
        }
        request = {
            "source": source, "destination": destination, "vrf": vrf,
            "destination_prefix": destination_prefix, "source_prefix": source_prefix,
            "service": service, "max_hops": max_hops, "incident_ref": incident_ref,
        }
        plan_key = _sha({"request": request, "evidence": evidence_identity})
        result["plan_key"] = plan_key
        result["evidence_fingerprint"] = _sha(evidence_identity)
        with self._persistence_lock(plan_key):
            row = self.conn.execute("SELECT id FROM change_plans WHERE plan_key=?", (plan_key,)).fetchone()
            now = time.time()
            if row:
                plan_id = int(row["id"])
                self.conn.execute(
                    "UPDATE change_plans SET planning_status=?,result_json=?,updated_ts=? WHERE id=?",
                    (result["planning_status"], _json(result), now, plan_id),
                )
            else:
                cur = self.conn.execute(
                    "INSERT INTO change_plans "
                    "(tenant_id,plan_key,source_selector,destination_selector,vrf,destination_prefix,source_prefix,service,"
                    "planning_status,input_json,result_json,created_by,created_ts,updated_ts) "
                    "VALUES ('default',?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (plan_key, source, destination, vrf, destination_prefix, source_prefix, service,
                     result["planning_status"], _json(request), _json(result), _clean(actor, 128), now, now),
                )
                plan_id = int(cur.lastrowid)
            self.conn.commit()
        self.db.audit(actor, "topology_change_plan", f"CHANGE_PLAN#{plan_id}",
                      f"status={result['planning_status']};gaps={len(gaps)};proposals={len(unique_proposals)}"
                      + (f";incident={incident_ref}" if incident_ref else ""))
        item = self.get_plan(plan_id)
        item["result"]["plan_id"] = plan_id
        return item

    def get_plan(self, plan_id):
        row = self.conn.execute("SELECT * FROM change_plans WHERE id=?", (int(plan_id),)).fetchone()
        return self._row_plan(row)

    def plans(self, limit=100):
        rows = self.conn.execute(
            "SELECT * FROM change_plans ORDER BY updated_ts DESC,id DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [self._row_plan(r) for r in rows]

    def what_if(self, plan_id, candidate_changes, *, actor="system"):
        plan = self.get_plan(plan_id)
        if not plan:
            raise ValueError("change plan not found")
        if not isinstance(candidate_changes, list) or len(candidate_changes) > 32:
            raise ValueError("candidate_changes must be a list with at most 32 proposals")
        candidates = [self._normalize_proposal(x) for x in candidate_changes]
        candidates = [x for x in candidates if x]
        candidate_fps = {self._proposal_fingerprint(x) for x in candidates}
        result = plan.get("result") or {}
        gaps = list(result.get("configuration_gaps") or [])
        closed = []
        remaining = []
        for gap in gaps:
            proposal = gap.get("proposed_change")
            if proposal and self._proposal_fingerprint(proposal) in candidate_fps:
                closed.append({**gap, "candidate_state": "CLOSED_BY_PROPOSAL"})
            else:
                remaining.append(gap)
        output = {
            "plan_id": int(plan_id), "plan_key": plan.get("plan_key"),
            "candidate_state": True, "network_write": False, "persisted_evidence_mutated": False,
            "candidate_changes": candidates,
            "closed_gaps": closed, "remaining_gaps": remaining,
            "baseline_forward_path": result.get("forward_path"),
            "baseline_return_path": result.get("return_path"),
            "status": "CANDIDATE_CLOSES_ALL_KNOWN_GAPS" if gaps and not remaining else (
                "CANDIDATE_REDUCES_KNOWN_GAPS" if closed else "NO_EVIDENCE_BACKED_CHANGE"),
        }
        self.db.audit(actor, "topology_change_plan_what_if", f"CHANGE_PLAN#{int(plan_id)}",
                      f"candidate={len(candidates)};closed={len(closed)};remaining={len(remaining)}")
        return output
