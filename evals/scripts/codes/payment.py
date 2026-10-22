pays = datasets[PAY_ART]
pos = datasets[POS_ART]
invs = datasets[INV_ART]
vendors = VENDORS
po_by_id = {}
for po in pos:
    po_by_id[po.get("poId")] = po
inv_by_id = {}
for inv in invs:
    inv_by_id[inv.get("invoiceId")] = inv
ven_by_id = {}
for v in vendors:
    ven_by_id[v.get("id")] = v
by_inv = defaultdict(list)
for p in pays:
    if p.get("invoiceId"):
        by_inv[p.get("invoiceId")].append(p)
dup_pay = []
for iid, rows in by_inv.items():
    if len(rows) <= 1:
        continue
    paid = [r for r in rows if r.get("status") == "PAID"]
    other = [r for r in rows if r.get("status") != "PAID"]
    inv = inv_by_id.get(iid) or {}
    invoice_total = to_number(inv.get("total")) if inv else 0.0
    paid_sum = round(sum(to_number(r.get("paymentAmount")) for r in paid), 2)
    po_id = rows[0].get("poId") or inv.get("purchaseOrderId")
    sid = None
    if po_id:
        sid = ((po_by_id.get(po_id) or {}).get("supplier") or {}).get("supplierId")
    dup_pay.append({"invoiceId": iid, "poId": po_id, "supplierId": sid, "paymentIds": [r.get("paymentId") for r in rows], "statuses": [r.get("status") for r in rows], "amounts": [to_number(r.get("paymentAmount")) for r in rows], "paidCount": len(paid), "paidSum": paid_sum, "invoiceTotal": invoice_total, "excessAmount": round(paid_sum - invoice_total, 2) if inv else None, "intercepted": len(other) > 0 and len(paid) <= 1, "riskLevel": "高风险" if len(paid) >= 2 else "低风险"})
payee_flags = []
for p in pays:
    info = p.get("payeeInfo") or {}
    payee_acct = info.get("payeeAccountNo")
    payee_name = info.get("payeeName")
    po = po_by_id.get(p.get("poId")) or {}
    sid = (po.get("supplier") or {}).get("supplierId")
    ven = ven_by_id.get(sid) or {}
    vendor_acct = ven.get("bankAccount")
    vendor_name = ven.get("name")
    account_match = bool(payee_acct) and str(payee_acct) == str(vendor_acct)
    name_match = bool(payee_name) and str(payee_name) == str(vendor_name)
    if account_match:
        continue
    nm = str(payee_name or "")
    personal = False
    if nm and ("公司" not in nm) and ("厂" not in nm) and ("中心" not in nm) and ("工作室" not in nm) and (2 <= len(nm) <= 4):
        personal = True
    payee_type = "个人" if personal else ("供应商本人" if payee_name == vendor_name else "未登记关联公司")
    level = "高风险" if personal else "待审"
    payee_flags.append({"paymentId": p.get("paymentId"), "invoiceId": p.get("invoiceId"), "poId": p.get("poId"), "supplierId": sid, "status": p.get("status"), "paymentAmount": to_number(p.get("paymentAmount")), "vendorAccountNo": vendor_acct, "vendorName": vendor_name, "payeeAccountNo": payee_acct, "payeeName": payee_name, "accountMatch": account_match, "nameMatch": name_match, "payeeType": payee_type, "ruleRiskLevel": level})
result = {"multiPayments": dup_pay, "payeeFlags": payee_flags, "paymentCount": len(pays)}
