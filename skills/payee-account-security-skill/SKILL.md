---
name: payee-account-security-skill
description: 核查付款收款账户是否与供应商主数据一致，识别打入个人账户或未完成变更审批即付款的资金红线问题。在用户询问收款账号、账户变更、打入个人卡时使用；不要用它调查重复付款或三单数量差异。
---

# 异常收款账户审计

所属 Agent：`PaymentRiskAgent`。覆盖风险类型⑧「异常收款账户」。

## 目标

核验付款单收款账户（户名、账号）是否等于供应商主数据登记账户。不一致时必须继续判断收款方类型（个人 / 未登记关联公司 / 本供应商换户），并用《供应商银行账户变更申请》判断风险能否消解。

## 执行步骤

1. 取付款单：`payment-query(paymentId=)` 或 `invoiceId=` / `poId=`。读取 `payeeInfo.payeeName`、`payeeAccountNo`、`payeeBankName`。
2. 取供应商主数据：`vendor-query(supplierId=)`，读取 `name`、`bankAccount`。
3. 比对账号与户名。任一不一致即进入异常路径。
4. 判断收款方类型：个人姓名、未登记的关联公司、仍是本供应商但账号变更。
5. 消解检查：`approval-query(businessId=供应商ID, keyword=银行账户)`。关注是否含财务总监 APPROVE 节点。细则见 [account-rules.md](references/account-rules.md)。
6. 需要制度原文时 `policy-query(keyword=银行账户)`。
7. 根因写成机制：供应商正常换户、虚假变更、出纳选错账户、内外勾结打入个人卡。

## 规则

- 高风险：付款打入第三方个人账户或未登记的关联公司账户，且无任何变更审批。资金已 PAID 时，即使其他字段缺失也按高风险确认。
- 中风险：账户变更申请仍为 PENDING 即发起付款（尤其是已 PAID）。
- 低风险：收款账户与供应商主数据完全一致，或变更已经财务总监审批闭环（COMPLETED + 财务总监 APPROVE）。
- 证据不足：付款单或供应商主数据缺少账号字段，无法比对，且看不出个人收款特征。
- 未查询审批不得说「没有任何变更审批」。查询为 0 写「ERP 未检索到供应商银行账户变更申请」。
- 户名像个人（2–4 个汉字、无「公司/厂/中心/工作室」等）且账号与主数据不同，优先走高风险路径。

## 输出格式

统一调查信封，字段名不可改。

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `payee-account-security-skill` |
| agent | string | 是 | 固定 `PaymentRiskAgent` |
| subject | object | 是 | 必填 `paymentId`、`supplierId`；尽量填 `invoiceId` |
| queries | object[] | 是 | 必须同时有 `payment-query` 与 `vendor-query`；账号不一致时必须有 `approval-query` |
| findings | object[] | 是 | 通常 1 条，`riskType` 固定 `异常收款账户` |
| findings[].riskLevel | string | 是 | `高风险` / `中风险` / `低风险` / `证据不足` |
| findings[].facts | string[] | 是 | 写明主数据账号 vs 付款收款账号、户名 |
| findings[].metrics | object | 是 | 见下表 |
| findings[].rootCause | string | 是 | 资金为何打到该账户 |
| findings[].mitigation | object | 是 | `queried/queryArgs/approvalIds/approvalStatus/resolved/detail` |
| findings[].recommendation | string | 是 | 止付/追回/等待审批闭环/可放行 |
| findings[].openQuestions | string[] | 是 | 无则 `[]` |
| findings[].evidenceRefs | object[] | 是 | 付款 ID、供应商 ID、审批 ID |
| overallRiskLevel | string | 是 | 与主发现一致 |

`findings[].metrics`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| vendorAccountNo | string \| null | 供应商主数据账号 |
| vendorName | string \| null | 供应商名称 |
| payeeAccountNo | string \| null | 付款收款账号 |
| payeeName | string \| null | 付款收款户名 |
| accountMatch | boolean | 账号是否一致 |
| nameMatch | boolean | 户名是否与供应商名称一致 |
| payeeType | string | `供应商本人` / `个人` / `未登记关联公司` / `未知` |
| paymentStatus | string | 付款状态，如 `PAID` |

## 示例

用户：「PAY-00345 收款账户正不正常？」

```json
{
  "skill": "payee-account-security-skill",
  "agent": "PaymentRiskAgent",
  "subject": {"paymentId": "PAY-00345", "invoiceId": "INV-004584", "poId": "PO-01567", "supplierId": "VEN-0021"},
  "queries": [
    {"tool": "payment-query", "args": {"paymentId": "PAY-00345"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "vendor-query", "args": {"supplierId": "VEN-0021"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "approval-query", "args": {"businessId": "VEN-0021", "keyword": "银行账户"}, "ok": true, "totalCount": 0, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "异常收款账户",
      "riskLevel": "高风险",
      "facts": [
        "PAY-00345 已 PAID，收款人陈晓东，账号 6226091234567890123",
        "VEN-0021 深圳腾跃不锈钢制品有限公司 登记账号为 0256471647897085460"
      ],
      "metrics": {
        "vendorAccountNo": "0256471647897085460",
        "vendorName": "深圳腾跃不锈钢制品有限公司",
        "payeeAccountNo": "6226091234567890123",
        "payeeName": "陈晓东",
        "accountMatch": false,
        "nameMatch": false,
        "payeeType": "个人",
        "paymentStatus": "PAID"
      },
      "rootCause": "货款打入第三方个人账户，属于资金红线，未见账户变更审批",
      "mitigation": {
        "queried": true,
        "queryArgs": {"businessId": "VEN-0021", "keyword": "银行账户"},
        "approvalIds": [],
        "approvalStatus": "NOT_FOUND",
        "resolved": false,
        "detail": "ERP 未检索到供应商银行账户变更申请"
      },
      "recommendation": "立即止付/追回，并核查出纳与供应商联系人是否内外勾结",
      "openQuestions": [],
      "evidenceRefs": [
        {"tool": "payment-query", "id": "PAY-00345"},
        {"tool": "vendor-query", "id": "VEN-0021"}
      ]
    }
  ],
  "overallRiskLevel": "高风险"
}
```

对照：`PAY-00353` 收款账号改为 7558120099887766554，变更审批 `APP-VEN-0044-BANK-202507` 仍 PENDING 却已付款 → 中风险。

## 边界

- 不判断同一发票是否付了两次，那是 `payment-audit-skill`。
- 账号一致即低风险，不要因为银行名称写法不同单独升风险；账号或户名不一致才进入异常路径。
- 不要编造财务总监审批节点。nodes 里没有财务总监时，不能说「已经财务总监审批闭环」。
- 个人收款且已 PAID，不得因缺少其他字段改判证据不足。