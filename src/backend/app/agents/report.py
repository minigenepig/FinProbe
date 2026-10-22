# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import REPO_ROOT
from ..errors import AppError
from ..llm.client import LLMClient, LLMError, extract_json
from ..skills_loader import load_skill

TZ = timezone(timedelta(hours=8))


def _load_render():
    scripts = REPO_ROOT / "skills" / "risk-report-generator-skill" / "scripts"
    path = str(scripts)
    if path not in sys.path:
        sys.path.insert(0, path)
    import render_report as module  # type: ignore

    return module.render


class ReportAgent:
    name = "ReportAgent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        *,
        question: str,
        envelopes: list[dict[str, Any]],
        evidence_review: dict[str, Any] | None,
        report_id: str,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if emit:
            emit("agent.started", {"agent": self.name, "skills": ["risk-report-generator-skill"]})
            emit("agent.thought", {"agent": self.name, "thought": "根据已审证据起草报告，不再回查 ERP。"})
        ready = bool((evidence_review or {}).get("readyForReport"))
        skill = load_skill("risk-report-generator-skill")
        payload = {
            "question": question,
            "company": "启衡精密制造有限公司",
            "reportId": report_id,
            "generatedAt": datetime.now(TZ).replace(microsecond=0).isoformat(),
            "envelopes": envelopes,
            "evidenceReview": evidence_review,
            "draft": not ready,
        }
        instruction = f"""你是 ReportAgent。禁止调用 ERP/MCP 查询工具，禁止发明新风险类型。
只使用已审证据。单据 ID 必须来自 evidenceRefs / queries。
公司名称固定为 启衡精密制造有限公司。
overallRiskLevel：高 > 中 > 低；已确认红线不被证据不足稀释。
若 readyForReport=false，只能出草稿，openQuestions 列出缺口，不得写成终稿。

{skill.prompt_block()}

输入：
{json.dumps(payload, ensure_ascii=False)[:14000]}
"""
        try:
            resp = self.llm.chat(
                [
                    {"role": "system", "content": "只输出报告 JSON，字段名不可改。"},
                    {"role": "user", "content": instruction},
                ],
                tools=None,
                temperature=0,
            )
            report = extract_json(resp.content or "")
        except (LLMError, ValueError) as exc:
            raise AppError("LLM_ERROR", f"报告生成失败: {exc}") from exc
        report.setdefault("reportId", report_id)
        report.setdefault("company", "启衡精密制造有限公司")
        report.setdefault("question", question)
        report.setdefault("generatedAt", payload["generatedAt"])
        if not ready:
            report["draft"] = True
            questions = list(report.get("openQuestions") or [])
            for item in (evidence_review or {}).get("ruleFindings") or []:
                if item.get("severity") == "blocker":
                    msg = f"证据缺口：{item.get('message')}"
                    if msg not in questions:
                        questions.append(msg)
            report["openQuestions"] = questions
        render = _load_render()
        markdown = render(report)
        result = {"report": report, "markdown": markdown, "draft": not ready}
        if emit:
            emit(
                "report.completed",
                {
                    "reportId": report.get("reportId"),
                    "overallRiskLevel": report.get("overallRiskLevel"),
                    "draft": not ready,
                },
            )
            emit("agent.completed", {"agent": self.name, "skills": ["risk-report-generator-skill"]})
        return result