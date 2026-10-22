# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from ..config import REPO_ROOT
from ..llm.client import LLMClient, LLMError, extract_json
from ..skills_loader import load_skill


def _load_validate():
    scripts = REPO_ROOT / "skills" / "evidence-validation-skill" / "scripts"
    path = str(scripts)
    if path not in sys.path:
        sys.path.insert(0, path)
    import validate_evidence as module  # type: ignore

    return module.validate


class EvidenceReviewAgent:
    name = "EvidenceReviewAgent"

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def run(
        self,
        *,
        envelopes: list[dict[str, Any]],
        question: str,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        cancel_check=None,
    ) -> dict[str, Any]:
        if emit:
            emit("agent.started", {"agent": self.name, "skills": ["evidence-validation-skill"]})
            emit("agent.thought", {"agent": self.name, "thought": "审核证据袋：必查工具是否都跑过、审批是否查过、结论能否闭环。"})
        bag = _merge_envelopes(envelopes)
        validate = _load_validate()
        rule_layer = validate(bag)
        skill = load_skill("evidence-validation-skill")
        semantic = {
            "semanticFindings": [],
            "followUpTasks": [],
            "notes": [],
        }
        if self.llm.configured():
            prompt = f"""你是 EvidenceReviewAgent。禁止调用任何 ERP/MCP 查询工具。
只审核下面的证据袋和规则层结果。不要编造审批，不要改原始 facts。
输出 JSON：semanticFindings, followUpTasks, notes。
followUpTasks 项为 {{agent, skill, tool, args, reason}}。
{skill.prompt_block()}

用户问题：{question}

证据袋：
{json.dumps(bag, ensure_ascii=False)[:14000]}

规则层：
{json.dumps(rule_layer, ensure_ascii=False)[:6000]}
"""
            try:
                resp = self.llm.chat(
                    [
                        {"role": "system", "content": "只输出 JSON。不查 ERP。"},
                        {"role": "user", "content": prompt},
                    ],
                    tools=None,
                    temperature=0,
                )
                semantic = extract_json(resp.content or "")
            except (LLMError, ValueError) as exc:
                semantic["notes"] = [f"语义层审核失败，仅保留规则层: {exc}"]
        follow = list(rule_layer.get("followUpTasks") or []) + list(semantic.get("followUpTasks") or [])
        semantic_findings = list(rule_layer.get("semanticFindings") or []) + list(
            semantic.get("semanticFindings") or []
        )
        blockers = [
            item
            for item in (rule_layer.get("ruleFindings") or []) + semantic_findings
            if (item or {}).get("severity") == "blocker"
        ]
        ready = not blockers
        result = {
            "skill": "evidence-validation-skill",
            "agent": self.name,
            "ruleFindings": rule_layer.get("ruleFindings") or [],
            "semanticFindings": semantic_findings,
            "evidenceSufficient": ready,
            "followUpTasks": follow,
            "readyForReport": ready,
            "overallRiskLevelSuggested": bag.get("overallRiskLevel") if ready else None,
            "notes": semantic.get("notes") or [],
        }
        if emit:
            emit(
                "evidence.completed",
                {
                    "readyForReport": ready,
                    "blockerCount": len(blockers),
                    "followUpCount": len(follow),
                },
            )
            emit("agent.completed", {"agent": self.name, "skills": ["evidence-validation-skill"]})
        return result


def _merge_envelopes(envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    queries: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    subject: dict[str, Any] = {}
    levels: list[str] = []
    for env in envelopes:
        if not isinstance(env, dict):
            continue
        for key, value in (env.get("subject") or {}).items():
            if value and not subject.get(key):
                subject[key] = value
        queries.extend(env.get("queries") or [])
        findings.extend(env.get("findings") or [])
        if env.get("overallRiskLevel"):
            levels.append(env["overallRiskLevel"])
    rank = {"高风险": 3, "中风险": 2, "低风险": 1, "证据不足": 0}
    confirmed = [lv for lv in levels if lv in rank and lv != "证据不足"]
    overall = None
    if confirmed:
        overall = max(confirmed, key=lambda item: rank[item])
    elif levels:
        overall = "证据不足"
    return {
        "subject": subject,
        "queries": queries,
        "findings": findings,
        "overallRiskLevel": overall,
        "envelopes": [
            {"skill": e.get("skill"), "agent": e.get("agent"), "overallRiskLevel": e.get("overallRiskLevel")}
            for e in envelopes
            if isinstance(e, dict)
        ],
    }