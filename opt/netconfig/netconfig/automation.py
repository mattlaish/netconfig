"""
automation.py -- Script variable substitution and body parsing (pure logic).

A "script" is text, one CLI command per line, with optional ${VAR} placeholders
that each device fills from its own inventory record. This is what lets one script
("username admin password ${NodeName}-x") fan out across a device group with each
switch pulling its own parameters.

Kept dependency-free and side-effect-free so it can be unit-tested on its own and
so the concurrent runner (in manager.py, which owns SSH/vault) stays thin.

Supported variables (case-insensitive), resolved per device:
    ${NodeName} / ${Name}     device name
    ${IP_Address} / ${Host}   management address
    ${Port}                   SSH port
    ${Platform}               platform key
    ${Tag:foo}                1 if device carries tag 'foo' else '' (rarely used)
    ${Var:KEY}                custom variable supplied at run time
Unknown variables are left intact and reported, so a typo fails loudly at review
time rather than silently sending "${Ip_Adress}" to a live switch.
"""

import re

_VAR = re.compile(r"\$\{([^}]+)\}")


def _device_vars(device):
    return {
        "nodename": device.get("name", ""),
        "name": device.get("name", ""),
        "ip_address": device.get("host", ""),
        "host": device.get("host", ""),
        "port": str(device.get("port", "")),
        "platform": device.get("platform", ""),
    }


def substitute(text, device, extra=None):
    """Return (resolved_text, unresolved_names). `extra` is a dict of custom
    variables provided at run time (matched via ${Var:KEY} or bare ${KEY})."""
    dv = _device_vars(device)
    extra = {k.lower(): v for k, v in (extra or {}).items()}
    tags = {t.lower() for t in device.get("tags", [])}
    unresolved = []

    def repl(m):
        raw = m.group(1).strip()
        key = raw.lower()
        if key.startswith("tag:"):
            return "1" if key[4:] in tags else ""
        if key.startswith("var:"):
            k = key[4:]
            if k in extra:
                return str(extra[k])
            unresolved.append(raw)
            return m.group(0)
        if key in dv:
            return dv[key]
        if key in extra:
            return str(extra[key])
        unresolved.append(raw)
        return m.group(0)

    out = _VAR.sub(repl, text)
    return out, unresolved


def commands(body):
    """Split a script body into executable command lines, dropping blanks and
    '!'/'#'-style comments (a leading # or ! comments the line)."""
    out = []
    for line in body.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if s.lstrip().startswith("#") or s.lstrip().startswith("! "):
            continue
        out.append(s)
    return out


def find_variables(body):
    """All distinct ${...} tokens in a body, for the UI to prompt/preview."""
    seen = []
    for m in _VAR.finditer(body):
        v = m.group(1).strip()
        if v not in seen:
            seen.append(v)
    return seen
