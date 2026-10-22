# -*- coding: utf-8 -*-
from src.backend.app.healthcheck import probe_erp


def test_probe_erp_down_does_not_pretend_ok():
    result = probe_erp("http://127.0.0.1:9", timeout=0.3)
    assert result["ok"] is False
    assert "error" in result
    assert result["ok"] is not True