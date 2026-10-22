# -*- coding: utf-8 -*-
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MCP_SANDBOX_TIMEOUT", "60")
os.environ.setdefault("ERP_BASE_URL", "http://127.0.0.1:8081")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server"))
from tools import dispatch

CODES = Path(__file__).resolve().parent / "codes"
TRACE = ROOT / "evals" / "traces"
TRACE.mkdir(parents=True, exist_ok=True)
QUERIES = []
TAGGED_POS = ["PO-01332","PO-01525","PO-01338","PO-01489","PO-01532","PO-02210","PO-01615","PO-01366","PO-04009","PO-04001","PO-04002","PO-04003","PO-04004","PO-04005","PO-04006","PO-01190","PO-01220","PO-01567","PO-01607"]

def load_code(name: str) -> str:
    return (CODES / name).read_text(encoding="utf-8-sig")

def call(tool, args=None):
    payload = json.loads(dispatch(tool, args or {}))
    art = payload.get("artifact") or {}
    QUERIES.append({"tool": tool, "args": args or {}, "ok": payload.get("ok"), "totalCount": payload.get("totalCount"), "artifactId": art.get("artifactId"), "summary": payload.get("summary"), "error": payload.get("error")})
    return payload

def aid(p):
    return (p.get("artifact") or {}).get("artifactId")

def analyze(name, artifact_ids, context):
    payload = call("financial-analysis", {"code": load_code(name), "artifactIds": artifact_ids, "context": context})
    if not payload.get("ok"):
        raise RuntimeError(name + ": " + str(payload.get("error")))
    return payload.get("result")

def first(payload):
    if payload.get("ok") and payload.get("data"):
        return payload["data"][0]
    return payload

def main():
    vendors_payload = call("vendor-query", {})
    vendors = vendors_payload.get("data") or []
    pos_payload = call("po-query", {"clusterWindowDays": 5})
    grs_payload = call("gr-query", {})
    inv_payload = call("invoice-query", {})
    pay_payload = call("payment-query", {})
    app_payload = call("approval-query", {})
    policy_payload = call("policy-query", {"keyword": "差旅"})
    rel_payload = call("approval-query", {"keyword": "关联"})
    pos_art, grs_art, inv_art, pay_art, app_art = aid(pos_payload), aid(grs_payload), aid(inv_payload), aid(pay_payload), aid(app_payload)
    profile = analyze("profile.py", [], {"VENDORS": vendors})
    three = analyze("three.py", [pos_art, grs_art, inv_art], {"POS_ART": pos_art, "GRS_ART": grs_art, "INV_ART": inv_art, "TAGGED_POS": TAGGED_POS})
    split = analyze("split.py", [pos_art], {"POS_ART": pos_art})
    invoices = analyze("invoice.py", [inv_art, pos_art], {"INV_ART": inv_art, "POS_ART": pos_art, "VENDORS": vendors})
    payments = analyze("payment.py", [pay_art, pos_art, inv_art], {"PAY_ART": pay_art, "POS_ART": pos_art, "INV_ART": inv_art, "VENDORS": vendors})
    approvals = analyze("approval.py", [app_art], {"APP_ART": app_art})
    po_details = {po_id: first(call("po-query", {"poId": po_id})) for po_id in TAGGED_POS}
    inv_ids = ["INV-004207","INV-004237","INV-004584","INV-004624","INV-007009"]
    pay_ids = ["PAY-00265","PAY-00895","PAY-00273","PAY-00896","PAY-00345","PAY-00353"]
    app_ids = ["APP-GR-01615-202505","APP-PO-04004-202604","APP-PO-04005-202604","APP-PO-04006-202604","APP-PAY-DUP-01220","APP-VEN-0044-BANK-202507","APP-VEN-S001-202512"]
    inv_details = {i: first(call("invoice-query", {"invoiceId": i})) for i in inv_ids}
    pay_details = {i: first(call("payment-query", {"paymentId": i})) for i in pay_ids}
    app_details = {i: first(call("approval-query", {"approvalId": i})) for i in app_ids}
    vendor_apps = {}
    for sid in ["VEN-S001","VEN-0044","VEN-0021","VEN-0104","VEN-0037","VEN-0095","VEN-0123"]:
        vendor_apps[sid] = first(call("approval-query", {"businessId": sid}))
    # extra GR for anomalies
    gr_details = {}
    for rec in three.get("anomalies") or []:
        if rec.get("grId"):
            gr_details[rec["grId"]] = first(call("gr-query", {"grId": rec["grId"]}))
        if rec.get("invoiceId") and rec["invoiceId"] not in inv_details:
            inv_details[rec["invoiceId"]] = first(call("invoice-query", {"invoiceId": rec["invoiceId"]}))
    raw = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summaries": {
            "vendor": vendors_payload.get("summary"),
            "po": pos_payload.get("summary"),
            "gr": grs_payload.get("summary"),
            "invoice": inv_payload.get("summary"),
            "payment": pay_payload.get("summary"),
            "approval": app_payload.get("summary"),
            "splitClustersTop": pos_payload.get("splitClusters"),
            "relationApprovalCount": rel_payload.get("totalCount"),
            "policyTravel": policy_payload.get("summary"),
        },
        "profile": profile,
        "threeWay": three,
        "split": split,
        "invoices": invoices,
        "payments": payments,
        "approvals": approvals,
        "taggedDetails": {"po": po_details, "gr": gr_details, "invoice": inv_details, "payment": pay_details, "approval": app_details, "vendorApprovals": vendor_apps},
        "queryCount": len(QUERIES),
    }
    (TRACE / "raw_analysis.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    (TRACE / "mcp_queries.json").write_text(json.dumps(QUERIES, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE raw_analysis queries=" + str(len(QUERIES)))

if __name__ == "__main__":
    main()
