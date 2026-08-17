"""
scrub.py -- Mask sensitive values in configs before they hit disk.

Network configs are full of secret material: SNMP communities, password hashes,
pre-shared keys, RADIUS/TACACS keys, VTY passwords. In a hospital estate you may
want a scrubbed copy for the SIEM / change-tracking view while keeping the real
config only in a restricted location (or not at all).

This is intentionally conservative and PATTERN-BASED. It will not catch every
vendor's every secret. It is a hygiene aid, not a guarantee -- treat the raw
config as sensitive regardless. Scrubbing is OFF by default because a scrubbed
config is not restorable; you opt in per device or globally.

Each rule keeps the directive keyword so the config still reads sensibly, and
replaces only the secret token with <scrubbed:kind>.
"""

import re

_MASK = "<scrubbed:{kind}>"

# (compiled regex, kind) -- group 'secret' is what gets masked; everything else kept.
_RULES = [
    (re.compile(r"(?im)^(?P<pre>\s*snmp-server community\s+)(?P<secret>\S+)"), "snmp"),
    (re.compile(r"(?im)^(?P<pre>\s*(?:enable )?secret\s+\d+\s+)(?P<secret>\S+)"), "hash"),
    (re.compile(r"(?im)^(?P<pre>\s*(?:enable )?password\s+\d+\s+)(?P<secret>\S+)"), "password"),
    (re.compile(r"(?im)(?P<pre>\bpassword\s+0\s+)(?P<secret>\S+)"), "password"),
    (re.compile(r"(?im)(?P<pre>\bpassword\s+7\s+)(?P<secret>\S+)"), "password7"),
    (re.compile(r"(?im)(?P<pre>\bmd5\s+\d+\s+)(?P<secret>\S+)"), "md5"),
    (re.compile(r"(?im)(?P<pre>\bkey\s+\d+\s+)(?P<secret>\S+)"), "key"),
    (re.compile(r"(?im)(?P<pre>\b(?:pre-shared-key|psk)\s+)(?P<secret>\S+)"), "psk"),
    (re.compile(r"(?im)(?P<pre>\b(?:tacacs|radius).*?\bkey\s+\d*\s*)(?P<secret>\S+)"), "aaa-key"),
    (re.compile(r"(?im)(?P<pre>\bset\b.*\bsecret\s+\")(?P<secret>[^\"]+)(?P<post>\")"), "juniper-secret"),
    (re.compile(r"(?im)(?P<pre>\bwpa-psk\s+ascii\s+\d+\s+)(?P<secret>\S+)"), "wpa"),
    (re.compile(r"(?im)(?P<pre>-----BEGIN [A-Z ]*PRIVATE KEY-----).*?(?P<post>-----END [A-Z ]*PRIVATE KEY-----)", re.S), "privkey"),
]


def scrub(text, extra_patterns=None):
    """Return (scrubbed_text, count). extra_patterns: list of raw regex strings;
    the whole match is masked as <scrubbed:custom>."""
    count = 0

    def repl(m, kind):
        nonlocal count
        count += 1
        gd = m.groupdict()
        pre = gd.get("pre", "")
        post = gd.get("post", "")
        if kind == "privkey":
            return pre + _MASK.format(kind=kind) + post
        return pre + _MASK.format(kind=kind) + post

    for rx, kind in _RULES:
        text = rx.sub(lambda m, k=kind: repl(m, k), text)

    for pat in (extra_patterns or []):
        rx = re.compile(pat)
        def crepl(m):
            nonlocal count
            count += 1
            return _MASK.format(kind="custom")
        text = rx.sub(crepl, text)

    return text, count
