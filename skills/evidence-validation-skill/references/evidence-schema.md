# 证据链 JSON 结构

领域 Agent 应输出统一调查信封，EvidenceReviewAgent 按此审核。

```json
{
  "skill": "p2p-three-way-match-skill",
  "agent": "TransactionRiskAgent",
  "subject": {"supplierId": "VEN-0069", "poId": "PO-01332", "grId": "GR-000289", "invoiceId": "INV-004349", "paymentId": null},
  "queries": [
    {"tool": "po-query", "args": {"poId": "PO-01332"}, "ok": true, "totalCount": 1, "artifactId": null}
  ],
  "findings": [
    {
      "riskType": "少货多付 / 数量/金额异常",
      "riskLevel": "高风险",
      "facts": ["GR 实收 62，发票数量 100"],
      "metrics": {"qtyDiffPct": 61.29, "overAmount": 77690},
      "rootCause": "短收仍按订单全额开票且无补货审批",
      "mitigation": {
        "queried": true,
        "queryArgs": {"businessId": "PO-01332", "keyword": "补货"},
        "approvalIds": [],
        "approvalStatus": "NOT_FOUND",
        "resolved": false,
        "detail": "ERP 未检索到分批收货或补货协议审批"
      },
      "recommendation": "暂停付款",
      "openQuestions": [],
      "evidenceRefs": [{"tool": "gr-query", "id": "GR-000289"}]
    }
  ],
  "overallRiskLevel": "高风险",
  "handoff": []
}
```

## 审核要点

- `queries[].tool` 必须覆盖该风险类型的必查工具
- 引用的 ID 必须出现在 `evidenceRefs` 或 `queries`
- `mitigation.approvalStatus=NOT_QUERIED` 时不得声称无审批或已消解
- 列表查询应带 `artifactId` 或明确 `totalCount` 很小
- 不要把领域 Agent 的原始大列表再复制一份；只保留 ID 与摘要