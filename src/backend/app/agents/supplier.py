# -*- coding: utf-8 -*-
from __future__ import annotations

from .base import BaseRiskAgent


class SupplierRiskAgent(BaseRiskAgent):
    name = "SupplierRiskAgent"

    def system_prompt(self, skills, subject, extra: str = ""):
        extra = extra + """
只调查供应商主信息异常、供应商之间关联关系风险。不要判断三单、拆单或付款。
输出统一调查信封：skill, agent, subject, queries, findings[], overallRiskLevel，可选 handoff。
findings[].riskType 只能是「供应商主信息异常」或「供应商之间关联关系风险」。
"""
        return super().system_prompt(skills, subject, extra)