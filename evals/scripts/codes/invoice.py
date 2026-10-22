invs = datasets[INV_ART]
pos = datasets[POS_ART]
vendors = VENDORS
po_by_id = {}
for po in pos:
    po_by_id[po.get("poId")] = po
ven_by_id = {}
for v in vendors:
    ven_by_id[v.get("id")] = v
pair = defaultdict(list)
similar = defaultdict(list)
tax_flags = []
for inv in invs:
    code = str(inv.get("invoiceCode") or "")
    no = str(inv.get("invoiceNo") or "")
    pair[code + "+" + no].append(inv.get("invoiceId"))
    po = po_by_id.get(inv.get("purchaseOrderId") or inv.get("poId"))
    sid = None
    if po:
        sid = (po.get("supplier") or {}).get("supplierId")
    if not sid:
        sid = (inv.get("supplier") or {}).get("supplierId") or inv.get("supplierId")
    total = to_number(inv.get("total"))
    dt = str(inv.get("invoice_date") or "")[:10]
    similar[str(sid) + "|" + str(round(total, 2)) + "|" + dt].append(inv.get("invoiceId"))
    ven = ven_by_id.get(sid) or {}
    cat = ven.get("category")
    expected = 0.06 if cat == "SERVICE" else 0.13
    po_tax = to_number(po.get("taxRate")) if po else None
    inv_tax = to_number(inv.get("taxRate")) if inv.get("taxRate") is not None else None
    mismatch_po = po is not None and inv.get("taxRate") is not None and abs(inv_tax - po_tax) > 1e-9
    mismatch_cat = cat is not None and inv.get("taxRate") is not None and abs(inv_tax - expected) > 1e-9
    if mismatch_po or mismatch_cat:
        tax_flags.append({"invoiceId": inv.get("invoiceId"), "poId": inv.get("purchaseOrderId") or inv.get("poId"), "supplierId": sid, "category": cat, "expectedCategoryRate": expected, "poTaxRate": po_tax, "invoiceTaxRate": inv_tax, "mismatchPo": mismatch_po, "mismatchCategory": mismatch_cat, "invoiceTotal": total})
dup_pairs = []
for k, v in pair.items():
    if len(v) > 1:
        dup_pairs.append({"key": k, "invoiceIds": v, "count": len(v)})
dup_similar = []
for k, v in similar.items():
    uniq = sorted(set([i for i in v if i]))
    if len(uniq) > 1:
        dup_similar.append({"key": k, "invoiceIds": uniq, "count": len(uniq)})
result = {"duplicateCodeNo": dup_pairs, "similarInvoiceGroups": dup_similar, "taxFlags": tax_flags, "invoiceCount": len(invs)}
