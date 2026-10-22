# -*- coding: utf-8 -*-
"""Unified MCP client.

v1 talks to the in-process `mcp-server.tools.dispatch`.
Agent code must only depend on this interface so a future stdio / official
MCP client can replace LocalDispatchMCPClient without rewriting agents.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import REPO_ROOT, Settings, get_settings

TOOL_NAMES = (
    "vendor-query",
    "po-query",
    "gr-query",
    "invoice-query",
    "payment-query",
    "approval-query",
    "policy-query",
    "financial-analysis",
    "artifact-get",
)

QUERY_TOOLS = TOOL_NAMES[:7]

TOOL_LABELS = {
    "vendor-query": "查供应商档案",
    "po-query": "查采购订单",
    "gr-query": "查入库单",
    "invoice-query": "查发票",
    "payment-query": "查付款单",
    "approval-query": "查审批记录",
    "policy-query": "查制度条款",
    "financial-analysis": "汇总计算",
    "artifact-get": "抽查明细",
}

_TARGET_KEYS = (
    "supplierId",
    "poId",
    "grId",
    "invoiceId",
    "paymentId",
    "purchaseOrderId",
    "businessId",
    "taxNo",
    "keyword",
    "docId",
    "artifactId",
)


def tool_label(name: str) -> str:
    return TOOL_LABELS.get(name, name)


def args_target(args: dict[str, Any] | None) -> str:
    items = []
    for key in _TARGET_KEYS:
        value = (args or {}).get(key)
        if value in (None, "", [], {}):
            continue
        items.append(f"{key}={value}")
    arts = (args or {}).get("artifactIds")
    if isinstance(arts, list) and arts:
        items.append(f"明细{len(arts)}份")
    if (args or {}).get("clusterWindowDays"):
        items.append("5日拆单窗口")
    if (args or {}).get("code") and not items:
        items.append("统计脚本")
    return "，".join(items[:4])


def _human_error(error: str | None) -> str:
    text = error or "调用失败"
    if "禁止语法: Try" in text or "Try" in text and "禁止" in text:
        return "统计脚本用了 try/except，沙箱现已支持；请改用 if 判断或重试。"
    if "isinstance" in text:
        return "统计脚本用了 isinstance，沙箱现已支持，请重试。"
    if "禁止名称: type" in text or "禁止语法: Import" in text:
        return "统计脚本不能使用 import 或 type()，请改用 to_number / isinstance。"
    if "NoneType" in text:
        return "未拿到明细（records 为空），需要带上 artifactIds 再计算。"
    return text.split("失败: ", 1)[-1][:180]


def observe_result(tool: str, ok: bool, arguments: dict[str, Any], payload: dict[str, Any], total_count: int | None, artifact_id: str | None, error: str | None) -> str:
    if not ok:
        return _human_error(error)
    if tool == "financial-analysis":
        result = payload.get("result")
        if isinstance(result, dict) and result:
            keys = "、".join(str(k) for k in list(result.keys())[:6])
            return f"计算完成，得到 {keys}"
        return "计算完成"
    if tool == "artifact-get":
        rows = payload.get("data") or payload.get("records") or []
        n = len(rows) if isinstance(rows, list) else 0
        return f"抽查了 {n} 条明细" if n else "未抽到明细"
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    bits: list[str] = []
    if total_count == 0:
        bits.append("未检索到记录")
    elif total_count is not None:
        bits.append(f"共 {total_count} 条")
    if artifact_id:
        bits.append("已收成摘要，未展开原文")
    if summary.get("duplicateTaxNo"):
        bits.append("发现重复税号")
    if summary.get("duplicatePhones"):
        bits.append("发现重复电话")
    if summary.get("duplicateBankAccounts"):
        bits.append("发现重复账号")
    rates = summary.get("taxRateCounts")
    if isinstance(rates, dict) and rates:
        bits.append("税率 " + " / ".join(f"{k}:{v}" for k, v in list(rates.items())[:4]))
    if summary.get("nearThresholdCount"):
        bits.append(f"近红线 {summary['nearThresholdCount']} 笔")
    if summary.get("duplicateCodeNoCount"):
        bits.append("疑似重复发票号")
    if summary.get("invoiceIdsWithMultiplePaid"):
        bits.append("同一发票多笔已付")
    if summary.get("pendingCount"):
        bits.append(f"待审 {summary['pendingCount']} 笔")
    return "，".join(bits) if bits else "已返回结果"


@dataclass
class MCPResult:
    ok: bool
    tool: str
    arguments: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict)
    raw: str = ""
    total_count: int | None = None
    artifact_id: str | None = None
    summary: dict[str, Any] | None = None
    error: str | None = None

    def to_query_record(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": self.arguments,
            "ok": self.ok,
            "totalCount": self.total_count,
            "artifactId": self.artifact_id,
            "error": self.error,
        }

    def public_event(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "ok": self.ok,
            "totalCount": self.total_count,
            "artifactId": self.artifact_id,
            "error": self.error,
            "label": tool_label(self.tool),
            "target": args_target(self.arguments),
            "observation": observe_result(
                self.tool,
                self.ok,
                self.arguments,
                self.payload,
                self.total_count,
                self.artifact_id,
                self.error,
            ),
        }

    def compact_for_llm(self, limit: int = 8000) -> str:
        payload = dict(self.payload)
        data = payload.get("data")
        if isinstance(data, list) and len(data) > 8:
            payload["data"] = data[:5]
            payload["dataOmitted"] = len(data) - 5
        raw = json.dumps(payload, ensure_ascii=False)
        if len(raw) > limit:
            payload.pop("data", None)
            payload.pop("sample", None)
            payload["truncated"] = True
            raw = json.dumps(payload, ensure_ascii=False)[:limit]
        return raw


def schemas_to_openai(schemas: list[dict[str, Any]], allowed: list[str] | None = None) -> list[dict[str, Any]]:
    allow = set(allowed or TOOL_NAMES)
    out: list[dict[str, Any]] = []
    for schema in schemas:
        name = schema.get("name")
        if name not in allow:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema.get("description") or name,
                    "parameters": schema.get("inputSchema") or {"type": "object", "properties": {}},
                },
            }
        )
    return out


def ensure_mcp_path() -> Path:
    mcp_dir = REPO_ROOT / "mcp-server"
    path = str(mcp_dir)
    if path not in sys.path:
        sys.path.insert(0, path)
    return mcp_dir


class MCPClient(ABC):
    @abstractmethod
    def list_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> MCPResult:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError

    def openai_tools(self, allowed: list[str] | None = None) -> list[dict[str, Any]]:
        return schemas_to_openai(self.list_tools(), allowed)


class LocalDispatchMCPClient(MCPClient):
    """In-process adapter over mcp-server/tools.py `dispatch`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._lock = threading.Lock()
        self._tools = None

    def _load(self):
        with self._lock:
            if self._tools is not None:
                return
            os.environ.setdefault("ERP_BASE_URL", self.settings.erp_base_url)
            os.environ.setdefault("ERP_API_KEY", self.settings.erp_api_key)
            ensure_mcp_path()
            import tools as mcp_tools  # type: ignore

            self._tools = mcp_tools

    def list_tools(self) -> list[dict[str, Any]]:
        self._load()
        return list(self._tools.TOOL_SCHEMAS)

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> MCPResult:
        self._load()
        args = arguments or {}
        raw = self._tools.dispatch(name, args)
        try:
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except json.JSONDecodeError:
            return MCPResult(ok=False, tool=name, arguments=args, raw=str(raw), error="MCP 返回非 JSON")
        ok = bool(payload.get("ok", False))
        artifact = payload.get("artifact") or {}
        artifact_id = None
        if isinstance(artifact, dict):
            artifact_id = artifact.get("artifactId") or artifact.get("id")
        artifact_id = artifact_id or payload.get("artifactId")
        error = None
        if not ok:
            err = payload.get("error")
            error = err if isinstance(err, str) else json.dumps(err, ensure_ascii=False)
        return MCPResult(
            ok=ok,
            tool=name,
            arguments=args,
            payload=payload,
            raw=raw if isinstance(raw, str) else json.dumps(payload, ensure_ascii=False),
            total_count=payload.get("totalCount"),
            artifact_id=artifact_id,
            summary=payload.get("summary") if isinstance(payload.get("summary"), dict) else None,
            error=error,
        )

    def health(self) -> dict[str, Any]:
        try:
            schemas = self.list_tools()
            names = [s.get("name") for s in schemas]
            missing = [n for n in TOOL_NAMES if n not in names]
            if missing:
                return {"ok": False, "tools": names, "error": f"缺少工具: {missing}"}
            return {"ok": True, "tools": names, "transport": "local-dispatch"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "tools": [], "error": str(exc), "transport": "local-dispatch"}


class StdioMCPClient(MCPClient):
    """Reserved for a future official MCP client. Do not call from Agent layer."""

    def list_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError("Stdio MCP client is not enabled in v1")

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> MCPResult:
        raise NotImplementedError("Stdio MCP client is not enabled in v1")

    def health(self) -> dict[str, Any]:
        return {"ok": False, "error": "stdio MCP client not implemented"}