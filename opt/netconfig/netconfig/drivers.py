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

_RE_PW = rb"(?i)password:\s*$"
_RE_DENIED = rb"(?i)(% access denied|% authentication failed|bad secret|denied)"


_RE_CFG_ERROR = re.compile(
    r"%\s*(invalid|incomplete|ambiguous|unrecognized|unknown command|"
    r"error|not permitted|authorization failed)", re.I)

# Config mode changes the prompt (e.g. R1# -> R1(config)# -> R1(config-if)#), so
# pushing config can't rely on the base prompt the transport discovered at login.
# This matches any trailing device prompt line ending in > or #.
_ANY_PROMPT = re.compile(rb"[\r\n][^\r\n]{1,120}?[>#]\s*$")


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

    def initialize(self, tp, enable_password=None):
        """Post-login setup: enter enable (if needed) then disable paging."""
        if self.needs_enable and enable_password is not None:
            self.enter_enable(tp, enable_password)
        for cmd in self.disable_paging:
            tp.execute(cmd)

    def enter_enable(self, tp, enable_password):
        tp.send_line(self.enable_command)
        idx, m, _ = tp.expect([_RE_PW, _RE_DENIED, re.escape(tp.prompt or b"")], timeout=tp.command_timeout)
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

    def apply_lines(self, tp, lines, save=False):
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


class DriverError(Exception):
    pass


# ---- concrete platforms -------------------------------------------------
class CiscoIOS(Driver):
    name = "cisco_ios"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = True
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"


class CiscoNXOS(Driver):
    name = "cisco_nxos"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = False  # NX-OS role-based; usually no enable step
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "copy running-config startup-config"


class CiscoASA(Driver):
    name = "cisco_asa"
    disable_paging = ["terminal pager 0"]
    config_command = "show running-config"
    needs_enable = True
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"


class AristaEOS(Driver):
    name = "arista_eos"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = True
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = "write memory"


class JuniperJunOS(Driver):
    name = "juniper_junos"
    disable_paging = ["set cli screen-length 0", "set cli screen-width 0"]
    config_command = "show configuration | display set"
    needs_enable = False  # operational mode can already read config
    # JunOS commits rather than saving; commit-and-quit leaves the CLI clean.
    config_enter = ["configure"]
    config_exit = ["commit and-quit"]
    save_command = None


class HPComware(Driver):
    name = "hp_comware"
    disable_paging = ["screen-length disable"]
    config_command = "display current-configuration"
    needs_enable = False
    enable_command = "super"
    config_enter = ["system-view"]
    config_exit = ["return"]
    save_command = None   # `save` is interactive on Comware; leave to operator


class MikroTik(Driver):
    name = "mikrotik_routeros"
    disable_paging = []  # RouterOS export doesn't page the same way
    config_command = "/export"
    needs_enable = False
    # RouterOS has no config mode; commands apply immediately at top level.
    config_enter = []
    config_exit = []
    save_command = None


class Generic(Driver):
    name = "generic"
    disable_paging = ["terminal length 0"]
    config_command = "show running-config"
    needs_enable = False
    config_enter = ["configure terminal"]
    config_exit = ["end"]
    save_command = None


_REGISTRY = {d.name: d for d in [
    CiscoIOS, CiscoNXOS, CiscoASA, AristaEOS, JuniperJunOS, HPComware, MikroTik, Generic,
]}


def get_driver(platform):
    cls = _REGISTRY.get((platform or "generic").lower())
    if cls is None:
        raise DriverError(f"unknown platform {platform!r}; known: {sorted(_REGISTRY)}")
    return cls()


def platforms():
    return sorted(_REGISTRY)
