#!/usr/bin/env python3
"""Deterministic, dependency-free RPM v4 emitter for NetConfig.

This tool is intentionally narrow: it packages the exact NetConfig filesystem
layout described by packaging/netconfig.spec. It does not replace rpmbuild for
production qualification; it exists so source/artifact integrity can be checked
on isolated runners that lack rpm/rpmbuild and network access.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
from typing import Iterable, Sequence

RPM_HEADER_MAGIC = b"\x8e\xad\xe8\x01"
TYPE_INT16 = 3
TYPE_INT32 = 4
TYPE_STRING = 6
TYPE_BINARY = 7
TYPE_STRING_ARRAY = 8
SIG_SIGNATURES = 62
HDR_IMMUTABLE = 63
HASH_SHA256 = 8
DEFAULT_SOURCE_DATE_EPOCH = 1789689600  # 2026-09-18T00:00:00Z

# RPM file flags.
RPMFILE_CONFIG = 1
RPMFILE_NOREPLACE = 16

# Common tags used by this intentionally small emitter.
TAG_HEADER_I18N = 100
SIG_SHA256 = 273
SIG_SIZE = 1000
SIG_PAYLOAD_SIZE = 1007
TAG_NAME = 1000
TAG_VERSION = 1001
TAG_RELEASE = 1002
TAG_SUMMARY = 1004
TAG_DESCRIPTION = 1005
TAG_BUILDTIME = 1006
TAG_BUILDHOST = 1007
TAG_SIZE = 1009
TAG_VENDOR = 1011
TAG_LICENSE = 1014
TAG_PACKAGER = 1015
TAG_GROUP = 1016
TAG_OS = 1021
TAG_ARCH = 1022
TAG_PREIN = 1023
TAG_POSTIN = 1024
TAG_PREUN = 1025
TAG_POSTUN = 1026
TAG_FILESIZES = 1028
TAG_FILEMODES = 1030
TAG_FILERDEVS = 1033
TAG_FILEMTIMES = 1034
TAG_FILEDIGESTS = 1035
TAG_FILELINKTOS = 1036
TAG_FILEFLAGS = 1037
TAG_FILEUSERNAME = 1039
TAG_FILEGROUPNAME = 1040
TAG_SOURCERPM = 1044
TAG_FILEVERIFYFLAGS = 1045
TAG_PROVIDES = 1047
TAG_REQUIREFLAGS = 1048
TAG_REQUIRES = 1049
TAG_REQUIREVERSION = 1050
TAG_PREINPROG = 1085
TAG_POSTINPROG = 1086
TAG_PREUNPROG = 1087
TAG_POSTUNPROG = 1088
TAG_FILEDEVICES = 1095
TAG_FILEINODES = 1096
TAG_FILELANGS = 1097
TAG_PROVIDEFLAGS = 1112
TAG_PROVIDEVERSION = 1113
TAG_DIRINDEXES = 1116
TAG_BASENAMES = 1117
TAG_DIRNAMES = 1118
TAG_PAYLOADFORMAT = 1124
TAG_PAYLOADCOMPRESSOR = 1125
TAG_PAYLOADFLAGS = 1126
TAG_FILEDIGESTALGO = 5011
TAG_PAYLOADDIGEST = 5092
TAG_PAYLOADDIGESTALGO = 5093


@dataclass(frozen=True)
class HeaderEntry:
    rpm_type: int
    count: int
    data: bytes


def _int16(values: Sequence[int]) -> HeaderEntry:
    return HeaderEntry(TYPE_INT16, len(values), struct.pack(">" + "H" * len(values), *values))


def _int32(values: Sequence[int]) -> HeaderEntry:
    return HeaderEntry(TYPE_INT32, len(values), struct.pack(">" + "I" * len(values), *values))


def _string(value: str) -> HeaderEntry:
    return HeaderEntry(TYPE_STRING, 1, value.encode("utf-8") + b"\0")


def _strings(values: Sequence[str]) -> HeaderEntry:
    return HeaderEntry(TYPE_STRING_ARRAY, len(values), b"\0".join(v.encode("utf-8") for v in values) + b"\0")


def _binary(value: bytes) -> HeaderEntry:
    return HeaderEntry(TYPE_BINARY, len(value), value)


def _index_record(tag: int, entry: HeaderEntry, offset: int) -> bytes:
    return struct.pack(">iiii", tag, entry.rpm_type, offset, entry.count)


def _header_bytes(entries: dict[int, HeaderEntry], region_tag: int) -> bytes:
    store = bytearray()
    offsets: dict[int, int] = {}
    boundaries = {TYPE_INT16: 2, TYPE_INT32: 4}
    for tag in sorted(entries):
        entry = entries[tag]
        boundary = boundaries.get(entry.rpm_type)
        if boundary and len(store) % boundary:
            store.extend(b"\0" * (boundary - len(store) % boundary))
        offsets[tag] = len(store)
        store.extend(entry.data)

    # RPM immutable/signature region pseudo-entry. The record is placed first
    # in the index but its 16-byte body is placed at the end of the store.
    immutable_data = struct.pack(">iiii", region_tag, TYPE_BINARY, -16 * (len(entries) + 1), 16)
    immutable_offset = len(store)
    store.extend(immutable_data)

    count = len(entries) + 1
    out = bytearray(RPM_HEADER_MAGIC + b"\0\0\0\0")
    out.extend(struct.pack(">II", count, len(store)))
    out.extend(struct.pack(">iiii", region_tag, TYPE_BINARY, immutable_offset, 16))
    for tag in sorted(entries):
        out.extend(_index_record(tag, entries[tag], offsets[tag]))
    out.extend(store)
    return bytes(out)


def _lead(name: str, full_version: str) -> bytes:
    nv = f"{name}-{full_version}".encode("utf-8")[:65]
    nv += b"\0" * (66 - len(nv))
    # RPM lead: magic, v3.0, binary package, i386 archnum placeholder,
    # 66-byte name, Linux osnum, header-style signature type, reserved.
    return (
        b"\xed\xab\xee\xdb\x03\x00\x00\x00\x00\x01"
        + nv
        + b"\x00\x01\x00\x05"
        + b"\0" * 16
    )


def _pad4(data: bytearray) -> None:
    data.extend(b"\0" * ((4 - len(data) % 4) % 4))


def _cpio_newc(entries: Sequence["PackageFile"], build_time: int) -> bytes:
    out = bytearray()
    ino = 1
    for item in list(entries) + [PackageFile("TRAILER!!!", b"", 0, "root", "root", 0, False)]:
        is_trailer = item.path == "TRAILER!!!"
        name = item.path.encode("utf-8") + b"\0"
        if is_trailer:
            mode = stat.S_IFREG
            body = b""
        elif item.is_dir:
            mode = stat.S_IFDIR | item.mode
            body = b""
        else:
            mode = stat.S_IFREG | item.mode
            body = item.body
        fields = (
            ino,
            mode,
            0,
            0,
            1,
            build_time,
            len(body),
            0,
            0,
            0,
            0,
            len(name),
            0,
        )
        out.extend(b"070701")
        out.extend(b"".join(f"{v:08x}".encode("ascii") for v in fields))
        out.extend(name)
        _pad4(out)
        out.extend(body)
        _pad4(out)
        ino += 1
    return bytes(out)


@dataclass(frozen=True)
class PackageFile:
    path: str
    body: bytes
    mode: int
    owner: str = "root"
    group: str = "root"
    flags: int = 0
    is_dir: bool = False

    @property
    def digest(self) -> str:
        if self.is_dir:
            return ""
        return hashlib.sha256(self.body).hexdigest()


def _read_text_lf(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def parse_spec_identity(spec_path: Path) -> tuple[str, str, str]:
    text = spec_path.read_text(encoding="utf-8")
    def field(name: str) -> str:
        m = re.search(rf"(?m)^{re.escape(name)}:\s*(\S+)", text)
        if not m:
            raise ValueError(f"missing {name}: in {spec_path}")
        return m.group(1)
    name = field("Name")
    version = field("Version")
    release = field("Release").replace("%{?dist}", "")
    if not release.isdigit():
        raise ValueError(f"unsupported non-numeric Release: {release!r}")
    return name, version, release


def collect_netconfig_payload(repo_root: Path) -> list[PackageFile]:
    items: list[PackageFile] = []
    def add_file(dest: str, src: Path, mode: int, owner: str = "root", group: str = "root", flags: int = 0, normalize_lf: bool = False) -> None:
        body = _read_text_lf(src) if normalize_lf else src.read_bytes()
        items.append(PackageFile(dest, body, mode, owner, group, flags, False))
    def add_dir(dest: str, mode: int, owner: str = "root", group: str = "root") -> None:
        items.append(PackageFile(dest, b"", mode, owner, group, 0, True))

    add_file("/etc/default/netconfig", repo_root / "etc/default/netconfig", 0o640, "root", "netconfig", RPMFILE_CONFIG | RPMFILE_NOREPLACE)
    add_file("/etc/profile.d/netconfig.sh", repo_root / "etc/profile.d/netconfig.sh", 0o644)
    add_dir("/opt/netconfig", 0o755)
    for name in ("CREDENTIALS.md", "INSTALL.md", "README.md", "WEBGUI.md"):
        add_file(f"/opt/netconfig/{name}", repo_root / "opt/netconfig" / name, 0o644)

    pkg_root = repo_root / "opt/netconfig/netconfig"
    for path in sorted(pkg_root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(repo_root / "opt/netconfig").as_posix()
        dest = "/opt/netconfig/" + rel
        if path.is_dir():
            # Match the canonical RPM payload: omit the package root itself,
            # but include nested package directories such as analytics/.
            add_dir(dest, 0o755)
        elif path.suffix not in {".pyc", ".pyo"} and "__pycache__" not in path.parts:
            add_file(dest, path, 0o644)

    add_file("/opt/netconfig/selftest.py", repo_root / "opt/netconfig/selftest.py", 0o644)
    add_file("/usr/bin/netconfig", repo_root / "usr/bin/netconfig", 0o755, normalize_lf=True)
    for name in ("netconfig-backup.service", "netconfig-backup.timer", "netconfig-web.service"):
        add_file(f"/usr/lib/systemd/system/{name}", repo_root / "usr/lib/systemd/system" / name, 0o644, normalize_lf=True)
    add_dir("/var/lib/netconfig", 0o700, "netconfig", "netconfig")
    items.sort(key=lambda x: x.path)
    return items


def _file_path_indexes(files: Sequence[PackageFile]) -> tuple[list[str], list[int], list[str]]:
    dirs: list[str] = []
    dir_index: dict[str, int] = {}
    basenames: list[str] = []
    indexes: list[int] = []
    for item in files:
        p = PurePosixPath(item.path)
        dirname = str(p.parent) + "/"
        basename = p.name
        if dirname not in dir_index:
            dir_index[dirname] = len(dirs)
            dirs.append(dirname)
        indexes.append(dir_index[dirname])
        basenames.append(basename)
    return basenames, indexes, dirs


PREIN = '''getent group netconfig >/dev/null || groupadd -r netconfig
getent passwd netconfig >/dev/null || useradd -r -g netconfig -d /var/lib/netconfig -s /sbin/nologin -c "NetConfig service account" netconfig
exit 0'''
POSTIN = '''if [ "$1" -eq 1 ] && [ -x /usr/bin/systemctl ]; then
  /usr/bin/systemctl preset netconfig-web.service netconfig-backup.timer >/dev/null 2>&1 || :
fi
exit 0'''
PREUN = '''if [ "$1" -eq 0 ] && [ -x /usr/bin/systemctl ]; then
  /usr/bin/systemctl --no-reload disable --now netconfig-web.service netconfig-backup.timer >/dev/null 2>&1 || :
fi
exit 0'''
POSTUN = '''if [ -x /usr/bin/systemctl ]; then
  /usr/bin/systemctl daemon-reload >/dev/null 2>&1 || :
  if [ "$1" -ge 1 ]; then
    /usr/bin/systemctl try-restart netconfig-web.service >/dev/null 2>&1 || :
  fi
fi
exit 0'''


def build_rpm(repo_root: Path, output: Path, dist: str, source_date_epoch: int) -> dict[str, object]:
    spec = repo_root / "packaging/netconfig.spec"
    name, version, release_base = parse_spec_identity(spec)
    release = f"{release_base}{dist}"
    files = collect_netconfig_payload(repo_root)
    payload_size = sum(len(f.body) for f in files)
    cpio = _cpio_newc(files, source_date_epoch)
    payload = gzip.compress(cpio, compresslevel=9, mtime=source_date_epoch)
    payload_digest = hashlib.sha256(payload).hexdigest()

    basenames, dirindexes, dirnames = _file_path_indexes(files)
    provides_version = f"{version}-{release}"
    requires = ["/bin/sh", "/usr/bin/python3.12", "/usr/bin/ssh", "/usr/bin/openssl", "shadow-utils", "systemd"]

    main: dict[int, HeaderEntry] = {
        TAG_HEADER_I18N: _string("C"),
        TAG_NAME: _string(name),
        TAG_VERSION: _string(version),
        TAG_RELEASE: _string(release),
        TAG_SUMMARY: _string("Network configuration and security operations console"),
        TAG_DESCRIPTION: _string("NetConfig provides device inventory, encrypted credential storage, configuration backup and diffing, approval workflows, compliance checks, telemetry, network intelligence, and a web operations console."),
        TAG_BUILDTIME: _int32([source_date_epoch]),
        TAG_BUILDHOST: _string("netconfig-offline-builder"),
        TAG_SIZE: _int32([payload_size]),
        TAG_VENDOR: _string("NetConfig Engineering"),
        TAG_LICENSE: _string("Proprietary"),
        TAG_PACKAGER: _string("NetConfig Offline RPM Builder"),
        TAG_GROUP: _string("Applications/System"),
        TAG_OS: _string("linux"),
        TAG_ARCH: _string("noarch"),
        TAG_PREIN: _string(PREIN),
        TAG_POSTIN: _string(POSTIN),
        TAG_PREUN: _string(PREUN),
        TAG_POSTUN: _string(POSTUN),
        TAG_FILESIZES: _int32([len(f.body) for f in files]),
        TAG_FILEMODES: _int16([(stat.S_IFDIR if f.is_dir else stat.S_IFREG) | f.mode for f in files]),
        TAG_FILERDEVS: _int16([0 for _ in files]),
        TAG_FILEMTIMES: _int32([source_date_epoch for _ in files]),
        TAG_FILEDIGESTS: _strings([f.digest for f in files]),
        TAG_FILELINKTOS: _strings(["" for _ in files]),
        TAG_FILEFLAGS: _int32([f.flags for f in files]),
        TAG_FILEUSERNAME: _strings([f.owner for f in files]),
        TAG_FILEGROUPNAME: _strings([f.group for f in files]),
        TAG_SOURCERPM: _string(f"{name}-{version}-{release}.src.rpm"),
        TAG_FILEVERIFYFLAGS: _int32([0xFFFFFFFF for _ in files]),
        TAG_PROVIDES: _strings([name]),
        TAG_REQUIREFLAGS: _int32([0 for _ in requires]),
        TAG_REQUIRES: _strings(requires),
        TAG_REQUIREVERSION: _strings(["" for _ in requires]),
        TAG_PREINPROG: _string("/bin/sh"),
        TAG_POSTINPROG: _string("/bin/sh"),
        TAG_PREUNPROG: _string("/bin/sh"),
        TAG_POSTUNPROG: _string("/bin/sh"),
        TAG_FILEDEVICES: _int32([1 for _ in files]),
        TAG_FILEINODES: _int32(list(range(1, len(files) + 1))),
        TAG_FILELANGS: _strings(["" for _ in files]),
        TAG_PROVIDEFLAGS: _int32([8]),
        TAG_PROVIDEVERSION: _strings([provides_version]),
        TAG_DIRINDEXES: _int32(dirindexes),
        TAG_BASENAMES: _strings(basenames),
        TAG_DIRNAMES: _strings(dirnames),
        TAG_PAYLOADFORMAT: _string("cpio"),
        TAG_PAYLOADCOMPRESSOR: _string("gzip"),
        TAG_PAYLOADFLAGS: _string("9"),
        TAG_FILEDIGESTALGO: _int32([HASH_SHA256 for _ in files]),
        TAG_PAYLOADDIGEST: _strings([payload_digest]),
        TAG_PAYLOADDIGESTALGO: _int32([HASH_SHA256]),
    }
    main_header = _header_bytes(main, HDR_IMMUTABLE)
    signature = {
        SIG_SHA256: _string(hashlib.sha256(main_header).hexdigest()),
        SIG_SIZE: _int32([len(main_header) + len(payload)]),
        SIG_PAYLOAD_SIZE: _int32([payload_size]),
    }
    signature_header = _header_bytes(signature, SIG_SIGNATURES)
    sig_padding = b"\0" * ((8 - len(signature_header) % 8) % 8)
    rpm_bytes = _lead(name, provides_version) + signature_header + sig_padding + main_header + payload
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rpm_bytes)
    return {
        "name": name,
        "version": version,
        "release": release,
        "arch": "noarch",
        "path": str(output),
        "sha256": hashlib.sha256(rpm_bytes).hexdigest(),
        "payload_sha256": payload_digest,
        "payload_files": len(files),
        "payload_size": payload_size,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dist", default=".el10")
    parser.add_argument("--source-date-epoch", type=int, default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)))
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    name, version, release = parse_spec_identity(repo_root / "packaging/netconfig.spec")
    output = args.output or (repo_root / "dist" / f"{name}-{version}-{release}{args.dist}.noarch.rpm")
    result = build_rpm(repo_root, output.resolve(), args.dist, args.source_date_epoch)
    for key in ("path", "sha256", "payload_sha256", "payload_files", "payload_size"):
        print(f"{key}={result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
