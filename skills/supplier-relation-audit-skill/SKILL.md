---
name: supplier-relation-audit-skill
description: 排查供应商之间共用税号、银行账号、电话等关联关系，分析是否交叉接单，并检查关联交易申报能否消解。在用户询问关联供应商、疑似同一控制人、串标、重复档案时使用；不要用它做三单数量核对或付款账户调查。
---

# 供应商关联关系审计

所属 Agent：`SupplierRiskAgent`。覆盖风险类型②「供应商之间关联关系风险」。

## 目标

在全量供应商主数据中识别共享标识（税号、银行账号、电话、高度相似名称），再核对其采购订单是否交叉，判断属于真实关联经营、主数据重复建档，还是疑似规避准入。识别后必须查关联交易申报 / 主数据合并审批，判断风险能否消解。

## 执行步骤

1. 调用 `vendor-query` 获取供应商集合。27 家主数据可全部内联；若未来变大，只使用 `summary`（含 `duplicateTaxNo` / `duplicatePhones` / `duplicateBankAccounts`）和 artifact。
2. 用 `financial-analysis` 按 `taxNo`、`bankAccount`、`contactPhone`、`contactName` 分组，找出 `n>1` 的键。名称高度相似（包含关系或去掉公司后缀后相同）作为补充信号，不能单独定为高风险。沙箱只允许 Python，赋值 `result=...`，禁止 `import`。
3. 对命中的每个供应商调用 `po-query(supplierId=...)`，看时间重叠、同一物料、金额规模。PO 列表用 summary / artifact，金额聚合用 `financial-analysis(artifactIds=...)`。
4. 调用 `approval-query(keyword=关联|合并档案|利益冲突)`，必要时再按 `businessId=供应商ID` 补查。
5. 需要制度原文时 `policy-query(keyword=关联交易)`。细则见 [relation-rules.md](references/relation-rules.md)。
6. 归纳根因：真实关联经营、历史简称/分公司重复建档、疑似规避准入。再给出能否消解的结论。

## 规则

- 高风险：不同名称供应商共享同一税号、同一银行账号或同一联系电话，并且存在大额资金或交叉订单（关联主体合计 PO 价税合计 >= 100,000 元，或相近时间承接相同 `itemCode`），且无关联交易申报。
- 中风险：仅部分联系方式或名称高度相似，业务类型不同且金额较小；或可解释为历史主数据重复建档，已启动合并/申报。
- 低风险：标识符无交叉重合。
- 证据不足：关键标识（税号/账号/电话）缺失，无法判断是否同一主体；或 PO/审批查询失败。
- 比较优先级：`taxNo` > `bankAccount` > `contactPhone` > `contactName` > 名称相似。
- 查询结果为空写成「ERP 中未检索到关联交易申报」，不要写成「肯定不存在申报」。若共享银行账号且已实际发生采购/付款，即使申报缺失也可按高风险确认。
- 申报完成不自动消解关联交易，仍须在 `rootCause` 中评估是否交叉接单。

## 输出格式

统一调查信封，字段名不可改。

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| skill | string | 是 | 固定 `supplier-relation-audit-skill` |
| agent | string | 是 | 固定 `SupplierRiskAgent` |
| subject | object | 是 | 可填单个 `supplierId`，全量排查时 `supplierId=null`，并在 `metrics.relatedSupplierIds` 列出 |
| queries | object[] | 是 | `tool/args/ok/totalCount/artifactId` |
| findings | object[] | 是 | 每个冲突键一组；无冲突时输出 1 条低风险发现 |
| findings[].riskType | string | 是 | 固定 `供应商之间关联关系风险` |
| findings[].riskLevel | string | 是 | `高风险` / `中风险` / `低风险` / `证据不足` |
| findings[].facts | string[] | 是 | 写明共享字段、供应商 ID、是否交叉接单 |
| findings[].metrics | object | 是 | 见下表 |
| findings[].rootCause | string | 是 | 关联机制，不能只写「电话相同」 |
| findings[].mitigation | object | 是 | `queried/queryArgs/approvalIds/approvalStatus/resolved/detail`；`approvalStatus` 取值同供应商主信息技能 |
| findings[].recommendation | string | 是 | 合并档案 / 补申报 / 关注定价公允性等 |
| findings[].openQuestions | string[] | 是 | 无则 `[]` |
| findings[].evidenceRefs | object[] | 是 | 供应商 ID、PO ID、审批 ID |
| overallRiskLevel | string | 是 | 取 findings 最高等级 |

`findings[].metrics`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| keyType | string | `taxNo` / `bankAccount` / `contactPhone` / `contactName` / `nameSimilar` |
| keyValue | string | 冲突键；账号电话可保留原文 |
| relatedSupplierIds | string[] | 命中的供应商 ID |
| poOverlap | boolean | 是否存在时间或物料交叉 |
| relatedPoAmountSum | number | 关联主体 PO 价税合计 |
| declarationFound | boolean | 是否检索到关联交易申报 |

## 示例

用户：「供应商里有没有疑似关联或重复建档？」

```python
# financial-analysis code 示例
groups = defaultdict(list)
for v in records:
    key = v.get("contactPhone")
    if key:
        groups[key].append(v.get("id"))
result = {k: ids for k, ids in groups.items() if len(ids) > 1}
```

输出（真实数据：VEN-0095 与 VEN-0123 共用电话 17090604194、联系人陆玉）：

```json
{
  "skill": "supplier-relation-audit-skill",
  "agent": "SupplierRiskAgent",
  "subject": {"supplierId": null, "supplierName": null},
  "queries": [
    {"tool": "vendor-query", "args": {}, "ok": true, "totalCount": 27, "artifactId": null},
    {"tool": "financial-analysis", "args": {"code": "result=..."}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "po-query", "args": {"supplierId": "VEN-0095"}, "ok": true, "totalCount": 1, "artifactId": null},
    {"tool": "approval-query", "args": {"keyword": "关联"}, "ok": true, "totalCount": 0, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "供应商之间关联关系风险",
      "riskLevel": "中风险",
      "facts": [
        "VEN-0095 南通润泽设备维护有限责任公司 与 VEN-0123 润泽设备维护 共用 contactPhone=17090604194、contactName=陆玉",
        "两者 taxNo 与 bankAccount 不同，名称呈全称/简称关系，符合重复建档特征"
      ],
      "metrics": {
        "keyType": "contactPhone",
        "keyValue": "17090604194",
        "relatedSupplierIds": ["VEN-0095", "VEN-0123"],
        "poOverlap": false,
        "relatedPoAmountSum": 0,
        "declarationFound": false
      },
      "rootCause": "历史简称与全称分别建档，共享联系人电话，更像主数据治理问题而非串标",
      "mitigation": {
        "queried": true,
        "queryArgs": {"keyword": "关联"},
        "approvalIds": [],
        "approvalStatus": "NOT_FOUND",
        "resolved": false,
        "detail": "ERP 未检索到关联交易申报或主数据合并审批"
      },
      "recommendation": "合并 VEN-0123 至 VEN-0095 有效档案，并补做关联关系备案",
      "openQuestions": ["两家是否曾交叉承接同一项目，需结合具体时间窗口再查 PO"],
      "evidenceRefs": [
        {"tool": "vendor-query", "id": "VEN-0095"},
        {"tool": "vendor-query", "id": "VEN-0123"}
      ]
    }
  ],
  "overallRiskLevel": "中风险"
}
```

## 边界

- 不做三单数量/单价核对，也不判断付款是否打入个人账户。
- 不要因为名称略相似就升为高风险；高风险必须有共享税号/账号/电话，并且有大额或交叉订单，或共享账号已发生资金。
- 不要把 27 家供应商全量字段在回复里再贴一遍，结论里只保留冲突组。
- 禁止 `financial-analysis` 使用 `import` / 文件读写。