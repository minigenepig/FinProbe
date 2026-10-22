# -*- coding: utf-8 -*-
from __future__ import annotations

from .base import BaseRiskAgent


class TransactionRiskAgent(BaseRiskAgent):
    name = "TransactionRiskAgent"

    def system_prompt(self, skills, subject, extra: str = ""):
        extra = extra + """
只调查少货多付/数量/金额异常、拆单避审、重复发票、税率异常。不要判断重复付款或收款账户。
数量差% = (发票数量 - 入库数量) / 入库数量 × 100；入库为 0 则证据不足。
不得把 receivedBy / warehouse_location 相同当作拆单高风险充分条件。
税率：SERVICE 默认 6%，MATERIAL/OUTSOURCE/OFFICE 默认 13%。PO 与发票税率相同不是低风险充分条件。
供应商全量（有 supplierId、无单张 poId）时：
- po-query(supplierId, clusterWindowDays=5)、invoice-query(supplierId)、gr-query(supplierId) 各至多 1 次列表。
- 大结果只看 summary/sample/artifact，用 financial-analysis(artifactIds=...) 聚合。
- 禁止按 PO 循环 gr-query 或按单据循环 approval-query；只对异常样本 artifact-get，消解用 supplierId/代表 PO 各查一次审批。
financial-analysis：禁止 import / type / getattr；金额先 to_number；必须赋值 result=...。
输出统一调查信封。subject 尽量补齐 invoiceId 与 grId，供后续 PaymentRiskAgent 使用。
"""
        return super().system_prompt(skills, subject, extra)
