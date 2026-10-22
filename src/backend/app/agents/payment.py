# -*- coding: utf-8 -*-
from __future__ import annotations

from .base import BaseRiskAgent


class PaymentRiskAgent(BaseRiskAgent):
    name = "PaymentRiskAgent"

    def system_prompt(self, skills, subject, extra: str = ""):
        extra = extra + """
只调查重复付款、异常收款账户。不要重做三单数量匹配。
重复付款没有中风险档，riskLevel 只能是 高风险 / 低风险 / 证据不足。
同一 PO 下不同发票的多笔付款不是重复付款；主口径是 invoiceId。
输出统一调查信封。
"""
        return super().system_prompt(skills, subject, extra)