"""
drivers.py -- Per-platform CLI behaviour.

A driver knows the vendor-specific incantations: how to turn off the pager, how
to get into privileged/enable mode, and which command dumps the config. The
transport is dumb (it moves bytes and finds prompts); the driver is the brains.

Adding a platform = add a Driver subclass and register it. Kept deliberately
small and declarative so it's obvious what each box needs.

The prompt-mode question ('>' user vs '#' privileged) is handled by re-discovering
the prompt after `enable`, rather than assuming, because banners and hostnames
vary wildly and guessing is how these tools break in the field.
"""

import re

from . import configmodel

_RE_PW = rb"(?i)password:\s*$"
_RE_DENIED = rb"(?i)(% access denied|% authentication failed|bad secret|denied)"


_RE_CFG_ERROR = re.compile(
    r"%\s*(invalid|incomplete|ambiguous|unrecognized|unknown command|"
    r"error|not permitted|authorization failed)", re.I)

# Config mode changes the prompt (e.g. R1# -> R1(config)# -> R1(config-if)#), so
# pushing config can't rely on the base prompt the transport discovered at login.
# This matches any trailing device prompt line ending in > or #.
_ANY_PROMPT = re.compile(rb"[\r\n][^\r\n]{1,120}?[>#]\s*$")

_RE_CONFIG_FETCH_ERROR = re.compile(
    r"(?im)^\s*(?:"
    r"%\s*(?:invalid input|incomplete command|ambiguous command|unrecognized command|unknown command|error|not permitted|authorization failed).*|"
    r"unknown action(?:\s+\d+)?\s*|"
    r"command fail(?:\.\s*return code\s*-?\d+)?\s*|"
    r"command parse error.*|invalid command.*|unrecognized command.*|syntax error.*"
    r")\s*$"
)


def validate_config_output(raw, *, command="", platform="generic"):
    """Reject obvious CLI error output before it can become config truth."""
    text = str(raw or "").replace("\x00", "")
    if not text.strip():
        raise DriverError(
            f"configuration collection returned empty output for {command or 'configured command'}")
    match = _RE_CONFIG_FETCH_ERROR.search(text)
    if match:
        snippet = " ".join(match.group(0).split())[:180]
        raise DriverError(
            f"configuration collection command failed on {platform}: {snippet}")
    return text


class Driver:
    name = "generic"
    disable_paging = []           # commands to send to stop the pager
    config_command = None         # command that emits the running config
    needs_enable = False
    enable_command = "enable"
    # config-push behaviour (None where a platform has no distinct config mode)
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = None           # persist running->startup, if the platform needs it
    negation_verb = "no"
    rollback_guard = None         # cisco_reload | junos_commit_confirmed | None
    # Optional read-only L3 evidence commands. Empty means unsupported rather
    # than guessed: topology collection must never send an arbitrary vendor CLI.
    l3_interface_command = None
    l3_route_command = None

    def initialize(self, tp, enable_password=None):
        """Post-login setup: enter enable (if needed) then disable paging."""
        if self.needs_enable and enable_password is not None:
            self.enter_enable(tp, enable_password)
        for cmd in self.disable_paging:
            tp.execute(cmd)

    def enter_enable(self, tp, enable_password):
        tp.send_line(self.enable_command)
        idx, _, _ = tp.expect([_RE_PW, _RE_DENIED, re.escape(tp.prompt or b"")], timeout=tp.command_timeout)
        if idx == 0:
            tp.send_line(enable_password)
            # re-discover prompt (should now end in '#')
            tp.prompt = None
            tp.discover_prompt()
            if not tp.prompt.rstrip().endswith(b"#"):
                # could be denied silently; check
                raise DriverError("enable did not reach privileged mode")
        elif idx == 1:
            raise DriverError("enable password rejected")
        # idx == 2: already privileged / no password needed

    def fetch_config(self, tp):
        if not self.config_command:
            raise DriverError(f"driver {self.name} has no config_command")
        return tp.execute(self.config_command)

    def run(self, tp, command):
        return tp.execute(command)

    def validate_config_output(self, raw, command=""):
        return validate_config_output(raw, command=command, platform=self.name)

    def apply_lines(self, tp, lines, save=False, remediation=False):
        """Push config commands. Enters config mode (if the platform has one),
        sends each line, checks each response for an error marker, exits, and
        optionally saves. Returns (output_text, errors[list of (line, snippet)]).

        The caller decides whether to save; nothing here writes to startup-config
        unless asked, so a bad push doesn't silently persist across reload."""
        out = []
        errors = []
        for c in self.config_enter:
            out.append(tp.execute(c, expect=_ANY_PROMPT))
        for line in lines:
            resp = tp.execute(line, expect=_ANY_PROMPT)
            out.append(resp)
            if _RE_CFG_ERROR.search(resp):
                errors.append((line, resp.strip()[:200]))
        for c in self.config_exit:
            tp.execute(c, expect=_ANY_PROMPT)
        # after config_exit we're back at the base prompt; refresh it so any
        # follow-on exec command (e.g. save) matches correctly
        tp.prompt = None
        tp.discover_prompt()
        if save and not errors:
            out.append(self.save(tp))
        return "\n".join(o for o in out if o), errors

    def save(self, tp):
        if not self.save_command:
            return ""
        return tp.execute(self.save_command)

    def remediation_plan(self, baseline, current):
        if self.name == "juniper_junos":
            return configmodel.plan_junos_set(baseline, current)
        return configmodel.plan_indented(
            baseline, current, negation=self.negation_verb, exit_command="exit")

    def begin_rollback_guard(self, tp):
        """Arm an automatic rollback before remediation. Fail closed when the
        platform has no implemented/testable timed rollback primitive."""
        if self.rollback_guard == "junos_commit_confirmed":
            # JunOS arms the timer when the candidate is committed in apply_lines.
            return {"kind": self.rollback_guard, "armed": False}
        if self.rollback_guard == "cisco_reload":
            tp.send_line("reload in 5")
            patterns = [rb"(?i)confirm", rb"(?i)save.*\[yes/no\]", _ANY_PROMPT]
            for _ in range(3):
                idx, _m, _raw = tp.expect(patterns, timeout=tp.command_timeout)
                if idx == 0:
                    tp.send_line("")
                    return {"kind": self.rollback_guard, "armed": True}
                if idx == 1:
                    tp.send_line("no")
                    continue
                if idx == 2:
                    # Some platforms accept the command without an extra confirm.
                    return {"kind": self.rollback_guard, "armed": True}
            raise DriverError("could not confirm automatic reload rollback guard")
        raise DriverError(
            f"safe remediation is disabled for {self.name}: no automatic rollback guard")

    def commit_rollback_guard(self, tp, guard, save=False):
        kind = (guard or {}).get("kind")
        if kind == "cisco_reload":
            # Persist only after post-change verification, then cancel the timer.
            if save:
                self.save(tp)
            tp.execute("reload cancel")
            return
        if kind == "junos_commit_confirmed":
            tp.execute("configure", expect=_ANY_PROMPT)
            tp.execute("commit", expect=_ANY_PROMPT)
            tp.execute("exit", expect=_ANY_PROMPT)
            tp.prompt = None
            tp.discover_prompt()
            return

    def leave_rollback_guard_armed(self, tp, guard):
        # Intentionally do not cancel. Timed device rollback is the recovery path.
        return None


class DriverError(Exception):
    pass


# ---- concrete platforms -------------------------------------------------
class CiscoIOS(Driver):
    name = "cisco_ios"
    l3_interface_command = "show ip interface brief"
    l3_route_command = "show ip route"
    rollback_guard = "cisco_reload"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = True
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"


class CiscoNXOS(Driver):
    name = "cisco_nxos"
    l3_interface_command = "show ip interface brief vrf all"
    l3_route_command = "show ip route vrf all"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = False  # NX-OS role-based; usually no enable step
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "copy running-config startup-config"


class CiscoASA(Driver):
    name = "cisco_asa"
    l3_interface_command = "show interface ip brief"
    l3_route_command = "show route"
    rollback_guard = "cisco_reload"
    disable_paging = ["terminal pager 0"]
    config_command = "show running-config"
    needs_enable = True
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"


class AristaEOS(Driver):
    name = "arista_eos"
    l3_interface_command = "show ip interface brief"
    l3_route_command = "show ip route vrf all"
    rollback_guard = "cisco_reload"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = True
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"


class JuniperJunOS(Driver):
    name = "juniper_junos"
    l3_interface_command = "show interfaces terse"
    l3_route_command = "show route terse"
    rollback_guard = "junos_commit_confirmed"
    disable_paging = ["set cli screen-length 0", "set cli screen-width 0"]
    config_command = "show configuration | display set"
    needs_enable = False  # operational mode can already read config
    # JunOS commits rather than saving; commit-and-quit leaves the CLI clean.
    config_enter = ["configure"]
    config_exit = ["commit and-quit"]
    save_command = None

    def apply_lines(self, tp, lines, save=False, remediation=False):
        if not remediation:
            return super().apply_lines(tp, lines, save=save, remediation=False)
        out = [tp.execute("configure", expect=_ANY_PROMPT)]
        errors = []
        for line in lines:
            resp = tp.execute(line, expect=_ANY_PROMPT)
            out.append(resp)
            if _RE_CFG_ERROR.search(resp):
                errors.append((line, resp.strip()[:200]))
        if errors:
            tp.execute("rollback 0", expect=_ANY_PROMPT)
            tp.execute("exit", expect=_ANY_PROMPT)
        else:
            resp = tp.execute("commit confirmed 5", expect=_ANY_PROMPT)
            out.append(resp)
            if _RE_CFG_ERROR.search(resp):
                errors.append(("commit confirmed 5", resp.strip()[:200]))
            tp.execute("exit", expect=_ANY_PROMPT)
        tp.prompt = None
        tp.discover_prompt()
        return "\n".join(o for o in out if o), errors


class HPComware(Driver):
    name = "hp_comware"
    l3_interface_command = "display ip interface brief"
    l3_route_command = "display ip routing-table"
    negation_verb = "undo"
    disable_paging = ["screen-length disable"]
    config_command = "display current-configuration"
    needs_enable = False
    enable_command = "super"
    config_enter = ["system-view"]
    config_exit = ["return"]
    save_command = None   # `save` is interactive on Comware; leave to operator


class FortiGateFortiOS(Driver):
    name = "fortigate_fortios"
    l3_interface_command = "get system interface"
    l3_route_command = "get router info routing-table all"
    # Do not change ``config system console set output`` merely to collect data:
    # that is device configuration state. Keep the collection path read-only.
    disable_paging = []
    config_command = "show full-configuration"
    needs_enable = False
    config_enter = []
    config_exit = []
    save_command = None


class MikroTik(Driver):
    name = "mikrotik_routeros"
    l3_interface_command = "/ip/address/print detail without-paging"
    l3_route_command = "/ip/route/print detail without-paging"
    disable_paging = []  # RouterOS export doesn't page the same way
    config_command = "/export"
    needs_enable = False
    # RouterOS has no config mode; commands apply immediately at top level.
    config_enter = []
    config_exit = []
    save_command = None


class ArubaAOSCX(Driver):
    name = "aruba_aoscx"
    disable_paging = ["no page"]
    config_command = "show running-config"
    needs_enable = False
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"
    l3_interface_command = "show ip interface brief"
    l3_route_command = "show ip route"


class Generic(Driver):
    name = "generic"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = False
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = None


_REGISTRY = {d.name: d for d in [
    CiscoIOS, CiscoNXOS, CiscoASA, AristaEOS, JuniperJunOS, HPComware, FortiGateFortiOS, MikroTik, ArubaAOSCX, Generic,
]}


def get_driver(platform):
    key = (platform or "generic").lower()
    key = {"fortigate": "fortigate_fortios", "fortios": "fortigate_fortios",
           "fortinet_fortigate": "fortigate_fortios"}.get(key, key)
    cls = _REGISTRY.get(key)
    if cls is None:
        raise DriverError(f"unknown platform {platform!r}; known: {sorted(_REGISTRY)}")
    return cls()


def platforms():
    return sorted(_REGISTRY)
