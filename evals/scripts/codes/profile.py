vendors = VENDORS
required = ["id","code","name","taxNo","category","paymentTermsDays","contactName","contactPhone","bankAccount","active"]
profiles = []
phone_groups = defaultdict(list)
tax_groups = defaultdict(list)
bank_groups = defaultdict(list)
name_groups = defaultdict(list)
for v in vendors:
    missing = [k for k in required if v.get(k) is None or v.get(k) == ""]
    profiles.append({"supplierId": v.get("id"), "code": v.get("code"), "name": v.get("name"), "shortName": v.get("shortName"), "taxNo": v.get("taxNo"), "category": v.get("category"), "paymentTermsDays": v.get("paymentTermsDays"), "contactName": v.get("contactName"), "contactPhone": v.get("contactPhone"), "bankAccount": v.get("bankAccount"), "active": v.get("active"), "missingFields": missing})
    if v.get("contactPhone"):
        phone_groups[v.get("contactPhone")].append(v.get("id"))
    if v.get("taxNo"):
        tax_groups[v.get("taxNo")].append(v.get("id"))
    if v.get("bankAccount"):
        bank_groups[v.get("bankAccount")].append(v.get("id"))
    nm = str(v.get("name") or "")
    for token in ["腾跃","正泰","润泽","鑫源","智诚","普瑞","新元"]:
        if token in nm:
            name_groups[token].append({"supplierId": v.get("id"), "name": nm, "category": v.get("category")})
def dups(groups):
    out = []
    for key, ids in groups.items():
        uniq = sorted(set(ids))
        if len(uniq) > 1:
            out.append({"key": key, "supplierIds": uniq})
    return out
result = {"profiles": profiles, "dupPhones": dups(phone_groups), "dupTax": dups(tax_groups), "dupBank": dups(bank_groups), "nameTokens": dict(name_groups)}
