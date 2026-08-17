"""Zero-dependency HTTP(S) / REST API + TLS status checks for 'application' devices.

For each configured endpoint we do an HTTP GET (status code + latency) and, for
HTTPS URLs, a TLS check reporting certificate validity and days-to-expiry.

Only the Python standard library is used (urllib + ssl + socket).
"""
import re
import socket
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse


def _name(seq):
    try:
        d = {}
        for rdn in seq or ():
            for k, v in rdn:
                d[k] = v
        return d.get("commonName") or d.get("organizationName") or ""
    except Exception:
        return ""


def check_tls(host, port=443, timeout=5.0):
    """TLS handshake with verification. Reports validity, days-to-expiry, issuer."""
    out = {"checked": True, "valid": False}
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                cert = ss.getpeercert() or {}
                out["valid"] = True
                out["version"] = ss.version()
                na = cert.get("notAfter")
                if na:
                    exp = ssl.cert_time_to_seconds(na)
                    out["expires_days"] = int((exp - time.time()) // 86400)
                    out["expires"] = na
                out["issuer"] = _name(cert.get("issuer"))
    except ssl.SSLCertVerificationError as e:
        out["error"] = getattr(e, "verify_message", None) or str(e)
    except Exception as e:
        out["error"] = str(e)
    return out


def check_http(url, timeout=5.0, expect=None):
    """HTTP GET; returns status, latency, ok. For https also runs a TLS check.
    Uses an unverified context for the GET so the HTTP status is still reported
    when the certificate is invalid (cert validity is reported separately)."""
    if "://" not in url:
        url = "https://" + url
    out = {"url": url, "expect": expect}
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(url, method="GET",
                                 headers={"User-Agent": "netconfig-appmon"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            out["status"] = getattr(r, "status", r.getcode())
            out["ms"] = round((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        out["status"] = e.code
        out["ms"] = round((time.time() - t0) * 1000)
    except Exception as e:
        out["status"] = None
        out["ms"] = round((time.time() - t0) * 1000)
        out["error"] = str(e)
    if out.get("status") is not None:
        out["ok"] = (out["status"] == expect) if expect else (200 <= out["status"] < 400)
    else:
        out["ok"] = False
    p = urlparse(url)
    if p.scheme == "https" and p.hostname:
        out["tls"] = check_tls(p.hostname, p.port or 443, timeout)
    return out


def parse_targets(spec, host=""):
    """One URL per line/comma, optional trailing expected-status code. Bare host
    -> https://host/. Defaults to https://host/ when nothing is configured."""
    targets = []
    for line in re.split(r"[\n,]+", spec or ""):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        url = parts[0]
        expect = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        if "://" not in url:
            url = "https://" + url
        targets.append((url, expect))
        if len(targets) >= 32:
            break
    if not targets and host:
        targets.append((f"https://{host}/", None))
    return targets


def check_all(spec, host="", timeout=5.0, workers=8):
    targets = parse_targets(spec, host)
    if not targets:
        return []
    results = []
    with ThreadPoolExecutor(max_workers=min(workers, len(targets))) as ex:
        futs = {ex.submit(check_http, u, timeout, e): (u, e) for u, e in targets}
        for fut, (u, e) in futs.items():
            try:
                r = fut.result()
            except Exception as ex2:
                r = {"url": u, "status": None, "error": str(ex2), "ok": False, "expect": e}
            results.append(r)
    results.sort(key=lambda x: x["url"])
    return results
