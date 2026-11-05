"""Per-device legacy SSH support without global or automatic downgrades."""
import re
import subprocess
from types import SimpleNamespace

import pytest

from netconfig import transport as tr
from test_web_ux import console as _console_fixture

console = _console_fixture
OFFER = (b"Unable to negotiate with 192.168.0.205 port 22: no matching key exchange method found. "
         b"Their offer: diffie-hellman-group-exchange-sha1,diffie-hellman-group14-sha1,diffie-hellman-group1-sha1\r\r\n")


@pytest.fixture(autouse=True)
def clear_capability_cache():
    tr._supported_ssh_algorithms.cache_clear()
    yield
    tr._supported_ssh_algorithms.cache_clear()


def _local_queries(monkeypatch, answers):
    calls = []
    def query(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="\n".join(answers.get(argv[-1], [])))
    monkeypatch.setattr(tr.subprocess, "run", query)
    return calls


def test_modern_connections_never_query_or_add_legacy_algorithms(monkeypatch):
    calls = _local_queries(monkeypatch, {})
    argv = tr.SSHTransport("192.0.2.205", "admin", known_hosts="pinned", host_key_policy="yes")._build_argv()
    assert calls == []
    assert not any(x.startswith(("KexAlgorithms=", "HostKeyAlgorithms=", "Ciphers=", "PubkeyAcceptedAlgorithms=")) for x in argv)
    assert "StrictHostKeyChecking=yes" in argv and "UserKnownHostsFile=pinned" in argv
    assert argv[-2:] == ["--", "admin@192.0.2.205"]


def test_legacy_filters_removed_algorithms_and_caches_local_queries(monkeypatch):
    calls = _local_queries(monkeypatch, {"kex": ["curve25519-sha256", "diffie-hellman-group14-sha1"],
                                        "key": ["ssh-rsa"], "cipher": ["aes128-cbc"]})
    tp = tr.SSHTransport("192.0.2.205", "admin", legacy=True, known_hosts="pinned", host_key_policy="yes")
    argv = tp._build_argv()
    assert "KexAlgorithms=+diffie-hellman-group14-sha1" in argv
    assert "HostKeyAlgorithms=+ssh-rsa" in argv and "PubkeyAcceptedAlgorithms=+ssh-rsa" in argv
    assert "Ciphers=+aes128-cbc" in argv
    assert "ssh-dss" not in " ".join(argv) and "3des-cbc" not in " ".join(argv)
    assert "StrictHostKeyChecking=yes" in argv and "UserKnownHostsFile=pinned" in argv
    tr.SSHTransport("192.0.2.206", "other", legacy=True)._build_argv()
    assert len(calls) == 3
    assert all(argv == [tr._SSH_BIN, "-Q", category] for (argv, _), category in zip(calls, ("kex", "key", "cipher"), strict=True))
    assert all(kwargs["timeout"] == 2 and not kwargs.get("shell") for _, kwargs in calls)
    # A previous legacy connection does not change later normal connections.
    modern = tr.SSHTransport("192.0.2.207", "admin")._build_argv()
    assert not any(x.startswith("KexAlgorithms=") for x in modern)


def test_no_legacy_algorithm_compiled_does_not_emit_invalid_empty_options(monkeypatch):
    _local_queries(monkeypatch, {})
    argv = tr.SSHTransport("192.0.2.205", "admin", legacy=True)._build_argv()
    assert not any(x.endswith("=+") for x in argv)
    assert not any(x.startswith(("KexAlgorithms=", "HostKeyAlgorithms=", "Ciphers=")) for x in argv)


def test_explicit_overrides_are_not_silently_filtered(monkeypatch):
    calls = _local_queries(monkeypatch, {})
    argv = tr.SSHTransport("192.0.2.205", "admin", legacy=True, kex="chosen-kex",
                           host_key_algos="chosen-key", ciphers="chosen-cipher")._build_argv()
    assert calls == []
    assert "KexAlgorithms=+chosen-kex" in argv and "HostKeyAlgorithms=+chosen-key" in argv
    assert "Ciphers=+chosen-cipher" in argv


@pytest.mark.parametrize("failure", ["exit", "timeout", "missing"])
def test_local_query_failure_is_bounded_and_clear(monkeypatch, failure):
    def failed(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("ssh", 2)
        if failure == "missing":
            raise FileNotFoundError("ssh")
        return SimpleNamespace(returncode=1, stdout="")
    monkeypatch.setattr(tr.subprocess, "run", failed)
    with pytest.raises(tr.TransportError, match="Could not check local SSH compatibility"):
        tr.SSHTransport("192.0.2.205", "admin", legacy=True)._build_argv()


def test_ssh_binary_replacement_invalidates_capability_cache(monkeypatch):
    stamp = [1]
    monkeypatch.setattr(tr.os, "stat", lambda path: SimpleNamespace(st_mtime_ns=stamp[0], st_size=20))
    calls = _local_queries(monkeypatch, {"kex": ["diffie-hellman-group14-sha1"]})
    tr._legacy_algorithms("kex", tr._DEFAULT_LEGACY_KEX)
    tr._legacy_algorithms("kex", tr._DEFAULT_LEGACY_KEX)
    assert len(calls) == 1
    stamp[0] = 2
    tr._legacy_algorithms("kex", tr._DEFAULT_LEGACY_KEX)
    assert len(calls) == 2


@pytest.mark.parametrize("via_eof", [True, False])
def test_reported_cisco_offer_enables_compatibility_without_password_retry(monkeypatch, via_eof):
    tp = tr.SSHTransport("192.168.0.205", "admin", legacy=False, password="secret")
    spawned, writes = [], []
    monkeypatch.setattr(tp, "_spawn", lambda: spawned.append(True))
    monkeypatch.setattr(tp, "_write", lambda data: writes.append(data))
    def read(*args, **kwargs):
        if via_eof:
            tp._buf = OFFER
            raise EOFError("old bytes repr")
        return 6, None, OFFER
    monkeypatch.setattr(tp, "_read_until", read)
    with pytest.raises(tr.TransportError) as caught:
        tp.connect()
    message = str(caught.value)
    assert "SSH key exchange method mismatch" in message and "secret" not in message
    assert "diffie-hellman-group14-sha1" in message
    assert "enable 'Older-device SSH compatibility'" in message
    assert len(spawned) == 1 and writes == []  # no automatic downgrade or auth retry


def test_legacy_negotiation_message_does_not_suggest_enabling_mode_again():
    message = tr._negotiation_message(OFFER, True)
    assert "already enabled" in message and "system policy" in message


@pytest.mark.parametrize("kind", ["host key type", "cipher", "MAC"])
def test_related_negotiation_types_are_recognized(kind):
    message = tr._negotiation_message(f"no matching {kind} found. Their offer: example-algo\r\n".encode(), False)
    assert "mismatch" in message and "Older-device SSH compatibility" in message


def test_normal_auth_failure_is_still_auth_failure(monkeypatch):
    tp = tr.SSHTransport("192.0.2.205", "admin")
    monkeypatch.setattr(tp, "_spawn", lambda: None)
    def read(*args, **kwargs):
        tp._buf = b"Connection closed by remote host"
        raise EOFError("closed")
    monkeypatch.setattr(tp, "_read_until", read)
    with pytest.raises(tr.AuthError, match="closed during auth"):
        tp.connect()


def test_checkbox_reaches_saved_device_and_explicit_test(console, monkeypatch):
    from netconfig import manager as manager_module
    calls = []
    class Transport:
        def __init__(self, host, username, **kwargs):
            calls.append(kwargs)
        def connect(self):
            pass
        def discover_prompt(self):
            return b"switch#"
        def close(self):
            pass
    monkeypatch.setattr(manager_module, "SSHTransport", Transport)
    form = {"csrf": "ux-csrf", "host": "192.0.2.205", "port": "22", "device_type": "network",
            "ssh_username": "admin", "ssh_password": "password", "legacy": "1", "cred_mode": "manual"}
    code, _, body = console.request("POST", "/device-test", form, token=console.session())
    assert code == 200 and '"ok": true' in body and calls[0]["legacy"] is True
    console.m.vault.create("test-master-password")
    console.m.unlock_vault("test-master-password")
    code, _, _ = console.request("POST", "/device-save", {**form, "name": "cisco", "platform": "generic", "enabled": "1"}, token=console.session())
    assert code == 303 and console.m.inv.get("cisco")["legacy"]
    code, _, page = console.request("GET", "/device-new?name=cisco", token=console.session())
    assert code == 200 and "Older-device SSH compatibility" in page
    checkbox = re.search(r'<input\b[^>]*\bname=legacy\b[^>]*>', page).group(0)
    assert re.search(r'\bchecked(?:\s|>|=)', checkbox)
