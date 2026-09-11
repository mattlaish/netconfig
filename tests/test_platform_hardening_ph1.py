import http.client
import re
import threading
from pathlib import Path

from netconfig.manager import Manager
from netconfig.security import security_headers
from netconfig.web import Console, _Server
from netconfig.web_ui import apply_csp_nonce


def test_enforced_csp_uses_nonce_and_blocks_script_attributes():
    headers = dict(security_headers(tls=False, csp_nonce="abc123"))
    csp = headers["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-abc123'" in csp
    assert "script-src-attr 'none'" in csp
    script_part = csp.split("script-src ", 1)[1].split(";", 1)[0]
    assert "unsafe-inline" not in script_part
    assert "style-src 'self' 'nonce-abc123'" in csp
    assert "style-src-attr 'none'" in csp


def test_nonce_injection_marks_every_inline_script():
    doc = '<html><script>one()</script><script type="application/json">{}</script></html>'
    out = apply_csp_nonce(doc, "nonce-value")
    assert out.count('nonce="nonce-value"') == 2
    assert '<script>one()' not in out


def test_login_response_nonce_matches_csp_and_has_no_inline_event_handlers(tmp_path):
    manager = Manager(str(tmp_path / "home"))
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        conn.request("GET", "/login")
        response = conn.getresponse()
        body = response.read().decode("utf-8")
        assert response.status == 200
        csp = response.getheader("Content-Security-Policy")
        nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
        scripts = re.findall(r"<script\b[^>]*>", body, flags=re.I)
        assert scripts
        assert all(f'nonce="{nonce}"' in tag for tag in scripts)
        assert not re.search(r"\son(?:click|submit|change|input|load|error)=", body, flags=re.I)
        assert not re.search(r'\sstyle="', body, flags=re.I)
        assert all(f'nonce="{nonce}"' in tag for tag in re.findall(r'<style\b[^>]*>', body, flags=re.I))
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        manager.close()


def test_graph_device_name_is_escaped_before_script_context():
    class Inv:
        def get_samples(self, device, since=0):
            return {}

    class ManagerStub:
        settings = {"snmp_poll_interval": 0, "snmp_history_seconds": 1800, "if_history_hours": 24}
        inv = Inv()
        def _history_backend(self):
            return None

    handler = object.__new__(Console)
    handler.manager = ManagerStub()
    hostile = '</script><script>alert("x")</script>'
    body = handler._live_graph(hostile)
    assert hostile not in body
    assert "\\u003c/script\\u003e" in body


def test_web_console_structural_split_gate():
    root = Path(__file__).resolve().parents[1]
    web = root / "opt/netconfig/netconfig/web.py"
    api = root / "opt/netconfig/netconfig/web_api.py"
    ui = root / "opt/netconfig/netconfig/web_ui.py"
    assert api.exists() and ui.exists()
    assert len(web.read_text(encoding="utf-8").splitlines()) < 4000
    assert web.stat().st_size < 240_000
    assert "class WebApiMixin" in api.read_text(encoding="utf-8")
    assert "def apply_csp_nonce" in ui.read_text(encoding="utf-8")


def test_web_source_has_no_html_inline_event_attributes():
    root = Path(__file__).resolve().parents[1]
    source = (root / "opt/netconfig/netconfig/web.py").read_text(encoding="utf-8")
    assert not re.search(r"on(?:click|submit|change|input|load|error)=", source, flags=re.I)
