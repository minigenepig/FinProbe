# -*- coding: utf-8 -*-
"""MCP server entry.

Prefer official FastMCP if installed. Otherwise speak MCP JSON-RPC over stdio
with Content-Length framing (same as the official SDK).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import TOOL_SCHEMAS, dispatch

try:
    from mcp.server.fastmcp import FastMCP

    HAS_FASTMCP = True
except ImportError:
    HAS_FASTMCP = False


def build_fastmcp() -> Any:
    from tools import (
        approval_query,
        artifact_get,
        financial_analysis,
        gr_query,
        invoice_query,
        payment_query,
        po_query,
        policy_query,
        vendor_query,
    )

    mcp = FastMCP("finprobe-erp")
    mcp.tool(name="vendor-query", title="VendorQueryTool")(vendor_query)
    mcp.tool(name="po-query", title="PurchaseOrderQueryTool")(po_query)
    mcp.tool(name="gr-query", title="GoodsReceiptQueryTool")(gr_query)
    mcp.tool(name="invoice-query", title="InvoiceQueryTool")(invoice_query)
    mcp.tool(name="payment-query", title="PaymentQueryTool")(payment_query)
    mcp.tool(name="approval-query", title="ApprovalQueryTool")(approval_query)
    mcp.tool(name="policy-query", title="PolicyQueryTool")(policy_query)
    mcp.tool(name="financial-analysis", title="FinancialAnalysisTool")(financial_analysis)
    mcp.tool(name="artifact-get", title="ArtifactGetTool")(artifact_get)
    return mcp


def _rpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_rpc(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    req_id = message.get("id")
    params = message.get("params") or {}
    if method == "initialize":
        return _rpc_result(
            req_id,
            {
                "protocolVersion": params.get("protocolVersion") or "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "finprobe-erp", "version": "1.0.0"},
            },
        )
    if method == "notifications/initialized" or method is None or req_id is None:
        return None
    if method in {"tools/list", "tools/listChanged"}:
        return _rpc_result(req_id, {"tools": TOOL_SCHEMAS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        text = dispatch(name, args)
        return _rpc_result(req_id, {"content": [{"type": "text", "text": text}]})
    if method == "ping":
        return _rpc_result(req_id, {})
    return _rpc_error(req_id, -32601, f"method not found: {method}")


def _read_stdio() -> dict[str, Any] | None:
    raw_in = sys.stdin.buffer
    first = raw_in.readline()
    if not first:
        return None
    if first.lstrip().startswith(b"{"):
        return json.loads(first.decode("utf-8"))
    headers: dict[str, str] = {}
    line = first
    while line not in (b"\r\n", b"\n"):
        if b":" in line:
            key, value = line.decode("utf-8").split(":", 1)
            headers[key.strip().lower()] = value.strip()
        line = raw_in.readline()
        if not line:
            return None
    length = int(headers.get("content-length") or 0)
    body = raw_in.read(length)
    return json.loads(body.decode("utf-8"))


def _write_stdio(message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


def run_stdio() -> None:
    sys.stderr.write("finprobe MCP stdio server\n")
    while True:
        try:
            message = _read_stdio()
        except json.JSONDecodeError:
            continue
        if message is None:
            break
        reply = handle_rpc(message)
        if reply is not None:
            _write_stdio(reply)


if __name__ == "__main__":
    if HAS_FASTMCP:
        build_fastmcp().run()
    else:
        run_stdio()
