#!/usr/bin/env python3
"""Offline structural and source-identity verifier for NetConfig RPMs."""
from __future__ import annotations

import argparse
import gzip
import hashlib
from pathlib import Path
import stat
import struct
import sys
from typing import Sequence

# Import the sibling builder without requiring installation.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rpm_builder import (  # noqa: E402
    RPM_HEADER_MAGIC,
    TAG_NAME,
    TAG_VERSION,
    TAG_RELEASE,
    TAG_ARCH,
    TAG_BASENAMES,
    TAG_DIRINDEXES,
    TAG_DIRNAMES,
    TAG_FILESIZES,
    TAG_FILEMODES,
    TAG_FILEDIGESTS,
    TAG_FILEFLAGS,
    TAG_FILEUSERNAME,
    TAG_FILEGROUPNAME,
    TAG_REQUIRES,
    TAG_PREIN,
    TAG_POSTIN,
    TAG_PREUN,
    TAG_POSTUN,
    RPMFILE_CONFIG,
    RPMFILE_NOREPLACE,
    SIG_SHA256,
    TAG_PAYLOADDIGEST,
    collect_netconfig_payload,
    parse_spec_identity,
)


def parse_header(data: bytes, offset: int):
    if data[offset:offset+4] != RPM_HEADER_MAGIC:
        raise ValueError(f"bad RPM header magic at offset {offset}")
    count, size = struct.unpack(">II", data[offset+8:offset+16])
    entries = []
    pos = offset + 16
    for _ in range(count):
        entries.append(struct.unpack(">iiii", data[pos:pos+16]))
        pos += 16
    store = data[pos:pos+size]
    return entries, store, pos + size


def decode(entries, store):
    result = {}
    for tag, typ, off, count in entries:
        if off < 0 or off >= len(store):
            continue
        if typ == 6:
            result[tag] = store[off:].split(b"\0", 1)[0].decode("utf-8")
        elif typ == 8:
            values = []
            p = off
            for _ in range(count):
                z = store.index(0, p)
                values.append(store[p:z].decode("utf-8"))
                p = z + 1
            result[tag] = values
        elif typ == 4:
            result[tag] = list(struct.unpack(">" + "I" * count, store[off:off+4*count]))
        elif typ == 3:
            result[tag] = list(struct.unpack(">" + "H" * count, store[off:off+2*count]))
        elif typ == 7:
            result[tag] = store[off:off+count]
    return result


def parse_cpio(raw: bytes):
    out = {}
    pos = 0
    while True:
        if raw[pos:pos+6] != b"070701":
            raise ValueError(f"bad newc magic at {pos}")
        fields = [int(raw[pos+6+i*8:pos+14+i*8], 16) for i in range(13)]
        mode = fields[1]
        size = fields[6]
        namesz = fields[11]
        pos += 110
        name = raw[pos:pos+namesz-1].decode("utf-8")
        pos += namesz
        pos = (pos + 3) & ~3
        body = raw[pos:pos+size]
        pos += size
        pos = (pos + 3) & ~3
        if name == "TRAILER!!!":
            break
        out[name] = (mode, body)
    return out


def verify(rpm_path: Path, repo_root: Path) -> list[str]:
    errors: list[str] = []
    data = rpm_path.read_bytes()
    if data[:4] != b"\xed\xab\xee\xdb":
        return ["not an RPM lead"]
    sig_entries, sig_store, sig_end = parse_header(data, 96)
    sig = decode(sig_entries, sig_store)
    main_offset = (sig_end + 7) // 8 * 8
    main_entries, main_store, payload_offset = parse_header(data, main_offset)
    h = decode(main_entries, main_store)
    main_header_bytes = data[main_offset:payload_offset]
    expected_header_digest = hashlib.sha256(main_header_bytes).hexdigest()
    if sig.get(SIG_SHA256) != expected_header_digest:
        errors.append("main-header SHA-256 signature tag mismatch")
    compressed_payload = data[payload_offset:]
    expected_payload_digest = hashlib.sha256(compressed_payload).hexdigest()
    if h.get(TAG_PAYLOADDIGEST) != [expected_payload_digest]:
        errors.append("compressed payload SHA-256 tag mismatch")
    name, version, rel_base = parse_spec_identity(repo_root / "packaging/netconfig.spec")
    expected_release = f"{rel_base}.el10"
    for tag, expected, label in ((TAG_NAME, name, "name"), (TAG_VERSION, version, "version"), (TAG_RELEASE, expected_release, "release"), (TAG_ARCH, "noarch", "arch")):
        if h.get(tag) != expected:
            errors.append(f"{label}: expected {expected!r}, got {h.get(tag)!r}")
    payload = gzip.decompress(compressed_payload)
    cpio = parse_cpio(payload)
    expected_files = collect_netconfig_payload(repo_root)
    if set(cpio) != {x.path for x in expected_files}:
        errors.append("payload path set differs from source package layout")
    expected_map = {x.path: x for x in expected_files}
    for path, item in expected_map.items():
        got = cpio.get(path)
        if got is None:
            continue
        mode, body = got
        if item.is_dir:
            if stat.S_IMODE(mode) != item.mode or not stat.S_ISDIR(mode):
                errors.append(f"mode/type mismatch: {path}")
        else:
            if stat.S_IMODE(mode) != item.mode or not stat.S_ISREG(mode):
                errors.append(f"mode/type mismatch: {path}")
            if body != item.body:
                errors.append(f"payload bytes mismatch: {path}")
    # Header file flags and paths must agree with CONFIG|NOREPLACE semantics.
    names = []
    if all(k in h for k in (TAG_BASENAMES, TAG_DIRINDEXES, TAG_DIRNAMES)):
        for base, di in zip(h[TAG_BASENAMES], h[TAG_DIRINDEXES], strict=True):
            names.append(h[TAG_DIRNAMES][di] + base)
    if names:
        try:
            i = names.index("/etc/default/netconfig")
            flags = h[TAG_FILEFLAGS][i]
            if flags != RPMFILE_CONFIG | RPMFILE_NOREPLACE:
                errors.append(f"/etc/default/netconfig flags expected 17, got {flags}")
        except ValueError:
            errors.append("/etc/default/netconfig missing from RPM header")
    requires = set(h.get(TAG_REQUIRES, []))
    for req in ("/bin/sh", "/usr/bin/python3.12", "/usr/bin/ssh", "/usr/bin/openssl", "shadow-utils", "systemd"):
        if req not in requires:
            errors.append(f"missing requirement: {req}")
    for tag, label in ((TAG_PREIN, "prein"), (TAG_POSTIN, "postin"), (TAG_PREUN, "preun"), (TAG_POSTUN, "postun")):
        if not h.get(tag):
            errors.append(f"missing {label} scriptlet")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rpm", type=Path)
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    args = p.parse_args(argv)
    errors = verify(args.rpm.resolve(), args.repo_root.resolve())
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print("PASS: RPM structure, metadata, modes, scriptlets, dependencies and source bytes verified")
    print(f"sha256={hashlib.sha256(args.rpm.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
