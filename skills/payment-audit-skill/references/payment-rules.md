# 重复付款口径

## 主口径

按 `invoiceId` 分组，不按供应商分组。同一 PO 下不同发票各付一次，不是重复付款。

- `paidCount = count(status=PAID)`
- `paidSum = sum(PAID paymentAmount)`
- `excessAmount = paidSum - invoice.total`

## 分级

- 高风险：同一发票 `paidCount >= 2`，资金已划转
- 低风险：一对一付款，或第二笔为 PENDING / REJECTED（拦截成功）
- 无中风险档
- 已两笔 PAID 时，即使发票总额暂时缺失，仍按高风险确认，总额问题放 openQuestions

## 消解

`approval-query(businessId=付款ID或发票ID, keyword=重复|拦截)`。  
REJECTED 审批（如 `APP-PAY-DUP-01220`）视为拦截成功。