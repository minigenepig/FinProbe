# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Query, Request

from ..erp_gateway import RESOURCES, ErpGateway
from ..errors import AppError

router = APIRouter()


def _gateway(request: Request) -> ErpGateway:
    existing = getattr(request.app.state, "erp", None)
    if existing is not None:
        return existing
    gw = ErpGateway(request.app.state.settings)
    request.app.state.erp = gw
    return gw


@router.get("/v1/erp/resources")
def list_resources():
    return {"ok": True, "resources": list(RESOURCES.keys())}


@router.get("/v1/erp/{resource}")
def list_erp(
    resource: str,
    request: Request,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    keyword: str | None = None,
    supplierId: str | None = None,
    status: str | None = None,
    category: str | None = None,
    poId: str | None = None,
    invoiceId: str | None = None,
    paymentId: str | None = None,
    businessType: str | None = None,
    approvalStatus: str | None = None,
):
    if resource not in RESOURCES:
        raise AppError("VALIDATION", f"未知资源: {resource}")
    params = {
        "page": page,
        "pageSize": pageSize,
        "keyword": keyword,
        "supplierId": supplierId,
        "status": status,
        "category": category,
        "poId": poId,
        "invoiceId": invoiceId,
        "paymentId": paymentId,
        "businessType": businessType,
        "approvalStatus": approvalStatus,
    }
    payload = _gateway(request).list_resource(resource, params)
    return {"ok": True, "resource": resource, **payload}


@router.get("/v1/erp/{resource}/{item_id}")
def get_erp(resource: str, item_id: str, request: Request):
    if resource not in RESOURCES:
        raise AppError("VALIDATION", f"未知资源: {resource}")
    rec = _gateway(request).get_resource(resource, item_id)
    return {"ok": True, "resource": resource, "data": rec}