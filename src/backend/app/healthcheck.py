# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

import httpx


def probe_erp(base_url: str, timeout: float = 2.5) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/health"
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url)
        if resp.status_code != 200:
            return {"ok": False, "baseUrl": base_url, "error": f"HTTP {resp.status_code}"}
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "ok": True,
            "baseUrl": base_url,
            "counts": payload.get("counts") if isinstance(payload, dict) else None,
            "company": payload.get("company") if isinstance(payload, dict) else None,
        }
    except httpx.RequestError as exc:
        return {"ok": False, "baseUrl": base_url, "error": f"无法连接 mock-erp: {exc}"}