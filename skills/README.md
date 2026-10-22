# Skills 索引

每个 Skill 必须是独立目录，内含 `SKILL.md`，必要时含 `scripts/`、`references/`、`assets/`。

## SKILL.md 统一结构

YAML frontmatter 只放 `name`、`description`（description 写清做什么、何时用、不要误用到什么）。正文固定六个一级标题，顺序不可变：

1. **目标** — 要产出什么，发现异常后必须继续查根因和消解
2. **执行步骤** — 按顺序调用哪些 MCP Tool、如何用 summary/artifact
3. **规则** — 风险分级、消解、证据不足、禁止事项
4. **输出格式** — 每个字段的名称、类型、是否必填、取值和含义
5. **示例** — 真实单据 ID 的输入/输出
6. **边界** — 不做什么、交给谁

调查类 Skill 的 JSON 统一信封：

| 字段 | 含义 |
| --- | --- |
| skill / agent | 技能名与所属 Agent |
| subject | 供应商/PO/GR/发票/付款 ID |
| queries | 实际调用过的工具及 totalCount、artifactId |
| findings[] | 每条含 riskType、riskLevel、facts、metrics、rootCause、mitigation、recommendation、openQuestions、evidenceRefs |
| overallRiskLevel | 高 > 中 > 低；仅关键证据缺失时为证据不足 |
| handoff | 可选，转给其他技能 |

`mitigation.approvalStatus` 只能是 `COMPLETED` / `PENDING` / `REJECTED` / `NOT_FOUND` / `NOT_QUERIED`。  
`riskLevel` 只能是 `高风险` / `中风险` / `低风险` / `证据不足`（重复付款无中风险档）。

风险类型名称必须与《项目规划.md》一致：供应商主信息异常、供应商之间关联关系风险、少货多付 / 数量/金额异常、拆单避审、重复发票、税率异常、重复付款、异常收款账户。

## 技能列表

| Skill | Agent | 工具 |
| ---- | ---- | ---- |
| supplier-profile-audit-skill | SupplierRiskAgent | vendor-query, approval-query, policy-query |
| supplier-relation-audit-skill | SupplierRiskAgent | vendor-query, po-query, financial-analysis, approval-query |
| internal-policy-qa-skill | 各 Agent 共用 | policy-query + references/policies.md |
| p2p-three-way-match-skill | TransactionRiskAgent | po/gr/invoice-query, financial-analysis, approval-query |
| split-order-audit-skill | TransactionRiskAgent | po-query, gr-query, approval-query, financial-analysis |
| payment-audit-skill | PaymentRiskAgent | payment-query, invoice-query, approval-query |
| payee-account-security-skill | PaymentRiskAgent | payment-query, vendor-query, approval-query |
| general-query-skill | GeneralQueryAgent | 全部查询工具；不下风险结论 |
| evidence-validation-skill | EvidenceReviewAgent | 不直接查 ERP，审证据链 |
| risk-report-generator-skill | ReportAgent | 基于已审证据出 JSON+MD |

调查类 Skill 都要求：识别风险 → 分析原因 → 用 approval-query 做消解检查 → 再给等级。