"""Controlled PostgreSQL core backup and restore helpers for Q-1.

The helpers deliberately shell out only to the fixed pg_dump/pg_restore binaries
with argument lists built from validated NetConfig settings. Passwords are
provided through a short-lived mode-0600 PGPASSFILE and never appear in argv,
logs, audit detail, or returned metadata.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .postgres_core import postgres_params


class PostgresBackupError(RuntimeError):
    """Raised when a controlled core backup/restore operation cannot proceed."""


_DB_NAME = re.compile(r"^[^\x00\r\n]{1,63}$")


def _validate_dbname(value: str) -> str:
    value = str(value or "").strip()
    if not _DB_NAME.fullmatch(value):
        raise PostgresBackupError("PostgreSQL database name must be 1-63 characters without control newlines")
    return value


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise PostgresBackupError(f"required PostgreSQL client tool is unavailable: {name}")
    return path


def _escape_pgpass(value: object) -> str:
    text = str(value if value is not None else "")
    if "\x00" in text or "\r" in text or "\n" in text:
        raise PostgresBackupError("PostgreSQL credential fields must not contain NUL or newlines")
    return text.replace("\\", "\\\\").replace(":", "\\:")


@contextmanager
def _pgpass(params: dict, password: str | None, *, dbname: str | None = None):
    """Yield an environment containing a private PGPASSFILE when needed."""
    base_env = dict(os.environ)
    if params.get("sslmode"):
        base_env["PGSSLMODE"] = str(params["sslmode"])
    if params.get("application_name"):
        base_env["PGAPPNAME"] = str(params["application_name"])[:63]
    base_env.setdefault("PGCONNECT_TIMEOUT", "5")
    if not password:
        yield base_env
        return
    directory = tempfile.mkdtemp(prefix="netconfig-pgpass-")
    os.chmod(directory, 0o700)
    path = os.path.join(directory, "pgpass")
    target_db = dbname or params.get("dbname") or "*"
    line = ":".join(
        _escape_pgpass(part)
        for part in (
            params.get("host") or "*",
            params.get("port") or 5432,
            target_db,
            params.get("user") or "*",
            password,
        )
    ) + "\n"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode != 0o600:
            raise PostgresBackupError("temporary PostgreSQL credential file permissions are not 0600")
        env = base_env
        env["PGPASSFILE"] = path
        yield env
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        shutil.rmtree(directory, ignore_errors=True)


def _connection_args(params: dict, *, dbname: str | None = None) -> list[str]:
    args = ["--host", str(params["host"]), "--port", str(params.get("port") or 5432)]
    if params.get("user"):
        args += ["--username", str(params["user"])]
    args += ["--dbname", _validate_dbname(dbname or params["dbname"])]
    return args


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(argv: list[str], *, env: dict, timeout: int, runner=None) -> subprocess.CompletedProcess:
    invoke = runner or subprocess.run
    try:
        result = invoke(
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=max(1, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PostgresBackupError(f"PostgreSQL client operation timed out after {timeout}s") from exc
    except OSError as exc:
        raise PostgresBackupError(f"unable to execute PostgreSQL client tool: {exc}") from exc
    if result.returncode != 0:
        # stderr may contain server/database names but should never contain a password because
        # credentials are carried only via PGPASSFILE. Bound the returned detail regardless.
        detail = (result.stderr or "PostgreSQL client operation failed").strip().replace("\x00", "")[:800]
        raise PostgresBackupError(detail)
    return result


def backup_core_database(settings: dict, password: str | None, output: str, *, timeout: int = 600,
                         overwrite: bool = False, runner=None) -> dict:
    """Create an atomic custom-format pg_dump of the configured core database."""
    if str(settings.get("core_db_backend") or "sqlite").lower() != "postgres":
        raise PostgresBackupError("core PostgreSQL backup requires core_db_backend=postgres")
    params = postgres_params(settings, password=None)
    raw_target = Path(output).expanduser()
    if raw_target.is_symlink() or raw_target.parent.is_symlink():
        raise PostgresBackupError("backup output and parent must not be symbolic links")
    target = raw_target.resolve()
    if target.exists() and not overwrite:
        raise PostgresBackupError(f"backup output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    pg_dump = _tool("pg_dump")
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    os.chmod(temp_name, 0o600)
    try:
        argv = [
            pg_dump,
            "--format=custom",
            "--no-password",
            "--no-owner",
            "--no-privileges",
            "--file",
            temp_name,
            *_connection_args(params),
        ]
        with _pgpass(params, password) as env:
            _run(argv, env=env, timeout=timeout, runner=runner)
        size = os.path.getsize(temp_name)
        if size <= 0:
            raise PostgresBackupError("pg_dump produced an empty backup")
        digest = sha256_file(temp_name)
        os.replace(temp_name, target)
        os.chmod(target, 0o600)
        checksum_path = Path(str(target) + ".sha256")
        checksum_tmp = checksum_path.with_name(f".{checksum_path.name}.tmp")
        checksum_fd = os.open(checksum_tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(checksum_fd, f"{digest}  {target.name}\n".encode("utf-8"))
        finally:
            os.close(checksum_fd)
        os.replace(checksum_tmp, checksum_path)
        return {
            "backend": "postgres",
            "database": params["dbname"],
            "path": str(target),
            "checksum_path": str(checksum_path),
            "sha256": digest,
            "bytes": size,
            "format": "pg_dump-custom",
        }
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _read_sidecar(path: Path) -> str | None:
    sidecar = Path(str(path) + ".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        return None
    text = sidecar.read_text(encoding="utf-8", errors="strict").strip()
    token = text.split(None, 1)[0] if text else ""
    if re.fullmatch(r"[0-9a-fA-F]{64}", token):
        return token.lower()
    raise PostgresBackupError("invalid PostgreSQL backup checksum sidecar")


def restore_core_database(settings: dict, password: str | None, backup: str, *, target_dbname: str,
                          confirm: str, expected_sha256: str | None = None, timeout: int = 900,
                          runner=None) -> dict:
    """Destructively restore a backup into an explicitly separate database.

    Restoring into the currently configured production database is intentionally
    refused. Operators must use a disposable/standby database for drills, validate
    it, then use their normal database promotion/runbook rather than hot-replacing
    the active database behind a running NetConfig process.
    """
    if str(settings.get("core_db_backend") or "sqlite").lower() != "postgres":
        raise PostgresBackupError("core PostgreSQL restore requires core_db_backend=postgres")
    if confirm != "RESTORE_DATABASE":
        raise PostgresBackupError("restore requires --confirm RESTORE_DATABASE")
    params = postgres_params(settings, password=None)
    target_dbname = _validate_dbname(target_dbname)
    if target_dbname == params["dbname"]:
        raise PostgresBackupError("refusing to restore over the currently configured core database")

    raw_source = Path(backup).expanduser()
    if raw_source.is_symlink():
        raise PostgresBackupError("backup must be a regular non-symlink file")
    source = raw_source.resolve()
    if not source.is_file():
        raise PostgresBackupError("backup must be a regular non-symlink file")
    digest = sha256_file(source)
    expected = (expected_sha256 or _read_sidecar(source) or "").strip().lower()
    if not expected:
        raise PostgresBackupError("restore requires a SHA-256 checksum or a valid .sha256 sidecar")
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PostgresBackupError("expected SHA-256 must be 64 lowercase hexadecimal characters")
    if digest != expected:
        raise PostgresBackupError("PostgreSQL backup SHA-256 mismatch")

    pg_restore = _tool("pg_restore")
    argv = [
        pg_restore,
        "--exit-on-error",
        "--no-password",
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        *_connection_args(params, dbname=target_dbname),
        str(source),
    ]
    with _pgpass(params, password, dbname=target_dbname) as env:
        _run(argv, env=env, timeout=timeout, runner=runner)
    return {
        "backend": "postgres",
        "source_database": params["dbname"],
        "target_database": target_dbname,
        "path": str(source),
        "sha256": digest,
        "verified": True,
        "restored": True,
    }
