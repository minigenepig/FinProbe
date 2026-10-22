# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_BY_RISK = {
    "少货多付": ["po-query", "gr-query", "invoice-query"],
    "数量金额异常": ["po-query", "gr-query", "invoice-query"],
    "数量/金额异常": ["po-query", "gr-query", "invoice-query"],
    "拆单避审": ["po-query", "approval-query"],
    "重复发票": ["invoice-query"],
    "税率异常": ["po-query", "invoice-query"],
    "重复付款": ["payment-query", "invoice-query"],
    "异常收款账户": ["payment-query", "vendor-query"],
    "供应商主信息": ["vendor-query"],
    "关联关系": ["vendor-query"],
}

SKILL_BY_RISK = {
    "少货多付": "p2p-three-way-match-skill",
    "数量金额异常": "p2p-three-way-match-skill",
    "数量/金额异常": "p2p-three-way-match-skill",
    "重复发票": "p2p-three-way-match-skill",
    "税率异常": "p2p-three-way-match-skill",
    "拆单避审": "split-order-audit-skill",
    "重复付款": "payment-audit-skill",
    "异常收款账户": "payee-account-security-skill",
    "供应商主信息": "supplier-profile-audit-skill",
    "关联关系": "supplier-relation-audit-skill",
}

AGENT_BY_SKILL = {
    "p2p-three-way-match-skill": "TransactionRiskAgent",
    "split-order-audit-skill": "TransactionRiskAgent",
    "payment-audit-skill": "PaymentRiskAgent",
    "payee-account-security-skill": "PaymentRiskAgent",
    "supplier-profile-audit-skill": "SupplierRiskAgent",
    "supplier-relation-audit-skill": "SupplierRiskAgent",
}

FINDING_REQUIRED = ("riskType", "riskLevel", "facts", "rootCause", "mitigation", "recommendation", "openQuestions", "evidenceRefs")
MITIGATION_REQUIRED = ("queried", "queryArgs", "approvalIds", "approvalStatus", "resolved", "detail")
LEVELS = {"高风险", "中风险", "低风险", "证据不足"}
APPROVAL_STATUS = {"COMPLETED", "PENDING", "REJECTED", "NOT_FOUND", "NOT_QUERIED"}


def _skill_for(rtype: str) -> str | None:
    for key, skill in SKILL_BY_RISK.items():
        if key in rtype:
            return skill
    return None


def _follow(rtype: str, tool: str, reason: str) -> dict[str, Any]:
    skill = _skill_for(rtype)
    return {
        "agent": AGENT_BY_SKILL.get(skill or "", "domain"),
        "skill": skill,
        "tool": tool,
        "args": {},
        "reason": reason,
    }


def _tools(evidence: dict[str, Any]) -> set[str]:
    return {str(q.get("tool")) for q in (evidence.get("queries") or []) if q.get("tool")}


def _text(finding: dict[str, Any]) -> str:
    return json.dumps(finding, ensure_ascii=False)


def validate(evidence: dict[str, Any]) -> dict[str, Any]:
    tools = _tools(evidence)
    findings = evidence.get("findings") or []
    rule_findings: list[dict[str, Any]] = []
    semantic_findings: list[dict[str, Any]] = []
    follow: list[dict[str, Any]] = []

    if not findings:
        rule_findings.append({"severity": "major", "message": "没有 findings", "relatedRiskType": None, "relatedIds": []})

    for finding in findings:
        rtype = str(finding.get("riskType") or "")
        level = str(finding.get("riskLevel") or "")
        related_ids = [str(x.get("id")) for x in (finding.get("evidenceRefs") or []) if isinstance(x, dict) and x.get("id")]

        for field in FINDING_REQUIRED:
            if field not in finding:
                rule_findings.append({"severity": "major", "message": f"{rtype or 'finding'} 缺少字段 {field}", "relatedRiskType": rtype or None, "relatedIds": related_ids})

        if level and level not in LEVELS:
            rule_findings.append({"severity": "major", "message": f"{rtype} 的 riskLevel 非法: {level}", "relatedRiskType": rtype or None, "relatedIds": related_ids})

        needed: list[str] = []
        for key, tools_needed in REQUIRED_BY_RISK.items():
            if key in rtype:
                needed.extend(tools_needed)

        blob = _text(finding)
        mentions_approval = any(x in blob for x in ("无审批", "没有审批", "审批不足", "已消解", "未消解", "approval"))
        mitigation = finding.get("mitigation")
        if mentions_approval or (isinstance(mitigation, dict) and mitigation.get("queried") is True):
            needed.append("approval-query")
        if "异常收款账户" in rtype and finding.get("metrics", {}).get("accountMatch") is False:
            needed.append("approval-query")

        for tool in dict.fromkeys(needed):
            if tool not in tools:
                rule_findings.append({"severity": "blocker", "message": f"{rtype or 'finding'} 缺少 {tool} 查询记录", "relatedRiskType": rtype or None, "relatedIds": related_ids})
                follow.append(_follow(rtype, tool, f"补齐 {rtype} 的必查工具"))

        if level in {"高风险", "中风险"} and not finding.get("rootCause"):
            rule_findings.append({"severity": "major", "message": f"{rtype} 未给出根因", "relatedRiskType": rtype or None, "relatedIds": related_ids})

        if isinstance(mitigation, dict):
            for field in MITIGATION_REQUIRED:
                if field not in mitigation:
                    rule_findings.append({"severity": "major", "message": f"{rtype} mitigation 缺少 {field}", "relatedRiskType": rtype or None, "relatedIds": related_ids})
            status = mitigation.get("approvalStatus")
            if status and status not in APPROVAL_STATUS:
                rule_findings.append({"severity": "major", "message": f"{rtype} approvalStatus 非法: {status}", "relatedRiskType": rtype or None, "relatedIds": related_ids})
            if status == "NOT_QUERIED" and any(x in blob for x in ("无审批", "没有审批", "已消解")):
                semantic_findings.append({"severity": "blocker", "message": f"{rtype} 未查询审批却声称无审批或已消解", "relatedRiskType": rtype or None, "relatedIds": related_ids})
                follow.append(_follow(rtype, "approval-query", f"{rtype} 需要补做消解检查"))
        elif mentions_approval:
            semantic_findings.append({"severity": "major", "message": f"{rtype} 谈及审批但 mitigation 不是对象", "relatedRiskType": rtype or None, "relatedIds": related_ids})

        facts = finding.get("facts")
        if facts is not None and not isinstance(facts, list):
            rule_findings.append({"severity": "major", "message": f"{rtype} facts 必须是字符串数组", "relatedRiskType": rtype or None, "relatedIds": related_ids})

    evidence_sufficient = not any(x["severity"] == "blocker" for x in rule_findings + semantic_findings)
    return {
        "skill": "evidence-validation-skill",
        "agent": "EvidenceReviewAgent",
        "ruleFindings": rule_findings,
        "semanticFindings": semantic_findings,
        "evidenceSufficient": evidence_sufficient,
        "followUpTasks": follow,
        "readyForReport": evidence_sufficient,
        "overallRiskLevelSuggested": evidence.get("overallRiskLevel") if evidence_sufficient else None,
        "notes": [],
    }


def main() -> None:
    raw = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8") if len(sys.argv) > 1 else sys.stdin.read())
    print(json.dumps(validate(raw), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()