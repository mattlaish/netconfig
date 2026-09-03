"""
aes.py -- Minimal pure-Python AES (128/192/256), stdlib only.

Why this exists: SNMPv3's privacy layer (authPriv) requires a block cipher --
AES-128-CFB per RFC 3826 -- and the Python standard library ships no symmetric
cipher at all. The suite's zero-dependency rule rules out pycryptodome, so the
block cipher is implemented here and validated against the FIPS-197 known-answer
vector in the self-test. It is used only to encrypt small SNMP PDUs, so the
modest speed of a pure-Python cipher is irrelevant.

Scope: ECB block encrypt/decrypt plus CFB-128 (what SNMP privacy uses). This is
NOT a general crypto library; the vault uses ChaCha20-Poly1305 (aead.py) for
everything else. AES lives here purely because the SNMPv3 wire format mandates it.
"""

_SBOX = []
_INV_SBOX = []


def _rotl8(x, n):
    return ((x << n) | (x >> (8 - n))) & 0xFF


def _init_sbox():
    p = q = 1
    sbox = [0] * 256
    # standard multiplicative-inverse (via log/exp walk) + affine transform.
    # The affine step rotates (ROTL8), it does not shift.
    while True:
        p = (p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)) & 0xFF
        q ^= (q << 1) & 0xFF
        q ^= (q << 2) & 0xFF
        q ^= (q << 4) & 0xFF
        q ^= 0x09 if q & 0x80 else 0
        q &= 0xFF
        xformed = q ^ _rotl8(q, 1) ^ _rotl8(q, 2) ^ _rotl8(q, 3) ^ _rotl8(q, 4)
        sbox[p] = (xformed ^ 0x63) & 0xFF
        if p == 1:
            break
    sbox[0] = 0x63
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i
    return sbox, inv


_SBOX, _INV_SBOX = _init_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36,
         0x6C, 0xD8, 0xAB, 0x4D]


def _xtime(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else (a << 1)


def _mul(a, b):
    res = 0
    for _ in range(8):
        if b & 1:
            res ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return res & 0xFF


def _key_expansion(key):
    nk = len(key) // 4
    nr = {4: 10, 6: 12, 8: 14}[nk]
    w = [list(key[4 * i:4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        temp = list(w[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]                 # RotWord
            temp = [_SBOX[b] for b in temp]            # SubWord
            temp[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            temp = [_SBOX[b] for b in temp]
        w.append([w[i - nk][j] ^ temp[j] for j in range(4)])
    return w, nr


def _add_round_key(state, w, rnd):
    for c in range(4):
        for r in range(4):
            state[r][c] ^= w[rnd * 4 + c][r]


def _sub_bytes(state, box):
    for r in range(4):
        for c in range(4):
            state[r][c] = box[state[r][c]]


def _shift_rows(state):
    for r in range(1, 4):
        state[r] = state[r][r:] + state[r][:r]


def _inv_shift_rows(state):
    for r in range(1, 4):
        state[r] = state[r][-r:] + state[r][:-r]


def _mix_columns(state):
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _xtime(a[0]) ^ (_xtime(a[1]) ^ a[1]) ^ a[2] ^ a[3]
        state[1][c] = a[0] ^ _xtime(a[1]) ^ (_xtime(a[2]) ^ a[2]) ^ a[3]
        state[2][c] = a[0] ^ a[1] ^ _xtime(a[2]) ^ (_xtime(a[3]) ^ a[3])
        state[3][c] = (_xtime(a[0]) ^ a[0]) ^ a[1] ^ a[2] ^ _xtime(a[3])


def _inv_mix_columns(state):
    for c in range(4):
        a = [state[r][c] for r in range(4)]
        state[0][c] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
        state[1][c] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
        state[2][c] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
        state[3][c] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)


def _bytes_to_state(b):
    return [[b[r + 4 * c] for c in range(4)] for r in range(4)]


def _state_to_bytes(s):
    return bytes(s[r][c] for c in range(4) for r in range(4))


class AES:
    def __init__(self, key):
        if len(key) not in (16, 24, 32):
            raise ValueError("AES key must be 16/24/32 bytes")
        self._w, self._nr = _key_expansion(key)

    def encrypt_block(self, block):
        if len(block) != 16:
            raise ValueError("block must be 16 bytes")
        state = _bytes_to_state(block)
        _add_round_key(state, self._w, 0)
        for rnd in range(1, self._nr):
            _sub_bytes(state, _SBOX)
            _shift_rows(state)
            _mix_columns(state)
            _add_round_key(state, self._w, rnd)
        _sub_bytes(state, _SBOX)
        _shift_rows(state)
        _add_round_key(state, self._w, self._nr)
        return _state_to_bytes(state)

    def decrypt_block(self, block):
        state = _bytes_to_state(block)
        _add_round_key(state, self._w, self._nr)
        for rnd in range(self._nr - 1, 0, -1):
            _inv_shift_rows(state)
            _sub_bytes(state, _INV_SBOX)
            _add_round_key(state, self._w, rnd)
            _inv_mix_columns(state)
        _inv_shift_rows(state)
        _sub_bytes(state, _INV_SBOX)
        _add_round_key(state, self._w, 0)
        return _state_to_bytes(state)


def _xor(a, b):
    return bytes(x ^ y for x, y in zip(a, b))


def cfb128_encrypt(key, iv, data):
    """AES-128-CFB (full-block feedback, s=128), as used by SNMP usmAesCfb128."""
    aes = AES(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        keystream = aes.encrypt_block(prev)
        ct = _xor(chunk, keystream[:len(chunk)])
        out += ct
        prev = ct if len(ct) == 16 else (ct + keystream[len(ct):])
    return bytes(out)


def cfb128_decrypt(key, iv, data):
    aes = AES(key)
    out = bytearray()
    prev = iv
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        keystream = aes.encrypt_block(prev)
        pt = _xor(chunk, keystream[:len(chunk)])
        out += pt
        prev = chunk if len(chunk) == 16 else (chunk + keystream[len(chunk):])
    return bytes(out)
