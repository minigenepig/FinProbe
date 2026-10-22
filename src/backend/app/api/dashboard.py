# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi import APIRouter, Request

from ..errors import AppError
from ..erp_gateway import ErpGateway
from ..gold import load_supplier_risk_board

router = APIRouter()


def _num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _month(value: Any) -> str:
    text = str(value or "")
    return text[:7] if len(text) >= 7 else "未知"


def _supplier_id(row: dict[str, Any]) -> str:
    nested = row.get("supplier") if isinstance(row.get("supplier"), dict) else {}
    return str(nested.get("supplierId") or row.get("supplierId") or "")


def _empty_erp() -> dict[str, Any]:
    return {
        "erpOk": False,
        "erpError": None,
        "counts": {
            "vendors": 0,
            "purchaseOrders": 0,
            "goodsReceipts": 0,
            "invoices": 0,
            "payments": 0,
            "approvals": 0,
            "policies": 0,
        },
        "kpis": {
            "vendorCount": 0,
            "activeVendorCount": 0,
            "inactiveVendorCount": 0,
            "poCount": 0,
            "grCount": 0,
            "invoiceCount": 0,
            "paymentCount": 0,
            "approvalCount": 0,
            "policyCount": 0,
            "poAmountSum": 0,
            "invoiceAmountSum": 0,
            "paymentAmountSum": 0,
            "personalPayeeHint": 0,
            "duplicatePhoneGroups": 0,
            "pendingApprovalCount": 0,
            "amountGapInvoiceMinusPo": 0,
        },
        "vendorByCategory": {},
        "poByStatus": {},
        "paymentByStatus": {},
        "approvalByStatus": {},
        "invoiceByTaxRate": {},
        "poAmountByMonth": {},
        "invoiceAmountByMonth": {},
        "paymentAmountByMonth": {},
        "poAmountByCategory": {},
        "topSuppliersByPoAmount": [],
        "duplicatePhones": [],
        "personalPayees": [],
        "recentInvestigations": [],
    }


def _looks_personal(name: str) -> bool:
    if not name:
        return False
    skip = ("公司", "厂", "中心", "集团", "银行", "股份", "有限")
    return 2 <= len(name) <= 4 and not any(token in name for token in skip)


def _build_erp_stats(gw: ErpGateway, store: Any) -> dict[str, Any]:
    names = [
        "vendors",
        "purchase-orders",
        "goods-receipts",
        "invoices",
        "payments",
        "approvals",
        "policies",
    ]
    with ThreadPoolExecutor(max_workers=7) as pool:
        fetched = {name: pool.submit(gw.fetch_all, name) for name in names}
        data = {name: fetched[name].result() for name in names}

    vendors = data["vendors"]
    pos = data["purchase-orders"]
    grs = data["goods-receipts"]
    invoices = data["invoices"]
    payments = data["payments"]
    approvals = data["approvals"]
    policies = data["policies"]

    vendor_cat = Counter(str(v.get("category") or "未知") for v in vendors)
    po_status = Counter(str(p.get("status") or "未知") for p in pos)
    pay_status = Counter(str(p.get("status") or "未知") for p in payments)
    appr_status = Counter(str(a.get("approvalStatus") or "未知") for a in approvals)
    tax_rates = Counter(str(inv.get("taxRate") if inv.get("taxRate") is not None else "未知") for inv in invoices)

    po_month: dict[str, float] = defaultdict(float)
    inv_month: dict[str, float] = defaultdict(float)
    pay_month: dict[str, float] = defaultdict(float)
    po_by_vendor: dict[str, float] = defaultdict(float)
    po_by_category: dict[str, float] = defaultdict(float)
    po_total = 0.0
    vendor_category = {str(v.get("id")): str(v.get("category") or "未知") for v in vendors}

    for p in pos:
        amt = _num(p.get("totalWithTax"))
        po_total += amt
        po_month[_month(p.get("orderDate"))] += amt
        sid = _supplier_id(p)
        if sid:
            po_by_vendor[sid] += amt
            po_by_category[vendor_category.get(sid, "未知")] += amt

    inv_total = 0.0
    for inv in invoices:
        amt = _num(inv.get("total"))
        inv_total += amt
        inv_month[_month(inv.get("invoice_date") or inv.get("invoiceDate"))] += amt

    pay_total = 0.0
    personal_rows: list[dict[str, Any]] = []
    for p in payments:
        amt = _num(p.get("paymentAmount"))
        pay_total += amt
        pay_month[_month(p.get("paymentDate"))] += amt
        payee = p.get("payeeInfo") if isinstance(p.get("payeeInfo"), dict) else {}
        name = str(payee.get("payeeName") or "")
        if _looks_personal(name):
            personal_rows.append(
                {
                    "paymentId": p.get("paymentId"),
                    "invoiceId": p.get("invoiceId"),
                    "payeeName": name,
                    "amount": round(amt, 2),
                }
            )

    phones: dict[str, list[str]] = defaultdict(list)
    for v in vendors:
        phone = str(v.get("contactPhone") or "").strip()
        vid = str(v.get("id") or "")
        if phone and vid:
            phones[phone].append(vid)
    duplicate_phones = [
        {"phone": phone, "supplierIds": ids, "count": len(ids)}
        for phone, ids in phones.items()
        if len(ids) > 1
    ]
    duplicate_phones.sort(key=lambda row: (-row["count"], row["phone"]))

    top_vendors = sorted(po_by_vendor.items(), key=lambda kv: kv[1], reverse=True)[:10]
    name_by_id = {str(v.get("id")): str(v.get("name") or v.get("id")) for v in vendors}
    active = sum(1 for v in vendors if v.get("active") is True or str(v.get("active")).lower() == "true")
    pending_appr = sum(1 for a in approvals if str(a.get("approvalStatus") or "").upper() == "PENDING")

    health = {}
    try:
        health = gw.health_counts()
    except AppError:
        health = {}
    counts = health.get("counts") if isinstance(health.get("counts"), dict) else {}

    recent = []
    if store is not None:
        recent = store.list_recent(20)

    return {
        "erpOk": True,
        "erpError": None,
        "counts": {
            "vendors": int(counts.get("vendors") or len(vendors)),
            "purchaseOrders": int(counts.get("purchaseOrders") or len(pos)),
            "goodsReceipts": int(counts.get("goodsReceipts") or len(grs)),
            "invoices": int(counts.get("invoices") or len(invoices)),
            "payments": int(counts.get("payments") or len(payments)),
            "approvals": int(counts.get("approvals") or len(approvals)),
            "policies": int(counts.get("policies") or len(policies)),
        },
        "kpis": {
            "vendorCount": len(vendors),
            "activeVendorCount": active,
            "inactiveVendorCount": max(0, len(vendors) - active),
            "poCount": len(pos),
            "grCount": len(grs),
            "invoiceCount": len(invoices),
            "paymentCount": len(payments),
            "approvalCount": len(approvals),
            "policyCount": len(policies),
            "poAmountSum": round(po_total, 2),
            "invoiceAmountSum": round(inv_total, 2),
            "paymentAmountSum": round(pay_total, 2),
            "personalPayeeHint": len(personal_rows),
            "duplicatePhoneGroups": len(duplicate_phones),
            "pendingApprovalCount": pending_appr,
            "amountGapInvoiceMinusPo": round(inv_total - po_total, 2),
        },
        "vendorByCategory": dict(vendor_cat),
        "poByStatus": dict(po_status),
        "paymentByStatus": dict(pay_status),
        "approvalByStatus": dict(appr_status),
        "invoiceByTaxRate": dict(tax_rates),
        "poAmountByMonth": dict(sorted(po_month.items())),
        "invoiceAmountByMonth": dict(sorted(inv_month.items())),
        "paymentAmountByMonth": dict(sorted(pay_month.items())),
        "poAmountByCategory": {key: round(val, 2) for key, val in po_by_category.items()},
        "topSuppliersByPoAmount": [
            {"supplierId": sid, "name": name_by_id.get(sid, sid), "amount": round(amt, 2)}
            for sid, amt in top_vendors
        ],
        "duplicatePhones": duplicate_phones[:20],
        "personalPayees": personal_rows[:20],
        "recentInvestigations": recent,
    }


@router.get("/v1/dashboard/supplier-risks")
def supplier_risks():
    board = load_supplier_risk_board()
    return {"ok": True, **board}


@router.get("/v1/dashboard/summary")
def dashboard_summary(request: Request):
    board = load_supplier_risk_board()
    payload = _empty_erp()
    store = getattr(request.app.state, "store", None)
    if store is not None:
        payload["recentInvestigations"] = store.list_recent(20)
    try:
        gw = getattr(request.app.state, "erp", None) or ErpGateway(request.app.state.settings)
        request.app.state.erp = gw
        gw.health_counts()
        payload = _build_erp_stats(gw, store)
    except AppError as exc:
        payload["erpOk"] = False
        payload["erpError"] = exc.message
        if store is not None:
            payload["recentInvestigations"] = store.list_recent(20)
    except Exception as exc:  # pragma: no cover - defensive
        payload["erpOk"] = False
        payload["erpError"] = str(exc)

    return {"ok": True, **payload, "supplierRisks": board}
