"""Zero-dependency Microsoft Entra ID (Office 365) OAuth2 client.

Uses the client-credentials grant to obtain an access token from Entra, which
can be used for Microsoft Graph or (with XOAUTH2) authenticated SMTP to
Office 365. Only the Python standard library is used.

Config keys (in settings):
  o365_enabled, o365_tenant, o365_client_id, o365_authority, o365_scope
The client secret is held in the vault (reserved secret ``__o365__``).
"""
import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

O365_SECRET = "__o365__"
DEFAULT_AUTHORITY = "https://login.microsoftonline.com"
DEFAULT_SCOPE = "https://outlook.office365.com/.default"   # for SMTP AUTH XOAUTH2

_cache = {}   # tenant+scope -> (token, expiry_epoch)

PUBLIC_CLOUD_AUTHORITY = "https://login.microsoftonline.com"
MAX_OAUTH_RESPONSE_BYTES = 1024 * 1024
_TENANT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,254}$")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url, code, "OAuth redirects are forbidden", headers, fp
        )


def _oauth_opener():
    # Default HTTPS handler uses Python's verified TLS context.  Redirects are
    # refused so a compromised authority endpoint cannot pivot to RFC1918/link-
    # local HTTP or silently downgrade TLS.
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        _NoRedirect(),
    )


def _oauth_urlopen(req, timeout=15):
    return _oauth_opener().open(req, timeout=timeout)


def _normalized_authority(settings):
    authority = str(settings.get("o365_authority") or PUBLIC_CLOUD_AUTHORITY).strip().rstrip("/")
    if authority != PUBLIC_CLOUD_AUTHORITY:
        raise ValueError("O365 authority must be https://login.microsoftonline.com")
    return authority


def _validated_tenant(settings):
    tenant = str(settings.get("o365_tenant") or "").strip()
    if not tenant or not _TENANT.fullmatch(tenant) or ".." in tenant:
        raise ValueError("O365 tenant must be a tenant ID or verified domain without URL/path syntax")
    return tenant


def token_endpoint(settings):
    authority = _normalized_authority(settings)
    tenant = _validated_tenant(settings)
    return f"{authority}/{tenant}/oauth2/v2.0/token"


def get_token(settings, client_secret, timeout=15, use_cache=True, _opener=None):
    """Return (token_dict, error). token_dict has access_token / expires_in."""
    tenant = settings.get("o365_tenant", "")
    client_id = settings.get("o365_client_id", "")
    scope = settings.get("o365_scope") or DEFAULT_SCOPE
    if not (tenant and client_id and client_secret):
        return None, "tenant ID, client ID and client secret are all required"
    try:
        endpoint = token_endpoint(settings)
    except ValueError as exc:
        return None, str(exc)
    ck = (endpoint, client_id, scope)
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
        endpoint, data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    opener = _opener or _oauth_urlopen
    try:
        with opener(req, timeout=timeout) as r:
            raw = r.read(MAX_OAUTH_RESPONSE_BYTES + 1)
            if len(raw) > MAX_OAUTH_RESPONSE_BYTES:
                return None, "OAuth response exceeds 1 MiB limit"
            body = json.loads(raw.decode())
        tok = body.get("access_token")
        if not tok:
            return None, "no access_token in response"
        if use_cache and body.get("expires_in"):
            _cache[ck] = (tok, time.time() + int(body["expires_in"]))
        return {"access_token": tok, "expires_in": body.get("expires_in"),
                "token_type": body.get("token_type")}, None
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read(64 * 1024).decode())
            msg = err.get("error_description") or err.get("error") or str(e)
        except Exception:
            msg = str(e)
        return None, msg.splitlines()[0][:200]
    except Exception as e:
        return None, str(e)


def xoauth2_string(user, access_token):
    """SASL XOAUTH2 initial-response payload for SMTP AUTH."""
    return f"user={user}\x01auth=Bearer {access_token}\x01\x01"
