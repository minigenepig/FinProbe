# -*- coding: utf-8 -*-
from __future__ import annotations

from .base import BaseRiskAgent


class GeneralQueryAgent(BaseRiskAgent):
    name = "GeneralQueryAgent"
    max_steps = 8
    output_kind = "general"

    def system_prompt(self, skills, subject, extra: str = ""):
        extra = (
            extra
            + """
输出 JSON 字段：skill, intent(policy_qa|document_lookup|clarify|handoff), question, queries, answer,
document, citations, clarifyQuestion, handoff。
禁止输出最终风险等级（高风险/中风险/低风险）。发现专项信号时 intent=handoff 并停止深入调查。
差旅/报销/制度问答不要转 PaymentRiskAgent。
"""
        )
        return super().system_prompt(skills, subject, extra)