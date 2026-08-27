"""
manager.py -- Orchestration layer.

Ties inventory + vault + transport + driver + store + scrubber + session recorder
into two operations the rest of the app calls:

    collect(device_name)          -> fetch & archive one device's config
    run(device_name, command)     -> run an arbitrary command, return output

The vault must be unlocked (unlock_vault) before collecting devices that use
password/enable secrets. Key-only devices need no vault.

Errors are captured per-device so a batch run over 200 switches doesn't abort on
the one that's powered off; each device's outcome is logged to the run table.
"""

import os
import concurrent.futures
import time

from . import config as _cfg
from . import automation as _auto
from . import snmp as _snmp
from . import ifhistory as _ifhistory
from .db import Database
from .inventory import Inventory
from .users import Users
from .vault import Vault
from .store import ConfigStore
from .session import SessionRecorder
from .transport import SSHTransport, TransportError, AuthError
from .drivers import get_driver, DriverError


def _remediation_lines(baseline_text):
    """Turn a stored baseline config into config-mode command lines.

    Honest limitation: a captured 'show running-config' is not a clean config
    script. This filters the obvious non-command noise (comment markers, blank
    lines, the "Building configuration" / "Current configuration" / "version"
    headers) and replays the rest. That cleanly re-asserts additive settings that
    drifted; it does NOT compute negations, so it will not by itself remove lines
    that were *added* to a device. Drift *detection* is the always-safe feature;
    remediation is a best-effort convenience, gated behind approval + opt-in.
    """
    out = []
    for raw in baseline_text.splitlines():
        s = raw.rstrip()
        st = s.strip()
        if not st:
            continue
        if st == "!" or st.startswith("! "):
            continue
        low = st.lower()
        if low.startswith(("building configuration", "current configuration",
                           "version ", "boot-start-marker", "boot-end-marker",
                           "end")):
            continue
        out.append(s)
    return out


class CollectionResult:
    def __init__(self, device, ok, changed=False, message="", version=None,
                 diff="", config=None, session_path=None):
        self.device = device
        self.ok = ok
        self.changed = changed
        self.message = message
        self.version = version
        self.diff = diff
        self.config = config
        self.session_path = session_path

    def __repr__(self):
        state = "OK" if self.ok else "FAIL"
        ch = " changed" if self.changed else ""
        return f"<{self.device} {state}{ch}: {self.message}>"


def _dtypes_m(dev):
    import re as _re
    raw = (dev.get("device_type") or "") if dev else ""
    ts = {t for t in _re.split(r"[,\s]+", raw) if t}
    return ts or {"network"}


class Manager:
    def __init__(self, home=None):
        self.paths = _cfg.Paths(home)
        self.settings = _cfg.load_settings(self.paths)
        self.db = Database(self.paths.inventory_db)
        self.inv = Inventory(self.db.conn)
        self.users = Users(self.db.conn)
        self.vault = Vault(self.paths.vault_file)
        self.store = ConfigStore(self.paths.configs_dir,
                                 keep_versions=self.settings["keep_versions"])
        self.recorder = SessionRecorder(
            self.paths.sessions_dir,
            enabled=self.settings["record_sessions"],
            do_scrub=self.settings["scrub_sessions"])
        self._vault_unlocked = False
        # optional long-term interface-history backend (PostgreSQL); rebuilt when
        # the relevant settings change. None when disabled or unconfigured.
        self._ifhist = None
        self._ifhist_key = None
        from . import mib as _mib
        self.mibindex = _mib.MibIndex(os.path.join(str(self.paths.home), "mibs"))
        if not self.mibindex.load():
            try:
                self.mibindex.rebuild()
            except Exception:
                pass

    def rebuild_mibindex(self):
        try:
            return self.mibindex.rebuild()
        except Exception:
            return 0
    def unlock_vault(self, master_password):
        if self.vault.exists():
            self.vault.unlock(master_password)
            self._vault_unlocked = True

    def vault_ready(self):
        return self._vault_unlocked or not self.vault.exists()

    def _creds_for(self, device):
        """Return (password, key_path, key_passphrase, enable_password)."""
        password = key_path = key_pass = enable_pw = None
        ref = device.get("secret_ref")
        if ref:
            if not self._vault_unlocked:
                raise RuntimeError(f"vault locked; needed for device {device['name']}")
            try:
                sec = self.vault.get_secret(ref)
            except KeyError:
                raise RuntimeError(
                    f"{device['name']} points at vault secret '{ref}', which does not exist.")
            password = sec.get("password")
            key_path = sec.get("key_path")
            key_pass = sec.get("key_passphrase")
            enable_pw = sec.get("enable_password")
        en_ref = device.get("enable_ref")
        if en_ref and self._vault_unlocked:
            try:
                enable_pw = self.vault.get_secret(en_ref).get("password") or enable_pw
            except KeyError:
                pass
        return password, key_path, key_pass, enable_pw

    # ---- core ops --------------------------------------------------------
    def _connect(self, device):
        name = device["name"]
        ref = device.get("secret_ref")
        if not ref:
            raise RuntimeError(
                f"{name} has no SSH credential. Add one with "
                f"`netconfig device set-cred {name} --username U --ask-password`. "
                f"If this device is SNMP-only, use `netconfig snmp poll {name}` instead of collect.")
        if not self._vault_unlocked:
            raise RuntimeError(
                "vault is locked (needed to read SSH credentials). Provide the master via "
                "NETCONFIG_MASTER, or run in a terminal to be prompted; under sudo use `sudo -E`.")
        try:
            sec = self.vault.get_secret(ref)
        except KeyError:
            raise RuntimeError(
                f"{name} points at vault secret '{ref}', which does not exist. "
                f"`--secret` takes a vault label, not a password. Create it with "
                f"`netconfig vault set {ref} --username U --ask-password`, or fix the device.")
        username = sec.get("username")
        if not username:
            raise RuntimeError(
                f"vault secret '{ref}' has no username (SSH needs one). "
                f"Set it: `netconfig vault set {ref} --username U`.")
        password, key_path, key_pass, enable_pw = self._creds_for(device)
        tp = SSHTransport(
            device["host"], username, port=device["port"],
            password=None if device["use_key"] else password,
            key_path=key_path if device["use_key"] else None,
            key_passphrase=key_pass,
            connect_timeout=self.settings["connect_timeout"],
            command_timeout=self.settings["command_timeout"],
            known_hosts=self.paths.known_hosts,
            host_key_policy=self.settings["host_key_policy"],
            legacy=device["legacy"])
        tp.connect()
        return tp, enable_pw

    def collect(self, device_name):
        device = self.inv.get(device_name)
        if not device:
            return CollectionResult(device_name, False, message="unknown device")
        if not (_dtypes_m(device) & {"system", "network"}):
            return CollectionResult(
                device_name, False,
                message="application-only endpoint has no SSH configuration to collect")
        tp = None
        try:
            tp, enable_pw = self._connect(device)
            driver = get_driver(device["platform"])
            tp.discover_prompt()
            driver.initialize(tp, enable_password=enable_pw)
            raw = driver.fetch_config(tp)
            from . import scrub as _scrub
            stored = raw
            if device["scrub"]:
                stored, _ = _scrub.scrub(raw)
            result = self.store.save(device_name, stored)
            spath = self.recorder.write(device_name, tp.transcript)
            self.inv.log_run(device_name, True, result["changed"],
                             "changed" if result["changed"] else "no change")
            return CollectionResult(
                device_name, True, changed=result["changed"],
                message="changed" if result["changed"] else "no change",
                version=result["version"], diff=result["diff"],
                config=stored, session_path=spath)
        except (AuthError, TransportError, DriverError, RuntimeError) as e:
            msg = f"{type(e).__name__}: {e}"
            if tp is not None:
                self.recorder.write(device_name, tp.transcript)
            self.inv.log_run(device_name, False, False, msg)
            return CollectionResult(device_name, False, message=msg)
        finally:
            if tp is not None:
                tp.close()

    def collect_all(self, only_enabled=True):
        results = []
        for dev in self.inv.all(only_enabled=only_enabled):
            if not (_dtypes_m(dev) & {"system", "network"}):
                continue
            results.append(self.collect(dev["name"]))
        return results

    def rename_device(self, old, new):
        """Rename a device everywhere: inventory + facts/stats + groups + the
        config archive directory."""
        new = (new or "").strip()
        if not new:
            raise ValueError("new name is empty")
        self.inv.rename(old, new)
        try:
            self.store.rename(old, new)
        except Exception:
            pass
        self.db.audit("system", "device_rename", old, new)

    def backup(self, keep=5, only_enabled=True):
        """Weekly-style backup: collect every (enabled) device's current config
        and trim each device's archive to `keep` copies. Returns a summary list
        of {device, ok, changed, kept, error}."""
        summary = []
        for dev in self.inv.all(only_enabled=only_enabled):
            name = dev["name"]
            r = self.collect(name)
            kept = None
            try:
                kept = self.store.prune(name, keep)
            except Exception:
                pass
            summary.append({"device": name, "ok": r.ok,
                            "changed": getattr(r, "changed", None),
                            "kept": kept,
                            "error": None if r.ok else r.message})
        return summary

    def run(self, device_name, command):
        device = self.inv.get(device_name)
        if not device:
            raise RuntimeError("unknown device")
        tp = None
        try:
            tp, enable_pw = self._connect(device)
            driver = get_driver(device["platform"])
            tp.discover_prompt()
            driver.initialize(tp, enable_password=enable_pw)
            out = driver.run(tp, command)
            self.recorder.write(device_name, tp.transcript)
            return out
        finally:
            if tp is not None:
                tp.close()

    # ---- bulk automation -------------------------------------------------
    def _apply_one(self, device, mode, body=None, extra_vars=None, save=False):
        """Run one device's part of a bulk job. Returns a result dict. Opens its
        own transport so callers can run these concurrently. No DB writes here --
        the caller persists results, keeping SQLite single-writer."""
        name = device["name"]
        tp = None
        try:
            if mode == "remediate":
                base = self.store.baseline_text(name)
                if base is None:
                    return {"device": name, "ok": False, "changed": False,
                            "output": "no baseline set"}
                lines = _remediation_lines(base)
                resolved_unresolved = []
            else:
                text, unresolved = _auto.substitute(body or "", device, extra_vars)
                lines = _auto.commands(text)
                resolved_unresolved = unresolved
            if resolved_unresolved:
                return {"device": name, "ok": False, "changed": False,
                        "output": "unresolved variables: "
                                  + ", ".join(sorted(set(resolved_unresolved)))}
            tp, enable_pw = self._connect(device)
            driver = get_driver(device["platform"])
            tp.discover_prompt()
            driver.initialize(tp, enable_password=enable_pw)
            if mode == "command":
                out = "\n".join(driver.run(tp, c) for c in lines)
                errors = []
            else:  # config | remediate
                out, errors = driver.apply_lines(tp, lines, save=save)
            self.recorder.write(name, tp.transcript)
            ok = not errors
            msg = out if ok else (out + "\n[errors] " +
                                  "; ".join(f"{l}: {e}" for l, e in errors))
            return {"device": name, "ok": ok, "changed": bool(lines and mode != "command"),
                    "output": msg}
        except (AuthError, TransportError, DriverError, RuntimeError) as e:
            if tp is not None:
                self.recorder.write(name, tp.transcript)
            return {"device": name, "ok": False, "changed": False,
                    "output": f"{type(e).__name__}: {e}"}
        finally:
            if tp is not None:
                tp.close()

    def bulk(self, devices, *, mode="command", body=None, extra_vars=None,
             save=False, max_workers=None, on_result=None):
        """Run `mode` across `devices` concurrently. mode in command|config|
        remediate. Returns a list of per-device result dicts. `on_result` is an
        optional callback(result) invoked as each finishes (in the main thread)."""
        if not self._vault_unlocked and not self.vault_ready():
            raise RuntimeError("vault locked; unlock before running jobs")
        workers = max_workers or self.settings.get("bulk_workers", 5)
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._apply_one, d, mode, body, extra_vars, save): d
                    for d in devices}
            for fut in concurrent.futures.as_completed(futs):
                r = fut.result()
                results.append(r)
                if on_result:
                    on_result(r)
        results.sort(key=lambda r: r["device"])
        return results

    # ---- drift / remediation --------------------------------------------
    def check_drift(self, device_name):
        return self.store.drift(device_name)

    def remediate(self, device_name, save=False):
        dev = self.inv.get(device_name)
        if not dev:
            return {"device": device_name, "ok": False, "output": "unknown device"}
        return self._apply_one(dev, "remediate", save=save)

    # ---- SNMP ------------------------------------------------------------
    def _snmp_params_for(self, device):
        ref = device.get("snmp_ref")
        sec = {}
        if ref:
            if not self._vault_unlocked:
                raise RuntimeError("vault locked; needed for SNMP credentials")
            sec = self.vault.get_secret(ref)
        version = device.get("snmp_version") or "v2c"
        port = int(sec.get("snmp_port") or self.settings.get("snmp_port", 161))
        if version == "v3":
            v3 = _snmp.V3Params(
                sec.get("snmp_user") or sec.get("username") or "",
                auth_proto=sec.get("snmp_auth_proto"),
                auth_pass=sec.get("snmp_auth_pass"),
                priv_proto=sec.get("snmp_priv_proto"),
                priv_pass=sec.get("snmp_priv_pass"))
            return version, None, v3, port
        community = sec.get("community") or sec.get("snmp_community") or "public"
        return version, community, None, port

    def snmp_walk(self, device_name, root="1.3.6.1.2.1.1", max_vars=400):
        """Walk an OID subtree and resolve each OID to a name via the MIB automap.
        Returns list of {oid, name, value}."""
        dev = self.inv.get(device_name)
        if not dev:
            raise RuntimeError("unknown device")
        version, community, v3, port = self._snmp_params_for(dev)
        pairs = _snmp.walk_subtree(dev["host"], root, version=version, community=community,
                                   v3=v3, port=port,
                                   timeout=self.settings.get("snmp_timeout", 2.0),
                                   max_vars=max_vars)
        out = []
        for oid, val in pairs:
            mapped = self.mibindex.resolve_detail(oid)
            out.append({"oid": oid, "name": mapped["name"], "value": val,
                        "mib_source": mapped["source"], "mapped": mapped["mapped"]})
        return out

    def _poll_vendor_mibs(self, device_name, dev, facts, version, community, v3, port,
                          force=False):
        """Collect uploaded-MIB OBJECT-TYPE values with strict load limits."""
        roots = self.mibindex.collection_roots(facts.get("sysobjectid", ""), max_roots=12)
        if not roots:
            self.db.set_mib_values(device_name, [], roots=0)
            return {"objects": 0, "roots": 0, "skipped": "no matching vendor MIB objects"}
        previous = self.db.get_mib_poll_status(device_name)
        min_interval = max(300, int(self.settings.get("snmp_poll_interval", 0) or 0) * 10)
        if (not force and previous and
                time.time() - float(previous.get("ts") or 0) < min_interval):
            return {"objects": previous.get("objects", 0),
                    "roots": previous.get("roots", 0), "skipped": "not due"}

        found = {}
        errors = []
        total_limit = 400
        for spec in roots:
            remaining = total_limit - len(found)
            if remaining <= 0:
                break
            try:
                pairs = _snmp.walk_subtree(
                    dev["host"], spec["root"], version=version, community=community,
                    v3=v3, port=port, timeout=self.settings.get("snmp_timeout", 2.0),
                    max_vars=min(80, remaining))
                for oid, value in pairs:
                    detail = self.mibindex.resolve_detail(oid)
                    found[oid] = {"oid": oid, "name": detail["name"], "value": value,
                                  "mib_source": detail["source"] or spec["source"]}
            except Exception as exc:
                errors.append(f'{spec["source"]} {spec["root"]}: {exc}')
        error = "; ".join(errors[:5])
        self.db.set_mib_values(device_name, list(found.values()), roots=len(roots), error=error)
        return {"objects": len(found), "roots": len(roots), "error": error}

    def _pg_password(self):
        """DB password from the vault (like the SMTP/O365 secrets), or "" when
        the vault is locked or no password is stored."""
        try:
            if self._vault_unlocked:
                return self.vault.get_secret(_ifhistory.VAULT_SECRET).get("password") or ""
        except Exception:
            pass
        return ""

    def _history_backend(self):
        """Current interface-history backend, rebuilt if its settings (or the
        resolved DB password) changed. Returns None when disabled/unconfigured."""
        pw = self._pg_password()
        key = (bool(self.settings.get("if_history_enabled")),
               (self.settings.get("if_history_dsn") or "").strip(),
               self.settings.get("pg_host"), self.settings.get("pg_port"),
               self.settings.get("pg_dbname"), self.settings.get("pg_user"),
               self.settings.get("pg_sslmode"),
               self.settings.get("if_history_hours", 24), bool(pw))
        if key != self._ifhist_key:
            self._ifhist_key = key
            self._ifhist = _ifhistory.get_backend(self.settings, password=pw)
        return self._ifhist

    def snmp_poll(self, device_name, interfaces=True, vendor_force=False):
        dev = self.inv.get(device_name)
        if not dev:
            return {"ok": False, "error": "unknown device"}
        try:
            version, community, v3, port = self._snmp_params_for(dev)
            facts = _snmp.poll_system(dev["host"], port=port, version=version,
                                      community=community, v3=v3,
                                      timeout=self.settings.get("snmp_timeout", 2.0))
            self.inv.set_facts(device_name, **facts)
            vendor_result = self._poll_vendor_mibs(
                device_name, dev, facts, version, community, v3, port,
                force=vendor_force)
            iface_count = None
            if interfaces:
                try:
                    ifs = _snmp.poll_interfaces(
                        dev["host"], port=port, version=version, community=community,
                        v3=v3, timeout=self.settings.get("snmp_timeout", 2.0))
                    samples = self.inv.set_interfaces(
                        device_name, ifs,
                        history_seconds=self.settings.get("snmp_history_seconds", 1800))
                    iface_count = len(ifs)
                    backend = self._history_backend()
                    if backend is not None and samples:
                        # best-effort: a history-store failure must never abort a poll
                        try:
                            backend.write(device_name, samples)
                        except Exception:
                            pass
                    if "network" in _dtypes_m(dev):
                        try:
                            ifdescr = {str(i["ifindex"]): i.get("descr", "") for i in ifs}
                            arp = _snmp.poll_arp(dev["host"], port=port, version=version,
                                                 community=community, v3=v3,
                                                 timeout=self.settings.get("snmp_timeout", 2.0))
                            mac = _snmp.poll_mac_table(dev["host"], port=port, version=version,
                                                       community=community, v3=v3,
                                                       timeout=self.settings.get("snmp_timeout", 2.0),
                                                       ifdescr=ifdescr)
                            self.db.set_arp(device_name, arp)
                            self.db.set_mac_table(device_name, mac)
                        except Exception:
                            pass
                except Exception as e:
                    # system poll succeeded; interface walk is best-effort
                    iface_count = f"iface walk failed: {e}"
            return {"ok": True, "interfaces": iface_count,
                    "vendor_mib": vendor_result, **facts}
        except Exception as e:
            self.inv.set_facts(device_name, reachable=False, error=str(e))
            return {"ok": False, "error": str(e)}

    def snmp_poll_all(self, vendor_force=False):
        """Poll every SNMP-enabled device. Returns {device: result}."""
        out = {}
        for d in self.inv.all():
            if d.get("snmp_version"):
                out[d["name"]] = self.snmp_poll(d["name"], vendor_force=vendor_force)
        return out

    def close(self):
        self.db.close()
