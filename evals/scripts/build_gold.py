# -*- coding: utf-8 -*-
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = json.loads((ROOT / "evals" / "traces" / "raw_analysis.json").read_text(encoding="utf-8"))
GOLD = ROOT / "evals" / "gold"
TRACE = ROOT / "evals" / "traces"
GOLD.mkdir(parents=True, exist_ok=True)

PROFILES = {p["supplierId"]: p for p in RAW["profile"]["profiles"]}
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
CROSS_ROUTE = {
    "mode": "cross",
    "scope": "supplier",
    "agents": ["SupplierRiskAgent", "TransactionRiskAgent", "PaymentRiskAgent"],
    "skills": [
        "supplier-profile-audit-skill",
        "supplier-relation-audit-skill",
        "p2p-three-way-match-skill",
        "split-order-audit-skill",
        "payment-audit-skill",
        "payee-account-security-skill",
    ],
    "paymentScheduling": "if_only_supplier_or_po_then_wait_for_invoiceId_else_parallel",
    "reviewRequired": True,
    "reviewAgents": ["EvidenceReviewAgent", "ReportAgent"],
    "reviewSkills": ["evidence-validation-skill", "risk-report-generator-skill"],
}

def ev(*pairs):
    return [{"tool": t, "id": i} for t, i in pairs if i]

def F(domain, agent, skill, risk_type, level, facts, metrics, root, evidence, tools, subject=None, approval_status=None, recommendation=None, open_questions=None, source="mcp_investigation_draft"):
    rec = {
        "domain": domain,
        "agent": agent,
        "skill": skill,
        "riskType": risk_type,
        "riskLevel": level,
        "mustDetect": True,
        "facts": facts,
        "metrics": metrics,
        "rootCause": root,
        "keyEvidence": evidence,
        "requiredTools": tools,
        "subject": subject or {},
        "source": source,
    }
    if approval_status:
        rec["approvalStatus"] = approval_status
    if recommendation:
        rec["recommendation"] = recommendation
    rec["openQuestions"] = open_questions or []
    return rec

def overall(findings):
    if not findings:
        return "低风险"
    return max((f["riskLevel"] for f in findings), key=lambda x: RANK.get(x, -1))

MUST = {
  "VEN-0013": [F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","低风险",
    ["PO-01615 / GR-000356 / INV-004632：GR实收92，发票数量100，数量差8.7%，超开8060.63元", "存在 APP-GR-01615-202505 分批收货及补货协议审批，状态 COMPLETED"],
    {"poQty":100,"grQty":92,"invoiceQty":100,"qtyDiff":8,"qtyDiffPct":8.7,"overAmount":8060.63},
    "短收按订单全额开票，但已有完整补货/分批审批，风险消解",
    ev(("po-query","PO-01615"),("gr-query","GR-000356"),("invoice-query","INV-004632"),("approval-query","APP-GR-01615-202505")),
    ["po-query","gr-query","invoice-query","approval-query"],
    {"poId":"PO-01615","grId":"GR-000356","invoiceId":"INV-004632","supplierId":"VEN-0013"},
    "COMPLETED", "按已批准口径放行，保留补货入库关闭订单", source="tagged_case_list")],
  "VEN-0014": [F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","高风险",
    ["PO-01338 / GR-000291 / INV-004355：数量均为100", "发票单价由1714.10调整为1850.00，超开15356.70元", "ERP未检索到调价审批"],
    {"poQty":100,"grQty":100,"invoiceQty":100,"qtyDiff":0,"qtyDiffPct":0.0,"overAmount":15356.7,"poUnitPrice":1714.1,"invoiceUnitPrice":1850.0},
    "发票单价高于订单单价形成超开，且无调价审批",
    ev(("po-query","PO-01338"),("gr-query","GR-000291"),("invoice-query","INV-004355")),
    ["po-query","gr-query","invoice-query","approval-query"],
    {"poId":"PO-01338","grId":"GR-000291","invoiceId":"INV-004355","supplierId":"VEN-0014"},
    "NOT_FOUND", "要求按订单单价重开或补调价审批", source="tagged_case_list")],
  "VEN-0018": [F("付款域","PaymentRiskAgent","payment-audit-skill","重复付款","低风险",
    ["INV-004237 / PO-01220 对应 PAY-00273(PAID) 与 PAY-00896(REJECTED)，金额均为90942.06", "拦截审批 APP-PAY-DUP-01220 状态 REJECTED，第二笔未划转"],
    {"invoiceTotal":90942.06,"paymentIds":["PAY-00273","PAY-00896"],"paidCount":1,"paidSum":90942.06,"excessAmount":0.0,"intercepted":True},
    "重复付款申请已被财务经理拒绝拦截，无资金损失",
    ev(("invoice-query","INV-004237"),("payment-query","PAY-00273"),("payment-query","PAY-00896"),("approval-query","APP-PAY-DUP-01220")),
    ["payment-query","invoice-query","approval-query"],
    {"invoiceId":"INV-004237","poId":"PO-01220","supplierId":"VEN-0018"},
    "REJECTED", "保持拦截即可", source="tagged_case_list")],
  "VEN-0021": [F("付款域","PaymentRiskAgent","payee-account-security-skill","异常收款账户","高风险",
    ["PAY-00345 已 PAID，收款人陈晓东，账号6226091234567890123", "VEN-0021 深圳腾跃不锈钢制品有限公司 登记账号0256471647897085460", "approval-query(businessId=VEN-0021, keyword=银行账户) totalCount=0"],
    {"vendorAccountNo":"0256471647897085460","vendorName":"深圳腾跃不锈钢制品有限公司","payeeAccountNo":"6226091234567890123","payeeName":"陈晓东","accountMatch":False,"nameMatch":False,"payeeType":"个人","paymentStatus":"PAID","paymentAmount":118060.8},
    "货款打入第三方个人账户，属于资金红线，ERP未检索到银行账户变更申请",
    ev(("payment-query","PAY-00345"),("invoice-query","INV-004584"),("po-query","PO-01567"),("vendor-query","VEN-0021")),
    ["payment-query","vendor-query","approval-query"],
    {"paymentId":"PAY-00345","invoiceId":"INV-004584","poId":"PO-01567","supplierId":"VEN-0021"},
    "NOT_FOUND", "立即止付/追回，并核查出纳与供应商联系人是否内外勾结", source="tagged_case_list")],
}

MUST.update({
  "VEN-0033": [F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","中风险",
    ["PO-01489 / GR-000327 / INV-004506：GR实收96，发票数量100，数量差4.17%，超开3012.06元", "ERP未检索到补货/分批审批"],
    {"poQty":100,"grQty":96,"invoiceQty":100,"qtyDiff":4,"qtyDiffPct":4.17,"overAmount":3012.06},
    "短收小幅超开，无完整补货审批",
    ev(("po-query","PO-01489"),("gr-query","GR-000327"),("invoice-query","INV-004506")),
    ["po-query","gr-query","invoice-query","approval-query"],
    {"poId":"PO-01489","grId":"GR-000327","invoiceId":"INV-004506","supplierId":"VEN-0033"},
    "NOT_FOUND", "要求补货或红字发票后再匹配", source="tagged_case_list")],
  "VEN-0037": [F("交易域","TransactionRiskAgent","split-order-audit-skill","拆单避审","中风险",
    ["PO-04004/PO-04005/PO-04006 于2026-04-14至2026-04-16下达，物料均为ITEM-0037", "金额484950/471700/466400元，均低于500000红线，合计1423050元", "审批APP-PO-04004-202604(厂务部一号车间年度维保)、APP-PO-04005-202604(IT部办公区弱电改造)、APP-PO-04006-202604(行政部宿舍区空调检修)均为COMPLETED"],
    {"windowDays":2,"poIds":["PO-04004","PO-04005","PO-04006"],"amounts":[484950.0,471700.0,466400.0],"amountSum":1423050.0,"itemCodes":["ITEM-0037"],"nearThreshold":True,"allBelowThreshold":True,"distinctProjects":["厂务部一号车间年度维保项目","IT部办公区弱电改造项目","行政部宿舍区空调检修项目"]},
    "相近时间多笔近红线订单，但审批写明不同项目/需求部门，属合理分单关注项",
    ev(("po-query","PO-04004"),("po-query","PO-04005"),("po-query","PO-04006"),("approval-query","APP-PO-04004-202604"),("approval-query","APP-PO-04005-202604"),("approval-query","APP-PO-04006-202604")),
    ["po-query","approval-query"],
    {"supplierId":"VEN-0037","poId":"PO-04004"},
    "COMPLETED", "关注汇总金额，不必按故意拆单升级", source="tagged_case_list")],
  "VEN-0044": [
    F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","低风险",
      ["PO-01366 / GR-000300 / INV-004383：数量金额一致", "发票日期2025-03-25早于入库日期2025-03-26"],
      {"poQty":100,"grQty":100,"invoiceQty":100,"qtyDiff":0,"qtyDiffPct":0.0,"overAmount":-0.1,"timingOnly":True},
      "仅开票/入库时间差，数量金额随后一致，不按少货多付升级",
      ev(("po-query","PO-01366"),("gr-query","GR-000300"),("invoice-query","INV-004383")),
      ["po-query","gr-query","invoice-query"],
      {"poId":"PO-01366","grId":"GR-000300","invoiceId":"INV-004383","supplierId":"VEN-0044"},
      None, "关注是否已过账，无需按超开处理", ["发票是否已过账"], "tagged_case_list"),
    F("供应商域","SupplierRiskAgent","supplier-profile-audit-skill","供应商主信息异常","低风险",
      ["VEN-0044 主数据 name/taxNo/bankAccount/contactPhone/category 均有值且 active=true", "银行账户变更审批 APP-VEN-0044-BANK-202507 状态 PENDING，财务总监节点待审"],
      {"missingFields":[],"changeApprovalCount":1,"frequentChange":False,"active":True},
      "供应商发起银行账户变更，主数据当前仍完整，不属于频繁改档",
      ev(("vendor-query","VEN-0044"),("approval-query","APP-VEN-0044-BANK-202507")),
      ["vendor-query","approval-query"],
      {"supplierId":"VEN-0044"},
      "PENDING", "主数据可继续使用；付款域必须核验收款账号", ["PENDING的银行账户变更是否已实际用于付款"], "tagged_case_list"),
    F("付款域","PaymentRiskAgent","payee-account-security-skill","异常收款账户","中风险",
      ["PAY-00353 已 PAID，收款账号7558120099887766554，户名仍为佛山仁和供应链管理股份有限公司", "主数据登记账号5054980504038742359", "变更审批 APP-VEN-0044-BANK-202507 仍 PENDING 时已付款"],
      {"vendorAccountNo":"5054980504038742359","vendorName":"佛山仁和供应链管理股份有限公司","payeeAccountNo":"7558120099887766554","payeeName":"佛山仁和供应链管理股份有限公司","accountMatch":False,"nameMatch":True,"payeeType":"供应商本人","paymentStatus":"PAID","paymentAmount":122810.8},
      "账户变更申请仍为PENDING即发起付款，资金已划转",
      ev(("payment-query","PAY-00353"),("invoice-query","INV-004624"),("po-query","PO-01607"),("vendor-query","VEN-0044"),("approval-query","APP-VEN-0044-BANK-202507")),
      ["payment-query","vendor-query","approval-query"],
      {"paymentId":"PAY-00353","invoiceId":"INV-004624","poId":"PO-01607","supplierId":"VEN-0044"},
      "PENDING", "暂停后续付款，等待财务总监审批闭环后再核对账号", source="tagged_case_list"),
  ],
})

MUST.update({
  "VEN-0053": [
    F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","低风险",
      ["PO-02210 / GR-000498 / INV-005227：GR实收99，发票数量100，数量差1.01%，超开340.21元"],
      {"poQty":100,"grQty":99,"invoiceQty":100,"qtyDiff":1,"qtyDiffPct":1.01,"overAmount":340.21},
      "数量差<=2%且超开<=1000，属于容差内低风险",
      ev(("po-query","PO-02210"),("gr-query","GR-000498"),("invoice-query","INV-005227")),
      ["po-query","gr-query","invoice-query"],
      {"poId":"PO-02210","grId":"GR-000498","invoiceId":"INV-005227","supplierId":"VEN-0053"},
      None, "无需按少货多付拦截", source="tagged_case_list"),
    F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","证据不足",
      ["PO-04009 有发票 INV-007009（价税合计90400.00），gr-query(poId=PO-04009) totalCount=0", "不得把缺入库单直接当成少货多付违规"],
      {"poQty":100,"grQty":None,"invoiceQty":100,"missing":["GR"]},
      "缺GR，三单无法闭环",
      ev(("po-query","PO-04009"),("invoice-query","INV-007009")),
      ["po-query","gr-query","invoice-query"],
      {"poId":"PO-04009","invoiceId":"INV-007009","supplierId":"VEN-0053"},
      "NOT_QUERIED", "补齐入库后再判断是否少货多付", source="tagged_case_list"),
  ],
  "VEN-0056": [F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","证据不足",
    ["VEN-0056 存在3张 poId为空的采购单：poNo=null-849/null-850/null-851，日期2024-08-17/2024-08-23，金额68265/63371/83484", "PO上supplier_name为北京VEN-0056公司，与主数据北京正泰金属材料股份有限公司不一致", "无法关联GR/发票，不能当成已确认违规"],
    {"nullPoCount":3,"poNos":["null-849","null-850","null-851"]},
    "单据主键缺失导致三单无法闭环，属于证据不足而非少货多付既成事实",
    ev(("po-query","VEN-0056"),("vendor-query","VEN-0056")),
    ["po-query","gr-query","invoice-query"],
    {"supplierId":"VEN-0056"},
    None, "先补齐PO主键并匹配入库/发票，再评估风险", source="mcp_investigation_draft")],
  "VEN-0069": [F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","高风险",
    ["PO-01332 / GR-000289 / INV-004349：GR实收62，发票数量100，相对入库数量差61.29%（差38件）", "超开金额77690.85元", "approval-query(businessId=PO-01332, keyword=补货) 未检索到审批"],
    {"poQty":100,"grQty":62,"invoiceQty":100,"qtyDiff":38,"qtyDiffPct":61.29,"overAmount":77690.85,"poUnitPrice":1809.28,"invoiceUnitPrice":1809.28},
    "短收仍按订单全额开票，且无补货或分批收货审批",
    ev(("po-query","PO-01332"),("gr-query","GR-000289"),("invoice-query","INV-004349")),
    ["po-query","gr-query","invoice-query","approval-query"],
    {"poId":"PO-01332","grId":"GR-000289","invoiceId":"INV-004349","supplierId":"VEN-0069"},
    "NOT_FOUND", "暂停付款，要求补货或开具红字发票后再匹配", source="tagged_case_list")],
  "VEN-0089": [F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","中风险",
    ["PO-01532 / GR-000340 / INV-004549：数量均为100", "发票单价由439.48调整为460.00，超开2318.76元", "ERP未检索到调价审批"],
    {"poQty":100,"grQty":100,"invoiceQty":100,"qtyDiff":0,"qtyDiffPct":0.0,"overAmount":2318.76,"poUnitPrice":439.48,"invoiceUnitPrice":460.0},
    "发票单价小幅高于订单单价，无完整调价审批",
    ev(("po-query","PO-01532"),("gr-query","GR-000340"),("invoice-query","INV-004549")),
    ["po-query","gr-query","invoice-query","approval-query"],
    {"poId":"PO-01532","grId":"GR-000340","invoiceId":"INV-004549","supplierId":"VEN-0089"},
    "NOT_FOUND", "要求按订单单价重开或补调价审批", source="tagged_case_list")],
})

REL_F = lambda sid: F("供应商域","SupplierRiskAgent","supplier-relation-audit-skill","供应商之间关联关系风险","中风险",
    ["VEN-0095 南通润泽设备维护有限责任公司 与 VEN-0123 润泽设备维护 共用 contactPhone=17090604194、contactName=陆玉", "两者 taxNo/bankAccount 不同，物料分别为 ITEM-0095 与 ITEM-0123，无相同 itemCode 交叉接单", "PO金额分别为6899213.95与6537789.98，approval-query(keyword=关联) totalCount=0"],
    {"keyType":"contactPhone","keyValue":"17090604194","relatedSupplierIds":["VEN-0095","VEN-0123"],"poOverlap":False,"relatedPoAmountSum":13437003.93,"declarationFound":False,"itemCodes":["ITEM-0095","ITEM-0123"]},
    "历史简称与全称分别建档并共享联系人电话，更像主数据重复建档而非串标；Gold按技能示例口径标中风险，不因各自大额PO单独升为高风险",
    ev(("vendor-query","VEN-0095"),("vendor-query","VEN-0123"),("po-query","VEN-0095"),("po-query","VEN-0123")),
    ["vendor-query","po-query","financial-analysis","approval-query"],
    {"supplierId":sid},
    "NOT_FOUND", "合并 VEN-0123 至 VEN-0095 有效档案，并补做关联关系备案",
    ["两家是否曾交叉承接同一项目"], "mcp_investigation_draft")

MUST.update({
  "VEN-0095": [REL_F("VEN-0095")],
  "VEN-0123": [REL_F("VEN-0123")],
  "VEN-0104": [F("交易域","TransactionRiskAgent","split-order-audit-skill","拆单避审","高风险",
    ["PO-04001/PO-04002/PO-04003 于2026-04-18至2026-04-21连续下达", "物料均为ITEM-0104，金额498895/496974/499460元，均低于500000红线，合计1495329元", "approval-query(businessId=PO-04001) totalCount=0，ERP未检索到大额加签或独立项目说明"],
    {"windowDays":3,"poIds":["PO-04001","PO-04002","PO-04003"],"amounts":[498895.0,496974.0,499460.0],"amountSum":1495329.0,"itemCodes":["ITEM-0104"],"nearThreshold":True,"allBelowThreshold":True,"distinctProjects":[]},
    "同一需求被拆成三笔刚好低于大额加签红线的订单，未见独立项目说明",
    ev(("po-query","PO-04001"),("po-query","PO-04002"),("po-query","PO-04003")),
    ["po-query","approval-query"],
    {"supplierId":"VEN-0104","poId":"PO-04001"},
    "NOT_FOUND", "按合并金额补履行大额采购加签，并评估是否暂停后续付款", source="tagged_case_list")],
  "VEN-0118": [
    F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","少货多付 / 数量/金额异常","高风险",
      ["PO-01525 / GR-000337 / INV-004542：入库100，发票数量130，数量差30%，超开40997.98元", "ERP未检索到补货/超开审批"],
      {"poQty":100,"grQty":100,"invoiceQty":130,"qtyDiff":30,"qtyDiffPct":30.0,"overAmount":40997.98},
      "超开数量且无有效审批",
      ev(("po-query","PO-01525"),("gr-query","GR-000337"),("invoice-query","INV-004542")),
      ["po-query","gr-query","invoice-query","approval-query"],
      {"poId":"PO-01525","grId":"GR-000337","invoiceId":"INV-004542","supplierId":"VEN-0118"},
      "NOT_FOUND", "暂停付款并要求红字发票或补审批", source="tagged_case_list"),
    F("付款域","PaymentRiskAgent","payment-audit-skill","重复付款","高风险",
      ["INV-004207 / PO-01190 对应 PAY-00265 与 PAY-00895，两笔均为PAID，金额均为134662.09", "发票总额134662.09，已付合计269324.18，超额134662.09", "ERP未检索到重复付款拦截"],
      {"invoiceTotal":134662.09,"paymentIds":["PAY-00265","PAY-00895"],"paidCount":2,"paidSum":269324.18,"excessAmount":134662.09,"intercepted":False},
      "同一发票全额被成功支付两次，系统未拦截重复提交",
      ev(("invoice-query","INV-004207"),("payment-query","PAY-00265"),("payment-query","PAY-00895"),("po-query","PO-01190")),
      ["payment-query","invoice-query","approval-query"],
      {"invoiceId":"INV-004207","poId":"PO-01190","supplierId":"VEN-0118"},
      "NOT_FOUND", "立即冻结后续付款并启动重复付款追回", source="tagged_case_list"),
  ],
  "VEN-S001": [
    F("供应商域","SupplierRiskAgent","supplier-profile-audit-skill","供应商主信息异常","低风险",
      ["ERP主数据 id=VEN-S001，name=供应商VEN-S001有限公司（案例叙事别名宁波恒远物流有限公司）", "taxNo/bankAccount/contactPhone/category=SERVICE 均有值，active=true", "APP-VEN-S001-202512 宁波恒远物流供应商档案及业务范围变更审批 COMPLETED（采购部主管 APPROVE）；未见财务总监节点，不得编造"],
      {"missingFields":[],"changeApprovalCount":1,"frequentChange":False,"active":True},
      "主数据完整，经营范围变更已有COMPLETED审批，不属于频繁改档",
      ev(("vendor-query","VEN-S001"),("approval-query","APP-VEN-S001-202512")),
      ["vendor-query","approval-query"],
      {"supplierId":"VEN-S001","supplierName":"供应商VEN-S001有限公司","alias":"宁波恒远物流有限公司"},
      "COMPLETED", "档案可继续使用；税率分类是否同步见税率发现", source="mcp_investigation_draft"),
    F("交易域","TransactionRiskAgent","p2p-three-way-match-skill","税率异常","中风险",
      ["供应商 category 仍为 SERVICE（默认6%），但2025-12-26起 PO-HY2000~PO-HY2006 共7笔税率为13%，且PO与发票税率一致", "APP-VEN-S001-202512 已批准新增金属材料转售并要求财务更新税率分类，主数据 category 尚未同步", "不得改动宁波恒远既有三单；本条只评价主数据/税率分类未落地"],
      {"poTaxRate":0.13,"invoiceTaxRate":0.13,"category":"SERVICE","expectedCategoryRate":0.06,"samplePoIds":["PO-HY2000","PO-HY2001","PO-HY2003"],"mismatchPo":False,"mismatchCategory":True},
      "税率变更有据（经营范围审批COMPLETED），但供应商主数据category尚未同步",
      ev(("vendor-query","VEN-S001"),("po-query","PO-HY2000"),("approval-query","APP-VEN-S001-202512")),
      ["vendor-query","po-query","invoice-query","approval-query"],
      {"supplierId":"VEN-S001"},
      "COMPLETED", "将 category/税率分类与已批经营范围对齐，无需把既有13%三单改造成异常样本", source="mcp_investigation_draft"),
  ],
})

REVIEWER = {
  "status": "pending_human_review",
  "method": "MCP tools.dispatch -> mock-erp HTTP; did not read mock-erp/data/*.json as evidence source",
  "decisions": [
    "八类风险名称与阈值以 SKILL.md 为准；重复付款无中风险。",
    "拆单必检仅保留两笔及以上均贴近红线(>=450000且<500000)的聚类：VEN-0104高、VEN-0037中。另外6个“一张近红线+一张较小PO”的5日窗不作为拆单必检，避免把计划补货打成化整为零。",
    "税率：PO与发票税率一致、仅与category默认税率不同的34张发票，不作为税率异常必检。例外：VEN-S001 有经营范围审批明确要求更新税率分类但category仍为SERVICE，按技能中风险口径标注。",
    "关联：全库仅 VEN-0095/VEN-0123 共享电话。名称含腾跃/正泰/润泽等只有字面相似，不作为必检。该对按技能示例标中风险（重复建档），不因各自大额PO升为高风险。",
    "VEN-0056 三张 poId 为空的PO（poNo=null-849/850/851）标证据不足，不标高风险。",
    "PO-01615 规则层为中风险，因 APP-GR-01615-202505 COMPLETED 消解为低风险。",
    "全部GR仓库WH-01-A、收货人EMP-3392，不得作为拆单证据。",
    "不改 VEN-S001 既有三单。主数据name是供应商VEN-S001有限公司，审批标题使用宁波恒远物流。",
  ],
}

FOCUS_NOTES = {
  "VEN-S001": "叙事名宁波恒远物流；ERP name=供应商VEN-S001有限公司。36笔三单均匹配。经营范围变更已批，category未改，7笔PO-HY2000~2006为13%。",
  "VEN-0043": "常州腾跃人力资源。主数据完整，41笔三单均低风险，无共享税号/电话/账号，不因名称含腾跃报关联。",
  "VEN-0104": "常州广盛金属。必检拆单高风险 PO-04001/04002/04003。历史其他5日窗合计越线但非多笔近红线，不作为必检。",
  "VEN-0056": "北京正泰金属。与深圳正泰商贸仅名称相似。3张poId为空单据导致证据不足。",
  "VEN-0121": "腾跃铜业。与深圳腾跃不锈钢/常州腾跃人力无共享标识。一张近红线伴生小额PO不作为拆单必检。",
}


# Tax findings are applied by evals/scripts/apply_tax_gold.py after this generator. Do not treat this file as the final gold.
def make_cross_case(sid):
    p = PROFILES[sid]
    findings = MUST.get(sid, [])
    detected_types = {f["riskType"] for f in findings}
    question = f"请对供应商 {sid}（{p['name']}）做采购到付款全链路风险排查，给出风险领域、风险类型、风险等级和必要证据。"
    if sid == "VEN-S001":
        question = "请对宁波恒远物流有限公司（VEN-S001 / 供应商VEN-S001有限公司）做采购到付款全链路风险排查，给出风险领域、风险类型、风险等级和必要证据。"
    return {
        "caseId": f"CROSS-{sid}",
        "split": "cross",
        "status": "pending_human_review",
        "input": {"question": question},
        "subject": {"supplierId": sid, "supplierName": p["name"], "category": p["category"], "alias": {"VEN-S001": "宁波恒远物流有限公司"}.get(sid)},
        "expectedRoute": CROSS_ROUTE,
        "expectedFindings": findings,
        "expectedBackgroundLowRisk": [t for t in EIGHT if t not in detected_types],
        "expectedOverallRiskLevel": overall(findings),
        "scoring": {
            "mustDetect": [{"riskType": f["riskType"], "riskLevel": f["riskLevel"], "subject": f.get("subject")} for f in findings],
            "falsePositivePenalty": "high_or_mid_on_background_types",
            "backgroundLowRisk": "optional_aggregate_ok",
            "overallRule": "高>中>证据不足>低；已确认红线不被缺口稀释",
        },
        "notes": FOCUS_NOTES.get(sid),
        "source": "mcp_investigation_draft",
    }

def route_single(mode, scope, agent, skill, review=False):
    rec = {"mode": mode, "scope": scope, "agents": [agent], "skills": [skill], "reviewRequired": review}
    if review:
        rec["reviewAgents"] = ["EvidenceReviewAgent", "ReportAgent"]
    return rec

SINGLE = [
  {
    "caseId": "SINGLE-TW-HIGH-PO-01332",
    "split": "single",
    "input": {"question": "PO-01332 三单是否匹配？请给出风险类型、等级和必要证据。"},
    "subject": {"poId": "PO-01332", "grId": "GR-000289", "invoiceId": "INV-004349", "supplierId": "VEN-0069"},
    "expectedRoute": route_single("single","document","TransactionRiskAgent","p2p-three-way-match-skill"),
    "expectedFindings": MUST["VEN-0069"],
    "expectedOverallRiskLevel": "高风险",
  },
  {
    "caseId": "SINGLE-TW-MID-PO-01489",
    "split": "single",
    "input": {"question": "PO-01489 短收超开是否构成少货多付？请给出风险类型、等级和必要证据。"},
    "subject": {"poId": "PO-01489", "grId": "GR-000327", "invoiceId": "INV-004506", "supplierId": "VEN-0033"},
    "expectedRoute": route_single("single","document","TransactionRiskAgent","p2p-three-way-match-skill"),
    "expectedFindings": MUST["VEN-0033"],
    "expectedOverallRiskLevel": "中风险",
  },
  {
    "caseId": "SINGLE-TW-INSUFF-PO-04009",
    "split": "single",
    "input": {"question": "PO-04009 能不能付款？三单是否已经闭环？请给出风险类型、等级和必要证据。"},
    "subject": {"poId": "PO-04009", "invoiceId": "INV-007009", "supplierId": "VEN-0053"},
    "expectedRoute": route_single("single","document","TransactionRiskAgent","p2p-three-way-match-skill"),
    "expectedFindings": [MUST["VEN-0053"][1]],
    "expectedOverallRiskLevel": "证据不足",
  },
  {
    "caseId": "SINGLE-SPLIT-HIGH-VEN-0104",
    "split": "single",
    "input": {"question": "常州广盛金属材料股份有限公司（VEN-0104）最近是不是在拆单规避大额审批？"},
    "subject": {"supplierId": "VEN-0104"},
    "expectedRoute": route_single("single","supplier","TransactionRiskAgent","split-order-audit-skill"),
    "expectedFindings": MUST["VEN-0104"],
    "expectedOverallRiskLevel": "高风险",
  },
  {
    "caseId": "SINGLE-SPLIT-MID-VEN-0037",
    "split": "single",
    "input": {"question": "VEN-0037 这几笔近红线订单是不是故意拆单？请给出风险类型、等级和必要证据。"},
    "subject": {"supplierId": "VEN-0037"},
    "expectedRoute": route_single("single","supplier","TransactionRiskAgent","split-order-audit-skill"),
    "expectedFindings": MUST["VEN-0037"],
    "expectedOverallRiskLevel": "中风险",
  },
  {
    "caseId": "SINGLE-DUPPAY-HIGH-INV-004207",
    "split": "single",
    "input": {"question": "INV-004207 是不是付了两次？请给出风险类型、等级和必要证据。"},
    "subject": {"invoiceId": "INV-004207", "poId": "PO-01190", "supplierId": "VEN-0118"},
    "expectedRoute": route_single("single","document","PaymentRiskAgent","payment-audit-skill"),
    "expectedFindings": [MUST["VEN-0118"][1]],
    "expectedOverallRiskLevel": "高风险",
  },
  {
    "caseId": "SINGLE-PAYEE-HIGH-PAY-00345",
    "split": "single",
    "input": {"question": "PAY-00345 收款账户正不正常？请给出风险类型、等级和必要证据。"},
    "subject": {"paymentId": "PAY-00345", "invoiceId": "INV-004584", "poId": "PO-01567", "supplierId": "VEN-0021"},
    "expectedRoute": route_single("single","document","PaymentRiskAgent","payee-account-security-skill"),
    "expectedFindings": MUST["VEN-0021"],
    "expectedOverallRiskLevel": "高风险",
  },
  {
    "caseId": "SINGLE-PAYEE-MID-PAY-00353",
    "split": "single",
    "input": {"question": "PAY-00353 账户变更还没批完是不是已经付款了？请给出风险类型、等级和必要证据。"},
    "subject": {"paymentId": "PAY-00353", "invoiceId": "INV-004624", "poId": "PO-01607", "supplierId": "VEN-0044"},
    "expectedRoute": route_single("single","document","PaymentRiskAgent","payee-account-security-skill"),
    "expectedFindings": [MUST["VEN-0044"][2]],
    "expectedOverallRiskLevel": "中风险",
  },
  {
    "caseId": "SINGLE-REL-PHONE",
    "split": "single",
    "input": {"question": "供应商里有没有共用电话或重复建档？请给出风险类型、等级和必要证据。"},
    "subject": {"supplierId": None, "relatedSupplierIds": ["VEN-0095", "VEN-0123"]},
    "expectedRoute": route_single("single","population","SupplierRiskAgent","supplier-relation-audit-skill"),
    "expectedFindings": [REL_F(None)],
    "expectedOverallRiskLevel": "中风险",
  },
  {
    "caseId": "SINGLE-POLICY-TRAVEL",
    "split": "single",
    "input": {"question": "帮我查一下公司内部报销制度关于差旅费的标准是什么。"},
    "subject": {},
    "expectedRoute": route_single("policy_qa","policy","GeneralQueryAgent","internal-policy-qa-skill"),
    "expectedIntent": "policy_qa",
    "expectedFindings": [],
    "expectedOverallRiskLevel": None,
    "expectedAnswer": {
      "skill": "internal-policy-qa-skill",
      "notCovered": False,
      "handoff": None,
      "requiredTools": ["policy-query"],
      "citations": [
        {"docId": "差旅与报销管理制度", "title": "差旅与报销管理制度", "version": "V1.2", "effectiveDate": "2025-01-01", "article": "第二条", "quote": "北京、上海、广州、深圳：500 元/晚；省会及计划单列市：400 元/晚；其他城市：350 元/晚。"},
        {"docId": "差旅与报销管理制度", "title": "差旅与报销管理制度", "version": "V1.2", "effectiveDate": "2025-01-01", "article": "第三条", "quote": "国内优先高铁/动车二等座；航班仅限经济舱。出租车/网约车仅用于机场、车站接驳或无公共交通场景，单日上限 150 元。"},
        {"docId": "差旅与报销管理制度", "title": "差旅与报销管理制度", "version": "V1.2", "effectiveDate": "2025-01-01", "article": "第四条", "quote": "一线城市 150 元/天；其他城市 100 元/天。出发和返回当天按半天计。"},
      ],
      "mustNot": ["给出高风险/中风险/低风险作为最终风控结论", "把差旅报销派给 PaymentRiskAgent", "引用已废止的供应商管理办法V1.0"],
    },
  },
]

def stamp(obj, extra=None):
    obj.update({
        "version": "v1.draft",
        "status": "pending_human_review",
        "goldFrozen": False,
        "protocol": "AGENTS.md",
        "company": "启衡精密制造有限公司",
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "investigationTrace": "evals/traces/raw_analysis.json",
        "mcpQueryTrace": "evals/traces/mcp_queries.json",
    })
    if extra:
        obj.update(extra)
    return obj

def main():
    sids = [p["supplierId"] for p in RAW["profile"]["profiles"]]
    cases = [make_cross_case(sid) for sid in sids]
    cross = stamp({
        "datasetId": "finprobe-cross-supplier-v1",
        "split": "cross",
        "description": "27家供应商全量跨域调查评测集。每家可能有多个风险。status=pending_human_review，确认后冻结为 gold。",
        "reviewerDecisions": REVIEWER,
        "riskTypes": EIGHT,
        "cases": cases,
    })
    for c in SINGLE:
        c["status"] = "pending_human_review"
        c["source"] = "mcp_investigation_draft"
        c.setdefault("expectedBackgroundLowRisk", [])
        c.setdefault("scoring", {"mustDetect": [{"riskType": f["riskType"], "riskLevel": f["riskLevel"]} for f in c.get("expectedFindings") or []]})
    single = stamp({
        "datasetId": "finprobe-single-domain-v1",
        "split": "single",
        "description": "10个单域评测题：8个单据/供应商调查 + 1个全量关联排查 + 1个制度问答。主体不一定是供应商。",
        "reviewerDecisions": REVIEWER,
        "cases": SINGLE,
    })
    (GOLD / "cross_supplier_v1.draft.json").write_text(json.dumps(cross, ensure_ascii=False, indent=2), encoding="utf-8")
    (GOLD / "single_domain_v1.draft.json").write_text(json.dumps(single, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [{"caseId": c["caseId"], "supplierId": c["subject"]["supplierId"], "name": c["subject"]["supplierName"], "overall": c["expectedOverallRiskLevel"], "must": [f"{f['riskType']}|{f['riskLevel']}" for f in c["expectedFindings"]]} for c in cases]
    (TRACE / "cross_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("cross", len(cases), "single", len(SINGLE))

if __name__ == "__main__":
    main()
