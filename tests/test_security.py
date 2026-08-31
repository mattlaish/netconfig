from netconfig.security import LoginThrottle, security_headers


def test_login_throttle_after_threshold_and_reset():
    t = LoginThrottle(window_seconds=60, max_failures=2, max_delay=10)
    assert t.failure("127.0.0.1", "Admin", now=100) == 0
    assert t.failure("127.0.0.1", "admin", now=101) >= 1
    assert t.retry_after("127.0.0.1", "ADMIN", now=101) >= 1
    t.success("127.0.0.1", "admin")
    assert t.retry_after("127.0.0.1", "admin", now=101) == 0


def test_security_headers_include_csp_referrer_and_hsts_under_tls():
    headers = dict(security_headers(tls=True, csp_nonce="abc"))
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert "nonce-abc" in headers["Content-Security-Policy-Report-Only"]
    assert headers["Strict-Transport-Security"].startswith("max-age=")
