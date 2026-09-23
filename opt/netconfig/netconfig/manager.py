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
from .inventory import Inventory
from .users import Users
from .incidents import Incidents
from .caseexport import SupportCaseExporter
from .protocoltrace import ProtocolTraceStore
from .operational_events import OperationalEventStore
from .operational_alerts import OperationalAlertLifecycle
from .vault import Vault
from .store import ConfigStore
from .session import SessionRecorder
from .transport import SSHTransport, TransportError, AuthError
from .drivers import get_driver, DriverError
from . import configmodel as _configmodel
from .observability import METRICS, event as _obs_event
from . import topology as _topology
from . import network_intelligence as _network_intelligence
from .structured_protocols import ProtocolProfiles, StructuredCollector


def _remediation_lines(baseline_text):
    """Legacy compatibility helper returning cleaned baseline commands.

    New remediation uses a fresh running-config plus semantic planning so added
    rogue lines can be removed. This helper remains for callers/tests that only
    need normalized baseline text.
    """
    return _configmodel.clean_lines(baseline_text)


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
        from .credentials import postgres_core_password
        from .postgres_core import build_core_database
        db_password, db_password_source = postgres_core_password()
        self.db = build_core_database(
            self.settings, self.paths.inventory_db, password=db_password)
        self.core_db_password_source = db_password_source
        from .storage_backend import StorageBackend
        self.storage = StorageBackend(self.db)
        import socket as _socket
        self.cluster_node_id = (str(self.settings.get("cluster_node_id") or "").strip() or
                                f"{_socket.gethostname()}:{os.getpid()}")
        try:
            self.db.register_cluster_node(
                self.cluster_node_id, _socket.gethostname(), os.getpid(), time.time())
        except Exception:
            # PostgreSQL selection itself is fail-closed at connection/schema time;
            # heartbeat metadata must not block SQLite development startup.
            if getattr(self.db, "dialect", "sqlite") == "postgres":
                raise
        self.inv = Inventory(self.storage.conn)
        from .sensor import SensorEngine
        self.sensors = SensorEngine(self.storage.conn)
        self.users = Users(self.storage.conn)
        self.vault = Vault(self.paths.vault_file)
        self.store = ConfigStore(self.paths.configs_dir,
                                 keep_versions=self.settings["keep_versions"])
        self.incidents = Incidents(
            self.db, os.path.join(str(self.paths.home), "debug-bundles"), self.store)
        self.case_exports = SupportCaseExporter(self)
        self.protocol_traces = ProtocolTraceStore(self)
        self.protocol_profiles = ProtocolProfiles(self)
        self.structured_collector = StructuredCollector(self)
        from .vendor_models import VendorModelRegistry
        from .structured_changes import StructuredChangeEngine
        from .telemetry import TelemetryService
        from .desired_state import DesiredStateService
        from .campaigns import CampaignService
        from .ha import HAService
        from .analytics import AnalyticsService
        self.vendor_models = VendorModelRegistry(self)
        self.structured_changes = StructuredChangeEngine(self)
        self.telemetry = TelemetryService(self)
        self.desired_state = DesiredStateService(self)
        self.campaigns = CampaignService(self)
        self.ha = HAService(self)
        self.analytics = AnalyticsService(self)
        self.alert_lifecycle = OperationalAlertLifecycle(self)
        self.events = OperationalEventStore(self)
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
            except KeyError as exc:
                raise RuntimeError(
                    f"{device['name']} points at vault secret '{ref}', which does not exist.") from exc
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

    def device_by_host(self, host):
        needle = str(host or "").strip().lower()
        for dev in self.inv.all():
            if str(dev.get("host", "")).strip().lower() == needle:
                return dev
        return None

    def topology(self):
        return self.db.get_neighbors()

    def topology_identities(self):
        inventory = []
        for item in self.inv.all():
            enriched = dict(item)
            facts = self.inv.get_facts(item["name"]) or {}
            enriched["sysname"] = facts.get("sysname", "")
            inventory.append(enriched)
        return _topology.identity_view(
            inventory, self.db.get_topology_device_identities(),
            self.db.get_topology_interfaces())

    def topology_graph(self):
        """Return a read-only managed topology graph from persisted evidence.

        No device I/O occurs here.  LLDP/CDP rows are OBSERVED adjacency;
        FDB matches against managed interface/chassis MACs are INFERRED path
        evidence only.  Every managed inventory device is represented.
        """
        inventory = []
        for item in self.inv.all():
            enriched = dict(item)
            facts = self.inv.get_facts(item["name"]) or {}
            enriched["sysname"] = facts.get("sysname", "")
            inventory.append(enriched)
        fdb_rows = list(self.db.get_vlan_fdb())
        seen = {(r.get("device", ""), str(r.get("mac", "")).lower(),
                 str(r.get("ifindex", "")), str(r.get("bridge_port", ""))) for r in fdb_rows}
        # Preserve compatibility with older databases that have only the legacy
        # mac_table populated.  This is persisted evidence reuse, not extra I/O.
        for dev in inventory:
            for row in self.db.get_mac_table(dev["name"]):
                key = (dev["name"], str(row.get("mac", "")).lower(),
                       str(row.get("ifindex", "")), str(row.get("port", "")))
                if key in seen:
                    continue
                fdb_rows.append({
                    "device": dev["name"], "mac": row.get("mac", ""),
                    "bridge_port": row.get("port", ""), "ifindex": row.get("ifindex", ""),
                    "ifdescr": row.get("ifdescr", ""), "vlan_id": "",
                    "source": "legacy-mac-table", "ts": row.get("ts"),
                })
                seen.add(key)
        return _topology.build_graph(
            self.db.get_neighbors(), inventory,
            self.db.get_topology_device_identities(),
            self.db.get_topology_interfaces(), fdb_rows)

    def downstream_impact(self, device, port=None, max_depth=16):
        if not self.inv.get(device):
            raise ValueError("unknown root device")
        return _topology.downstream_impact(
            self.db.get_neighbors(), device, root_port=port, max_depth=max_depth)

    def _refresh_topology_identity(self, dev, version, community, v3, port, facts=None,
                                   interfaces=None):
        """Best-effort bounded local identity collection for NI-2.

        Missing LLDP/ENTITY-MIB support never fails the parent SNMP poll.  The
        inventory/facts identity remains available, while unsupported fields
        stay empty instead of being guessed from arbitrary components.
        """
        timeout = self.settings.get("snmp_timeout", 2.0)
        trace_cb = self.protocol_traces.callback(dev["name"], "snmp")
        local_pairs = []
        entity_rows = {}
        try:
            with _snmp.trace_capture(trace_cb):
                local_pairs = _snmp.get_oids(
                    dev["host"], list(_topology.LLDP_LOCAL_IDENTITY.values()),
                    version=version, community=community, v3=v3, port=port,
                    timeout=timeout)
        except Exception as exc:
            _obs_event("topology_local_identity_lldp_failed", device=dev["name"], error=str(exc))
        try:
            with _snmp.trace_capture(trace_cb):
                entity_rows = _snmp.walk_table(
                    dev["host"], list(_topology.ENTITY_COLUMNS.values()),
                    version=version, community=community, v3=v3, port=port,
                    timeout=timeout, max_rows=256)
        except Exception as exc:
            _obs_event("topology_local_identity_entity_failed", device=dev["name"], error=str(exc))
        identity = _topology.parse_device_identity(
            local_pairs, entity_rows, facts or self.inv.get_facts(dev["name"]) or {})
        self.db.set_topology_device_identity(dev["name"], identity)
        if interfaces is not None:
            self.db.set_topology_interfaces(dev["name"], interfaces)
        return identity

    def endpoint_inventory(self, device=None):
        return _network_intelligence.correlate(
            self.db, device,
            max_age=self.settings.get("network_intelligence_max_age_seconds", 1800))

    def endpoint_summary(self, device=None):
        return _network_intelligence.summary(self.endpoint_inventory(device))

    def discover_neighbors(self, device_name):
        """Discover LLDP over SNMP, with read-only CDP CLI fallback."""
        dev = self.inv.get(device_name)
        if not dev:
            return []
        entries = []
        if dev.get("snmp_version"):
            try:
                version, community, v3, port = self._snmp_params_for(dev)
                trace_cb = self.protocol_traces.callback(device_name, "snmp")
                with _snmp.trace_capture(trace_cb):
                    remote = _snmp.walk_subtree(
                        dev["host"], _topology.LLDP_REM_BASE, version=version,
                        community=community, v3=v3, port=port,
                        timeout=self.settings.get("snmp_timeout", 2.0), max_vars=512)
                    local = _snmp.walk_subtree(
                        dev["host"], _topology.LLDP_LOC_PORT_DESC, version=version,
                        community=community, v3=v3, port=port,
                        timeout=self.settings.get("snmp_timeout", 2.0), max_vars=256)
                entries = _topology.parse_lldp_walk(remote, local)
                self._refresh_topology_identity(
                    dev, version, community, v3, port,
                    facts=self.inv.get_facts(device_name) or {})
            except Exception as exc:
                _obs_event("topology_lldp_failed", device=device_name, error=str(exc))
        if not entries and dev.get("secret_ref") and self.vault_ready():
            tp = None
            try:
                tp, enable_pw = self._connect(dev)
                driver = get_driver(dev["platform"])
                tp.discover_prompt(); driver.initialize(tp, enable_password=enable_pw)
                out = driver.run(tp, "show cdp neighbors detail")
                entries = _topology.parse_cdp_detail(out)
            except Exception:
                entries = []
            finally:
                if tp is not None:
                    tp.close()
        inventory = []
        for item in self.inv.all():
            enriched = dict(item)
            facts = self.inv.get_facts(item["name"]) or {}
            enriched["sysname"] = facts.get("sysname", "")
            inventory.append(enriched)
        entries = _topology.analyze(
            entries, inventory, self.db.get_topology_device_identities())
        self.db.set_neighbors(device_name, entries)
        unmanaged = sum(1 for e in entries if e.get("unmanaged"))
        METRICS.set("netconfig_topology_unmanaged_neighbors", unmanaged)
        return entries

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
        except KeyError as exc:
            raise RuntimeError(
                f"{name} points at vault secret '{ref}', which does not exist. "
                f"`--secret` takes a vault label, not a password. Create it with "
                f"`netconfig vault set {ref} --username U --ask-password`, or fix the device.") from exc
        username = sec.get("username")
        if not username:
            raise RuntimeError(
                f"vault secret '{ref}' has no username (SSH needs one). "
                f"Set it: `netconfig vault set {ref} --username U`.")
        password, key_path, key_pass, enable_pw = self._creds_for(device)
        trace_cb = self.protocol_traces.callback(name, "cli_ssh")
        tp = SSHTransport(
            device["host"], username, port=device["port"],
            password=None if device["use_key"] else password,
            key_path=key_path if device["use_key"] else None,
            key_passphrase=key_pass,
            connect_timeout=self.settings["connect_timeout"],
            command_timeout=self.settings["command_timeout"],
            known_hosts=self.paths.known_hosts,
            host_key_policy=self.settings["host_key_policy"],
            legacy=device["legacy"], trace_callback=trace_cb)
        try:
            tp.connect()
        except Exception as exc:
            if trace_cb:
                try:
                    trace_cb({"event_type": "connect", "operation": "ssh connect",
                              "status": "error", "error_type": type(exc).__name__,
                              "host": device["host"], "port": device["port"]})
                except Exception:
                    pass
            raise
        return tp, enable_pw

    def collect(self, device_name):
        device = self.inv.get(device_name)
        if not device:
            return CollectionResult(device_name, False, message="unknown device")
        if not (_dtypes_m(device) & {"system", "network"}):
            return CollectionResult(
                device_name, False,
                message="application-only endpoint has no SSH configuration to collect")
        profile = self.protocol_profiles.get(device_name)
        if profile and profile.get("enabled") and profile.get("protocol") != "cli_ssh":
            try:
                raw, meta = self.structured_collector.collect(device, profile)
                from . import scrub as _scrub
                stored = raw
                if device["scrub"]:
                    stored, _ = _scrub.scrub(raw)
                result = self.store.save(device_name, stored)
                proto = meta.get("protocol", profile.get("protocol"))
                self.inv.log_run(device_name, True, result["changed"], f"{proto}: " + ("changed" if result["changed"] else "no change"))
                return CollectionResult(device_name, True, changed=result["changed"],
                    message=f"{proto}: " + ("changed" if result["changed"] else "no change"),
                    version=result["version"], diff=result["diff"], config=stored)
            except Exception as exc:
                # Selected structured profiles are fail-closed.  Unexpected adapter
                # errors are normalized here rather than escaping into Web/API callers.
                if not profile.get("allow_cli_fallback"):
                    msg = f"StructuredProtocolError: {exc}"
                    self.inv.log_run(device_name, False, False, msg)
                    return CollectionResult(device_name, False, message=msg)
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
            self.protocol_profiles.rename(old, new)
        except Exception:
            pass
        try:
            self.store.rename(old, new)
        except Exception:
            pass
        self.db.audit("system", "device_rename", old, new)

    def protocol_status(self, device=None):
        if device:
            dev = self.inv.get(device)
            if not dev:
                raise ValueError("unknown device")
            return {"device": device, "profile": self.protocol_profiles.get(device)}
        return [{"device": d["name"], "profile": self.protocol_profiles.get(d["name"])} for d in self.inv.all()]

    def protocol_collect(self, device):
        return self.collect(device)

    def _structured_profile_for(self, device):
        dev = self.inv.get(device)
        if not dev:
            raise ValueError("unknown device")
        profile = self.protocol_profiles.get(device)
        if not profile or not profile.get("enabled") or profile.get("protocol") == "cli_ssh":
            raise ValueError("device does not have an enabled structured protocol profile")
        return dev, profile

    def protocol_capabilities(self, device):
        dev, profile = self._structured_profile_for(device)
        return self.structured_collector.capabilities(dev, profile)

    def protocol_read_state(self, device, path=None):
        dev, profile = self._structured_profile_for(device)
        text, meta = self.structured_collector.read_state(dev, profile, path=path)
        return {"device": device, "metadata": meta, "data": text}

    def protocol_subscribe_once(self, device, path=None):
        dev, profile = self._structured_profile_for(device)
        text, meta = self.structured_collector.subscribe_once(dev, profile, path=path)
        return {"device": device, "metadata": meta, "data": text}

    def structured_change(self, device, resource, selectors, value, actor, approved=False,
                          source_kind="manual", source_ref=""):
        return self.structured_changes.execute_resource(
            device=device, resource=resource, selectors=selectors, value=value,
            actor=actor, approved=approved, source_kind=source_kind, source_ref=source_ref)

    def automation_status(self):
        subscriptions = self.telemetry.list()
        campaigns = self.campaigns.list()
        desired_states = self.desired_state.list()
        transactions = self.structured_changes.list(limit=10_000)
        now = time.time()
        return {
            "implementation_tracks": {
                "PH-4": "IMPLEMENTED_TESTING_DEFERRED",
                "NI-5": "IMPLEMENTED_TESTING_DEFERRED",
                "VM-1": "IMPLEMENTED_TESTING_DEFERRED",
                "NA-1": "IMPLEMENTED_TESTING_DEFERRED",
                "NA-2": "IMPLEMENTED_TESTING_DEFERRED",
                "HA-1": "IMPLEMENTED_TESTING_DEFERRED",
            },
            "structured_transactions": len(transactions),
            "structured_recovery_required": sum(
                1 for item in transactions if item.get("state") == "RECOVERY_REQUIRED"
            ),
            "telemetry_subscriptions": len(subscriptions),
            "telemetry_enabled": sum(1 for item in subscriptions if item.get("enabled")),
            "telemetry_due": sum(
                1
                for item in subscriptions
                if item.get("enabled") and float(item.get("next_run_ts") or 0) <= now
            ),
            "telemetry_errors": sum(1 for item in subscriptions if item.get("state") == "ERROR"),
            "desired_states": len(desired_states),
            "desired_published": sum(1 for item in desired_states if item.get("state") == "PUBLISHED"),
            "desired_state_runs": len(self.desired_state.runs(limit=10_000)),
            "campaigns": len(campaigns),
            "campaigns_active": sum(1 for item in campaigns if item.get("state") in {"RUNNING", "PAUSED"}),
            "vendor_model_packs": len(self.vendor_models.list()),
            "explicit_model_bindings": len(self.vendor_models.list_bindings()),
            "ha": self.ha.readiness(),
        }

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
            base = None
            if mode == "remediate":
                if device.get("scrub"):
                    return {"device": name, "ok": False, "changed": False,
                            "output": "safe remediation disabled: stored config is scrubbed; "
                                      "a sanitized baseline cannot be replayed as device config"}
                base = self.store.baseline_text(name)
                if base is None:
                    return {"device": name, "ok": False, "changed": False,
                            "output": "no baseline set"}
                lines = []  # planned after a fresh live config is collected
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
            elif mode == "remediate":
                current = driver.fetch_config(tp)
                plan = driver.remediation_plan(base, current)
                lines = plan["commands"]
                if not lines:
                    return {"device": name, "ok": True, "changed": False,
                            "output": "already matches baseline"}
                guard = driver.begin_rollback_guard(tp)
                try:
                    out, errors = driver.apply_lines(tp, lines, save=False, remediation=True)
                    if errors:
                        raise DriverError("remediation command errors: " +
                                          "; ".join(f"{line}: {e}" for line, e in errors))
                    verify = driver.fetch_config(tp)
                    post = driver.remediation_plan(base, verify)
                    if post["commands"]:
                        raise DriverError("post-change verification still differs from baseline")
                    driver.commit_rollback_guard(tp, guard, save=save)
                    out = (out + "\n[verified] semantic baseline match").strip()
                    errors = []
                except Exception:
                    driver.leave_rollback_guard_armed(tp, guard)
                    raise
            else:  # config
                out, errors = driver.apply_lines(tp, lines, save=save)
            self.recorder.write(name, tp.transcript)
            ok = not errors
            msg = out if ok else (out + "\n[errors] " +
                                  "; ".join(f"{line}: {e}" for line, e in errors))
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
        trace_cb = self.protocol_traces.callback(device_name, "snmp")
        with _snmp.trace_capture(trace_cb):
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

    def storage_status(self):
        try:
            self.db.heartbeat_cluster_node(self.cluster_node_id, time.time())
        except Exception:
            pass
        out = self.db.readiness()
        out["node_id"] = self.cluster_node_id
        out["core_db_password_source"] = self.core_db_password_source or "none"
        return out

    def scheduler_leader(self, name):
        """True when this ACTIVE node may start a singleton background scheduler.

        SQLite deliberately stays single-node. PostgreSQL uses a session-scoped
        advisory lock, released automatically if the DB connection dies. A node
        in DRAINING/DRAINED state never acquires new scheduler leadership.
        """
        if hasattr(self, "ha") and not self.ha.accepts_automation_work():
            return False
        return bool(self.db.try_advisory_lock(f"netconfig:scheduler:{name}"))

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

    def _refresh_sensors_and_bridge_events(self, device_name):
        """Refresh canonical Sensors and bridge only newly durable transitions.

        The high-water mark is captured before the DB-only Sensor refresh.  This
        preserves MC-1/MC-2 no-extra-device-I/O behavior and prevents unchanged
        refreshes from generating MC-3 operational events.
        """
        before_id = self.sensors.latest_transition_id()
        self.sensors.refresh_inventory_health(self.inv)
        bridged = []
        for transition in self.sensors.transitions_after_id(before_id, device=device_name):
            row = self.events.record_sensor_transition(transition)
            if row is not None:
                bridged.append(row)
        return bridged

    def snmp_poll(self, device_name, interfaces=True, vendor_force=False):
        dev = self.inv.get(device_name)
        if not dev:
            return {"ok": False, "error": "unknown device"}
        previous_facts = self.inv.get_facts(device_name) or {}
        try:
            version, community, v3, port = self._snmp_params_for(dev)
            trace_cb = self.protocol_traces.callback(device_name, "snmp")
            with _snmp.trace_capture(trace_cb):
                facts = _snmp.poll_system(dev["host"], port=port, version=version,
                                          community=community, v3=v3,
                                          timeout=self.settings.get("snmp_timeout", 2.0))
            self.inv.set_facts(device_name, **facts)
            self._refresh_topology_identity(
                dev, version, community, v3, port, facts=facts)
            with _snmp.trace_capture(trace_cb):
                vendor_result = self._poll_vendor_mibs(
                    device_name, dev, facts, version, community, v3, port,
                    force=vendor_force)
            iface_count = None
            if interfaces:
                try:
                    with _snmp.trace_capture(trace_cb):
                        ifs = _snmp.poll_interfaces(
                            dev["host"], port=port, version=version, community=community,
                            v3=v3, timeout=self.settings.get("snmp_timeout", 2.0))
                    samples = self.inv.set_interfaces(
                        device_name, ifs,
                        history_seconds=self.settings.get("snmp_history_seconds", 1800))
                    iface_count = len(ifs)
                    self.db.set_topology_interfaces(device_name, ifs)
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
                            with _snmp.trace_capture(trace_cb):
                                ip_neighbors = _snmp.poll_ip_neighbors(
                                    dev["host"], port=port, version=version, community=community,
                                    v3=v3, timeout=self.settings.get("snmp_timeout", 2.0),
                                    ifdescr=ifdescr)
                                vlan_fdb = _snmp.poll_vlan_fdb(
                                    dev["host"], port=port, version=version, community=community,
                                    v3=v3, timeout=self.settings.get("snmp_timeout", 2.0),
                                    ifdescr=ifdescr)
                            self.db.set_ip_neighbors(device_name, ip_neighbors)
                            self.db.set_vlan_fdb(device_name, vlan_fdb)
                            # Keep legacy device-detail views populated from the new
                            # authoritative tables without an extra SNMP walk.
                            self.db.set_arp(device_name, [
                                {"ip": r.get("ip", ""), "mac": r.get("mac", ""),
                                 "ifindex": r.get("ifindex", "")}
                                for r in ip_neighbors if r.get("address_family") == "ipv4"
                            ])
                            self.db.set_mac_table(device_name, [
                                {"mac": r.get("mac", ""), "port": r.get("bridge_port", ""),
                                 "ifindex": r.get("ifindex", ""), "ifdescr": r.get("ifdescr", "")}
                                for r in vlan_fdb
                            ])
                            self.discover_neighbors(device_name)
                            eps = self.endpoint_inventory()
                            summ = _network_intelligence.summary(eps)
                            METRICS.set("netconfig_endpoints_total", summ["total"])
                            METRICS.set("netconfig_endpoints_attached", summ["attached"])
                            METRICS.set("netconfig_endpoints_ambiguous", summ["ambiguous"])
                        except Exception:
                            pass
                except Exception as e:
                    # system poll succeeded; interface walk is best-effort
                    iface_count = f"iface walk failed: {e}"
            # MC-1/MC-2: collection produces persisted evidence and canonical Sensor
            # state. MC-3 bridges only durable state transitions into the event stream.
            try:
                self._refresh_sensors_and_bridge_events(device_name)
            except Exception:
                pass
            return {"ok": True, "interfaces": iface_count,
                    "vendor_mib": vendor_result, **facts}
        except Exception as e:
            self.inv.set_facts(device_name, reachable=False, error=str(e))
            try:
                self._refresh_sensors_and_bridge_events(device_name)
            except Exception:
                pass
            return {"ok": False, "error": str(e)}

    def snmp_poll_all(self, vendor_force=False):
        """Poll every SNMP-enabled device with a bounded worker pool."""
        devices = [d for d in self.inv.all() if d.get("snmp_version")]
        workers = max(1, min(int(self.settings.get("snmp_workers", 8) or 8),
                             max(1, len(devices))))
        out = {}
        started = time.monotonic()
        METRICS.set("netconfig_snmp_poll_queue_depth", len(devices))
        if not devices:
            return out
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers,
                                                   thread_name_prefix="snmp") as ex:
            futs = {ex.submit(self.snmp_poll, d["name"], vendor_force=vendor_force): d
                    for d in devices}
            pending = len(futs)
            for fut in concurrent.futures.as_completed(futs):
                d = futs[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {"ok": False, "error": str(e)}
                out[d["name"]] = result
                pending -= 1
                METRICS.set("netconfig_snmp_poll_queue_depth", pending)
                METRICS.inc("netconfig_snmp_polls_total")
                if not result.get("ok"):
                    METRICS.inc("netconfig_snmp_poll_failures_total")
        failures = sum(1 for r in out.values() if not r.get("ok"))
        METRICS.set("netconfig_snmp_poll_last_duration_seconds",
                    time.monotonic() - started)
        METRICS.set("netconfig_snmp_devices_total", len(devices))
        METRICS.set("netconfig_snmp_devices_reachable", len(devices) - failures)
        _obs_event("snmp_poll_all", devices=len(devices), workers=workers,
                   failures=failures)
        return out

    def close(self):
        self.db.close()
