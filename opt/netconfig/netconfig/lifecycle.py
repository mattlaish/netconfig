"""R60 appliance lifecycle preservation and rollback helpers.

The module deliberately separates *state preservation* from package installation.
It creates a root/operator-controlled pre-upgrade snapshot for local NetConfig state,
verifies checksums before restore, records external secret/certificate fingerprints
without copying those files into exported evidence, and restores local state only
behind an explicit destructive confirmation token.

PostgreSQL rollback remains a database runbook operation: create a checksummed
pg_dump before upgrade, restore it into a separate rollback database, validate it,
and switch the configured database deliberately.  This module never hot-replaces
an active PostgreSQL database.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
from typing import Iterable

from .config import Paths, load_settings

SNAPSHOT_FORMAT = "netconfig-r60-local-state-v1"
CONFIRM_RESTORE = "RESTORE_LOCAL_STATE"
DEFAULT_MIN_FREE_BYTES = 256 * 1024 * 1024


class LifecycleError(RuntimeError):
    """Raised when lifecycle preservation/restore cannot proceed safely."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _safe_regular(path: Path, *, required: bool = False) -> bool:
    if not path.exists():
        if required:
            raise LifecycleError(f"required path missing: {path}")
        return False
    if path.is_symlink() or not path.is_file():
        raise LifecycleError(f"preservation path must be a regular non-symlink file: {path}")
    return True


def _walk_regular(root: Path) -> list[Path]:
    if root.is_symlink():
        raise LifecycleError(f"state root must not be a symlink: {root}")
    if not root.exists():
        return []
    if not root.is_dir():
        raise LifecycleError(f"state root must be a directory: {root}")
    out: list[Path] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in list(dirs):
            p = current_path / name
            if p.is_symlink():
                raise LifecycleError(f"symbolic links are not allowed in lifecycle state: {p}")
        for name in files:
            p = current_path / name
            if p.is_symlink():
                raise LifecycleError(f"symbolic links are not allowed in lifecycle state: {p}")
            if not p.is_file():
                raise LifecycleError(f"non-regular lifecycle state entry: {p}")
            out.append(p)
    return sorted(out)


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    _safe_regular(path)
    for raw in path.read_text(encoding="utf-8", errors="strict").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if re.fullmatch(r"[A-Z0-9_]+", key):
            values[key] = value
    return values


def _absolute_file(value: str) -> Path | None:
    if not value:
        return None
    p = Path(value).expanduser()
    if not p.is_absolute():
        return None
    return p


def referenced_external_files(settings: dict, *, config_path: str = "/etc/default/netconfig") -> list[tuple[str, Path]]:
    """Return external preservation references without reading secret contents into logs.

    These files are fingerprinted only.  They are intentionally not duplicated into
    the lifecycle snapshot because package upgrade must not mutate them and copying
    external secret material increases exposure.
    """
    refs: list[tuple[str, Path]] = []
    env = _parse_env_file(Path(config_path))
    for key in ("NETCONFIG_MASTER_FILE", "NETCONFIG_DB_PASSWORD_FILE", "NETCONFIG_EVIDENCE_SIGNING_KEY_FILE"):
        p = _absolute_file(env.get(key, ""))
        if p is not None:
            refs.append((key.lower(), p))
    for key in ("web_tls_cert", "web_tls_key"):
        p = _absolute_file(str(settings.get(key) or ""))
        if p is not None:
            refs.append((key, p))
    dedup: dict[str, tuple[str, Path]] = {}
    for kind, path in refs:
        dedup[str(path)] = (kind, path)
    return [dedup[k] for k in sorted(dedup)]


def _file_record(path: Path, *, relative_to: Path | None = None, copied: bool = True, kind: str = "state") -> dict:
    st = path.stat()
    name = str(path.relative_to(relative_to)) if relative_to else str(path)
    return {
        "path": name,
        "kind": kind,
        "copied": bool(copied),
        "bytes": st.st_size,
        "sha256": _sha256(path),
        "mode": f"{stat.S_IMODE(st.st_mode):04o}",
        "uid": st.st_uid,
        "gid": st.st_gid,
    }


def estimate_state_bytes(home: str) -> int:
    root = Path(home).expanduser().resolve()
    return sum(p.stat().st_size for p in _walk_regular(root))


def _require_space(parent: Path, required: int) -> dict:
    usage = shutil.disk_usage(parent)
    if usage.free < required:
        raise LifecycleError(f"insufficient free space for lifecycle snapshot: required={required} free={usage.free}")
    return {"required_bytes": required, "free_bytes": usage.free}


def create_local_snapshot(home: str, output: str, *, config_path: str = "/etc/default/netconfig",
                          min_free_bytes: int = DEFAULT_MIN_FREE_BYTES) -> dict:
    root = Path(home).expanduser().resolve()
    out = Path(output).expanduser()
    if out.exists() or out.is_symlink():
        raise LifecycleError(f"snapshot output must not already exist: {out}")
    parent = out.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    if out.parent.is_symlink():
        raise LifecycleError("snapshot parent must not be a symbolic link")

    state_files = _walk_regular(root)
    state_bytes = sum(p.stat().st_size for p in state_files)
    config = Path(config_path).expanduser()
    config_bytes = config.stat().st_size if _safe_regular(config) else 0
    # One complete copy plus a conservative fixed reserve for package/cache/temp work.
    space = _require_space(parent, state_bytes + config_bytes + max(0, int(min_free_bytes)))

    settings = load_settings(Paths(str(root)))
    external: list[dict] = []
    for kind, path in referenced_external_files(settings, config_path=str(config)):
        if _safe_regular(path):
            external.append(_file_record(path, copied=False, kind=kind))

    try:
        out.mkdir(mode=0o700)
        data_dir = out / "state"
        data_dir.mkdir(mode=0o700)
        if root.exists():
            for src in state_files:
                rel = src.relative_to(root)
                dst = data_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst, follow_symlinks=False)
        config_copy = None
        if config.exists():
            config_copy = out / "netconfig.default"
            shutil.copy2(config, config_copy, follow_symlinks=False)

        records = [_file_record(p, relative_to=root, kind="state") for p in state_files]
        manifest = {
            "format": SNAPSHOT_FORMAT,
            "created_unix": time.time(),
            "home": str(root),
            "config_path": str(config),
            "backend": str(settings.get("core_db_backend") or "sqlite").lower(),
            "space_preflight": space,
            "files": records,
            "config": _file_record(config, kind="config") if config.exists() else None,
            "external_fingerprints": external,
            "postgresql_rollback_rule": (
                "When backend=postgres, create a checksummed pg_dump before upgrade; on failed upgrade restore "
                "into a separate rollback database, validate it, then deliberately switch database configuration."
            ),
        }
        manifest_path = out / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(manifest_path, 0o600)
        for current, dirs, files in os.walk(out):
            for name in dirs:
                os.chmod(Path(current) / name, 0o700)
        result = verify_local_snapshot(str(out))
        result.update({"snapshot": str(out.resolve()), "backend": manifest["backend"]})
        return result
    except Exception:
        shutil.rmtree(out, ignore_errors=True)
        raise


def _load_manifest(snapshot: Path) -> dict:
    if snapshot.is_symlink() or not snapshot.is_dir():
        raise LifecycleError("snapshot must be a non-symlink directory")
    manifest_path = snapshot / "manifest.json"
    _safe_regular(manifest_path, required=True)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"invalid lifecycle snapshot manifest: {exc}") from exc
    if manifest.get("format") != SNAPSHOT_FORMAT:
        raise LifecycleError("unsupported lifecycle snapshot format")
    return manifest


def verify_local_snapshot(snapshot: str, *, verify_external: bool = True) -> dict:
    root = Path(snapshot).expanduser().resolve()
    manifest = _load_manifest(root)
    errors: list[str] = []
    data_dir = root / "state"
    if data_dir.is_symlink() or not data_dir.is_dir():
        errors.append("snapshot state directory missing or unsafe")
    for rec in manifest.get("files") or []:
        rel = Path(str(rec.get("path") or ""))
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"unsafe manifest path: {rel}")
            continue
        path = data_dir / rel
        try:
            if not _safe_regular(path, required=True):
                continue
            if path.stat().st_size != int(rec["bytes"]) or _sha256(path) != rec["sha256"]:
                errors.append(f"state checksum mismatch: {rel}")
        except (LifecycleError, KeyError, ValueError) as exc:
            errors.append(str(exc))
    config_rec = manifest.get("config")
    if config_rec:
        config_copy = root / "netconfig.default"
        try:
            _safe_regular(config_copy, required=True)
            if config_copy.stat().st_size != int(config_rec["bytes"]) or _sha256(config_copy) != config_rec["sha256"]:
                errors.append("configuration snapshot checksum mismatch")
        except (LifecycleError, KeyError, ValueError) as exc:
            errors.append(str(exc))
    if verify_external:
        for rec in manifest.get("external_fingerprints") or []:
            path = Path(str(rec.get("path") or ""))
            try:
                _safe_regular(path, required=True)
                if path.stat().st_size != int(rec["bytes"]) or _sha256(path) != rec["sha256"]:
                    errors.append(f"external preservation fingerprint changed: {path}")
            except (LifecycleError, KeyError, ValueError) as exc:
                errors.append(str(exc))
    return {
        "verified": not errors,
        "format": manifest.get("format"),
        "backend": manifest.get("backend"),
        "files_checked": len(manifest.get("files") or []),
        "external_checked": len(manifest.get("external_fingerprints") or []) if verify_external else 0,
        "errors": errors,
    }


def _apply_record_metadata(path: Path, rec: dict) -> None:
    try:
        os.chmod(path, int(str(rec.get("mode") or "0600"), 8), follow_symlinks=False)
    except OSError as exc:
        raise LifecycleError(f"unable to restore mode for {path}: {exc}") from exc
    if os.geteuid() == 0:
        try:
            os.chown(path, int(rec.get("uid", 0)), int(rec.get("gid", 0)), follow_symlinks=False)
        except OSError as exc:
            raise LifecycleError(f"unable to restore ownership for {path}: {exc}") from exc


def restore_local_snapshot(snapshot: str, *, home: str | None = None, config_path: str | None = None,
                           confirm: str) -> dict:
    if confirm != CONFIRM_RESTORE:
        raise LifecycleError(f"restore requires --confirm {CONFIRM_RESTORE}")
    source = Path(snapshot).expanduser().resolve()
    manifest = _load_manifest(source)
    verified = verify_local_snapshot(str(source), verify_external=True)
    if not verified["verified"]:
        raise LifecycleError("snapshot verification failed: " + "; ".join(verified["errors"]))

    target = Path(home or manifest["home"]).expanduser().resolve()
    cfg_target = Path(config_path or manifest["config_path"]).expanduser()
    if target.is_symlink() or cfg_target.is_symlink():
        raise LifecycleError("restore target paths must not be symbolic links")
    quarantine = target.with_name(f"{target.name}.pre-r60-restore-{int(time.time())}")
    if quarantine.exists():
        raise LifecycleError(f"restore quarantine path already exists: {quarantine}")

    if target.exists():
        target.rename(quarantine)
    try:
        target.mkdir(parents=True, mode=0o700)
        data_dir = source / "state"
        rec_by_path = {str(r["path"]): r for r in manifest.get("files") or []}
        for src in _walk_regular(data_dir):
            rel = src.relative_to(data_dir)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst, follow_symlinks=False)
            _apply_record_metadata(dst, rec_by_path[str(rel)])
        if manifest.get("config"):
            cfg_target.parent.mkdir(parents=True, exist_ok=True)
            tmp = cfg_target.with_name(f".{cfg_target.name}.r60-restore.tmp")
            if tmp.exists():
                raise LifecycleError(f"temporary restore file already exists: {tmp}")
            shutil.copy2(source / "netconfig.default", tmp, follow_symlinks=False)
            _apply_record_metadata(tmp, manifest["config"])
            os.replace(tmp, cfg_target)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        if quarantine.exists():
            quarantine.rename(target)
        raise

    return {
        "restored": True,
        "home": str(target),
        "config_path": str(cfg_target),
        "quarantine": str(quarantine) if quarantine.exists() else None,
        "backend": manifest.get("backend"),
        "external_preservation_verified": True,
    }


def retention_candidates(root: str, *, keep: int) -> list[str]:
    """Return oldest R60 lifecycle snapshots that exceed a bounded keep count."""
    if keep < 1:
        raise LifecycleError("keep must be >= 1")
    base = Path(root).expanduser()
    if not base.exists():
        return []
    if base.is_symlink() or not base.is_dir():
        raise LifecycleError("lifecycle retention root must be a directory")
    rows: list[tuple[float, Path]] = []
    for child in base.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        try:
            manifest = _load_manifest(child)
            rows.append((float(manifest.get("created_unix") or 0), child))
        except LifecycleError:
            continue
    rows.sort(key=lambda x: (x[0], x[1].name), reverse=True)
    return [str(path) for _ts, path in rows[keep:]]

_DBNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$.-]{0,62}$")


def switch_postgres_database(home: str, target_dbname: str, *, confirm: str) -> dict:
    """Atomically repoint NetConfig to a pre-restored PostgreSQL rollback database.

    This does not create, restore, validate, or promote a database.  The target must
    already have been restored and validated by the PostgreSQL lifecycle runbook.
    """
    if confirm != "SWITCH_POSTGRES_ROLLBACK":
        raise LifecycleError("database switch requires --confirm SWITCH_POSTGRES_ROLLBACK")
    if not _DBNAME_RE.fullmatch(str(target_dbname or "")):
        raise LifecycleError("invalid PostgreSQL rollback database name")
    paths = Paths(str(Path(home).expanduser().resolve()))
    settings = load_settings(paths)
    if str(settings.get("core_db_backend") or "sqlite").lower() != "postgres":
        raise LifecycleError("PostgreSQL rollback switch requires core_db_backend=postgres")
    old = str(settings.get("pg_dbname") or "")
    if not old:
        raise LifecycleError("configured PostgreSQL database name is empty")
    if old == target_dbname:
        return {"switched": False, "old_database": old, "new_database": target_dbname}
    settings["pg_dbname"] = target_dbname
    target = Path(paths.settings_file)
    tmp = target.with_name(f".{target.name}.r60-switch.tmp")
    if tmp.exists() or tmp.is_symlink():
        raise LifecycleError(f"temporary settings path already exists: {tmp}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, (json.dumps(settings, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    os.replace(tmp, target)
    return {"switched": True, "old_database": old, "new_database": target_dbname}


def verify_live_state(snapshot: str, *, home: str | None = None, config_path: str | None = None,
                      verify_external: bool = True) -> dict:
    """Compare current local state with a snapshot; intended for rollback verification."""
    source = Path(snapshot).expanduser().resolve()
    manifest = _load_manifest(source)
    target = Path(home or manifest["home"]).expanduser().resolve()
    cfg = Path(config_path or manifest["config_path"]).expanduser()
    errors: list[str] = []
    expected = {str(rec["path"]): rec for rec in manifest.get("files") or []}
    try:
        current_files = _walk_regular(target)
    except LifecycleError as exc:
        current_files = []
        errors.append(str(exc))
    current_names = {str(p.relative_to(target)) for p in current_files} if target.exists() else set()
    if current_names != set(expected):
        missing = sorted(set(expected) - current_names)[:20]
        extra = sorted(current_names - set(expected))[:20]
        if missing:
            errors.append("missing restored state files: " + ", ".join(missing))
        if extra:
            errors.append("unexpected restored state files: " + ", ".join(extra))
    for p in current_files:
        rel = str(p.relative_to(target))
        rec = expected.get(rel)
        if not rec:
            continue
        if p.stat().st_size != int(rec["bytes"]) or _sha256(p) != rec["sha256"]:
            errors.append(f"restored state checksum mismatch: {rel}")
    config_rec = manifest.get("config")
    if config_rec:
        try:
            _safe_regular(cfg, required=True)
            if cfg.stat().st_size != int(config_rec["bytes"]) or _sha256(cfg) != config_rec["sha256"]:
                errors.append("restored configuration checksum mismatch")
        except LifecycleError as exc:
            errors.append(str(exc))
    if verify_external:
        for rec in manifest.get("external_fingerprints") or []:
            path = Path(str(rec.get("path") or ""))
            try:
                _safe_regular(path, required=True)
                if path.stat().st_size != int(rec["bytes"]) or _sha256(path) != rec["sha256"]:
                    errors.append(f"external preservation fingerprint changed: {path}")
            except LifecycleError as exc:
                errors.append(str(exc))
    return {"verified": not errors, "files_checked": len(expected), "errors": errors}
