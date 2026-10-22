---
name: internal-policy-qa-skill
description: 回答企业内控、采购付款、供应商管理、发票合规、差旅报销等制度问题。在用户问标准、限额、审批门槛、税率适用、报销规则，且不需要调查具体单据风险时使用；一旦用户要判断某张 PO/发票/付款是否违规，应转给对应调查技能。
---

# 企业内部制度问答

各领域 Agent 与 GeneralQueryAgent 共用。优先用本技能回答制度问题，不要把差旅报销标准误判成供应商或付款调查。

## 目标

基于现行制度原文回答用户的规则/限额/审批门槛问题，给出可追溯的条款引用。目标是答对制度，而不是调查某张单据是否违规。

## 执行步骤

1. 判断问题属于哪本制度：采购与付款内控、供应商管理办法、发票合规指引、差旅与报销、关联交易申报。可先读 [policies.md](references/policies.md)。
2. 需要原文核实时调用 `policy-query(keyword=用户关键词)`。返回的是命中片段，全文在 artifact 中，不要假装已读完全文。
3. 核对生效日期与版本：供应商管理办法 V2.0 自 2024-11-01 现行，V1.0 废止，禁止引用 V1.0 条款。
4. 用条款原文回答，并注明制度名称、版本、条目。数字必须来自制度，不得估算。
5. 若制度未覆盖，明确说「现有制度未规定」，不要编造数字。
6. 若用户把制度和某张具体 PO/发票/付款联系起来，先回答制度阈值，再 `handoff` 给对应调查技能，不要在本技能里下风险等级。

## 规则

- 只引用现行有效版本。V1.0 供应商管理办法仅可在用户明确问历史版本时作为对照，并标注「已废止」。
- 差旅标准（住宿/交通/餐饮）走本技能，不转 PaymentRiskAgent。
- 三单容差、拆单红线、重复付款、异常账户的阈值可以在本技能直接回答；要查某张单据是否踩线，必须移交调查技能。
- 「这家供应商能不能用 13% 税率」属于调查，不是纯 QA：制度给出类别-税率表后，应 handoff 到 `p2p-three-way-match-skill` 或 `supplier-profile-audit-skill`。
- 不得把制度未规定的内容补成「行业惯例」。

## 输出格式

本技能不是调查信封，使用以下 JSON：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `internal-policy-qa-skill` |
| intent | string | 是 | 固定 `policy_qa` |
| question | string | 是 | 用户原话 |
| citations | object[] | 是 | 每条含 `docId`、`title`、`version`、`effectiveDate`、`article`、`quote` |
| answer | string | 是 | 面向用户的结论，必须能被 citations 支撑 |
| notCovered | boolean | 是 | 制度是否未规定该问题 |
| handoff | object \| null | 是 | 无需续查则为 `null`，否则 `{agent, skill, reason}` |
| queries | object[] | 是 | 实际调用的 `policy-query`；若只读了本地 reference 也要注明 `tool=reference` |

`citations` 单条字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| docId | string \| null | policy-query 返回的文档 ID，未知则 null |
| title | string | 如 `差旅与报销管理制度` |
| version | string | 如 `V1.2` / `V2.0` / `现行` |
| effectiveDate | string \| null | 生效日期 |
| article | string | 如 `第二条` |
| quote | string | 原文摘句，不要改写数字 |

## 示例

用户：「帮我查一下公司内部报销制度关于差旅费的标准是什么。」

```json
{
  "skill": "internal-policy-qa-skill",
  "intent": "policy_qa",
  "question": "帮我查一下公司内部报销制度关于差旅费的标准是什么。",
  "queries": [
    {"tool": "policy-query", "args": {"keyword": "差旅"}, "ok": true, "totalCount": 1, "artifactId": null}
  ],
  "citations": [
    {
      "docId": null,
      "title": "差旅与报销管理制度",
      "version": "V1.2",
      "effectiveDate": "2025-01-01",
      "article": "第二条",
      "quote": "北京、上海、广州、深圳：500 元/晚；省会及计划单列市：400 元/晚；其他城市：350 元/晚。"
    },
    {
      "docId": null,
      "title": "差旅与报销管理制度",
      "version": "V1.2",
      "effectiveDate": "2025-01-01",
      "article": "第四条",
      "quote": "一线城市餐饮补贴 150 元/天；其他城市 100 元/天。出发和返回当天按半天计。"
    }
  ],
  "answer": "现行《差旅与报销管理制度》V1.2：住宿北上广深 500 元/晚、省会及计划单列市 400 元/晚、其他城市 350 元/晚；餐饮一线城市 150 元/天、其他城市 100 元/天。交通优先高铁二等座，机票仅经济舱。该问题不属于供应商或付款调查。",
  "notCovered": false,
  "handoff": null
}
```

## 边界

- 不查询、不评价具体 PO/GR/Invoice/Payment 是否违规。
- 不把差旅报销混入 P2P 三单流程。
- 不引用已废止 V1.0 作为现行依据。
- 不要把 `policy-query` 的片段当成已读完全文；需要更多条款时用新的 keyword 再查，或读本地 `references/policies.md`。