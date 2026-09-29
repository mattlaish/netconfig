"""Security helpers for the web console.

Stdlib-only primitives: bounded login throttling and security headers.  R64 also
keeps attacker-controlled throttle cardinality bounded; session lifetime/cap
enforcement lives in :mod:`netconfig.web` because it owns the session store.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class LoginThrottle:
    """Bounded in-memory throttle keyed by source IP + username.

    This is process-local by design. It protects the built-in console without a
    new dependency; multi-node deployments should move the counters to a shared
    store before claiming cluster-wide lockout semantics.
    """

    def __init__(self, *, window_seconds=900, max_failures=5, max_delay=60,
                 max_keys=4096, max_identity_chars=128):
        self.window_seconds = int(window_seconds)
        self.max_failures = int(max_failures)
        self.max_delay = int(max_delay)
        self.max_keys = max(32, int(max_keys))
        self.max_identity_chars = max(16, int(max_identity_chars))
        self._lock = threading.Lock()
        self._failures = {}
        self._last_seen = {}

    def _key(self, ip, username):
        # Bound attacker-controlled identity material before it becomes a dict key.
        ip = str(ip or "unknown")[:self.max_identity_chars]
        username = str(username or "").strip().lower()[:self.max_identity_chars]
        return (ip, username)

    def _prune(self, q, now):
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

    def _prune_stale_keys(self, now):
        # Only called when creating a new key, keeping the common retry path O(1).
        for key, q in list(self._failures.items()):
            self._prune(q, now)
            if not q:
                self._failures.pop(key, None)
                self._last_seen.pop(key, None)
        while len(self._failures) >= self.max_keys:
            oldest = min(self._last_seen, key=self._last_seen.get)
            self._failures.pop(oldest, None)
            self._last_seen.pop(oldest, None)

    def retry_after(self, ip, username, now=None):
        now = time.time() if now is None else float(now)
        key = self._key(ip, username)
        with self._lock:
            q = self._failures.get(key)
            if q is None:
                return 0
            self._prune(q, now)
            if not q:
                self._failures.pop(key, None)
                self._last_seen.pop(key, None)
                return 0
            self._last_seen[key] = now
            if len(q) < self.max_failures:
                return 0
            exponent = min(len(q) - self.max_failures, 6)
            delay = min(self.max_delay, 2 ** exponent)
            last = q[-1]
            return max(0, int((last + delay) - now + 0.999))

    def failure(self, ip, username, now=None):
        now = time.time() if now is None else float(now)
        key = self._key(ip, username)
        with self._lock:
            q = self._failures.get(key)
            if q is None:
                self._prune_stale_keys(now)
                q = deque()
                self._failures[key] = q
            self._prune(q, now)
            q.append(now)
            self._last_seen[key] = now
            if len(q) < self.max_failures:
                return 0
            exponent = min(len(q) - self.max_failures, 6)
            delay = min(self.max_delay, 2 ** exponent)
            return max(0, int((q[-1] + delay) - now + 0.999))

    def success(self, ip, username):
        key = self._key(ip, username)
        with self._lock:
            self._failures.pop(key, None)
            self._last_seen.pop(key, None)

    def tracked_keys(self):
        """Return current throttle-key count for diagnostics/tests, not identities."""
        with self._lock:
            return len(self._failures)


def security_headers(*, tls=False, csp_nonce=None):
    """Return conservative headers for every console response.

    PH-1 removes inline JavaScript event attributes and authorizes inline script
    blocks only with a per-response nonce. Inline style attributes remain a
    PH-1 also normalizes server-rendered style attributes into nonce-authorized
    utility classes, allowing style-src-attr to be denied in the enforced policy.
    """
    nonce = csp_nonce or ""
    csp = (
        "default-src 'self'; "
        "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        f"script-src 'self' 'nonce-{nonce}'; script-src-attr 'none'; "
        f"style-src 'self' 'nonce-{nonce}'; style-src-attr 'none'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "form-action 'self'"
    )
    out = [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
        ("Content-Security-Policy", csp),
        ("Content-Security-Policy-Report-Only",
         "default-src 'self'; object-src 'none'; base-uri 'none'; "
         f"script-src 'self' 'nonce-{nonce}'; script-src-attr 'none'; style-src 'self' 'nonce-{nonce}'; style-src-attr 'none'; "
         "frame-ancestors 'none'"),
        ("Cache-Control", "no-store"),
    ]
    if tls:
        out.append(("Strict-Transport-Security", "max-age=31536000; includeSubDomains"))
    return out
