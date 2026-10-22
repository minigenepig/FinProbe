# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..errors import error_body
from ..healthcheck import probe_erp

router = APIRouter()


def _probe_llm(request: Request) -> dict[str, Any]:
    llm = request.app.state.llm
    settings = request.app.state.settings
    info = {
        "ok": bool(llm.configured()),
        "configured": bool(llm.configured()),
        "model": settings.llm_model,
        "baseUrl": settings.llm_base_url,
    }
    if not llm.configured():
        info["error"] = "未配置 FINPROBE_LLM_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY"
    return info


@router.get("/v1/health")
def health(request: Request):
    settings = request.app.state.settings
    erp = probe_erp(settings.erp_base_url)
    mcp = request.app.state.mcp.health()
    if not erp["ok"]:
        mcp = {**mcp, "ok": False, "error": mcp.get("error") or "ERP 不可用，MCP 无法查询"}
    llm = _probe_llm(request)
    body: dict[str, Any] = {"ok": bool(erp["ok"] and mcp.get("ok")), "erp": erp, "mcp": mcp, "llm": llm}
    if not erp["ok"]:
        body.update(error_body("ERP_UNAVAILABLE", erp.get("error") or "无法连接 mock-erp", True))
        return JSONResponse(body, status_code=503)
    if not mcp.get("ok"):
        body.update(error_body("ERP_UNAVAILABLE", mcp.get("error") or "MCP 不可用", True))
        return JSONResponse(body, status_code=503)
    return body