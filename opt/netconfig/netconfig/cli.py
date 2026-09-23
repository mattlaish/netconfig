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
import json
import os
import sys

from .manager import Manager
from .apitokens import ApiTokens, VALID_SCOPES
from .drivers import platforms as _platforms
from .workflow import Workflow
from . import compliance as _compliance
from .debug import DebugBundle
from .evidence_signing import signing_status


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

def cmd_debug(m, args):
    dbg = DebugBundle(m)
    if args.action == "collect":
        out = dbg.collect(args.output, require_signature=args.require_signature)
        print(out)
    elif args.action == "device":
        out = dbg.device_capture(args.name, args.output, require_signature=args.require_signature)
        print(out)
    elif args.action == "list":
        for item in dbg.list_bundles():
            print(f"{item['name']} {item['size']}")
    elif args.action == "cleanup":
        print("\n".join(dbg.cleanup(args.keep)))
    elif args.action == "maintenance":
        from . import diagnostic_maintenance as _diag_maint
        print(json.dumps(_diag_maint.run_once(m, actor=args.actor), indent=2, sort_keys=True))
    elif args.action == "verify":
        result = dbg.verify_bundle(args.name, args.trusted_fingerprint or [])
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.action == "signing-status":
        print(json.dumps(signing_status(m.settings), indent=2, sort_keys=True))


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
    p.add_argument("--snmp-priv-proto", choices=["aes","aes192","aes256","aes192c","aes256c"])
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
    elif args.action == "submit-structured":
        rid = wf.submit_automation(
            title=args.title, requested_by=args.actor,
            intent={
                "kind": "structured_change", "device": args.device,
                "resource": args.resource, "selectors": _selector_args(args.selector),
                "value": _json_value_arg(args.value),
            },
        )
        print(f"submitted structured change request CR#{rid} (pending)")
    elif args.action == "submit-desired":
        rid = wf.submit_automation(
            title=args.title, requested_by=args.actor,
            intent={"kind": "desired_apply", "desired_state_id": args.id,
                    "rollback_on_failure": not args.no_rollback},
        )
        print(f"submitted desired-state apply request CR#{rid} (pending)")
    elif args.action == "submit-campaign-wave":
        rid = wf.submit_automation(
            title=args.title, requested_by=args.actor,
            intent={"kind": "campaign_wave", "campaign_id": args.id},
        )
        print(f"submitted campaign-wave request CR#{rid} (pending)")
    elif args.action == "submit-rollback":
        rid = wf.submit_automation(
            title=args.title, requested_by=args.actor,
            intent={"kind": "structured_rollback", "transaction_id": args.id},
        )
        print(f"submitted structured rollback request CR#{rid} (pending)")
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
        if cr["mode"] == "automation":
            auto = prev["automation"]
            print(f"  snapshot match: {auto['snapshot_matches']}")
            print(json.dumps(auto["submitted_snapshot"], indent=4, sort_keys=True))
        else:
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
                  f"-x {_snmp.net_snmp_priv_name(v3.priv_proto)} -X '<privpass>' {dev['host']}:{port} system")
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
def cmd_api_token(m, args):
    tokens = ApiTokens(m.db.conn)
    if args.action == "create":
        token_id, raw = tokens.create(args.name, args.scope, created_by=args.actor, role=args.role)
        m.db.audit(args.actor, "api_token_create", str(token_id), ",".join(args.scope))
        print(f"id={token_id} name={args.name}")
        print(raw)
        print("Save this token now; only its SHA-256 hash is stored.")
    elif args.action == "list":
        for row in tokens.list():
            print(f"{row['id']}	{row['name']}	{row['scopes']}	{'disabled' if row['disabled'] else 'active'}")
    elif args.action == "revoke":
        tokens.revoke(args.id); m.db.audit(args.actor, "api_token_revoke", str(args.id), "")
        print("revoked")


def cmd_trace(m, args):
    traces = m.protocol_traces
    if args.action == "start":
        item = traces.start(args.device, args.protocol, actor=args.actor,
                            incident_ref=args.incident, ttl=args.ttl,
                            max_events=args.max_events, max_bytes=args.max_bytes,
                            reason=args.reason or "")
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "list":
        print(json.dumps(traces.list(device=args.device, incident_ref=args.incident,
                                     status=args.status, limit=args.limit),
                         indent=2, sort_keys=True))
    elif args.action == "show":
        item = traces.get(args.ref)
        if not item:
            print("protocol trace not found", file=sys.stderr); sys.exit(1)
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "events":
        print(json.dumps(traces.events(args.ref, args.limit), indent=2, sort_keys=True))
    elif args.action == "stop":
        print(json.dumps(traces.stop(args.ref, actor=args.actor), indent=2, sort_keys=True))


def cmd_incident(m, args):
    incidents = m.incidents
    if args.action == "create":
        item = incidents.create(args.title, args.description or "", args.severity,
                                created_by=args.actor, tags=args.tag or [])
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "list":
        rows = incidents.list(status=args.status, severity=args.severity, limit=args.limit)
        if not rows:
            print("(no incidents)"); return
        for row in rows:
            print(f"{row['incident_key']}\t{row['severity']}\t{row['status']}\t{row['title']}")
    elif args.action == "show":
        item = incidents.get(args.ref)
        if not item:
            print("incident not found", file=sys.stderr); sys.exit(1)
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "update":
        tags = args.tag if args.tag is not None else None
        item = incidents.update(args.ref, args.actor, title=args.title,
                                description=args.description, severity=args.severity, tags=tags)
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "status":
        item = incidents.set_status(args.ref, args.status, args.actor, note=args.note or "")
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "link-bundle":
        item = incidents.link_bundle(args.ref, args.bundle, args.actor)
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "unlink-bundle":
        item = incidents.unlink_bundle(args.ref, args.bundle, args.actor)
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "link-evidence":
        item = incidents.link_evidence(args.ref, args.type, args.source_id, args.actor,
                                       note=args.note or "")
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "link-drift":
        item = incidents.link_drift(args.ref, args.device, args.actor, note=args.note or "")
        print(json.dumps(item, indent=2, sort_keys=True))
    elif args.action == "unlink-evidence":
        rows = incidents.unlink_evidence(args.ref, args.link_id, args.actor)
        print(json.dumps(rows, indent=2, sort_keys=True))
    elif args.action == "evidence":
        item = incidents.get(args.ref)
        if not item:
            print("incident not found", file=sys.stderr); sys.exit(1)
        print(json.dumps(incidents.evidence_links(item["id"]), indent=2, sort_keys=True))
    elif args.action == "timeline":
        print(json.dumps(incidents.timeline(args.ref, args.limit), indent=2, sort_keys=True))
    elif args.action == "export-case":
        item = m.case_exports.export_case(
            args.ref, args.actor, args.bundle or [], args.reason or "",
            require_signature=args.require_signature)
        _meta, path = m.case_exports.get_export(args.ref, item["export_key"])
        print(json.dumps(item, indent=2, sort_keys=True))
        if path is not None:
            print(f"path={path}")
    elif args.action == "exports":
        print(json.dumps(m.case_exports.list_exports(args.ref, args.limit), indent=2, sort_keys=True))
    elif args.action == "verify-export":
        result = m.case_exports.verify_signature(
            args.ref, args.export_key, args.trusted_fingerprint or [], actor=args.actor)
        print(json.dumps(result, indent=2, sort_keys=True))


def cmd_topology(m, args):
    if args.discover:
        # Discovery may need SNMP/SSH credentials.  Unlock inside this same CLI
        # process so a stateless `vault unlock` command is not misleading.
        _master(m)
        names = [args.device] if args.device else [d["name"] for d in m.inv.all() if d.get("snmp_version")]
        for name in names:
            rows = m.discover_neighbors(name)
            print(f"{name}: {len(rows)} neighbour(s)")
    if args.identities:
        rows = m.topology_identities()
        if args.device:
            rows = [r for r in rows if r.get("device") == args.device]
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True)); return
        for r in rows:
            ident = r.get("chassis_serial") or r.get("chassis_mac") or r.get("chassis_id") or "-"
            print(f"{r['device']} sysName={r.get('sys_name') or '-'} chassis={ident} model={r.get('chassis_model') or '-'} interfaces={len(r.get('interfaces') or [])}")
        return
    if args.impact:
        value = m.downstream_impact(args.impact, args.port, args.max_depth)
        if args.json:
            print(json.dumps(value, indent=2, sort_keys=True)); return
        print(f"root={value['root_device']} port={value['root_port'] or '*'} downstream={value['device_count']} edges={value['edge_count']}")
        for r in value["devices"]:
            print(f"  depth={r['depth']} {r['device']} via {r['via']}")
        return
    rows = m.db.get_neighbors(args.device)
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True)); return
    for n in rows:
        if n.get("managed_neighbor"):
            state = "managed:" + n["neighbor_device"]
        else:
            state = n.get("resolution_state") or "UNMANAGED"
        print(f"{n['device']} {n['local_port']} -> {n['sys_name'] or n['chassis_id']} {n['port_id']} [{n['protocol']}] {state}")


def cmd_endpoints(m, args):
    if args.refresh:
        if args.device:
            result = m.snmp_poll(args.device)
            if not result.get("ok"):
                print(result.get("error", "SNMP poll failed"), file=sys.stderr); sys.exit(1)
        else:
            m.snmp_poll_all()
    rows = m.endpoint_inventory(args.device)
    if args.json:
        print(json.dumps({"summary": m.endpoint_summary(args.device), "endpoints": rows}, indent=2, sort_keys=True))
        return
    for row in rows:
        att = row.get("attachment") or {}
        ips = ",".join((row.get("ipv4") or []) + (row.get("ipv6") or [])) or "-"
        loc = "-"
        if att:
            port = att.get("ifdescr") or ("if" + att.get("ifindex", "") if att.get("ifindex") else att.get("bridge_port", ""))
            vlan = (" vlan=" + att.get("vlan_id", "")) if att.get("vlan_id") else ""
            loc = f"{att.get('device','')}:{port}{vlan}"
        print(f"{row['mac']} {ips} {row['status']} {row['confidence']} {loc}")



def cmd_events(m, args):
    rows = m.events.list(limit=args.limit, device=args.device, include_suppressed=not args.unsuppressed_only)
    if args.json:
        print(json.dumps({"events": rows, "suppressions": m.events.suppressions(active_only=True)}, indent=2, sort_keys=True))
        return
    for r in rows:
        sup = " SUPPRESSED" if r.get("suppressed") else ""
        dev = r.get("device") or r.get("source") or "-"
        iface = (" " + r.get("interface")) if r.get("interface") else ""
        print(f"{int(r.get('last_ts') or 0)} {r.get('severity')} {r.get('event_type')} {dev}{iface} x{r.get('event_count',1)}{sup} {r.get('message','')}")


def cmd_alerts(m, args):
    life = m.alert_lifecycle
    if args.action == "list":
        rows = life.list(state=args.state, device=args.device, limit=args.limit)
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True)); return
        for r in rows:
            print(f"#{r['id']} {r['state']} {r['severity']} {r['device'] or '-'} {r['event_type']} x{r['event_count']} {r['message']}")
        return
    if args.action == "ack":
        row=life.acknowledge(args.id,args.actor,args.note); print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"alert #{row['id']} {row['state']}"); return
    if args.action == "resolve":
        row=life.resolve(args.id,args.actor,args.note); print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"alert #{row['id']} {row['state']}"); return
    if args.action == "maintenance-add":
        row=life.add_maintenance(args.name,args.actor,minutes=args.minutes,device=args.device or "",reason=args.reason or "")
        print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"maintenance #{row['id']} {row['name']}"); return
    if args.action == "maintenance-list":
        rows=life.maintenance(active_only=args.active_only)
        if args.json:
            print(json.dumps(rows,indent=2,sort_keys=True)); return
        for r in rows:
            print(f"#{r['id']} {r['name']} device={r['device'] or 'all'} {int(r['start_ts'])}-{int(r['end_ts'])} cancelled={bool(r.get('cancelled_ts'))}")
        return
    if args.action == "maintenance-cancel":
        row=life.cancel_maintenance(args.id,args.actor); print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"maintenance #{row['id']} cancelled"); return
    if args.action == "report-add":
        row=life.add_report_schedule(args.name,args.actor,interval_seconds=args.interval,lookback_hours=args.lookback_hours)
        print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"report schedule #{row['id']} {row['name']}"); return
    if args.action == "report-list":
        value={"schedules":life.report_schedules(),"runs":life.report_runs(args.limit)}
        if args.json:
            print(json.dumps(value,indent=2,sort_keys=True)); return
        for r in value["schedules"]:
            print(f"schedule #{r['id']} {'on' if r['enabled'] else 'off'} {r['name']} every={r['interval_seconds']}s lookback={r['lookback_hours']}h")
        for r in value["runs"][:10]:
            print(f"run #{r['id']} status={r['status']} {int(r['finished_ts'])}")
        return
    if args.action == "report-run":
        row=life.run_report(schedule_id=args.id,lookback_hours=args.lookback_hours,actor=args.actor)
        print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"report run #{row['id']} complete"); return
    if args.action == "report-state":
        row=life.set_report_schedule_enabled(args.id,args.enabled,args.actor); print(json.dumps(row,indent=2,sort_keys=True) if args.json else f"schedule #{row['id']} {'enabled' if row['enabled'] else 'disabled'}"); return
    if args.action == "deliveries":
        rows=life.notifications(args.limit)
        if args.json:
            print(json.dumps(rows,indent=2,sort_keys=True)); return
        for r in rows:
            print(f"#{r['id']} {r['kind']} {r['state']} attempts={r['attempts']} next={int(r['next_attempt_ts'])}")
        return
    if args.action == "tick":
        out=life.tick(); print(json.dumps(out,indent=2,sort_keys=True)); return

def cmd_storage(m, args):
    import time
    if args.action == "status":
        out = m.storage_status()
        out["nodes"] = m.db.list_cluster_nodes(time.time() - max(0, int(args.node_max_age)))
        print(json.dumps(out, indent=2, sort_keys=True))
        return
    if args.action == "tasks":
        print(json.dumps(m.db.list_distributed_tasks(args.queue, args.limit), indent=2, sort_keys=True))
        return
    if args.action == "enqueue":
        payload = args.payload or "{}"
        try:
            json.loads(payload)
        except Exception:
            print("--payload must be valid JSON", file=sys.stderr); sys.exit(2)
        row = m.db.enqueue_distributed_task(args.queue, args.kind, payload, time.time())
        print(json.dumps(row, indent=2, sort_keys=True)); return
    if args.action == "claim":
        row = m.db.claim_distributed_task(args.queue, args.worker, time.time(), args.lease_seconds)
        print(json.dumps(row, indent=2, sort_keys=True)); return
    if args.action == "finish":
        row = m.db.finish_distributed_task(
            args.id, args.worker, time.time(), ok=not args.failed,
            result=args.result or "", error=args.error or "")
        print(json.dumps(row, indent=2, sort_keys=True)); return
    if args.action == "migrate-sqlite":
        from .credentials import postgres_core_password
        from .postgres_core import PostgresDatabase, migrate_sqlite_to_postgres, postgres_params
        target = m.db if getattr(m.db, "dialect", "sqlite") == "postgres" else None
        owned = False
        if target is None:
            password, _ = postgres_core_password()
            target = PostgresDatabase(params=postgres_params(m.settings, password=password))
            owned = True
        try:
            out = migrate_sqlite_to_postgres(args.source or m.paths.inventory_db, target)
            print(json.dumps(out, indent=2, sort_keys=True))
        finally:
            if owned:
                target.close()
        return
    if args.action == "backup-postgres":
        from .credentials import postgres_core_password
        from .postgres_backup import backup_core_database
        password, _ = postgres_core_password()
        out = backup_core_database(
            m.settings, password, args.output, timeout=args.timeout, overwrite=args.overwrite)
        m.db.audit(args.actor, "postgres_core_backup", out.get("sha256", ""),
                   f"bytes={out.get('bytes', 0)}")
        print(json.dumps(out, indent=2, sort_keys=True))
        return
    if args.action == "restore-postgres":
        from .credentials import postgres_core_password
        from .postgres_backup import restore_core_database
        password, _ = postgres_core_password()
        out = restore_core_database(
            m.settings, password, args.input, target_dbname=args.target_dbname,
            confirm=args.confirm, expected_sha256=args.sha256, timeout=args.timeout)
        m.db.audit(args.actor, "postgres_core_restore_drill", args.target_dbname,
                   f"sha256={out.get('sha256', '')}")
        print(json.dumps(out, indent=2, sort_keys=True))
        return


def _cmd_restore_postgres_offline(args):
    """Recovery-safe restore path that does not open the active core database."""
    from . import config as _cfg
    from .credentials import postgres_core_password
    from .postgres_backup import restore_core_database

    paths = _cfg.Paths(args.home)
    settings = _cfg.load_settings(paths)
    password, _ = postgres_core_password()
    out = restore_core_database(
        settings, password, args.input, target_dbname=args.target_dbname,
        confirm=args.confirm, expected_sha256=args.sha256, timeout=args.timeout)
    out["audit_note"] = (
        "recovery-safe restore bypassed active core initialization; retain shell/change evidence")
    print(json.dumps(out, indent=2, sort_keys=True))


def cmd_qualify(m, args):
    from .qualification import runtime_preflight
    report = runtime_preflight(m)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report.get("ok"):
        sys.exit(1)


def cmd_protocol(m, args):
    if args.action == "list":
        rows = m.protocol_status()
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True)); return
        for row in rows:
            prof = row.get("profile") or {}
            print(f"{row['device']} {prof.get('protocol','cli_ssh')} enabled={prof.get('enabled',False)} fallback={prof.get('allow_cli_fallback',False)}")
        return
    if args.action == "show":
        print(json.dumps(m.protocol_status(args.device), indent=2, sort_keys=True)); return
    if args.action == "set":
        row = m.protocol_profiles.set(
            args.device, args.protocol, enabled=not args.disabled, port=args.port or 0,
            path=args.path or "", secret_ref=args.secret_ref or "",
            tls_verify=not args.no_tls_verify, ca_file=args.ca_file or "",
            allow_cli_fallback=args.allow_cli_fallback)
        print(json.dumps(row, indent=2, sort_keys=True)); return
    if args.action == "delete":
        m.protocol_profiles.delete(args.device); print(f"deleted protocol profile for {args.device}"); return
    if args.action == "collect":
        result = m.protocol_collect(args.device)
        print(json.dumps({"device":result.device,"ok":result.ok,"changed":result.changed,"message":result.message,"version":result.version}, indent=2, sort_keys=True))
        if not result.ok:
            sys.exit(1)
        return
    if args.action == "capabilities":
        print(json.dumps(m.protocol_capabilities(args.device), indent=2, sort_keys=True)); return
    if args.action == "state":
        print(json.dumps(m.protocol_read_state(args.device, path=args.path), indent=2, sort_keys=True)); return
    if args.action == "subscribe-once":
        print(json.dumps(m.protocol_subscribe_once(args.device, path=args.path), indent=2, sort_keys=True)); return


def _json_value_arg(value):
    raw = str(value or "")
    if raw.startswith("@"):
        with open(raw[1:], encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("JSON argument must be valid JSON or @file.json") from exc


def _selector_args(values):
    out = {}
    for item in values or []:
        if "=" not in item:
            raise ValueError("selector must be KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key or key in out:
            raise ValueError("selector keys must be non-empty and unique")
        out[key] = value
    return out


def cmd_automation(m, args):
    action = args.action
    if action == "status":
        print(json.dumps(m.automation_status(), indent=2, sort_keys=True))
        return
    if action == "model-list":
        print(json.dumps(m.vendor_models.list(), indent=2, sort_keys=True))
        return
    if action == "model-show":
        print(json.dumps(m.vendor_models.get(args.pack), indent=2, sort_keys=True))
        return
    if action == "model-resources":
        print(json.dumps(m.vendor_models.resources(args.device, args.protocol), indent=2, sort_keys=True))
        return
    if action == "model-create":
        row = m.vendor_models.create(
            name=args.pack,
            revision=args.revision,
            spec=_json_value_arg(args.spec),
            actor=args.actor,
        )
        print(json.dumps(row, indent=2, sort_keys=True))
        return
    if action in {"model-enable", "model-disable"}:
        row = m.vendor_models.set_enabled(
            args.pack, action == "model-enable", actor=args.actor
        )
        print(json.dumps(row, indent=2, sort_keys=True))
        return
    if action == "model-delete":
        m.vendor_models.delete(args.pack, actor=args.actor)
        print(json.dumps({"deleted": args.pack}, indent=2, sort_keys=True))
        return
    if action == "model-bind":
        print(
            json.dumps(
                m.vendor_models.bind(args.device, args.pack, actor=args.actor),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "model-unbind":
        m.vendor_models.unbind(args.device, actor=args.actor)
        print(json.dumps({"device": args.device, "binding": None}, indent=2, sort_keys=True))
        return
    if action == "model-bindings":
        print(json.dumps(m.vendor_models.list_bindings(), indent=2, sort_keys=True))
        return
    if action == "model-binding":
        print(json.dumps(m.vendor_models.binding_detail(args.device), indent=2, sort_keys=True))
        return
    if action == "change":
        raise ValueError("direct structured writes are disabled; use request submit-structured, approve, then execute")
    if action == "change-list":
        print(json.dumps(m.structured_changes.list(args.limit), indent=2, sort_keys=True))
        return
    if action == "change-rollback":
        raise ValueError("direct rollback is disabled; use request submit-rollback, approve, then execute")
    if action == "change-interrupted":
        print(
            json.dumps(
                m.structured_changes.interrupted(args.stale_seconds),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "change-mark-interrupted":
        print(
            json.dumps(
                m.structured_changes.mark_interrupted_for_recovery(
                    actor=args.actor, stale_seconds=args.stale_seconds
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "change-recover":
        print(
            json.dumps(
                m.structured_changes.recover(args.id, actor=args.actor),
                indent=2, sort_keys=True,
            )
        )
        return
    if action == "telemetry-add":
        row = m.telemetry.create(
            name=args.name,
            device=args.device,
            path=args.path,
            mode=args.mode,
            sample_interval_ms=args.sample_interval_ms,
            heartbeat_interval_ms=args.heartbeat_interval_ms,
            window_seconds=args.window_seconds,
            collection_interval_seconds=args.collection_interval_seconds,
            retention_days=args.retention_days,
            actor=args.actor,
        )
        print(json.dumps(row, indent=2, sort_keys=True))
        return
    if action == "telemetry-list":
        print(json.dumps(m.telemetry.list(), indent=2, sort_keys=True))
        return
    if action == "telemetry-capture":
        print(json.dumps(m.telemetry.capture_once(args.id, actor=args.actor), indent=2, sort_keys=True))
        return
    if action == "telemetry-window":
        print(
            json.dumps(
                m.telemetry.capture_window(
                    args.id, duration_seconds=args.duration_seconds, actor=args.actor
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "telemetry-samples":
        print(json.dumps(m.telemetry.samples(args.id, args.limit), indent=2, sort_keys=True))
        return
    if action == "telemetry-points":
        print(
            json.dumps(
                m.telemetry.points(
                    args.id,
                    value_path=args.value_path,
                    since_ts=args.since_ts,
                    limit=args.limit,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "telemetry-summary":
        print(
            json.dumps(
                m.telemetry.summary(
                    args.id,
                    value_path=args.value_path,
                    since_ts=args.since_ts,
                    limit=args.limit,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "telemetry-run-due":
        print(json.dumps(m.telemetry.run_due(actor=args.actor, limit=args.limit), indent=2, sort_keys=True))
        return
    if action in {"telemetry-enable", "telemetry-disable"}:
        print(
            json.dumps(
                m.telemetry.set_enabled(
                    args.id, action == "telemetry-enable", actor=args.actor
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "telemetry-delete":
        print(json.dumps(m.telemetry.delete(args.id, actor=args.actor), indent=2, sort_keys=True))
        return
    if action == "desired-create":
        row = m.desired_state.create(
            name=args.name,
            target_kind=args.target_kind,
            target_value=args.target_value,
            document=_json_value_arg(args.document),
            actor=args.actor,
            description=args.description or "",
        )
        print(json.dumps(row, indent=2, sort_keys=True))
        return
    if action == "desired-list":
        print(json.dumps(m.desired_state.list(), indent=2, sort_keys=True))
        return
    if action == "desired-show":
        print(json.dumps(m.desired_state.get(args.id), indent=2, sort_keys=True))
        return
    if action == "desired-update":
        document = _json_value_arg(args.document) if args.document else None
        print(
            json.dumps(
                m.desired_state.update(
                    args.id, document=document, description=args.description,
                    target_kind=args.target_kind, target_value=args.target_value, actor=args.actor,
                ),
                indent=2, sort_keys=True,
            )
        )
        return
    if action == "desired-publish":
        print(json.dumps(m.desired_state.publish(args.id, args.actor), indent=2, sort_keys=True))
        return
    if action == "desired-plan":
        print(json.dumps(m.desired_state.plan(args.id), indent=2, sort_keys=True))
        return
    if action == "desired-evaluate":
        print(json.dumps(m.desired_state.evaluate(args.id), indent=2, sort_keys=True))
        return
    if action == "desired-clone":
        print(
            json.dumps(
                m.desired_state.clone_revision(args.id, actor=args.actor, name=args.name),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "desired-runs":
        print(json.dumps(m.desired_state.runs(args.id, args.limit), indent=2, sort_keys=True))
        return
    if action == "desired-apply":
        raise ValueError("direct desired-state apply is disabled; use request submit-desired, approve, then execute")
    if action == "campaign-create":
        row = m.campaigns.create(
            name=args.name,
            desired_state_id=args.desired_state_id,
            wave_size=args.wave_size,
            max_failures=args.max_failures,
            canary_size=args.canary_size,
            rollback_on_failure=args.rollback_on_failure,
            actor=args.actor,
        )
        print(json.dumps(row, indent=2, sort_keys=True))
        return
    if action == "campaign-list":
        print(json.dumps(m.campaigns.list(), indent=2, sort_keys=True))
        return
    if action == "campaign-show":
        print(json.dumps(m.campaigns.get(args.id), indent=2, sort_keys=True))
        return
    if action in {"campaign-start", "campaign-pause", "campaign-resume", "campaign-abort"}:
        method = getattr(m.campaigns, action.split("-", 1)[1])
        print(json.dumps(method(args.id, args.actor), indent=2, sort_keys=True))
        return
    if action == "campaign-retry":
        print(
            json.dumps(
                m.campaigns.retry_failed(args.id, args.actor, wave=args.wave),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "campaign-wave":
        raise ValueError("direct campaign wave execution is disabled; use request submit-campaign-wave, approve, then execute")
    if action == "ha-status":
        print(json.dumps(m.ha.readiness(), indent=2, sort_keys=True))
        return
    if action == "ha-nodes":
        print(json.dumps(m.ha.nodes(args.stale_seconds), indent=2, sort_keys=True))
        return
    if action == "ha-drain":
        print(
            json.dumps(
                m.ha.set_node_state(
                    state="DRAINED" if args.final else "DRAINING",
                    actor=args.actor,
                    node_id=args.node_id or None,
                    reason=args.reason,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "ha-activate":
        print(
            json.dumps(
                m.ha.set_node_state(
                    state="ACTIVE", actor=args.actor, node_id=args.node_id or None
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "ha-drill-record":
        detail = _json_value_arg(args.detail) if args.detail else {}
        print(
            json.dumps(
                m.ha.record_drill(
                    kind=args.kind,
                    actor=args.actor,
                    state=args.state,
                    detail=detail,
                    verification_ref=args.verification_ref or "",
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "ha-drill-complete":
        detail = _json_value_arg(args.detail) if args.detail else {}
        print(
            json.dumps(
                m.ha.complete_drill(
                    args.id,
                    actor=args.actor,
                    state=args.state,
                    detail=detail,
                    verification_ref=args.verification_ref or "",
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return
    if action == "ha-drills":
        print(json.dumps(m.ha.drills(args.limit), indent=2, sort_keys=True))
        return
    raise ValueError("unsupported automation action")

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
    sset.add_argument("--snmp-priv-proto", choices=["aes","aes192","aes256","aes192c","aes256c"])
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
    rs = rqs.add_parser("submit-structured")
    rs.add_argument("device"); rs.add_argument("resource"); rs.add_argument("--title", required=True)
    rs.add_argument("--selector", action="append", default=[])
    rs.add_argument("--value", required=True, help="JSON scalar/object or @file.json")
    rd = rqs.add_parser("submit-desired")
    rd.add_argument("id", type=int); rd.add_argument("--title", required=True); rd.add_argument("--no-rollback", action="store_true")
    rcw = rqs.add_parser("submit-campaign-wave")
    rcw.add_argument("id", type=int); rcw.add_argument("--title", required=True)
    rr = rqs.add_parser("submit-rollback")
    rr.add_argument("id", type=int); rr.add_argument("--title", required=True)
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

    topo = sub.add_parser("topology", help="show/discover LLDP/CDP neighbours")
    topo.add_argument("--device"); topo.add_argument("--discover", action="store_true")
    topo.add_argument("--identities", action="store_true", help="show normalized managed-device identity")
    topo.add_argument("--impact", metavar="DEVICE", help="show observed managed-L2 downstream impact")
    topo.add_argument("--port", help="limit impact to the root device's first-hop local port")
    topo.add_argument("--max-depth", type=int, default=16)
    topo.add_argument("--json", action="store_true")
    topo.set_defaults(func=cmd_topology)

    ep = sub.add_parser("endpoints", help="VLAN-aware IP/MAC/switch/port correlation")
    ep.add_argument("--device")
    ep.add_argument("--refresh", action="store_true", help="poll SNMP before showing correlation")
    ep.add_argument("--json", action="store_true")
    ep.set_defaults(func=cmd_endpoints)

    ev = sub.add_parser("events", help="NI-3 unified operational event stream")
    ev.add_argument("--device")
    ev.add_argument("--limit", type=int, default=200)
    ev.add_argument("--unsuppressed-only", action="store_true")
    ev.add_argument("--json", action="store_true")
    ev.set_defaults(func=cmd_events)

    al = sub.add_parser("alerts", help="NI-4 operational alert/report lifecycle")
    als = al.add_subparsers(dest="action", required=True)
    alp = als.add_parser("list"); alp.add_argument("--state", choices=["OPEN","ACKNOWLEDGED","RESOLVED"]); alp.add_argument("--device"); alp.add_argument("--limit",type=int,default=200); alp.add_argument("--json",action="store_true")
    for name in ("ack","resolve"):
        ap=als.add_parser(name); ap.add_argument("id",type=int); ap.add_argument("--note",default=""); ap.add_argument("--json",action="store_true")
    ma=als.add_parser("maintenance-add"); ma.add_argument("name"); ma.add_argument("--device"); ma.add_argument("--minutes",type=int,default=60); ma.add_argument("--reason",default=""); ma.add_argument("--json",action="store_true")
    ml=als.add_parser("maintenance-list"); ml.add_argument("--active-only",action="store_true"); ml.add_argument("--json",action="store_true")
    mc=als.add_parser("maintenance-cancel"); mc.add_argument("id",type=int); mc.add_argument("--json",action="store_true")
    ra=als.add_parser("report-add"); ra.add_argument("name"); ra.add_argument("--interval",type=int,default=86400); ra.add_argument("--lookback-hours",type=int,default=24); ra.add_argument("--json",action="store_true")
    rl=als.add_parser("report-list"); rl.add_argument("--limit",type=int,default=50); rl.add_argument("--json",action="store_true")
    rr=als.add_parser("report-run"); rr.add_argument("--id",type=int); rr.add_argument("--lookback-hours",type=int); rr.add_argument("--json",action="store_true")
    rs=als.add_parser("report-state"); rs.add_argument("id",type=int); rs.add_argument("--enabled",action=argparse.BooleanOptionalAction,default=True); rs.add_argument("--json",action="store_true")
    dl=als.add_parser("deliveries"); dl.add_argument("--limit",type=int,default=100); dl.add_argument("--json",action="store_true")
    als.add_parser("tick")
    al.set_defaults(func=cmd_alerts)

    pr = sub.add_parser("protocol", help="PH-3 structured protocol profiles and collection")
    prs = pr.add_subparsers(dest="action", required=True)
    pl = prs.add_parser("list"); pl.add_argument("--json", action="store_true")
    ps = prs.add_parser("show"); ps.add_argument("device")
    pset = prs.add_parser("set"); pset.add_argument("device"); pset.add_argument("protocol", choices=["cli_ssh","netconf","restconf","gnmi"]); pset.add_argument("--port", type=int); pset.add_argument("--path"); pset.add_argument("--secret-ref"); pset.add_argument("--ca-file"); pset.add_argument("--no-tls-verify", action="store_true"); pset.add_argument("--allow-cli-fallback", action="store_true"); pset.add_argument("--disabled", action="store_true")
    pd = prs.add_parser("delete"); pd.add_argument("device")
    pc = prs.add_parser("collect"); pc.add_argument("device")
    pcap = prs.add_parser("capabilities"); pcap.add_argument("device")
    pst = prs.add_parser("state"); pst.add_argument("device"); pst.add_argument("--path")
    psub = prs.add_parser("subscribe-once"); psub.add_argument("device"); psub.add_argument("--path")
    pr.set_defaults(func=cmd_protocol)

    auto = sub.add_parser("automation", help="PH-4/NI-5/NA/VM/HA structured automation")
    aus = auto.add_subparsers(dest="action", required=True)
    aus.add_parser("status")
    aus.add_parser("model-list")
    mshow = aus.add_parser("model-show")
    mshow.add_argument("pack")
    mres = aus.add_parser("model-resources")
    mres.add_argument("device")
    mres.add_argument("--protocol", choices=["netconf", "restconf", "gnmi"])
    mcreate = aus.add_parser("model-create")
    mcreate.add_argument("pack")
    mcreate.add_argument("revision")
    mcreate.add_argument("--spec", required=True, help="JSON object or @file.json")
    for name in ("model-enable", "model-disable", "model-delete"):
        parser = aus.add_parser(name)
        parser.add_argument("pack")
    mbind = aus.add_parser("model-bind")
    mbind.add_argument("device")
    mbind.add_argument("pack")
    munbind = aus.add_parser("model-unbind")
    munbind.add_argument("device")
    aus.add_parser("model-bindings")
    mbinding = aus.add_parser("model-binding")
    mbinding.add_argument("device")

    change = aus.add_parser("change")
    change.add_argument("device")
    change.add_argument("resource")
    change.add_argument("--selector", action="append", default=[])
    change.add_argument("--value", required=True, help="JSON scalar/object or @file.json")
    change.add_argument("--reference")
    change.add_argument("--approved", action="store_true")
    change_list = aus.add_parser("change-list")
    change_list.add_argument("--limit", type=int, default=200)
    change_rollback = aus.add_parser("change-rollback")
    change_rollback.add_argument("id", type=int)
    change_rollback.add_argument("--reference")
    change_rollback.add_argument("--approved", action="store_true")
    for name in ("change-interrupted", "change-mark-interrupted"):
        parser = aus.add_parser(name)
        parser.add_argument("--stale-seconds", type=int, default=300)
    change_recover = aus.add_parser("change-recover")
    change_recover.add_argument("id", type=int)

    telemetry_add = aus.add_parser("telemetry-add")
    telemetry_add.add_argument("name")
    telemetry_add.add_argument("device")
    telemetry_add.add_argument("path")
    telemetry_add.add_argument(
        "--mode", choices=["ON_CHANGE", "SAMPLE", "TARGET_DEFINED"], default="ON_CHANGE"
    )
    telemetry_add.add_argument("--sample-interval-ms", type=int, default=10_000)
    telemetry_add.add_argument("--heartbeat-interval-ms", type=int, default=0)
    telemetry_add.add_argument("--window-seconds", type=int, default=30)
    telemetry_add.add_argument("--collection-interval-seconds", type=int, default=60)
    telemetry_add.add_argument("--retention-days", type=int, default=30)
    aus.add_parser("telemetry-list")
    telemetry_capture = aus.add_parser("telemetry-capture")
    telemetry_capture.add_argument("id", type=int)
    telemetry_window = aus.add_parser("telemetry-window")
    telemetry_window.add_argument("id", type=int)
    telemetry_window.add_argument("--duration-seconds", type=int)
    telemetry_samples = aus.add_parser("telemetry-samples")
    telemetry_samples.add_argument("id", type=int)
    telemetry_samples.add_argument("--limit", type=int, default=500)
    telemetry_points = aus.add_parser("telemetry-points")
    telemetry_points.add_argument("id", type=int)
    telemetry_points.add_argument("--value-path")
    telemetry_points.add_argument("--since-ts", type=float, default=0)
    telemetry_points.add_argument("--limit", type=int, default=2000)
    telemetry_summary = aus.add_parser("telemetry-summary")
    telemetry_summary.add_argument("id", type=int)
    telemetry_summary.add_argument("value_path")
    telemetry_summary.add_argument("--since-ts", type=float, default=0)
    telemetry_summary.add_argument("--limit", type=int, default=20_000)
    telemetry_due = aus.add_parser("telemetry-run-due")
    telemetry_due.add_argument("--limit", type=int, default=32)
    for name in ("telemetry-enable", "telemetry-disable", "telemetry-delete"):
        parser = aus.add_parser(name)
        parser.add_argument("id", type=int)

    desired_create = aus.add_parser("desired-create")
    desired_create.add_argument("name")
    desired_create.add_argument("target_kind", choices=["device", "group", "tag"])
    desired_create.add_argument("target_value")
    desired_create.add_argument("--document", required=True, help="JSON object or @file.json")
    desired_create.add_argument("--description")
    aus.add_parser("desired-list")
    desired_update = aus.add_parser("desired-update")
    desired_update.add_argument("id", type=int)
    desired_update.add_argument("--document", help="JSON object or @file.json")
    desired_update.add_argument("--description")
    desired_update.add_argument("--target-kind", choices=["device", "group", "tag"])
    desired_update.add_argument("--target-value")
    for name in ("desired-show", "desired-publish", "desired-plan", "desired-evaluate"):
        parser = aus.add_parser(name)
        parser.add_argument("id", type=int)
    desired_clone = aus.add_parser("desired-clone")
    desired_clone.add_argument("id", type=int)
    desired_clone.add_argument("--name")
    desired_runs = aus.add_parser("desired-runs")
    desired_runs.add_argument("id", type=int, nargs="?")
    desired_runs.add_argument("--limit", type=int, default=100)
    desired_apply = aus.add_parser("desired-apply")
    desired_apply.add_argument("id", type=int)
    desired_apply.add_argument("--approved", action="store_true")
    desired_apply.add_argument("--no-rollback", action="store_true")

    campaign_create = aus.add_parser("campaign-create")
    campaign_create.add_argument("name")
    campaign_create.add_argument("desired_state_id", type=int)
    campaign_create.add_argument("--wave-size", type=int, default=1)
    campaign_create.add_argument("--canary-size", type=int, default=0)
    campaign_create.add_argument("--max-failures", type=int, default=0)
    campaign_create.add_argument("--rollback-on-failure", action="store_true")
    aus.add_parser("campaign-list")
    campaign_show = aus.add_parser("campaign-show")
    campaign_show.add_argument("id", type=int)
    for name in ("campaign-start", "campaign-pause", "campaign-resume", "campaign-abort"):
        parser = aus.add_parser(name)
        parser.add_argument("id", type=int)
    campaign_retry = aus.add_parser("campaign-retry")
    campaign_retry.add_argument("id", type=int)
    campaign_retry.add_argument("--wave", type=int)
    campaign_wave = aus.add_parser("campaign-wave")
    campaign_wave.add_argument("id", type=int)
    campaign_wave.add_argument("--approved", action="store_true")

    aus.add_parser("ha-status")
    ha_nodes = aus.add_parser("ha-nodes")
    ha_nodes.add_argument("--stale-seconds", type=int, default=86_400)
    ha_drain = aus.add_parser("ha-drain")
    ha_drain.add_argument("--reason", required=True)
    ha_drain.add_argument("--final", action="store_true")
    ha_drain.add_argument("--node-id")
    ha_activate = aus.add_parser("ha-activate")
    ha_activate.add_argument("--node-id")
    ha_record = aus.add_parser("ha-drill-record")
    ha_record.add_argument(
        "kind", choices=["NODE_FAILOVER", "DATABASE_RESTORE", "REBOOT_RECOVERY", "BACKUP_VERIFY"]
    )
    ha_record.add_argument("state", choices=["STARTED", "PASSED", "FAILED", "NOT_RUN"])
    ha_record.add_argument("--detail", help="JSON object or @file.json")
    ha_record.add_argument("--verification-ref")
    ha_complete = aus.add_parser("ha-drill-complete")
    ha_complete.add_argument("id", type=int)
    ha_complete.add_argument("state", choices=["PASSED", "FAILED", "NOT_RUN"])
    ha_complete.add_argument("--detail", help="JSON object or @file.json")
    ha_complete.add_argument("--verification-ref")
    ha_drills = aus.add_parser("ha-drills")
    ha_drills.add_argument("--limit", type=int, default=100)
    auto.set_defaults(func=cmd_automation)

    st = sub.add_parser("storage", help="PH-2 core database and distributed coordination")
    sts = st.add_subparsers(dest="action", required=True)
    ss = sts.add_parser("status"); ss.add_argument("--node-max-age", type=int, default=300)
    sl = sts.add_parser("tasks"); sl.add_argument("--queue"); sl.add_argument("--limit", type=int, default=100)
    se = sts.add_parser("enqueue"); se.add_argument("kind"); se.add_argument("--queue", default="default"); se.add_argument("--payload", default="{}")
    sc = sts.add_parser("claim"); sc.add_argument("--queue", default="default"); sc.add_argument("--worker", required=True); sc.add_argument("--lease-seconds", type=int, default=60)
    sf = sts.add_parser("finish"); sf.add_argument("id", type=int); sf.add_argument("--worker", required=True); sf.add_argument("--failed", action="store_true"); sf.add_argument("--result", default=""); sf.add_argument("--error", default="")
    sm = sts.add_parser("migrate-sqlite"); sm.add_argument("--source", help="SQLite inventory.db to copy; default current home/inventory.db")
    sb = sts.add_parser("backup-postgres", help="create an atomic checksummed pg_dump of the configured PostgreSQL core")
    sb.add_argument("--output", required=True); sb.add_argument("--timeout", type=int, default=600); sb.add_argument("--overwrite", action="store_true")
    sr = sts.add_parser("restore-postgres", help="restore a core pg_dump into an explicitly separate drill database")
    sr.add_argument("--input", required=True); sr.add_argument("--target-dbname", required=True)
    sr.add_argument("--sha256", help="expected SHA-256; otherwise require <backup>.sha256")
    sr.add_argument("--confirm", required=True, help="must be RESTORE_DATABASE")
    sr.add_argument("--timeout", type=int, default=900)
    st.set_defaults(func=cmd_storage)

    ql = sub.add_parser("qualify", help="Q-1 production runtime dependency/readiness preflight")
    ql.set_defaults(func=cmd_qualify)

    at = sub.add_parser("api-token", help="manage scoped read-only API bearer tokens")
    ats = at.add_subparsers(dest="action", required=True)
    atc = ats.add_parser("create"); atc.add_argument("name")
    atc.add_argument("--scope", action="append", required=True, choices=sorted(VALID_SCOPES))
    atc.add_argument("--role", default="viewer", choices=["viewer","operator","approver","admin"])
    ats.add_parser("list")
    atr = ats.add_parser("revoke"); atr.add_argument("id", type=int)
    at.set_defaults(func=cmd_api_token)

    au = sub.add_parser("audit"); au.add_argument("--limit", type=int, default=100)
    au.set_defaults(func=cmd_audit)

    tr = sub.add_parser("trace", help="bounded metadata-only protocol trace capture")
    trs = tr.add_subparsers(dest="action", required=True)
    trst = trs.add_parser("start")
    trst.add_argument("device")
    trst.add_argument("--protocol", required=True, choices=["cli_ssh","snmp","netconf","restconf","gnmi"])
    trst.add_argument("--incident")
    trst.add_argument("--ttl", type=int, default=900)
    trst.add_argument("--max-events", type=int, default=500)
    trst.add_argument("--max-bytes", type=int, default=1048576)
    trst.add_argument("--reason")
    trls = trs.add_parser("list")
    trls.add_argument("--device"); trls.add_argument("--incident")
    trls.add_argument("--status", choices=["ACTIVE","STOPPED","EXPIRED","LIMIT_REACHED"])
    trls.add_argument("--limit", type=int, default=200)
    trsh = trs.add_parser("show"); trsh.add_argument("ref")
    trev = trs.add_parser("events"); trev.add_argument("ref"); trev.add_argument("--limit", type=int, default=1000)
    trsp = trs.add_parser("stop"); trsp.add_argument("ref")
    tr.set_defaults(func=cmd_trace)

    inc = sub.add_parser("incident", help="manage diagnostic incidents")
    incs = inc.add_subparsers(dest="action", required=True)
    incc = incs.add_parser("create")
    incc.add_argument("--title", required=True)
    incc.add_argument("--description")
    incc.add_argument("--severity", default="MEDIUM", choices=["LOW","MEDIUM","HIGH","CRITICAL"])
    incc.add_argument("--tag", action="append")
    incl = incs.add_parser("list")
    incl.add_argument("--status", choices=["OPEN","INVESTIGATING","RESOLVED","CLOSED"])
    incl.add_argument("--severity", choices=["LOW","MEDIUM","HIGH","CRITICAL"])
    incl.add_argument("--limit", type=int, default=100)
    incshow = incs.add_parser("show"); incshow.add_argument("ref")
    incu = incs.add_parser("update"); incu.add_argument("ref")
    incu.add_argument("--title"); incu.add_argument("--description")
    incu.add_argument("--severity", choices=["LOW","MEDIUM","HIGH","CRITICAL"]); incu.add_argument("--tag", action="append")
    incst = incs.add_parser("status"); incst.add_argument("ref")
    incst.add_argument("status", choices=["OPEN","INVESTIGATING","RESOLVED","CLOSED"]); incst.add_argument("--note")
    inclb = incs.add_parser("link-bundle"); inclb.add_argument("ref"); inclb.add_argument("bundle")
    inculb = incs.add_parser("unlink-bundle"); inculb.add_argument("ref"); inculb.add_argument("bundle")
    ince = incs.add_parser("link-evidence")
    ince.add_argument("ref"); ince.add_argument("type", choices=["audit","syslog","collection","compliance","protocol_trace"])
    ince.add_argument("source_id"); ince.add_argument("--note")
    incd = incs.add_parser("link-drift")
    incd.add_argument("ref"); incd.add_argument("device"); incd.add_argument("--note")
    incue = incs.add_parser("unlink-evidence")
    incue.add_argument("ref"); incue.add_argument("link_id", type=int)
    incev = incs.add_parser("evidence"); incev.add_argument("ref")
    inctl = incs.add_parser("timeline"); inctl.add_argument("ref"); inctl.add_argument("--limit", type=int, default=500)
    incex = incs.add_parser("export-case", help="build a bounded support-case archive")
    incex.add_argument("ref")
    incex.add_argument("--bundle", action="append", help="linked diagnostic bundle to embed; repeatable")
    incex.add_argument("--reason")
    incex.add_argument("--require-signature", action="store_true",
                       help="fail closed unless an external Ed25519 signing key is configured")
    inclx = incs.add_parser("exports", help="list support-case exports for an incident")
    inclx.add_argument("ref"); inclx.add_argument("--limit", type=int, default=100)
    incvx = incs.add_parser("verify-export", help="verify a signed support-case export")
    incvx.add_argument("ref"); incvx.add_argument("export_key")
    incvx.add_argument("--trusted-fingerprint", action="append",
                       help="independent SHA-256 SPKI trust pin; repeatable")
    inc.set_defaults(func=cmd_incident)

    dbg = sub.add_parser("debug", help="create redacted diagnostic support bundle")
    dbgs = dbg.add_subparsers(dest="action", required=True)
    dbc = dbgs.add_parser("collect")
    dbc.add_argument("--output", help="output .tar.gz path")
    dbc.add_argument("--require-signature", action="store_true")
    dbd = dbgs.add_parser("device")
    dbd.add_argument("name")
    dbd.add_argument("--output", help="output .tar.gz path")
    dbd.add_argument("--require-signature", action="store_true")
    dbgs.add_parser("list")
    dbgc = dbgs.add_parser("cleanup")
    dbgc.add_argument("--keep", type=int, default=10)
    dbgm = dbgs.add_parser("maintenance", help="run configured D.5 retention maintenance once")
    dbgm.add_argument("--actor", default="cli")
    dbgv = dbgs.add_parser("verify", help="verify signed diagnostic bundle")
    dbgv.add_argument("name")
    dbgv.add_argument("--trusted-fingerprint", action="append",
                      help="independent SHA-256 SPKI trust pin; repeatable")
    dbgs.add_parser("signing-status", help="show external evidence signer readiness")
    dbg.set_defaults(func=cmd_debug)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.cmd == "storage" and args.action == "restore-postgres":
        _cmd_restore_postgres_offline(args)
        return
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
