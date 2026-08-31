"""Service credential bootstrap without adding runtime dependencies."""
from __future__ import annotations

import os


def _read_secret_file(path):
    st = os.stat(path)
    # Reject group/world writable credential sources. Readability is intentionally
    # left to deployment policy (systemd credential files are typically 0400).
    if st.st_mode & 0o022:
        raise RuntimeError(f"credential file is group/world writable: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        value = fh.read().rstrip("\r\n")
    if not value:
        raise RuntimeError(f"credential file is empty: {path}")
    return value


def service_master_password(env=None):
    """Return (secret, source) for unattended vault unlock.

    Precedence: explicit NETCONFIG_MASTER_FILE, systemd $CREDENTIALS_DIRECTORY
    vault-master credential, then legacy NETCONFIG_MASTER environment variable.
    """
    env = os.environ if env is None else env
    explicit = env.get("NETCONFIG_MASTER_FILE")
    if explicit:
        return _read_secret_file(explicit), "file"
    cred_dir = env.get("CREDENTIALS_DIRECTORY")
    if cred_dir:
        candidate = os.path.join(cred_dir, "vault-master")
        if os.path.isfile(candidate):
            return _read_secret_file(candidate), "systemd-credential"
    legacy = env.get("NETCONFIG_MASTER")
    if legacy:
        return legacy, "environment-legacy"
    return None, None
