apps = datasets[APP_ART]
by_biz = defaultdict(list)
pending = []
rejected = []
keyword_hits = []
for a in apps:
    rec = {"approvalId": a.get("approvalId"), "businessType": a.get("businessType"), "businessId": a.get("businessId"), "workflowTitle": a.get("workflowTitle"), "approvalStatus": a.get("approvalStatus"), "submitComment": a.get("submitComment"), "nodes": [{"step": n.get("step"), "nodeName": n.get("nodeName"), "approverName": n.get("approverName"), "action": n.get("action")} for n in (a.get("nodes") or [])]}
    by_biz[str(a.get("businessId"))].append(rec)
    if a.get("approvalStatus") == "PENDING":
        pending.append(rec)
    if a.get("approvalStatus") == "REJECTED":
        rejected.append(rec)
    title = str(a.get("workflowTitle") or "") + " " + str(a.get("submitComment") or "")
    keys = ["关联","合并档案","利益冲突","补货","分批","价格","税率","经营范围","银行","重复","拦截","大额","项目","厂务","IT","行政"]
    hit = [k for k in keys if k in title]
    if hit:
        rec2 = dict(rec)
        rec2["keywords"] = hit
        keyword_hits.append(rec2)
result = {"count": len(apps), "byBusinessId": dict(by_biz), "pending": pending, "rejected": rejected, "keywordHits": keyword_hits}
