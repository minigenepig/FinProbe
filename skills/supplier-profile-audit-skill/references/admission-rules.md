# 供应商主数据审计细则

## 必查字段

`id`, `code`, `name`, `taxNo`, `category`, `paymentTermsDays`, `contactName`, `contactPhone`, `bankAccount`, `active`

空值写入 `metrics.missingFields`。`creditCode` 若存在应与 `taxNo` 一致，但不作为单独红线。

## 制度要点

- V2.0（2024-11-01 起现行）：同一纳税人识别号只允许一条有效档案。
- 经营范围、纳税人性质、主体名称或银行账户变更：采购部 10 个工作日内更新，并附变更文件。
- V1.0 已废止，不得引用其「总分公司可分别建档」「30 个工作日更新银行账户」条款。

## 分级补充

- 频繁变更：同类核心字段（税号或银行账户）在 12 个月内变更审批 >= 2 次，且至少一次未闭环。
- 中风险：任一必查字段缺失，或历史重复档案未清理。
- 低风险：字段完整；变更审批 `COMPLETED` 且关键节点 APPROVE。
- 证据不足：`vendor-query` 定位失败，或审批查询报错。`totalCount=0` 不是查询失败。

## 消解示例

- `APP-VEN-S001-202512` 这类经营范围变更审批且 COMPLETED：类别/税率变更有据。
- `APP-VEN-0044-BANK-202507` PENDING：主数据当前仍完整，付款是否可用新账号交给 `payee-account-security-skill`。
- 仅有申请没有采购/财务闭环：不能消解。