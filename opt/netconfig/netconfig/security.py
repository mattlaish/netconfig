"""Security helpers for the web console.

Stdlib-only primitives: login throttling and security headers. Session expiry is
intentionally not implemented here yet; see SECURITY.md / ROADMAP.md.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class LoginThrottle:
    """Bounded in-memory throttle keyed by source IP + username.

    This is process-local by design. It protects the built-in console without a
    new dependency; multi-node deployments should move the counters to a shared
    store before claiming cluster-wide lockout semantics.
    """

    def __init__(self, *, window_seconds=900, max_failures=5, max_delay=60):
        self.window_seconds = int(window_seconds)
        self.max_failures = int(max_failures)
        self.max_delay = int(max_delay)
        self._lock = threading.Lock()
        self._failures = defaultdict(deque)

    @staticmethod
    def _key(ip, username):
        return (str(ip or "unknown"), str(username or "").strip().lower())

    def _prune(self, q, now):
        cutoff = now - self.window_seconds
        while q and q[0] < cutoff:
            q.popleft()

    def retry_after(self, ip, username, now=None):
        now = time.time() if now is None else float(now)
        key = self._key(ip, username)
        with self._lock:
            q = self._failures[key]
            self._prune(q, now)
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
            q = self._failures[key]
            self._prune(q, now)
            q.append(now)
        return self.retry_after(ip, username, now)

    def success(self, ip, username):
        with self._lock:
            self._failures.pop(self._key(ip, username), None)


def security_headers(*, tls=False, csp_nonce=None):
    """Return conservative headers for every console response.

    Inline style attributes and event handlers still exist in the legacy monolithic
    UI, so the enforced policy temporarily permits inline CSS/JS. A stricter nonce-
    based policy is also emitted in report-only mode to drive the migration.
    """
    nonce = csp_nonce or ""
    csp = (
        "default-src 'self'; "
        "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
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
         f"script-src 'self' 'nonce-{nonce}'; style-src 'self' 'unsafe-inline'; "
         "frame-ancestors 'none'"),
        ("Cache-Control", "no-store"),
    ]
    if tls:
        out.append(("Strict-Transport-Security", "max-age=31536000; includeSubDomains"))
    return out
