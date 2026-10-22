# -*- coding: utf-8 -*-
"""Stdlib HTTP mock ERP. curl-compatible REST, no FastAPI required."""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import API_KEY, COMPANY_NAME, HOST, PORT
from store import ErpStore, paginate

STORE = ErpStore()


def _q(qs: dict[str, list[str]], key: str, default: str | None = None) -> str | None:
    vals = qs.get(key)
    if not vals:
        return default
    return vals[0]


def _q_int(qs: dict[str, list[str]], key: str, default: int) -> int:
    raw = _q(qs, key)
    if raw is None or raw == "":
        return default
    return int(raw)


def _q_float(qs: dict[str, list[str]], key: str) -> float | None:
    raw = _q(qs, key)
    if raw is None or raw == "":
        return None
    return float(raw)


class handler(BaseHTTPRequestHandler):
    server_version = "FinprobeMockERP/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self._send(401, {"error": "unauthorized", "message": "缺少或错误的 X-Api-Key"})

    def _not_found(self, msg: str) -> None:
        self._send(404, {"detail": msg})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        qs = parse_qs(parsed.query)
        if path == "/health":
            self._send(
                200,
                {
                    "status": "ok",
                    "company": COMPANY_NAME,
                    "counts": {
                        "vendors": len(STORE.vendors),
                        "purchaseOrders": len(STORE.pos),
                        "goodsReceipts": len(STORE.grs),
                        "invoices": len(STORE.invoices),
                        "payments": len(STORE.payments),
                        "approvals": len(STORE.approvals),
                        "policies": len(STORE.policies),
                    },
                },
            )
            return
        key = self.headers.get("X-Api-Key")
        if key != API_KEY:
            self._unauthorized()
            return
        try:
            data = route_get(path, qs)
        except LookupError as exc:
            self._not_found(str(exc))
            return
        except ValueError as exc:
            self._send(400, {"detail": str(exc)})
            return
        if data is None:
            self._not_found(path)
            return
        self._send(200, data)


def route_get(path: str, qs: dict[str, list[str]]) -> Any:
    page = _q_int(qs, "page", 1)
    page_size = _q_int(qs, "pageSize", 20)
    if path == "/v1/vendors":
        rows = STORE.query_vendors(
            id=_q(qs, "id"),
            supplierId=_q(qs, "supplierId"),
            code=_q(qs, "code"),
            name=_q(qs, "name"),
            taxNo=_q(qs, "taxNo"),
            bankAccount=_q(qs, "bankAccount"),
            contactPhone=_q(qs, "contactPhone"),
            category=_q(qs, "category"),
            active=_q(qs, "active"),
            keyword=_q(qs, "keyword"),
        )
        return paginate(rows, page, page_size)
    if path.startswith("/v1/vendors/"):
        rec = STORE.vendor_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("vendor not found")
        return rec
    if path == "/v1/purchase-orders":
        rows = STORE.query_pos(
            poId=_q(qs, "poId"),
            poNo=_q(qs, "poNo"),
            supplierId=_q(qs, "supplierId"),
            status=_q(qs, "status"),
            itemCode=_q(qs, "itemCode"),
            dateFrom=_q(qs, "dateFrom"),
            dateTo=_q(qs, "dateTo"),
            minAmount=_q_float(qs, "minAmount"),
            maxAmount=_q_float(qs, "maxAmount"),
            keyword=_q(qs, "keyword"),
        )
        return paginate(rows, page, page_size)
    if path.startswith("/v1/purchase-orders/"):
        rec = STORE.po_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("purchase order not found")
        return rec
    if path == "/v1/goods-receipts":
        rows = STORE.query_grs(
            grId=_q(qs, "grId"),
            poId=_q(qs, "poId"),
            supplierId=_q(qs, "supplierId"),
            receivedBy=_q(qs, "receivedBy"),
            status=_q(qs, "status"),
            dateFrom=_q(qs, "dateFrom"),
            dateTo=_q(qs, "dateTo"),
            keyword=_q(qs, "keyword"),
        )
        return paginate(rows, page, page_size)
    if path.startswith("/v1/goods-receipts/"):
        rec = STORE.gr_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("goods receipt not found")
        return rec
    if path == "/v1/invoices":
        rows = STORE.query_invoices(
            invoiceId=_q(qs, "invoiceId"),
            purchaseOrderId=_q(qs, "purchaseOrderId"),
            poId=_q(qs, "poId"),
            supplierId=_q(qs, "supplierId"),
            invoiceCode=_q(qs, "invoiceCode"),
            invoiceNo=_q(qs, "invoiceNo"),
            status=_q(qs, "status"),
            dateFrom=_q(qs, "dateFrom"),
            dateTo=_q(qs, "dateTo"),
            keyword=_q(qs, "keyword"),
        )
        return paginate(rows, page, page_size)
    if path.startswith("/v1/invoices/"):
        rec = STORE.invoice_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("invoice not found")
        return rec
    if path == "/v1/payments":
        rows = STORE.query_payments(
            paymentId=_q(qs, "paymentId"),
            invoiceId=_q(qs, "invoiceId"),
            poId=_q(qs, "poId"),
            status=_q(qs, "status"),
            payeeAccountNo=_q(qs, "payeeAccountNo"),
            dateFrom=_q(qs, "dateFrom"),
            dateTo=_q(qs, "dateTo"),
            keyword=_q(qs, "keyword"),
        )
        return paginate(rows, page, page_size)
    if path.startswith("/v1/payments/"):
        rec = STORE.payment_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("payment not found")
        return rec
    if path == "/v1/approvals":
        rows = STORE.query_approvals(
            approvalId=_q(qs, "approvalId"),
            businessType=_q(qs, "businessType"),
            businessId=_q(qs, "businessId"),
            approvalStatus=_q(qs, "approvalStatus"),
            keyword=_q(qs, "keyword"),
        )
        return paginate(rows, page, page_size)
    if path.startswith("/v1/approvals/"):
        rec = STORE.approval_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("approval not found")
        return rec
    if path == "/v1/policies":
        rows = STORE.query_policies(docId=_q(qs, "docId"), keyword=_q(qs, "keyword"))
        compact = [{"docId": r["docId"], "title": r["title"], "fileName": r["fileName"], "charCount": len(r["content"])} for r in rows]
        return paginate(compact, page, page_size)
    if path.startswith("/v1/policies/"):
        rec = STORE.policy_by_id(path.split("/", 3)[-1])
        if not rec:
            raise LookupError("policy not found")
        return rec
    return None


def serve(host: str = HOST, port: int = PORT) -> None:
    httpd = ThreadingHTTPServer((host, port), handler)
    sys.stderr.write(f"Mock ERP listening on http://{host}:{port}\n")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()
