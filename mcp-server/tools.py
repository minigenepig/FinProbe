# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any, Callable

from artifacts import ArtifactStore
from erp_client import ErpClient, ErpError
from sandbox import SandboxError, execute_financial_analysis
from settings import INLINE_LIMIT, SAMPLE_SIZE, VENDOR_INLINE_LIMIT
from summarizers import (
    cluster_pos_by_supplier,
    summarize_approvals,
    summarize_grs,
    summarize_invoices,
    summarize_payments,
    summarize_policies,
    summarize_pos,
    summarize_vendors,
)

erp = ErpClient()
artifacts = ArtifactStore()


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2)


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != ""}


def pack_list(
    *,
    tool: str,
    query: dict[str, Any],
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    inline_limit: int | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    limit = INLINE_LIMIT if inline_limit is None else inline_limit
    sample_n = min(SAMPLE_SIZE, len(rows))
    artifact_meta = None
    if len(rows) > limit:
        artifact_meta = artifacts.save(rows, tool, query)
        returned = rows[:sample_n]
        hint = [
            "完整结果已写入 artifact，不要要求工具直接返回全量明细。",
            "需要统计请调用 financial-analysis，并传入 artifactIds。",
            "需要再看若干条请调用 artifact-get。",
        ]
        payload = {
            "tool": tool,
            "query": query,
            "totalCount": len(rows),
            "returnedCount": len(returned),
            "summary": summary,
            "sample": returned,
            "artifact": artifact_meta,
            "nextActions": hint,
        }
    else:
        payload = {
            "tool": tool,
            "query": query,
            "totalCount": len(rows),
            "returnedCount": len(rows),
            "summary": summary,
            "data": rows,
            "nextActions": ["结果集较小，已内联返回全部记录。"],
        }
    if extra:
        payload.update(extra)
    return _ok(payload)


def vendor_query(
    supplierId: str | None = None,
    code: str | None = None,
    name: str | None = None,
    taxNo: str | None = None,
    bankAccount: str | None = None,
    contactPhone: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    active: str | None = None,
) -> str:
    query = _clean(locals())
    try:
        if supplierId and not any([code, name, taxNo, bankAccount, contactPhone, category, keyword, active]):
            rec = erp.get(f"/v1/vendors/{supplierId}")
            return _ok({"tool": "vendor-query", "totalCount": 1, "data": [rec]})
        rows = erp.fetch_all("/v1/vendors", query)
        return pack_list(tool="vendor-query", query=query, rows=rows, summary=summarize_vendors(rows), inline_limit=VENDOR_INLINE_LIMIT)
    except ErpError as exc:
        return _err(str(exc))


def po_query(
    poId: str | None = None,
    poNo: str | None = None,
    supplierId: str | None = None,
    status: str | None = None,
    itemCode: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    minAmount: float | None = None,
    maxAmount: float | None = None,
    keyword: str | None = None,
    clusterWindowDays: int | None = None,
) -> str:
    query = _clean({k: v for k, v in locals().items() if k != "clusterWindowDays"})
    extra_query = dict(query)
    try:
        if poId and not any([poNo, supplierId, status, itemCode, dateFrom, dateTo, minAmount, maxAmount, keyword]):
            rec = erp.get(f"/v1/purchase-orders/{poId}")
            return _ok({"tool": "po-query", "totalCount": 1, "data": [rec]})
        rows = erp.fetch_all("/v1/purchase-orders", query)
        extra = {}
        if clusterWindowDays:
            extra["splitClusters"] = cluster_pos_by_supplier(rows, window_days=int(clusterWindowDays))
            extra_query["clusterWindowDays"] = clusterWindowDays
        return pack_list(tool="po-query", query=extra_query, rows=rows, summary=summarize_pos(rows), extra=extra or None)
    except ErpError as exc:
        return _err(str(exc))


def gr_query(
    grId: str | None = None,
    poId: str | None = None,
    supplierId: str | None = None,
    receivedBy: str | None = None,
    status: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    keyword: str | None = None,
) -> str:
    query = _clean(locals())
    try:
        if grId and not any([poId, supplierId, receivedBy, status, dateFrom, dateTo, keyword]):
            rec = erp.get(f"/v1/goods-receipts/{grId}")
            return _ok({"tool": "gr-query", "totalCount": 1, "data": [rec]})
        rows = erp.fetch_all("/v1/goods-receipts", query)
        return pack_list(tool="gr-query", query=query, rows=rows, summary=summarize_grs(rows))
    except ErpError as exc:
        return _err(str(exc))


def invoice_query(
    invoiceId: str | None = None,
    purchaseOrderId: str | None = None,
    poId: str | None = None,
    supplierId: str | None = None,
    invoiceCode: str | None = None,
    invoiceNo: str | None = None,
    status: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    keyword: str | None = None,
) -> str:
    query = _clean(locals())
    try:
        if invoiceId and not any([purchaseOrderId, poId, supplierId, invoiceCode, invoiceNo, status, dateFrom, dateTo, keyword]):
            rec = erp.get(f"/v1/invoices/{invoiceId}")
            return _ok({"tool": "invoice-query", "totalCount": 1, "data": [rec]})
        rows = erp.fetch_all("/v1/invoices", query)
        return pack_list(tool="invoice-query", query=query, rows=rows, summary=summarize_invoices(rows))
    except ErpError as exc:
        return _err(str(exc))


def payment_query(
    paymentId: str | None = None,
    invoiceId: str | None = None,
    poId: str | None = None,
    status: str | None = None,
    payeeAccountNo: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
    keyword: str | None = None,
) -> str:
    query = _clean(locals())
    try:
        if paymentId and not any([invoiceId, poId, status, payeeAccountNo, dateFrom, dateTo, keyword]):
            rec = erp.get(f"/v1/payments/{paymentId}")
            return _ok({"tool": "payment-query", "totalCount": 1, "data": [rec]})
        rows = erp.fetch_all("/v1/payments", query)
        return pack_list(tool="payment-query", query=query, rows=rows, summary=summarize_payments(rows))
    except ErpError as exc:
        return _err(str(exc))


def approval_query(
    approvalId: str | None = None,
    businessType: str | None = None,
    businessId: str | None = None,
    approvalStatus: str | None = None,
    keyword: str | None = None,
) -> str:
    query = _clean(locals())
    try:
        if approvalId and not any([businessType, businessId, approvalStatus, keyword]):
            rec = erp.get(f"/v1/approvals/{approvalId}")
            return _ok({"tool": "approval-query", "totalCount": 1, "data": [rec]})
        rows = erp.fetch_all("/v1/approvals", query)
        return pack_list(tool="approval-query", query=query, rows=rows, summary=summarize_approvals(rows))
    except ErpError as exc:
        return _err(str(exc))


def policy_query(docId: str | None = None, keyword: str | None = None) -> str:
    query = _clean(locals())
    try:
        if docId and not keyword:
            rec = erp.get(f"/v1/policies/{docId}")
            content = rec.get("content") or ""
            compact = dict(rec)
            compact["contentPreview"] = content[:1200]
            compact.pop("content", None)
            compact["charCount"] = len(content)
            artifact = artifacts.save([{"docId": rec.get("docId"), "title": rec.get("title"), "content": content}], "policy-query", query)
            return _ok({"tool": "policy-query", "totalCount": 1, "data": [compact], "artifact": artifact})
        metas = erp.fetch_all("/v1/policies", query)
        full_rows = []
        for meta in metas:
            did = meta.get("docId")
            if did:
                full_rows.append(erp.get(f"/v1/policies/{did}"))
        if not full_rows:
            return _ok({"tool": "policy-query", "query": query, "totalCount": 0, "summary": {"count": 0, "docs": []}, "data": []})
        summary = summarize_policies(full_rows, keyword=keyword)
        artifact = artifacts.save(full_rows, "policy-query", query)
        return _ok(
            {
                "tool": "policy-query",
                "query": query,
                "totalCount": len(full_rows),
                "summary": summary,
                "data": summary["docs"],
                "artifact": artifact,
                "nextActions": ["制度全文在 artifact 中。回答问题时引用条款原文，不要编造条文。"],
            }
        )
    except ErpError as exc:
        return _err(str(exc))


def financial_analysis(code: str, artifactIds: list[str] | None = None, context: dict[str, Any] | None = None) -> str:
    try:
        datasets: dict[str, Any] = {}
        loaded_meta = []
        for art_id in artifactIds or []:
            payload = artifacts.load(art_id)
            datasets[art_id] = payload.get("records") or []
            loaded_meta.append({"artifactId": art_id, "recordCount": payload.get("recordCount")})
        result = execute_financial_analysis(code, context=context, datasets=datasets)
        return _ok({"tool": "financial-analysis", "artifacts": loaded_meta, "result": result})
    except (SandboxError, FileNotFoundError, SyntaxError, Exception) as exc:
        return _err(f"financial-analysis 失败: {type(exc).__name__}: {exc}")


def artifact_get(artifactId: str, offset: int = 0, limit: int = 5, ids: list[str] | None = None, idField: str | None = None) -> str:
    try:
        payload = artifacts.slice(artifactId, offset=offset, limit=limit, ids=ids, id_field=idField)
        return _ok({"tool": "artifact-get", **payload})
    except FileNotFoundError as exc:
        return _err(str(exc))


TOOL_IMPLS: dict[str, Callable[..., str]] = {
    "vendor-query": vendor_query,
    "po-query": po_query,
    "gr-query": gr_query,
    "invoice-query": invoice_query,
    "payment-query": payment_query,
    "approval-query": approval_query,
    "policy-query": policy_query,
    "financial-analysis": financial_analysis,
    "artifact-get": artifact_get,
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "vendor-query",
        "description": "查询供应商主数据。可用 supplierId 精确查询，或按税号/账号/电话/名称检索。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "supplierId": {"type": "string"},
                "code": {"type": "string"},
                "name": {"type": "string"},
                "taxNo": {"type": "string"},
                "bankAccount": {"type": "string"},
                "contactPhone": {"type": "string"},
                "category": {"type": "string"},
                "keyword": {"type": "string"},
                "active": {"type": "string"},
            },
        },
    },
    {
        "name": "po-query",
        "description": "查询采购订单。列表返回摘要+样例+artifact；clusterWindowDays 可生成拆单聚类。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "poId": {"type": "string"},
                "poNo": {"type": "string"},
                "supplierId": {"type": "string"},
                "status": {"type": "string"},
                "itemCode": {"type": "string"},
                "dateFrom": {"type": "string"},
                "dateTo": {"type": "string"},
                "minAmount": {"type": "number"},
                "maxAmount": {"type": "number"},
                "keyword": {"type": "string"},
                "clusterWindowDays": {"type": "integer"},
            },
        },
    },
    {
        "name": "gr-query",
        "description": "查询入库单。单张用 poId/grId；供应商全量用 supplierId 一次拉取（大结果走 artifact），禁止按 PO 循环。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "grId": {"type": "string"},
                "poId": {"type": "string"},
                "supplierId": {"type": "string"},
                "receivedBy": {"type": "string"},
                "status": {"type": "string"},
                "dateFrom": {"type": "string"},
                "dateTo": {"type": "string"},
                "keyword": {"type": "string"},
            },
        },
    },
    {
        "name": "invoice-query",
        "description": "查询发票。全量发票不会直接返回，只给 summary/sample/artifact。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "invoiceId": {"type": "string"},
                "purchaseOrderId": {"type": "string"},
                "poId": {"type": "string"},
                "supplierId": {"type": "string"},
                "invoiceCode": {"type": "string"},
                "invoiceNo": {"type": "string"},
                "status": {"type": "string"},
                "dateFrom": {"type": "string"},
                "dateTo": {"type": "string"},
                "keyword": {"type": "string"},
            },
        },
    },
    {
        "name": "payment-query",
        "description": "查询付款单。summary 会标出同一发票多笔付款。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "paymentId": {"type": "string"},
                "invoiceId": {"type": "string"},
                "poId": {"type": "string"},
                "status": {"type": "string"},
                "payeeAccountNo": {"type": "string"},
                "dateFrom": {"type": "string"},
                "dateTo": {"type": "string"},
                "keyword": {"type": "string"},
            },
        },
    },
    {
        "name": "approval-query",
        "description": "查询审批流，用于消解检查。未调用不得声称没有审批。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "approvalId": {"type": "string"},
                "businessType": {"type": "string"},
                "businessId": {"type": "string"},
                "approvalStatus": {"type": "string"},
                "keyword": {"type": "string"},
            },
        },
    },
    {
        "name": "policy-query",
        "description": "查询企业制度，返回命中片段；全文写入 artifact。",
        "inputSchema": {
            "type": "object",
            "properties": {"docId": {"type": "string"}, "keyword": {"type": "string"}},
        },
    },
    {
        "name": "financial-analysis",
        "description": "沙箱执行 Python 统计。必须赋值 result=...。允许 try/except 与 isinstance。禁止 import、type()、getattr、下划线属性。金额/税率先 to_number。用 artifactIds 把大结果注入 records；多个 artifact 会合并进 records。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "artifactIds": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "object"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "artifact-get",
        "description": "按需读取 artifact 中的若干条记录，默认最多 5 条。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifactId": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "ids": {"type": "array", "items": {"type": "string"}},
                "idField": {"type": "string"},
            },
            "required": ["artifactId"],
        },
    },
]


def dispatch(name: str, arguments: dict[str, Any] | None) -> str:
    fn = TOOL_IMPLS.get(name)
    if not fn:
        return _err(f"unknown tool: {name}")
    return fn(**(arguments or {}))
