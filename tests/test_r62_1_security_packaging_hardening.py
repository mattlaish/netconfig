from __future__ import annotations

import http.server
import ssl
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from netconfig.structured_protocols import _restconf_opener
from netconfig.transport import SSHTransport


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_EXECUTABLES = (
    "usr/bin/netconfig",
    "packaging/build-rpm.sh",
    "packaging/install-rpm.sh",
    "packaging/inspect-rpm.sh",
    "packaging/q1-qualify-almalinux.sh",
    "packaging/q1-qualify-postgres.sh",
    "packaging/q1-source-gates.sh",
    "packaging/q2-qualify.sh",
    "packaging/q2-source-gates.sh",
    "packaging/r60-qualify.sh",
    "packaging/r60-lifecycle-upgrade.sh",
    "packaging/r61-qualify.sh",
    "packaging/r62-qualify.sh",
    "packaging/r63-qualify.sh",
    "packaging/r64-qualify.sh",
    "qualification/q2_runner.py",
    "qualification/r60_runner.py",
    "qualification/r61_runner.py",
    "qualification/r61_benchmark.py",
    "qualification/r62_runner.py",
    "qualification/r63_runner.py",
    "qualification/r64_runner.py",
    "qualification/run_bounded_regression.py",
    "packaging/smoke-installed.sh",
    "tools/rpm-builder/build.sh",
    "tools/rpm-builder/verify.sh",
    "tools/rpm-builder/rpm_builder.py",
    "tools/rpm-builder/verify_rpm.py",
)


def test_restconf_opener_refuses_redirect_before_second_request():
    hits = {"start": 0, "target": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            return

        def do_GET(self):
            if self.path == "/start":
                hits["start"] += 1
                self.send_response(302)
                self.send_header(
                    "Location", f"http://127.0.0.1:{self.server.server_port}/metadata"
                )
                self.end_headers()
                return
            if self.path == "/metadata":
                hits["target"] += 1
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"should-not-be-fetched")
                return
            self.send_response(404)
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        opener = _restconf_opener(ssl.create_default_context())
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/start", method="GET"
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            opener.open(request, timeout=2)
        assert exc.value.code == 302
        assert hits == {"start": 1, "target": 0}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_ssh_target_is_after_double_dash_for_cli_and_subsystem():
    cli = SSHTransport("-oProxyCommand=evil", "-operator")
    argv = cli._build_argv()
    target = "-operator@-oProxyCommand=evil"
    assert argv[-2:] == ["--", target]

    netconf = SSHTransport(
        "-oProxyCommand=evil", "-operator", subsystem="netconf"
    )
    argv = netconf._build_argv()
    assert argv[-4:] == ["-s", "--", target, "netconf"]


def test_mode_fix_patch_covers_every_required_executable():
    patch = (ROOT / "UPSTREAM_GIT_MODE_FIX.patch").read_text(encoding="utf-8")
    for relative in REQUIRED_EXECUTABLES:
        section = f"diff --git a/{relative} b/{relative}\nold mode 100644\nnew mode 100755\n"
        assert section in patch, relative
        assert (ROOT / relative).stat().st_mode & 0o777 == 0o755


def test_reviewed_dead_code_is_removed():
    manager = (ROOT / "opt/netconfig/netconfig/manager.py").read_text(encoding="utf-8")
    web = (ROOT / "opt/netconfig/netconfig/web.py").read_text(encoding="utf-8")
    cli = (ROOT / "opt/netconfig/netconfig/cli.py").read_text(encoding="utf-8")
    assert "previous_facts = self.inv.get_facts" not in manager
    assert "_TOPOLOGY_JS" not in web
    assert 'print(f"  v2c community: (hidden)")' not in cli


def test_r62_1_hotfix_history_is_preserved_under_r64():
    spec = (ROOT / "packaging/netconfig.spec").read_text(encoding="utf-8")
    road = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "Release:        67.2%{?dist}" in spec
    assert "2.0.0-62.1" in spec
    assert "R64" in road and "IMPLEMENTED_TESTING_DEFERRED" in road
