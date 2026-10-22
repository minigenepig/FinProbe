# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..agents.base import AgentCancelled, degraded_envelope
from ..agents.evidence_review import EvidenceReviewAgent
from ..agents.general import GeneralQueryAgent
from ..agents.payment import PaymentRiskAgent
from ..agents.report import ReportAgent
from ..agents.supplier import SupplierRiskAgent
from ..agents.transaction import TransactionRiskAgent
from ..errors import AppError
from ..llm.client import LLMClient, LLMError, extract_json
from ..mcp_client.client import MCPClient
from ..schemas import ChatMessage, InvestigationSnapshot, RouteObject, Subject
from ..store.sqlite import InvestigationStore, now_iso
from .routing import (
    ALL_INVESTIGATION_SKILLS,
    PAY_SKILLS,
    SUPPLIER_SKILLS,
    TX_SKILLS,
    aggregate_risk_level,
    decide_route,
    merge_subject,
    payment_must_wait,
)

LOCATE_TOOLS = {"vendor-query", "po-query"}


class LeadOrchestrator:
    def __init__(self, store: InvestigationStore, mcp: MCPClient, llm: LLMClient) -> None:
        self.store = store
        self.mcp = mcp
        self.llm = llm
        self.general = GeneralQueryAgent(mcp, llm)
        self.supplier = SupplierRiskAgent(mcp, llm)
        self.transaction = TransactionRiskAgent(mcp, llm)
        self.payment = PaymentRiskAgent(mcp, llm)
        self.evidence = EvidenceReviewAgent(llm)
        self.report = ReportAgent(llm)
        self._bag_lock = __import__("threading").Lock()

    def run(self, inv_id: str) -> None:
        try:
            self._run(inv_id)
        except AppError as exc:
            self._fail(inv_id, exc.code, exc.message, exc.retryable)
        except LLMError as exc:
            self._fail(inv_id, "LLM_ERROR", str(exc), exc.retryable)
        except Exception as exc:  # noqa: BLE001
            self._fail(inv_id, "LLM_ERROR", f"编排失败: {exc}", True)

    def _emit(self, inv_id: str, event_type: str, payload: dict[str, Any] | None = None) -> None:
        self.store.append_event(inv_id, event_type, payload or {})

    def _set_status(self, inv_id: str, status: str) -> None:
        def mutate(snap: InvestigationSnapshot) -> None:
            snap.status = status  # type: ignore[assignment]

        self.store.update(inv_id, mutate)
        self._emit(inv_id, "status.changed", {"status": status})

    def _fail(self, inv_id: str, code: str, message: str, retryable: bool) -> None:
        try:
            snap = self.store.get(inv_id)
            if snap.status in {"cancelled"}:
                return
        except AppError:
            return

        def mutate(item: InvestigationSnapshot) -> None:
            item.status = "failed"
            item.error = {"code": code, "message": message, "retryable": retryable}

        self.store.update(inv_id, mutate)
        self._emit(inv_id, "error", {"code": code, "message": message, "retryable": retryable})
        self._emit(inv_id, "status.changed", {"status": "failed"})

    def _cancelled(self, inv_id: str) -> bool:
        snap = self.store.get(inv_id)
        return bool(snap.cancelled) or snap.status == "cancelled"

    def _run(self, inv_id: str) -> None:
        if self._cancelled(inv_id):
            return
        self._set_status(inv_id, "routing")
        snap = self.store.get(inv_id)
        route = decide_route(snap.question, snap.wantReport)
        route = self._maybe_refine_route(snap.question, route)
        want_report = bool(route.wantReport) if route.wantReport is not None else snap.wantReport

        def apply_route(item: InvestigationSnapshot) -> None:
            item.mode = route.mode
            item.scope = route.scope
            item.subject = route.subject
            item.agents = route.agents
            item.skills = route.skills
            item.reason = route.reason
            item.clarifyQuestion = route.clarifyQuestion
            item.wantReport = want_report

        self.store.update(inv_id, apply_route)
        self._emit(
            inv_id,
            "route.decided",
            {
                "mode": route.mode,
                "scope": route.scope,
                "subject": route.subject.model_dump(),
                "agents": route.agents,
                "skills": route.skills,
                "reason": route.reason,
                "clarifyQuestion": route.clarifyQuestion,
            },
        )

        if route.mode == "clarify":
            self._clarify(inv_id, route.clarifyQuestion or "请补充供应商或单据编号。")
            return

        if self._needs_locate(route.subject):
            self._locate(inv_id, route)
            route.subject = self.store.get(inv_id).subject

        if not self.llm.configured():
            raise AppError("LLM_ERROR", "未配置 FINPROBE_LLM_API_KEY / OPENAI_API_KEY", retryable=False)

        self._set_status(inv_id, "running")
        if route.mode in {"policy_qa", "lookup"}:
            self._run_general(inv_id, route)
            snap = self.store.get(inv_id)
            handoff = self._collect_handoffs(snap.envelopes)
            if handoff:
                self._upgrade_and_investigate(inv_id, route, handoff)
            else:
                self._finish_without_report(inv_id)
            return

        self._run_risk_agents(inv_id, route)
        snap = self.store.get(inv_id)
        if snap.wantReport or snap.mode == "cross":
            self._review_and_report(inv_id)
        else:
            self._finish_without_report(inv_id)

    def _maybe_refine_route(self, question: str, route: RouteObject) -> RouteObject:
        if not self.llm.configured():
            return route
        try:
            resp = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是 LeadAgent。只输出路由 JSON，字段：mode, scope, subject, agents, skills, reason, clarifyQuestion。"
                            "mode 只能是 clarify/policy_qa/lookup/single/cross。"
                            "差旅报销制度问题不得派 PaymentRiskAgent。"
                            "缺少可绑定实体且非制度时 mode=clarify，只问一个问题。"
                            "不要发明新的 Skill 或风险类型。不要下风险等级。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"question": question, "heuristic": route.model_dump()},
                            ensure_ascii=False,
                        ),
                    },
                ],
                tools=None,
                temperature=0,
            )
            data = extract_json(resp.content or "")
            merged = route.model_dump()
            for key in ("mode", "scope", "reason", "clarifyQuestion"):
                if data.get(key):
                    merged[key] = data[key]
            if isinstance(data.get("subject"), dict):
                merged["subject"] = {**merged["subject"], **{k: v for k, v in data["subject"].items() if v}}
            if isinstance(data.get("skills"), list) and data["skills"]:
                allowed = set(ALL_INVESTIGATION_SKILLS) | {
                    "internal-policy-qa-skill",
                    "general-query-skill",
                }
                skills = [s for s in data["skills"] if s in allowed]
                if skills:
                    merged["skills"] = skills
                    from .routing import _skills_to_agents

                    merged["agents"] = _skills_to_agents(skills)
            # hard guard: travel must not go to payment
            q = question
            if any(x in q for x in ("差旅", "报销", "住宿标准")) and not any(
                getattr(route.subject, k) for k in ("poId", "invoiceId", "paymentId", "supplierId")
            ):
                merged["mode"] = "policy_qa"
                merged["scope"] = "policy"
                merged["agents"] = ["GeneralQueryAgent"]
                merged["skills"] = ["internal-policy-qa-skill"]
                merged["clarifyQuestion"] = None
            return RouteObject.model_validate(merged)
        except Exception:
            return route

    def _needs_locate(self, subject: Subject) -> bool:
        if subject.supplierId or subject.poId or subject.invoiceId or subject.paymentId or subject.grId:
            return False
        return bool(subject.supplierName or subject.taxNo)

    def _locate(self, inv_id: str, route: RouteObject) -> None:
        self._set_status(inv_id, "locating")
        self._emit(inv_id, "agent.thought", {"agent": "LeadAgent", "thought": "先把供应商名称解析成编号，再开始分域调查。"})
        subject = route.subject
        if subject.supplierName:
            result = self.mcp.call("vendor-query", {"keyword": subject.supplierName})
        else:
            result = self.mcp.call("vendor-query", {"taxNo": subject.taxNo})
        self._emit(inv_id, "tool.started", {"agent": "LeadAgent", "tool": result.tool})
        self._emit(inv_id, "tool.completed", result.public_event())

        def mutate(snap: InvestigationSnapshot) -> None:
            snap.locateQueries = list(snap.locateQueries) + [result.to_query_record()]
            rows = []
            payload = result.payload
            rows.extend(payload.get("data") or [])
            rows.extend(payload.get("sample") or [])
            chosen = None
            name = (subject.supplierName or "").replace(" ", "")
            for row in rows:
                row_name = str(row.get("name") or "")
                if name and (name in row_name.replace(" ", "") or row_name.replace(" ", "") in name):
                    chosen = row
                    break
            if chosen is None and len(rows) == 1:
                chosen = rows[0]
            if chosen:
                snap.subject.supplierId = chosen.get("id") or chosen.get("supplierId") or snap.subject.supplierId
                snap.subject.supplierName = chosen.get("name") or snap.subject.supplierName
                route.subject = snap.subject

        self.store.update(inv_id, mutate)

    def _clarify(self, inv_id: str, question: str) -> None:
        def mutate(snap: InvestigationSnapshot) -> None:
            snap.status = "awaiting_user"
            snap.clarifyQuestion = question
            snap.messages = list(snap.messages) + [
                ChatMessage(role="clarify", content=question, ts=now_iso())
            ]

        self.store.update(inv_id, mutate)
        self._emit(inv_id, "message.clarify", {"content": question})
        self._emit(inv_id, "status.changed", {"status": "awaiting_user"})

    def _run_general(self, inv_id: str, route: RouteObject) -> None:
        snap = self.store.get(inv_id)
        env = self.general.run(
            skills=route.skills,
            subject=snap.subject,
            question=snap.question,
            emit=lambda t, p: self._emit(inv_id, t, p),
            cancel_check=lambda: self._cancelled(inv_id),
        )
        self._upsert_envelope(inv_id, env)
        answer = env.get("answer") or ""
        if env.get("clarifyQuestion") and env.get("intent") == "clarify":
            self._clarify(inv_id, env["clarifyQuestion"])
            return
        if answer:
            self._assistant(inv_id, answer)

    def _run_risk_agents(self, inv_id: str, route: RouteObject, follow_skill: str | None = None) -> None:
        snap = self.store.get(inv_id)
        skills = [follow_skill] if follow_skill else list(route.skills)
        supplier_skills = [s for s in skills if s in SUPPLIER_SKILLS]
        tx_skills = [s for s in skills if s in TX_SKILLS]
        pay_skills = [s for s in skills if s in PAY_SKILLS]
        subject = snap.subject
        jobs = []
        with ThreadPoolExecutor(max_workers=3) as pool:
            if supplier_skills:
                jobs.append(
                    pool.submit(
                        self._run_one,
                        inv_id,
                        self.supplier,
                        supplier_skills,
                        subject,
                        snap.question,
                    )
                )
            if tx_skills:
                jobs.append(
                    pool.submit(
                        self._run_one,
                        inv_id,
                        self.transaction,
                        tx_skills,
                        subject,
                        snap.question,
                    )
                )
            wait_pay = bool(pay_skills) and payment_must_wait(subject)
            if pay_skills and not wait_pay:
                jobs.append(
                    pool.submit(
                        self._run_one,
                        inv_id,
                        self.payment,
                        pay_skills,
                        subject,
                        snap.question,
                    )
                )
            for fut in as_completed(jobs):
                try:
                    fut.result()
                except AgentCancelled:
                    raise
                except Exception as exc:  # noqa: BLE001
                    self._emit(
                        inv_id,
                        "error",
                        {
                            "code": getattr(exc, "code", "LLM_ERROR"),
                            "message": str(exc),
                            "retryable": bool(getattr(exc, "retryable", True)),
                        },
                    )
        if pay_skills and wait_pay:
            snap = self.store.get(inv_id)
            subject = self._subject_from_envelopes(snap)
            self._run_one(inv_id, self.payment, pay_skills, subject, snap.question)

    def _run_one(self, inv_id, agent, skills, subject, question, extra="", prior=None):
        try:
            env = agent.run(
                skills=skills,
                subject=subject,
                question=question,
                emit=lambda t, p: self._emit(inv_id, t, p),
                cancel_check=lambda: self._cancelled(inv_id),
                extra_instruction=extra,
                prior_envelope=prior,
            )
        except AgentCancelled:
            raise
        except AppError as exc:
            agent_name = getattr(agent, "name", "RiskAgent")
            env = degraded_envelope(
                agent=agent_name,
                skills=list(skills or []),
                subject=subject,
                queries=[],
                reason=agent_name + ": " + exc.message,
            )
            env["error"] = {"code": exc.code, "message": exc.message, "retryable": exc.retryable}
            self._emit(
                inv_id,
                "error",
                {
                    "code": exc.code,
                    "message": agent_name + ": " + exc.message,
                    "retryable": exc.retryable,
                    "agent": agent_name,
                    "isolated": True,
                },
            )
            self._emit(
                inv_id,
                "agent.completed",
                {
                    "agent": agent_name,
                    "skills": skills,
                    "overallRiskLevel": "证据不足",
                    "degraded": True,
                },
            )
        self._upsert_envelope(inv_id, env)
        return env

    def _subject_from_envelopes(self, snap: InvestigationSnapshot) -> Subject:
        subject = snap.subject
        for env in snap.envelopes:
            subject = merge_subject(subject, env.get("subject") if isinstance(env, dict) else None)
        def mutate(item: InvestigationSnapshot) -> None:
            item.subject = subject
        self.store.update(snap.id, mutate)
        return subject

    def _upsert_envelope(self, inv_id: str, envelope: dict[str, Any]) -> None:
        with self._bag_lock:
            def mutate(snap: InvestigationSnapshot) -> None:
                skill = envelope.get("skill")
                bags = [e for e in snap.envelopes if e.get("skill") != skill]
                bags.append(envelope)
                snap.envelopes = bags
                levels = [e.get("overallRiskLevel") for e in bags if e.get("overallRiskLevel")]
                snap.overallRiskLevel = aggregate_risk_level([lv for lv in levels if isinstance(lv, str)])
                extra = envelope.get("subject") if isinstance(envelope.get("subject"), dict) else None
                snap.subject = merge_subject(snap.subject, extra)

            self.store.update(inv_id, mutate)
        self._emit(
            inv_id,
            "envelope.upserted",
            {
                "skill": envelope.get("skill"),
                "agent": envelope.get("agent"),
                "overallRiskLevel": envelope.get("overallRiskLevel"),
                "findingCount": len(envelope.get("findings") or []),
            },
        )

    def _collect_handoffs(self, envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for env in envelopes:
            handoff = env.get("handoff")
            if not handoff:
                continue
            if isinstance(handoff, dict):
                out.append(handoff)
            elif isinstance(handoff, list):
                out.extend([h for h in handoff if isinstance(h, dict)])
        return out

    def _upgrade_and_investigate(self, inv_id: str, route: RouteObject, handoffs: list[dict[str, Any]]) -> None:
        skills = list(route.skills)
        for item in handoffs:
            skill = item.get("skill")
            if skill and skill not in skills and skill in ALL_INVESTIGATION_SKILLS:
                skills.append(skill)
        from .routing import _skills_to_agents

        agents = [a for a in _skills_to_agents(skills) if a != "GeneralQueryAgent"]
        def mutate(snap: InvestigationSnapshot) -> None:
            snap.mode = "cross" if len(agents) >= 2 else "single"
            snap.skills = [s for s in skills if s in ALL_INVESTIGATION_SKILLS]
            snap.agents = agents
            snap.wantReport = True
            snap.reason = (snap.reason or "") + "；GeneralQuery 发现风险信号，已升级调查"

        self.store.update(inv_id, mutate)
        self._emit(inv_id, "route.decided", {"mode": "cross" if len(agents) >= 2 else "single", "skills": skills, "reason": "handoff 升级"})
        snap = self.store.get(inv_id)
        upgraded = RouteObject(
            mode=snap.mode,  # type: ignore[arg-type]
            scope=snap.scope or "document",  # type: ignore[arg-type]
            subject=snap.subject,
            agents=snap.agents,
            skills=snap.skills,
            reason=snap.reason or "handoff",
            wantReport=True,
        )
        self._set_status(inv_id, "running")
        self._run_risk_agents(inv_id, upgraded)
        self._review_and_report(inv_id)

    def _review_and_report(self, inv_id: str) -> None:
        for round_n in range(0, 3):
            if self._cancelled(inv_id):
                return
            self._set_status(inv_id, "reviewing")
            snap = self.store.get(inv_id)
            review = self.evidence.run(
                envelopes=snap.envelopes,
                question=snap.question,
                emit=lambda t, p: self._emit(inv_id, t, p),
                cancel_check=lambda: self._cancelled(inv_id),
            )

            def save_review(item: InvestigationSnapshot) -> None:
                item.evidenceReview = review
                item.followUpRound = round_n

            self.store.update(inv_id, save_review)
            if review.get("readyForReport") or round_n >= 2:
                break
            tasks = review.get("followUpTasks") or []
            if not tasks:
                break
            self._set_status(inv_id, "follow_up")
            self._run_followups(inv_id, tasks)

        self._set_status(inv_id, "reporting")
        snap = self.store.get(inv_id)
        report_id = self.store.next_report_id()
        produced = self.report.run(
            question=snap.question,
            envelopes=snap.envelopes,
            evidence_review=snap.evidenceReview,
            report_id=report_id,
            emit=lambda t, p: self._emit(inv_id, t, p),
        )
        envelope_levels = [
            env.get("overallRiskLevel")
            for env in snap.envelopes
            if isinstance(env.get("overallRiskLevel"), str)
        ]
        report_level = produced["report"].get("overallRiskLevel")
        overall = aggregate_risk_level(
            [lv for lv in envelope_levels + [report_level] if isinstance(lv, str)]
        )
        if overall:
            produced["report"]["overallRiskLevel"] = overall
        answer = produced["report"].get("summary") or "调查完成。"
        draft = bool(produced.get("draft"))
        if draft:
            answer = "证据尚未齐备，以下为草稿摘要：\n" + answer

        def save_report(item: InvestigationSnapshot) -> None:
            item.report = produced["report"]
            item.reportMarkdown = produced["markdown"]
            item.overallRiskLevel = overall or produced["report"].get("overallRiskLevel") or item.overallRiskLevel
            item.answer = answer
            item.status = "completed"
            item.messages = list(item.messages) + [ChatMessage(role="assistant", content=answer, ts=now_iso())]

        self.store.update(inv_id, save_report)
        self._emit(inv_id, "message.assistant", {"content": answer})
        self._emit(inv_id, "status.changed", {"status": "completed"})

    def _run_followups(self, inv_id: str, tasks: list[dict[str, Any]]) -> None:
        snap = self.store.get(inv_id)
        by_skill: dict[str, list[dict[str, Any]]] = {}
        for task in tasks:
            skill = task.get("skill")
            if not skill:
                continue
            by_skill.setdefault(skill, []).append(task)
        mapping = {
            "SupplierRiskAgent": self.supplier,
            "TransactionRiskAgent": self.transaction,
            "PaymentRiskAgent": self.payment,
        }
        from .routing import AGENT_FOR_SKILL

        for skill, skill_tasks in by_skill.items():
            agent_name = AGENT_FOR_SKILL.get(skill)
            agent = mapping.get(agent_name or "")
            if not agent:
                continue
            prior = next((e for e in snap.envelopes if e.get("skill") == skill), None)
            extra = "补查任务：\n" + json.dumps(skill_tasks, ensure_ascii=False) + "\n禁止按 PO 循环 query；步数将尽时直接输出信封。缺数据标证据不足。"
            self._run_one(inv_id, agent, [skill], snap.subject, snap.question, extra=extra, prior=prior)

    def _assistant(self, inv_id: str, content: str) -> None:
        def mutate(snap: InvestigationSnapshot) -> None:
            snap.answer = content
            snap.messages = list(snap.messages) + [ChatMessage(role="assistant", content=content, ts=now_iso())]

        self.store.update(inv_id, mutate)
        self._emit(inv_id, "message.assistant", {"content": content})

    def _finish_without_report(self, inv_id: str) -> None:
        snap = self.store.get(inv_id)
        if snap.status == "awaiting_user":
            return
        if not snap.answer:
            answer = _summarize_envelopes(snap)
            self._assistant(inv_id, answer)

        def mutate(item: InvestigationSnapshot) -> None:
            item.status = "completed"
            levels = [e.get("overallRiskLevel") for e in item.envelopes if e.get("overallRiskLevel")]
            if not item.overallRiskLevel:
                item.overallRiskLevel = aggregate_risk_level([lv for lv in levels if isinstance(lv, str)])

        self.store.update(inv_id, mutate)
        self._emit(inv_id, "status.changed", {"status": "completed"})


def _summarize_envelopes(snap: InvestigationSnapshot) -> str:
    if snap.answer:
        return snap.answer
    if not snap.envelopes:
        return "调查结束，未形成发现。"
    lines = []
    if snap.overallRiskLevel:
        lines.append(f"总体风险：{snap.overallRiskLevel}")
    for env in snap.envelopes:
        for finding in env.get("findings") or []:
            lines.append(
                f"- {finding.get('riskType')}：{finding.get('riskLevel')}。{finding.get('rootCause') or ''}"
            )
        if env.get("answer"):
            lines.append(env["answer"])
    return "\n".join(lines) or "调查完成。"