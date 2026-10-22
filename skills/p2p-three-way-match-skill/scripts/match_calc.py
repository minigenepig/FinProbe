# -*- coding: utf-8 -*-
"""Deterministic three-way match calculator. Input: JSON with po/gr/invoice objects or an artifact file."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _qty(doc: dict[str, Any], kind: str) -> float:
    if kind == "po":
        items = doc.get("items") or []
        return _num(items[0].get("quantity")) if items else 0.0
    if kind == "gr":
        lines = doc.get("lines") or []
        return _num(lines[0].get("receivedQuantity")) if lines else 0.0
    items = doc.get("items") or []
    return _num(items[0].get("invoiced_quantity")) if items else 0.0


def _price(doc: dict[str, Any], kind: str) -> float:
    if kind == "gr":
        return 0.0
    items = doc.get("items") or []
    key = "unitPrice" if kind == "po" else "unit_price"
    return _num(items[0].get(key)) if items else 0.0


def match_calc(po: dict[str, Any] | None, gr: dict[str, Any] | None, inv: dict[str, Any] | None) -> dict[str, Any]:
    if not po:
        return {"riskLevel": "证据不足", "reason": "缺少 PO"}
    if not gr or not inv:
        missing = []
        if not gr:
            missing.append("GR")
        if not inv:
            missing.append("Invoice")
        return {"riskLevel": "证据不足", "reason": "缺少 " + "/".join(missing), "poId": po.get("poId")}

    po_qty, gr_qty, inv_qty = _qty(po, "po"), _qty(gr, "gr"), _qty(inv, "invoice")
    po_price, inv_price = _price(po, "po"), _price(inv, "invoice")
    tax_rate = _num(inv.get("taxRate") if inv.get("taxRate") is not None else po.get("taxRate"))
    po_total = _num(po.get("totalWithTax"))
    inv_total = _num(inv.get("total"))
    received_value = round(gr_qty * po_price * (1 + tax_rate), 2)
    qty_base = gr_qty if gr_qty else po_qty
    qty_diff = inv_qty - gr_qty
    qty_pct = (qty_diff / qty_base * 100) if qty_base else None
    amount_diff = round(inv_total - received_value, 2)

    if qty_pct is not None and qty_pct > 10 + 1e-9 or amount_diff > 10000 + 1e-9:
        level = "高风险"
    elif (qty_pct is not None and qty_pct > 2 + 1e-9) or amount_diff > 1000 + 1e-9:
        level = "中风险"
    else:
        level = "低风险"

    return {
        "poId": po.get("poId"),
        "grId": gr.get("grId"),
        "invoiceId": inv.get("invoiceId"),
        "poQty": po_qty,
        "grQty": gr_qty,
        "invoiceQty": inv_qty,
        "qtyDiff": qty_diff,
        "qtyDiffPct": None if qty_pct is None else round(qty_pct, 2),
        "poUnitPrice": po_price,
        "invoiceUnitPrice": inv_price,
        "poTotalWithTax": po_total,
        "invoiceTotal": inv_total,
        "receivedValue": received_value,
        "overAmount": amount_diff,
        "poTaxRate": po.get("taxRate"),
        "invoiceTaxRate": inv.get("taxRate"),
        "invoiceDate": inv.get("invoice_date"),
        "receivedDate": gr.get("receivedDate"),
        "ruleRiskLevel": level,
        "note": "若存在已完成的分批收货/补货/调价审批，应将 ruleRiskLevel 消解为低风险。",
    }


def main() -> None:
    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read())
    po = raw.get("po") or raw.get("purchaseOrder")
    gr = raw.get("gr") or raw.get("goodsReceipt")
    inv = raw.get("invoice")
    print(json.dumps(match_calc(po, gr, inv), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
