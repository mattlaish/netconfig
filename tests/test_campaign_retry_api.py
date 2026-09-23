import http.client
import json
import threading

from netconfig.apitokens import ApiTokens
from netconfig.manager import Manager
from netconfig.web import Console, _Server


def _request(server, token, payload):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    body = json.dumps(payload)
    conn.request(
        "POST",
        "/api/v1/campaigns/42/retry",
        body=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    response = conn.getresponse()
    raw = response.read().decode()
    status = response.status
    data = json.loads(raw or "null")
    conn.close()
    return status, data


def test_campaign_retry_rest_route_uses_form_wave_and_calls_service(tmp_path, monkeypatch):
    manager = Manager(str(tmp_path / "home"))
    token = ApiTokens(manager.db.conn).create(
        "campaign-operator",
        {"campaign:write"},
        created_by="test",
        role="operator",
    )[1]
    calls = []

    def retry_failed(campaign_id, actor, wave=None):
        calls.append((campaign_id, actor, wave))
        return {"id": campaign_id, "state": "PAUSED", "retried_wave": wave}

    monkeypatch.setattr(manager.campaigns, "retry_failed", retry_failed)
    Console.manager = manager
    Console.tls_enabled = False
    server = _Server(("127.0.0.1", 0), Console)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, data = _request(server, token, {"wave": 3})
        assert status == 200
        assert data["retried_wave"] == 3
        assert calls == [(42, "api:campaign-operator", 3)]

        status, data = _request(server, token, {})
        assert status == 200
        assert data["retried_wave"] is None
        assert calls[-1] == (42, "api:campaign-operator", None)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        manager.close()
