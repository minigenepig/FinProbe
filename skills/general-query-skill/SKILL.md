---
name: general-query-skill
description: 处理不属于供应商、三单、付款核心调查的杂项查询，例如制度问答、模糊单据检索、数据探查。在用户问题模棱两可或只是想查一笔单据/一条制度时使用；不要用它替代专项风险调查，也不要在本技能里下风险等级结论。
---

# 通用查询

所属 Agent：`GeneralQueryAgent`。LeadAgent 发现提问模棱两可、或不属于三个 P2P 核心风控域时使用。

## 目标

用最少的查询回答杂项问题：查制度、查一张单据的关键字段、或提出一个澄清问题。一旦出现专项风险信号，必须移交对应 RiskAgent 技能，而不是在本技能里完成调查结论。

## 执行步骤

1. 分类意图：`policy_qa` / `document_lookup` / `clarify` / `handoff`。
2. 若像制度问题，先走 `internal-policy-qa-skill` 的步骤与 `policy-query`，输出对齐该技能的 citations。
3. 若像查单，用最具体的 ID 调用对应 query：`po-query` / `gr-query` / `invoice-query` / `payment-query` / `vendor-query` / `approval-query`。只返回关键字段摘要。
4. 信息不足时只问一个澄清问题，不要同时打所有工具。
5. 若 summary 已出现专项风险信号（同一发票多笔 PAID、数量差超过容差、收款户名为个人、短窗口多笔近红线 PO 等），设置 `intent=handoff` 并停止深入调查。
6. 需要统计时用 `financial-analysis`；需要再看几条明细用 `artifact-get`。禁止要求工具返回全量 74 张发票。

## 规则

- 可使用全部查询类 MCP 工具，但要克制：一次解决一个意图。
- 禁止在本技能输出 `高风险/中风险/低风险` 作为最终风控结论。最多在 `handoff.reason` 里描述观察到的信号。
- 明确的风险调查应转：
  - 供应商档案/准入 → `supplier-profile-audit-skill`
  - 关联供应商 → `supplier-relation-audit-skill`
  - 三单/超开/重复发票/税率 → `p2p-three-way-match-skill`
  - 拆单避审 → `split-order-audit-skill`
  - 重复付款 → `payment-audit-skill`
  - 收款账户 → `payee-account-security-skill`
- 已经在跑复杂跨域调查时，不要用本技能覆盖领域 Agent 结论。
- 查不到单据时如实说「ERP 未检索到」，不要编造。

## 输出格式

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `general-query-skill` |
| intent | string | 是 | `policy_qa` / `document_lookup` / `clarify` / `handoff` |
| question | string | 是 | 用户原话 |
| queries | object[] | 是 | 实际调用；未调用则为 `[]` |
| answer | string | 是 | 给用户的简短答复 |
| document | object \| null | 是 | 查单时的关键字段摘要，否则 `null` |
| document.id | string | 否 | 单据 ID |
| document.type | string | 否 | `PO` / `GR` / `Invoice` / `Payment` / `Vendor` / `Approval` |
| document.fields | object | 否 | 只放关键字段，如金额、日期、供应商、状态 |
| citations | object[] | 否 | 制度问答时必填，结构同 internal-policy-qa-skill |
| clarifyQuestion | string \| null | 是 | 需要澄清时给一个问题，否则 `null` |
| handoff | object \| null | 是 | `{agent, skill, reason, signal}`，否则 `null` |
| artifactId | string \| null | 否 | 若结果写入 artifact |

`document.fields` 建议键：`supplierId`、`supplierName`、`amount`、`date`、`status`、`relatedIds`。不要把 items 全量数组塞进来。

## 示例

用户：「帮我看一下 PO-00005 是什么。」

```json
{
  "skill": "general-query-skill",
  "intent": "document_lookup",
  "question": "帮我看一下 PO-00005 是什么。",
  "queries": [
    {"tool": "po-query", "args": {"poId": "PO-00005"}, "ok": true, "totalCount": 1, "artifactId": null}
  ],
  "answer": "PO-00005 是一张已批准的采购订单，供应商 VEN-0044，价税合计约 94,012.52 元，订单日 2024-07-18。当前问题只是查单，未做风险调查。",
  "document": {
    "id": "PO-00005",
    "type": "PO",
    "fields": {
      "supplierId": "VEN-0044",
      "status": "APPROVED",
      "date": "2024-07-18",
      "amount": 94012.52,
      "relatedIds": []
    }
  },
  "clarifyQuestion": null,
  "handoff": null
}
```

若查询付款 summary 出现同一发票两笔 PAID：

```json
{
  "skill": "general-query-skill",
  "intent": "handoff",
  "question": "看一下 INV-004207 的付款。",
  "queries": [
    {"tool": "payment-query", "args": {"invoiceId": "INV-004207"}, "ok": true, "totalCount": 2, "artifactId": null}
  ],
  "answer": "INV-004207 检索到 2 笔付款且均为 PAID，已超出通用查询范围，转交重复付款审计。",
  "document": {"id": "INV-004207", "type": "Invoice", "fields": {"relatedIds": ["PAY-00265", "PAY-00895"]}},
  "clarifyQuestion": null,
  "handoff": {
    "agent": "PaymentRiskAgent",
    "skill": "payment-audit-skill",
    "reason": "同一发票多笔 PAID",
    "signal": "invoiceIdsWithMultiplePaid"
  }
}
```

## 边界

- 不下风险等级，不做根因与消解结案。
- 不在一次回答里跑完供应商+三单+付款全套工具。
- 不把大结果集贴给用户。
- 用户明确说「查风险/是否违规」时，不要停留在本技能。