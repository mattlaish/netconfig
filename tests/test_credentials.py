import os

import pytest

from netconfig.credentials import service_master_password


def test_systemd_credential_precedes_legacy_env(tmp_path):
    p = tmp_path / "vault-master"
    p.write_text("from-credential\n")
    p.chmod(0o400)
    value, source = service_master_password({
        "CREDENTIALS_DIRECTORY": str(tmp_path),
        "NETCONFIG_MASTER": "legacy",
    })
    assert (value, source) == ("from-credential", "systemd-credential")


def test_explicit_file_rejects_group_world_writable(tmp_path):
    p = tmp_path / "master"
    p.write_text("secret")
    p.chmod(0o666)
    with pytest.raises(RuntimeError, match="writable"):
        service_master_password({"NETCONFIG_MASTER_FILE": os.fspath(p)})
