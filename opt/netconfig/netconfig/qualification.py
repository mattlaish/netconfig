"""Q-1 runtime qualification/preflight helpers."""
from __future__ import annotations

import os
import platform
import shutil
import sys

from . import __version__


def runtime_preflight(manager) -> dict:
    """Return a secret-free runtime readiness report for the active configuration."""
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str = "", required: bool = True):
        checks.append({"name": name, "ok": bool(ok), "required": bool(required), "detail": detail[:300]})

    add("python", sys.version_info >= (3, 12), platform.python_version())
    add("ssh", bool(shutil.which(os.environ.get("NETCONFIG_SSH") or "ssh")), "required CLI transport")
    add("openssl", bool(shutil.which("openssl")), "required evidence-signing/verification adapter")

    storage = manager.storage_status()
    add("core-storage", bool(storage.get("ok") and storage.get("reachable")),
        f"backend={storage.get('backend')} revision={storage.get('schema_revision')}")
    if storage.get("backend") == "postgres":
        try:
            import psycopg  # noqa: F401
            psycopg_ok = True
        except Exception:
            psycopg_ok = False
        add("psycopg", psycopg_ok, "required for PostgreSQL core")
        add("pg_dump", bool(shutil.which("pg_dump")), "required for PostgreSQL core backup")
        add("pg_restore", bool(shutil.which("pg_restore")), "required for PostgreSQL restore drill")

    profiles = manager.protocol_profiles.list()
    gnmi_required = any(
        bool(row.get("enabled")) and str(row.get("protocol") or "").lower() == "gnmi"
        for row in profiles
    )
    add("gnmic", bool(shutil.which("gnmic")), "required when an enabled gNMI profile exists",
        required=gnmi_required)

    required_failures = [row["name"] for row in checks if row["required"] and not row["ok"]]
    return {
        "qualification_track": "Q-1",
        "version": __version__,
        "platform": platform.platform(),
        "storage": storage,
        "checks": checks,
        "required_failures": required_failures,
        "ok": not required_failures,
    }
