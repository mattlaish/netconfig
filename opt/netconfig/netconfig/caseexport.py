"""Support-case export workflow for D.5 Phase 4C.

A case export is a bounded, portable archive built from incident-owned metadata,
reference-only timeline/evidence indexes, and selected *existing* diagnostic
bundles already linked to that incident.  It deliberately does not copy raw
syslog messages, audit details, compliance reports, or device configuration text.

Diagnostic bundles are embedded as opaque files and are never extracted or
rewritten.  Phase 4D is responsible for cryptographic signing; Phase 4C provides
hash/integrity manifests only.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .debug import redact, sha256_file
from .evidence_signing import (
    EvidenceSigner, EvidenceSigningError, configured_trusted_fingerprints,
    signing_required, verify_signed_archive,
)

MAX_CASE_BUNDLES = 32
MAX_CASE_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_REASON = 1000

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|community|client[_-]?secret|api[_-]?token)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def _safe_text(value, limit):
    text = str(value or "").strip()
    if len(text) > limit:
        raise ValueError(f"text exceeds {limit} characters")
    return _SECRET_ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)


def _write_json(path, data):
    path.write_text(json.dumps(redact(data), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _manifest_for(root):
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {"manifest.json", "manifest.sha256"}:
            rows.append({
                "path": str(path.relative_to(root)),
                "sha256": sha256_file(path),
                "size": path.stat().st_size,
            })
    return rows


class SupportCaseExporter:
    """Create and manage incident support-case archives."""

    def __init__(self, manager):
        self.manager = manager
        self.db = manager.db
        self.conn = manager.db.conn
        self.incidents = manager.incidents
        self.bundle_root = Path(manager.paths.home) / "debug-bundles"
        self.root = Path(manager.paths.home) / "case-exports"
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass

    @staticmethod
    def _row(row):
        if not row:
            return None
        out = dict(row)
        for key in ("bundle_names", "missing_bundles"):
            try:
                out[key] = json.loads(out.get(key) or "[]")
            except (TypeError, json.JSONDecodeError):
                out[key] = []
        out["available"] = bool(out.get("available", True))
        return out

    def list_exports(self, incident_ref, limit=100):
        incident = self.incidents.get(incident_ref)
        if not incident:
            raise ValueError("incident not found")
        limit = max(1, min(int(limit), 1000))
        rows = self.conn.execute(
            "SELECT * FROM incident_case_exports WHERE incident_id=? "
            "ORDER BY created_ts DESC,id DESC LIMIT ?", (incident["id"], limit)).fetchall()
        result = []
        for row in rows:
            item = self._row(row)
            item["available"] = self._path_for_record(item) is not None
            result.append(item)
        return result

    def get_export(self, incident_ref, export_key):
        incident = self.incidents.get(incident_ref)
        if not incident:
            return None, None
        key = str(export_key or "").strip()
        if not key or "/" in key or "\\" in key:
            return None, None
        row = self.conn.execute(
            "SELECT * FROM incident_case_exports WHERE incident_id=? AND export_key=?",
            (incident["id"], key)).fetchone()
        item = self._row(row)
        if not item:
            return None, None
        path = self._path_for_record(item)
        item["available"] = path is not None
        return item, path

    def _path_for_record(self, record):
        raw = str(record.get("filename") or "")
        safe = Path(raw).name
        if not safe or safe != raw or not safe.endswith(".tar.gz"):
            return None
        target = self.root / safe
        return target if target.is_file() else None

    def _select_bundles(self, incident, requested):
        linked = {item["bundle_name"]: item for item in self.incidents.bundles(incident["id"])}
        if requested:
            names = []
            for raw in requested:
                name = Path(str(raw or "")).name
                if not name or name != str(raw) or not name.endswith(".tar.gz"):
                    raise ValueError("invalid diagnostic bundle name")
                if name not in linked:
                    raise ValueError(f"diagnostic bundle is not linked to incident: {name}")
                if name not in names:
                    names.append(name)
        else:
            names = list(linked)
        if len(names) > MAX_CASE_BUNDLES:
            raise ValueError(f"support case exceeds {MAX_CASE_BUNDLES} diagnostic bundles")

        selected = []
        missing = []
        total = 0
        for name in names:
            target = self.bundle_root / name
            if not target.is_file():
                if requested:
                    raise ValueError(f"diagnostic bundle not found: {name}")
                missing.append(name)
                continue
            size = target.stat().st_size
            total += size
            if total > MAX_CASE_BUNDLE_BYTES:
                raise ValueError("support case diagnostic bundles exceed byte budget")
            selected.append((name, target, size))
        return selected, missing

    def _incident_metadata(self, incident):
        fields = (
            "id", "incident_key", "title", "description", "severity", "status", "tags",
            "created_by", "created_ts", "updated_by", "updated_ts", "closed_by", "closed_ts",
        )
        data = {key: incident.get(key) for key in fields}
        data["title"] = _safe_text(data.get("title"), 200)
        data["description"] = _safe_text(data.get("description"), 10000)
        data["tags"] = [_safe_text(tag, 64) for tag in (data.get("tags") or [])]
        return data

    def _evidence_index(self, incident):
        rows = []
        for item in self.incidents.evidence_links(incident["id"]):
            rows.append({
                "link_id": item.get("id"),
                "source_type": item.get("source_type"),
                "source_ref": item.get("source_ref"),
                "linked_by": item.get("linked_by"),
                "linked_ts": item.get("linked_ts"),
                "note": _safe_text(item.get("note"), 1000),
                "available": bool(item.get("available")),
            })
        return rows

    def _timeline_index(self, incident):
        rows = []
        for item in self.incidents.timeline(incident["id"], 2000):
            # Reference/index fields only.  In particular, do not export the
            # authoritative audit detail, syslog body, compliance report, or
            # configuration contents resolved by Incident.timeline().
            rows.append({
                "kind": item.get("kind"),
                "source_type": item.get("source_type"),
                "source_id": item.get("source_id"),
                "link_id": item.get("link_id"),
                "ts": item.get("ts"),
                "available": bool(item.get("available", False)),
            })
        return rows

    def export_case(self, incident_ref, actor, bundle_names=None, reason="", require_signature=False):
        incident = self.incidents.get(incident_ref)
        if not incident:
            raise ValueError("incident not found")
        reason = _safe_text(reason, MAX_REASON)
        if isinstance(bundle_names, str):
            bundle_names = [bundle_names]
        requested = [str(x) for x in (bundle_names or []) if str(x).strip()]
        selected, missing = self._select_bundles(incident, requested)

        signer = EvidenceSigner()
        require_signing = bool(require_signature or signing_required(self.manager.settings))
        signing_identity = None
        if signer.available:
            # A configured-but-invalid key is a hard failure.  Never silently
            # downgrade to unsigned output after an operator configured signing.
            signing_identity = signer.identity()
        elif require_signing:
            raise EvidenceSigningError("evidence signing is required but no signing key is configured")

        now = time.time()
        stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%Y%m%d-%H%M%S")
        year = datetime.fromtimestamp(now, timezone.utc).year
        export_key = f"CEX-{year}-{secrets.token_hex(6).upper()}"
        filename = f"netconfig-case-{incident['incident_key']}-{stamp}-{export_key[-6:]}.tar.gz"
        output = self.root / filename

        temp_parent = Path(tempfile.mkdtemp(prefix=".case-build-", dir=self.root))
        case_dir = temp_parent / f"netconfig-case-{incident['incident_key']}-{export_key}"
        case_dir.mkdir(mode=0o700)
        try:
            bundle_dir = case_dir / "bundles"
            bundle_dir.mkdir(mode=0o700)
            embedded = []
            for name, source, size in selected:
                destination = bundle_dir / name
                shutil.copyfile(source, destination)
                try:
                    destination.chmod(0o600)
                except OSError:
                    pass
                embedded.append({"name": name, "size": size, "sha256": sha256_file(destination)})

            case_data = {
                "schema": "netconfig-support-case-v1",
                "export_key": export_key,
                "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "created_by": actor or "",
                "reason": reason,
                "incident": self._incident_metadata(incident),
                "embedded_bundles": embedded,
                "missing_linked_bundles": missing,
                "evidence_policy": (
                    "reference-only indexes; authoritative syslog/audit/compliance/config payloads "
                    "are not copied into this package"
                ),
                "signing": ({
                    "status": "SIGNED",
                    "algorithm": signing_identity["algorithm"],
                    "key_fingerprint": signing_identity["key_fingerprint"],
                    "trust_model": "signature validity plus independent fingerprint trust pin",
                } if signing_identity else {
                    "status": "UNSIGNED",
                    "reason": "no evidence signing key configured",
                }),
            }
            _write_json(case_dir / "case.json", case_data)
            _write_json(case_dir / "evidence-links.json", self._evidence_index(incident))
            _write_json(case_dir / "timeline-references.json", self._timeline_index(incident))
            _write_json(case_dir / "protocol-traces.json",
                        self.manager.protocol_traces.export_for_incident(incident["id"]))
            readme = (
                "NetConfig support-case export\n"
                f"Incident: {incident['incident_key']}\n"
                f"Export: {export_key}\n\n"
                "This Phase 4C package contains incident-owned metadata, reference-only evidence/timeline "
                "indexes, sanitized protocol-trace metadata, and selected diagnostic bundles copied byte-for-byte. "
                "It does not embed raw syslog messages, audit details, compliance reports, device "
                "configuration text, SSH terminal output, or SNMP packets/credentials.\n"
                "Integrity is SHA-256 based only; cryptographic signing/verification is Phase 4D work.\n"
            )
            (case_dir / "README.txt").write_text(readme, encoding="utf-8")

            manifest = {
                "schema": "netconfig-support-case-manifest-v1",
                "export_key": export_key,
                "incident_key": incident["incident_key"],
                "created_at": case_data["created_at"],
                "files": _manifest_for(case_dir),
            }
            _write_json(case_dir / "manifest.json", manifest)
            digest = sha256_file(case_dir / "manifest.json")
            (case_dir / "manifest.sha256").write_text(
                f"{digest}  manifest.json\n", encoding="ascii")
            signature_record = None
            if signing_identity:
                signature_record = signer.sign_manifest(case_dir / "manifest.json", case_dir)

            with tarfile.open(output, "w:gz") as tar:
                tar.add(case_dir, arcname=case_dir.name, recursive=True)
            try:
                output.chmod(0o600)
            except OSError:
                pass

            archive_size = output.stat().st_size
            archive_sha = sha256_file(output)
            self.conn.execute(
                "INSERT INTO incident_case_exports(incident_id,export_key,filename,created_by,created_ts,"
                "reason,bundle_names,missing_bundles,bundle_count,size,sha256,signature_state,"
                "signature_algorithm,signer_fingerprint) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (incident["id"], export_key, filename, actor or "", now, reason,
                 json.dumps([x[0] for x in selected]), json.dumps(missing), len(selected),
                 archive_size, archive_sha, "SIGNED" if signature_record else "UNSIGNED",
                 signature_record.get("algorithm", "") if signature_record else "",
                 signature_record.get("key_fingerprint", "") if signature_record else ""))
            self.conn.commit()
            self.db.audit(actor, "incident_case_export_create", incident["incident_key"],
                          f"{export_key};bundles={len(selected)};sha256={archive_sha}")
            return self.get_export(incident["id"], export_key)[0]
        except Exception:
            try:
                self.conn.execute("DELETE FROM incident_case_exports WHERE export_key=?", (export_key,))
                self.conn.commit()
            except Exception:
                pass
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
            raise
        finally:
            shutil.rmtree(temp_parent, ignore_errors=True)

    def verify_export(self, incident_ref, export_key, trusted_fingerprints=None):
        item, path = self.get_export(incident_ref, export_key)
        if not item or path is None:
            raise ValueError("support case export not found")
        if path.stat().st_size != int(item.get("size") or -1) or sha256_file(path) != item.get("sha256"):
            raise ValueError("support case export integrity mismatch")
        if item.get("signature_state") == "SIGNED":
            trusted = configured_trusted_fingerprints(
                settings=self.manager.settings, extra=trusted_fingerprints)
            result = verify_signed_archive(path, trusted)
            if result.get("key_fingerprint") != item.get("signer_fingerprint"):
                raise ValueError("support case signer fingerprint mismatch")
            if trusted and not result.get("trusted"):
                raise ValueError("support case signature is valid but signer is not trusted")
            item["signature_verification"] = result
        else:
            item["signature_verification"] = {
                "signed": False, "signature_valid": False, "trusted": False,
            }
        return item, path

    def verify_signature(self, incident_ref, export_key, trusted_fingerprints=None, actor=""):
        item, _path = self.verify_export(incident_ref, export_key, trusted_fingerprints)
        result = item.get("signature_verification", {})
        if actor:
            incident = self.incidents.get(incident_ref)
            if incident:
                self.db.audit(actor, "incident_case_export_verify", incident["incident_key"],
                              f"{export_key};signed={bool(result.get('signed'))};"
                              f"valid={bool(result.get('signature_valid'))};"
                              f"trusted={bool(result.get('trusted'))}")
        return result

    def record_download(self, incident_ref, export_key, actor):
        try:
            item, path = self.verify_export(incident_ref, export_key)
        except ValueError as exc:
            text = str(exc)
            incident = self.incidents.get(incident_ref)
            if incident and "integrity mismatch" in text:
                self.db.audit(actor, "incident_case_export_integrity_failure",
                              incident["incident_key"], str(export_key)[:200])
            elif incident and ("signature" in text or "signer" in text):
                self.db.audit(actor, "incident_case_export_signature_failure",
                              incident["incident_key"], str(export_key)[:200])
            raise
        incident = self.incidents.get(incident_ref)
        self.db.audit(actor, "incident_case_export_download", incident["incident_key"], export_key)
        return item, path
