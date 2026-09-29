import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def _load_runner():
    path = ROOT / "qualification/r67_runner.py"
    spec = importlib.util.spec_from_file_location("r67_runner_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_r67_release_identity_feature_freeze_and_no_mc12_contract():
    spec = (ROOT / "packaging/netconfig.spec").read_text()
    roadmap = (ROOT / "ROADMAP.md").read_text()
    assert "Release:        67.2%{?dist}" in spec
    assert "R67" in roadmap and "feature freeze" in roadmap.lower()
    assert "mc11-topology-change-planning-1" in roadmap
    assert "do not create mc-12" in roadmap.lower()
    assert "R68" in roadmap


def test_r67_runner_contract_has_fixed_live_matrix_and_no_shell_true():
    source = (ROOT / "qualification/r67_runner.py").read_text()
    mod = _load_runner()
    live = [g for g in mod.GATES if g.evidence_class == "LIVE_RC"]
    assert len(live) == 12
    assert len({g.gate_id for g in live}) == 12
    assert len({g.hook_name for g in live}) == 12
    assert "shell=True" not in source
    assert "NETCONFIG_R67_LIVE_RC" in source
    assert "selected_live_ids == required_live_ids" in source
    assert "production_release_claim\": False" in source


def test_r67_local_baseline_never_claims_rc_or_production_release(tmp_path):
    out = tmp_path / "evidence"
    cp = subprocess.run(
        [sys.executable, str(ROOT / "qualification/r67_runner.py"), "--output-dir", str(out),
         "--include-local", "--gate", "R67-BASE-001"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 1, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["product_baseline"] == "2.0.0-67"
    assert campaign["gates"][0]["status"] == "FAIL"
    assert campaign["release_candidate_qualified"] is False
    assert campaign["production_release_claim"] is False
    assert campaign["all_required_live_rc_gates_selected"] is False
    assert campaign["live_rc_pass_count"] == 0
    assert campaign["release_promotion_performed"] is False


def test_r67_live_gate_without_independent_environment_is_blocked(tmp_path):
    out = tmp_path / "live"
    cp = subprocess.run(
        [sys.executable, str(ROOT / "qualification/r67_runner.py"), "--output-dir", str(out),
         "--live", "--gate", "R67-RC-012"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["gates"][0]["status"] in {"BLOCKED_ENVIRONMENT", "NOT_RUN"}
    assert campaign["release_candidate_qualified"] is False
    assert campaign["production_release_claim"] is False


def test_r67_release_manifest_metadata_is_current_and_feature_frozen():
    manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    assert manifest["current_package"] == "2.0.0-67.2"
    assert manifest["current_release"] == "67.2"
    assert manifest["current_slice"] == "R67.2 Fresh Database Bootstrap Hardening Corrective RC"
    assert manifest["schema_revision"] == "mc11-topology-change-planning-1"
    assert manifest["feature_freeze"] is True
    assert manifest["mc12_defined"] is False
    assert manifest["release_promotion"] == "NOT_PERFORMED"
    assert manifest["production_release_claim"] is False
    assert manifest["release_candidate_policy"]["changes_invalidate_prior_rc_evidence"] is True


def test_r67_spdx_sbom_is_current_bounded_and_checksummed():
    sbom = json.loads((ROOT / "SBOM.spdx.json").read_text())
    assert sbom["spdxVersion"] == "SPDX-2.3"
    assert sbom["name"] == "NetConfig 2.0.0-67.2 source SBOM"
    package = sbom["packages"][0]
    assert package["versionInfo"] == "2.0.0-67.2"
    assert package["filesAnalyzed"] is True
    assert len(sbom["files"]) >= 300
    assert all(len(item.get("checksums", [])) == 2 for item in sbom["files"])
    assert all(not item["fileName"].endswith((".key", ".pem", ".sqlite", ".db")) for item in sbom["files"])


def test_r67_release_metadata_generator_detects_drift():
    cp = subprocess.run(
        [sys.executable, str(ROOT / "tools/release_metadata.py"), "--check"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    assert "release metadata PASS" in cp.stdout


def test_r67_ci_contract_uses_current_rpm_and_includes_rc_tools():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "netconfig-2.0.0-42.el10.noarch.rpm" not in workflow
    assert "netconfig-2.0.0-67*.noarch.rpm" in workflow
    for relative in (
        "packaging/r67-qualify.sh", "qualification/r67_runner.py", "tools/release_metadata.py",
    ):
        assert relative in workflow
        assert (ROOT / relative).stat().st_mode & 0o777 == 0o755


def test_r67_installer_and_almalinux_qualifier_require_release67_rpm():
    installer = (ROOT / "packaging/install-rpm.sh").read_text()
    alma = (ROOT / "packaging/q1-qualify-almalinux.sh").read_text()
    assert '${RELEASE%%.*} != "67"' in installer
    assert "expected NetConfig RPM release 67" in installer
    assert "netconfig-2.0.0-67.2.el10.noarch.rpm" in installer
    assert "2.0.0-67.*.noarch" in alma


def test_r67_candidate_fingerprint_is_nonempty_and_named():
    fp = _load_runner().candidate_fingerprint()
    assert fp["kind"] in {"PRE_FREEZE_CRITICAL_METADATA_SHA256", "R67_SOURCE_MANIFEST_SHA256"}
    assert len(fp["sha256"]) == 64
    int(fp["sha256"], 16)


def test_r67_r66_manifest_drift_defect_is_closed():
    release = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    artifact = json.loads((ROOT / "ARTIFACT_MANIFEST.json").read_text())
    assert release["current_package"] == "2.0.0-67.2"
    # ARTIFACT_MANIFEST is finalized during packaging; it must never be mistaken
    # for the authoritative current release metadata before the final freeze.
    assert artifact.get("version") in {"2.0.0-67", "2.0.0-67.1", "2.0.0-67.2"}
    assert release["current_package"] != "2.0.0-65"
