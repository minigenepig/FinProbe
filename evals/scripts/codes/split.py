pos = datasets[POS_ART]
groups = defaultdict(list)
for r in pos:
    sid = str((r.get("supplier") or {}).get("supplierId") or "")
    if sid and r.get("orderDate"):
        groups[sid].append(r)
def parse_day(s):
    t = str(s)[:10]
    return datetime(int(t[0:4]), int(t[5:7]), int(t[8:10]))
def date_key(x):
    return str(x.get("orderDate"))
clusters = []
near_pos = []
large_pos = []
for sid, items in groups.items():
    items = sorted(items, key=date_key)
    for po in items:
        amt = to_number(po.get("totalWithTax"))
        ic = None
        if po.get("items"):
            ic = po.get("items")[0].get("itemCode")
        if amt >= 500000:
            large_pos.append({"supplierId": sid, "poId": po.get("poId"), "orderDate": po.get("orderDate"), "amount": amt, "itemCode": ic})
        elif 450000 <= amt < 500000:
            near_pos.append({"supplierId": sid, "poId": po.get("poId"), "orderDate": po.get("orderDate"), "amount": amt, "itemCode": ic})
    i = 0
    n = len(items)
    while i < n:
        j = i
        while j + 1 < n:
            d1 = parse_day(items[i]["orderDate"])
            d2 = parse_day(items[j + 1]["orderDate"])
            if (d2 - d1).days <= 5:
                j += 1
            else:
                break
        if j > i:
            chunk = items[i:j+1]
            amounts = [to_number(x.get("totalWithTax")) for x in chunk]
            item_codes = []
            for x in chunk:
                its = x.get("items") or []
                if its:
                    item_codes.append(its[0].get("itemCode"))
            amount_sum = round(sum(amounts), 2)
            near = any(450000 <= a < 500000 for a in amounts)
            all_below = all(a < 500000 for a in amounts)
            window = (parse_day(chunk[-1]["orderDate"]) - parse_day(chunk[0]["orderDate"])).days
            clusters.append({"supplierId": sid, "size": len(chunk), "dateFrom": chunk[0]["orderDate"], "dateTo": chunk[-1]["orderDate"], "windowDays": window, "amountSum": amount_sum, "amounts": amounts, "poIds": [x.get("poId") for x in chunk], "itemCodes": sorted(set([c for c in item_codes if c])), "nearThreshold": near, "allBelowThreshold": all_below, "suspect": bool(near and all_below and amount_sum >= 500000)})
        i = j + 1
result = {"clusterCount": len(clusters), "suspects": [c for c in clusters if c.get("suspect")], "nearThresholdPos": near_pos, "largePos": large_pos}
