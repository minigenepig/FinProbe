---
name: p2p-three-way-match-skill
description: 对 PO-GR-Invoice 做三单匹配，识别少货多付、数量金额异常、重复发票和税率异常，并分析根因与审批消解。在用户提到三单、超开、短收、发票重复、税率不对时使用；不要用它调查拆单避审或付款账户。
---

# 三单匹配与发票合规

所属 Agent：`TransactionRiskAgent`。覆盖风险类型③「少货多付 / 数量/金额异常」、⑤「重复发票」、⑥「税率异常」。

## 目标

把指定 PO（或供应商下的相关三单）做成可复核的匹配结论：数量、单价、金额、税率是否一致，发票代码号码是否唯一，税率是否与 PO/供应商类别匹配。发现差异后必须继续查原因，并用 `approval-query` 判断补货、分批收货、价格调整、业务范围与税率变更能否消解风险。

## 执行步骤

1. 定位单据。有 `poId` 时分别调用 `po-query(poId=)`、`gr-query(poId=)`、`invoice-query(purchaseOrderId=)`。只有供应商时：`po-query(supplierId=)`、`invoice-query(supplierId=)`、`gr-query(supplierId=)` 各至多 1 次列表，用 summary/artifact，不要倾倒全量，禁止按 PO 循环 `gr-query`。拆单聚类用 `po-query(..., clusterWindowDays=5)`。
2. 三单匹配。比对物料、数量、单价、金额、税率。计算公式见 [match-rules.md](references/match-rules.md)。可选本地脚本：`python skills/p2p-three-way-match-skill/scripts/match_calc.py input.json`。复杂聚合用 `financial-analysis`。
3. 少货多付分级：按数量差%与超开金额阈值判定；有完整补货/分批/调价审批则消解为低风险。缺 GR 或缺 Invoice 判证据不足，不得直接当违规。
4. 重复发票：`invoice-query(supplierId=)` 全量后看 summary 中的重复 `invoiceCode+invoiceNo`。全量发票走 artifact，不要要求返回 74 张原文。号不同但供应商+金额+日期高度一致，按换号重报。
5. 税率异常：比对 PO `taxRate` 与 Invoice `taxRate`，再看该供应商发票税率分布（孤立异常必须单列）；用 `vendor-query` 核对 `category` 默认税率（服务类 6%，原材料/外协/办公 13%）。税额差 = to_number(amountExclTax) × (默认税率 − 发票税率)，正数为少计税、负数为多计税。PO 与发票税率相同不能直接判低风险。本环境没有 VENDOR_PROFILE_CHANGE 这种 businessType，消解用 approval-query(businessId=供应商或PO, keyword=税率|经营范围)。
6. 消解检查：`approval-query(businessId=PO或供应商ID, keyword=补货|分批|价格|税率|经营范围)`。未查询审批不得宣称无审批。
7. 根因必须写成机制，例如：短收仍按订单全额开票、单价被改、连号虚开、开票入库时间差未同步、服务类误开 13%。分别输出 ③⑤⑥ 的 findings，没有的类型也要写明已检查且低风险或未触发。

## 规则

数量差% = (发票数量 - 入库数量) / 入库数量 × 100（以入库为分母，与 `scripts/match_calc.py` 一致）。入库数量为 0 视为无法匹配，判证据不足。相对订购数量的短收只写入 facts，不单独作为分级口径。  
超开金额 = 发票价税合计 - 入库数量 × 订单单价 × (1 + 税率)。

**③ 少货多付 / 数量/金额异常**

- 高风险：数量差% > 10，或超开金额 > 10,000 元，且无有效审批。
- 中风险：2 < 数量差% ≤ 10，或 1,000 < 超开金额 ≤ 10,000 元，且无完整审批。
- 低风险：完全一致，或数量差% ≤ 2 且超开金额 ≤ 1,000 元；或仅开票/入库时间差且数量金额随后一致；或有完整补货/分批/调价审批。
- 证据不足：缺 GR 或缺 Invoice，无法闭环。

**⑤ 重复发票**

- 高风险：相同 `invoiceCode+invoiceNo` 出现两次以上，且已被多次关联报销/付款。
- 中风险：发票号不同，但供应商、金额、开票日期高度一致（疑似换号重报）。
- 低风险：发票号码唯一，无重复报销嫌疑。

**⑥ 税率异常**

默认税率：`SERVICE` 6%；`MATERIAL` / `OUTSOURCE` / `OFFICE` 13%。
税额差 = `to_number(amountExclTax)` × (类别默认税率 − 发票 `taxRate`)。正数=少计税，负数=多计税；分级用绝对值。PO 与发票税率相同 **不是** 低风险的充分条件，还须对照 `category`。

- 高风险：无税率/经营范围变更审批，且满足任一：① 发票税率与 PO 不一致且税额增加；② 发票或 PO 税率与 `category` 默认税率不一致，属于该供应商的孤立/少数异常，且 |税额差| > 10,000 元。
- 中风险：税率/经营范围变更审批为 COMPLETED，但 `category` 尚未同步；或无审批的同类差异满足 1,000 < |税额差| ≤ 10,000 元。
- 低风险：发票、PO 与类别默认税率三者一致；或 |税额差| ≤ 1,000 元；或变更审批已闭环且后续开票符合新范围。
- 证据不足：缺 `category` 或税率字段，无法比对。已确认的错税率不得因无关主数据传闻（例如不存在的同税号双档案）降为证据不足。
- 本环境没有 `VENDOR_PROFILE_CHANGE` 这种 businessType。查询 0 条写「ERP 未检索到税率/经营范围变更审批」。

对照：`INV-003948`（VEN-0056 MATERIAL 开 6%，少计约 28,248）→ 高风险；`INV-006335`（VEN-0121 开 9%，少计约 9,679）→ 中风险；`INV-003530`（VEN-0104 开 3%，少计约 189）→ 低风险；VEN-S001 七笔 13% 且 `APP-VEN-S001-202512` COMPLETED、`category` 仍为 SERVICE → 中风险。

统一：不得将数据缺失直接等同于违规；已能确认的红线不因次要字段缺失降为证据不足。

## 输出格式

统一调查信封。本技能 `findings` 按风险类型拆条，至少覆盖已检查的 ③，若做了供应商全量发票核验再追加 ⑤⑥。

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `p2p-three-way-match-skill` |
| agent | string | 是 | 固定 `TransactionRiskAgent` |
| subject | object | 是 | 至少 `poId`；有则填 `grId`、`invoiceId`、`supplierId` |
| queries | object[] | 是 | 实际调用的 po/gr/invoice/approval/vendor/financial-analysis |
| findings | object[] | 是 | 每类风险一条，`riskType` 取值：`少货多付 / 数量/金额异常`、`重复发票`、`税率异常` |
| findings[].riskLevel | string | 是 | `高风险` / `中风险` / `低风险` / `证据不足` |
| findings[].facts | string[] | 是 | 引用 PO/GR/INV ID 与数量金额 |
| findings[].metrics | object | 是 | 见下表 |
| findings[].rootCause | string | 是 | 机制，不能只写「对不上」 |
| findings[].mitigation | object | 是 | `queried/queryArgs/approvalIds/approvalStatus/resolved/detail` |
| findings[].recommendation | string | 是 | 如暂停付款、要求红字发票、补审批 |
| findings[].openQuestions | string[] | 是 | 无则 `[]` |
| findings[].evidenceRefs | object[] | 是 | `{tool,id}` |
| overallRiskLevel | string | 是 | 取 findings 最高等级 |

`findings[].metrics`（按 riskType 选用）：

| 字段 | 类型 | 适用 | 含义 |
| --- | --- | --- | --- |
| poQty / grQty / invoiceQty | number | ③ | 订购/实收/开票数量 |
| qtyDiff / qtyDiffPct | number | ③ | 数量差及百分比 |
| overAmount | number | ③ | 超开金额（价税合计） |
| poUnitPrice / invoiceUnitPrice | number | ③ | 单价 |
| poTaxRate / invoiceTaxRate | number | ⑥ | 税率 |
| expectedCategoryRate | number | ⑥ | category 默认税率 |
| taxDelta | number | ⑥ | 少计税为正、多计税为负 |
| outlierInvoiceIds | string[] | ⑥ | 偏离默认税率的发票 |
| duplicateKey | string | ⑤ | `invoiceCode+invoiceNo` |
| duplicateCount | number | ⑤ | 重复次数 |

## 示例

用户：「PO-01332 三单是否匹配？」

```json
{
  "skill": "p2p-three-way-match-skill",
  "agent": "TransactionRiskAgent",
  "subject": {"poId": "PO-01332", "grId": "GR-000289", "invoiceId": "INV-004349", "supplierId": "VEN-0069"},
  "queries": [
    {"tool": "po-query", "args": {"poId": "PO-01332"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "gr-query", "args": {"poId": "PO-01332"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "invoice-query", "args": {"purchaseOrderId": "PO-01332"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "approval-query", "args": {"businessId": "PO-01332", "keyword": "补货"}, "ok": true, "totalCount": 0, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "少货多付 / 数量/金额异常",
      "riskLevel": "高风险",
      "facts": ["GR 实收 62，发票数量 100，相对入库数量差 61.29%（差 38 件）", "超开金额约 77,690 元"],
      "metrics": {"poQty": 100, "grQty": 62, "invoiceQty": 100, "qtyDiff": 38, "qtyDiffPct": 61.29, "overAmount": 77690},
      "rootCause": "短收仍按订单全额开票，且无补货或分批收货审批",
      "mitigation": {
        "queried": true,
        "queryArgs": {"businessId": "PO-01332", "keyword": "补货"},
        "approvalIds": [],
        "approvalStatus": "NOT_FOUND",
        "resolved": false,
        "detail": "ERP 未检索到分批收货或补货协议审批"
      },
      "recommendation": "暂停付款，要求补货或开具红字发票后再匹配",
      "openQuestions": [],
      "evidenceRefs": [
        {"tool": "po-query", "id": "PO-01332"},
        {"tool": "gr-query", "id": "GR-000289"},
        {"tool": "invoice-query", "id": "INV-004349"}
      ]
    }
  ],
  "overallRiskLevel": "高风险"
}
```

对照：`PO-01489` 数量差 4%、超开约 3,012 元 → 中风险；`PO-01615` 有 `APP-GR-01615-202505` 补货审批 → 低风险（已消解）；`PO-04009` 无 GR → 证据不足。

## 边界

- 不调查拆单避审（交给 `split-order-audit-skill`），不调查付款是否重复或收款账户是否异常。
- 不要改动或特殊对待宁波恒远物流（VEN-S001）既有三单；可以查询，但不要把它当成需要改造的样本。
- 发票日期早于入库日期、数量金额一致时，按时间差低风险，把「是否已过账」放入 `openQuestions`，不要升为高风险。
- 禁止声称已阅读全量发票原文；只能基于 summary / sample / artifact-get / financial-analysis。