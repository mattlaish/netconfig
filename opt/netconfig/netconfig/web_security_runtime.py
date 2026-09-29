"""Bounded web-console session and request framing helpers.

R64 keeps these abuse-resistance primitives outside the main request router so
security controls do not reverse the PH-1 structural split of ``web.py``.
"""

import hashlib
import secrets
import threading
import time

SESSION_IDLE_SECONDS = 30 * 60
SESSION_ABSOLUTE_SECONDS = 12 * 60 * 60
MAX_CONSOLE_SESSIONS = 1024
MAX_SESSIONS_PER_USER = 8
MAX_FORM_BODY_BYTES = 1024 * 1024
MAX_MIB_UPLOAD_BODY_BYTES = 16 * 1024 * 1024
MAX_MIB_FILES_PER_REQUEST = 16
MAX_MULTIPART_PARTS = 64
MAX_MULTIPART_BOUNDARY_BYTES = 200

_SESSIONS = {}
_SESSIONS_LOCK = threading.RLock()


class RequestRejected(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = int(status)


def _auth_fingerprint(user):
    raw = user.get("pw_hash") if isinstance(user, dict) else None
    if raw is None:
        return ""
    if not isinstance(raw, (bytes, bytearray)):
        raw = str(raw).encode("utf-8", "replace")
    return hashlib.sha256(bytes(raw)).hexdigest()


def _managed_session_expired(sess, now):
    if "last_seen" not in sess or "absolute_expires" not in sess:
        return False
    return (
        float(sess.get("last_seen") or 0) + SESSION_IDLE_SECONDS < now
        or float(sess.get("absolute_expires") or 0) < now
    )


def create_managed_session(user, now=None):
    now = time.time() if now is None else float(now)
    token = secrets.token_urlsafe(32)
    username = str(user["username"])
    record = {
        "username": username,
        "role": user["role"],
        "csrf": secrets.token_urlsafe(24),
        "created": now,
        "last_seen": now,
        "absolute_expires": now + SESSION_ABSOLUTE_SECONDS,
        "auth_fingerprint": _auth_fingerprint(user),
    }
    with _SESSIONS_LOCK:
        for sid, item in list(_SESSIONS.items()):
            if _managed_session_expired(item, now):
                _SESSIONS.pop(sid, None)
        mine = sorted(
            (
                (sid, item)
                for sid, item in _SESSIONS.items()
                if item.get("username") == username and "last_seen" in item
            ),
            key=lambda pair: float(pair[1].get("created") or 0),
        )
        while len(mine) >= MAX_SESSIONS_PER_USER:
            sid, _item = mine.pop(0)
            _SESSIONS.pop(sid, None)
        managed = sorted(
            ((sid, item) for sid, item in _SESSIONS.items() if "last_seen" in item),
            key=lambda pair: float(pair[1].get("created") or 0),
        )
        while len(managed) >= MAX_CONSOLE_SESSIONS:
            sid, _item = managed.pop(0)
            _SESSIONS.pop(sid, None)
        _SESSIONS[token] = record
    return token, record


def session_for(handler):
    cookie = handler.headers.get("Cookie", "")
    for part in cookie.split(";"):
        if "=" not in part:
            continue
        key, token = part.strip().split("=", 1)
        if key != "ncsid":
            continue
        now = time.time()
        with _SESSIONS_LOCK:
            sess = _SESSIONS.get(token)
            if sess is None:
                return None, None
            if _managed_session_expired(sess, now):
                _SESSIONS.pop(token, None)
                return None, None
            if "last_seen" in sess:
                current = handler.manager.users.get(sess.get("username", ""))
                if not current or current.get("disabled"):
                    _SESSIONS.pop(token, None)
                    return None, None
                expected = sess.get("auth_fingerprint") or ""
                actual = _auth_fingerprint(current)
                if expected and not secrets.compare_digest(expected, actual):
                    _SESSIONS.pop(token, None)
                    return None, None
                sess["role"] = current["role"]
                sess["last_seen"] = now
            return token, sess
    return None, None


def content_length(headers, max_bytes):
    if headers.get("Transfer-Encoding"):
        raise RequestRejected("Transfer-Encoding request bodies are not supported", 400)
    values = headers.get_all("Content-Length") if hasattr(headers, "get_all") else None
    if values and len(values) != 1:
        raise RequestRejected("ambiguous Content-Length", 400)
    raw = headers.get("Content-Length", "0")
    try:
        length = int(raw or 0)
    except (TypeError, ValueError) as exc:
        raise RequestRejected("invalid Content-Length", 400) from exc
    if length < 0:
        raise RequestRejected("invalid Content-Length", 400)
    if length > int(max_bytes):
        raise RequestRejected("request body exceeds limit", 413)
    return length
