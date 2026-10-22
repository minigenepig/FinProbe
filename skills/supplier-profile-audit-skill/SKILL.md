---
name: supplier-profile-audit-skill
description: 调查供应商主数据完整性、频繁变更与准入合规，分析根因并检查审批能否消解。在用户询问供应商档案、税号/银行账户缺失或变更、经营范围、准入资格时使用；不要用它做三单匹配、拆单或付款调查。
---

# 供应商主信息审计

所属 Agent：`SupplierRiskAgent`。覆盖风险类型①「供应商主信息异常」。

## 目标

对指定供应商完成主数据完整性、变更频率与准入合规调查，输出可被 EvidenceReviewAgent / ReportAgent 消费的结构化 JSON。发现异常后必须继续分析根因，并用 `approval-query` 判断风险能否被合规审批消解，不能停在「字段缺失/有变更」。

## 执行步骤

1. 定位供应商。优先 `vendor-query(supplierId=)`；用户只给名称/税号/账号时分别用 `name` / `taxNo` / `bankAccount` / `keyword`。禁止直接读取 `mock-erp/data` JSON。
2. 核对必填字段：`id`、`code`、`name`、`taxNo`、`category`、`paymentTermsDays`、`contactName`、`contactPhone`、`bankAccount`、`active`。把空值写入 `metrics.missingFields`。
3. 调用 `approval-query(businessId=供应商ID, keyword=变更|经营范围|银行|档案)`，记录 `approvalStatus` 与 `nodes`。未调用不得声称「没有审批」。
4. 需要核对现行条款时调用 `policy-query(keyword=供应商管理办法)`，只引用 V2.0（2024-11-01 起现行），不得引用已废止 V1.0。细则见 [admission-rules.md](references/admission-rules.md)。
5. 若发现变更或缺失后供应商仍在采购，可用 `po-query(supplierId=)` 看近期订单规模。列表结果只使用 `summary` / `sample` / `artifactId`，不要要求返回全量 PO。
6. 归纳根因，只能从这些机制中选并写清依据：主数据治理遗留、供应商真实变更但审批未闭环、审批缺失的频繁改档、无法定位供应商。
7. 做消解判定，填写 `findings[]`、`overallRiskLevel`、`recommendation`、`openQuestions`。若发现银行账户变更待审且已有付款线索，用 `handoff` 交给 `payee-account-security-skill`，不要在本技能里下付款结论。

## 规则

- 高风险：供应商核心信息（税号、银行账户）频繁变更，且审批流程不完整。
- 中风险：供应商主数据关键字段缺失，或历史重复档案未清理。
- 低风险：主数据完整；如有变更，已有完整审批（`approvalStatus=COMPLETED` 且关键节点为 APPROVE）。
- 证据不足：无法定位供应商，或审批系统查询失败。查询结果 `totalCount=0` 应写「ERP 未检索到对应审批」，不得写成「肯定不存在审批」。
- 未调用 `approval-query` 时，`mitigation.approvalStatus` 必须为 `NOT_QUERIED`，不得给出「无审批支撑」的最终表述。
- 不得把非关键字段缺失直接升为高风险。若核心红线已能确认，不因次要字段缺失降为证据不足。
- 大结果走 artifact + `financial-analysis` / `artifact-get`，禁止把全量明细贴进结论。

## 输出格式

调查类技能统一信封，本技能必须输出如下 JSON（不要改字段名）：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `supplier-profile-audit-skill` |
| agent | string | 是 | 固定 `SupplierRiskAgent` |
| subject | object | 是 | 调查对象。至少填 `supplierId`、`supplierName` |
| queries | object[] | 是 | 实际调用过的工具。每项含 `tool`、`args`、`ok`、`totalCount`、`artifactId` |
| findings | object[] | 是 | 本技能通常 1 条，`riskType` 固定为 `供应商主信息异常` |
| findings[].riskLevel | string | 是 | `高风险` / `中风险` / `低风险` / `证据不足` |
| findings[].facts | string[] | 是 | 已核实事实，必须引用供应商 ID 与字段名 |
| findings[].metrics | object | 是 | 见下方 metrics 表 |
| findings[].rootCause | string | 是 | 根因机制，不能只复述「缺字段」 |
| findings[].mitigation | object | 是 | 消解检查。字段：`queried`(bool)、`queryArgs`(object)、`approvalIds`(string[])、`approvalStatus`(`COMPLETED`/`PENDING`/`REJECTED`/`NOT_FOUND`/`NOT_QUERIED`)、`resolved`(bool)、`detail`(string) |
| findings[].recommendation | string | 是 | 处置建议 |
| findings[].openQuestions | string[] | 是 | 未确认事项，无则 `[]` |
| findings[].evidenceRefs | object[] | 是 | `{ "tool": "vendor-query", "id": "VEN-0044" }` |
| overallRiskLevel | string | 是 | 与 findings 聚合：高 > 中 > 低；仅当无法确认也无法排除时为证据不足 |
| handoff | object[] | 否 | 需要其他技能续查时填写 `{agent, skill, reason}` |

`findings[].metrics` 字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| missingFields | string[] | 空值字段名 |
| changeApprovalCount | number | 检索到的档案/账户/经营范围变更审批数 |
| frequentChange | boolean | 是否构成频繁变更（同类变更 12 个月内 >= 2 次且无完整闭环） |
| active | boolean \| null | 供应商是否有效 |

## 示例

用户：「查一下 VEN-0044 供应商档案是否合规。」

工具调用：`vendor-query(supplierId=VEN-0044)`，再 `approval-query(businessId=VEN-0044, keyword=变更)`。

输出：

```json
{
  "skill": "supplier-profile-audit-skill",
  "agent": "SupplierRiskAgent",
  "subject": {"supplierId": "VEN-0044", "supplierName": "佛山仁和供应链管理股份有限公司"},
  "queries": [
    {"tool": "vendor-query", "args": {"supplierId": "VEN-0044"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "approval-query", "args": {"businessId": "VEN-0044", "keyword": "变更"}, "ok": true, "totalCount": 1, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "供应商主信息异常",
      "riskLevel": "低风险",
      "facts": [
        "VEN-0044 主数据 name/taxNo/bankAccount/contactPhone/category 均有值且 active=true",
        "检索到银行账户变更审批 APP-VEN-0044-BANK-202507，状态 PENDING，尚未闭环"
      ],
      "metrics": {"missingFields": [], "changeApprovalCount": 1, "frequentChange": false, "active": true},
      "rootCause": "供应商发起银行账户变更，主数据当前仍完整，不属于频繁改档",
      "mitigation": {
        "queried": true,
        "queryArgs": {"businessId": "VEN-0044", "keyword": "变更"},
        "approvalIds": ["APP-VEN-0044-BANK-202507"],
        "approvalStatus": "PENDING",
        "resolved": true,
        "detail": "主数据本身完整；账户变更是否允许付款交由付款域核查"
      },
      "recommendation": "主数据档案可继续使用；若存在付款，必须转异常收款账户技能核验收款账号",
      "openQuestions": ["PENDING 的银行账户变更是否已实际用于付款"],
      "evidenceRefs": [
        {"tool": "vendor-query", "id": "VEN-0044"},
        {"tool": "approval-query", "id": "APP-VEN-0044-BANK-202507"}
      ]
    }
  ],
  "overallRiskLevel": "低风险",
  "handoff": [
    {"agent": "PaymentRiskAgent", "skill": "payee-account-security-skill", "reason": "存在 PENDING 银行账户变更，需核对应付款单收款账号"}
  ]
}
```

## 边界

- 只调查供应商主数据与准入/变更审批，不判断少货多付、拆单、重复付款、异常收款账户是否成立。
- 差旅报销标准、发票抬头规则属于 `internal-policy-qa-skill`，不要在本技能下风险结论。
- 不要把「ERP 未检索到审批」写成「肯定没有审批」。
- 不要编造供应商或审批记录，也不要直接打开 JSON 文件当查询结果。