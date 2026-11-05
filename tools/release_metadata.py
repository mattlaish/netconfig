#!/usr/bin/env python3
"""Generate/check deterministic corrective-RPM release metadata and SPDX 2.3 source SBOM."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "67.6"
VERSION = "2.0.0-67.6"
SCHEMA = "mc11-topology-change-planning-1"
EXCLUDE_NAMES = {
    "SBOM.spdx.json", "RELEASE_MANIFEST.json", "RELEASE_MANIFEST_SHA256.txt",
    "R67_SOURCE_MANIFEST.json", "R67_2_SOURCE_MANIFEST.json", "SHA256SUMS", "ARTIFACT_MANIFEST.json",
    "source-manifest.sha256",
}
EXCLUDE_PARTS = {".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__", "dist", "build", "RPMS", "SRPMS", "SOURCES", "SPECS", "BUILD", "BUILDROOT"}


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_files():
    result = []
    # Sort by the POSIX relative path: Path ordering is case-insensitive on Windows,
    # which made Windows-generated metadata fail the drift check on Linux.
    for path in sorted(ROOT.rglob("*"), key=lambda p: p.relative_to(ROOT).as_posix()):
        if not path.is_file() or any(part in EXCLUDE_PARTS for part in path.parts):
            continue
        if path.name in EXCLUDE_NAMES or path.suffix in {".pyc", ".rpm"}:
            continue
        result.append(path)
    return result


def spdx_id(relative: str) -> str:
    return "SPDXRef-File-" + hashlib.sha256(relative.encode()).hexdigest()[:24]


def build_sbom():
    files = source_files()
    entries = []
    sha1s = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        sha1 = digest(path, "sha1")
        sha256 = digest(path, "sha256")
        sha1s.append(sha1)
        entries.append({
            "SPDXID": spdx_id(rel),
            "fileName": "./" + rel,
            "checksums": [
                {"algorithm": "SHA1", "checksumValue": sha1},
                {"algorithm": "SHA256", "checksumValue": sha256},
            ],
            "licenseConcluded": "NOASSERTION",
            "copyrightText": "NOASSERTION",
        })
    verification = hashlib.sha1("".join(sorted(sha1s)).encode()).hexdigest()
    namespace = f"https://netconfig.local/spdx/{VERSION}/{verification}"
    package_id = "SPDXRef-Package-NetConfig"
    relationships = [
        {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": package_id}
    ] + [
        {"spdxElementId": package_id, "relationshipType": "CONTAINS", "relatedSpdxElement": item["SPDXID"]}
        for item in entries
    ]
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"NetConfig {VERSION} source SBOM",
        "documentNamespace": namespace,
        "creationInfo": {"creators": ["Tool: NetConfig deterministic release_metadata.py"], "created": "2026-09-25T00:00:00Z"},
        "packages": [{
            "name": "netconfig",
            "SPDXID": package_id,
            "versionInfo": VERSION,
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": True,
            "packageVerificationCode": {"packageVerificationCodeValue": verification},
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "LicenseRef-Proprietary",
            "copyrightText": "NOASSERTION",
        }],
        "files": entries,
        "relationships": relationships,
        "hasExtractedLicensingInfos": [{
            "licenseId": "LicenseRef-Proprietary",
            "name": "Proprietary - all rights reserved",
            "extractedText": "No open-source license is granted by this artifact.",
        }],
    }


def build_release_manifest(sbom):
    return {
        "name": "NetConfig",
        "version": "2.0.0",
        "current_release": RELEASE,
        "current_package": VERSION,
        "current_slice": "R67.6 RSA 512+ SSH Compatibility RPM",
        "base_track": "Corrective packaging on R67.5; frozen MC-11 feature lineage",
        "status": "IMPLEMENTED_TESTING_DEFERRED",
        "schema_revision": SCHEMA,
        "feature_freeze": True,
        "mc12_defined": False,
        "monitoring_correlation_lineage": "CLOSED at R59/MC-11; do not create MC-12",
        "authority_boundary": "Feature lineage remains frozen; R67.6 adds an isolated, per-device SSHv2 compatibility backend for legacy algorithms and RSA host keys from 512 bits while preserving prior SNMPv3, Endpoint CSV, history and workflow fixes. Network mutation authority is unchanged and remains exclusively approval-gated.",
        "release_candidate_policy": {
            "candidate_evidence_bound_to_exact_fingerprint": True,
            "changes_invalidate_prior_rc_evidence": True,
            "all_required_live_rc_gates_required": True,
            "r67_2_cannot_promote_released": True,
        },
        "sbom": {
            "artifact": "SBOM.spdx.json",
            "format": "SPDX-2.3",
            "files_analyzed": len(sbom["files"]),
            "package_verification_code": sbom["packages"][0]["packageVerificationCode"]["packageVerificationCodeValue"],
        },
        "qualification": {
            "source_tree": "2026-11-04 RSA 512/1024/2048 loopback and related SSH/SNMPv3/Web/protocol regression: 99 passed / 2 explicit Windows POSIX-mode exclusions; selftest ALL PASS",
            "vendor_profile_focused": "Historical September checkpoint: 8/8 PASS; November evidence repairs covered by focused source regression",
            "legacy_selftest": "ALL PASS",
            "release_candidate_qualified": False,
            "production_release_claim": False,
        },
        "offline_rpm": {
            "boundary": "offline helper RPM only; deterministic artifact evidence is external to source metadata to avoid a source/artifact hash cycle",
            "artifact_evidence": "see external artifact packaging integrity gate",
        },
        "deferred": [
            "all 12 required LIVE_RC gates",
            "external/upstream Git-index 100755 fresh-clone verification",
            "live AlmaLinux 10 RPM/systemd/SELinux install and upgrade",
            "live PostgreSQL/backup/restore/concurrency/recovery",
            "live multi-node HA/failure-domain failover/fencing",
            "real protocol/vendor device qualification",
            "production scale/performance",
            "independent security/operator/supportability/MC-11 end-to-end acceptance",
        ],
        "release_promotion": "NOT_PERFORMED",
        "production_release_claim": False,
        "next_track": "R68 v2 Production Release Decision only after exact current candidate live qualification",
    }


def serialized(obj):
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sbom = build_sbom()
    release = build_release_manifest(sbom)
    outputs = {
        ROOT / "SBOM.spdx.json": serialized(sbom),
        ROOT / "RELEASE_MANIFEST.json": serialized(release),
    }
    if args.check:
        bad = [path.name for path, content in outputs.items() if not path.is_file() or path.read_text() != content]
        if bad:
            print("release metadata drift: " + ", ".join(bad))
            return 1
        print(f"release metadata PASS: {len(sbom['files'])} SPDX source files")
        return 0
    for path, content in outputs.items():
        path.write_text(content)
    manifest_hash = digest(ROOT / "RELEASE_MANIFEST.json", "sha256")
    (ROOT / "RELEASE_MANIFEST_SHA256.txt").write_text(f"{manifest_hash}  RELEASE_MANIFEST.json\n")
    print(f"wrote {VERSION} release metadata: {len(sbom['files'])} SPDX source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
