"""
users.py -- Console user accounts and role-based access control.

Distinct from the credential vault. The vault holds *device* secrets and is
unlocked by an admin so the tool can talk to devices. This module holds *operator*
identities: who logs into the console, and what each is allowed to do. The change-
approval workflow needs this separation -- a junior who can submit but not approve,
a senior who can approve, an admin who runs the show.

Passwords: PBKDF2-HMAC-SHA256, per-user random salt, stored iteration count
(same primitive as the vault KDF and the suite's other tools). No plaintext, no
reversible storage.

Roles (least -> most privilege):
    viewer    - read-only: see devices, configs, diffs, reports, audit
    operator  - viewer + collect configs + author scripts + submit change requests
    approver  - operator + approve/reject requests + execute approved changes
    admin     - everything, including user management and unlocking the vault
"""

import hashlib
import os
import secrets
import time

_ITERS = 600_000
_ROLES = ("viewer", "operator", "approver", "admin")

# capability -> minimum roles that hold it
_CAPS = {
    "view":            {"viewer", "operator", "approver", "admin"},
    "collect":         {"operator", "approver", "admin"},
    "submit":          {"operator", "approver", "admin"},
    "author_scripts":  {"operator", "approver", "admin"},
    "approve":         {"approver", "admin"},
    "execute":         {"approver", "admin"},
    "remediate":       {"approver", "admin"},
    "manage_devices":  {"approver", "admin"},
    "unlock_vault":    {"approver", "admin"},
    "manage_users":    {"admin"},
    "settings":        {"admin"},
}


def can(role, capability):
    return role in _CAPS.get(capability, set())


def roles():
    return list(_ROLES)


def _hash(password, salt, iters=_ITERS):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, dklen=32)


class Users:
    def __init__(self, conn):
        self._conn = conn

    def count(self):
        return self._conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]

    def exists(self, username):
        return self.get(username) is not None

    def get(self, username):
        r = self._conn.execute(
            "SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(r) if r else None

    def all(self):
        rows = self._conn.execute(
            "SELECT username, role, fullname, disabled, created, last_login "
            "FROM users ORDER BY username").fetchall()
        return [dict(r) for r in rows]

    def create(self, username, password, role="viewer", fullname=""):
        if role not in _ROLES:
            raise ValueError(f"unknown role {role!r}; valid: {_ROLES}")
        if self.exists(username):
            raise ValueError(f"user {username!r} already exists")
        if not password:
            raise ValueError("password required")
        salt = os.urandom(16)
        self._conn.execute(
            "INSERT INTO users (username, pw_salt, pw_hash, iters, role, fullname, "
            "disabled, created) VALUES (?,?,?,?,?,?,0,?)",
            (username, salt, _hash(password, salt), _ITERS, role, fullname, time.time()))
        self._conn.commit()

    def set_password(self, username, password):
        u = self.get(username)
        if not u:
            raise ValueError("no such user")
        salt = os.urandom(16)
        self._conn.execute(
            "UPDATE users SET pw_salt=?, pw_hash=?, iters=? WHERE username=?",
            (salt, _hash(password, salt), _ITERS, username))
        self._conn.commit()

    def set_role(self, username, role):
        if role not in _ROLES:
            raise ValueError(f"unknown role {role!r}")
        self._conn.execute("UPDATE users SET role=? WHERE username=?", (role, username))
        self._conn.commit()

    def set_disabled(self, username, disabled):
        self._conn.execute("UPDATE users SET disabled=? WHERE username=?",
                           (int(bool(disabled)), username))
        self._conn.commit()

    def delete(self, username):
        self._conn.execute("DELETE FROM users WHERE username=?", (username,))
        self._conn.commit()

    def verify(self, username, password):
        """Return the user dict on success, else None. Constant-time compare."""
        u = self.get(username)
        if not u or u["disabled"]:
            # still burn some time to blunt user-enumeration timing
            _hash(password, b"0000000000000000")
            return None
        calc = _hash(password, u["pw_salt"], u["iters"])
        if secrets.compare_digest(calc, u["pw_hash"]):
            self._conn.execute("UPDATE users SET last_login=? WHERE username=?",
                               (time.time(), username))
            self._conn.commit()
            return u
        return None
