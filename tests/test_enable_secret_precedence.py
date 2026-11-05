"""Credential precedence regression for Cisco privileged-mode collection."""

from netconfig.manager import Manager


def _device(manager, *, secret_ref, enable_ref):
    manager.inv.upsert(
        name="router", host="192.0.2.10", port=22, platform="cisco_ios",
        device_type="network", secret_ref=secret_ref, enable_ref=enable_ref,
        use_key=False, legacy=True, scrub=True, enabled=True, tags=[], notes="",
        snmp_version="", snmp_ref=None,
    )
    return manager.inv.get("router")


def _manager(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    manager.vault.create("master-password")
    manager.unlock_vault("master-password")
    return manager


def test_same_web_secret_uses_enable_password_not_ssh_password(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.vault.set_secret(
            "router-ssh", username="admin", password="login-password",
            enable_password="actual-enable-secret",
        )
        device = _device(manager, secret_ref="router-ssh", enable_ref="router-ssh")
        password, _key, _passphrase, enable = manager._creds_for(device)
        assert password == "login-password"
        assert enable == "actual-enable-secret"
    finally:
        manager.close()


def test_separate_enable_secret_prefers_its_explicit_enable_password(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.vault.set_secret("router-ssh", username="admin", password="login-password")
        manager.vault.set_secret(
            "router-enable", password="fallback-password",
            enable_password="actual-enable-secret",
        )
        device = _device(manager, secret_ref="router-ssh", enable_ref="router-enable")
        assert manager._creds_for(device)[3] == "actual-enable-secret"
    finally:
        manager.close()


def test_separate_password_only_enable_secret_remains_supported(tmp_path):
    manager = _manager(tmp_path)
    try:
        manager.vault.set_secret("router-ssh", username="admin", password="login-password")
        manager.vault.set_secret("router-enable", password="actual-enable-secret")
        device = _device(manager, secret_ref="router-ssh", enable_ref="router-enable")
        assert manager._creds_for(device)[3] == "actual-enable-secret"
    finally:
        manager.close()
