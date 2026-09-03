"""Zero-dependency Microsoft Entra ID (Office 365) OAuth2 client.

Uses the client-credentials grant to obtain an access token from Entra, which
can be used for Microsoft Graph or (with XOAUTH2) authenticated SMTP to
Office 365. Only the Python standard library is used.

Config keys (in settings):
  o365_enabled, o365_tenant, o365_client_id, o365_authority, o365_scope
The client secret is held in the vault (reserved secret ``__o365__``).
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

O365_SECRET = "__o365__"
DEFAULT_AUTHORITY = "https://login.microsoftonline.com"
DEFAULT_SCOPE = "https://outlook.office365.com/.default"   # for SMTP AUTH XOAUTH2

_cache = {}   # tenant+scope -> (token, expiry_epoch)


def token_endpoint(settings):
    authority = (settings.get("o365_authority") or DEFAULT_AUTHORITY).rstrip("/")
    tenant = settings.get("o365_tenant", "")
    return f"{authority}/{tenant}/oauth2/v2.0/token"


def get_token(settings, client_secret, timeout=15, use_cache=True, _opener=None):
    """Return (token_dict, error). token_dict has access_token / expires_in."""
    tenant = settings.get("o365_tenant", "")
    client_id = settings.get("o365_client_id", "")
    scope = settings.get("o365_scope") or DEFAULT_SCOPE
    if not (tenant and client_id and client_secret):
        return None, "tenant ID, client ID and client secret are all required"
    ck = (tenant, client_id, scope)
    if use_cache:
        cached = _cache.get(ck)
        if cached and cached[1] - 60 > time.time():
            return {"access_token": cached[0], "cached": True}, None
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": scope,
    }).encode()
    req = urllib.request.Request(
        token_endpoint(settings), data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    opener = _opener or urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
        tok = body.get("access_token")
        if not tok:
            return None, "no access_token in response"
        if use_cache and body.get("expires_in"):
            _cache[ck] = (tok, time.time() + int(body["expires_in"]))
        return {"access_token": tok, "expires_in": body.get("expires_in"),
                "token_type": body.get("token_type")}, None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            msg = err.get("error_description") or err.get("error") or str(e)
        except Exception:
            msg = str(e)
        return None, msg.splitlines()[0][:200]
    except Exception as e:
        return None, str(e)


def xoauth2_string(user, access_token):
    """SASL XOAUTH2 initial-response payload for SMTP AUTH."""
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"
