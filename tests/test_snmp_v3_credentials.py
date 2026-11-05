"""Reject missing USM fields and test the same credential edits that Save uses."""
import hashlib
import json

import pytest

from netconfig import snmp
from test_web_ux import console as _console_fixture, _device

console = _console_fixture


@pytest.mark.parametrize("username", [None, "", 7])
def test_missing_or_invalid_username_has_a_field_error(username):
    with pytest.raises(snmp.SNMPError, match="SNMPv3 username is missing"):
        snmp.V3Params(username)


@pytest.mark.parametrize("password", [None, "", 7])
@pytest.mark.parametrize("protocol", ["sha1", "sha256", "md5"])
def test_authentication_never_silently_falls_back_when_password_is_missing(password, protocol):
    with pytest.raises(snmp.SNMPError, match="SNMPv3 authentication password is missing"):
        snmp.V3Params("user", auth_proto=protocol, auth_pass=password)


@pytest.mark.parametrize("password", [None, "", b"not-a-text-password"])
def test_direct_password_localization_rejects_missing_input(password):
    with pytest.raises(snmp.SNMPError, match="SNMPv3 password is missing"):
        snmp.password_to_key(password, b"engine", hashlib.sha1)


def test_explicit_noauth_and_privacy_password_reuse_remain_supported():
    assert snmp.V3Params("reader").level == "noAuthNoPriv"
    auth = snmp.V3Params("reader", "sha256", "  auth password  ")
    assert auth.level == "authNoPriv" and auth.auth_pass == "  auth password  "
    private = snmp.V3Params("reader", "sha256", "  auth password  ", "aes256")
    assert private.level == "authPriv" and private.priv_pass == private.auth_pass
    assert snmp.V3Params("reader", "sha256", "auth-pass", "aes256", " private ").priv_pass == " private "


def test_invalid_privacy_configuration_has_clear_error():
    with pytest.raises(snmp.SNMPError, match="encryption requires an authentication protocol"):
        snmp.V3Params("user", priv_proto="aes")
    with pytest.raises(snmp.SNMPError, match="privacy password is missing"):
        snmp.V3Params("user", "sha256", "auth-pass", "aes", priv_pass=7)


def _vault(manager):
    manager.vault.create("test-master-password")
    manager.unlock_vault("test-master-password")


def _post(console, **fields):
    form = {"csrf": "ux-csrf", "host": "192.0.2.10", "port": "22", "device_type": "network",
            "snmp_version": "v3", "cred_mode": "manual", **fields}
    code, _, body = console.request("POST", "/device-test", form, token=console.session())
    return code, json.loads(body), body


def _capture(console, monkeypatch):
    calls = []
    def tested(host, **kwargs):
        calls.append((host, kwargs))
        return [{"check": "SNMP v3", "ok": True, "detail": "test-system"}]
    monkeypatch.setattr(console.m, "test_device_connection", tested)
    return calls


def test_manual_edit_reuses_own_saved_passwords_when_hidden_refs_are_not_submitted(console, monkeypatch):
    m = console.m
    _vault(m)
    m.vault.set_secret("old-ssh", username="ssh-old", password="ssh-secret")
    m.vault.set_secret("old-snmp", snmp_user="snmp-old", snmp_auth_proto="sha256",
                       snmp_auth_pass="auth-secret", snmp_priv_proto="aes", snmp_priv_pass="priv-secret")
    _device(m, "fw", "192.0.2.10", snmp_version="v3", secret_ref="old-ssh", snmp_ref="old-snmp")
    calls = _capture(console, monkeypatch)
    before = m.vault.list_secrets()
    code, result, body = _post(console, orig_name="fw", ssh_username="ssh-new", snmp_user="snmp-new",
                               ssh_password="", snmp_auth_pass="", snmp_priv_pass="")
    assert code == 200 and result["results"][0]["ok"]
    values = calls[0][1]
    assert values["ssh"]["username"] == "ssh-new" and values["ssh"]["password"] == "ssh-secret"
    assert values["snmp"]["snmp_user"] == "snmp-new" and values["snmp"]["snmp_auth_pass"] == "auth-secret"
    assert values["snmp"]["snmp_priv_pass"] == "priv-secret"
    assert m.vault.list_secrets() == before
    assert m.vault.get_secret("old-snmp")["snmp_user"] == "snmp-old"
    assert not any(secret in body for secret in ("ssh-secret", "auth-secret", "priv-secret"))


def test_manual_test_uses_new_fields_and_preserves_password_whitespace(console, monkeypatch):
    _vault(console.m)
    console.m.vault.set_secret("old", snmp_user="old", snmp_auth_proto="sha1", snmp_auth_pass="old-pass")
    calls = _capture(console, monkeypatch)
    code, _, body = _post(console, snmp_ref="old", snmp_user=" new ", snmp_auth_proto="sha256",
                          snmp_auth_pass="  new-auth  ", snmp_priv_proto="aes", snmp_priv_pass=" new-priv ")
    assert code == 200
    values = calls[0][1]["snmp"]
    assert values["snmp_user"] == "new" and values["snmp_auth_proto"] == "sha256"
    assert values["snmp_auth_pass"] == "  new-auth  " and values["snmp_priv_pass"] == " new-priv "
    assert console.m.vault.get_secret("old")["snmp_auth_pass"] == "old-pass"
    assert "new-auth" not in body and "new-priv" not in body


def test_saved_mode_ignores_forged_manual_fields(console, monkeypatch):
    _vault(console.m)
    saved = {"snmp_user": "saved-user", "snmp_auth_proto": "sha256", "snmp_auth_pass": "saved-auth"}
    console.m.vault.set_secret("saved-snmp", **saved)
    calls = _capture(console, monkeypatch)
    code, _, _ = _post(console, cred_mode="saved", snmp_ref="saved-snmp", snmp_user="forged",
                        snmp_auth_pass="forged", ssh_username="forged", ssh_password="forged")
    assert code == 200
    assert calls[0][1]["snmp"] == {**saved, "version": "v3"}
    assert calls[0][1]["ssh"] is None


def test_v2c_manual_community_override_is_used_instead_of_selected_old_secret(console, monkeypatch):
    _vault(console.m)
    console.m.vault.set_secret("old-v2", community="old-community")
    calls = _capture(console, monkeypatch)
    code, _, body = _post(console, snmp_version="v2c", snmp_ref="old-v2", community=" new-community ")
    assert code == 200
    assert calls[0][1]["snmp"]["version"] == "v2c"
    assert calls[0][1]["snmp"]["community"] == " new-community "
    assert console.m.vault.get_secret("old-v2")["community"] == "old-community"
    assert "new-community" not in body and "old-community" not in body


@pytest.mark.parametrize("fields", [{"cred_mode": "saved"}, {"cred_mode": "invalid"}])
def test_bad_secret_selection_is_rejected_before_a_connection(console, monkeypatch, fields):
    calls = _capture(console, monkeypatch)
    code, result, _ = _post(console, **fields)
    assert code == 400 and "error" in result
    assert calls == []


def test_incomplete_v3_connection_test_returns_useful_error_before_network_io(console, monkeypatch):
    sent = []
    def no_send(*args, **kwargs):
        sent.append(args)
        raise AssertionError("incomplete credentials must not send")
    monkeypatch.setattr(snmp, "_udp_exchange", no_send)
    code, result, body = _post(console, snmp_user="reader", snmp_auth_proto="sha256")
    assert code == 200 and result["results"][0]["ok"] is False
    assert "authentication password is missing" in result["results"][0]["detail"]
    assert "NoneType" not in body and sent == []


def test_regular_poll_reports_same_missing_password_without_sending(console, monkeypatch):
    m = console.m
    _vault(m)
    m.vault.set_secret("incomplete", snmp_user="reader", snmp_auth_proto="sha256")
    _device(m, "fw", "192.0.2.10", snmp_version="v3", snmp_ref="incomplete")
    sent = []
    monkeypatch.setattr(snmp, "_udp_exchange", lambda *a, **kw: sent.append(a))
    result = m.snmp_poll("fw")
    assert result["ok"] is False and "authentication password is missing" in result["error"]
    assert sent == []
