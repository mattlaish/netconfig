"""
transport.py -- SSH transport for network devices, pure stdlib.

Python stdlib has no SSH client. Rather than reimplement the SSH transport
protocol in Python (a large, security-critical undertaking) or take a third-party
dependency (paramiko/netmiko), this drives the system OpenSSH client as a
subprocess behind a stdlib pty and interacts with it expect-style.

Why a pty and not plain pipes: ssh reads passwords and passphrases from the
controlling terminal, not stdin. Without a tty it will not prompt and auth fails.
So we allocate a local pty, hand ssh the slave end, and read/write the master end.

Everything here is byte-oriented. Device banners, pagers, and prompts are matched
as bytes so partial UTF-8 reads across the pty never corrupt matching; the caller
decodes the final transcript.

Real-world gotchas handled / exposed:
  * Legacy algorithms: old switches/routers negotiate KEX/host-key/cipher suites
    that modern OpenSSH disables by default. `legacy=True` (or explicit algo
    strings) re-enables group14-sha1 / ssh-rsa / cbc so you can actually reach
    that 2011 IOS box. This is a knowing security tradeoff, opt-in per device.
  * Host keys: a per-tool known_hosts file with accept-new by default; a CHANGED
    host key still fails hard (that's a signal worth surfacing, not suppressing).
  * Pager: the driver disables paging first; as a backstop the engine can answer
    a --More-- prompt with space.
"""

import os
import pty
import re
import select
import shutil
import signal
import time


# Resolve the ssh binary to an absolute path at import so a hijacked $PATH can't
# substitute a malicious `ssh` for this privileged tool. Overridable via
# $NETCONFIG_SSH for non-standard locations.
_SSH_BIN = os.environ.get("NETCONFIG_SSH") or shutil.which("ssh") or "ssh"


class TransportError(Exception):
    pass


class AuthError(TransportError):
    pass


# Prompt / interaction patterns (bytes).
_RE_PASSWORD = re.compile(rb"(?i)password:\s*$")
_RE_PASSPHRASE = re.compile(rb"(?i)enter passphrase for key")
_RE_HOSTKEY_CONFIRM = re.compile(rb"(?i)are you sure you want to continue connecting")
_RE_PERM_DENIED = re.compile(rb"(?i)(permission denied|authentication failed)")
_RE_CONN_FAIL = re.compile(
    rb"(?i)(connection refused|connection timed out|no route to host|"
    rb"could not resolve|host key verification failed|remote host identification has changed)"
)
_RE_MORE = re.compile(rb"--\s*more\s*--|<--- more --->", re.I)
# A device CLI prompt: last line ending in > or # (optionally after a mode paren).
_RE_PROMPT = re.compile(rb"[\r\n]([^\r\n]{1,80}?[>#])\s*$")

_DEFAULT_LEGACY_KEX = "diffie-hellman-group14-sha1,diffie-hellman-group1-sha1,diffie-hellman-group-exchange-sha1"
_DEFAULT_LEGACY_HOSTKEY = "ssh-rsa,ssh-dss"
_DEFAULT_LEGACY_CIPHERS = "aes256-cbc,aes192-cbc,aes128-cbc,3des-cbc"


class SSHTransport:
    def __init__(self, host, username, *, port=22, password=None,
                 key_path=None, key_passphrase=None,
                 connect_timeout=15, command_timeout=60,
                 known_hosts=None, host_key_policy="accept-new",
                 legacy=False, kex=None, host_key_algos=None, ciphers=None,
                 extra_ssh_options=None):
        self.host = host
        self.username = username
        self.port = port
        self.password = password
        self.key_path = key_path
        self.key_passphrase = key_passphrase
        self.connect_timeout = connect_timeout
        self.command_timeout = command_timeout
        self.known_hosts = known_hosts
        self.host_key_policy = host_key_policy  # accept-new | yes | no
        self.legacy = legacy
        self.kex = kex
        self.host_key_algos = host_key_algos
        self.ciphers = ciphers
        self.extra_ssh_options = extra_ssh_options or []

        self._pid = None
        self._fd = None
        self._buf = b""
        self.prompt = None          # bytes, the discovered base prompt line
        self.transcript = bytearray()

    # ---- process management ---------------------------------------------
    def _build_argv(self):
        argv = ["ssh", "-tt",
                "-o", f"ConnectTimeout={self.connect_timeout}",
                "-o", "NumberOfPasswordPrompts=1",
                "-o", f"StrictHostKeyChecking={self.host_key_policy}",
                "-o", "GlobalKnownHostsFile=/dev/null"]
        if self.known_hosts:
            argv += ["-o", f"UserKnownHostsFile={self.known_hosts}"]
        if self.key_path:
            argv += ["-i", self.key_path,
                     "-o", "PreferredAuthentications=publickey,keyboard-interactive,password"]
        elif self.password is not None:
            # Force password path; don't let it silently try (and burn) agent keys.
            argv += ["-o", "PubkeyAuthentication=no",
                     "-o", "PreferredAuthentications=password,keyboard-interactive"]
        kex = self.kex or (_DEFAULT_LEGACY_KEX if self.legacy else None)
        hka = self.host_key_algos or (_DEFAULT_LEGACY_HOSTKEY if self.legacy else None)
        ciph = self.ciphers or (_DEFAULT_LEGACY_CIPHERS if self.legacy else None)
        if kex:
            argv += ["-o", f"KexAlgorithms=+{kex}"]
        if hka:
            argv += ["-o", f"HostKeyAlgorithms=+{hka}",
                     "-o", f"PubkeyAcceptedAlgorithms=+{hka}"]
        if ciph:
            argv += ["-o", f"Ciphers=+{ciph}"]
        for opt in self.extra_ssh_options:
            argv += ["-o", opt]
        argv += ["-p", str(self.port), f"{self.username}@{self.host}"]
        return argv

    def _spawn(self):
        argv = self._build_argv()
        pid, fd = pty.fork()
        if pid == 0:  # child
            try:
                # exec the resolved absolute path when available (no PATH search);
                # keep argv[0]="ssh" for a clean process title.
                if os.path.isabs(_SSH_BIN):
                    os.execv(_SSH_BIN, argv)
                else:
                    os.execvp(_SSH_BIN, argv)
            except Exception:
                os._exit(127)
        self._pid = pid
        self._fd = fd

    # ---- low-level expect ------------------------------------------------
    def _read_until(self, patterns, timeout, feed_transcript=True):
        """patterns: list of compiled bytes-regex. Returns (index, match, consumed)."""
        deadline = time.monotonic() + timeout
        while True:
            for i, pat in enumerate(patterns):
                m = pat.search(self._buf)
                if m:
                    consumed = self._buf[:m.end()]
                    self._buf = self._buf[m.end():]
                    return i, m, consumed
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TransportError(
                    f"timeout after {timeout}s; last data: "
                    f"{self._buf[-200:]!r}")
            try:
                r, _, _ = select.select([self._fd], [], [], min(remaining, 0.5))
            except (OSError, ValueError):
                raise TransportError("transport closed")
            if self._fd in r:
                try:
                    data = os.read(self._fd, 65536)
                except OSError:
                    data = b""
                if not data:
                    raise EOFError("ssh process ended: "
                                   + repr(bytes(self._buf[-200:])))
                self._buf += data
                if feed_transcript:
                    self.transcript += data

    def _write(self, data, echo_to_transcript=False):
        if isinstance(data, str):
            data = data.encode()
        os.write(self._fd, data)
        if echo_to_transcript:
            self.transcript += data

    # ---- connect ---------------------------------------------------------
    def connect(self):
        self._spawn()
        # Auth phase: we may see a host-key confirm, passphrase, password, an
        # error, or land straight at a device prompt (key auth, no passphrase).
        patterns = [_RE_HOSTKEY_CONFIRM, _RE_PASSPHRASE, _RE_PASSWORD,
                    _RE_PERM_DENIED, _RE_CONN_FAIL, _RE_PROMPT]
        password_sent = False
        for _ in range(8):  # bounded interaction loop
            try:
                idx, m, _ = self._read_until(patterns, self.connect_timeout)
            except EOFError as e:
                raise AuthError(f"connection to {self.host} closed during auth: {e}")
            if idx == 0:  # host key confirm (only if policy=yes)
                self._write("yes\n")
            elif idx == 1:  # key passphrase
                if not self.key_passphrase:
                    raise AuthError("key passphrase required but not provided")
                self._write(self.key_passphrase + "\n")
            elif idx == 2:  # password
                if password_sent or self.password is None:
                    raise AuthError("password requested but not provided (or rejected)")
                self._write(self.password + "\n")
                password_sent = True
            elif idx == 3:  # permission denied
                raise AuthError(f"authentication rejected by {self.host}")
            elif idx == 4:  # connection-level failure
                raise TransportError(f"connection to {self.host} failed: "
                                     f"{m.group(0).decode(errors='replace')}")
            elif idx == 5:  # device prompt -> authenticated
                self.prompt = m.group(1).strip()
                return
        raise AuthError("exceeded interaction steps during auth")

    def discover_prompt(self):
        """Nudge the CLI and capture the base prompt if not already known."""
        if self.prompt:
            return self.prompt
        self._write("\n")
        _, m, _ = self._read_until([_RE_PROMPT], self.command_timeout)
        self.prompt = m.group(1).strip()
        return self.prompt

    # ---- public primitives for drivers ----------------------------------
    def send_line(self, text):
        self._write(text + "\n", echo_to_transcript=True)

    def expect(self, patterns, timeout=None):
        """Wait for any of `patterns` (bytes regex or compiled). Returns
        (index, match, consumed_bytes)."""
        timeout = timeout or self.command_timeout
        compiled = [p if hasattr(p, "search") else re.compile(p) for p in patterns]
        return self._read_until(compiled, timeout)

    # ---- command execution ----------------------------------------------
    def execute(self, command, timeout=None, expect=None, handle_pager=True):
        """Send a command, return decoded output with echo + trailing prompt
        stripped. `expect` overrides the prompt regex (bytes pattern)."""
        timeout = timeout or self.command_timeout
        self._write(command + "\n", echo_to_transcript=True)
        prompt_re = re.compile(re.escape(self.prompt) + rb"\s*$") if (self.prompt and expect is None) \
            else (expect or _RE_PROMPT)
        collected = bytearray()
        while True:
            patterns = [prompt_re, _RE_MORE] if handle_pager else [prompt_re]
            idx, m, consumed = self._read_until(patterns, timeout)
            collected += consumed
            if idx == 0:
                break
            # pager backstop: driver should have disabled paging already, but if a
            # --More-- slips through, advance with space. _clean() strips the marker.
            self._write(" ")
        return self._clean(bytes(collected), command)

    @staticmethod
    def _clean(raw, command):
        text = raw.decode("utf-8", "replace")
        # Normalise line endings. The remote pty's ONLCR can turn a device's
        # CRLF into CR CR LF, so collapse any run of CR (+ optional LF) to one \n.
        text = re.sub(r"\r+\n?", "\n", text)
        lines = text.split("\n")
        # drop leading echo of the command
        if lines and command.strip() and command.strip() in lines[0]:
            lines = lines[1:]
        # drop trailing prompt line(s)
        while lines and re.search(r"[>#]\s*$", lines[-1]) and len(lines[-1]) < 90:
            lines.pop()
        # strip any residual pager artifacts
        cleaned = "\n".join(l for l in lines if not _RE_MORE.search(l.encode()))
        return cleaned.strip("\n")

    # ---- teardown --------------------------------------------------------
    def close(self):
        if self._fd is not None:
            try:
                self._write("exit\n")
            except OSError:
                pass
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        if self._pid is not None:
            for sig in (0, signal.SIGTERM, signal.SIGKILL):
                try:
                    if sig:
                        os.kill(self._pid, sig)
                    pid, _ = os.waitpid(self._pid, os.WNOHANG)
                    if pid:
                        break
                except OSError:
                    break
                time.sleep(0.2)
            self._pid = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
