# -*- coding: utf-8 -*-
from src.backend.app.errors import error_body


def test_error_body_shape():
    body = error_body("ERP_UNAVAILABLE", "无法连接 mock-erp", True)
    assert body == {
        "ok": False,
        "error": {"code": "ERP_UNAVAILABLE", "message": "无法连接 mock-erp", "retryable": True},
    }