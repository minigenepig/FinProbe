---
name: split-order-audit-skill
description: 识别为规避大额采购审批红线而拆分订单的行为，并区分不同项目的合理分单与故意拆单。在用户提到拆单、化整为零、审批红线、短时间内多笔相近订单时使用；不要用它做三单数量核对或付款调查。
---

# 拆单避审审计

所属 Agent：`TransactionRiskAgent`。覆盖风险类型④「拆单避审」。

## 目标

判断同一供应商在短时间窗口内的多笔采购订单，是否为规避「单笔价税合计 >= 500,000 元须大额采购加签」而拆单。发现疑似拆单后必须分析根因，并用审批记录判断是故意拆单、还是不同项目的合理分单。

## 执行步骤

1. 取目标供应商一段时间 PO：`po-query(supplierId=..., dateFrom=..., dateTo=..., clusterWindowDays=5)`。用返回的 `splitClusters` 与 `summary.nearThresholdCount`，全量明细走 artifact。
2. 对每个聚类计算：笔数、合计金额、是否每笔都 < 500,000 且接近红线（>= 450,000）、物料是否同一 `itemCode`、时间跨度。金额聚合用 `financial-analysis`。
3. 不要对每张 PO 循环 `gr-query`。本环境收货人通常为 `EMP-3392`、仓库 `WH-01-A`，不能单独据此定罪。仅当 `summary.nearThresholdCount` 或 `splitClusters` 出现近红线时，才对最多 3 个代表 `poId` 抽查入库；「同一供应商 + 5 日窗口 + 物料一致 + 金额贴近红线」仍有效。
4. 消解检查：`approval-query(businessId=各 poId)` 或 `keyword=项目|厂务|IT|行政|大额`。审批写明不同部门或项目，判中风险关注汇总，而不是高风险故意拆单。细则见 [split-rules.md](references/split-rules.md)。
5. 需要红线原文时 `policy-query(keyword=大额采购)`。
6. 根因只能写：规避加签、项目窗口重叠的合理分单、计划性补货。未检索到大额审批时表述为「ERP 未检索到大额加签或独立项目说明」。若单笔已 >= 500,000 且存在 COMPLETED 大额审批，不按拆单处理。

## 规则

- 企业内控红线：单笔 PO `totalWithTax` >= 500,000 元须大额采购加签（部门经理 → 采购总监 → 财务总监）。
- 观察窗口：同一供应商 5 日内。接近红线：450,000 <= 单笔 < 500,000。合计越线：sum(totalWithTax) >= 500,000。
- 高风险：同一经办人在 5 日内向同一供应商连续下达多笔刚好低于红线、物料高度一致的订单，无独立项目说明。
- 中风险：相近时间有多笔订单，但分属于不同业务部门或项目，且审批中注明项目名称/需求部门。
- 低风险：采购单独立下达，时间间隔超过 5 日，或无故意拆单特征。
- 证据不足：无法取到订单金额或订单日期，导致不能判断窗口与是否贴近红线。
- 本环境几乎所有 GR 都是同一收货人/仓库，不得把「receivedBy 相同」当作高风险的充分条件。

## 输出格式

统一调查信封，字段名不可改。

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `split-order-audit-skill` |
| agent | string | 是 | 固定 `TransactionRiskAgent` |
| subject | object | 是 | `supplierId` 必填；`poId` 可填聚类代表单 |
| queries | object[] | 是 | 至少包含 `po-query`；下结论前应有 `approval-query` |
| findings | object[] | 是 | 每个拆单聚类一条；无拆单特征时输出 1 条低风险 |
| findings[].riskType | string | 是 | 固定 `拆单避审` |
| findings[].riskLevel | string | 是 | `高风险` / `中风险` / `低风险` / `证据不足` |
| findings[].facts | string[] | 是 | 必须列出 poId 列表、日期、金额、物料 |
| findings[].metrics | object | 是 | 见下表 |
| findings[].rootCause | string | 是 | 规避加签 / 合理分单 / 计划补货 |
| findings[].mitigation | object | 是 | `queried/queryArgs/approvalIds/approvalStatus/resolved/detail` |
| findings[].recommendation | string | 是 | 补大额加签 / 关注汇总金额 / 无需处理 |
| findings[].openQuestions | string[] | 是 | 无则 `[]` |
| findings[].evidenceRefs | object[] | 是 | PO ID 与审批 ID |
| overallRiskLevel | string | 是 | 取 findings 最高等级 |

`findings[].metrics`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| windowDays | number | 实际跨度天数 |
| poIds | string[] | 聚类内订单 |
| amounts | number[] | 各单 `totalWithTax` |
| amountSum | number | 合计 |
| itemCodes | string[] | 物料集合 |
| nearThreshold | boolean | 是否存在贴近红线的订单 |
| allBelowThreshold | boolean | 是否每笔都 < 500,000 |
| distinctProjects | string[] | 从审批中抽出的项目/部门，无则为 `[]` |

## 示例

用户：「VEN-0104 最近是不是在拆单规避大额审批？」

```json
{
  "skill": "split-order-audit-skill",
  "agent": "TransactionRiskAgent",
  "subject": {"supplierId": "VEN-0104", "supplierName": "常州广盛金属材料股份有限公司"},
  "queries": [
    {"tool": "po-query", "args": {"supplierId": "VEN-0104", "clusterWindowDays": 5}, "ok": true, "totalCount": 3, "artifactId": null},
    {"tool": "approval-query", "args": {"businessId": "PO-04001", "keyword": "项目"}, "ok": true, "totalCount": 0, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "拆单避审",
      "riskLevel": "高风险",
      "facts": [
        "PO-04001/PO-04002/PO-04003 于 2026-04-18 至 2026-04-21 连续下达",
        "物料均为 ITEM-0104，金额 498895 / 496974 / 499460 元，均低于 500000 红线，合计 1495329 元"
      ],
      "metrics": {
        "windowDays": 4,
        "poIds": ["PO-04001", "PO-04002", "PO-04003"],
        "amounts": [498895.0, 496974.0, 499460.0],
        "amountSum": 1495329.0,
        "itemCodes": ["ITEM-0104"],
        "nearThreshold": true,
        "allBelowThreshold": true,
        "distinctProjects": []
      },
      "rootCause": "同一需求被拆成三笔刚好低于大额加签红线的订单，未见独立项目说明",
      "mitigation": {
        "queried": true,
        "queryArgs": {"businessId": "PO-04001", "keyword": "项目"},
        "approvalIds": [],
        "approvalStatus": "NOT_FOUND",
        "resolved": false,
        "detail": "ERP 未检索到大额加签或独立项目说明"
      },
      "recommendation": "按合并金额补履行大额采购加签，并评估是否暂停后续付款",
      "openQuestions": [],
      "evidenceRefs": [
        {"tool": "po-query", "id": "PO-04001"},
        {"tool": "po-query", "id": "PO-04002"},
        {"tool": "po-query", "id": "PO-04003"}
      ]
    }
  ],
  "overallRiskLevel": "高风险"
}
```

对照：VEN-0037 的 `PO-04004/04005/04006` 虽 3 日内合计超过红线，但分别有厂务部/IT部/行政部项目审批 → 中风险。

## 边界

- 不核对入库数量与发票数量，那是 `p2p-three-way-match-skill` 的职责。
- 单笔已超过 500,000 且大额审批 COMPLETED，不是拆单问题。
- 不要因为收货人相同就定罪；也不要在未查审批时说「故意拆单且无任何项目说明」。
- 禁止把供应商全部历史 PO 原文贴进结论，只用聚类摘要。