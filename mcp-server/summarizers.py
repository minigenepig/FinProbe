# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _top(counter: Counter, n: int = 5) -> dict[str, int]:
    return {str(k): int(v) for k, v in counter.most_common(n)}


def summarize_vendors(rows: list[dict[str, Any]]) -> dict[str, Any]:
    missing = Counter()
    tax = Counter()
    phone = Counter()
    account = Counter()
    cats = Counter()
    for v in rows:
        cats[_blank(v.get("category"))] += 1
        for field in ("taxNo", "bankAccount", "contactPhone", "name"):
            if not v.get(field):
                missing[field] += 1
        tax[_blank(v.get("taxNo"))] += 1
        phone[_blank(v.get("contactPhone"))] += 1
        account[_blank(v.get("bankAccount"))] += 1
    dup_tax = [k for k, n in tax.items() if k != "" and n > 1]
    dup_phone = [k for k, n in phone.items() if k != "" and n > 1]
    dup_account = [k for k, n in account.items() if k != "" and n > 1]
    return {
        "count": len(rows),
        "categoryCounts": dict(cats),
        "missingFieldCounts": dict(missing),
        "duplicateTaxNo": dup_tax,
        "duplicatePhones": dup_phone,
        "duplicateBankAccounts": dup_account,
        "inactiveCount": sum(1 for v in rows if v.get("active") is False),
    }


def summarize_pos(rows: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = [_num(r.get("totalWithTax")) for r in rows]
    dates = [str(r.get("orderDate") or "") for r in rows if r.get("orderDate")]
    return {
        "count": len(rows),
        "amountSum": round(sum(amounts), 2),
        "amountMin": round(min(amounts), 2) if amounts else 0,
        "amountMax": round(max(amounts), 2) if amounts else 0,
        "dateRange": [min(dates), max(dates)] if dates else None,
        "statusCounts": dict(Counter(str(r.get("status")) for r in rows)),
        "taxRateCounts": dict(Counter(str(r.get("taxRate")) for r in rows)),
        "supplierCountsTop": _top(Counter(str((r.get("supplier") or {}).get("supplierId")) for r in rows)),
        "nearThresholdCount": sum(1 for a in amounts if 450000 <= a < 500000),
        "overThresholdCount": sum(1 for a in amounts if a >= 500000),
    }


def summarize_grs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dates = [str(r.get("receivedDate") or "") for r in rows if r.get("receivedDate")]
    qty = 0.0
    for r in rows:
        for line in r.get("lines") or []:
            qty += _num(line.get("receivedQuantity"))
    return {
        "count": len(rows),
        "poIdDistinct": len({r.get("poId") for r in rows}),
        "qtySum": qty,
        "dateRange": [min(dates), max(dates)] if dates else None,
        "statusCounts": dict(Counter(str(r.get("status")) for r in rows)),
        "inspectionCounts": dict(Counter(str(r.get("inspection_status")) for r in rows)),
        "receivedByCounts": dict(Counter(str(r.get("receivedBy")) for r in rows)),
        "missingPoIdCount": sum(1 for r in rows if not r.get("poId")),
    }


def summarize_invoices(rows: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = [_num(r.get("total")) for r in rows]
    dates = [str(r.get("invoice_date") or "") for r in rows if r.get("invoice_date")]
    pair = Counter((str(r.get("invoiceCode")), str(r.get("invoiceNo"))) for r in rows)
    code_only = Counter(str(r.get("invoiceCode")) for r in rows)
    return {
        "count": len(rows),
        "amountSum": round(sum(amounts), 2),
        "dateRange": [min(dates), max(dates)] if dates else None,
        "statusCounts": dict(Counter(str(r.get("status")) for r in rows)),
        "taxRateCounts": dict(Counter(str(r.get("taxRate")) for r in rows)),
        "supplierCountsTop": _top(Counter(str((r.get("supplier") or {}).get("supplierId")) for r in rows)),
        "duplicateCodeNoCount": sum(1 for _, n in pair.items() if n > 1),
        "duplicateInvoiceCodeCount": sum(1 for _, n in code_only.items() if n > 1),
        "missingPoIdCount": sum(1 for r in rows if not r.get("purchaseOrderId")),
    }


def summarize_payments(rows: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = [_num(r.get("paymentAmount")) for r in rows]
    dates = [str(r.get("paymentDate") or "") for r in rows if r.get("paymentDate")]
    by_inv = defaultdict(list)
    by_po = defaultdict(list)
    for r in rows:
        if r.get("invoiceId"):
            by_inv[r["invoiceId"]].append(r)
        if r.get("poId"):
            by_po[r["poId"]].append(r)
    multi_inv = {k: len(v) for k, v in by_inv.items() if len(v) > 1}
    paid_multi = {
        k: len(v)
        for k, v in by_inv.items()
        if sum(1 for x in v if x.get("status") == "PAID") >= 2
    }
    return {
        "count": len(rows),
        "amountSum": round(sum(amounts), 2),
        "dateRange": [min(dates), max(dates)] if dates else None,
        "statusCounts": dict(Counter(str(r.get("status")) for r in rows)),
        "distinctPayeeAccounts": len({str((r.get("payeeInfo") or {}).get("payeeAccountNo")) for r in rows}),
        "invoiceIdsWithMultiplePayments": len(multi_inv),
        "invoiceIdsWithMultiplePaid": len(paid_multi),
        "sampleMultiInvoiceIds": list(multi_inv.keys())[:5],
    }


def summarize_approvals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "statusCounts": dict(Counter(str(r.get("approvalStatus")) for r in rows)),
        "businessTypeCounts": dict(Counter(str(r.get("businessType")) for r in rows)),
        "pendingCount": sum(1 for r in rows if r.get("approvalStatus") == "PENDING"),
        "rejectedCount": sum(1 for r in rows if r.get("approvalStatus") == "REJECTED"),
    }


def summarize_policies(rows: list[dict[str, Any]], keyword: str | None = None) -> dict[str, Any]:
    hits = []
    for doc in rows:
        snippets = []
        if keyword:
            snippets = _snippets(doc.get("content") or "", keyword)
        hits.append(
            {
                "docId": doc.get("docId"),
                "title": doc.get("title"),
                "fileName": doc.get("fileName"),
                "charCount": len(doc.get("content") or ""),
                "snippets": snippets[:3],
            }
        )
    return {"count": len(rows), "docs": hits}


def cluster_pos_by_supplier(rows: list[dict[str, Any]], window_days: int = 5) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        sid = str((r.get("supplier") or {}).get("supplierId") or "")
        if sid and r.get("orderDate"):
            groups[sid].append(r)
    clusters = []
    for sid, items in groups.items():
        items = sorted(items, key=lambda x: str(x.get("orderDate")))
        i = 0
        while i < len(items):
            j = i
            while j + 1 < len(items):
                d1 = datetime.strptime(items[i]["orderDate"][:10], "%Y-%m-%d")
                d2 = datetime.strptime(items[j + 1]["orderDate"][:10], "%Y-%m-%d")
                if (d2 - d1).days <= window_days:
                    j += 1
                else:
                    break
            if j > i:
                chunk = items[i : j + 1]
                total = round(sum(_num(x.get("totalWithTax")) for x in chunk), 2)
                clusters.append(
                    {
                        "supplierId": sid,
                        "size": len(chunk),
                        "dateFrom": chunk[0]["orderDate"],
                        "dateTo": chunk[-1]["orderDate"],
                        "amountSum": total,
                        "poIds": [x.get("poId") for x in chunk],
                        "itemCodes": sorted({(x.get("items") or [{}])[0].get("itemCode") for x in chunk if x.get("items")}),
                    }
                )
            i = j + 1
    clusters.sort(key=lambda x: (-x["size"], -x["amountSum"]))
    return {"windowDays": window_days, "clusterCount": len(clusters), "clustersTop": clusters[:10]}


def _blank(value: Any) -> str:
    return "" if value is None else str(value)


def _snippets(text: str, keyword: str, radius: int = 80) -> list[str]:
    low = text.lower()
    key = keyword.lower()
    snippets = []
    start = 0
    while True:
        idx = low.find(key, start)
        if idx < 0:
            break
        left = max(idx - radius, 0)
        right = min(idx + len(keyword) + radius, len(text))
        snippets.append(text[left:right].replace("\n", " "))
        start = idx + len(keyword)
        if len(snippets) >= 5:
            break
    return snippets
