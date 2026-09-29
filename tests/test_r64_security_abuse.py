from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from netconfig import oauth, web
from netconfig.apitokens import ApiTokens
from netconfig.change_planning import TopologyChangePlanningService
from netconfig.evidence_signing import (
    EvidenceSigningError,
    MAX_ARCHIVE_MEMBERS,
    verify_signed_archive,
)
from netconfig.manager import Manager
from netconfig.security import LoginThrottle

ROOT = Path(__file__).resolve().parents[1]


class Headers(dict):
    def get_all(self, name):
        value = super().get(name)
        if value is None:
            return None
        return value if isinstance(value, list) else [value]

    def get(self, name, default=None):
        value = super().get(name, default)
        if isinstance(value, list):
            return value[-1]
        return value


class NoRead(io.BytesIO):
    def read(self, *args, **kwargs):
        raise AssertionError("body must be rejected before reading")


def _console(manager=None, *, headers=None, body=b""):
    handler = web.Console.__new__(web.Console)
    handler.manager = manager
    handler.headers = Headers(headers or {})
    handler.rfile = io.BytesIO(body)
    handler._responded = False
    handler.command = "POST"
    handler.path = "/test"
    handler.client_address = ("127.0.0.1", 12345)
    return handler


def test_r64_login_throttle_cardinality_is_bounded():
    throttle = LoginThrottle(max_keys=32, window_seconds=3600)
    for idx in range(200):
        throttle.failure("192.0.2.10", f"user-{idx}", now=1000 + idx)
    assert throttle.tracked_keys() <= 32
    # A retry check for a never-failed identity must not allocate a new key.
    before = throttle.tracked_keys()
    assert throttle.retry_after("192.0.2.10", "never-seen", now=2000) == 0
    assert throttle.tracked_keys() == before


def test_r64_managed_session_idle_and_absolute_expiry(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    try:
        m.users.create("alice", "CorrectHorseBatteryStaple", role="admin")
        user = m.users.get("alice")
        web._SESSIONS.clear()
        token, record = web._create_managed_session(user, now=100.0)
        assert record["absolute_expires"] == 100.0 + web.SESSION_ABSOLUTE_SECONDS
        h = _console(m, headers={"Cookie": f"ncsid={token}"})
        monkeypatch.setattr(web.time, "time", lambda: 101.0)
        assert h._session()[1]["username"] == "alice"
        monkeypatch.setattr(web.time, "time", lambda: 101.0 + web.SESSION_IDLE_SECONDS + 1)
        assert h._session() == (None, None)
        assert token not in web._SESSIONS
    finally:
        web._SESSIONS.clear()
        m.close()


def test_r64_session_revalidates_role_disable_and_password_reset(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    try:
        m.users.create("alice", "one-long-password", role="admin")
        web._SESSIONS.clear()
        token, _ = web._create_managed_session(m.users.get("alice"), now=100.0)
        h = _console(m, headers={"Cookie": f"ncsid={token}"})
        monkeypatch.setattr(web.time, "time", lambda: 101.0)
        m.users.set_role("alice", "viewer")
        assert h._session()[1]["role"] == "viewer"
        m.users.set_password("alice", "another-long-password")
        assert h._session() == (None, None)

        token, _ = web._create_managed_session(m.users.get("alice"), now=102.0)
        h.headers = Headers({"Cookie": f"ncsid={token}"})
        monkeypatch.setattr(web.time, "time", lambda: 103.0)
        m.users.set_disabled("alice", True)
        assert h._session() == (None, None)
    finally:
        web._SESSIONS.clear()
        m.close()


def test_r64_session_cardinality_limits_per_user_and_global():
    user = {"username": "alice", "role": "viewer", "pw_hash": b"x" * 32}
    web._SESSIONS.clear()
    try:
        for idx in range(web.MAX_SESSIONS_PER_USER + 5):
            web._create_managed_session(user, now=float(idx + 1))
        mine = [x for x in web._SESSIONS.values() if x.get("username") == "alice"]
        assert len(mine) == web.MAX_SESSIONS_PER_USER

        for idx in range(web.MAX_CONSOLE_SESSIONS + 20):
            other = {"username": f"u{idx}", "role": "viewer", "pw_hash": bytes(str(idx), "ascii")}
            web._create_managed_session(other, now=1000.0 + idx)
        managed = [x for x in web._SESSIONS.values() if "last_seen" in x]
        assert len(managed) <= web.MAX_CONSOLE_SESSIONS
    finally:
        web._SESSIONS.clear()


def test_r64_oversized_form_rejected_before_body_read():
    h = _console(headers={"Content-Length": str(web.MAX_FORM_BODY_BYTES + 1)})
    h.rfile = NoRead()
    with pytest.raises(web.RequestRejected) as exc:
        h._read_post()
    assert exc.value.status == 413


def test_r64_transfer_encoding_and_ambiguous_content_length_fail_closed():
    h = _console(headers={"Transfer-Encoding": "chunked", "Content-Length": "5"})
    with pytest.raises(web.RequestRejected, match="Transfer-Encoding"):
        h._read_post()
    h = _console(headers={"Content-Length": ["5", "5"]})
    with pytest.raises(web.RequestRejected, match="ambiguous"):
        h._read_post()


def test_r64_mib_multipart_budget_enforced_before_body_read():
    h = _console(headers={
        "Content-Type": "multipart/form-data; boundary=x",
        "Content-Length": str(web.MAX_MIB_UPLOAD_BODY_BYTES + 1),
    })
    h.rfile = NoRead()
    with pytest.raises(web.RequestRejected) as exc:
        h._read_multipart()
    assert exc.value.status == 413


def test_r64_server_error_does_not_reflect_exception_secret(capsys):
    h = _console()
    captured = {}
    h._send = lambda body, status=200, ctype="text/html; charset=utf-8", headers=None: captured.update(
        body=body, status=status
    )
    try:
        raise RuntimeError("database password=hunter2 at /var/lib/netconfig/private.db")
    except RuntimeError:
        h._server_error()
    assert captured["status"] == 500
    assert "hunter2" not in captured["body"]
    assert "/var/lib/netconfig" not in captured["body"]
    assert "Reference ID" in captured["body"]
    # Full detail remains server-side for operator correlation.
    assert "hunter2" in capsys.readouterr().err


def test_r64_oauth_authority_and_tenant_are_not_general_url_inputs():
    good = {"o365_tenant": "contoso.onmicrosoft.com", "o365_authority": oauth.PUBLIC_CLOUD_AUTHORITY}
    assert oauth.token_endpoint(good).startswith("https://login.microsoftonline.com/contoso.onmicrosoft.com/")
    for bad in (
        "http://login.microsoftonline.com",
        "https://169.254.169.254",
        "https://login.microsoftonline.com.evil.example",
    ):
        with pytest.raises(ValueError, match="authority"):
            oauth.token_endpoint({**good, "o365_authority": bad})
    for bad_tenant in ("../metadata", "tenant/path", "tenant?x=1", "https://evil.example"):
        with pytest.raises(ValueError, match="tenant"):
            oauth.token_endpoint({**good, "o365_tenant": bad_tenant})


def test_r64_oauth_redirect_handler_refuses_second_request():
    seen = {"start": 0, "target": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/start":
                seen["start"] += 1
                self.send_response(302)
                self.send_header("Location", "/target")
                self.end_headers()
            else:
                seen["target"] += 1
                self.send_response(200)
                self.end_headers()
        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/start")
        with pytest.raises(urllib.error.HTTPError) as exc:
            oauth._oauth_opener().open(req, timeout=2)
        assert exc.value.code == 302
        assert seen == {"start": 1, "target": 0}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_r64_oauth_response_size_is_bounded():
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, n=-1):
            return b"x" * (oauth.MAX_OAUTH_RESPONSE_BYTES + 1)
    settings = {
        "o365_tenant": "contoso.onmicrosoft.com",
        "o365_client_id": "client",
        "o365_scope": oauth.DEFAULT_SCOPE,
        "o365_authority": oauth.PUBLIC_CLOUD_AUTHORITY,
    }
    token, err = oauth.get_token(settings, "secret", use_cache=False, _opener=lambda *_a, **_k: Response())
    assert token is None and "1 MiB" in err


def test_r64_signed_archive_rejects_special_file_types(tmp_path):
    archive = tmp_path / "fifo.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        info = tarfile.TarInfo("root/pipe")
        info.type = tarfile.FIFOTYPE
        tar.addfile(info)
    with pytest.raises(EvidenceSigningError, match="regular files/directories"):
        verify_signed_archive(archive)


def test_r64_signed_archive_member_budget_stops_iteration_early(monkeypatch, tmp_path):
    class FakeTar:
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def __iter__(self):
            for idx in range(MAX_ARCHIVE_MEMBERS + 1):
                info = tarfile.TarInfo(f"root/d{idx}")
                info.type = tarfile.DIRTYPE
                yield info
    monkeypatch.setattr("netconfig.evidence_signing.tarfile.open", lambda *_a, **_k: FakeTar())
    archive = tmp_path / "present.tar.gz"
    archive.write_bytes(b"placeholder")
    with pytest.raises(EvidenceSigningError, match="too many members"):
        verify_signed_archive(archive)


def test_r64_api_token_scope_role_and_revocation_boundary(tmp_path):
    m = Manager(str(tmp_path / "home"))
    try:
        tokens = ApiTokens(m.db.conn)
        with pytest.raises(ValueError, match="requires role admin"):
            tokens.create("bad-admin", ["external:manage"], role="operator")
        token_id, raw = tokens.create("reader", ["inventory:read"], role="viewer")
        assert tokens.verify(raw)["role"] == "viewer"
        tokens.revoke(token_id)
        assert tokens.verify(raw) is None
    finally:
        m.close()


def test_r64_mc11_proposals_reject_arbitrary_execution_fields():
    base = {
        "kind": "structured_change", "device": "fw1", "resource": "interface_enabled",
        "selectors": {"interface": "Gi0/1"}, "value": True,
    }
    assert TopologyChangePlanningService._normalize_proposal(base)["resource"] == "interface_enabled"
    for field in ("command", "shell", "netconf_rpc", "restconf_url", "gnmi_request", "approved"):
        with pytest.raises(ValueError, match="unsupported fields"):
            TopologyChangePlanningService._normalize_proposal({**base, field: "evil"})
    with pytest.raises(ValueError, match="selector values must be scalar"):
        TopologyChangePlanningService._normalize_proposal({**base, "selectors": {"interface": {"command": "reload"}}})


def test_r64_mc11_what_if_is_non_execution_even_with_candidate(tmp_path, monkeypatch):
    m = Manager(str(tmp_path / "home"))
    try:
        for name, host in (("r1", "192.0.2.1"), ("r2", "192.0.2.2")):
            m.inv.upsert(name=name, host=host, platform="generic", device_type="network", enabled=True)
        plan = m.change_planning.plan(
            source="r1", destination="r2", vrf="default",
            destination_prefix="203.0.113.2/32", source_prefix="203.0.113.1/32", actor="abuse-test")
        called = []
        monkeypatch.setattr(m.structured_changes, "execute_resource", lambda **_kw: called.append(True))
        candidate = {
            "kind": "structured_change", "device": "r1", "resource": "interface_enabled",
            "selectors": {"interface": "Gi0/1"}, "value": False,
        }
        out = m.change_planning.what_if(plan["id"], [candidate], actor="abuse-test")
        assert out["network_write"] is False
        assert out["persisted_evidence_mutated"] is False
        assert called == []
    finally:
        m.close()


def test_r64_release_track_does_not_create_mc12_or_new_execution_authority():
    road = (ROOT / "ROADMAP.md").read_text().lower()
    planning = (ROOT / "opt/netconfig/netconfig/change_planning.py").read_text().lower()
    structured = (ROOT / "opt/netconfig/netconfig/structured_changes.py").read_text().lower()
    assert "do not create mc-12" in road
    assert '"network_write": false' in planning
    assert "never accepts arbitrary" in structured


def test_r64_runner_historical_baseline_detects_release65_drift(tmp_path):
    out = tmp_path / "evidence"
    cp = subprocess.run(
        [sys.executable, str(ROOT / "qualification/r64_runner.py"), "--output-dir", str(out),
         "--include-local", "--gate", "R64-BASE-001"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 1, cp.stdout + cp.stderr
    campaign = json.loads((out / "campaign.json").read_text())
    assert campaign["product_baseline"] == "2.0.0-64"
    assert campaign["gates"][0]["status"] == "FAIL"
    assert campaign["production_security_claim"] is False
    assert campaign["live_abuse_pass_count"] == 0
    assert campaign["release_promotion_performed"] is False


def test_r64_live_gate_without_assessor_lab_is_blocked_not_false_pass(tmp_path):
    out = tmp_path / "live"
    cp = subprocess.run(
        [sys.executable, str(ROOT / "qualification/r64_runner.py"), "--output-dir", str(out),
         "--live", "--gate", "R64-ABUSE-012"],
        cwd=ROOT, text=True, capture_output=True,
    )
    assert cp.returncode == 0, cp.stdout + cp.stderr
    row = json.loads((out / "campaign.json").read_text())["gates"][0]
    assert row["status"] in {"BLOCKED_ENVIRONMENT", "NOT_RUN"}


def test_r64_runner_fixed_hooks_redaction_and_no_arbitrary_command():
    source = (ROOT / "qualification/r64_runner.py").read_text()
    assert "--command" not in source
    assert "shell=True" not in source
    assert "LIVE_ABUSE" in source
    assert "independent-abuse-signoff" in source
    import importlib.util
    spec = importlib.util.spec_from_file_location("r64_runner_historical", ROOT / "qualification/r64_runner.py")
    r64_runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = r64_runner
    spec.loader.exec_module(r64_runner)
    redacted = r64_runner.redact("Bearer abc token=xyz password:secret")
    assert "abc" not in redacted and "xyz" not in redacted and "secret" not in redacted


def test_r64_package_authority_and_modes():
    spec = (ROOT / "packaging/netconfig.spec").read_text()
    installer = (ROOT / "packaging/install-rpm.sh").read_text()
    road = (ROOT / "ROADMAP.md").read_text().lower()
    assert "Release:        67.2%{?dist}" in spec
    assert '${RELEASE%%.*} != "67"' in installer
    assert "do not create mc-12" in road
    for relative in ("qualification/r64_runner.py", "packaging/r64-qualify.sh"):
        assert (ROOT / relative).stat().st_mode & 0o777 == 0o755
