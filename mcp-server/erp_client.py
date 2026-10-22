# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import httpx

from settings import ERP_API_KEY, ERP_BASE_URL, MAX_FETCH


class ErpError(RuntimeError):
    pass


class ErpClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = (base_url or ERP_BASE_URL).rstrip("/")
        self.api_key = api_key or ERP_API_KEY
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            timeout=30.0,
        )

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        clean = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        try:
            resp = self._client.get(path, params=clean)
        except httpx.RequestError as exc:
            raise ErpError(
                f"无法连接 mock-erp ({self.base_url})。请先启动：python mock-erp/server.py。原始错误：{exc}"
            ) from exc
        if resp.status_code == 401:
            raise ErpError("ERP 鉴权失败，请检查 X-Api-Key / ERP_API_KEY")
        if resp.status_code == 404:
            raise ErpError(resp.json().get("detail") if _is_json(resp) else f"not found: {path}")
        if resp.status_code >= 400:
            raise ErpError(f"ERP HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def fetch_all(self, path: str, params: dict[str, Any] | None = None, max_records: int | None = None) -> list[dict[str, Any]]:
        cap = max_records or MAX_FETCH
        page = 1
        page_size = 100
        rows: list[dict[str, Any]] = []
        total = None
        while True:
            query = dict(params or {})
            query.update({"page": page, "pageSize": page_size})
            payload = self.get(path, query)
            batch = payload.get("data") or []
            if total is None:
                total = int(payload.get("totalCount") or 0)
            rows.extend(batch)
            if len(rows) >= cap or len(rows) >= total or not batch:
                break
            page += 1
        return rows[:cap]


def _is_json(resp: httpx.Response) -> bool:
    ctype = resp.headers.get("content-type", "")
    return "json" in ctype
