#!/usr/bin/env python3
"""Offline self-test: crypto vectors + vault/store/scrub round-trips.
Requires no network or device. Run: python3 selftest.py"""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from netconfig import aead, scrub, aes, snmp, compliance, automation, mib
from netconfig.vault import Vault
from netconfig.store import ConfigStore
from netconfig.db import Database
from netconfig.inventory import Inventory
from netconfig.store import ConfigStore as Store
from netconfig.users import Users, can

fails = 0


def check(name, cond):
    global fails
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        fails += 1


print("aead (RFC 8439 vector):")
key = bytes(range(0x80, 0xa0))
nonce = bytes.fromhex("070000004041424344454647")
aad = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
pt = (b"Ladies and Gentlemen of the class of '99: If I could offer you "
      b"only one tip for the future, sunscreen would be it.")
ct = aead.encrypt(key, nonce, pt, aad)
check("tag matches RFC", ct[-16:] == bytes.fromhex("1ae10b594f09e26a7e902ecbd0600691"))
check("roundtrip", aead.decrypt(key, nonce, ct, aad) == pt)
try:
    aead.decrypt(key, nonce, ct[:-1] + bytes([ct[-1] ^ 1]), aad)
    check("tamper rejected", False)
except ValueError:
    check("tamper rejected", True)

print("vault:")
d = tempfile.mkdtemp()
try:
    v = Vault(os.path.join(d, "t.vault"))
    v.create("pw123")
    v.set_secret("s1", username="admin", password="p@ss", enable_password="en")
    v2 = Vault(os.path.join(d, "t.vault"))
    v2.unlock("pw123")
    check("secret survives lock/unlock", v2.get_secret("s1")["password"] == "p@ss")
    check("list hides material", v2.list_secrets()["s1"] == ["enable_password", "password", "username"])
    try:
        Vault(os.path.join(d, "t.vault")).unlock("wrong")
        check("wrong password rejected", False)
    except ValueError:
        check("wrong password rejected", True)
finally:
    shutil.rmtree(d)

print("store (versioning + diff):")
d = tempfile.mkdtemp()
try:
    s = ConfigStore(d)
    r1 = s.save("sw", "hostname sw\ninterface Gi0/0\n")
    r2 = s.save("sw", "hostname sw\ninterface Gi0/0\n")           # identical
    r3 = s.save("sw", "hostname sw\ninterface Gi0/1\n")           # changed
    check("first save is a change", r1["changed"])
    check("identical save is no change", not r2["changed"])
    check("modified save is a change", r3["changed"])
    check("diff shows the change", "Gi0/1" in r3["diff"] and "Gi0/0" in r3["diff"])
    check("two versions retained", len(s.versions("sw")) == 2)
    # path-traversal guard: a stamp from an HTTP param must not escape the dir
    _traversed = False
    try:
        s.read_version("sw", "../../../../../../etc/passwd")
        _traversed = True
    except FileNotFoundError:
        pass
    check("read_version blocks path traversal", not _traversed)
    check("read_version still reads a legit version",
          s.read_version("sw", s.versions("sw")[-1]["stamp"]).startswith("hostname"))
finally:
    shutil.rmtree(d)

print("scrub:")
cfg = ("snmp-server community S3cret RO\n"
       "enable secret 5 $1$ab$hashhash\n"
       "username x password 0 Plain\n")
out, n = scrub.scrub(cfg)
check("snmp masked", "S3cret" not in out and "<scrubbed:snmp>" in out)
check("enable secret masked", "hashhash" not in out)
check("plaintext password masked", "Plain" not in out)
check("count > 0", n >= 3)

print("aes (FIPS-197 vectors):")
_k128 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
_pt = bytes.fromhex("00112233445566778899aabbccddeeff")
check("AES-128 encrypt", aes.AES(_k128).encrypt_block(_pt) ==
      bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a"))
check("AES-128 decrypt roundtrip", aes.AES(_k128).decrypt_block(
      aes.AES(_k128).encrypt_block(_pt)) == _pt)
_k256 = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
check("AES-256 encrypt", aes.AES(_k256).encrypt_block(_pt) ==
      bytes.fromhex("8ea2b7ca516745bfeafc49904b496089"))
_iv = os.urandom(16); _kk = os.urandom(16); _msg = os.urandom(53)
check("AES CFB-128 roundtrip", aes.cfb128_decrypt(_kk, _iv,
      aes.cfb128_encrypt(_kk, _iv, _msg)) == _msg)

print("snmp (BER codec, offline):")
check("INTEGER roundtrip", snmp.decode(snmp.enc_int(123456))[1] == 123456)
check("OCTET STRING roundtrip", snmp.decode(snmp.enc_octet(b"hello"))[1] == b"hello")
check("OID encode/decode", snmp.decode(snmp.enc_oid(".1.3.6.1.2.1.1.5.0"))[1]
      == ".1.3.6.1.2.1.1.5.0")
_seq = snmp.enc_seq(snmp.enc_int(1), snmp.enc_octet(b"public"))
_tag, _kids, _ = snmp.decode(_seq)
check("SEQUENCE nesting", _tag == snmp.SEQUENCE and _kids[0][1] == 1 and _kids[1][1] == b"public")
_key = snmp.password_to_key("maplesyrup", b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02",
                            __import__("hashlib").sha1)
# RFC 3414 A.3.2 known localized SHA key for engineID 000000000000000000000002
check("SNMPv3 SHA key localization (RFC 3414)",
      _key.hex() == "6695febc9288e36282235fc7151f128497b38f3f")
# GETNEXT PDU builds with the right tag, and IF-MIB column bases are well-formed
_gn = snmp._build_get_pdu(1, [snmp.IF["descr"]], snmp.GET_NEXT)
check("GETNEXT PDU uses GET_NEXT tag", _gn[0] == snmp.GET_NEXT)
check("IF-MIB columns are valid OIDs",
      all(snmp.decode(snmp.enc_oid(o))[1] == o for o in snmp.IF.values()))

print("users / RBAC:")
_d = tempfile.mkdtemp()
try:
    _db = Database(os.path.join(_d, "t.db"))
    _u = Users(_db.conn)
    _u.create("alice", "pw1", role="admin")
    _u.create("bob", "pw2", role="operator")
    check("verify good password", bool(_u.verify("alice", "pw1")))
    check("verify bad password", _u.verify("alice", "nope") is None)
    check("operator can submit", can("operator", "submit"))
    check("operator cannot approve", not can("operator", "approve"))
    check("approver can approve", can("approver", "approve"))
    check("only admin manages users", can("admin", "manage_users") and not can("approver", "manage_users"))
    _db.close()
finally:
    shutil.rmtree(_d)

print("automation (variable substitution):")
_dev = {"name": "sw7", "host": "10.1.1.7", "port": 22, "platform": "cisco_ios", "tags": ["core"]}
_out, _un = automation.substitute("hostname ${NodeName}\nlogging ${IP_Address}", _dev)
check("substitutes NodeName + IP", "sw7" in _out and "10.1.1.7" in _out)
check("no false unresolved", _un == [])
_out2, _un2 = automation.substitute("snmp ${Bogus}", _dev)
check("reports unresolved var", _un2 == ["Bogus"])
check("comment lines dropped", automation.commands("# c\nntp server 1.1.1.1\n") == ["ntp server 1.1.1.1"])

print("compliance (rule packs):")
_good = ("service password-encryption\ntransport input ssh\nbanner login ^C hi ^C\n"
         "ip ssh version 2\nlogging host 10.0.0.9\nntp server 10.0.0.254\n"
         "enable secret 5 x\nexec-timeout 10 0\n")
_bad = ("transport input telnet\nenable password clear\nsnmp-server community public RO\n"
        "exec-timeout 0 0\n")
_gr = compliance.evaluate_device(_good, "cisco_ios")
_br = compliance.evaluate_device(_bad, "cisco_ios")
check("clean config passes all", all(r["status"] == "pass" for r in _gr))
check("telnet flagged", any(r["id"] == "PCI-2.2.2-TELNET" and r["status"] == "fail" for r in _br))
check("default community flagged", any(r["id"] == "PCI-2.1-DEFCOMM" and r["status"] == "fail" for r in _br))
from netconfig import portmon as _portmon, appmon as _appmon
_old_ports, _old_apps = _portmon.check_ports, _appmon.check_all
try:
    _portmon.check_ports = lambda *a, **k: [
        {"proto": "tcp", "port": p, "state": "error"}
        for p in (21, 22, 23, 445, 3389)]
    _sr = compliance.evaluate_system({"host": "bad.invalid", "monitor_ports": ""})
    check("system probe errors are unknown, never false passes",
          all(r["status"] == "unknown" for r in _sr))
    _appmon.check_all = lambda *a, **k: [{
        "url": "https://app.invalid/", "status": None, "ok": False,
        "tls": {"valid": False, "legacy_protocols": {"TLSv1": None,
                                                        "TLSv1.1": None}}}]
    _ar = compliance.evaluate_application(
        {"host": "app.invalid", "monitor_urls": "https://app.invalid/"})
    _by_id = {r["id"]: r for r in _ar}
    check("invalid TLS cannot falsely pass expiry or protocol checks",
          _by_id["APP-CERT-EXPIRY"]["status"] == "unknown" and
          _by_id["APP-TLS-VERSION"]["status"] == "unknown")
    check("application health evidence is not compliance-scored",
          _by_id["APP-HEALTH"]["status"] == "fail" and
          not _by_id["APP-HEALTH"]["scored"])
finally:
    _portmon.check_ports, _appmon.check_all = _old_ports, _old_apps

print("baseline / drift:")
_d = tempfile.mkdtemp()
try:
    _s = ConfigStore(_d)
    _s.save("sw", "hostname sw\nntp server 10.0.0.1\n")
    _s.set_baseline("sw")
    check("no drift right after baseline", not _s.drift("sw")["drifted"])
    _s.save("sw", "hostname sw\nntp server 10.0.0.1\naccess-list 1 permit any\n")
    _dr = _s.drift("sw")
    check("drift detected after change", _dr["drifted"])
    check("drift diff shows added line", "access-list" in _dr["diff"])
finally:
    shutil.rmtree(_d)

print("groups / target resolution:")
_d = tempfile.mkdtemp()
try:
    _db = Database(os.path.join(_d, "t.db"))
    _inv = Inventory(_db.conn)
    for i in (1, 2, 3):
        _inv.upsert(name=f"n{i}", host=f"10.0.0.{i}", platform="cisco_ios",
                    tags=["edge"] if i < 3 else ["core"])
    _inv.add_group("edge-grp"); _inv.set_group_members("edge-grp", ["n1", "n2"])
    check("group resolves members", [d["name"] for d in _inv.resolve_target("group", "edge-grp")] == ["n1", "n2"])
    check("tag resolves members", [d["name"] for d in _inv.resolve_target("tag", "edge")] == ["n1", "n2"])
    check("all resolves everything", len(_inv.resolve_target("all", "")) == 3)
    _db.close()
finally:
    shutil.rmtree(_d)

print("interface stats / live samples:")
_d = tempfile.mkdtemp()
try:
    _db = Database(os.path.join(_d, "t.db"))
    _inv = Inventory(_db.conn)
    base = [{"ifindex": "1", "descr": "Gi0/1", "admin": "up", "oper": "up",
             "speed": 1000000000, "in_octets": 1000, "out_octets": 2000,
             "in_errors": 0, "out_errors": 0}]
    _inv.set_interfaces("d", base)                     # first sample -> no rate yet
    check("first poll stores interface, no rate", _inv.get_interfaces("d")[0]["in_bps"] is None)
    import time as _t
    _t.sleep(1.05)
    grown = [dict(base[0], in_octets=1000 + 125000, out_octets=2000 + 250000)]
    written = _inv.set_interfaces("d", grown)           # second sample -> rate computed
    row = _inv.get_interfaces("d")[0]
    check("second poll computes a positive in-rate", row["in_bps"] and row["in_bps"] > 0)
    samples = _inv.get_samples("d")
    check("time-series sample recorded for the graph",
          "1" in samples and len(samples["1"]["points"]) >= 1)
    check("set_interfaces returns computed samples for history backend",
          isinstance(written, list) and len(written) == 1 and written[0][0] == "1"
          and written[0][2] is not None)
    check("interface_counts reports up/total", _inv.interface_counts().get("d") == (1, 1))
    _db.close()
finally:
    shutil.rmtree(_d)

print("interface history backend selection (optional PostgreSQL):")
from netconfig import ifhistory as _ifh
from netconfig import config as _ifhcfg
_base = dict(_ifhcfg.DEFAULT_SETTINGS)
check("disabled by default -> no backend", _ifh.get_backend(_base) is None)
check("enabled but no DSN -> no backend",
      _ifh.get_backend(dict(_base, if_history_enabled=True)) is None)
_be = _ifh.get_backend(dict(_base, if_history_enabled=True,
                            if_history_dsn="host=127.0.0.1 dbname=x"))
# construction stays lazy: a backend object exists without importing psycopg
check("enabled + legacy DSN -> PgHistory built lazily (no driver import)",
      _be is not None and _be.__class__.__name__ == "PgHistory")
check("enabled + discrete host/dbname -> PgHistory built lazily",
      _ifh.get_backend(dict(_base, if_history_enabled=True, pg_host="db",
                            pg_dbname="nc")).__class__.__name__ == "PgHistory")
check("enabled + host but no dbname -> no backend",
      _ifh.get_backend(dict(_base, if_history_enabled=True, pg_host="db")) is None)

print("concurrent DB access (poller + requests):")
_d = tempfile.mkdtemp()
try:
    _db = Database(os.path.join(_d, "c.db"))
    _inv = Inventory(_db.conn)
    for i in range(4):
        _inv.upsert(name=f"d{i}", host="10.0.0.1", platform="generic")
    import threading as _th
    errs = []
    def _writer():
        try:
            for _ in range(60):
                for i in range(4):
                    _inv.set_interfaces(f"d{i}", [{"ifindex": str(j), "descr": f"e{j}",
                        "admin": "up", "oper": "up", "speed": 10**9,
                        "in_octets": j * 1000, "out_octets": j * 2000,
                        "in_errors": 0, "out_errors": 0} for j in range(4)])
        except Exception as e:
            errs.append(repr(e))
    def _reader():
        try:
            for _ in range(120):
                _inv.all(); _db.recent_audit(3); _inv.get_interfaces("d2")
                _db.audit("t", "x"); _inv.interface_counts()
        except Exception as e:
            errs.append(repr(e))
    threads = [_th.Thread(target=_writer) for _ in range(2)] + \
              [_th.Thread(target=_reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("no errors under concurrent connection use (" + (errs[0] if errs else "clean") + ")", not errs)
    check("locking connection wrapper is in use", hasattr(_db.conn, "lock"))
    _db.close()
finally:
    shutil.rmtree(_d)

def _raises(fn):
    try:
        fn(); return False
    except Exception:
        return True

print("device rename + backup retention:")
_d = tempfile.mkdtemp()
try:
    _db = Database(os.path.join(_d, "r.db"))
    _inv = Inventory(_db.conn)
    _store = Store(os.path.join(_d, "cfg"), keep_versions=30)
    _inv.upsert(name="old", host="10.0.0.1", platform="generic", tags=["t"])
    _inv.add_group("g", ""); _inv.set_group_members("g", ["old"])
    _store.save("old", "hostname old\n")
    _inv.rename("old", "new")
    _store.rename("old", "new")
    check("rename: old gone, new present",
          _inv.get("old") is None and _inv.get("new") is not None)
    _mem = [x["name"] for x in _inv.all()] 
    check("rename: inventory list shows new name", "new" in _mem and "old" not in _mem)
    check("rename: config archive moved", len(_store.versions("new")) == 1)
    check("rename: duplicate name rejected", _raises(lambda: _inv.rename("new", "new")))
    for i in range(6):
        _store.save("new", f"hostname new\n! {i}\n")
    kept = _store.prune("new", 3)
    check("backup prune keeps N copies", kept == 3 and len(_store.versions("new")) == 3)
    _db.close()
finally:
    shutil.rmtree(_d)

print("SNMPv3 SHA-2 auth family + AES key sizes:")
from netconfig import snmp as _sx
check("all SHA/MD5 auth protocols registered",
      set(_sx._AUTH) >= {"md5","sha","sha1","sha224","sha256","sha384","sha512"})
check("SHA-256 uses 24-byte (192-bit) tag", _sx._AUTH["sha256"][1] == 24)
check("SHA-512 uses 48-byte (384-bit) tag", _sx._AUTH["sha512"][1] == 48)
check("net-snmp names normalize", _sx._norm_auth("SHA-256")=="sha256" and _sx._norm_priv("AES")=="aes128"
      and _sx._norm_priv("AES-256")=="aes256")
_eid=bytes.fromhex("80001f8880e9630000d61f9d00")
_k=_sx.password_to_key("privpassword1", _eid, __import__("hashlib").sha1)
check("AES-192 key extended to 24 bytes", len(_sx._extend_priv_key(_k,_eid,__import__("hashlib").sha1,24))==24)
check("AES-256 key extended to 32 bytes", len(_sx._extend_priv_key(_k,_eid,__import__("hashlib").sha1,32))==32)
_orig_ptk = _sx.password_to_key
_ptk_calls = []
_sx.password_to_key = lambda password, engine, ctor: (_ptk_calls.append((password, engine)) or b"k" * 32)
try:
    _vp = _sx.V3Params("u", auth_proto="sha256", auth_pass="a",
                       priv_proto="aes256", priv_pass="p")
    _sx._localized_for(_vp, _eid)
    _sx._localized_for(_vp, _eid)
    check("SNMPv3 localized keys cached across OIDs", len(_ptk_calls) == 2)
finally:
    _sx.password_to_key = _orig_ptk
_orig_discover = _sx._discover_engine
_discover_calls = []
_sx._discover_engine = lambda *args: (_discover_calls.append(args) or (_eid, 1, 2))
try:
    _ep = _sx.V3Params("u")
    _sx._engine_for(_ep, "10.0.0.1", 161, 1, 0)
    _sx._engine_for(_ep, "10.0.0.1", 161, 1, 0)
    check("SNMPv3 engine discovery cached per target", len(_discover_calls) == 1)
finally:
    _sx._discover_engine = _orig_discover

print("monitor alerts engine:")
_d3 = tempfile.mkdtemp()
try:
    _db3 = Database(os.path.join(_d3, "a.db"))
    from netconfig import monitor as _monm
    rid = _db3.add_rule("t", "d1", "port_state", "tcp/22", "is", "closed", "high")
    check("rule stored + listed", len(_db3.rules(enabled_only=True)) == 1)
    r = _db3.rules()[0]
    br, _ = _monm._breach(r, {"target": "tcp/22", "status": "closed", "value": None})
    check("port_state breach detected", br is True)
    br2, _ = _monm._breach(r, {"target": "tcp/22", "status": "open", "value": 1})
    check("port_state no breach when open", br2 is False)
    er = _db3.rules()[0]
    er["metric"], er["op"], er["threshold"] = "tls_expiry", "<", "14"
    b3, _ = _monm._breach(er, {"target": "u", "status": "valid", "value": 5})
    check("tls_expiry <14 breaches at 5 days", b3 is True)
    aid = _db3.open_alert(rid, "t", "d1", "tcp/22", "port_state", "high", "msg")
    check("alert opens as firing", len(_db3.alerts(state="firing")) == 1)
    _db3.resolve_alert(aid)
    check("alert resolves", len(_db3.alerts(state="firing")) == 0)
    _db3.close()
finally:
    shutil.rmtree(_d3)

print("settings subpages:")
from netconfig import web as _web
check("dark theme stylesheet and persisted toggle are present",
      'data-theme="dark"' in _web._CSS and
      "netconfig-theme" in _web._THEME_JS and
      "netconfigToggleTheme" in _web._THEME_JS)
class _FakeAudit:
    def audit(self, *args):
        pass
class _FakeManager:
    def __init__(self):
        self.settings = {
            "web_bind": "127.0.0.1", "web_port": 8778,
            "snmp_timeout": 2.0, "snmp_port": 161,
            "snmp_poll_interval": 5, "snmp_history_seconds": 1800,
            "netflow_enabled": True, "smtp_enabled": True,
        }
        self.paths = object()
        self.db = _FakeAudit()
    def vault_ready(self):
        return False
_wc = object.__new__(_web.Console)
_wc.manager = _FakeManager()
_wc._settings_page_v2 = lambda *args, **kwargs: kwargs
_save_settings = _web._config.save_settings
_web._config.save_settings = lambda paths, settings: None
try:
    _wc._do_settings_save_v2({
        "section": ["snmp"], "snmp_timeout": ["1.5"], "snmp_port": ["1161"],
        "snmp_poll_interval": ["30"], "snmp_history_seconds": ["3600"],
    }, {"username": "tester", "role": "admin"})
finally:
    _web._config.save_settings = _save_settings
check("SNMP subpage updates only SNMP values",
      _wc.manager.settings["snmp_timeout"] == 1.5 and
      _wc.manager.settings["snmp_port"] == 1161 and
      _wc.manager.settings["netflow_enabled"] is True and
      _wc.manager.settings["smtp_enabled"] is True)
_render = object.__new__(_web.Console)
_render.manager = _FakeManager()
_render._page = lambda title, body, sess, flash=None: body
_render._csrf_field = lambda: '<input type=hidden name=csrf value="test">'
_rendered = []
_render._send = lambda body, *args, **kwargs: _rendered.append(body)
_render._settings_page_v2({"username": "tester", "role": "admin"},
                          q={"section": ["netflow"]})
check("left menu renders every settings topic",
      all(f"section={key}" in _rendered[0]
          for key in ("general", "snmp", "netflow", "monitoring", "email")))
check("selected subpage hides unrelated fields",
      'name="netflow_port"' in _rendered[0] and 'name="smtp_host"' not in _rendered[0])

print("MIB automap + diagnostics:")
_mib_dir = tempfile.mkdtemp()
try:
    _vendor_mib = """TEST-MIB DEFINITIONS ::= BEGIN
testRoot OBJECT IDENTIFIER ::= { enterprises 424242 }
testMetric OBJECT-TYPE
    SYNTAX INTEGER
    ::= { testRoot 1 }
duplicateNode OBJECT IDENTIFIER ::= { testRoot 2 }
orphanMetric OBJECT IDENTIFIER ::= { missingParent 1 }
END
"""
    _duplicate_mib = """TEST-DUP-MIB DEFINITIONS ::= BEGIN
duplicateNode OBJECT IDENTIFIER ::= { enterprises 999999 }
END
"""
    with open(os.path.join(_mib_dir, "TEST-MIB.mib"), "w", encoding="utf-8") as _fh:
        _fh.write(_vendor_mib)
    with open(os.path.join(_mib_dir, "TEST-DUP-MIB.mib"), "w", encoding="utf-8") as _fh:
        _fh.write(_duplicate_mib)
    _idx = mib.MibIndex(_mib_dir)
    _idx.rebuild()
    _resolved = _idx.resolve_detail("1.3.6.1.4.1.424242.1.0")
    check("uploaded MIB maps OID and preserves instance suffix",
          _resolved["name"] == "testMetric.0")
    check("resolved OID reports its source MIB",
          _resolved["source"] == "TEST-MIB.mib")
    check("per-file diagnostics report unresolved parents",
          _idx.file_stats["TEST-MIB.mib"]["unresolved"] == 1 and
          "orphanMetric" in _idx.file_stats["TEST-MIB.mib"]["unresolved_names"])
    check("duplicate definitions are reported as conflicts",
          any(row["name"] == "duplicateNode" for row in _idx.conflicts))
    _roots = _idx.collection_roots("1.3.6.1.4.1.424242.99")
    check("uploaded OBJECT-TYPE produces a matching vendor collection root",
          len(_roots) == 1 and _roots[0]["root"] == "1.3.6.1.4.1.424242")
    check("different vendor sysObjectID cannot trigger the uploaded MIB",
          _idx.collection_roots("1.3.6.1.4.1.9.1") == [])
    _linux_mibs = """LINUX-TEST-MIB DEFINITIONS ::= BEGIN
netSnmpRoot OBJECT IDENTIFIER ::= { enterprises 8072 }
netSnmpMetric OBJECT-TYPE SYNTAX INTEGER ::= { netSnmpRoot 99 }
ucdRoot OBJECT IDENTIFIER ::= { enterprises 2021 }
ucdMetric OBJECT-TYPE SYNTAX INTEGER ::= { ucdRoot 99 }
host OBJECT IDENTIFIER ::= { mib-2 25 }
hostMetric OBJECT-TYPE SYNTAX INTEGER ::= { host 99 }
END
"""
    with open(os.path.join(_mib_dir, "LINUX-TEST-MIB.mib"), "w", encoding="utf-8") as _fh:
        _fh.write(_linux_mibs)
    _idx.rebuild()
    _linux_roots = {row["root"] for row in
                    _idx.collection_roots("1.3.6.1.4.1.8072.3.2.10")}
    check("Net-SNMP Linux collection includes Net-SNMP, UCD and host resources",
          _linux_roots == {"1.3.6.1.4.1.8072", "1.3.6.1.4.1.2021",
                           "1.3.6.1.2.1.25"})
    _loaded = mib.MibIndex(_mib_dir)
    check("cached MIB diagnostics reload",
          _loaded.load() and _loaded.resolve_detail("1.3.6.1.4.1.424242.1.0")["source"] ==
          "TEST-MIB.mib" and _loaded.file_stats["TEST-MIB.mib"]["unresolved"] == 1)
    _dbm = Database(os.path.join(_mib_dir, "mib-values.db"))
    _dbm.set_mib_values("d1", [{"oid": "1.3.6.1.4.1.424242.1.0",
                                  "name": "testMetric.0", "value": "42",
                                  "mib_source": "TEST-MIB.mib"}], roots=1)
    check("vendor MIB values and poll status persist",
          _dbm.get_mib_values("d1")[0]["value"] == "42" and
          _dbm.get_mib_poll_status("d1")["objects"] == 1)
    _dbm.close()
finally:
    shutil.rmtree(_mib_dir)

print()
print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAILURE(S)")
sys.exit(1 if fails else 0)
