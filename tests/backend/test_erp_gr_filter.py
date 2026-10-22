# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ERP_DIR = Path(__file__).resolve().parents[2] / "mock-erp"
if str(ERP_DIR) not in sys.path:
    sys.path.insert(0, str(ERP_DIR))

from store import ErpStore  # type: ignore  # noqa: E402


def test_gr_query_filters_by_supplier_via_po():
    store = ErpStore()
    rows = store.query_grs(supplierId="VEN-S001")
    assert rows
    po_ids = {
        p["poId"]
        for p in store.pos
        if (p.get("supplier") or {}).get("supplierId") == "VEN-S001"
    }
    assert {g["poId"] for g in rows} <= po_ids
    assert store.query_grs(poId=rows[0]["poId"])
