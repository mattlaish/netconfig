#!/usr/bin/env python3
"""Generate/check deterministic R67.2 corrective-RC release metadata and SPDX 2.3 source SBOM."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = "67.2"
VERSION = "2.0.0-67.2"
SCHEMA = "mc11-topology-change-planning-1"
EXCLUDE_NAMES = {
    "SBOM.spdx.json", "RELEASE_MANIFEST.json", "RELEASE_MANIFEST_SHA256.txt",
    "R67_SOURCE_MANIFEST.json", "R67_2_SOURCE_MANIFEST.json", "SHA256SUMS", "ARTIFACT_MANIFEST.json",
}
EXCLUDE_PARTS = {".git", ".pytest_cache", ".mypy_cache", "__pycache__", "dist", "build", "RPMS", "SRPMS", "SOURCES", "SPECS", "BUILD", "BUILDROOT"}


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_files():
    result = []
    for path in sorted(ROOT.rglob("*")):
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
        "current_slice": "R67.2 Fresh Database Bootstrap Hardening Corrective RC",
        "base_track": "R67.2 corrective RC on frozen R67",
        "status": "IMPLEMENTED_TESTING_DEFERRED",
        "schema_revision": SCHEMA,
        "feature_freeze": True,
        "mc12_defined": False,
        "monitoring_correlation_lineage": "CLOSED at R59/MC-11; do not create MC-12",
        "authority_boundary": "R67.2 repairs fresh login, additive schema/index ordering, fail-closed Core PostgreSQL preflight, Core/History PostgreSQL separation, and fresh PostgreSQL bootstrap; network mutation authority is unchanged and remains exclusively approval-gated.",
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
            "source_tree": "548 collected / 534 passed / 14 skipped / 0 failed (12 bounded groups)",
            "r67_2_focused": "9/9 PASS",
            "mc11_focused": "12/12 PASS",
            "transition_focused": "71/71 PASS",
            "single_process_full_pytest": "TIMED_OUT around 37 percent with no failure output; not counted as PASS",
            "initial_campaign": "external candidate-bound evidence; not embedded in source metadata",
            "release_candidate_qualified": False,
            "production_release_claim": False,
        },
        "offline_rpm": {
            "artifact": "netconfig-2.0.0-67.2.el10.noarch.rpm",
            "boundary": "offline helper RPM; not live AlmaLinux/rpmbuild/systemd/SELinux qualification",
            "deterministic_rebuild": "PASS",
            "independent_verifier": "PASS",
            "payload_files": 106,
            "payload_size": 1966675,
            "payload_sha256": "a2bcab1a23a90eaf9bd27a13f4b88cdfeab4669010b2f1d98a97a2a148fd026e",
            "sha256": "289caa0e57137ed3c2e5a3a3fb55b197c3c58d8094b682c4b5e5f6861ecbb118",
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
        "next_track": "R68 v2 Production Release Decision rerun after R67.2 live qualification",
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
    print(f"wrote R67.2 release metadata: {len(sbom['files'])} SPDX source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
