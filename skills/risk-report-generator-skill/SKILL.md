---
name: risk-report-generator-skill
description: 将已审定的调查结论写成结构化风险报告 JSON 和 Markdown。在 EvidenceReview 完成或用户明确要求出报告时使用；不要在证据未齐、readyForReport=false 时编写最终结论。
---

# 风险报告生成

所属 Agent：`ReportAgent`。输入是领域 Agent + EvidenceReview 的结论，不是再去翻 ERP。

## 目标

把已经审定的 findings 写成一份可归档的风险报告：同时输出 JSON 与 Markdown。报告必须包含风险等级、对象、事实、根因、消解情况与建议，并保留待确认问题，不得把开放问题写成既定事实。

## 执行步骤

1. 确认输入已通过证据审核，或用户明确要求「先出当前报告」。若 `readyForReport=false`，只可输出草稿并在 `openQuestions` 中列出缺口，不得写成最终结论。
2. 只使用已确认证据。单据 ID 必须来自前序 `evidenceRefs`。
3. 按风险类型逐条写入 `findings`：风险名称、等级、对象、事实、根因、消解、建议。
4. 计算 `overallRiskLevel`：高 > 中 > 低；仅当全部关键发现都是证据不足时才用证据不足。已确认红线不被其他缺口稀释。
5. 同时写 JSON 和 Markdown。可用 `python skills/risk-report-generator-skill/scripts/render_report.py report.json [out.md]`。模板见 [report-template.md](assets/report-template.md)，字段契约见 [report-schema.json](assets/report-schema.json)。
6. 引用单据 ID，不贴全量明细，不重新查询 ERP。

## 规则

- 等级用：`高风险` / `中风险` / `低风险` / `证据不足`。低风险若等于无风险，在说明里写「未发现故意违规」。
- `facts` 必须可核对：数量、金额、日期、状态、ID。
- `rootCause` 写机制，不写「存在异常」。
- `mitigation` 写审批查询结果，沿用「ERP 未检索到…」表述。
- `openQuestions` 放尚未确认事项；不要删掉 EvidenceReview 留下的缺口。
- 公司名称固定为「启衡精密制造有限公司」，除非输入另有指定。
- 不要发明新的风险类型名称，使用项目规划中的八类名称。

## 输出格式

必须同时给出 `report.json` 对象和由其渲染的 Markdown。JSON 字段如下：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| reportId | string | 是 | `RPT-YYYYMMDD-XXX` |
| company | string | 是 | 默认 `启衡精密制造有限公司` |
| generatedAt | string | 是 | ISO-8601 |
| question | string | 是 | 用户原问题 |
| overallRiskLevel | string | 是 | `高风险` / `中风险` / `低风险` / `证据不足` |
| summary | string | 是 | 不超过 8 句的结论摘要 |
| findings | object[] | 是 | 分项发现，无风险时仍给 1 条低风险说明 |
| openQuestions | string[] | 是 | 待确认问题，无则 `[]` |
| evidenceRefs | object[] | 是 | `{tool,id}` 证据索引 |

`findings` 单条：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| riskType | string | 是 | 八类风险之一，或制度问答不走本技能 |
| riskLevel | string | 是 | 与调查技能同一套枚举 |
| subject | object | 是 | 至少含 `supplierId` / `poId` / `invoiceId` / `paymentId` 之一 |
| facts | string[] | 是 | 已核实事实 |
| rootCause | string | 是 | 根因 |
| mitigation | string | 是 | 消解情况的自然语言（由前序 mitigation.detail 转写） |
| recommendation | string | 是 | 处置建议 |

Markdown 结构必须含：结论摘要、分项发现、待确认问题、证据索引。不要输出未在 JSON 中出现的新事实。

## 示例

输入：PO-01332 三单高风险且 EvidenceReview `readyForReport=true`。

```json
{
  "reportId": "RPT-20260520-001",
  "company": "启衡精密制造有限公司",
  "generatedAt": "2026-05-20T10:00:00+08:00",
  "question": "PO-01332 三单是否匹配？",
  "overallRiskLevel": "高风险",
  "summary": "PO-01332 入库 62、开票 100，相对入库数量差超过 10% 且超开金额远超 10000 元，ERP 未检索到补货或分批收货审批，构成少货多付高风险，建议暂停付款。",
  "findings": [
    {
      "riskType": "少货多付 / 数量/金额异常",
      "riskLevel": "高风险",
      "subject": {"supplierId": "VEN-0069", "poId": "PO-01332", "grId": "GR-000289", "invoiceId": "INV-004349"},
      "facts": ["GR 实收 62，发票数量 100", "超开金额约 77690 元", "无补货/分批收货审批记录"],
      "rootCause": "短收仍按订单全额开票且无补货审批",
      "mitigation": "ERP 未检索到分批收货或补货协议审批，风险未消解",
      "recommendation": "暂停付款并要求补货或红字发票"
    }
  ],
  "openQuestions": [],
  "evidenceRefs": [
    {"tool": "po-query", "id": "PO-01332"},
    {"tool": "gr-query", "id": "GR-000289"},
    {"tool": "invoice-query", "id": "INV-004349"}
  ]
}
```

## 边界

- 不重新调查，不调用 query 工具翻 ERP，不修改前序 facts。
- EvidenceReview 未放行时，不得输出看起来像终稿的报告。
- 不把证据不足写成违规，也不把低风险写成「完全没问题」而不提已核对范围。
- 不在报告中粘贴全量发票/订单数组。