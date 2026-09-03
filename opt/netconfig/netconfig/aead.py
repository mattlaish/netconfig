"""
aead.py -- Pure-Python ChaCha20-Poly1305 (RFC 8439).

Zero external dependencies. Python stdlib has no symmetric AEAD cipher, so the
credential vault needs one implemented here. ChaCha20-Poly1305 is chosen over an
AES construction because it is defined entirely in terms of 32-bit add/xor/rotate
and modular arithmetic -- no lookup tables, no timing-sensitive S-boxes -- which
makes a correct pure-Python implementation tractable and constant-ish in structure.

This mirrors the "secretbox" AEAD used elsewhere in the suite. Validated against
the RFC 8439 Section 2.8.2 test vector (see tests).

NOTE ON PERFORMANCE: pure-Python ChaCha is fine for encrypting a credential store
(kilobytes, done rarely). Do not use it on a hot path for bulk data.
"""

import struct
import os
import hmac

_MASK32 = 0xFFFFFFFF


def _rotl32(v, c):
    return ((v << c) & _MASK32) | (v >> (32 - c))


def _quarter_round(s, a, b, c, d):
    s[a] = (s[a] + s[b]) & _MASK32
    s[d] ^= s[a]
    s[d] = _rotl32(s[d], 16)
    s[c] = (s[c] + s[d]) & _MASK32
    s[b] ^= s[c]
    s[b] = _rotl32(s[b], 12)
    s[a] = (s[a] + s[b]) & _MASK32
    s[d] ^= s[a]
    s[d] = _rotl32(s[d], 8)
    s[c] = (s[c] + s[d]) & _MASK32
    s[b] ^= s[c]
    s[b] = _rotl32(s[b], 7)


_CONST = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)


def _chacha20_block(key, counter, nonce):
    # key: 32 bytes, nonce: 12 bytes, counter: 32-bit int
    k = struct.unpack("<8I", key)
    n = struct.unpack("<3I", nonce)
    state = [
        _CONST[0], _CONST[1], _CONST[2], _CONST[3],
        k[0], k[1], k[2], k[3],
        k[4], k[5], k[6], k[7],
        counter & _MASK32, n[0], n[1], n[2],
    ]
    working = list(state)
    for _ in range(10):  # 20 rounds = 10 double-rounds
        _quarter_round(working, 0, 4, 8, 12)
        _quarter_round(working, 1, 5, 9, 13)
        _quarter_round(working, 2, 6, 10, 14)
        _quarter_round(working, 3, 7, 11, 15)
        _quarter_round(working, 0, 5, 10, 15)
        _quarter_round(working, 1, 6, 11, 12)
        _quarter_round(working, 2, 7, 8, 13)
        _quarter_round(working, 3, 4, 9, 14)
    out = [(working[i] + state[i]) & _MASK32 for i in range(16)]
    return struct.pack("<16I", *out)


def chacha20(key, counter, nonce, data):
    out = bytearray()
    blocks, rem = divmod(len(data), 64)
    total = blocks + (1 if rem else 0)
    for i in range(total):
        ks = _chacha20_block(key, counter + i, nonce)
        chunk = data[i * 64:(i + 1) * 64]
        out.extend(b ^ ks[j] for j, b in enumerate(chunk))
    return bytes(out)


_P = (1 << 130) - 5


def _poly1305_mac(msg, key):
    r = int.from_bytes(key[:16], "little")
    r &= 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:32], "little")
    acc = 0
    for i in range(0, len(msg), 16):
        block = msg[i:i + 16]
        n = int.from_bytes(block + b"\x01", "little") if len(block) < 16 \
            else int.from_bytes(block, "little") | (1 << 128)
        acc = (acc + n) % _P
        acc = (acc * r) % _P
    acc = (acc + s) & ((1 << 128) - 1)
    return acc.to_bytes(16, "little")


def _pad16(data):
    if len(data) % 16 == 0:
        return b""
    return b"\x00" * (16 - (len(data) % 16))


def encrypt(key, nonce, plaintext, aad=b""):
    """AEAD_CHACHA20_POLY1305 encrypt. Returns ciphertext || 16-byte tag."""
    if len(key) != 32:
        raise ValueError("key must be 32 bytes")
    if len(nonce) != 12:
        raise ValueError("nonce must be 12 bytes")
    otk = _chacha20_block(key, 0, nonce)[:32]
    ciphertext = chacha20(key, 1, nonce, plaintext)
    mac_data = (aad + _pad16(aad) + ciphertext + _pad16(ciphertext)
                + struct.pack("<Q", len(aad)) + struct.pack("<Q", len(ciphertext)))
    tag = _poly1305_mac(mac_data, otk)
    return ciphertext + tag


def decrypt(key, nonce, ciphertext_and_tag, aad=b""):
    """AEAD decrypt. Raises ValueError on auth failure."""
    if len(key) != 32:
        raise ValueError("key must be 32 bytes")
    if len(nonce) != 12:
        raise ValueError("nonce must be 12 bytes")
    if len(ciphertext_and_tag) < 16:
        raise ValueError("ciphertext too short")
    ciphertext = ciphertext_and_tag[:-16]
    tag = ciphertext_and_tag[-16:]
    otk = _chacha20_block(key, 0, nonce)[:32]
    mac_data = (aad + _pad16(aad) + ciphertext + _pad16(ciphertext)
                + struct.pack("<Q", len(aad)) + struct.pack("<Q", len(ciphertext)))
    expected = _poly1305_mac(mac_data, otk)
    if not hmac.compare_digest(expected, tag):
        raise ValueError("authentication failed")
    return chacha20(key, 1, nonce, ciphertext)


def random_nonce():
    return os.urandom(12)
