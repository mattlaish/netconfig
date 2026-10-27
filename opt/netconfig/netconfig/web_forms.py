"""Validated console form changes and same-site operation feedback."""
from __future__ import annotations

import time
import math
import re
import uuid
import urllib.parse

from . import config
from .users import can
from .manager import validate_config_collect_command


SECRET_FIELDS = {"ssh_password", "enable_password", "key_passphrase", "community",
                 "snmp_auth_pass", "snmp_priv_pass", "smtp_password",
                 "o365_client_secret", "if_history_pg_password", "master"}


def safe_draft(form):
    return {k: list(v) for k, v in form.items() if k not in SECRET_FIELDS}


def feedback(handler, sess, target, message):
    from .web_ux import safe_next_path
    target = safe_next_path(target) or "/"
    sess["operation_feedback"] = {"target": target.split("#", 1)[0],
                                  "message": str(message)[:1000], "expires": time.time() + 120}
    return handler._redirect(target)


def take_feedback(handler, sess):
    if not sess:
        return None
    item = sess.get("operation_feedback")
    if not item:
        return None
    if item["expires"] < time.time():
        sess.pop("operation_feedback", None)
    elif getattr(handler, "path", "").split("#", 1)[0] == item["target"]:
        sess.pop("operation_feedback", None)
        return item["message"]
    return None


def numeric_value(key, raw):
    """Zero means off only for interval/retention fields which support it."""
    label = {"netflow_max_flows": "Recent flows kept per device",
             "web_port": "Web port", "netflow_port": "NetFlow port",
             "snmp_timeout": "SNMP timeout"}.get(key, key.replace("_", " ").capitalize())
    low, high = 0, 31536000
    if key.endswith("port"):
        low, high = 1, 65535
    elif key == "netflow_max_flows":
        low, high = 1, 1000000
    elif key == "bulk_workers":
        low, high = 1, 256
    elif key in {"connect_timeout", "command_timeout", "snmp_timeout"}:
        low, high = 0.1 if key == "snmp_timeout" else 1, 3600
    elif key.endswith("queue_size"):
        low, high = 1, 1000000
    elif key in {"keep_versions", "backup_keep", "debug_bundle_keep",
                 "operational_notification_max_attempts", "cluster_stale_seconds",
                 "distributed_task_lease_seconds", "if_history_hours", "if_history_bucket_seconds"}:
        low, high = 1, 1000000
    try:
        value = float(raw) if key == "snmp_timeout" else int(raw)
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError
    except (ValueError, OverflowError):
        kind = "a number" if key == "snmp_timeout" else "a whole number"
        raise ValueError(f"{label}: enter {kind} from {low} to {high}.") from None
    return value


def commit_settings(manager, candidate, secrets=()):
    """Save secrets before publishing settings; compensate failed writes."""
    if secrets and (not manager.vault_ready() or not manager.vault.exists()):
        raise ValueError("Settings not saved. Unlock or create the vault before saving a new password or client secret. Re-enter secret fields after unlocking.")
    before, attempted = {}, []
    try:
        for name, fields in secrets:
            try:
                before[name] = dict(manager.vault.get_secret(name))
            except KeyError:
                before[name] = None
            attempted.append(name)
            manager.vault.set_secret(name, **{**(before[name] or {}), **fields})
        config.save_settings(manager.paths, candidate)
    except Exception:
        restored = True
        for name in reversed(attempted):
            try:
                if before[name] is None:
                    manager.vault.delete_secret(name)
                else:
                    manager.vault.set_secret(name, **before[name])
            except Exception:
                restored = False
        suffix = (" Previous credentials restored." if attempted and restored else
                  " Credential recovery needs administrator review." if attempted else "")
        raise ValueError("Settings not saved: storage could not be updated. Check storage access and try again. Re-enter secret fields." + suffix) from None
    manager.settings.update(candidate)


_OWNED_SUFFIX = re.compile(r"-(?:ssh|snmp)-[0-9a-f]{32}")


def device_owned_ref(ref, name):
    """True for vault entries created by the device form for this device only:
    ``<name>-ssh-<uuid>`` / ``<name>-snmp-<uuid>``, or the legacy ``<name>-cred``."""
    ref, name = str(ref or ""), str(name or "")
    if not name or not ref.startswith(name + "-"):
        return False
    return ref == name + "-cred" or bool(_OWNED_SUFFIX.fullmatch(ref[len(name):]))


def _release_replaced_refs(m, old, names, keep):
    """Delete this device's previous own credential entries once nothing uses them.

    Shared (user-named) secrets are never deleted. Failures are ignored: an
    orphaned entry is harmless, deleting a referenced one is not."""
    candidates = {old.get(k) for k in ("secret_ref", "snmp_ref", "enable_ref")} - set(keep) - {None, ""}
    candidates = {r for r in candidates if any(device_owned_ref(r, n) for n in names)}
    if not candidates or not m.vault_ready():
        return
    try:
        used = set()
        for dev in m.inv.all():
            used.update(dev.get(k) for k in ("secret_ref", "snmp_ref", "enable_ref"))
        for prof in m.protocol_profiles.list():
            used.add(prof.get("secret_ref"))
    except Exception:
        return
    for ref in candidates - used:
        try:
            m.vault.delete_secret(ref)
        except Exception:
            pass


def save_device(handler, form, sess):
    if not can(sess["role"], "manage_devices"):
        return handler._dashboard(sess, flash="Not permitted.")
    m = handler.manager
    def g(key, default=""):
        return (form.get(key) or [default])[0]
    name, orig = g("name").strip(), g("orig_name").strip()
    def error(message):
        return handler._device_form({"name": [orig]}, sess, draft=safe_draft(form),
                                    flash=message + " Secret fields must be re-entered.", status=400)
    types = [t for t in form.get("device_type", []) if t in {"system", "network", "application"}] or ["network"]
    app = set(types) == {"application"}
    old = m.inv.get(orig or name) or {}
    mode = g("cred_mode") or ("manual" if any(g(k) for k in ("ssh_username", "ssh_password", "snmp_user", "community")) else "saved")
    try:
        if not name or not g("host").strip():
            raise ValueError("Device name and host are required.")
        if orig and not old:
            raise ValueError("The original device no longer exists. Reload Devices before trying again.")
        if orig != name and m.inv.get(name):
            raise ValueError("That device name is already in use.")
        if not orig and old:
            raise ValueError("That device name is already in use. Open Edit device instead.")
        port = 22 if app else numeric_value("ssh_port", g("port", "22") or "22")
        command = "" if app else validate_config_collect_command(g("config_collect_command"))
        if mode not in {"manual", "saved"}:
            raise ValueError("Choose saved credentials or credentials for this device.")
        if not app and g("snmp_port"):
            numeric_value("snmp_port", g("snmp_port"))
    except ValueError as exc:
        return error(f"Device not saved: {exc}")
    ssh_ref = g("secret_ref", old.get("secret_ref") or "").strip()
    snmp_ref = g("snmp_ref", old.get("snmp_ref") or "").strip()
    enable_ref = g("enable_ref", old.get("enable_ref") or "").strip()
    staged = []
    renamed = False
    try:
        if not app and mode == "manual":
            ssh = {key: g(field) for key, field in (("username", "ssh_username"), ("password", "ssh_password"),
                   ("enable_password", "enable_password"), ("key_path", "key_path"), ("key_passphrase", "key_passphrase"))}
            snmp = {k: g(k) for k in ("snmp_user", "community", "snmp_auth_proto", "snmp_auth_pass", "snmp_priv_proto", "snmp_priv_pass", "snmp_port")}
            if any(ssh.values()) or any(snmp.values()):
                if not m.vault_ready() or not m.vault.exists():
                    return error("Device not saved: unlock or create the vault before saving credentials.")
                for fields, previous, kind in ((ssh, old.get("secret_ref"), "ssh"), (snmp, old.get("snmp_ref"), "snmp")):
                    if not any(fields.values()):
                        continue
                    merged = dict(m.vault.get_secret(previous)) if previous else {}
                    if kind == "ssh" and old.get("enable_ref"):
                        enabled = m.vault.get_secret(old["enable_ref"])
                        merged["enable_password"] = enabled.get("enable_password") or enabled.get("password", "")
                    unchanged = dict(merged)
                    merged.update({k: v for k, v in fields.items() if v})
                    if previous and merged == unchanged and device_owned_ref(previous, orig or name) and not (orig and orig != name):
                        continue  # nothing new for this device's own entry; keep it
                    ref = f"{name}-{kind}-{uuid.uuid4().hex}"
                    staged.append(ref)
                    m.vault.set_secret(ref, **merged)
                    if kind == "ssh":
                        ssh_ref = ref
                        if merged.get("enable_password"):
                            enable_ref = ref
                    else:
                        snmp_ref = ref
        if orig and orig != name:
            m.rename_device(orig, name)
            renamed = True
        m.inv.upsert(name=name, host=g("host").strip(), port=port,
            platform="generic" if app else g("platform").strip() or "generic", device_type=",".join(types),
            secret_ref="" if app else ssh_ref, snmp_ref="" if app else snmp_ref,
            enable_ref="" if app else enable_ref, snmp_version="" if app else g("snmp_version").strip(),
            use_key=False if app else bool(form.get("use_key")), legacy=False if app else bool(form.get("legacy")),
            scrub=False if app else bool(form.get("scrub")), enabled=bool(form.get("enabled")),
            netflow=False if app else bool(form.get("netflow")), monitor_ports="" if app else g("monitor_ports"),
            monitor_urls=g("monitor_urls"), config_collect_command=command,
            tags=g("tags").replace(",", " ").split(), notes=g("notes"))
    except Exception:
        # Cross-file vault/archive/inventory changes are not one DB transaction.
        # Do not claim an atomic rollback after a storage failure.
        try:
            current = m.inv.get(name) or {}
            renamed = renamed or bool(orig and orig != name and current and not m.inv.get(orig))
            attached = any(current.get(k) in staged for k in ("secret_ref", "snmp_ref", "enable_ref"))
        except Exception:
            # Outcome cannot be established. Never delete possibly referenced secrets.
            return handler._dashboard(sess, flash="Device save outcome could not be confirmed. Review inventory and credentials before retrying.")
        if renamed or attached:
            detail = f" after renaming to '{name}'" if renamed else ""
            return handler._dashboard(sess, flash=f"Device save interrupted{detail}. Review this device and its credentials before retrying.")
        for ref in staged:
            try:
                m.vault.delete_secret(ref)
            except Exception:
                pass
        return error("Device not saved: credentials or inventory could not be updated. Check storage access and saved credential names.")
    m.db.audit(sess["username"], "device_save", name, g("host"))
    if not app:
        _release_replaced_refs(m, old, {orig, name}, {ssh_ref, snmp_ref, enable_ref})
    else:
        _release_replaced_refs(m, old, {orig, name}, set())
    return handler._redirect("/device?" + urllib.parse.urlencode({"name": name}))
