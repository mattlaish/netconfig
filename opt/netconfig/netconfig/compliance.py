"""
compliance.py -- Config policy auditing against security standards.

A rule scans a device's stored configuration text and returns pass/fail with the
evidence line(s) and a remediation string. Rules are declarative: a compiled
regex plus a mode ("present" = must appear, "absent" = must not appear). Complex
checks use a small callable.

Two starter packs ship: ISO 27001 (Annex A control families) and PCI-DSS. They
are deliberately Cisco-IOS-shaped because that's the common case; each rule
declares which platforms it applies to and is reported "n/a" elsewhere. They are
starting points meant to be extended for a specific estate, not a certification
guarantee -- passing every rule here is necessary hygiene, not a signed audit.

The engine is pure text analysis: no device contact, no side effects.
"""

import re

_CISCOISH = {"cisco_ios", "cisco_nxos", "cisco_asa", "arista_eos", "generic"}


class Rule:
    def __init__(self, rid, title, standard, severity, mode, pattern,
                 remediation, platforms=None, refs=""):
        self.id = rid
        self.title = title
        self.standard = standard
        self.severity = severity      # high | medium | low
        self.mode = mode              # present | absent | custom
        self.pattern = re.compile(pattern, re.I | re.M) if pattern else None
        self.remediation = remediation
        self.platforms = platforms or _CISCOISH
        self.refs = refs
        self.check_fn = None

    def applies(self, platform):
        return platform in self.platforms

    def evaluate(self, config):
        """Return (status, evidence). status in pass|fail."""
        if self.mode == "custom":
            return self.check_fn(config)
        m = self.pattern.search(config or "")
        if self.mode == "present":
            return ("pass", m.group(0).strip()) if m else ("fail", "")
        if self.mode == "absent":
            return ("fail", m.group(0).strip()) if m else ("pass", "")
        return ("fail", "unknown rule mode")


def _check_no_default_community(config):
    m = re.search(r"^\s*snmp-server community\s+(public|private)\b", config or "",
                  re.I | re.M)
    return ("fail", m.group(0).strip()) if m else ("pass", "")


def _check_exec_timeout(config):
    # fail if any vty/console line sets exec-timeout 0 0 (never times out)
    m = re.search(r"^\s*exec-timeout\s+0\s+0\b", config or "", re.I | re.M)
    return ("fail", m.group(0).strip()) if m else ("pass", "")


def _rule_custom(rid, title, standard, severity, fn, remediation, platforms=None, refs=""):
    r = Rule(rid, title, standard, severity, "custom", None, remediation, platforms, refs)
    r.check_fn = fn
    return r


_RULES = [
    # ---- ISO 27001 (Annex A) -------------------------------------------
    Rule("ISO-A9.4-TELNET", "Insecure Telnet access disabled", "ISO 27001",
         "high", "absent", r"transport input (all|telnet)",
         "Restrict VTY transport to SSH: `line vty 0 4` then "
         "`transport input ssh`. Remove `transport input telnet|all`.",
         refs="A.9.4.2 / A.13.1.1"),
    Rule("ISO-A9.4-BANNER", "Login banner / legal notice present", "ISO 27001",
         "low", "present", r"banner (login|motd)",
         "Configure an authorized-access-only banner: "
         "`banner login ^C ... ^C`.", refs="A.9.4.2"),
    Rule("ISO-A9.4-SSHV2", "SSH protocol version 2 enforced", "ISO 27001",
         "medium", "present", r"ip ssh version 2",
         "Enforce SSHv2: `ip ssh version 2`.", refs="A.13.1.1"),
    Rule("ISO-A12.4-LOGGING", "Central logging configured", "ISO 27001",
         "medium", "present", r"logging (host|server)\s+\S+",
         "Send logs to the SIEM: `logging host <mini-SIEM-ip>`.",
         refs="A.12.4.1"),
    Rule("ISO-A12.4-NTP", "Time synchronization (NTP) configured", "ISO 27001",
         "medium", "present", r"ntp server\s+\S+",
         "Configure NTP so log timestamps are trustworthy: "
         "`ntp server <ntp-ip>`.", refs="A.12.4.4"),

    # ---- PCI-DSS --------------------------------------------------------
    Rule("PCI-2.2.2-TELNET", "Insecure services disabled (Telnet)", "PCI-DSS",
         "high", "absent", r"transport input (all|telnet)",
         "PCI-DSS 2.2.2/2.2.7: disable insecure services. Use "
         "`transport input ssh` only.", refs="2.2.2"),
    Rule("PCI-8.3.1-PWENC", "Passwords stored encrypted", "PCI-DSS",
         "high", "present", r"service password-encryption",
         "PCI-DSS 8.3.1: render credentials unreadable. Enable "
         "`service password-encryption` and use `enable secret`.",
         refs="8.3.1"),
    _rule_custom("PCI-8.3.1-NOPLAIN", "No unencrypted enable password", "PCI-DSS",
         "high",
         lambda c: (("fail", re.search(r"^\s*enable password\s+(?!5|7|8|9)\S",
                     c or "", re.I | re.M).group(0).strip())
                    if re.search(r"^\s*enable password\s+(?!5|7|8|9)\S", c or "",
                     re.I | re.M) else ("pass", "")),
         "Replace `enable password` with `enable secret` (hashed).",
         refs="8.3.1"),
    _rule_custom("PCI-2.1-DEFCOMM", "No default SNMP communities", "PCI-DSS",
         "high", _check_no_default_community,
         "PCI-DSS 2.1: change vendor defaults. Remove `public`/`private` "
         "communities; use SNMPv3 with auth+priv.", refs="2.1"),
    _rule_custom("PCI-8.6-TIMEOUT", "Idle session timeout enforced", "PCI-DSS",
         "medium", _check_exec_timeout,
         "PCI-DSS 8.6: terminate idle sessions. Avoid `exec-timeout 0 0`; "
         "set e.g. `exec-timeout 10 0`.", refs="8.6"),
]


def _r(rid, title, standard, severity, ok, evidence, remediation, refs="",
       status=None, scored=True, category="security"):
    if status is None:
        status = "unknown" if ok is None else ("pass" if ok else "fail")
    return {"id": rid, "title": title, "standard": standard, "severity": severity,
            "status": status, "evidence": evidence, "remediation": remediation,
            "refs": refs, "scored": bool(scored), "category": category}


def evaluate_system(dev, standard=None):
    """Live TCP/UDP posture audit for a 'system' device. Actively probes a fixed
    set of ports that should/shouldn't be exposed (independent of what the device
    is configured to monitor)."""
    from . import portmon
    host = dev.get("host")
    checks = portmon.check_ports(host, "tcp/23, tcp/21, tcp/3389, tcp/445, tcp/22", timeout=1.5)
    state = {(c["proto"], c["port"]): c["state"] for c in checks}
    approved = set(portmon.parse_ports(dev.get("monitor_ports") or ""))

    def openp(port):
        return state.get(("tcp", port)) == "open"
    def closedp(port):
        value = state.get(("tcp", port))
        return True if value in ("closed", "filtered") else (False if value == "open" else None)
    def evidence(port):
        return f"tcp/{port} {state.get(('tcp', port), 'no result')}"
    out = [
        _r("SYS-TELNET", "Telnet (tcp/23) not exposed", "ISO 27001", "high",
           closedp(23), evidence(23),
           "Disable Telnet; use SSH. Close tcp/23 / firewall it.", "A.9.4.2 / A.13.1.1"),
        _r("SYS-FTP", "FTP (tcp/21) not exposed", "PCI-DSS", "high",
           closedp(21), evidence(21),
           "Disable FTP; use SFTP/SCP. Close tcp/21.", "2.2.2"),
        _r("SYS-SMB", "SMB exposure is explicitly monitored", "ISO 27001", "medium",
           (True if openp(445) and ("tcp", 445) in approved else closedp(445)),
           evidence(445) + ("; approved in monitored ports" if ("tcp", 445) in approved else ""),
           "Add an approved SMB service to monitored ports, or restrict tcp/445.",
           "A.13.1.1"),
        _r("SYS-RDP", "RDP exposure is explicitly monitored", "PCI-DSS", "medium",
           (True if openp(3389) and ("tcp", 3389) in approved else closedp(3389)),
           evidence(3389) + ("; approved in monitored ports" if ("tcp", 3389) in approved else ""),
           "Add an approved RDP service to monitored ports, or restrict tcp/3389.", "1.3"),
        _r("SYS-SSH", "SSH (tcp/22) reachable for management", "ISO 27001", "low",
           (True if openp(22) else (False if state.get(("tcp", 22)) in
                                    ("closed", "filtered") else None)), evidence(22),
           "Ensure secure management access (SSH) is available.", "A.9.4.2"),
    ]
    return [x for x in out if not standard or x["standard"] == standard]


def evaluate_application(dev, standard=None):
    """HTTP(S)/TLS posture audit for an 'application' device using its monitored
    endpoints (defaults to https://host/)."""
    from . import appmon
    spec = (dev.get("monitor_urls") or "").strip() or f"https://{dev.get('host')}/"
    results = appmon.check_all(spec, dev.get("host"), timeout=5.0)
    if not results:
        return [_r("APP-REACHABLE", "Application audit completed", "ISO 27001", "high",
                   None, "no endpoint results", "Check the endpoint configuration and DNS.")]
    https = [r for r in results if r["url"].lower().startswith("https://")]
    http_only = [r for r in results if r["url"].lower().startswith("http://")]
    tls = [r.get("tls") for r in https if r.get("tls")]
    valid = [t for t in tls if t.get("valid")]
    soon = [t for t in valid if t.get("expires_days") is not None and t["expires_days"] < 30]
    weak = [t for t in valid if t.get("version") in ("SSLv3", "TLSv1", "TLSv1.1")]
    unhealthy = [r for r in results if not r.get("ok")]
    response_results = [r for r in results if r.get("status") is not None]
    legacy = [state for t in tls for state in (t.get("legacy_protocols") or {}).values()]
    cipher_bits = [t.get("cipher_bits") for t in tls if t.get("cipher_bits") is not None]
    html_results = [r for r in response_results
                    if "text/html" in (r.get("headers") or {}).get("content-type", "").lower()]

    if not https or len(valid) != len(https):
        expiry_ok = None
    elif any(t.get("expires_days") is None for t in valid):
        expiry_ok = None
    else:
        expiry_ok = not soon
    if not tls or not legacy or any(x is None for x in legacy):
        legacy_ok = None
    else:
        legacy_ok = not any(legacy)
    if not tls or len(cipher_bits) != len(tls):
        cipher_ok = None
    else:
        cipher_ok = all(bits >= 128 for bits in cipher_bits)

    def all_header(rows, name):
        if not rows:
            return None
        return all(bool((r.get("headers") or {}).get(name)) for r in rows)

    out = [
        _r("APP-HTTPS-ONLY", "All endpoints use HTTPS", "PCI-DSS", "high",
           not http_only, f"{len(http_only)} plain-HTTP endpoint(s)" if http_only else "all HTTPS",
           "Serve the API/app over HTTPS only; redirect HTTP to HTTPS.", "4.2.1"),
        _r("APP-TLS-VALID", "TLS certificates valid", "ISO 27001", "high",
           bool(https) and len(valid) == len(https),
           f"{len(https) - len(valid)} invalid of {len(https)}" if https else "no HTTPS endpoints",
           "Install a valid, trusted certificate matching the hostname.", "A.10.1.1 / A.14.1.2"),
        _r("APP-CERT-EXPIRY", "No certificate expiring within 30 days", "ISO 27001", "medium",
           expiry_ok, (f"{len(soon)} cert(s) expiring <30d" if soon else
                       ("expiry unavailable until TLS validates" if expiry_ok is None else "ok")),
           "Renew certificates well before expiry; automate renewal.", "A.10.1.2"),
        _r("APP-TLS-VERSION", "TLS 1.0/1.1 rejected", "PCI-DSS", "high",
           legacy_ok, ("legacy TLS accepted" if any(x is True for x in legacy) else
                       ("legacy TLS probe inconclusive" if legacy_ok is None else "legacy TLS rejected")),
           "Disable SSLv3/TLS 1.0/1.1; require TLS 1.2 or higher.", "4.2.1"),
        _r("APP-TLS-CIPHER", "TLS cipher strength is at least 128 bits", "PCI-DSS", "high",
           cipher_ok, ", ".join(str(x) for x in cipher_bits) + " bits" if cipher_bits else
           "cipher unavailable", "Enable modern AEAD cipher suites and forward secrecy.", "4.2.1"),
        _r("APP-HSTS", "HTTPS responses enable HSTS", "ISO 27001", "medium",
           all_header([r for r in response_results if r["url"].lower().startswith("https://")],
                      "strict-transport-security"),
           "Strict-Transport-Security present on all HTTPS responses" if
           all_header([r for r in response_results if r["url"].lower().startswith("https://")],
                      "strict-transport-security") else "HSTS missing or unavailable",
           "Add a Strict-Transport-Security header after confirming HTTPS-only operation.",
           "A.8.20"),
        _r("APP-NOSNIFF", "Responses prevent MIME sniffing", "ISO 27001", "low",
           all((r.get("headers") or {}).get("x-content-type-options", "").lower() == "nosniff"
               for r in response_results) if response_results else None,
           "X-Content-Type-Options: nosniff required",
           "Return `X-Content-Type-Options: nosniff` on application responses.", "A.8.26"),
        _r("APP-CSP", "HTML responses define a content security policy", "ISO 27001", "medium",
           all_header(html_results, "content-security-policy"),
           "Content-Security-Policy required for HTML" if html_results else "no HTML response",
           "Define a restrictive Content-Security-Policy for HTML pages.", "A.8.26",
           status="not_applicable" if not html_results else None),
        _r("APP-HEALTH", "All monitored endpoints healthy", "ISO 27001", "medium",
           not unhealthy, f"{len(unhealthy)} endpoint(s) unhealthy" if unhealthy else "all healthy",
           "Investigate non-2xx/unreachable endpoints.", "A.12.1.3",
           scored=False, category="operational"),
    ]
    return [x for x in out if not standard or x["standard"] == standard]


def _types_of(dev):
    raw = (dev.get("device_type") or "") if dev else ""
    ts = {t for t in re.split(r"[,\s]+", raw) if t}
    return ts or {"network"}


def rules_for(platform):
    return [r for r in _RULES if r.applies(platform)]


def standards():
    out = []
    for r in _RULES:
        if r.standard not in out:
            out.append(r.standard)
    return out


def evaluate_device(config, platform, standard=None):
    """Return a list of per-rule result dicts for one device's config."""
    results = []
    for r in rules_for(platform):
        if standard and r.standard != standard:
            continue
        status, evidence = r.evaluate(config or "")
        results.append({
            "id": r.id, "title": r.title, "standard": r.standard,
            "severity": r.severity, "status": status, "evidence": evidence,
            "remediation": r.remediation, "refs": r.refs,
        })
    return results


def evaluate_fleet(store, devices, standard=None):
    """Evaluate every device that has a stored config. Returns a report dict:
    {devices:[{device, platform, passed, failed, results:[...]}], totals:{...}}"""
    dev_reports = []
    tot_pass = tot_fail = 0
    for d in devices:
        types = _types_of(d)
        res = []
        # network devices: config-policy checks (need a stored config)
        if "network" in types:
            cfg = store.current(d["name"])
            if cfg is not None:
                res += evaluate_device(cfg, d["platform"], standard)
        # system devices: live TCP/UDP posture
        if "system" in types:
            try:
                res += evaluate_system(d, standard)
            except Exception:
                pass
        # application devices: HTTP(S)/TLS posture
        if "application" in types:
            try:
                res += evaluate_application(d, standard)
            except Exception:
                pass
        if not res:
            dev_reports.append({"device": d["name"], "platform": d["platform"],
                                "types": sorted(types), "passed": 0, "failed": 0,
                                "skipped": True, "results": []})
            continue
        scored = [r for r in res if r.get("scored", True)]
        p = sum(1 for r in scored if r["status"] == "pass")
        f = sum(1 for r in scored if r["status"] == "fail")
        u = sum(1 for r in scored if r["status"] == "unknown")
        na = sum(1 for r in scored if r["status"] == "not_applicable")
        tot_pass += p
        tot_fail += f
        dev_reports.append({"device": d["name"], "platform": d["platform"],
                            "types": sorted(types), "passed": p, "failed": f,
                            "unknown": u, "not_applicable": na,
                            "skipped": False, "results": res})
    tot_unknown = sum(r.get("unknown", 0) for r in dev_reports)
    tot_na = sum(r.get("not_applicable", 0) for r in dev_reports)
    return {
        "devices": dev_reports,
        "totals": {"pass": tot_pass, "fail": tot_fail,
                   "unknown": tot_unknown, "not_applicable": tot_na,
                   "checks": tot_pass + tot_fail + tot_unknown,
                   "compliant_devices": sum(1 for r in dev_reports
                                            if not r["skipped"] and r["failed"] == 0 and
                                            r.get("unknown", 0) == 0),
                   "device_count": sum(1 for r in dev_reports if not r["skipped"])},
    }
