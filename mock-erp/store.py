# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import DATA_DIR


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _first(glob_pat: str) -> Path:
    matches = sorted(DATA_DIR.glob(glob_pat))
    if not matches:
        raise FileNotFoundError(f"ERP data not found: {DATA_DIR / glob_pat}")
    return matches[0]


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _lower(value: Any) -> str:
    return _norm(value).lower()


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _in_range(value: str, date_from: str | None, date_to: str | None) -> bool:
    if not value:
        return not date_from and not date_to
    if date_from and value < date_from:
        return False
    if date_to and value > date_to:
        return False
    return True


def _contains(haystack: Any, needle: str | None) -> bool:
    if not needle:
        return True
    return _lower(needle) in _lower(haystack)


def _eq(value: Any, expected: str | None) -> bool:
    if expected is None or expected == "":
        return True
    return _norm(value) == _norm(expected)


def paginate(rows: list[dict[str, Any]], page: int = 1, page_size: int = 20) -> dict[str, Any]:
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 20), 1), 100)
    total = len(rows)
    start = (page - 1) * page_size
    return {
        "totalCount": total,
        "page": page,
        "pageSize": page_size,
        "data": rows[start : start + page_size],
    }


class ErpStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir or DATA_DIR)
        self.vendors: list[dict[str, Any]] = []
        self.pos: list[dict[str, Any]] = []
        self.grs: list[dict[str, Any]] = []
        self.invoices: list[dict[str, Any]] = []
        self.payments: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self.policies: list[dict[str, Any]] = []
        self._vendor_by_id: dict[str, dict[str, Any]] = {}
        self._po_by_id: dict[str, dict[str, Any]] = {}
        self._gr_by_id: dict[str, dict[str, Any]] = {}
        self._inv_by_id: dict[str, dict[str, Any]] = {}
        self._pay_by_id: dict[str, dict[str, Any]] = {}
        self._app_by_id: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self.vendors = _load_json(_first("供应商主数据*.json"))["data"]
        self.pos = _load_json(_first("PO订单*.json"))["data"]
        self.grs = _load_json(_first("GR入库*.json"))["data"]
        self.invoices = _load_json(_first("Invoice发票*.json"))["data"]
        self.payments = _load_json(_first("付款单*.json"))["data"]
        self.approvals = _load_json(_first("审批单*.json"))["data"]
        self.policies = []
        docs_dir = self.data_dir / "docs"
        if docs_dir.exists():
            for path in sorted(docs_dir.glob("*.txt")):
                text = path.read_text(encoding="utf-8")
                self.policies.append(
                    {
                        "docId": path.stem,
                        "title": path.stem,
                        "fileName": path.name,
                        "content": text,
                    }
                )
        self._vendor_by_id = {v["id"]: v for v in self.vendors if v.get("id")}
        self._po_by_id = {p["poId"]: p for p in self.pos if p.get("poId")}
        self._gr_by_id = {g["grId"]: g for g in self.grs if g.get("grId")}
        self._inv_by_id = {i["invoiceId"]: i for i in self.invoices if i.get("invoiceId")}
        self._pay_by_id = {p["paymentId"]: p for p in self.payments if p.get("paymentId")}
        self._app_by_id = {a["approvalId"]: a for a in self.approvals if a.get("approvalId")}

    def vendor_by_id(self, vendor_id: str) -> dict[str, Any] | None:
        return self._vendor_by_id.get(vendor_id)

    def po_by_id(self, po_id: str) -> dict[str, Any] | None:
        return self._po_by_id.get(po_id)

    def gr_by_id(self, gr_id: str) -> dict[str, Any] | None:
        return self._gr_by_id.get(gr_id)

    def invoice_by_id(self, invoice_id: str) -> dict[str, Any] | None:
        return self._inv_by_id.get(invoice_id)

    def payment_by_id(self, payment_id: str) -> dict[str, Any] | None:
        return self._pay_by_id.get(payment_id)

    def approval_by_id(self, approval_id: str) -> dict[str, Any] | None:
        return self._app_by_id.get(approval_id)

    def policy_by_id(self, doc_id: str) -> dict[str, Any] | None:
        for doc in self.policies:
            if doc["docId"] == doc_id or doc["fileName"] == doc_id:
                return doc
        return None

    def query_vendors(self, **params: Any) -> list[dict[str, Any]]:
        rows = []
        for v in self.vendors:
            if not _eq(v.get("id"), params.get("id") or params.get("supplierId")):
                continue
            if not _eq(v.get("code"), params.get("code")):
                continue
            if not _eq(v.get("taxNo"), params.get("taxNo")):
                continue
            if not _eq(v.get("bankAccount"), params.get("bankAccount")):
                continue
            if not _eq(v.get("contactPhone"), params.get("contactPhone")):
                continue
            if not _eq(v.get("category"), params.get("category")):
                continue
            if params.get("active") not in (None, ""):
                expected = str(params["active"]).lower() in {"1", "true", "yes"}
                if bool(v.get("active")) != expected:
                    continue
            keyword = params.get("keyword") or params.get("name")
            if keyword:
                blob = " ".join(_norm(v.get(k)) for k in ("id", "code", "name", "shortName", "taxNo", "contactName", "bankAccount"))
                if not _contains(blob, keyword):
                    continue
            rows.append(v)
        return rows

    def query_pos(self, **params: Any) -> list[dict[str, Any]]:
        rows = []
        min_amount = _as_float(params.get("minAmount"))
        max_amount = _as_float(params.get("maxAmount"))
        for p in self.pos:
            supplier = p.get("supplier") or {}
            if not _eq(p.get("poId"), params.get("poId")):
                continue
            if not _eq(p.get("poNo"), params.get("poNo")):
                continue
            if not _eq(supplier.get("supplierId"), params.get("supplierId")):
                continue
            if not _eq(p.get("status"), params.get("status")):
                continue
            if not _in_range(_norm(p.get("orderDate")), params.get("dateFrom"), params.get("dateTo")):
                continue
            item_code = params.get("itemCode")
            if item_code:
                codes = [str((it or {}).get("itemCode") or "") for it in (p.get("items") or [])]
                if item_code not in codes:
                    continue
            amount = _as_float(p.get("totalWithTax"))
            if min_amount is not None and (amount is None or amount < min_amount):
                continue
            if max_amount is not None and (amount is None or amount > max_amount):
                continue
            keyword = params.get("keyword")
            if keyword:
                blob = " ".join(
                    [
                        _norm(p.get("poId")),
                        _norm(p.get("poNo")),
                        _norm(supplier.get("supplierId")),
                        _norm(supplier.get("supplier_name")),
                    ]
                )
                if not _contains(blob, keyword):
                    continue
            rows.append(p)
        return rows

    def query_grs(self, **params: Any) -> list[dict[str, Any]]:
        rows = []
        supplier_id = params.get("supplierId")
        allowed_po_ids = None
        if supplier_id:
            sid = _norm(supplier_id)
            allowed_po_ids = {
                p.get("poId")
                for p in self.pos
                if _norm((p.get("supplier") or {}).get("supplierId")) == sid
            }
        for g in self.grs:
            if not _eq(g.get("grId"), params.get("grId")):
                continue
            if not _eq(g.get("poId"), params.get("poId")):
                continue
            if allowed_po_ids is not None and g.get("poId") not in allowed_po_ids:
                continue
            if not _eq(g.get("receivedBy"), params.get("receivedBy")):
                continue
            if not _eq(g.get("status"), params.get("status")):
                continue
            if not _in_range(_norm(g.get("receivedDate")), params.get("dateFrom"), params.get("dateTo")):
                continue
            keyword = params.get("keyword")
            if keyword:
                blob = " ".join([_norm(g.get("grId")), _norm(g.get("grNo")), _norm(g.get("poId"))])
                if not _contains(blob, keyword):
                    continue
            rows.append(g)
        return rows

    def query_invoices(self, **params: Any) -> list[dict[str, Any]]:
        rows = []
        for inv in self.invoices:
            supplier = inv.get("supplier") or {}
            if not _eq(inv.get("invoiceId"), params.get("invoiceId")):
                continue
            if not _eq(inv.get("purchaseOrderId"), params.get("purchaseOrderId") or params.get("poId")):
                continue
            if not _eq(supplier.get("supplierId"), params.get("supplierId")):
                continue
            if not _eq(inv.get("invoiceCode"), params.get("invoiceCode")):
                continue
            if not _eq(inv.get("invoiceNo"), params.get("invoiceNo")):
                continue
            if not _eq(inv.get("status"), params.get("status")):
                continue
            if not _in_range(_norm(inv.get("invoice_date")), params.get("dateFrom"), params.get("dateTo")):
                continue
            keyword = params.get("keyword")
            if keyword:
                blob = " ".join(
                    [
                        _norm(inv.get("invoiceId")),
                        _norm(inv.get("invoiceCode")),
                        _norm(inv.get("invoiceNo")),
                        _norm(inv.get("purchaseOrderId")),
                        _norm(supplier.get("supplierId")),
                        _norm(supplier.get("supplier_name")),
                    ]
                )
                if not _contains(blob, keyword):
                    continue
            rows.append(inv)
        return rows

    def query_payments(self, **params: Any) -> list[dict[str, Any]]:
        rows = []
        for pay in self.payments:
            payee = pay.get("payeeInfo") or {}
            if not _eq(pay.get("paymentId"), params.get("paymentId")):
                continue
            if not _eq(pay.get("invoiceId"), params.get("invoiceId")):
                continue
            if not _eq(pay.get("poId"), params.get("poId")):
                continue
            if not _eq(pay.get("status"), params.get("status")):
                continue
            if not _eq(payee.get("payeeAccountNo"), params.get("payeeAccountNo")):
                continue
            if not _in_range(_norm(pay.get("paymentDate")), params.get("dateFrom"), params.get("dateTo")):
                continue
            keyword = params.get("keyword")
            if keyword:
                blob = " ".join(
                    [
                        _norm(pay.get("paymentId")),
                        _norm(pay.get("paymentNo")),
                        _norm(pay.get("invoiceId")),
                        _norm(pay.get("poId")),
                        _norm(payee.get("payeeName")),
                        _norm(payee.get("payeeAccountNo")),
                    ]
                )
                if not _contains(blob, keyword):
                    continue
            rows.append(pay)
        return rows

    def query_approvals(self, **params: Any) -> list[dict[str, Any]]:
        rows = []
        for rec in self.approvals:
            if not _eq(rec.get("approvalId"), params.get("approvalId")):
                continue
            if not _eq(rec.get("businessType"), params.get("businessType")):
                continue
            if not _eq(rec.get("businessId"), params.get("businessId")):
                continue
            if not _eq(rec.get("approvalStatus"), params.get("approvalStatus")):
                continue
            keyword = params.get("keyword")
            if keyword:
                node_text = " ".join(
                    _norm((n or {}).get("comment")) + " " + _norm((n or {}).get("nodeName"))
                    for n in (rec.get("nodes") or [])
                )
                blob = " ".join(
                    [
                        _norm(rec.get("approvalId")),
                        _norm(rec.get("businessId")),
                        _norm(rec.get("workflowTitle")),
                        _norm(rec.get("submitComment")),
                        node_text,
                    ]
                )
                if not _contains(blob, keyword):
                    continue
            rows.append(rec)
        return rows

    def query_policies(self, **params: Any) -> list[dict[str, Any]]:
        keyword = params.get("keyword")
        doc_id = params.get("docId")
        rows = []
        for doc in self.policies:
            if doc_id and doc["docId"] != doc_id and doc["fileName"] != doc_id:
                continue
            if keyword and not _contains(doc["title"] + "\n" + doc["content"], keyword):
                continue
            rows.append(doc)
        return rows
