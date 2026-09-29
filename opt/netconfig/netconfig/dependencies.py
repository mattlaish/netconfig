"""MC-6 Service & Dependency Graph.

This module extends persisted network evidence into an explicit service graph
without turning temporal co-occurrence into production dependencies.  Stored
edges are typed and provenance/freshness aware.  Traversal is deterministic,
bounded, cycle-safe, tenant-scoped, and fail-closed for UNKNOWN, stale, and
(unless explicitly requested) INFERRED evidence.

Network overlays reuse the NI-7 L3 analyzer over persisted route observations;
no device I/O is performed and next-hop IP addresses are never promoted into
managed devices.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict

from .analytics.impact import ImpactSimulator

ENTITY_TYPES = (
    "SERVICE", "APPLICATION", "DATABASE", "STORAGE",
    "LOAD_BALANCER", "DNS", "VM", "HYPERVISOR",
)
RELATIONSHIPS = (
    "DEPENDS_ON", "RUNS_ON", "ROUTES_THROUGH", "USES_DNS",
    "USES_DATABASE", "USES_STORAGE", "PROTECTED_BY",
)
EVIDENCE_STATES = ("CONFIGURED", "DISCOVERED", "INFERRED", "UNKNOWN")

_HARD_MAX_DEPTH = 8
_HARD_MAX_NODES = 250
_HARD_MAX_EDGES = 1000
_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")


def _clean(value, limit=512):
    return str(value or "").replace("\x00", "").strip()[:limit]


def _json(value, limit=16384):
    raw = json.dumps(value if value is not None else {}, sort_keys=True,
                     separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) > limit:
        raise ValueError(f"metadata exceeds {limit} bytes")
    return raw


def _decode_json(value, default):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(default)) else default
    except (TypeError, json.JSONDecodeError):
        return default


class ServiceDependencyGraph:
    """Durable MC-6 service/dependency graph service."""

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self.impact_simulator = ImpactSimulator()

    @staticmethod
    def _tenant(tenant_id):
        tenant = _clean(tenant_id or "default", 128) or "default"
        # Current NetConfig control plane is single-tenant.  Keep the storage
        # column for forward compatibility but never let callers cross scope.
        if tenant != "default":
            raise ValueError("tenant scope is not available in this deployment")
        return tenant

    @staticmethod
    def _key(value, label="entity_key"):
        key = _clean(value, 200)
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f"invalid {label}")
        return key

    @staticmethod
    def _entity_type(value):
        value = _clean(value, 64).upper()
        if value not in ENTITY_TYPES:
            raise ValueError("invalid service entity type")
        return value

    @staticmethod
    def _relationship(value):
        value = _clean(value, 64).upper()
        if value not in RELATIONSHIPS:
            raise ValueError("invalid dependency relationship")
        return value

    @staticmethod
    def _evidence_state(value):
        value = _clean(value, 32).upper()
        if value not in EVIDENCE_STATES:
            raise ValueError("invalid dependency evidence state")
        return value

    @staticmethod
    def _row_entity(row):
        if not row:
            return None
        item = dict(row)
        item["metadata"] = _decode_json(item.pop("metadata_json", "{}"), {})
        return item

    @staticmethod
    def _freshness(row, now=None):
        now = time.time() if now is None else float(now)
        state = str(row.get("evidence_state") or "UNKNOWN").upper()
        observed = float(row.get("observed_ts") or 0)
        max_age = int(row.get("max_age_seconds") or 0)
        active = bool(row.get("active", 1))
        age = max(0.0, now - observed) if observed > 0 else None
        if not active:
            return {"fresh": False, "freshness": "INACTIVE", "age_seconds": age}
        if state == "CONFIGURED":
            return {"fresh": True, "freshness": "CONFIGURED", "age_seconds": age}
        if state == "UNKNOWN" or observed <= 0 or max_age <= 0:
            return {"fresh": False, "freshness": "UNKNOWN", "age_seconds": age}
        fresh = age <= max_age
        return {"fresh": bool(fresh), "freshness": "FRESH" if fresh else "STALE",
                "age_seconds": age}

    @classmethod
    def _row_dependency(cls, row, now=None):
        if not row:
            return None
        item = dict(row)
        item["active"] = bool(item.get("active"))
        item["metadata"] = _decode_json(item.pop("metadata_json", "{}"), {})
        item.update(cls._freshness(item, now))
        return item

    def put_entity(self, entity_key, entity_type, name, *, description="", metadata=None,
                   actor="system", tenant_id="default"):
        tenant = self._tenant(tenant_id)
        key = self._key(entity_key)
        entity_type = self._entity_type(entity_type)
        name = _clean(name, 200)
        if not name:
            raise ValueError("entity name is required")
        description = _clean(description, 2000)
        metadata_json = _json(metadata or {})
        actor = _clean(actor, 128)
        now = time.time()
        row = self.conn.execute(
            "SELECT id FROM service_entities WHERE tenant_id=? AND entity_key=?",
            (tenant, key),
        ).fetchone()
        if row:
            entity_id = int(row["id"])
            self.conn.execute(
                "UPDATE service_entities SET entity_type=?,name=?,description=?,metadata_json=?,updated_ts=? "
                "WHERE id=?",
                (entity_type, name, description, metadata_json, now, entity_id),
            )
            action = "dependency_entity_update"
        else:
            cur = self.conn.execute(
                "INSERT INTO service_entities(tenant_id,entity_key,entity_type,name,description,metadata_json,"
                "created_by,created_ts,updated_ts) VALUES(?,?,?,?,?,?,?,?,?)",
                (tenant, key, entity_type, name, description, metadata_json, actor, now, now),
            )
            entity_id = int(cur.lastrowid)
            action = "dependency_entity_create"
        self.conn.commit()
        self.db.audit(actor, action, key, f"type={entity_type}")
        return self.get_entity(key, tenant_id=tenant)

    def get_entity(self, entity_key, *, tenant_id="default"):
        tenant = self._tenant(tenant_id)
        key = self._key(entity_key)
        row = self.conn.execute(
            "SELECT * FROM service_entities WHERE tenant_id=? AND entity_key=?",
            (tenant, key),
        ).fetchone()
        return self._row_entity(row)

    def entities(self, *, entity_type="", search="", limit=250, tenant_id="default"):
        tenant = self._tenant(tenant_id)
        q = "SELECT * FROM service_entities WHERE tenant_id=?"
        args = [tenant]
        if entity_type:
            q += " AND entity_type=?"; args.append(self._entity_type(entity_type))
        if search:
            needle = "%" + _clean(search, 200).replace("%", "") + "%"
            q += " AND (entity_key LIKE ? OR name LIKE ? OR description LIKE ?)"
            args += [needle, needle, needle]
        q += " ORDER BY entity_type,name,entity_key LIMIT ?"
        args.append(max(1, min(int(limit), 1000)))
        return [self._row_entity(r) for r in self.conn.execute(q, tuple(args)).fetchall()]

    def put_dependency(self, source_key, target_key, relationship, *, evidence_state,
                       provenance, evidence_ref="", observed_ts=None, max_age_seconds=None,
                       vrf="", destination_prefix="", metadata=None, actor="system",
                       tenant_id="default"):
        tenant = self._tenant(tenant_id)
        source = self._key(source_key, "source_key")
        target = self._key(target_key, "target_key")
        if source == target:
            raise ValueError("self dependency is not allowed")
        if not self.get_entity(source, tenant_id=tenant) or not self.get_entity(target, tenant_id=tenant):
            raise ValueError("dependency endpoints must be existing service entities")
        relationship = self._relationship(relationship)
        state = self._evidence_state(evidence_state)
        provenance = _clean(provenance, 256)
        evidence_ref = _clean(evidence_ref, 512)
        if not provenance:
            raise ValueError("dependency provenance is required")
        if state in {"DISCOVERED", "INFERRED"} and not evidence_ref:
            raise ValueError(f"{state.lower()} dependency requires evidence_ref")
        now = time.time()
        observed_ts = now if observed_ts is None else float(observed_ts)
        if observed_ts < 0:
            raise ValueError("observed_ts must be non-negative")
        if state == "CONFIGURED":
            max_age = 0
        elif state == "UNKNOWN":
            max_age = 0 if max_age_seconds in (None, "", 0, "0") else int(max_age_seconds)
        else:
            max_age = 3600 if max_age_seconds in (None, "", 0, "0") else int(max_age_seconds)
            if max_age < 60 or max_age > 2592000:
                raise ValueError("evidence max_age_seconds must be between 60 and 2592000")
        vrf = _clean(vrf, 128)
        destination_prefix = _clean(destination_prefix, 255)
        if relationship != "ROUTES_THROUGH" and (vrf or destination_prefix):
            raise ValueError("VRF/destination scope is only valid for ROUTES_THROUGH")
        metadata_json = _json(metadata or {})
        fp_basis = json.dumps({
            "tenant": tenant, "source": source, "target": target,
            "relationship": relationship, "state": state,
            "provenance": provenance, "evidence_ref": evidence_ref,
            "vrf": vrf, "destination_prefix": destination_prefix,
        }, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(fp_basis.encode("utf-8")).hexdigest()
        row = self.conn.execute(
            "SELECT id FROM service_dependencies WHERE fingerprint=?", (fingerprint,)
        ).fetchone()
        actor = _clean(actor, 128)
        if row:
            dep_id = int(row["id"])
            self.conn.execute(
                "UPDATE service_dependencies SET observed_ts=?,received_ts=?,max_age_seconds=?,metadata_json=?,"
                "active=1,updated_ts=? WHERE id=?",
                (observed_ts, now, max_age, metadata_json, now, dep_id),
            )
            action = "dependency_edge_refresh"
        else:
            cur = self.conn.execute(
                "INSERT INTO service_dependencies(tenant_id,source_key,target_key,relationship,evidence_state,"
                "provenance,evidence_ref,vrf,destination_prefix,max_age_seconds,observed_ts,received_ts,active,"
                "metadata_json,fingerprint,created_by,created_ts,updated_ts) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?)",
                (tenant, source, target, relationship, state, provenance, evidence_ref,
                 vrf, destination_prefix, max_age, observed_ts, now, metadata_json,
                 fingerprint, actor, now, now),
            )
            dep_id = int(cur.lastrowid)
            action = "dependency_edge_create"
        self.conn.commit()
        self.db.audit(actor, action, f"DEPENDENCY#{dep_id}",
                      f"{source}->{target};relationship={relationship};state={state}")
        return self.get_dependency(dep_id, tenant_id=tenant)

    def get_dependency(self, dependency_id, *, tenant_id="default", now=None):
        tenant = self._tenant(tenant_id)
        row = self.conn.execute(
            "SELECT * FROM service_dependencies WHERE tenant_id=? AND id=?",
            (tenant, int(dependency_id)),
        ).fetchone()
        return self._row_dependency(row, now)

    def dependencies(self, *, source_key="", target_key="", relationship="",
                     evidence_state="", include_inactive=False, limit=500,
                     tenant_id="default", now=None):
        tenant = self._tenant(tenant_id)
        q = "SELECT * FROM service_dependencies WHERE tenant_id=?"
        args = [tenant]
        if not include_inactive:
            q += " AND active=1"
        if source_key:
            q += " AND source_key=?"; args.append(self._key(source_key, "source_key"))
        if target_key:
            q += " AND target_key=?"; args.append(self._key(target_key, "target_key"))
        if relationship:
            q += " AND relationship=?"; args.append(self._relationship(relationship))
        if evidence_state:
            q += " AND evidence_state=?"; args.append(self._evidence_state(evidence_state))
        q += " ORDER BY source_key,relationship,target_key,id LIMIT ?"
        args.append(max(1, min(int(limit), 2000)))
        return [self._row_dependency(r, now) for r in self.conn.execute(q, tuple(args)).fetchall()]

    def set_active(self, dependency_id, active, *, actor="system", tenant_id="default"):
        tenant = self._tenant(tenant_id)
        current = self.get_dependency(dependency_id, tenant_id=tenant)
        if not current:
            raise ValueError("dependency not found")
        now = time.time()
        self.conn.execute(
            "UPDATE service_dependencies SET active=?,updated_ts=? WHERE tenant_id=? AND id=?",
            (int(bool(active)), now, tenant, int(dependency_id)),
        )
        self.conn.commit()
        self.db.audit(_clean(actor, 128), "dependency_edge_state", f"DEPENDENCY#{int(dependency_id)}",
                      "active=1" if active else "active=0")
        return self.get_dependency(dependency_id, tenant_id=tenant)

    @staticmethod
    def _traversable(edge, include_inferred, include_stale):
        if not edge.get("active"):
            return False, "INACTIVE"
        state = edge.get("evidence_state")
        if state == "UNKNOWN":
            return False, "UNKNOWN"
        if state == "INFERRED" and not include_inferred:
            return False, "INFERRED_REQUIRES_OPT_IN"
        if edge.get("freshness") == "STALE" and not include_stale:
            return False, "STALE"
        if state in {"DISCOVERED", "INFERRED"} and not edge.get("fresh") and not include_stale:
            return False, edge.get("freshness") or "NOT_FRESH"
        return True, ""

    def graph(self, root_key, *, max_depth=4, max_nodes=100, include_inferred=False,
              include_stale=False, tenant_id="default", now=None):
        tenant = self._tenant(tenant_id)
        root = self._key(root_key, "root_key")
        root_entity = self.get_entity(root, tenant_id=tenant)
        if not root_entity:
            raise ValueError("root service entity not found")
        depth_limit = int(max_depth)
        node_limit = int(max_nodes)
        if depth_limit < 0 or depth_limit > _HARD_MAX_DEPTH:
            raise ValueError(f"max_depth must be between 0 and {_HARD_MAX_DEPTH}")
        if node_limit < 1 or node_limit > _HARD_MAX_NODES:
            raise ValueError(f"max_nodes must be between 1 and {_HARD_MAX_NODES}")
        now = time.time() if now is None else float(now)

        nodes = {root: {**root_entity, "depth": 0}}
        edges = []
        queue = [(root, 0, frozenset({root}))]
        expanded = set()
        truncated = False
        truncation_reason = ""
        cycle_edges = 0

        while queue and not truncated:
            source, depth, ancestors = queue.pop(0)
            if source in expanded:
                continue
            expanded.add(source)
            if depth >= depth_limit:
                continue
            outgoing = self.dependencies(source_key=source, limit=2000, tenant_id=tenant, now=now)
            for edge in outgoing:
                if len(edges) >= _HARD_MAX_EDGES:
                    truncated = True; truncation_reason = "max_edges"; break
                traversable, excluded = self._traversable(edge, bool(include_inferred), bool(include_stale))
                target = edge["target_key"]
                cycle = target in ancestors
                already_seen = target in nodes
                if cycle and traversable:
                    cycle_edges += 1
                rendered = dict(edge)
                rendered["traversed"] = bool(traversable and not cycle and not already_seen)
                rendered["cycle"] = bool(cycle)
                rendered["exclusion_reason"] = excluded
                if traversable and already_seen and not cycle:
                    rendered["exclusion_reason"] = "ALREADY_VISITED"
                edges.append(rendered)
                if not traversable or cycle or already_seen:
                    continue
                if len(nodes) >= node_limit:
                    truncated = True; truncation_reason = "max_nodes"; break
                target_entity = self.get_entity(target, tenant_id=tenant)
                if not target_entity:
                    # Referential integrity is enforced by the service, but fail
                    # closed if a DB was manually damaged.
                    rendered["traversed"] = False
                    rendered["exclusion_reason"] = "MISSING_TARGET"
                    continue
                nodes[target] = {**target_entity, "depth": depth + 1}
                queue.append((target, depth + 1, ancestors | {target}))

        result_nodes = sorted(nodes.values(), key=lambda x: (int(x["depth"]), x["entity_type"], x["entity_key"]))
        counts = {state: 0 for state in EVIDENCE_STATES}
        freshness = {"CONFIGURED": 0, "FRESH": 0, "STALE": 0, "UNKNOWN": 0, "INACTIVE": 0}
        for edge in edges:
            counts[edge["evidence_state"]] = counts.get(edge["evidence_state"], 0) + 1
            freshness[edge["freshness"]] = freshness.get(edge["freshness"], 0) + 1
        return {
            "root": root,
            "nodes": result_nodes,
            "edges": edges,
            "summary": {"nodes": len(result_nodes), "edges": len(edges),
                        "cycle_edges": cycle_edges, "evidence_states": counts,
                        "freshness": freshness},
            "bounds": {"max_depth": depth_limit, "max_nodes": node_limit,
                       "hard_max_depth": _HARD_MAX_DEPTH, "hard_max_nodes": _HARD_MAX_NODES,
                       "hard_max_edges": _HARD_MAX_EDGES},
            "truncated": truncated,
            "truncation_reason": truncation_reason,
            "semantics": {
                "inferred_traversal": bool(include_inferred),
                "stale_traversal": bool(include_stale),
                "unknown_is_failure": False,
            },
        }

    def impact(self, root_key, *, max_depth=5, max_nodes=100, include_inferred=False,
               tenant_id="default", now=None):
        graph = self.graph(root_key, max_depth=max_depth, max_nodes=max_nodes,
                           include_inferred=include_inferred, include_stale=False,
                           tenant_id=tenant_id, now=now)
        node_types = {n["entity_key"]: n["entity_type"] for n in graph["nodes"]}
        links = []
        for edge in graph["edges"]:
            if not edge.get("traversed"):
                continue
            links.append({
                "source": edge["source_key"], "target": edge["target_key"],
                "target_type": node_types.get(edge["target_key"], "SERVICE"),
                "relationship": edge["relationship"], "resolution_state": "RESOLVED",
                "evidence_ref": edge.get("evidence_ref") or f"dependency:{edge['id']}",
            })
        observations = self.impact_simulator.simulate(
            self._tenant(tenant_id), self._key(root_key, "root_key"), links,
            max_depth=min(int(max_depth), _HARD_MAX_DEPTH),
        )
        return {"root": graph["root"], "graph": graph,
                "affected": [asdict(x) for x in observations]}

    def network_overlay(self, root_key, source_device, vrf, destination_prefix, *,
                        max_hops=16, tenant_id="default"):
        """Read-only overlay from explicit NI-7 route observations.

        This method never polls a device and never persists an analytics job.  It
        reuses the existing L3 analyzer and therefore preserves VRF scoping,
        ambiguity fail-closed behavior, loop bounds, and the rule that a next-hop
        IP is not a managed-device identity.
        """
        self._tenant(tenant_id)
        root = self._key(root_key, "root_key")
        if not self.get_entity(root):
            raise ValueError("root service entity not found")
        source_device = _clean(source_device, 255)
        vrf = _clean(vrf or "default", 128) or "default"
        destination_prefix = _clean(destination_prefix, 255)
        max_hops = int(max_hops)
        if max_hops < 1 or max_hops > 64:
            raise ValueError("max_hops must be between 1 and 64")
        rows = self.manager.analytics.l3_routes(
            vrf=vrf, destination_prefix=destination_prefix, limit=1000)
        managed = [d["name"] for d in self.manager.inv.all()]
        observation = self.manager.analytics.l3_analyzer.simulate(
            source_device, vrf, destination_prefix, rows, managed, max_hops=max_hops)
        path = asdict(observation)
        nodes = [{"key": root, "kind": "SERVICE_ENTITY", "label": root}]
        edges = []
        for hop in observation.hops:
            device = str(hop.get("device") or "")
            device_key = "device:" + device
            if not any(n["key"] == device_key for n in nodes):
                nodes.append({"key": device_key, "kind": "NETWORK_DEVICE", "label": device,
                              "managed": bool(self.manager.inv.get(device))})
            if len(nodes) == 2 and not edges:
                edges.append({"source": root, "target": device_key,
                              "relationship": "ROUTES_THROUGH",
                              "evidence_state": "DISCOVERED",
                              "evidence_ref": f"l3_route:{hop.get('route_id') or 0}",
                              "vrf": vrf, "destination_prefix": destination_prefix})
            next_device = str(hop.get("next_device") or "")
            if next_device:
                # The analyzer already requires next_device to be an explicit
                # managed object.  We intentionally ignore next_hop IP here.
                next_key = "device:" + next_device
                if not any(n["key"] == next_key for n in nodes):
                    nodes.append({"key": next_key, "kind": "NETWORK_DEVICE", "label": next_device,
                                  "managed": bool(self.manager.inv.get(next_device))})
                edges.append({"source": device_key, "target": next_key,
                              "relationship": "ROUTES_THROUGH",
                              "evidence_state": "DISCOVERED",
                              "evidence_ref": f"l3_route:{hop.get('route_id') or 0}",
                              "vrf": vrf, "destination_prefix": destination_prefix})
        return {"root": root, "path": path, "nodes": nodes, "edges": edges,
                "overlay_complete": observation.status == self.manager.analytics.l3_analyzer.TERMINAL,
                "device_io_performed": False}
