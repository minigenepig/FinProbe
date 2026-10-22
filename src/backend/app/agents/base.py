# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from ..errors import AppError
from ..llm.client import LLMClient, LLMError, extract_json
from ..mcp_client.client import MCPClient, MCPResult, QUERY_TOOLS, args_target, tool_label
from ..schemas import Subject
from ..skills_loader import SkillDoc, load_skills

CancelCheck = Callable[[], bool]
EventEmitter = Callable[[str, dict[str, Any]], None]

ID_LOOP_FIELDS = (
    "poId",
    "grId",
    "invoiceId",
    "paymentId",
    "businessId",
    "purchaseOrderId",
    "approvalId",
)

DOMAIN_RISK_TYPES = {
    "SupplierRiskAgent": ["供应商主信息异常", "供应商之间关联关系风险"],
    "TransactionRiskAgent": ["少货多付/数量/金额异常", "拆单避审", "重复发票", "税率异常"],
    "PaymentRiskAgent": ["重复付款", "异常收款账户"],
}


class AgentCancelled(RuntimeError):
    pass


def _ensure_not_cancelled(check: CancelCheck | None) -> None:
    if check and check():
        raise AgentCancelled("调查已取消")


def merge_queries(actual: list[dict[str, Any]], claimed: list[Any] | None) -> list[dict[str, Any]]:
    """Actual MCP calls are the source of truth; LLM-claimed queries cannot invent calls."""
    return list(actual)


def _dump_subject(subject: Subject | dict[str, Any] | None) -> dict[str, Any]:
    if subject is None:
        return {}
    if isinstance(subject, Subject):
        return subject.model_dump()
    return dict(subject)


def tool_signature(name: str, args: dict[str, Any]) -> str:
    cleaned = {k: v for k, v in (args or {}).items() if v not in (None, "", [], {})}
    return f"{name}:{json.dumps(cleaned, ensure_ascii=False, sort_keys=True, default=str)}"


def _id_loop_key(name: str, args: dict[str, Any]) -> tuple[str, str, str] | None:
    present = [field for field in ID_LOOP_FIELDS if (args or {}).get(field)]
    if len(present) != 1:
        return None
    field = present[0]
    others = {
        k: v
        for k, v in (args or {}).items()
        if k not in ID_LOOP_FIELDS and k != "supplierId" and v not in (None, "", [], {})
    }
    if (args or {}).get("supplierId"):
        return None
    return (name, field, json.dumps(others, ensure_ascii=False, sort_keys=True, default=str))


def _approval_status(queries: list[dict[str, Any]]) -> str:
    calls = [q for q in queries if q.get("tool") == "approval-query"]
    if not calls:
        return "NOT_QUERIED"
    if all(not q.get("ok") for q in calls):
        return "NOT_QUERIED"
    return "NOT_FOUND"


def degraded_envelope(
    *,
    agent: str,
    skills: list[str],
    subject: Subject | dict[str, Any] | None,
    queries: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    risk_type = (DOMAIN_RISK_TYPES.get(agent) or ["少货多付/数量/金额异常"])[0]
    refs = []
    for query in queries:
        if not query.get("ok"):
            continue
        args = query.get("args") if isinstance(query.get("args"), dict) else {}
        ref_id = (
            args.get("poId")
            or args.get("invoiceId")
            or args.get("grId")
            or args.get("paymentId")
            or args.get("supplierId")
            or args.get("businessId")
            or query.get("artifactId")
        )
        refs.append({"tool": query.get("tool"), "id": ref_id})
    finding = {
        "riskType": risk_type,
        "riskLevel": "证据不足",
        "facts": [reason],
        "metrics": {},
        "rootCause": "调查未能在步数内完成必查聚合，不能确认也不能排除该领域风险。",
        "mitigation": {"approvalStatus": _approval_status(queries)},
        "recommendation": "请基于已执行 queries 补查，或缩小到单张单据后重跑。",
        "openQuestions": [reason],
        "evidenceRefs": refs,
    }
    return {
        "skill": skills[0] if skills else None,
        "agent": agent,
        "subject": _dump_subject(subject),
        "queries": list(queries),
        "findings": [finding],
        "overallRiskLevel": "证据不足",
        "degraded": True,
        "openQuestions": [reason],
    }


def _thought_text(content: str | None, tool_calls: list[dict[str, Any]]) -> str:
    raw = (content or "").strip()
    if raw and not raw.startswith("{") and not raw.startswith("```"):
        compact = " ".join(raw.split())
        return compact[:280]
    names = []
    for call in tool_calls:
        name = call.get("name") or ""
        args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        label = tool_label(name)
        target = args_target(args)
        names.append(f"{label}{('（' + target + '）') if target else ''}")
    if not names:
        return "继续按技能核对证据。"
    return "下一步：" + "；".join(names[:4])


class BaseRiskAgent:
    name = "RiskAgent"
    allowed_tools: tuple[str, ...] = QUERY_TOOLS + ("financial-analysis", "artifact-get")
    max_steps = 16
    output_kind = "envelope"  # envelope | general | evidence | report

    def __init__(self, mcp: MCPClient, llm: LLMClient, max_steps: int | None = None) -> None:
        self.mcp = mcp
        self.llm = llm
        if max_steps is not None:
            self.max_steps = max_steps

    def system_prompt(self, skills: list[SkillDoc], subject: Subject, extra: str = "") -> str:
        blocks = "\n\n".join(doc.prompt_block() for doc in skills)
        skill_names = ", ".join(doc.name for doc in skills)
        return f"""你是 {self.name}，只加载并遵守这些技能：{skill_names}。
不要调用未授权工具。不要编造 ERP 记录、审批节点或金额。
列表结果只使用 summary / sample / artifact；禁止要求工具返回全量发票或 PO 原文。
金额、税率、百分比必须来自工具返回或 financial-analysis 沙箱计算。
financial-analysis 禁止 import、type、getattr、下划线属性；金额先 to_number；必须赋值 result=...；用 artifactIds 注入 records。
供应商全量调查时，po-query / invoice-query / gr-query 用 supplierId 各至多 1 次列表，大结果走 artifact + financial-analysis。
禁止按 PO/发票循环调用 gr-query 或 approval-query；异常样本才 artifact-get。
未调用 approval-query 时，mitigation.approvalStatus 必须是 NOT_QUERIED，不得声称无审批或已消解。
查询为空时写「ERP 未检索到…」，不要写成「肯定不存在」。
公司名称固定为「启衡精密制造有限公司」。
全部 GR 仓库都是 WH-01-A、收货人都是 EMP-3392，不得把二者相同当作拆单或串通证据。
重复付款没有中风险档。
步数将尽时停止工具调用，仅输出信封 JSON；缺数据的类型标「证据不足」。

当前调查对象 subject = {json.dumps(subject.model_dump(), ensure_ascii=False)}

完成调查后，必须只输出一个 JSON 对象（不要 Markdown 解释），字段名不可改写。
{extra}

{blocks}
"""

    def run(
        self,
        *,
        skills: list[str],
        subject: Subject,
        question: str,
        emit: EventEmitter | None = None,
        cancel_check: CancelCheck | None = None,
        extra_instruction: str = "",
        prior_envelope: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        docs = load_skills(skills)
        if emit:
            emit("agent.started", {"agent": self.name, "skills": skills})
        actual_queries: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt(docs, subject, extra_instruction)},
            {
                "role": "user",
                "content": self._user_prompt(question, subject, prior_envelope, extra_instruction),
            },
        ]
        tools = self.mcp.openai_tools(list(self.allowed_tools)) if self.allowed_tools else None
        last_content = ""
        stop_nudged = False
        signature_counts: dict[str, int] = defaultdict(int)
        loop_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        try:
            for step in range(self.max_steps):
                _ensure_not_cancelled(cancel_check)
                remaining = self.max_steps - step
                if remaining <= 2 and not stop_nudged:
                    messages.append(
                        {
                            "role": "system",
                            "content": self._stop_nudge(actual_queries, remaining),
                        }
                    )
                    stop_nudged = True
                use_tools = tools if remaining > 1 and self.allowed_tools else None
                try:
                    response = self.llm.chat(messages, tools=use_tools, temperature=0)
                except LLMError as exc:
                    if actual_queries:
                        return self._finish(
                            degraded_envelope(
                                agent=self.name,
                                skills=skills,
                                subject=subject,
                                queries=actual_queries,
                                reason=f"{self.name} LLM 调用失败: {exc}",
                            ),
                            skills,
                            emit,
                        )
                    raise AppError("LLM_ERROR", str(exc), retryable=exc.retryable) from exc
                if response.has_tool_calls and use_tools:
                    if emit:
                        emit("agent.thought", {
                            "agent": self.name,
                            "thought": _thought_text(response.content, response.tool_calls),
                        })
                    messages.append(
                        {
                            "role": "assistant",
                            "content": response.content or "",
                            "tool_calls": [
                                {
                                    "id": call["id"],
                                    "type": "function",
                                    "function": {
                                        "name": call["name"],
                                        "arguments": json.dumps(call["arguments"], ensure_ascii=False),
                                    },
                                }
                                for call in response.tool_calls
                            ],
                        }
                    )
                    for call in response.tool_calls:
                        _ensure_not_cancelled(cancel_check)
                        name = call["name"]
                        args = call["arguments"] if isinstance(call["arguments"], dict) else {}
                        if name not in self.allowed_tools:
                            tool_content = json.dumps(
                                {"ok": False, "error": f"{self.name} 无权调用 {name}"},
                                ensure_ascii=False,
                            )
                            messages.append(
                                {"role": "tool", "tool_call_id": call["id"], "content": tool_content}
                            )
                            continue
                        if emit:
                            emit(
                                "tool.started",
                                {
                                    "agent": self.name,
                                    "tool": name,
                                    "label": tool_label(name),
                                    "target": args_target(args),
                                },
                            )
                        result = self._call_tool(name, args)
                        record = result.to_query_record()
                        actual_queries.append(record)
                        if emit:
                            emit("tool.completed", {**result.public_event(), "agent": self.name})
                        signature_counts[tool_signature(name, args)] += 1
                        loop_key = _id_loop_key(name, args)
                        if loop_key:
                            loop_counts[loop_key] += 1
                        tool_content = result.compact_for_llm()
                        nudge = self._tool_nudge(name, args, result, signature_counts, loop_counts)
                        if nudge:
                            tool_content = f"{tool_content}\n\n[系统提示] {nudge}"
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call["id"],
                                "content": tool_content,
                            }
                        )
                    continue
                last_content = response.content or ""
                break
            else:
                envelope = degraded_envelope(
                    agent=self.name,
                    skills=skills,
                    subject=subject,
                    queries=actual_queries,
                    reason=f"{self.name} 超过最大 ReAct 步数，已停止工具循环。",
                )
                return self._finish(envelope, skills, emit)
            if not (last_content or "").strip():
                envelope = degraded_envelope(
                    agent=self.name,
                    skills=skills,
                    subject=subject,
                    queries=actual_queries,
                    reason=f"{self.name} 超过最大 ReAct 步数，已停止工具循环。",
                )
            else:
                try:
                    envelope = self._parse_output(last_content)
                except Exception:
                    envelope = degraded_envelope(
                        agent=self.name,
                        skills=skills,
                        subject=subject,
                        queries=actual_queries,
                        reason=f"{self.name} 未能输出可解析的调查信封。",
                    )
            envelope.setdefault("agent", self.name)
            if skills:
                envelope.setdefault("skill", skills[0])
            envelope["queries"] = merge_queries(actual_queries, envelope.get("queries"))
            envelope.setdefault("subject", subject.model_dump())
            return self._finish(envelope, skills, emit)
        except AgentCancelled:
            raise
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001
            if actual_queries:
                return self._finish(
                    degraded_envelope(
                        agent=self.name,
                        skills=skills,
                        subject=subject,
                        queries=actual_queries,
                        reason=f"{self.name} 执行失败: {exc}",
                    ),
                    skills,
                    emit,
                )
            raise AppError("LLM_ERROR", f"{self.name} 执行失败: {exc}") from exc

    def _finish(
        self,
        envelope: dict[str, Any],
        skills: list[str],
        emit: EventEmitter | None,
    ) -> dict[str, Any]:
        if emit:
            emit(
                "agent.completed",
                {
                    "agent": self.name,
                    "skills": skills,
                    "overallRiskLevel": envelope.get("overallRiskLevel"),
                    "intent": envelope.get("intent"),
                    "degraded": bool(envelope.get("degraded")),
                },
            )
        return envelope

    def _stop_nudge(self, actual_queries: list[dict[str, Any]], remaining: int) -> str:
        tools_used = sorted({q.get("tool") for q in actual_queries if q.get("tool")})
        return (
            f"步数将尽（剩余 {remaining} 步）。立即停止调用工具，只输出统一调查信封 JSON。"
            f"已执行工具：{tools_used or ['无']}，这些 queries 就是 evidenceRefs。"
            "缺数据的风险类型标「证据不足」，openQuestions 写明缺口。"
            "禁止再按 PO 循环 gr-query/approval-query；禁止 import/type/getattr。"
        )

    def _tool_nudge(
        self,
        name: str,
        args: dict[str, Any],
        result: MCPResult,
        signature_counts: dict[str, int],
        loop_counts: dict[tuple[str, str, str], int],
    ) -> str | None:
        notes: list[str] = []
        sig = tool_signature(name, args)
        if signature_counts[sig] >= 2 and name != "financial-analysis":
            notes.append("同一工具参数已重复调用，不要再调，改用已有 summary/artifact 或直接输出信封。")
        loop_key = _id_loop_key(name, args)
        if loop_key and loop_counts[loop_key] >= 3:
            notes.append(
                "检测到按单循环查询。供应商范围应改用 supplierId 一次列表 + artifact + financial-analysis；"
                "异常样本才 artifact-get。请停止循环并输出信封。"
            )
        if name == "financial-analysis" and not result.ok:
            error = result.error or ""
            if "Import" in error or "禁止名称: type" in error or "getattr" in error:
                notes.append(
                    "沙箱禁止 import、type、getattr、下划线属性。金额先 to_number，必须赋值 result=...，"
                    "用 artifactIds 注入 records。"
                )
            elif "NoneType" in error:
                notes.append(
                    "records 为空。financial-analysis 必须传入 artifactIds，并先判断 records 再下标/求长。"
                )
        return " ".join(notes) if notes else None

    def _user_prompt(
        self,
        question: str,
        subject: Subject,
        prior_envelope: dict[str, Any] | None,
        extra_instruction: str,
    ) -> str:
        parts = [f"用户问题：{question}"]
        if extra_instruction:
            parts.append(extra_instruction)
        if prior_envelope:
            parts.append("前序信封（补查时在此基础上更新，不要丢弃已核实 facts）：")
            parts.append(json.dumps(prior_envelope, ensure_ascii=False)[:6000])
        parts.append("请按技能步骤调查，最终只输出 JSON。")
        return "\n\n".join(parts)

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> MCPResult:
        return self.mcp.call(name, arguments)

    def _parse_output(self, content: str) -> dict[str, Any]:
        try:
            return extract_json(content)
        except Exception:
            retry = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": "把下面内容提取为单个 JSON 对象，不要解释。字段名保持原样。",
                    },
                    {"role": "user", "content": content[:12000]},
                ],
                tools=None,
                temperature=0,
            )
            return extract_json(retry.content or "")
