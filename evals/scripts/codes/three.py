pos = datasets[POS_ART]
grs = datasets[GRS_ART]
invs = datasets[INV_ART]
gr_by_po = defaultdict(list)
inv_by_po = defaultdict(list)
for g in grs:
    if g.get("poId"):
        gr_by_po[g.get("poId")].append(g)
for inv in invs:
    pid = inv.get("purchaseOrderId") or inv.get("poId")
    if pid:
        inv_by_po[pid].append(inv)
anomalies = []
vendor_stats = {}
tagged = set(TAGGED_POS)
for po in pos:
    po_id = po.get("poId")
    sid = (po.get("supplier") or {}).get("supplierId")
    if sid not in vendor_stats:
        vendor_stats[sid] = {"poCount": 0, "low": 0, "mid": 0, "high": 0, "insufficient": 0}
    vendor_stats[sid]["poCount"] += 1
    items = po.get("items") or []
    po_qty = to_number(items[0].get("quantity")) if items else 0.0
    po_price = to_number(items[0].get("unitPrice")) if items else 0.0
    po_tax = to_number(po.get("taxRate"))
    po_item = items[0].get("itemCode") if items else None
    glist = gr_by_po.get(po_id) or []
    ilist = inv_by_po.get(po_id) or []
    rec = {"poId": po_id, "supplierId": sid, "orderDate": po.get("orderDate"), "poQty": po_qty, "poUnitPrice": po_price, "poTaxRate": po_tax, "poTotalWithTax": to_number(po.get("totalWithTax")), "itemCode": po_item, "grCount": len(glist), "invoiceCount": len(ilist)}
    if (not glist) or (not ilist):
        rec["riskLevel"] = "证据不足"
        rec["missing"] = ([] if glist else ["GR"]) + ([] if ilist else ["Invoice"])
        rec["grId"] = glist[0].get("grId") if glist else None
        rec["invoiceId"] = ilist[0].get("invoiceId") if ilist else None
        vendor_stats[sid]["insufficient"] += 1
        anomalies.append(rec)
        continue
    gr = glist[0]
    inv = ilist[0]
    lines = gr.get("lines") or []
    gr_qty = to_number(lines[0].get("receivedQuantity")) if lines else 0.0
    inv_items = inv.get("items") or []
    inv_qty = to_number(inv_items[0].get("invoiced_quantity")) if inv_items else 0.0
    inv_price = to_number(inv_items[0].get("unit_price")) if inv_items else 0.0
    inv_tax = to_number(inv.get("taxRate")) if inv.get("taxRate") is not None else po_tax
    inv_total = to_number(inv.get("total"))
    rec["grId"] = gr.get("grId")
    rec["invoiceId"] = inv.get("invoiceId")
    rec["invoiceCode"] = inv.get("invoiceCode")
    rec["invoiceNo"] = inv.get("invoiceNo")
    rec["grQty"] = gr_qty
    rec["invoiceQty"] = inv_qty
    rec["invoiceUnitPrice"] = inv_price
    rec["invoiceTaxRate"] = to_number(inv.get("taxRate"))
    rec["invoiceTotal"] = inv_total
    rec["invoiceDate"] = inv.get("invoice_date")
    rec["receivedDate"] = gr.get("receivedDate")
    if gr_qty == 0:
        rec["riskLevel"] = "证据不足"
        rec["missing"] = ["GR_QTY_ZERO"]
        vendor_stats[sid]["insufficient"] += 1
        anomalies.append(rec)
        continue
    qty_diff = inv_qty - gr_qty
    qty_pct = round(qty_diff / gr_qty * 100, 2)
    received_value = round(gr_qty * po_price * (1 + inv_tax), 2)
    over = round(inv_total - received_value, 2)
    rec["qtyDiff"] = qty_diff
    rec["qtyDiffPct"] = qty_pct
    rec["overAmount"] = over
    rec["receivedValue"] = received_value
    if qty_pct > 10 or over > 10000:
        level = "高风险"
        vendor_stats[sid]["high"] += 1
    elif qty_pct > 2 or over > 1000:
        level = "中风险"
        vendor_stats[sid]["mid"] += 1
    else:
        level = "低风险"
        vendor_stats[sid]["low"] += 1
    rec["timingOnly"] = False
    if level == "低风险" and rec.get("invoiceDate") and rec.get("receivedDate"):
        if str(rec["invoiceDate"])[:10] < str(rec["receivedDate"])[:10]:
            rec["timingOnly"] = True
    rec["riskLevel"] = level
    if level != "低风险" or po_id in tagged or rec["timingOnly"]:
        anomalies.append(rec)
result = {"vendorStats": vendor_stats, "anomalies": anomalies, "poCount": len(pos), "grCount": len(grs), "invoiceCount": len(invs)}
