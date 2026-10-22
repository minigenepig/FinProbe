# -*- coding: utf-8 -*-
from unittest.mock import patch

from src.backend.app.errors import error_body


def test_error_body_shape():
    body = error_body("ERP_UNAVAILABLE", "无法连接 mock-erp", True)
    assert body == {
        "ok": False,
        "error": {"code": "ERP_UNAVAILABLE", "message": "无法连接 mock-erp", "retryable": True},
    }


def test_create_and_get_investigation(api_client):
    resp = api_client.post("/v1/investigations", json={"question": "PO-01332 三单是否匹配？"})
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    inv = data["investigation"]
    assert inv["id"].startswith("INVST-")
    assert inv["status"] == "created"
    assert inv["wantReport"] is True
    for key in ("mode", "scope", "subject", "agents", "skills", "envelopes", "followUpRound"):
        assert key in inv
    got = api_client.get(f"/v1/investigations/{inv['id']}")
    assert got.status_code == 200
    assert got.json()["investigation"]["id"] == inv["id"]
    assert api_client.runner.submitted == [inv["id"]]


def test_policy_question_want_report_false(api_client):
    resp = api_client.post("/v1/investigations", json={"question": "差旅住宿标准是多少？"})
    assert resp.json()["investigation"]["wantReport"] is False


def test_missing_investigation_404(api_client):
    resp = api_client.get("/v1/investigations/INVST-20990101-999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_cancel_and_conflict(api_client):
    created = api_client.post("/v1/investigations", json={"question": "帮我查一下风险"}).json()
    inv_id = created["investigation"]["id"]
    # force awaiting by writing snapshot
    store = api_client.app.state.store
    def mutate(item):
        item.status = "running"
    store.update(inv_id, mutate)
    ok = api_client.post(f"/v1/investigations/{inv_id}/cancel")
    assert ok.status_code == 200
    again = api_client.post(f"/v1/investigations/{inv_id}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "CONFLICT"


def test_message_only_when_awaiting(api_client):
    created = api_client.post("/v1/investigations", json={"question": "帮我查一下风险"}).json()
    inv_id = created["investigation"]["id"]
    bad = api_client.post(f"/v1/investigations/{inv_id}/messages", json={"content": "VEN-0044"})
    assert bad.status_code == 409
    store = api_client.app.state.store
    store.update(inv_id, lambda item: setattr(item, "status", "awaiting_user"))
    good = api_client.post(f"/v1/investigations/{inv_id}/messages", json={"content": "VEN-0044"})
    assert good.status_code == 200
    assert "VEN-0044" in good.json()["investigation"]["question"]


def test_health_erp_down(api_client):
    with patch(
        "src.backend.app.api.health.probe_erp",
        return_value={"ok": False, "baseUrl": "http://127.0.0.1:8081", "error": "无法连接 mock-erp"},
    ):
        resp = api_client.get("/v1/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "ERP_UNAVAILABLE"
    assert body["erp"]["ok"] is False


def test_report_not_found(api_client):
    created = api_client.post("/v1/investigations", json={"question": "PO-01332 三单是否匹配？"}).json()
    resp = api_client.get(f"/v1/investigations/{created['investigation']['id']}/report")
    assert resp.status_code == 404

def test_root_ok(api_client):
    resp = api_client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["health"] == "/v1/health"


def test_list_investigations(api_client):
    api_client.post("/v1/investigations", json={"question": "PO-01332 三单是否匹配？"})
    resp = api_client.get("/v1/investigations")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["investigations"]) >= 1


def test_unknown_erp_resource(api_client):
    resp = api_client.get("/v1/erp/not-a-resource")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION"
