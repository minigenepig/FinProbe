---
name: payment-audit-skill
description: 调查重复付款：同一发票或订单是否关联多笔付款、金额是否超额、重复申请是否被拦截。在用户询问重复支付、一票多付、付款失败重试时使用；不要用它判断收款账户是否打入个人卡，也不要做三单数量匹配。
---

# 重复付款审计

所属 Agent：`PaymentRiskAgent`。覆盖风险类型⑦「重复付款」。

## 目标

确认同一发票或同一订单是否被支付多次，以及资金是否已经划转。发现多笔付款后必须区分 PAID / PENDING / REJECTED，核对金额是否超过发票总额，分析根因，并检查拦截审批是否已消解风险。

## 执行步骤

1. 用发票或订单拉付款：优先 `payment-query(invoiceId=)`，否则 `payment-query(poId=)`。`summary.invoiceIdsWithMultiplePaid` 是第一信号。
2. 对可疑 `invoiceId` 再查一次 `payment-query(invoiceId=)`，核对 `paymentId`、`status`、`paymentAmount`、付款日期。
3. 用 `invoice-query(invoiceId=)` 取发票 `total`，比较 `sum(PAID paymentAmount)` 是否超过发票总额。多张付款用 `financial-analysis` 分组求和。
4. 消解检查：若存在第二笔 `PENDING`/`REJECTED`，或 `approval-query(businessId=付款ID/发票ID, keyword=重复|拦截)` 显示拒绝，则无资金损失，低风险。细则见 [payment-rules.md](references/payment-rules.md)。
5. 需要制度原文时 `policy-query(keyword=重复付款)`。
6. 根因写成机制：系统未做幂等、人工重复提交、部分付款后的二次付、拦截失效。不要只写「有两笔付款」。

## 规则

- 高风险：同一发票两次及以上 `status=PAID`，资金已实际划转。即使其他次要字段缺失，只要两笔 PAID 已确认，就按高风险，不降为证据不足。
- 低风险：一对一精准付款，或重复付款已被拦截（第二笔 `PENDING` / `REJECTED`）。
- 证据不足：找不到发票总额，无法判断是否超额，且目前只能看到一笔付款或状态不明。若已两笔 PAID，仍先按高风险确认。
- 规划中本类型无「中风险」档，不要自行发明中风险。
- 未查询审批不得说「没有任何拦截」。查询为 0 写「ERP 未检索到拦截/拒绝审批」。
- 按 `invoiceId` 分组是主口径，同一 `poId` 多笔付款若对应不同发票，不是重复付款。

## 输出格式

统一调查信封，字段名不可改。

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `payment-audit-skill` |
| agent | string | 是 | 固定 `PaymentRiskAgent` |
| subject | object | 是 | 必填 `invoiceId`；尽量填 `poId`、`supplierId`、`paymentId` |
| queries | object[] | 是 | 至少 `payment-query`；比较超额时必须有 `invoice-query` |
| findings | object[] | 是 | 通常 1 条，`riskType` 固定 `重复付款` |
| findings[].riskLevel | string | 是 | `高风险` / `低风险` / `证据不足`（无中风险） |
| findings[].facts | string[] | 是 | 列出全部 paymentId、status、金额 |
| findings[].metrics | object | 是 | 见下表 |
| findings[].rootCause | string | 是 | 重复发生的机制 |
| findings[].mitigation | object | 是 | `queried/queryArgs/approvalIds/approvalStatus/resolved/detail` |
| findings[].recommendation | string | 是 | 追回资金 / 保持拦截 / 无需处理 |
| findings[].openQuestions | string[] | 是 | 无则 `[]` |
| findings[].evidenceRefs | object[] | 是 | 付款 ID 与发票 ID |
| overallRiskLevel | string | 是 | 与主发现一致 |

`findings[].metrics`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| invoiceTotal | number \| null | 发票价税合计 |
| paymentIds | string[] | 全部相关付款 |
| paidCount | number | status=PAID 的笔数 |
| paidSum | number | PAID 金额合计 |
| excessAmount | number | `paidSum - invoiceTotal`，无法计算时为 0 并在 openQuestions 说明 |
| intercepted | boolean | 是否存在 PENDING/REJECTED 拦截 |

## 示例

用户：「INV-004207 是不是付了两次？」

```json
{
  "skill": "payment-audit-skill",
  "agent": "PaymentRiskAgent",
  "subject": {"invoiceId": "INV-004207", "poId": "PO-01190", "paymentId": "PAY-00265"},
  "queries": [
    {"tool": "payment-query", "args": {"invoiceId": "INV-004207"}, "ok": true, "totalCount": 2, "artifactId": null},
    {"tool": "invoice-query", "args": {"invoiceId": "INV-004207"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "approval-query", "args": {"keyword": "重复", "businessId": "INV-004207"}, "ok": true, "totalCount": 0, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "重复付款",
      "riskLevel": "高风险",
      "facts": [
        "INV-004207 对应 PAY-00265 与 PAY-00895，两笔均为 PAID，金额均为 134662.09",
        "发票总额 134662.09，已付合计 269324.18，超额 134662.09"
      ],
      "metrics": {
        "invoiceTotal": 134662.09,
        "paymentIds": ["PAY-00265", "PAY-00895"],
        "paidCount": 2,
        "paidSum": 269324.18,
        "excessAmount": 134662.09,
        "intercepted": false
      },
      "rootCause": "同一发票全额被成功支付两次，系统未拦截重复提交",
      "mitigation": {
        "queried": true,
        "queryArgs": {"keyword": "重复", "businessId": "INV-004207"},
        "approvalIds": [],
        "approvalStatus": "NOT_FOUND",
        "resolved": false,
        "detail": "ERP 未检索到重复付款拦截或拒绝审批，资金已划转"
      },
      "recommendation": "立即冻结后续付款并启动重复付款追回",
      "openQuestions": [],
      "evidenceRefs": [
        {"tool": "payment-query", "id": "PAY-00265"},
        {"tool": "payment-query", "id": "PAY-00895"},
        {"tool": "invoice-query", "id": "INV-004207"}
      ]
    }
  ],
  "overallRiskLevel": "高风险"
}
```

对照：`INV-004237` 对应 `PAY-00273`(PAID) + `PAY-00896`(REJECTED)，拦截审批 `APP-PAY-DUP-01220` → 低风险。

## 边界

- 不判断收款账户是否与供应商主数据一致，那是 `payee-account-security-skill`。
- 不因为同一 PO 有多张不同发票的付款就报重复付款。
- 不要把 REJECTED/PENDING 当成已划转资金。
- 不要要求工具一次返回全部历史付款原文；先看 summary 再按 invoiceId 深查。