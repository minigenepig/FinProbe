# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import httpx

from .config import Settings, get_settings
from .errors import AppError

RESOURCES = {
    "vendors": "/v1/vendors",
    "purchase-orders": "/v1/purchase-orders",
    "goods-receipts": "/v1/goods-receipts",
    "invoices": "/v1/invoices",
    "payments": "/v1/payments",
    "approvals": "/v1/approvals",
    "policies": "/v1/policies",
}


class ErpGateway:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base = self.settings.erp_base_url.rstrip("/")
        self.key = self.settings.erp_api_key

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.key, "Accept": "application/json"}

    def request(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.get(f"{self.base}{path}", params=clean, headers=self._headers())
        except httpx.RequestError as exc:
            raise AppError("ERP_UNAVAILABLE", f"无法连接 mock-erp: {exc}", retryable=True) from exc
        if resp.status_code == 401:
            raise AppError("ERP_UNAVAILABLE", "ERP 鉴权失败", retryable=False)
        if resp.status_code == 404:
            raise AppError("NOT_FOUND", f"ERP 记录不存在: {path}")
        if resp.status_code >= 400:
            raise AppError("ERP_UNAVAILABLE", f"ERP HTTP {resp.status_code}: {resp.text[:300]}", retryable=True)
        return resp.json()

    def list_resource(self, resource: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if resource not in RESOURCES:
            raise AppError("VALIDATION", f"未知资源: {resource}")
        return self.request(RESOURCES[resource], params)

    def get_resource(self, resource: str, item_id: str) -> dict[str, Any]:
        if resource not in RESOURCES:
            raise AppError("VALIDATION", f"未知资源: {resource}")
        return self.request(f"{RESOURCES[resource]}/{item_id}")

    def fetch_all(self, resource: str, params: dict[str, Any] | None = None, cap: int = 2000) -> list[dict[str, Any]]:
        page = 1
        rows: list[dict[str, Any]] = []
        total = None
        while True:
            query = dict(params or {})
            query.update({"page": page, "pageSize": 100})
            payload = self.list_resource(resource, query)
            batch = payload.get("data") or []
            if total is None:
                total = int(payload.get("totalCount") or 0)
            rows.extend(batch)
            if len(rows) >= cap or len(rows) >= total or not batch:
                break
            page += 1
        return rows[:cap]

    def health_counts(self) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=2.5) as client:
                resp = client.get(f"{self.base}/health")
            if resp.status_code != 200:
                raise AppError("ERP_UNAVAILABLE", f"ERP health HTTP {resp.status_code}", retryable=True)
            return resp.json()
        except httpx.RequestError as exc:
            raise AppError("ERP_UNAVAILABLE", f"无法连接 mock-erp: {exc}", retryable=True) from exc