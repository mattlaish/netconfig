import io
import json
import shutil
import sqlite3
import subprocess
import tarfile
from pathlib import Path

import pytest

from netconfig.db import Database
from netconfig.debug import DebugBundle
from netconfig.evidence_signing import (
    EvidenceSigner,
    EvidenceSigningError,
    verify_signed_archive,
)
from netconfig.manager import Manager


pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL is required")


def _ed25519_key(path: Path) -> Path:
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    path.chmod(0o600)
    return path


def _clear_signing_env(monkeypatch):
    monkeypatch.delenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", raising=False)
    monkeypatch.delenv("NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS", raising=False)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)


def _rewrite_tar(source: Path, destination: Path, mutate_name: str, replacement: bytes):
    with tarfile.open(source, "r:gz") as src, tarfile.open(destination, "w:gz") as dst:
        for member in src.getmembers():
            if member.isfile():
                fh = src.extractfile(member)
                data = fh.read() if fh else b""
                if member.name.endswith("/" + mutate_name):
                    data = replacement
                    member.size = len(data)
                dst.addfile(member, io.BytesIO(data))
            else:
                dst.addfile(member)


def test_phase4d_external_ed25519_case_signing_and_trust_pin(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    key = _ed25519_key(tmp_path / "evidence.pem")
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(key))

    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("signed case", created_by="alice")
    record = manager.case_exports.export_case(
        incident["incident_key"], "alice", require_signature=True)

    assert record["signature_state"] == "SIGNED"
    assert record["signature_algorithm"] == "Ed25519"
    assert record["signer_fingerprint"].startswith("SHA256:")

    result = manager.case_exports.verify_signature(
        incident["incident_key"], record["export_key"],
        [record["signer_fingerprint"]], actor="alice")
    assert result["signed"] is True
    assert result["signature_valid"] is True
    assert result["trusted"] is True
    assert result["key_fingerprint"] == record["signer_fingerprint"]

    _, archive = manager.case_exports.get_export(incident["incident_key"], record["export_key"])
    with tarfile.open(archive, "r:gz") as tar:
        names = {Path(m.name).name for m in tar.getmembers() if m.isfile()}
        assert {"manifest.json", "manifest.sha256", "manifest.signature.json", "manifest.public.pem"} <= names
        assert key.name not in names
    assert any(row["action"] == "incident_case_export_verify" for row in manager.db.recent_audit(50))
    manager.db.close()


def test_phase4d_trust_pin_mismatch_fails_case_verification(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    key = _ed25519_key(tmp_path / "evidence.pem")
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(key))
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("trust mismatch", created_by="alice")
    record = manager.case_exports.export_case(incident["incident_key"], "alice")
    with pytest.raises(ValueError, match="not trusted"):
        manager.case_exports.verify_signature(
            incident["incident_key"], record["export_key"], ["SHA256:" + "0" * 64])
    manager.db.close()


def test_phase4d_signed_archive_detects_manifest_and_payload_tamper(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    key = _ed25519_key(tmp_path / "evidence.pem")
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(key))
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("tamper", created_by="alice")
    record = manager.case_exports.export_case(incident["incident_key"], "alice")
    _, archive = manager.case_exports.get_export(incident["incident_key"], record["export_key"])

    manifest_tampered = tmp_path / "manifest-tampered.tar.gz"
    _rewrite_tar(archive, manifest_tampered, "manifest.json", b'{"files": []}\n')
    with pytest.raises(EvidenceSigningError):
        verify_signed_archive(manifest_tampered, [record["signer_fingerprint"]])

    payload_tampered = tmp_path / "payload-tampered.tar.gz"
    _rewrite_tar(archive, payload_tampered, "case.json", b'{"tampered": true}\n')
    with pytest.raises(EvidenceSigningError, match="payload mismatch"):
        verify_signed_archive(payload_tampered, [record["signer_fingerprint"]])
    manager.db.close()


def test_phase4d_debug_bundle_is_signed_and_verifiable(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    key = _ed25519_key(tmp_path / "evidence.pem")
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(key))
    manager = Manager(str(tmp_path / "home"))
    dbg = DebugBundle(manager)
    bundle = dbg.collect(require_signature=True)
    fingerprint = EvidenceSigner().identity()["key_fingerprint"]
    result = dbg.verify_bundle(bundle.name, [fingerprint])
    assert result["signature_valid"] is True
    assert result["trusted"] is True
    manager.db.close()


def test_phase4d_unsigned_compatibility_and_required_policy(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    manager = Manager(str(tmp_path / "home"))
    incident = manager.incidents.create("unsigned compatibility", created_by="alice")
    record = manager.case_exports.export_case(incident["incident_key"], "alice")
    assert record["signature_state"] == "UNSIGNED"
    result = manager.case_exports.verify_signature(incident["incident_key"], record["export_key"])
    assert result == {"signed": False, "signature_valid": False, "trusted": False}
    with pytest.raises(EvidenceSigningError, match="required"):
        manager.case_exports.export_case(
            incident["incident_key"], "alice", require_signature=True)
    with pytest.raises(EvidenceSigningError, match="required"):
        DebugBundle(manager).collect(require_signature=True)
    manager.db.close()


def test_phase4d_insecure_or_wrong_key_fails_closed(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    insecure = _ed25519_key(tmp_path / "insecure.pem")
    insecure.chmod(0o644)
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(insecure))
    with pytest.raises(EvidenceSigningError, match="group/world"):
        EvidenceSigner().identity()

    rsa = tmp_path / "rsa.pem"
    subprocess.run(
        ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(rsa)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rsa.chmod(0o600)
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(rsa))
    with pytest.raises(EvidenceSigningError, match="Ed25519"):
        EvidenceSigner().identity()


def test_phase4d_systemd_credential_precedes_environment_key(tmp_path, monkeypatch):
    _clear_signing_env(monkeypatch)
    credential_dir = tmp_path / "creds"
    credential_dir.mkdir()
    preferred = _ed25519_key(credential_dir / "evidence-signing-key.pem")
    fallback = _ed25519_key(tmp_path / "fallback.pem")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(credential_dir))
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(fallback))
    actual = EvidenceSigner().identity()["key_fingerprint"]
    expected = EvidenceSigner(preferred).identity()["key_fingerprint"]
    assert actual == expected


def test_phase4d_case_export_schema_migrates_existing_table(tmp_path):
    path = tmp_path / "legacy.db"
    raw = sqlite3.connect(path)
    raw.execute("PRAGMA foreign_keys=OFF")
    raw.execute("CREATE TABLE incidents(id INTEGER PRIMARY KEY, incident_key TEXT UNIQUE, title TEXT, description TEXT DEFAULT '', severity TEXT DEFAULT 'MEDIUM', status TEXT DEFAULT 'OPEN', tags TEXT DEFAULT '[]', created_by TEXT DEFAULT '', created_ts REAL, updated_by TEXT DEFAULT '', updated_ts REAL, closed_by TEXT, closed_ts REAL)")
    raw.execute("CREATE TABLE incident_case_exports(id INTEGER PRIMARY KEY AUTOINCREMENT, incident_id INTEGER NOT NULL, export_key TEXT UNIQUE, filename TEXT UNIQUE, created_by TEXT DEFAULT '', created_ts REAL, reason TEXT DEFAULT '', bundle_names TEXT DEFAULT '[]', missing_bundles TEXT DEFAULT '[]', bundle_count INTEGER DEFAULT 0, size INTEGER DEFAULT 0, sha256 TEXT DEFAULT '')")
    raw.commit(); raw.close()

    db = Database(str(path))
    cols = {row["name"] for row in db.conn.execute("PRAGMA table_info(incident_case_exports)").fetchall()}
    assert {"signature_state", "signature_algorithm", "signer_fingerprint"} <= cols
    db.close()


def test_phase4d_case_verify_api_and_signed_download(tmp_path, monkeypatch):
    import http.client
    import threading

    from netconfig.apitokens import ApiTokens
    from netconfig.web import Console, _Server

    _clear_signing_env(monkeypatch)
    key = _ed25519_key(tmp_path / "evidence.pem")
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(key))
    manager = Manager(str(tmp_path / "home"))
    fingerprint = EvidenceSigner().identity()["key_fingerprint"]
    manager.settings["evidence_trusted_fingerprints"] = [fingerprint]
    incident = manager.incidents.create("api signed case", created_by="alice")
    record = manager.case_exports.export_case(incident["incident_key"], "alice", require_signature=True)

    tokens = ApiTokens(manager.db.conn)
    _, raw = tokens.create(
        "signing-api", ["incident:read", "incident:export"],
        created_by="admin", role="operator")

    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + raw}
    try:
        verify_path = f"/api/v1/incidents/{incident['incident_key']}/exports/{record['export_key']}/verify"
        conn.request("GET", verify_path, headers=headers)
        response = conn.getresponse(); payload = json.loads(response.read())
        assert response.status == 200
        assert payload["signature_valid"] is True and payload["trusted"] is True

        download_path = f"/api/v1/incidents/{incident['incident_key']}/exports/{record['export_key']}"
        conn.request("GET", download_path, headers=headers)
        response = conn.getresponse(); body = response.read()
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/gzip"
        assert len(body) > 0
    finally:
        conn.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        manager.db.close()


def test_phase4d_debug_signing_status_and_verify_api(tmp_path, monkeypatch):
    import http.client
    import threading

    from netconfig.apitokens import ApiTokens
    from netconfig.web import Console, _Server

    _clear_signing_env(monkeypatch)
    key = _ed25519_key(tmp_path / "evidence.pem")
    monkeypatch.setenv("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", str(key))
    manager = Manager(str(tmp_path / "home"))
    fingerprint = EvidenceSigner().identity()["key_fingerprint"]
    manager.settings["evidence_trusted_fingerprints"] = [fingerprint]
    bundle = DebugBundle(manager).collect(require_signature=True)

    tokens = ApiTokens(manager.db.conn)
    _, raw = tokens.create("debug-signing", ["debug:read"], created_by="admin", role="viewer")
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    headers = {"Authorization": "Bearer " + raw}
    try:
        conn.request("GET", "/api/v1/debug/signing", headers=headers)
        response = conn.getresponse(); status = json.loads(response.read())
        assert response.status == 200
        assert status["ready"] is True
        assert status["key_fingerprint"] == fingerprint

        conn.request("GET", f"/api/v1/debug/bundles/{bundle.name}/verify", headers=headers)
        response = conn.getresponse(); result = json.loads(response.read())
        assert response.status == 200
        assert result["signature_valid"] is True
        assert result["trusted"] is True
    finally:
        conn.close()
        server.shutdown(); server.server_close(); thread.join(timeout=5)
        manager.db.close()
