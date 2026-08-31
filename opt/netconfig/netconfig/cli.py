"""
cli.py -- Command-line interface for netconfig.

v1 commands (init, vault, device, collect, run, config, versions, diff, runs,
web, platforms) plus v2:

  netconfig user add|list|role|passwd ...
  netconfig group add|list|members|rm ...
  netconfig bulk --target group:core --mode config --script FILE [--save]
  netconfig request submit|list|show|approve|reject|execute ...
  netconfig baseline set|clear|drift <device>
  netconfig compliance [--standard ISO 27001|PCI-DSS]
  netconfig snmp poll <device>
  netconfig audit

The CLI is operated by whoever holds a shell on the host; it acts with admin
authority. Actions are attributed to --actor (default "cli") in the audit trail
so the record still shows who ran what. The web console is where role separation
(junior submits, senior approves) is enforced.

Vault master password: prompted with getpass, or via $NETCONFIG_MASTER for
unattended runs (an env var is visible to the process user; prefer key auth).
"""

import argparse
import getpass
import os
import sys

from .manager import Manager
from .drivers import platforms as _platforms
from .workflow import Workflow, Scripts
from . import compliance as _compliance
from . import automation as _auto


def _master(manager, required=True):
    if not manager.vault.exists():
        return
    if manager.vault_ready():
        return
    pw = os.environ.get("NETCONFIG_MASTER")
    if not pw and required:
        if not sys.stdin.isatty():
            print("vault is locked and no master password is available. Set NETCONFIG_MASTER "
                  "(under sudo use `sudo -E`, or set it in /etc/default/netconfig), or run in a "
                  "terminal to be prompted.", file=sys.stderr)
            sys.exit(2)
        pw = getpass.getpass("Vault master password: ")
    if not pw:
        if required:
            print("vault: no master password provided.", file=sys.stderr)
            sys.exit(2)
        return
    try:
        manager.unlock_vault(pw)
    except ValueError as e:
        print(f"vault: {e}", file=sys.stderr)
        sys.exit(2)


def _wf(m):
    return Workflow(m.db, m)


def _print_result(r):
    tag = "OK " if r.ok else "ERR"
    ch = " [changed]" if r.changed else ""
    print(f"{tag} {r.device}: {r.message}{ch}")
    if r.ok and r.changed and r.diff:
        print(r.diff)


# ---- v1 commands --------------------------------------------------------
def cmd_init(m, args):
    print(f"data home: {m.paths.home}")
    for p in (m.paths.configs_dir, m.paths.sessions_dir):
        os.makedirs(p, exist_ok=True)
    from . import config as cfg
    cfg.save_settings(m.paths, m.settings)
    if m.users.count() == 0:
        print("initialized. Next: create an admin user (netconfig user add <name> "
              "--role admin), a vault (netconfig vault create), and add a device.")
    else:
        print("initialized.")


def cmd_vault(m, args):
    if args.action == "create":
        if m.vault.exists():
            print("vault already exists", file=sys.stderr); sys.exit(1)
        pw = getpass.getpass("New master password: ")
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            print("passwords do not match", file=sys.stderr); sys.exit(1)
        m.vault.create(pw)
        print(f"vault created at {m.paths.vault_file}")
    elif args.action == "set":
        _master(m)
        fields = {"username": args.username}
        if args.ask_password:
            fields["password"] = getpass.getpass("Device password: ")
        if args.ask_enable:
            fields["enable_password"] = getpass.getpass("Enable password: ")
        if args.key_path:
            fields["key_path"] = os.path.abspath(args.key_path)
        # SNMP credential fields (optional)
        if args.snmp_user:
            fields["snmp_user"] = args.snmp_user
        if args.snmp_community:
            fields["community"] = args.snmp_community
        if args.snmp_auth_pass:
            fields["snmp_auth_proto"] = args.snmp_auth_proto or "sha"
            fields["snmp_auth_pass"] = getpass.getpass("SNMP auth password: ")
        if args.snmp_priv_pass:
            fields["snmp_priv_proto"] = args.snmp_priv_proto or "aes"
            fields["snmp_priv_pass"] = getpass.getpass("SNMP priv password: ")
        if args.snmp_port:
            fields["snmp_port"] = str(args.snmp_port)
        m.vault.set_secret(args.name, **fields)
        print(f"secret '{args.name}' stored")
    elif args.action == "list":
        _master(m)
        for name, present in m.vault.list_secrets().items():
            print(f"  {name}: {', '.join(present)}")
    elif args.action == "rm":
        _master(m)
        m.vault.delete_secret(args.name)
        print(f"secret '{args.name}' removed")
    elif args.action == "unlock":
        if not m.vault.exists():
            print("no vault yet -- create one with `netconfig vault create`", file=sys.stderr)
            sys.exit(1)
        _master(m)
        print("master password OK. Note: the CLI runs one command per process, so each command "
              "unlocks on its own (interactive prompt or $NETCONFIG_MASTER). There is no "
              "persistent unlocked session to carry between commands.")


def _add_inline_cred_args(p):
    """SSH + SNMP credential flags shared by `device add` and `device set-cred`.
    When any are given, credentials are stored (encrypted) in a per-device vault
    secret automatically -- the user never has to touch vault labels."""
    p.add_argument("--username", help="SSH username")
    p.add_argument("--ask-password", action="store_true", help="prompt for the SSH password")
    p.add_argument("--key-path", help="SSH private key path")
    p.add_argument("--snmp-user", help="SNMPv3 username")
    p.add_argument("--snmp-community", help="SNMP v2c community")
    p.add_argument("--snmp-auth-pass", action="store_true", help="prompt for SNMPv3 auth password")
    p.add_argument("--snmp-auth-proto", choices=["md5","sha","sha224","sha256","sha384","sha512"])
    p.add_argument("--snmp-priv-pass", action="store_true", help="prompt for SNMPv3 priv password")
    p.add_argument("--snmp-priv-proto", choices=["aes","aes192","aes256"])
    p.add_argument("--snmp-port", type=int)


def _looks_like_password(s):
    # heuristic: a vault label is a short simple token; passwords tend to have symbols/spaces
    return bool(s) and (any(c in s for c in " @!#$%^&*()=+/\\:;\"'`") or len(s) >= 24)


def _apply_inline_creds(m, device_name, args, secret_name=None):
    """Build/merge a per-device vault secret from inline flags. Returns
    (secret_ref, snmp_ref) to store on the device (either may be None)."""
    have_ssh = bool(args.username or args.ask_password or args.key_path)
    have_snmp = bool(args.snmp_user or args.snmp_community or args.snmp_auth_pass
                     or args.snmp_priv_pass)
    if not (have_ssh or have_snmp):
        return None, None
    _master(m)  # unlock (prompt / env), exits with a clear message if it can't
    name = secret_name or f"{device_name}-cred"
    try:
        fields = dict(m.vault.get_secret(name))
    except KeyError:
        fields = {}
    if args.username:
        fields["username"] = args.username
    if args.ask_password:
        fields["password"] = getpass.getpass("SSH password: ")
    if args.key_path:
        fields["key_path"] = os.path.abspath(args.key_path)
    if args.snmp_user:
        fields["snmp_user"] = args.snmp_user
    if args.snmp_community:
        fields["community"] = args.snmp_community
    if args.snmp_auth_pass:
        fields["snmp_auth_proto"] = args.snmp_auth_proto or "sha"
        fields["snmp_auth_pass"] = getpass.getpass("SNMP auth password: ")
    if args.snmp_priv_pass:
        fields["snmp_priv_proto"] = args.snmp_priv_proto or "aes"
        fields["snmp_priv_pass"] = getpass.getpass("SNMP priv password: ")
    if args.snmp_port:
        fields["snmp_port"] = str(args.snmp_port)
    m.vault.set_secret(name, **fields)
    print(f"stored credentials in vault secret '{name}'")
    return (name if have_ssh else None), (name if have_snmp else None)


def cmd_device(m, args):
    if args.action == "add":
        # warn if --secret looks like a password rather than a vault label
        if args.secret and _looks_like_password(args.secret):
            print(f"warning: --secret expects a vault label, but '{args.secret[:3]}...' looks "
                  f"like a password. Use --username/--ask-password to store credentials, or "
                  f"--secret-name <label> to reference an existing vault secret.", file=sys.stderr)
        # inline credentials -> auto per-device vault secret
        ssh_ref, snmp_ref = _apply_inline_creds(m, args.name, args)
        secret_ref = args.secret or ssh_ref
        snmp_secret = args.snmp_secret or snmp_ref
        # validate that a named secret actually exists (if the vault is open)
        if secret_ref and m.vault_ready():
            try:
                m.vault.get_secret(secret_ref)
            except KeyError:
                print(f"warning: no vault secret named '{secret_ref}' yet. Create it with "
                      f"`netconfig vault set {secret_ref} --username U --ask-password`, or add "
                      f"credentials inline with --username/--ask-password.", file=sys.stderr)
        m.inv.upsert(
            name=args.name, host=args.host, port=args.port, platform=args.platform,
            device_type=getattr(args, "device_type", "network"),
            secret_ref=secret_ref, enable_ref=args.enable_secret,
            use_key=args.use_key, legacy=args.legacy, scrub=args.scrub,
            enabled=not args.disabled, tags=args.tag or [], notes=args.notes or "",
            snmp_version=args.snmp_version or "", snmp_ref=snmp_secret)
        print(f"device '{args.name}' saved")
    elif args.action == "set-cred":
        dev = m.inv.get(args.name)
        if not dev:
            print(f"no such device '{args.name}'", file=sys.stderr); sys.exit(1)
        # reuse the device's existing secret if it already has one
        existing = dev.get("secret_ref") or dev.get("snmp_ref")
        ssh_ref, snmp_ref = _apply_inline_creds(m, args.name, args, secret_name=existing)
        if not (ssh_ref or snmp_ref):
            print("nothing to set -- pass --username/--ask-password and/or --snmp-* flags",
                  file=sys.stderr); sys.exit(1)
        kw = {"name": args.name}
        if ssh_ref:
            kw["secret_ref"] = ssh_ref
        if snmp_ref:
            kw["snmp_ref"] = snmp_ref
            if not dev.get("snmp_version"):
                kw["snmp_version"] = "v3" if (args.snmp_auth_pass or args.snmp_user) else "v2c"
        m.inv.upsert(**kw)
        print(f"credentials updated for '{args.name}'")
    elif args.action == "list":
        rows = m.inv.all()
        if not rows:
            print("(no devices)"); return
        w = max(len(r["name"]) for r in rows)
        for r in rows:
            en = " " if r["enabled"] else "x"
            snmp = f" snmp={r['snmp_version']}" if r.get("snmp_version") else ""
            print(f"[{en}] {r['name']:<{w}}  {r['host']}:{r['port']:<5} "
                  f"{r['platform']:<14} secret={r['secret_ref'] or '-'}"
                  f"{' legacy' if r['legacy'] else ''}{' scrub' if r['scrub'] else ''}{snmp}")
    elif args.action == "show":
        r = m.inv.get(args.name)
        if not r:
            print("unknown device", file=sys.stderr); sys.exit(1)
        for k in ("name", "host", "port", "platform", "secret_ref", "enable_ref",
                  "use_key", "legacy", "scrub", "enabled", "tags", "notes",
                  "snmp_version", "snmp_ref"):
            print(f"  {k:<13}: {r[k]}")
    elif args.action == "rm":
        m.inv.delete(args.name)
        print(f"device '{args.name}' removed")


def cmd_backup(m, args):
    _master(m)
    keep = args.keep if args.keep is not None else m.settings.get("backup_keep", 5)
    summary = m.backup(keep=keep, only_enabled=not args.include_disabled)
    ok = sum(1 for r in summary if r["ok"])
    changed = sum(1 for r in summary if r.get("changed"))
    for r in summary:
        if r["ok"]:
            tag = "changed" if r.get("changed") else "no change"
            print(f"  {r['device']}: {tag}, {r['kept']} copies kept")
        else:
            print(f"  {r['device']}: ERROR {r['error']}")
    print(f"backup complete: {ok}/{len(summary)} ok, {changed} changed, keeping {keep} copies each")
    if ok < len(summary):
        sys.exit(1)


def cmd_collect(m, args):
    _master(m)
    if args.all:
        results = m.collect_all()
        for r in results:
            _print_result(r)
        ok = sum(1 for r in results if r.ok)
        ch = sum(1 for r in results if r.changed)
        print(f"\n{ok}/{len(results)} ok, {ch} changed")
    else:
        if not args.name:
            print("specify a device name or --all", file=sys.stderr); sys.exit(1)
        _print_result(m.collect(args.name))


def cmd_run(m, args):
    _master(m)
    print(m.run(args.name, args.command))


def cmd_config(m, args):
    if args.version:
        print(m.store.read_version(args.name, args.version))
    else:
        cur = m.store.current(args.name)
        if cur is None:
            print("(no stored config)", file=sys.stderr); sys.exit(1)
        print(cur)


def cmd_versions(m, args):
    vs = m.store.versions(args.name)
    if not vs:
        print("(no versions)"); return
    base = m.store.get_baseline(args.name)
    bstamp = base["stamp"] if base else None
    for v in vs:
        mark = "  <= baseline" if v["stamp"] == bstamp else ""
        print(f"  {v['stamp']}  {v['hash'][:12]}  {v['ts']}{mark}")


def _color_diff(diff):
    G, R, C, X = "\033[32m", "\033[31m", "\033[36m", "\033[0m"
    out = []
    for line in diff.splitlines():
        if line.startswith(("+++", "---", "@@")):
            out.append(C + line + X)
        elif line.startswith("+"):
            out.append(G + line + X)
        elif line.startswith("-"):
            out.append(R + line + X)
        else:
            out.append(line)
    return "\n".join(out)


def cmd_diff(m, args):
    if args.stamps and len(args.stamps) == 2:
        d = m.store.diff_versions(args.name, args.stamps[0], args.stamps[1])
    else:
        vs = m.store.versions(args.name)
        if len(vs) < 2:
            print("need at least two versions to diff"); return
        d = m.store.diff_versions(args.name, vs[-2]["stamp"], vs[-1]["stamp"])
    if not d:
        print("(identical)"); return
    use_color = sys.stdout.isatty() and not args.no_color
    print(_color_diff(d) if use_color else d)


def cmd_runs(m, args):
    import datetime
    for row in m.inv.recent_runs(args.limit, device=args.device):
        ts = datetime.datetime.fromtimestamp(row["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        state = "OK " if row["ok"] else "ERR"
        ch = " changed" if row["changed"] else ""
        print(f"{ts}  {state}  {row['device']}{ch}  {row['message']}")


def cmd_platforms(m, args):
    print("supported platforms:")
    for p in _platforms():
        print("  " + p)


def cmd_web(m, args):
    from .web import serve
    if getattr(args, "tls_cert", None):
        m.settings["web_tls_cert"] = args.tls_cert
    if getattr(args, "tls_key", None):
        m.settings["web_tls_key"] = args.tls_key
    serve(m, bind=args.bind or m.settings["web_bind"],
          port=args.port or m.settings["web_port"])


# ---- v2 commands --------------------------------------------------------
def cmd_user(m, args):
    if args.action == "add":
        pw = getpass.getpass(f"Password for {args.name}: ")
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            print("passwords do not match", file=sys.stderr); sys.exit(1)
        m.users.create(args.name, pw, role=args.role, fullname=args.fullname or "")
        m.db.audit(args.actor, "user_create", args.name, args.role)
        print(f"user '{args.name}' created ({args.role})")
    elif args.action == "list":
        for u in m.users.all():
            dis = " [disabled]" if u["disabled"] else ""
            print(f"  {u['username']:<16} {u['role']:<10}{dis}  {u['fullname']}")
    elif args.action == "role":
        m.users.set_role(args.name, args.role)
        m.db.audit(args.actor, "user_update", args.name, f"role={args.role}")
        print(f"{args.name} -> {args.role}")
    elif args.action == "passwd":
        pw = getpass.getpass(f"New password for {args.name}: ")
        m.users.set_password(args.name, pw)
        print("password updated")
    elif args.action == "rm":
        m.users.delete(args.name)
        m.db.audit(args.actor, "user_delete", args.name, "")
        print(f"user '{args.name}' removed")


def cmd_group(m, args):
    if args.action == "add":
        m.inv.add_group(args.name, args.description or "")
        if args.member:
            m.inv.set_group_members(args.name, args.member)
        print(f"group '{args.name}' saved"
              + (f" ({len(args.member)} members)" if args.member else ""))
    elif args.action == "list":
        for g in m.inv.groups():
            print(f"  {g['name']}: {', '.join(g['members']) or '(empty)'}"
                  + (f"  -- {g['description']}" if g['description'] else ""))
    elif args.action == "members":
        m.inv.set_group_members(args.name, args.member or [])
        print(f"group '{args.name}' now has {len(args.member or [])} members")
    elif args.action == "rm":
        m.inv.delete_group(args.name)
        print(f"group '{args.name}' removed")


def _parse_target(spec):
    if ":" in spec:
        kind, value = spec.split(":", 1)
    else:
        kind, value = "device", spec
    return kind, value


def cmd_bulk(m, args):
    _master(m)
    kind, value = _parse_target(args.target)
    devices = m.inv.resolve_target(kind, value, only_enabled=not args.include_disabled)
    if not devices:
        print("no devices matched target", file=sys.stderr); sys.exit(1)
    body = ""
    if args.script:
        with open(args.script) as f:
            body = f.read()
    elif args.command:
        body = args.command
    elif args.mode != "remediate":
        print("provide --script FILE or --command, or use --mode remediate",
              file=sys.stderr); sys.exit(1)
    print(f"running mode={args.mode} on {len(devices)} device(s) "
          f"with {args.workers or m.settings['bulk_workers']} workers...")

    def on_result(r):
        tag = "OK " if r["ok"] else "ERR"
        print(f"  {tag} {r['device']}")
        if not r["ok"] or args.verbose:
            for line in r["output"].splitlines():
                print(f"      {line}")

    wf = _wf(m)
    job = wf.run_adhoc(devices=devices, mode=args.mode, body=body,
                       run_by=args.actor, title=args.title or f"cli bulk {args.mode}",
                       save=args.save)
    j = wf.get_job(job["id"])
    for r in j["results"]:
        on_result(r)
    print(f"\njob#{j['id']}: {j['summary']}")


def cmd_request(m, args):
    wf = _wf(m)
    if args.action == "submit":
        kind, value = _parse_target(args.target)
        body = ""
        if args.script:
            with open(args.script) as f:
                body = f.read()
        elif args.command:
            body = args.command
        rid = wf.submit(title=args.title, body=body, target_kind=kind,
                        target_value=value, mode=args.mode, requested_by=args.actor)
        print(f"submitted change request CR#{rid} (pending)")
    elif args.action == "list":
        for r in wf.list(status=args.status):
            print(f"  CR#{r['id']:<4} [{r['status']:<9}] {r['title']}  "
                  f"({r['mode']} {r['target_kind']}:{r['target_value']}) "
                  f"by {r['requested_by']}")
    elif args.action == "show":
        prev = wf.preview(args.id)
        if not prev:
            print("no such request", file=sys.stderr); sys.exit(1)
        cr = prev["request"]
        print(f"CR#{cr['id']} [{cr['status']}] {cr['title']}")
        print(f"  mode={cr['mode']} target={cr['target_kind']}:{cr['target_value']}")
        print(f"  requested by {cr['requested_by']}")
        if cr["reviewed_by"]:
            print(f"  reviewed by {cr['reviewed_by']} — {cr['review_note'] or 'ok'}")
        print("  --- resolved plan ---")
        for t in prev["targets"]:
            un = f"  !! unresolved: {t['unresolved']}" if t["unresolved"] else ""
            print(f"  {t['device']} ({t['host']}){un}")
            for ln in t["lines"]:
                print(f"      {ln}")
    elif args.action == "approve":
        wf.approve(args.id, args.actor)
        print(f"CR#{args.id} approved")
    elif args.action == "reject":
        wf.reject(args.id, args.actor, args.note or "")
        print(f"CR#{args.id} rejected")
    elif args.action == "execute":
        _master(m)
        job = wf.execute(args.id, args.actor, save=args.save)
        print(f"CR#{args.id} executed -> job#{job['id']}: {job['summary']}")
        for r in job["results"]:
            print(f"  {'OK ' if r['ok'] else 'ERR'} {r['device']}")


def cmd_baseline(m, args):
    if args.action == "set":
        b = m.store.set_baseline(args.name, args.version)
        m.db.audit(args.actor, "baseline_set", args.name, b["stamp"])
        print(f"baseline for '{args.name}' set to {b['stamp']}")
    elif args.action == "clear":
        m.store.clear_baseline(args.name)
        print(f"baseline for '{args.name}' cleared")
    elif args.action == "drift":
        d = m.store.drift(args.name)
        if not d["baselined"]:
            print("no baseline set"); return
        if not d["drifted"]:
            print(f"{args.name}: in sync with baseline ({d['baseline_stamp']})")
        else:
            print(f"{args.name}: DRIFTED from baseline ({d['baseline_stamp']})")
            use_color = sys.stdout.isatty()
            print(_color_diff(d["diff"]) if use_color else d["diff"])


def cmd_compliance(m, args):
    devices = m.inv.all(only_enabled=False)
    report = _compliance.evaluate_fleet(m.store, devices, args.standard)
    t = report["totals"]
    for dr in report["devices"]:
        if dr.get("skipped"):
            print(f"  {dr['device']:<20} (no stored config)")
            continue
        state = "PASS" if dr["failed"] == 0 else "FAIL"
        print(f"  {dr['device']:<20} {state}  ({dr['passed']} pass / {dr['failed']} fail)")
        if args.verbose:
            for r in dr["results"]:
                if r["status"] == "fail":
                    print(f"      [{r['severity']}] {r['id']}: {r['title']}")
                    print(f"          -> {r['remediation']}")
    print(f"\n{t['compliant_devices']}/{t['device_count']} devices compliant; "
          f"{t['pass']} checks passed, {t['fail']} failed")
    import json as _json
    import time as _time
    m.db.conn.execute(
        "INSERT INTO compliance_runs (ts, standard, run_by, total, passed, failed, report) "
        "VALUES (?,?,?,?,?,?,?)",
        (_time.time(), args.standard or "", args.actor, t["checks"], t["pass"],
         t["fail"], _json.dumps(report)))
    m.db.conn.commit()
    m.db.audit(args.actor, "compliance_run", args.standard or "all",
               f"{t['compliant_devices']}/{t['device_count']} compliant")


def cmd_snmp(m, args):
    _master(m)
    if args.action == "poll":
        targets = [args.name] if args.name else [d["name"] for d in m.inv.all()
                                                 if d.get("snmp_version")]
        for name in targets:
            res = m.snmp_poll(name, vendor_force=True)
            if res.get("ok"):
                ic = res.get("interfaces")
                ic = f", {ic} interfaces" if isinstance(ic, int) else ""
                print(f"  {name}: {res['sysname'] or '(no name)'} — {res['sysdescr'][:50]} "
                      f"[up {res['uptime']}]{ic}")
            else:
                print(f"  {name}: ERROR {res.get('error')}")
    elif args.action == "debug":
        import traceback as _tb
        from . import snmp as _snmp
        dev = m.inv.get(args.name)
        if not dev:
            print(f"no such device '{args.name}'", file=sys.stderr); sys.exit(1)
        _snmp.set_debug(2 if args.hex else 1)
        try:
            ver, comm, v3, port = m._snmp_params_for(dev)
        except Exception as e:
            print(f"could not resolve SNMP params: {e}", file=sys.stderr); sys.exit(1)
        to = m.settings.get("snmp_timeout", 2.0)
        print(f"device {args.name}: host={dev['host']} version={dev.get('snmp_version') or '-'} port={port} timeout={to}s")
        if v3:
            lvl = "authPriv" if v3.priv_proto else ("authNoPriv" if v3.auth_proto else "noAuthNoPriv")
            print(f"  v3: user={v3.username!r} level={lvl} auth={(v3.auth_proto or '-')} priv={(v3.priv_proto or '-')}")
            print(f"  compare with: snmpwalk -v3 -l {lvl} -u {v3.username} "
                  f"-a {(v3.auth_proto or '').upper()} -A '<authpass>' "
                  f"-x {(v3.priv_proto or '').upper()} -X '<privpass>' {dev['host']}:{port} system")
        else:
            print(f"  v2c community: (hidden)")
            print(f"  compare with: snmpwalk -v2c -c '<community>' {dev['host']}:{port} system")
        print("--- 1) system group (single GETs) ---")
        try:
            facts = _snmp.poll_system(dev["host"], port=port, version=ver, community=comm, v3=v3, timeout=to)
            print("  OK:", {k: facts.get(k) for k in ("reachable", "sysname", "sysdescr", "uptime")})
        except Exception as e:
            print("  FAILED:", repr(e)); _tb.print_exc()
        print("--- 2) interface table (multi-varbind GETNEXT, our default) ---")
        try:
            r_multi = _snmp.walk_table(dev["host"], list(_snmp.IF.values()), version=ver,
                                       community=comm, v3=v3, port=port, timeout=to)
            print(f"  multi-varbind walk: {len(r_multi)} rows")
        except Exception as e:
            r_multi = {}; print("  FAILED:", repr(e)); _tb.print_exc()
        print("--- 3) interface table (one OID at a time, like snmpwalk) ---")
        try:
            r_single = _snmp.walk_table(dev["host"], list(_snmp.IF.values()), version=ver,
                                        community=comm, v3=v3, port=port, timeout=to, single=True)
            print(f"  single-OID walk: {len(r_single)} rows")
        except Exception as e:
            r_single = {}; print("  FAILED:", repr(e)); _tb.print_exc()
        if not r_multi and r_single:
            print("\nDIAGNOSIS: this agent rejects multi-varbind GETNEXT. NetConfig auto-falls back "
                  "to single-OID walking, so interface polling will work. If it still didn't, "
                  "send this output.")
        elif not r_multi and not r_single:
            print("\nDIAGNOSIS: no interface rows either way. Check the OID subtree your agent exposes "
                  "and that the credentials/community match your working snmpwalk exactly.")
        _snmp.set_debug(0)
    elif args.action == "stats":
        ifs = m.inv.get_interfaces(args.name)
        if not ifs:
            print("(no interface data — run 'snmp poll' first)"); return
        def _bps(v):
            if v is None:
                return "-"
            for u in ("bps", "Kbps", "Mbps", "Gbps"):
                if v < 1000:
                    return f"{v:.0f}{u}"
                v /= 1000
            return f"{v:.0f}Tbps"
        print(f"{'#':<4} {'interface':<16} {'oper':<6} {'in':>11} {'out':>11} {'errs':>6}")
        for i in ifs:
            errs = (i["in_errors"] or 0) + (i["out_errors"] or 0)
            print(f"{i['ifindex']:<4} {i['descr'][:16]:<16} {i['oper']:<6} "
                  f"{_bps(i['in_bps']):>11} {_bps(i['out_bps']):>11} {errs:>6}")


def cmd_audit(m, args):
    for a in reversed(m.db.recent_audit(args.limit)):
        import datetime
        ts = datetime.datetime.fromtimestamp(a["ts"]).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts}  {a['actor']:<12} {a['action']:<18} {a['target']:<18} {a['detail']}")


# ---- parser -------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(prog="netconfig",
                                description="Zero-dependency network configuration manager")
    p.add_argument("--home", help="data directory (default $NETCONFIG_HOME or ./netconfig-data)")
    p.add_argument("--actor", default="cli", help="who to attribute actions to in the audit trail")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)
    sub.add_parser("platforms").set_defaults(func=cmd_platforms)

    v = sub.add_parser("vault"); vs = v.add_subparsers(dest="action", required=True)
    vs.add_parser("create")
    sset = vs.add_parser("set")
    sset.add_argument("name"); sset.add_argument("--username", required=True)
    sset.add_argument("--ask-password", action="store_true")
    sset.add_argument("--ask-enable", action="store_true")
    sset.add_argument("--key-path")
    sset.add_argument("--snmp-user", help="SNMPv3 username (if different from --username)")
    sset.add_argument("--snmp-community")
    sset.add_argument("--snmp-auth-pass", action="store_true",
                      help="prompt for SNMPv3 auth password")
    sset.add_argument("--snmp-auth-proto", choices=["md5","sha","sha224","sha256","sha384","sha512"])
    sset.add_argument("--snmp-priv-pass", action="store_true",
                      help="prompt for SNMPv3 priv password")
    sset.add_argument("--snmp-priv-proto", choices=["aes","aes192","aes256"])
    sset.add_argument("--snmp-port", type=int, help="non-standard SNMP port (default 161)")
    vs.add_parser("list")
    srm = vs.add_parser("rm"); srm.add_argument("name")
    vs.add_parser("unlock", help="verify the master password (CLI is stateless)")
    v.set_defaults(func=cmd_vault)

    d = sub.add_parser("device"); ds = d.add_subparsers(dest="action", required=True)
    da = ds.add_parser("add")
    da.add_argument("name"); da.add_argument("--host", required=True)
    da.add_argument("--port", type=int, default=22)
    da.add_argument("--platform", default="generic")
    da.add_argument("--type", dest="device_type", choices=["system","network","application"], default="network", help="device category")
    da.add_argument("--secret-name", "--secret", dest="secret",
                    help="name of an existing vault secret to use (a label, NOT a password)")
    da.add_argument("--enable-secret")
    da.add_argument("--use-key", action="store_true")
    da.add_argument("--legacy", action="store_true")
    da.add_argument("--scrub", action="store_true")
    da.add_argument("--disabled", action="store_true")
    da.add_argument("--tag", action="append")
    da.add_argument("--notes")
    da.add_argument("--snmp-version", choices=["v2c", "v3"])
    da.add_argument("--snmp-secret-name", "--snmp-secret", dest="snmp_secret",
                    help="name of an existing vault secret holding SNMP credentials")
    _add_inline_cred_args(da)
    # set-cred: enter/update this device's credentials inline (auto-stored in the vault)
    dsc = ds.add_parser("set-cred", help="set a device's SSH/SNMP credentials directly")
    dsc.add_argument("name")
    _add_inline_cred_args(dsc)
    ds.add_parser("list")
    dsh = ds.add_parser("show"); dsh.add_argument("name")
    drm = ds.add_parser("rm"); drm.add_argument("name")
    d.set_defaults(func=cmd_device)

    c = sub.add_parser("collect")
    c.add_argument("name", nargs="?"); c.add_argument("--all", action="store_true")
    bk = sub.add_parser("backup", help="collect all devices and keep N copies (weekly backup)")
    bk.add_argument("--keep", type=int, default=None, help="copies to keep per device (default 5)")
    bk.add_argument("--include-disabled", action="store_true")
    bk.set_defaults(func=cmd_backup)
    c.set_defaults(func=cmd_collect)

    r = sub.add_parser("run"); r.add_argument("name"); r.add_argument("command")
    r.set_defaults(func=cmd_run)

    cf = sub.add_parser("config"); cf.add_argument("name")
    cf.add_argument("--version"); cf.set_defaults(func=cmd_config)

    ver = sub.add_parser("versions"); ver.add_argument("name")
    ver.set_defaults(func=cmd_versions)

    df = sub.add_parser("diff"); df.add_argument("name")
    df.add_argument("stamps", nargs="*"); df.add_argument("--no-color", action="store_true")
    df.set_defaults(func=cmd_diff)

    rn = sub.add_parser("runs"); rn.add_argument("--device")
    rn.add_argument("--limit", type=int, default=50); rn.set_defaults(func=cmd_runs)

    w = sub.add_parser("web"); w.add_argument("--bind"); w.add_argument("--port", type=int)
    w.add_argument("--tls-cert", help="PEM certificate for optional built-in TLS")
    w.add_argument("--tls-key", help="PEM private key for optional built-in TLS")
    w.set_defaults(func=cmd_web)

    # --- v2 ---
    u = sub.add_parser("user"); us = u.add_subparsers(dest="action", required=True)
    ua = us.add_parser("add"); ua.add_argument("name")
    ua.add_argument("--role", default="viewer",
                    choices=["viewer", "operator", "approver", "admin"])
    ua.add_argument("--fullname")
    us.add_parser("list")
    ur = us.add_parser("role"); ur.add_argument("name")
    ur.add_argument("role", choices=["viewer", "operator", "approver", "admin"])
    up = us.add_parser("passwd"); up.add_argument("name")
    udel = us.add_parser("rm"); udel.add_argument("name")
    u.set_defaults(func=cmd_user)

    g = sub.add_parser("group"); gs = g.add_subparsers(dest="action", required=True)
    ga = gs.add_parser("add"); ga.add_argument("name")
    ga.add_argument("--description"); ga.add_argument("--member", action="append")
    gs.add_parser("list")
    gm = gs.add_parser("members"); gm.add_argument("name")
    gm.add_argument("--member", action="append")
    grm = gs.add_parser("rm"); grm.add_argument("name")
    g.set_defaults(func=cmd_group)

    b = sub.add_parser("bulk", help="run commands/config across a target concurrently")
    b.add_argument("--target", required=True,
                   help="device:NAME | group:NAME | tag:NAME | all:")
    b.add_argument("--mode", default="command", choices=["command", "config", "remediate"])
    b.add_argument("--script", help="file with commands (one per line, ${VAR} allowed)")
    b.add_argument("--command", help="single command/line to run")
    b.add_argument("--save", action="store_true", help="save to startup after config push")
    b.add_argument("--workers", type=int)
    b.add_argument("--title")
    b.add_argument("--include-disabled", action="store_true")
    b.add_argument("--verbose", action="store_true")
    b.set_defaults(func=cmd_bulk)

    rq = sub.add_parser("request"); rqs = rq.add_subparsers(dest="action", required=True)
    rsub = rqs.add_parser("submit"); rsub.add_argument("--title", required=True)
    rsub.add_argument("--target", required=True)
    rsub.add_argument("--mode", default="config", choices=["config", "remediate"])
    rsub.add_argument("--script"); rsub.add_argument("--command")
    rlist = rqs.add_parser("list"); rlist.add_argument("--status")
    rshow = rqs.add_parser("show"); rshow.add_argument("id", type=int)
    rap = rqs.add_parser("approve"); rap.add_argument("id", type=int)
    rrj = rqs.add_parser("reject"); rrj.add_argument("id", type=int); rrj.add_argument("--note")
    rex = rqs.add_parser("execute"); rex.add_argument("id", type=int)
    rex.add_argument("--save", action="store_true")
    rq.set_defaults(func=cmd_request)

    bl = sub.add_parser("baseline"); bls = bl.add_subparsers(dest="action", required=True)
    blset = bls.add_parser("set"); blset.add_argument("name"); blset.add_argument("--version")
    blclr = bls.add_parser("clear"); blclr.add_argument("name")
    bldr = bls.add_parser("drift"); bldr.add_argument("name")
    bl.set_defaults(func=cmd_baseline)

    cp = sub.add_parser("compliance")
    cp.add_argument("--standard", help="ISO 27001 | PCI-DSS (default: all)")
    cp.add_argument("--verbose", action="store_true")
    cp.set_defaults(func=cmd_compliance)

    sn = sub.add_parser("snmp"); sns = sn.add_subparsers(dest="action", required=True)
    snp = sns.add_parser("poll"); snp.add_argument("name", nargs="?")
    sns_stats = sns.add_parser("stats"); sns_stats.add_argument("name")
    sns_dbg = sns.add_parser("debug", help="verbose SNMP trace vs snmpwalk")
    sns_dbg.add_argument("name"); sns_dbg.add_argument("--hex", action="store_true", help="include packet hex")
    sn.set_defaults(func=cmd_snmp)

    au = sub.add_parser("audit"); au.add_argument("--limit", type=int, default=100)
    au.set_defaults(func=cmd_audit)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    m = Manager(args.home)
    try:
        args.func(m, args)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        os._exit(0)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
    finally:
        m.close()


if __name__ == "__main__":
    main()
