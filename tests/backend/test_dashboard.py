# -*- coding: utf-8 -*-
from __future__ import annotations


def test_supplier_risks_has_27_vendors(api_client):
    resp = api_client.get("/v1/dashboard/supplier-risks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["vendorCount"] == 27
    assert len(body["vendors"]) == 27
    ids = {row["supplierId"] for row in body["vendors"]}
    assert {"VEN-0056", "VEN-0121", "VEN-0104", "VEN-0043", "VEN-S001"} <= ids
    target = next(row for row in body["vendors"] if row["supplierId"] == "VEN-0056")
    assert target["overallRiskLevel"] == "高风险"
    types = {item["riskType"] for item in target["findings"]}
    assert "税率异常" in types


def test_dashboard_summary_includes_gold_when_erp_down(api_client):
    resp = api_client.get("/v1/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["supplierRisks"]["vendorCount"] == 27
    assert "kpis" in body
    assert "levelCounts" in body["supplierRisks"]
