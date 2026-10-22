# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any


HTTP_BY_CODE = {
    "VALIDATION": 400,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "ERP_UNAVAILABLE": 503,
    "LLM_ERROR": 500,
    "EVIDENCE_BLOCKED": 409,
    "CANCELLED": 409,
}

RETRYABLE = {"ERP_UNAVAILABLE", "LLM_ERROR"}


class AppError(Exception):
    def __init__(self, code: str, message: str, retryable: bool | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = RETRYABLE.__contains__(code) if retryable is None else retryable
        self.http_status = http_status if http_status is not None else HTTP_BY_CODE.get(code, 500)

    def body(self) -> dict[str, Any]:
        return error_body(self.code, self.message, self.retryable)


def error_body(code: str, message: str, retryable: bool | None = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "retryable": RETRYABLE.__contains__(code) if retryable is None else retryable,
        },
    }