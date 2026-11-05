"""Live loopback coverage for the opt-in RSA 512+ SSH compatibility backend."""
import math
import secrets
import socket
import threading

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

from netconfig.transport import (
    SSHTransport,
    TransportError,
    _compat_rsa_key_class,
)

# Skip (not error) where the optional older-device SSH backend is not installed.
paramiko = pytest.importorskip("paramiko")
rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")


def _is_probable_prime(value, rounds=24):
    if value < 2:
        return False
    for small in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if value % small == 0:
            return value == small
    odd, shifts = value - 1, 0
    while odd % 2 == 0:
        odd //= 2
        shifts += 1
    for _ in range(rounds):
        base = secrets.randbelow(value - 3) + 2
        trial = pow(base, odd, value)
        if trial in (1, value - 1):
            continue
        for _ in range(shifts - 1):
            trial = pow(trial, 2, value)
            if trial == value - 1:
                break
        else:
            return False
    return True


def _prime(bits, exponent):
    while True:
        value = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if math.gcd(value - 1, exponent) == 1 and _is_probable_prime(value):
            return value


def _small_rsa(bits):
    exponent = 65537
    while True:
        p = _prime(bits // 2, exponent)
        q = _prime(bits - bits // 2, exponent)
        if p != q and (p * q).bit_length() == bits:
            break
    if p < q:
        p, q = q, p
    modulus = p * q
    private = pow(exponent, -1, math.lcm(p - 1, q - 1))
    return rsa.RSAPrivateNumbers(
        p=p, q=q, d=private,
        dmp1=private % (p - 1), dmq1=private % (q - 1), iqmp=pow(q, -1, p),
        public_numbers=rsa.RSAPublicNumbers(exponent, modulus),
    ).private_key()


def _rsa_key(bits):
    private = _small_rsa(bits) if bits < 1024 else rsa.generate_private_key(65537, bits)
    return paramiko.RSAKey(key=private)


def _ssh_rsa_signature(private_key, data, algorithm="ssh-rsa"):
    digest = hashes.SHA1() if algorithm == "ssh-rsa" else hashes.SHA256()
    message = paramiko.Message()
    message.add_string(algorithm)
    message.add_string(private_key.sign(data, padding.PKCS1v15(), digest))
    return message


def test_legacy_rsa_sha1_verification_survives_restricted_crypto_backend(monkeypatch):
    private_key = rsa.generate_private_key(65537, 1024)
    data = b"netconfig legacy host-key exchange"
    signature = _ssh_rsa_signature(private_key, data)

    def reject_sha1(_self, _data, _message):
        raise UnsupportedAlgorithm("sha1 is not supported by this backend for RSA signing")

    monkeypatch.setattr(paramiko.RSAKey, "verify_ssh_sig", reject_sha1)
    _compat_rsa_key_class.cache_clear()
    compat_key = _compat_rsa_key_class(paramiko)(key=private_key.public_key())
    try:
        assert compat_key.verify_ssh_sig(data, paramiko.Message(signature.asbytes()))
        assert not compat_key.verify_ssh_sig(
            data + b"!", paramiko.Message(signature.asbytes())
        )
    finally:
        _compat_rsa_key_class.cache_clear()


def test_legacy_fallback_never_overrides_non_sha1_rsa_rejection(monkeypatch):
    private_key = rsa.generate_private_key(65537, 1024)
    signature = _ssh_rsa_signature(private_key, b"data", algorithm="rsa-sha2-256")

    def reject_algorithm(_self, _data, _message):
        raise UnsupportedAlgorithm("simulated backend rejection")

    monkeypatch.setattr(paramiko.RSAKey, "verify_ssh_sig", reject_algorithm)
    _compat_rsa_key_class.cache_clear()
    compat_key = _compat_rsa_key_class(paramiko)(key=private_key.public_key())
    try:
        with pytest.raises(UnsupportedAlgorithm, match="simulated backend rejection"):
            compat_key.verify_ssh_sig(b"data", paramiko.Message(signature.asbytes()))
    finally:
        _compat_rsa_key_class.cache_clear()


class _Server(paramiko.ServerInterface):
    def __init__(self):
        self.auth_attempted = False

    def get_allowed_auths(self, username):
        return "password"

    def check_auth_password(self, username, password):
        self.auth_attempted = True
        return paramiko.AUTH_SUCCESSFUL if (username, password) == ("admin", "secret") else paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == "session" else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

    def check_channel_shell_request(self, channel):
        return True


class _Fixture:
    def __init__(self, key):
        self.key = key
        self.server = _Server()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def _run(self):
        transport = None
        try:
            connection, _ = self.listener.accept()
            transport = paramiko.Transport(
                connection,
                disabled_algorithms={"keys": ["rsa-sha2-512", "rsa-sha2-256"]},
            )
            transport.add_server_key(self.key)
            transport.start_server(server=self.server)
            channel = transport.accept(10)
            if channel is None:
                return
            channel.sendall(b"\r\nold-switch# ")
            command = channel.recv(1024)
            if command:
                channel.sendall(command + b"RSA_COMPAT_OK\r\nold-switch# ")
            channel.close()
        except EOFError:
            # The client may close immediately after its assertion; a final
            # server-side channel-close packet can then observe the closed TCP stream.
            pass
        except Exception as exc:  # surfaced by close()
            self.error = exc
        finally:
            if transport is not None:
                transport.close()
            self.listener.close()

    def close(self, *, allow_client_reset=False):
        self.thread.join(10)
        assert not self.thread.is_alive()
        if self.error and not (allow_client_reset and isinstance(self.error, ConnectionResetError)):
            raise self.error


@pytest.mark.parametrize("bits", [512, 1024, 2048])
def test_legacy_backend_authenticates_and_executes_with_rsa_512_or_higher(tmp_path, bits):
    fixture = _Fixture(_rsa_key(bits)).start()
    transport = SSHTransport(
        "127.0.0.1", "admin", port=fixture.port, password="secret", legacy=True,
        known_hosts=str(tmp_path / "known_hosts"), host_key_policy="accept-new",
        connect_timeout=5, command_timeout=5,
    )
    try:
        transport.connect()
        assert transport.prompt == b"old-switch#"
        assert "RSA_COMPAT_OK" in transport.execute("show version")
    finally:
        transport.close()
        fixture.close()
    pinned = paramiko.HostKeys(str(tmp_path / "known_hosts"))
    assert pinned.lookup(f"[127.0.0.1]:{fixture.port}")["ssh-rsa"].get_bits() == bits


def test_changed_legacy_host_key_is_rejected_before_password(tmp_path):
    known_hosts = tmp_path / "known_hosts"
    first_key = _rsa_key(512)
    second_key = _rsa_key(512)
    first = _Fixture(first_key).start()
    first_transport = SSHTransport(
        "127.0.0.1", "admin", port=first.port, password="secret", legacy=True,
        known_hosts=str(known_hosts), host_key_policy="accept-new", connect_timeout=5,
    )
    try:
        first_transport.connect()
    finally:
        first_transport.close()
        first.close()

    # Reuse the pinned port with a different key.
    second = _Fixture(second_key)
    second.listener.close()
    second.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    second.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    second.listener.bind(("127.0.0.1", first.port))
    second.listener.listen(1)
    second.port = first.port
    second.start()
    changed = SSHTransport(
        "127.0.0.1", "admin", port=second.port, password="secret", legacy=True,
        known_hosts=str(known_hosts), host_key_policy="accept-new", connect_timeout=5,
    )
    try:
        with pytest.raises(TransportError, match="pinned ssh-rsa key changed"):
            changed.connect()
        assert not second.server.auth_attempted
    finally:
        changed.close()
        second.close()


def test_rsa_below_512_is_rejected_before_password(tmp_path):
    fixture = _Fixture(_rsa_key(384)).start()
    transport = SSHTransport(
        "127.0.0.1", "admin", port=fixture.port, password="secret", legacy=True,
        known_hosts=str(tmp_path / "known_hosts"), host_key_policy="accept-new",
        connect_timeout=5,
    )
    try:
        with pytest.raises(TransportError, match="at least 512 bits"):
            transport.connect()
        assert not fixture.server.auth_attempted
    finally:
        transport.close()
        fixture.close(allow_client_reset=True)
