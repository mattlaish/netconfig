"""Evidence-manifest signing and verification for D.5 Phase 4D.

The implementation intentionally keeps private signing keys outside NetConfig's
SQLite database, settings JSON, diagnostic archives, and source tree.  A key is
resolved from a systemd credential directory first, then from the explicit
``NETCONFIG_EVIDENCE_SIGNING_KEY_FILE`` environment variable.

Only Ed25519 private keys are accepted.  OpenSSL is invoked with fixed argument
vectors (never through a shell) so this remains dependency-light without
exposing a generic command-execution surface.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

SIGNATURE_FILE = "manifest.signature.json"
PUBLIC_KEY_FILE = "manifest.public.pem"
MANIFEST_FILE = "manifest.json"
MANIFEST_SHA_FILE = "manifest.sha256"
SIGNATURE_SCHEMA = "netconfig-evidence-signature-v1"
ALGORITHM = "Ed25519"
MAX_KEY_BYTES = 64 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 8192
MAX_MANIFEST_ENTRIES = 4096
MAX_VERIFIED_PAYLOAD_BYTES = 1024 * 1024 * 1024


class EvidenceSigningError(ValueError):
    """Raised when signing or signature verification cannot be completed safely."""


def _openssl_path() -> str:
    path = shutil.which("openssl")
    if not path:
        raise EvidenceSigningError("OpenSSL executable not found")
    return path


def _run_openssl(args, *, input_data=None) -> subprocess.CompletedProcess:
    cmd = [_openssl_path(), *args]
    try:
        return subprocess.run(
            cmd,
            input=input_data,
            stdin=subprocess.DEVNULL if input_data is None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
        if detail:
            detail = ": " + detail[:500]
        raise EvidenceSigningError(f"OpenSSL operation failed{detail}") from exc


def _normalize_fingerprint(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.lower().startswith("sha256:"):
        raw = raw.split(":", 1)[1]
    raw = raw.replace(":", "").strip().lower()
    if len(raw) != 64 or any(ch not in "0123456789abcdef" for ch in raw):
        raise EvidenceSigningError("trusted fingerprint must be a SHA-256 hex digest")
    return "SHA256:" + raw


def _public_key_fingerprint(public_pem: bytes) -> str:
    der = _run_openssl(["pkey", "-pubin", "-outform", "DER"], input_data=public_pem).stdout
    return "SHA256:" + hashlib.sha256(der).hexdigest()


def _assert_ed25519_public_key(public_pem: bytes) -> None:
    text = _run_openssl(["pkey", "-pubin", "-text", "-noout"], input_data=public_pem).stdout
    if b"ED25519" not in text.upper():
        raise EvidenceSigningError("evidence signing key must be Ed25519")


def _resolve_private_key_path(explicit=None) -> Path | None:
    if explicit:
        return Path(explicit)
    credential_dir = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
    if credential_dir:
        candidate = Path(credential_dir) / "evidence-signing-key.pem"
        if candidate.is_file():
            return candidate
    env_path = os.environ.get("NETCONFIG_EVIDENCE_SIGNING_KEY_FILE", "").strip()
    if env_path:
        return Path(env_path)
    return None


def _validate_private_key_path(path: Path) -> None:
    try:
        st = path.lstat()
    except OSError as exc:
        raise EvidenceSigningError("evidence signing private key is not readable") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise EvidenceSigningError("evidence signing private key must be a regular non-symlink file")
    if st.st_size <= 0 or st.st_size > MAX_KEY_BYTES:
        raise EvidenceSigningError("evidence signing private key has an invalid size")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise EvidenceSigningError("evidence signing private key must not be group/world accessible")



def signing_required(settings=None) -> bool:
    raw = os.environ.get("NETCONFIG_EVIDENCE_SIGNING_REQUIRED")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() in {"1", "true", "yes", "on", "required"}
    return bool((settings or {}).get("evidence_signing_required", False))

def configured_trusted_fingerprints(settings=None, extra=None) -> set[str]:
    values = []
    if settings:
        configured = settings.get("evidence_trusted_fingerprints", [])
        if isinstance(configured, str):
            values.extend(x for x in configured.split(",") if x.strip())
        elif isinstance(configured, (list, tuple, set)):
            values.extend(configured)
    env_values = os.environ.get("NETCONFIG_EVIDENCE_TRUSTED_FINGERPRINTS", "")
    if env_values:
        values.extend(x for x in env_values.split(",") if x.strip())
    if extra:
        if isinstance(extra, str):
            values.append(extra)
        else:
            values.extend(extra)
    result = set()
    for value in values:
        result.add(_normalize_fingerprint(value))
    return result


class EvidenceSigner:
    """Fixed-function Ed25519 signer backed by an external PEM private key."""

    def __init__(self, private_key_path=None):
        self.private_key_path = _resolve_private_key_path(private_key_path)
        self._identity = None

    @property
    def available(self) -> bool:
        return self.private_key_path is not None

    def identity(self) -> dict:
        if not self.available:
            raise EvidenceSigningError("no evidence signing key is configured")
        if self._identity is not None:
            return dict(self._identity)
        _validate_private_key_path(self.private_key_path)
        public_pem = _run_openssl(
            ["pkey", "-in", str(self.private_key_path), "-pubout"]
        ).stdout
        _assert_ed25519_public_key(public_pem)
        fingerprint = _public_key_fingerprint(public_pem)
        self._identity = {
            "algorithm": ALGORITHM,
            "key_fingerprint": fingerprint,
            "public_key_pem": public_pem,
        }
        return dict(self._identity)

    def sign_manifest(self, manifest_path, root_dir) -> dict:
        identity = self.identity()
        manifest_path = Path(manifest_path)
        root = Path(root_dir)
        raw = manifest_path.read_bytes()
        if not raw or len(raw) > MAX_MANIFEST_BYTES:
            raise EvidenceSigningError("manifest size is outside the signing limit")
        signature = _run_openssl(
            ["pkeyutl", "-sign", "-rawin", "-inkey", str(self.private_key_path),
             "-in", str(manifest_path)]
        ).stdout
        if not signature:
            raise EvidenceSigningError("OpenSSL returned an empty signature")
        public_path = root / PUBLIC_KEY_FILE
        public_path.write_bytes(identity["public_key_pem"])
        metadata = {
            "schema": SIGNATURE_SCHEMA,
            "algorithm": ALGORITHM,
            "key_fingerprint": identity["key_fingerprint"],
            "signed_file": MANIFEST_FILE,
            "signed_sha256": hashlib.sha256(raw).hexdigest(),
            "signature_base64": base64.b64encode(signature).decode("ascii"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "trust_model": (
                "embedded public key proves signature validity only; authenticity requires an "
                "independently trusted key fingerprint"
            ),
        }
        signature_path = root / SIGNATURE_FILE
        signature_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            public_path.chmod(0o644)
            signature_path.chmod(0o644)
        except OSError:
            pass
        return {k: v for k, v in metadata.items() if k != "signature_base64"}


def _safe_member_path(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or ".." in p.parts or "" in p.parts:
        raise EvidenceSigningError("unsafe path in evidence archive")
    return p


def _read_member_bytes(tar: tarfile.TarFile, member: tarfile.TarInfo, limit: int) -> bytes:
    if member.size < 0 or member.size > limit:
        raise EvidenceSigningError("evidence archive member exceeds verification size limit")
    fh = tar.extractfile(member)
    if fh is None:
        raise EvidenceSigningError("evidence archive member could not be read")
    data = fh.read(limit + 1)
    if len(data) > limit:
        raise EvidenceSigningError("evidence archive member exceeds verification size limit")
    return data


def _hash_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> tuple[str, int]:
    fh = tar.extractfile(member)
    if fh is None:
        raise EvidenceSigningError("evidence archive payload could not be read")
    h = hashlib.sha256()
    total = 0
    while True:
        chunk = fh.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        h.update(chunk)
    return h.hexdigest(), total


def _verify_signature_bytes(manifest: bytes, signature: bytes, public_pem: bytes) -> None:
    _assert_ed25519_public_key(public_pem)
    with tempfile.TemporaryDirectory(prefix="netconfig-evidence-verify-") as td:
        td = Path(td)
        manifest_path = td / "manifest.json"
        sig_path = td / "manifest.sig"
        pub_path = td / "public.pem"
        manifest_path.write_bytes(manifest)
        sig_path.write_bytes(signature)
        pub_path.write_bytes(public_pem)
        _run_openssl([
            "pkeyutl", "-verify", "-rawin", "-pubin", "-inkey", str(pub_path),
            "-in", str(manifest_path), "-sigfile", str(sig_path),
        ])


def verify_signed_archive(archive_path, trusted_fingerprints=None) -> dict:
    """Verify archive structure, payload hashes, signature and optional trust pin.

    The archive is never extracted.  A valid signature from an embedded public key
    proves integrity; ``trusted=True`` additionally requires the embedded key's
    SHA-256 SPKI fingerprint to match an independent configured/provided pin.
    """
    archive = Path(archive_path)
    if not archive.is_file():
        raise EvidenceSigningError("evidence archive not found")
    trusted = configured_trusted_fingerprints(extra=trusted_fingerprints)

    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        if not members:
            raise EvidenceSigningError("empty evidence archive")
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise EvidenceSigningError("evidence archive has too many members")
        files = {}
        roots = set()
        for member in members:
            p = _safe_member_path(member.name)
            roots.add(p.parts[0])
            if member.issym() or member.islnk() or member.isdev():
                raise EvidenceSigningError("links/devices are not allowed in evidence archives")
            if member.isfile():
                key = str(p)
                if key in files:
                    raise EvidenceSigningError("duplicate file path in evidence archive")
                files[key] = member
        if len(roots) != 1:
            raise EvidenceSigningError("evidence archive must have one top-level directory")
        root = next(iter(roots))
        required = {
            f"{root}/{MANIFEST_FILE}",
            f"{root}/{MANIFEST_SHA_FILE}",
            f"{root}/{SIGNATURE_FILE}",
            f"{root}/{PUBLIC_KEY_FILE}",
        }
        missing = required - set(files)
        if missing:
            raise EvidenceSigningError("signed evidence archive is missing signature metadata")

        manifest_raw = _read_member_bytes(tar, files[f"{root}/{MANIFEST_FILE}"], MAX_MANIFEST_BYTES)
        sha_raw = _read_member_bytes(tar, files[f"{root}/{MANIFEST_SHA_FILE}"], 4096)
        signature_raw = _read_member_bytes(tar, files[f"{root}/{SIGNATURE_FILE}"], 128 * 1024)
        public_pem = _read_member_bytes(tar, files[f"{root}/{PUBLIC_KEY_FILE}"], MAX_KEY_BYTES)

        try:
            manifest = json.loads(manifest_raw)
            metadata = json.loads(signature_raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceSigningError("invalid signed evidence metadata") from exc
        if metadata.get("schema") != SIGNATURE_SCHEMA or metadata.get("algorithm") != ALGORITHM:
            raise EvidenceSigningError("unsupported evidence signature metadata")
        if metadata.get("signed_file") != MANIFEST_FILE:
            raise EvidenceSigningError("signature does not target manifest.json")

        manifest_digest = hashlib.sha256(manifest_raw).hexdigest()
        if metadata.get("signed_sha256") != manifest_digest:
            raise EvidenceSigningError("signed manifest digest mismatch")
        expected_sha_line = f"{manifest_digest}  manifest.json"
        if sha_raw.decode("ascii", "replace").strip() != expected_sha_line:
            raise EvidenceSigningError("manifest.sha256 mismatch")

        fingerprint = _public_key_fingerprint(public_pem)
        if metadata.get("key_fingerprint") != fingerprint:
            raise EvidenceSigningError("embedded public key fingerprint mismatch")
        try:
            signature = base64.b64decode(metadata.get("signature_base64", ""), validate=True)
        except (ValueError, TypeError) as exc:
            raise EvidenceSigningError("invalid evidence signature encoding") from exc
        if not signature:
            raise EvidenceSigningError("empty evidence signature")
        _verify_signature_bytes(manifest_raw, signature, public_pem)

        manifest_files = manifest.get("files")
        if not isinstance(manifest_files, list):
            raise EvidenceSigningError("manifest files list is invalid")
        if len(manifest_files) > MAX_MANIFEST_ENTRIES:
            raise EvidenceSigningError("manifest has too many file entries")
        expected_payload = set()
        verified_payload_bytes = 0
        for row in manifest_files:
            if not isinstance(row, dict):
                raise EvidenceSigningError("manifest file entry is invalid")
            rel = str(row.get("path") or "")
            rel_path = _safe_member_path(rel)
            if len(rel_path.parts) and rel_path.parts[0] == root:
                raise EvidenceSigningError("manifest paths must be relative to archive root")
            full = f"{root}/{rel}"
            if full in expected_payload:
                raise EvidenceSigningError("duplicate manifest file entry")
            expected_payload.add(full)
            member = files.get(full)
            if not member:
                raise EvidenceSigningError(f"manifest payload missing: {rel}")
            verified_payload_bytes += max(0, member.size)
            if verified_payload_bytes > MAX_VERIFIED_PAYLOAD_BYTES:
                raise EvidenceSigningError("verified evidence payload exceeds byte budget")
            digest, size = _hash_member(tar, member)
            if digest != row.get("sha256") or size != int(row.get("size", -1)):
                raise EvidenceSigningError(f"manifest payload mismatch: {rel}")

        allowed = expected_payload | required
        extras = set(files) - allowed
        if extras:
            raise EvidenceSigningError("signed evidence archive contains unmanifested files")

        return {
            "signed": True,
            "signature_valid": True,
            "algorithm": ALGORITHM,
            "key_fingerprint": fingerprint,
            "trusted": fingerprint in trusted if trusted else False,
            "trust_pins_supplied": bool(trusted),
            "manifest_sha256": manifest_digest,
            "payload_files": len(expected_payload),
        }


def signing_status(settings=None) -> dict:
    signer = EvidenceSigner()
    trusted = configured_trusted_fingerprints(settings=settings)
    result = {
        "configured": signer.available,
        "algorithm": ALGORITHM,
        "trusted_fingerprints": sorted(trusted),
        "required": signing_required(settings),
    }
    if signer.available:
        try:
            identity = signer.identity()
            result["key_fingerprint"] = identity["key_fingerprint"]
            result["ready"] = True
        except EvidenceSigningError as exc:
            result["ready"] = False
            result["error"] = str(exc)
    else:
        result["ready"] = False
    return result
