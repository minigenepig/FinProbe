---
name: evidence-validation-skill
description: 对前序 Agent 的证据链做两层校验：规则层检查必查工具与关键字段，语义层检查结论是否被证据支撑、消解是否真的发生。用于复杂跨域任务的 EvidenceReviewAgent；发现缺口时产出补查任务，不要自己编造 ERP 数据。
---

# 证据完整性与语义校验

所属 Agent：`EvidenceReviewAgent`。复杂跨域任务必须经过本技能，形成「调查 → 审核 → 补查 → 结论」闭环。

## 目标

审核前序领域 Agent 输出的调查 JSON，确认：必查工具已调用、关键单据 ID 能在 evidence 中找到、风险等级与阈值一致、消解不是「没看见就是没有」、根因不是只复述差异。输出是否可以交给 ReportAgent，以及需要哪些 follow-up。

## 执行步骤

1. 读取前序证据链 JSON（结构见 [evidence-schema.md](references/evidence-schema.md)）。无 ERP 写入权限，不要自己调用 query 去补数；需要补数时只产出 `followUpTasks`。
2. 规则层：用脚本或逐项检查。可运行 `python skills/evidence-validation-skill/scripts/validate_evidence.py evidence.json` 作为第一层辅助，但脚本不能替代语义判断。
3. 核对每个声称被引用的单据 ID 是否出现在 `queries` / `evidenceRefs` / `documents` 中。
4. 按风险类型核对必查工具：
   - 少货多付 / 数量金额异常：po-query + gr-query + invoice-query
   - 拆单避审：po-query + approval-query
   - 重复发票：invoice-query
   - 税率异常：po-query + invoice-query（类别匹配还需 vendor-query）
   - 重复付款：payment-query + invoice-query
   - 异常收款账户：payment-query + vendor-query；账号不一致还必须有 approval-query
   - 供应商主信息：vendor-query；谈及审批则必须有 approval-query
   - 关联关系：vendor-query；谈及交叉接单还需 po-query
5. 凡作出「无审批 / 审批不足 / 已消解」的结论，必须有 `approval-query` 记录（允许 `totalCount=0`）。
6. 语义层：核对阈值、根因、消解、跨 Agent 是否矛盾、证据不足是否被误用。
7. 输出 `ruleFindings`、`semanticFindings`、`followUpTasks`、`readyForReport`。blocker 未解决时 `readyForReport=false`。

## 规则

规则层：

- 列表类结果只应保存 summary/sample/artifactId。若结论声称「已阅读全部 N 张发票原文」却没有 artifact，记 blocker。
- 缺必查工具记 `severity=blocker` 并生成 followUpTask。
- 高/中风险缺少 `rootCause` 记 `severity=major`。

语义层：

- 风险等级必须与项目规划阈值一致。例如数量差 4% 不得判高风险；两笔 PAID 不得判低风险。
- 消解必须发生在已查询的审批上。`approvalStatus=NOT_QUERIED` 却写「无审批」是语义错误。
- 根因不能只复述差异（「数量不一致」不是根因，「短收仍按订单全额开票」才是）。
- 跨 Agent 矛盾必须指出，例如三单说未付款，付款域却有 PAID。
- 不得把数据缺失直接等同于违规；也不得把未查询到审批直接等同于不存在审批。
- 若现有证据已足以确认红线，不因非关键字段缺失改判证据不足。

补查：

- `followUpTasks[]` 每项：`agent`、`skill`、`tool`、`args`、`reason`。
- 不要编造 ERP 数据，不要代替领域 Agent 改风险等级；可以建议「待补查后再判定」。

## 输出格式

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `evidence-validation-skill` |
| agent | string | 是 | 固定 `EvidenceReviewAgent` |
| taskId | string \| null | 否 | 前序任务 ID |
| ruleFindings | object[] | 是 | 规则层问题，无则 `[]` |
| semanticFindings | object[] | 是 | 语义层问题，无则 `[]` |
| evidenceSufficient | boolean | 是 | 是否不存在 blocker |
| followUpTasks | object[] | 是 | 补查任务，无则 `[]` |
| readyForReport | boolean | 是 | 无 blocker 且无必须先补查的语义矛盾时为 true |
| overallRiskLevelSuggested | string \| null | 否 | 仅当证据充分时给出建议等级，否则 null |
| notes | string[] | 是 | 给 ReportAgent 的注意事项，无则 `[]` |

`ruleFindings` / `semanticFindings` 单条：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| severity | string | `blocker` / `major` / `minor` |
| message | string | 问题描述 |
| relatedRiskType | string \| null | 关联风险类型 |
| relatedIds | string[] | 相关单据 ID |

`followUpTasks` 单条：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| agent | string | 如 `TransactionRiskAgent` |
| skill | string | 如 `p2p-three-way-match-skill` |
| tool | string | 如 `approval-query` |
| args | object | 建议参数 |
| reason | string | 为什么必须补 |

## 示例

前序把 PO-01489 数量差 4% 判成高风险，且未查审批：

```json
{
  "skill": "evidence-validation-skill",
  "agent": "EvidenceReviewAgent",
  "taskId": "T-01489",
  "ruleFindings": [
    {
      "severity": "blocker",
      "message": "少货多付结论写无审批，但 queries 中没有 approval-query",
      "relatedRiskType": "少货多付 / 数量/金额异常",
      "relatedIds": ["PO-01489"]
    }
  ],
  "semanticFindings": [
    {
      "severity": "major",
      "message": "数量差约 4%，阈值上应为中风险，不能判高风险",
      "relatedRiskType": "少货多付 / 数量/金额异常",
      "relatedIds": ["PO-01489"]
    }
  ],
  "evidenceSufficient": false,
  "followUpTasks": [
    {
      "agent": "TransactionRiskAgent",
      "skill": "p2p-three-way-match-skill",
      "tool": "approval-query",
      "args": {"businessId": "PO-01489", "keyword": "补货"},
      "reason": "补齐消解检查后再分级"
    }
  ],
  "readyForReport": false,
  "overallRiskLevelSuggested": null,
  "notes": ["补查审批后按中风险模板出报告，除非出现有效补货审批可消解为低风险"]
}
```

## 边界

- 不直接查 ERP，不改原始单据，不编造缺失的审批。
- 不在证据未齐时放行报告。
- 不做制度问答，不重写风险报告正文。
- 脚本 `validate_evidence.py` 只覆盖规则层子集，语义层必须人工/模型审。