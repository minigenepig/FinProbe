# -*- coding: utf-8 -*-
import json
from pathlib import Path

ROOT = Path(r"D:/产品经理学习/vibe-coding/Finprobe")
GOLD = ROOT / "evals" / "gold"
EIGHT = [
    "供应商主信息异常",
    "供应商之间关联关系风险",
    "少货多付 / 数量/金额异常",
    "拆单避审",
    "重复发票",
    "税率异常",
    "重复付款",
    "异常收款账户",
]
RANK = {"高风险": 3, "中风险": 2, "证据不足": 1, "低风险": 0}

def ev(*pairs):
    return [{"tool": t, "id": i} for t, i in pairs if i]

def tax_finding(level, facts, metrics, root, evidence, subject, recommendation, source="mcp_investigation_draft"):
    return {
        "domain": "交易域",
        "agent": "TransactionRiskAgent",
        "skill": "p2p-three-way-match-skill",
        "riskType": "税率异常",
        "riskLevel": level,
        "mustDetect": True,
        "facts": facts,
        "metrics": metrics,
        "rootCause": root,
        "keyEvidence": evidence,
        "requiredTools": ["invoice-query", "po-query", "vendor-query", "approval-query"],
        "subject": subject,
        "source": source,
        "approvalStatus": metrics.get("approvalStatus", "NOT_FOUND"),
        "recommendation": recommendation,
        "openQuestions": [],
    }

TAX = {
    "VEN-0056": tax_finding(
        "高风险",
        [
            "VEN-0056 北京正泰金属材料股份有限公司 category=MATERIAL，默认税率13%",
            "INV-003948 / PO-00931 发票与PO税率均为6%，开票日期2025-01-13，未税403539.56，价税合计427751.94",
            "其余35/36张发票均为13%，此为孤立异常；少计税额约28247.77元，约占该供应商发票总额4.46%",
            "approval-query(businessId=VEN-0056/PO-00931, keyword=税率|经营范围) 为0；ERP没有 VENDOR_PROFILE_CHANGE 这种 businessType",
        ],
        {
            "poTaxRate": 0.06,
            "invoiceTaxRate": 0.06,
            "expectedCategoryRate": 0.13,
            "category": "MATERIAL",
            "taxDelta": 28247.77,
            "amountExclTax": 403539.56,
            "invoiceTotal": 427751.94,
            "outlierInvoiceIds": ["INV-003948"],
            "mismatchPo": False,
            "approvalStatus": "NOT_FOUND",
        },
        "原材料供应商孤立开具6%发票且PO同步为6%，无经营范围/税率变更审批，少计税额超过10000元",
        ev(("invoice-query", "INV-003948"), ("po-query", "PO-00931"), ("vendor-query", "VEN-0056")),
        {"invoiceId": "INV-003948", "poId": "PO-00931", "supplierId": "VEN-0056"},
        "按13%重开或补税率/经营范围变更审批后再入账",
    ),
    "VEN-0121": tax_finding(
        "中风险",
        [
            "VEN-0121 腾跃铜业 category=MATERIAL，默认税率13%；vendor-query(taxNo=913205Q9T9TP2FQA63) 仅返回 VEN-0121，不存在 VEN-0052 / 烟台腾跃铜业双档案",
            "INV-006335 / PO-03318 发票与PO税率均为9%，未税241973.59，价税合计263751.21",
            "其余73/74张发票均为13%；少计税额约9678.95元，约占1.12%",
            "ERP未检索到税率/经营范围变更审批",
        ],
        {
            "poTaxRate": 0.09,
            "invoiceTaxRate": 0.09,
            "expectedCategoryRate": 0.13,
            "category": "MATERIAL",
            "taxDelta": 9678.95,
            "amountExclTax": 241973.59,
            "invoiceTotal": 263751.21,
            "outlierInvoiceIds": ["INV-006335"],
            "mismatchPo": False,
            "duplicateTaxNo": False,
            "approvalStatus": "NOT_FOUND",
        },
        "原材料供应商孤立开具9%发票，PO与发票一致但偏离category默认税率，少计税额处于1000至10000区间；不得因不存在的同税号双档案改判证据不足",
        ev(("invoice-query", "INV-006335"), ("po-query", "PO-03318"), ("vendor-query", "VEN-0121")),
        {"invoiceId": "INV-006335", "poId": "PO-03318", "supplierId": "VEN-0121"},
        "按13%重开或补税率变更审批",
    ),
    "VEN-0043": tax_finding(
        "高风险",
        [
            "VEN-0043 常州腾跃人力资源服务有限公司 category=SERVICE，默认税率6%；39/41张发票为6%",
            "INV-004485 / PO-01468 发票与PO均为3%，未税358043.45，少计税额约10741.31元",
            "INV-003871 / PO-00854 发票与PO均为9%，未税129204.57，多计税额约3876.14元",
            "无共享税号/电话/账号，不因名称含腾跃报关联；ERP未检索到税率/经营范围变更审批",
        ],
        {
            "expectedCategoryRate": 0.06,
            "category": "SERVICE",
            "outlierInvoiceIds": ["INV-004485", "INV-003871"],
            "taxDeltas": {"INV-004485": 10741.31, "INV-003871": -3876.14},
            "taxDelta": 10741.31,
            "mismatchPo": False,
            "approvalStatus": "NOT_FOUND",
        },
        "服务类供应商出现偏离6%的孤立开票：3%少计超过10000元构成高风险，9%多计3876元同属无审批税率异常，总体取高",
        ev(("invoice-query", "INV-004485"), ("invoice-query", "INV-003871"), ("po-query", "PO-01468"), ("po-query", "PO-00854"), ("vendor-query", "VEN-0043")),
        {"invoiceId": "INV-004485", "poId": "PO-01468", "supplierId": "VEN-0043"},
        "按6%重开或补税率变更审批；优先处理少计税的 INV-004485",
    ),
    "VEN-0104": tax_finding(
        "低风险",
        [
            "VEN-0104 常州广盛金属材料股份有限公司 category=MATERIAL，默认13%，33/34张发票为13%",
            "INV-003530 / PO-00513 发票与PO均为3%，未税1887.30，价税合计1943.92，少计税额约188.73元，约占该供应商发票总额0.019%",
            "ERP未检索到税率变更审批；因|税额差|<=1000，不升级",
        ],
        {
            "poTaxRate": 0.03,
            "invoiceTaxRate": 0.03,
            "expectedCategoryRate": 0.13,
            "category": "MATERIAL",
            "taxDelta": 188.73,
            "amountExclTax": 1887.3,
            "invoiceTotal": 1943.92,
            "outlierInvoiceIds": ["INV-003530"],
            "mismatchPo": False,
            "approvalStatus": "NOT_FOUND",
        },
        "原材料供应商有一张3%孤立票，但少计税额仅约189元，按重要性归低风险关注项",
        ev(("invoice-query", "INV-003530"), ("po-query", "PO-00513"), ("vendor-query", "VEN-0104")),
        {"invoiceId": "INV-003530", "poId": "PO-00513", "supplierId": "VEN-0104"},
        "可要求重开，但不必按高风险拦截整户",
    ),
}

NOTES = {
    "VEN-0056": "北京正泰金属。INV-003948 税率高风险（MATERIAL 开6%，少计约28248）。另有3张poId为空单据（poNo=null-849/850/851）三单证据不足，不稀释已确认红线。与深圳正泰商贸仅名称相似，无共享税号。",
    "VEN-0121": "腾跃铜业。INV-006335 税率中风险（MATERIAL 开9%，少计约9679）。不存在 VEN-0052 同税号双档案。与深圳腾跃不锈钢/常州腾跃人力无共享标识。近红线伴生小额PO不作为拆单必检。",
    "VEN-0043": "常州腾跃人力。税率高风险：INV-004485 开3%少计约10741，INV-003871 开9%多计约3876。主数据完整，无共享税号/电话/账号，不因名称含腾跃报关联。",
    "VEN-0104": "常州广盛金属。必检拆单高风险 PO-04001/04002/04003。另有 INV-003530 开3%、少计约189，税率低风险。历史其他5日窗合计越线但非多笔近红线，不作为拆单必检。",
    "VEN-S001": "叙事名宁波恒远物流；ERP name=供应商VEN-S001有限公司。36笔数量三单均匹配。经营范围变更已批，category仍为SERVICE，PO-HY2000~2006共7笔13%，税率中风险。",
}

def overall(findings):
    if not findings:
        return "低风险"
    return max((f["riskLevel"] for f in findings), key=lambda x: RANK.get(x, -1))

def patch_case(case, sid):
    findings = list(case.get("expectedFindings") or [])
    # replace existing 税率异常 or append
    findings = [f for f in findings if f.get("riskType") != "税率异常"]
    if sid in TAX:
        findings.append(TAX[sid])
    # VEN-S001 keep existing profile finding; tax already removed and we'll re-add via TAX? VEN-S001 not in TAX dict - keep original tax finding
    if sid == "VEN-S001":
        # restore original tax if we stripped it - need original from file before strip
        pass
    case["expectedFindings"] = findings
    detected = {f["riskType"] for f in findings}
    case["expectedBackgroundLowRisk"] = [t for t in EIGHT if t not in detected]
    case["expectedOverallRiskLevel"] = overall(findings)
    case["scoring"]["mustDetect"] = [
        {"riskType": f["riskType"], "riskLevel": f["riskLevel"], "subject": f.get("subject")} for f in findings
    ]
    if sid in NOTES:
        case["notes"] = NOTES[sid]
    return case

# VEN-S001: don't strip tax - handle separately
cross_path = GOLD / "cross_supplier_v1.draft.json"
cross = json.loads(cross_path.read_text(encoding="utf-8"))

# update reviewer tax decision
decs = cross["reviewerDecisions"]["decisions"]
new_decs = []
for d in decs:
    if d.startswith("税率："):
        new_decs.append("税率：PO与发票相同不是低风险充分条件。无审批时按|税额差|分级：>10000高、1000-10000中、<=1000低；有经营范围审批但category未同步为中。VEN-0056 INV-003948高；VEN-0121 INV-006335中；VEN-0043 INV-004485高（另INV-003871中，总体高）；VEN-0104 INV-003530低；VEN-S001七笔13%中。不存在VEN-0052同税号双档案。")
    else:
        new_decs.append(d)
cross["reviewerDecisions"]["decisions"] = new_decs

for case in cross["cases"]:
    sid = case["subject"]["supplierId"]
    if sid == "VEN-S001":
        case["notes"] = NOTES[sid]
        continue
    if sid in TAX:
        findings = [f for f in case.get("expectedFindings") or [] if f.get("riskType") != "税率异常"]
        findings.append(TAX[sid])
        case["expectedFindings"] = findings
        detected = {f["riskType"] for f in findings}
        case["expectedBackgroundLowRisk"] = [t for t in EIGHT if t not in detected]
        case["expectedOverallRiskLevel"] = overall(findings)
        case["scoring"]["mustDetect"] = [
            {"riskType": f["riskType"], "riskLevel": f["riskLevel"], "subject": f.get("subject")} for f in findings
        ]
        case["notes"] = NOTES[sid]

cross_path.write_text(json.dumps(cross, ensure_ascii=False, indent=2), encoding="utf-8")

# summary
from collections import Counter
print("patched overall", Counter(c["expectedOverallRiskLevel"] for c in cross["cases"]))
for sid in ["VEN-0056","VEN-0121","VEN-0043","VEN-0104","VEN-S001"]:
    c = next(x for x in cross["cases"] if x["subject"]["supplierId"]==sid)
    print(sid, c["expectedOverallRiskLevel"], [(f["riskType"], f["riskLevel"]) for f in c["expectedFindings"]])
print("cross written")
