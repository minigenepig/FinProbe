# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import REPO_ROOT

RISK_TYPES = [
    "供应商主信息异常",
    "供应商之间关联关系风险",
    "少货多付 / 数量/金额异常",
    "拆单避审",
    "重复发票",
    "税率异常",
    "重复付款",
    "异常收款账户",
]

LEVEL_RANK = {"高风险": 3, "中风险": 2, "证据不足": 1, "低风险": 0}

_GOLD_CANDIDATES = [
    REPO_ROOT / "evals" / "gold" / "cross_supplier_v1.json",
    REPO_ROOT / "evals" / "gold" / "cross_supplier_v1.draft.json",
]


def gold_path() -> Path | None:
    for path in _GOLD_CANDIDATES:
        if path.is_file():
            return path
    return None


def _document_ids(finding: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    subject = finding.get("subject") if isinstance(finding.get("subject"), dict) else {}
    for key in ("poId", "grId", "invoiceId", "paymentId", "supplierId"):
        value = subject.get(key)
        if value and str(value) not in ids:
            ids.append(str(value))
    for item in finding.get("keyEvidence") or []:
        if isinstance(item, dict) and item.get("id"):
            text = str(item["id"])
            if text not in ids:
                ids.append(text)
    return ids


def _compact_finding(finding: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    for item in finding.get("keyEvidence") or []:
        if isinstance(item, dict):
            evidence.append({"tool": item.get("tool"), "id": item.get("id")})
    return {
        "riskType": finding.get("riskType"),
        "riskLevel": finding.get("riskLevel"),
        "domain": finding.get("domain"),
        "agent": finding.get("agent"),
        "skill": finding.get("skill"),
        "rootCause": finding.get("rootCause"),
        "recommendation": finding.get("recommendation"),
        "facts": finding.get("facts") or [],
        "metrics": finding.get("metrics") or {},
        "evidence": evidence,
        "documentIds": _document_ids(finding),
        "approvalStatus": finding.get("approvalStatus"),
        "openQuestions": finding.get("openQuestions") or [],
    }


@lru_cache(maxsize=1)
def load_supplier_risk_board() -> dict[str, Any]:
    path = gold_path()
    empty: dict[str, Any] = {
        "source": None,
        "datasetId": None,
        "status": None,
        "goldFrozen": False,
        "vendorCount": 0,
        "riskTypes": RISK_TYPES,
        "levelCounts": {},
        "domainCounts": {},
        "typeLevelCounts": {},
        "vendors": [],
        "disclaimer": "未找到供应商全量调查评测集。",
    }
    if path is None:
        return empty

    data = json.loads(path.read_text(encoding="utf-8"))
    level_counts: Counter[str] = Counter()
    domain_counts: Counter[str] = Counter()
    type_level_counts: dict[str, Counter[str]] = defaultdict(Counter)
    vendors: list[dict[str, Any]] = []

    for case in data.get("cases") or []:
        subject = case.get("subject") if isinstance(case.get("subject"), dict) else {}
        raw_findings = case.get("expectedFindings") or []
        findings = [_compact_finding(item) for item in raw_findings if isinstance(item, dict)]
        type_levels = {name: "低风险" for name in (case.get("expectedBackgroundLowRisk") or RISK_TYPES)}
        for item in findings:
            risk_type = str(item.get("riskType") or "未知")
            risk_level = str(item.get("riskLevel") or "低风险")
            type_levels[risk_type] = risk_level
            domain_counts[str(item.get("domain") or "未知")] += 1
            type_level_counts[risk_type][risk_level] += 1
        overall = str(case.get("expectedOverallRiskLevel") or "低风险")
        level_counts[overall] += 1
        vendors.append(
            {
                "caseId": case.get("caseId"),
                "supplierId": subject.get("supplierId"),
                "name": subject.get("supplierName") or subject.get("name"),
                "category": subject.get("category"),
                "alias": subject.get("alias"),
                "overallRiskLevel": overall,
                "findingCount": len(findings),
                "mustDetectCount": sum(
                    1 for item in raw_findings if isinstance(item, dict) and item.get("mustDetect")
                ),
                "findings": findings,
                "typeLevels": type_levels,
                "notes": case.get("notes"),
                "question": (case.get("input") or {}).get("question"),
            }
        )

    vendors.sort(
        key=lambda row: (-LEVEL_RANK.get(str(row.get("overallRiskLevel")), 0), str(row.get("supplierId") or ""))
    )
    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    return {
        "source": rel,
        "datasetId": data.get("datasetId"),
        "status": data.get("status"),
        "goldFrozen": bool(data.get("goldFrozen")),
        "vendorCount": len(vendors),
        "riskTypes": data.get("riskTypes") or RISK_TYPES,
        "levelCounts": dict(level_counts),
        "domainCounts": dict(domain_counts),
        "typeLevelCounts": {key: dict(value) for key, value in type_level_counts.items()},
        "vendors": vendors,
        "disclaimer": "27家供应商采购到付款全量调查标注结果，供复审对照；点击调查风险可发起一次新的 Agent 调查。",
    }
