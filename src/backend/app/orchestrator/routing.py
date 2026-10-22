# -*- coding: utf-8 -*-
"""LeadAgent routing. Heuristic first; LLM may confirm but must not invent new risk types."""
from __future__ import annotations

import re
from typing import Any

from ..schemas import RouteObject, Subject

SUPPLIER_SKILLS = ("supplier-profile-audit-skill", "supplier-relation-audit-skill")
TX_SKILLS = ("p2p-three-way-match-skill", "split-order-audit-skill")
PAY_SKILLS = ("payment-audit-skill", "payee-account-security-skill")
ALL_INVESTIGATION_SKILLS = SUPPLIER_SKILLS + TX_SKILLS + PAY_SKILLS

AGENT_FOR_SKILL = {
    "supplier-profile-audit-skill": "SupplierRiskAgent",
    "supplier-relation-audit-skill": "SupplierRiskAgent",
    "p2p-three-way-match-skill": "TransactionRiskAgent",
    "split-order-audit-skill": "TransactionRiskAgent",
    "payment-audit-skill": "PaymentRiskAgent",
    "payee-account-security-skill": "PaymentRiskAgent",
    "internal-policy-qa-skill": "GeneralQueryAgent",
    "general-query-skill": "GeneralQueryAgent",
    "evidence-validation-skill": "EvidenceReviewAgent",
    "risk-report-generator-skill": "ReportAgent",
}

ID_SPECS = (
    ("supplierId", re.compile(r"\bVEN-[A-Z0-9]+\b", re.I)),
    ("poId", re.compile(r"\bPO-\d+\b", re.I)),
    ("grId", re.compile(r"\bGR-\d+\b", re.I)),
    ("invoiceId", re.compile(r"\bINV-\d+\b", re.I)),
    ("paymentId", re.compile(r"\bPAY-\d+\b", re.I)),
)

NAME_RE = re.compile(
    r"([\u4e00-\u9fff]{2,20}(?:有限责任公司|股份有限公司|有限公司|公司|铜业))"
)
TAXNO_RE = re.compile(r"\b(\d{15,20}|[0-9A-Z]{15,20})\b")
LEADIN_RE = re.compile(
    r"^(请)?(帮我)?(全面)?(排查|调查|审计)?(一下)?(供应商)?"
)
NOISE = ("全面排查", "请全面排查", "排查供应商", "调查供应商", "供应商")

POLICY_HINTS = (
    "制度",
    "差旅",
    "报销",
    "管理办法",
    "内控",
    "住宿标准",
    "交通费",
    "餐饮标准",
    "审批门槛",
    "限额",
    "怎么规定",
    "条款",
    "差旅费",
)
LOOKUP_HINTS = ("查一下", "查一查", "帮我看", "是什么", "调阅", "详情", "基本信息")
INVEST_HINTS = ("风险", "排查", "调查", "违规", "能否付款", "能不能付款", "是否匹配", "异常", "全面", "审计", "结案")
CROSS_HINTS = ("全面排查", "从采购到付款", "全链路", "所有风险", "综合调查", "全面调查")
POP_HINTS = ("关联供应商", "重复建档", "同税号", "共用电话", "同一控制人", "串标")
PROFILE_HINTS = ("档案", "准入", "主信息", "改档", "税号缺失", "银行账户缺失")
RELATION_HINTS = ("关联", "重复建档", "同电话", "同税号", "关联交易")
THREE_HINTS = ("三单", "超开", "短收", "少货", "数量", "匹配", "重复发票", "税率", "开票")
SPLIT_HINTS = ("拆单", "化整为零", "避审", "红线")
PAYMENT_HINTS = ("重复付款", "一票多付", "付了两次", "多付了")
PAYEE_HINTS = ("收款账户", "个人卡", "打到个人", "打入个人", "账号不一致", "收款账号")


def _has_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(h in text for h in hints)


def extract_subject(question: str) -> Subject:
    subject = Subject()
    for field, pattern in ID_SPECS:
        match = pattern.search(question)
        if match:
            setattr(subject, field, match.group(0).upper())
    if not subject.supplierId:
        cleaned = question
        for noise in NOISE:
            cleaned = cleaned.replace(noise, " ")
        cleaned = LEADIN_RE.sub("", cleaned.strip())
        name_match = NAME_RE.search(cleaned) or NAME_RE.search(question)
        if name_match:
            name = name_match.group(1)
            for noise in ("全面排查", "排查", "调查", "请"):
                name = name.replace(noise, "")
            subject.supplierName = name or name_match.group(1)
    tax = TAXNO_RE.search(question)
    if tax and not question.upper().startswith(tax.group(1)[:3]):
        raw = tax.group(1)
        if raw.startswith("91") and len(raw) >= 15:
            subject.taxNo = raw
    return subject


def _skills_to_agents(skills: list[str]) -> list[str]:
    agents: list[str] = []
    for skill in skills:
        agent = AGENT_FOR_SKILL.get(skill)
        if agent and agent not in agents:
            agents.append(agent)
    return agents


def infer_want_report(mode: str, explicit: bool | None) -> bool:
    if explicit is not None:
        return explicit
    return mode in {"single", "cross"}


def decide_route(question: str, want_report: bool | None = None) -> RouteObject:
    text = (question or "").strip()
    subject = extract_subject(text)
    has_doc = any([subject.poId, subject.grId, subject.invoiceId, subject.paymentId])
    has_supplier = bool(subject.supplierId or subject.supplierName or subject.taxNo)
    has_entity = has_doc or has_supplier

    is_policy = _has_any(text, POLICY_HINTS) and not _has_any(text, INVEST_HINTS)
    # 差旅/报销/制度问答即使出现「标准」也不转付款域
    travel_only = _has_any(text, ("差旅", "报销", "住宿", "交通费", "餐饮")) and not has_doc
    if travel_only and not _has_any(text, ("付款账户", "重复付款", "供应商")):
        is_policy = True

    is_cross = _has_any(text, CROSS_HINTS) or ("全面" in text and (has_supplier or has_doc))
    is_pop = _has_any(text, POP_HINTS) and not has_doc
    is_lookup = _has_any(text, LOOKUP_HINTS) and not _has_any(text, INVEST_HINTS) and not is_cross

    picked: list[str] = []
    if _has_any(text, PROFILE_HINTS):
        picked.append("supplier-profile-audit-skill")
    if _has_any(text, RELATION_HINTS) or is_pop:
        picked.append("supplier-relation-audit-skill")
    if _has_any(text, THREE_HINTS):
        picked.append("p2p-three-way-match-skill")
    if _has_any(text, SPLIT_HINTS):
        picked.append("split-order-audit-skill")
    if _has_any(text, PAYMENT_HINTS):
        picked.append("payment-audit-skill")
    if _has_any(text, PAYEE_HINTS):
        picked.append("payee-account-security-skill")
    # de-dup keep order
    seen: set[str] = set()
    skills: list[str] = []
    for item in picked:
        if item not in seen:
            seen.add(item)
            skills.append(item)

    if is_policy and not is_cross and not skills:
        route = RouteObject(
            mode="policy_qa",
            scope="policy",
            subject=subject,
            agents=["GeneralQueryAgent"],
            skills=["internal-policy-qa-skill"],
            reason="纯制度/差旅/报销问题，不进入付款或供应商调查",
            wantReport=False,
        )
        route.wantReport = infer_want_report(route.mode, want_report)
        return route

    if is_pop and not has_doc:
        route = RouteObject(
            mode="single" if not is_cross else "cross",
            scope="population",
            subject=subject,
            agents=["SupplierRiskAgent"],
            skills=["supplier-relation-audit-skill"],
            reason="全量供应商关联/重复建档排查",
        )
        route.wantReport = infer_want_report(route.mode, want_report if want_report is not None else True)
        return route

    if not has_entity and not is_pop:
        route = RouteObject(
            mode="clarify",
            scope="lookup",
            subject=subject,
            agents=["GeneralQueryAgent"],
            skills=["general-query-skill"],
            reason="缺少可绑定的供应商或单据 ID",
            clarifyQuestion="请提供供应商名称/编号，或 PO、发票、付款单号，以便开始调查。",
            wantReport=False,
        )
        route.wantReport = infer_want_report(route.mode, want_report)
        return route

    if is_lookup and not is_cross and not skills:
        route = RouteObject(
            mode="lookup",
            scope="lookup",
            subject=subject,
            agents=["GeneralQueryAgent"],
            skills=["general-query-skill"],
            reason="查单/探查，先不进入风险结案",
            wantReport=False,
        )
        route.wantReport = infer_want_report(route.mode, want_report)
        return route

    if is_cross or (has_supplier and _has_any(text, ("全面", "排查", "调查")) and not has_doc and not skills):
        skills = list(ALL_INVESTIGATION_SKILLS)
        route = RouteObject(
            mode="cross",
            scope="supplier" if has_supplier and not has_doc else ("document" if has_doc else "supplier"),
            subject=subject,
            agents=_skills_to_agents(skills),
            skills=skills,
            reason="用户要求全面排查或从采购到付款，跨域协作",
        )
        route.wantReport = infer_want_report(route.mode, want_report if want_report is not None else True)
        return route

    if has_doc and not skills:
        # 点名单据且要结论/付款/匹配 → 文档范围默认三单+付款+主信息
        if _has_any(text, INVEST_HINTS) or _has_any(text, ("付款", "结案", "报告")):
            skills = [
                "p2p-three-way-match-skill",
                "payment-audit-skill",
                "payee-account-security-skill",
                "supplier-profile-audit-skill",
            ]
            mode: str = "cross"
            reason = "点名单据并要求给出调查/付款结论"
        else:
            skills = ["p2p-three-way-match-skill"] if subject.poId or subject.invoiceId else (
                ["payment-audit-skill", "payee-account-security-skill"] if subject.paymentId else ["p2p-three-way-match-skill"]
            )
            mode = "single" if len(_skills_to_agents(skills)) == 1 else "cross"
            reason = "点名单据，按默认文档范围调查"
        route = RouteObject(
            mode=mode,  # type: ignore[arg-type]
            scope="document",
            subject=subject,
            agents=_skills_to_agents(skills),
            skills=skills,
            reason=reason,
        )
        route.wantReport = infer_want_report(route.mode, want_report)
        return route

    if has_supplier and not skills:
        skills = list(ALL_INVESTIGATION_SKILLS)
        route = RouteObject(
            mode="cross",
            scope="supplier",
            subject=subject,
            agents=_skills_to_agents(skills),
            skills=skills,
            reason="点名供应商但未限定单一风险类型，按供应商全量调查",
        )
        route.wantReport = infer_want_report(route.mode, want_report if want_report is not None else True)
        return route

    if not skills:
        skills = ["general-query-skill"]
        route = RouteObject(
            mode="lookup",
            scope="lookup",
            subject=subject,
            agents=["GeneralQueryAgent"],
            skills=skills,
            reason="未能判定专项风险，先做最少查询",
            wantReport=False,
        )
        route.wantReport = infer_want_report(route.mode, want_report)
        return route

    agents = _skills_to_agents(skills)
    mode = "cross" if len(agents) >= 2 else "single"
    if has_doc:
        scope = "document"
    elif has_supplier:
        scope = "supplier"
    else:
        scope = "lookup"
    # 文档范围：拆单/关联仅当用户要全面或已选中这些 skill
    if scope == "document" and mode == "cross" and "supplier-profile-audit-skill" not in skills:
        if _has_any(text, INVEST_HINTS):
            skills = list(dict.fromkeys(skills + ["supplier-profile-audit-skill"]))
            agents = _skills_to_agents(skills)
            mode = "cross" if len(agents) >= 2 else "single"
    route = RouteObject(
        mode=mode,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        subject=subject,
        agents=agents,
        skills=skills,
        reason="按用户点名的风险类型分派领域 Agent",
    )
    route.wantReport = infer_want_report(route.mode, want_report)
    return route


def payment_must_wait(subject: Subject) -> bool:
    return not bool(subject.invoiceId or subject.paymentId)


def merge_subject(base: Subject, extra: dict[str, Any] | None) -> Subject:
    data = base.model_dump()
    for key, value in (extra or {}).items():
        if key in data and value and not data.get(key):
            data[key] = value
    return Subject.model_validate(data)


def aggregate_risk_level(levels: list[str]) -> str | None:
    rank = {"高风险": 3, "中风险": 2, "低风险": 1, "证据不足": 0}
    cleaned = [lv for lv in levels if lv in rank]
    if not cleaned:
        return None
    confirmed = [lv for lv in cleaned if lv != "证据不足"]
    pool = confirmed or cleaned
    return max(pool, key=lambda item: rank[item])