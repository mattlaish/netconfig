"""
vault.py -- Encrypted credential store, pure stdlib.

Master password -> PBKDF2-HMAC-SHA256 -> 32-byte key -> ChaCha20-Poly1305 over
the JSON credential blob. The file on disk is:

    magic(4) | version(1) | kdf_iters(4, BE) | salt(16) | nonce(12) | ciphertext+tag

Design notes / honest limits:
  * This protects credentials AT REST. Once unlocked in a running process the
    plaintext secrets live in memory; that's unavoidable for a tool that has to
    hand a password to ssh. Prefer SSH key auth where the device supports it.
  * There is no key escrow / backdoor by design (consistent with VaultGate).
    Lose the master password and the store is gone. That is the intended property.
  * KDF iteration count is stored in the header so it can be raised later without
    breaking existing vaults.
"""

import json
import os
import hashlib
import struct

from . import aead

_MAGIC = b"NCV1"
_VERSION = 1
_DEFAULT_ITERS = 600_000  # OWASP-ish floor for PBKDF2-HMAC-SHA256 (2024)


def _derive(password, salt, iters):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, dklen=32)


class Vault:
    def __init__(self, path):
        self.path = path
        self._data = {"secrets": {}}
        self._key = None
        self._mtime = None
        self._iters = _DEFAULT_ITERS

    # ---- lifecycle -------------------------------------------------------
    def exists(self):
        return os.path.exists(self.path)

    def create(self, master_password, iters=_DEFAULT_ITERS):
        if self.exists():
            raise FileExistsError(self.path)
        salt = os.urandom(16)
        self._iters = iters
        self._key = _derive(master_password, salt, iters)
        self._salt = salt
        self._data = {"secrets": {}}
        self._flush()

    def unlock(self, master_password):
        with open(self.path, "rb") as f:
            blob = f.read()
        if blob[:4] != _MAGIC:
            raise ValueError("not a netconfig vault")
        ver = blob[4]
        if ver != _VERSION:
            raise ValueError(f"unsupported vault version {ver}")
        iters = struct.unpack(">I", blob[5:9])[0]
        salt = blob[9:25]
        nonce = blob[25:37]
        ct = blob[37:]
        key = _derive(master_password, salt, iters)
        try:
            pt = aead.decrypt(key, nonce, ct, aad=_MAGIC)
        except ValueError:
            raise ValueError("wrong master password or corrupt vault")
        self._data = json.loads(pt.decode("utf-8"))
        self._key = key
        self._salt = salt
        self._iters = iters
        try:
            self._mtime = os.path.getmtime(self.path)
        except OSError:
            self._mtime = None

    def _reload_if_changed(self):
        """If another process (e.g. the CLI) has written the vault since we last
        read it, re-decrypt so a running console sees the change. Same-salt writes
        (the normal case) decrypt with our existing key; a master rotated elsewhere
        won't decrypt and we keep our current view."""
        if self._key is None:
            return
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return
        if self._mtime is not None and mtime <= self._mtime:
            return
        try:
            with open(self.path, "rb") as f:
                blob = f.read()
            if blob[:4] != _MAGIC:
                return
            nonce = blob[25:37]
            ct = blob[37:]
            pt = aead.decrypt(self._key, nonce, ct, aad=_MAGIC)
            self._data = json.loads(pt.decode("utf-8"))
            self._mtime = mtime
        except Exception:
            pass  # mid-write or key mismatch; keep current view

    def _flush(self):
        if self._key is None:
            raise RuntimeError("vault locked")
        pt = json.dumps(self._data, separators=(",", ":")).encode("utf-8")
        nonce = aead.random_nonce()
        ct = aead.encrypt(self._key, nonce, pt, aad=_MAGIC)
        header = _MAGIC + bytes([_VERSION]) + struct.pack(">I", self._iters) + self._salt + nonce
        tmp = self.path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(header + ct)
        os.replace(tmp, self.path)  # atomic
        try:
            self._mtime = os.path.getmtime(self.path)
        except OSError:
            self._mtime = None
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    # ---- secret CRUD -----------------------------------------------------
    def set_secret(self, name, **fields):
        """Store a named credential. fields may include: username, password,
        enable_password, key_path, key_passphrase."""
        self._reload_if_changed()
        self._data["secrets"][name] = {k: v for k, v in fields.items() if v is not None}
        self._flush()

    def get_secret(self, name):
        self._reload_if_changed()
        if name not in self._data["secrets"]:
            raise KeyError(name)
        return dict(self._data["secrets"][name])

    def delete_secret(self, name):
        self._reload_if_changed()
        self._data["secrets"].pop(name, None)
        self._flush()

    def list_secrets(self):
        self._reload_if_changed()
        # Never returns secret material -- just names + which fields are present.
        out = {}
        for name, fields in self._data["secrets"].items():
            out[name] = sorted(fields.keys())
        return out

    def change_master(self, new_password, iters=None):
        if self._key is None:
            raise RuntimeError("vault locked")
        self._salt = os.urandom(16)
        if iters:
            self._iters = iters
        self._key = _derive(new_password, self._salt, self._iters)
        self._flush()
