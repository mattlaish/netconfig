"""Hashed, scoped bearer tokens for the read-only API."""
import hashlib, json, secrets, time

VALID_SCOPES = {
    "inventory:read", "topology:read", "endpoint:read", "events:read", "alerts:read", "alerts:write", "reports:read", "reports:write", "drift:read", "compliance:read", "audit:read",
    "debug:create", "debug:read", "debug:download", "debug:admin",
    "incident:read", "incident:write", "incident:export",
    "trace:read", "trace:capture", "protocol:read", "protocol:write",
    "automation:read", "automation:write", "telemetry:read", "telemetry:write",
    "desired:read", "desired:write", "campaign:read", "campaign:write",
    "model:read", "model:write", "ha:read", "ha:write",
    "analytics:read", "analytics:write",
}

_SCOPE_MIN_ROLE = {
    "incident:write": "operator",
    "incident:export": "operator",
    "trace:capture": "operator",
    "alerts:write": "operator",
    "reports:write": "operator",
    "protocol:write": "operator",
    "automation:write": "operator",
    "telemetry:write": "operator",
    "desired:write": "operator",
    "campaign:write": "operator",
    "model:write": "admin",
    "ha:write": "operator",
    "analytics:write": "operator",
}
_ROLE_LEVEL = {"viewer": 0, "operator": 1, "approver": 2, "admin": 3}


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()

class ApiTokens:
    def __init__(self, conn):
        self.conn = conn
    def create(self, name, scopes, created_by="", role="viewer"):
        if role not in {"viewer", "operator", "approver", "admin"}:
            raise ValueError("invalid role")
        scopes = sorted(set(scopes)); bad = set(scopes) - VALID_SCOPES
        if bad:
            raise ValueError("invalid scopes: " + ", ".join(sorted(bad)))
        for scope in scopes:
            minimum = _SCOPE_MIN_ROLE.get(scope)
            if minimum and _ROLE_LEVEL[role] < _ROLE_LEVEL[minimum]:
                raise ValueError(f"scope {scope} requires role {minimum} or higher")
        raw = "nct_" + secrets.token_urlsafe(32)
        cur = self.conn.execute("INSERT INTO api_tokens(name, token_hash, scopes, role, created_by, created_ts, disabled) VALUES (?,?,?,?,?,?,0)",
                                (name, _hash(raw), json.dumps(scopes), role, created_by, time.time()))
        self.conn.commit(); return cur.lastrowid, raw
    def verify(self, raw):
        if not raw:
            return None
        row = self.conn.execute("SELECT * FROM api_tokens WHERE token_hash=? AND disabled=0", (_hash(raw),)).fetchone()
        if not row:
            return None
        d = dict(row); d["scopes"] = set(json.loads(d.get("scopes") or "[]"))
        self.conn.execute("UPDATE api_tokens SET last_used_ts=? WHERE id=?", (time.time(), d["id"])); self.conn.commit()
        return d
    def list(self):
        return [dict(r) for r in self.conn.execute("SELECT id,name,scopes,role,created_by,created_ts,last_used_ts,disabled FROM api_tokens ORDER BY id").fetchall()]
    def revoke(self, token_id):
        self.conn.execute("UPDATE api_tokens SET disabled=1 WHERE id=?", (int(token_id),)); self.conn.commit()
