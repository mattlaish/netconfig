"""Zero-dependency SMTP mailer for alert notifications (stdlib smtplib + email).

SMTP configuration lives in settings (host/port/from/to/starttls/user). The
password, if any, is kept in the vault under the reserved secret name
``__smtp__`` (key ``password``) so it is never written to settings.json.
"""
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate

SMTP_SECRET = "__smtp__"


def smtp_config(settings):
    return {
        "enabled": bool(settings.get("smtp_enabled")),
        "host": settings.get("smtp_host", ""),
        "port": int(settings.get("smtp_port", 587) or 587),
        "starttls": bool(settings.get("smtp_starttls", True)),
        "user": settings.get("smtp_user", ""),
        "from": settings.get("smtp_from", ""),
        "to": settings.get("smtp_to", ""),
    }


def _recipients(cfg):
    return [a.strip() for a in (cfg.get("to") or "").replace(";", ",").split(",") if a.strip()]


def resolve_auth(manager):
    """Return (password, oauth_token) for the SMTP send, based on settings.
    O365 OAuth (XOAUTH2) takes precedence when enabled; else the vault SMTP
    password; else neither (open relay)."""
    settings = manager.settings
    if settings.get("o365_enabled"):
        from . import oauth
        secret = None
        try:
            if manager.vault_ready():
                secret = manager.vault.get_secret(oauth.O365_SECRET).get("client_secret")
        except Exception:
            secret = None
        tok, _err = oauth.get_token(settings, secret)
        return None, (tok.get("access_token") if tok else None)
    pw = None
    try:
        if manager.vault_ready():
            pw = manager.vault.get_secret(SMTP_SECRET).get("password")
    except Exception:
        pw = None
    return pw, None


def send_mail(settings, subject, body, password=None, oauth_token=None,
              timeout=10, _smtp=smtplib.SMTP):
    """Send a plain-text email using the SMTP settings. Returns (ok, message).
    Authentication: XOAUTH2 with `oauth_token` (Office 365 modern auth) if given,
    otherwise LOGIN with `user`+`password`, otherwise unauthenticated (open relay).
    `_smtp` is injectable for testing."""
    cfg = smtp_config(settings)
    if not cfg["host"]:
        return False, "no SMTP host configured"
    to = _recipients(cfg)
    if not to:
        return False, "no recipients configured"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"] or (cfg["user"] or "netconfig@localhost")
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    try:
        server = _smtp(cfg["host"], cfg["port"], timeout=timeout)
        try:
            server.ehlo()
            if cfg["starttls"]:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if oauth_token and cfg["user"]:
                from . import oauth
                server.auth("XOAUTH2",
                            lambda: oauth.xoauth2_string(cfg["user"], oauth_token))
            elif cfg["user"] and password:
                server.login(cfg["user"], password)
            server.send_message(msg)
        finally:
            try:
                server.quit()
            except Exception:
                pass
        return True, f"sent to {', '.join(to)}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
