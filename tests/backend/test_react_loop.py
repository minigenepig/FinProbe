# -*- coding: utf-8 -*-
from src.backend.app.agents.base import BaseRiskAgent, degraded_envelope
from src.backend.app.agents.transaction import TransactionRiskAgent
from src.backend.app.errors import AppError
from src.backend.app.llm.client import LLMResponse
from src.backend.app.mcp_client.client import MCPResult
from src.backend.app.schemas import Subject
from tests.backend.conftest import FakeMCP


class ScriptedLLM:
    model = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def configured(self) -> bool:
        return True

    def chat(self, messages, tools=None, temperature=0) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.script:
            return LLMResponse(content='{"overallRiskLevel":"证据不足","findings":[]}')
        item = self.script.pop(0)
        return item(self.calls) if callable(item) else item


def _tool_call(name: str, args: dict, call_id: str = "call-1") -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[{"id": call_id, "name": name, "arguments": args}],
    )


def test_max_steps_returns_insufficient_envelope_instead_of_raising():
    llm = ScriptedLLM(
        [
            _tool_call("gr-query", {"poId": "PO-00001"}, "c1"),
            _tool_call("gr-query", {"poId": "PO-00002"}, "c2"),
            _tool_call("gr-query", {"poId": "PO-00003"}, "c3"),
            LLMResponse(content=""),
        ]
    )
    agent = TransactionRiskAgent(FakeMCP(), llm, max_steps=4)
    env = agent.run(
        skills=["p2p-three-way-match-skill"],
        subject=Subject(supplierId="VEN-S001"),
        question="请全面排查供应商 VEN-S001",
    )
    assert env["overallRiskLevel"] == "证据不足"
    assert env.get("degraded") is True
    assert len(env["queries"]) == 3
    assert env["queries"][0]["tool"] == "gr-query"
    last_tools = llm.calls[-1]["tools"]
    assert last_tools is None
    stop_notes = [
        msg["content"]
        for msg in llm.calls[-1]["messages"]
        if msg.get("role") == "system" and "步数将尽" in (msg.get("content") or "")
    ]
    assert stop_notes


def test_last_step_json_is_used_and_queries_preserved():
    llm = ScriptedLLM(
        [
            _tool_call("po-query", {"supplierId": "VEN-S001"}, "c1"),
            LLMResponse(
                content='{"skill":"p2p-three-way-match-skill","overallRiskLevel":"中风险","findings":[]}'
            ),
        ]
    )
    agent = TransactionRiskAgent(FakeMCP(), llm, max_steps=2)
    env = agent.run(
        skills=["p2p-three-way-match-skill"],
        subject=Subject(supplierId="VEN-S001"),
        question="请全面排查供应商 VEN-S001",
    )
    assert env["overallRiskLevel"] == "中风险"
    assert env["queries"][0]["tool"] == "po-query"
    assert env.get("degraded") is not True


def test_id_loop_nudge_injected_into_tool_message():
    llm = ScriptedLLM(
        [
            _tool_call("gr-query", {"poId": "PO-00001"}, "c1"),
            _tool_call("gr-query", {"poId": "PO-00002"}, "c2"),
            _tool_call("gr-query", {"poId": "PO-00003"}, "c3"),
            LLMResponse(content='{"overallRiskLevel":"证据不足","findings":[]}'),
        ]
    )
    agent = TransactionRiskAgent(FakeMCP(), llm, max_steps=5)
    agent.run(
        skills=["p2p-three-way-match-skill"],
        subject=Subject(supplierId="VEN-S001"),
        question="请全面排查供应商 VEN-S001",
    )
    tool_msgs = [
        msg["content"]
        for call in llm.calls
        for msg in call["messages"]
        if msg.get("role") == "tool"
    ]
    assert any("按单循环" in (content or "") for content in tool_msgs)


def test_transaction_prompt_forbids_po_loop_and_sandbox_import():
    agent = TransactionRiskAgent(FakeMCP(), ScriptedLLM([]))
    prompt = agent.system_prompt([], Subject(supplierId="VEN-S001"))
    assert "gr-query(supplierId)" in prompt
    assert "禁止按 PO 循环" in prompt
    assert "禁止 import" in prompt
    assert "to_number" in prompt


def test_degraded_envelope_keeps_queries_as_evidence():
    env = degraded_envelope(
        agent="TransactionRiskAgent",
        skills=["p2p-three-way-match-skill"],
        subject=Subject(supplierId="VEN-S001"),
        queries=[{"tool": "po-query", "ok": True, "args": {"supplierId": "VEN-S001"}, "artifactId": "art_1"}],
        reason="TransactionRiskAgent 超过最大 ReAct 步数",
    )
    assert env["overallRiskLevel"] == "证据不足"
    assert env["findings"][0]["riskType"] == "少货多付/数量/金额异常"
    assert env["queries"][0]["artifactId"] == "art_1"


def test_max_steps_does_not_raise_apperror():
    llm = ScriptedLLM([_tool_call("vendor-query", {"supplierId": "VEN-S001"}, f"c{i}") for i in range(6)])
    agent = BaseRiskAgent(FakeMCP(), llm, max_steps=3)
    agent.name = "TransactionRiskAgent"
    try:
        env = agent.run(
            skills=["p2p-three-way-match-skill"],
            subject=Subject(supplierId="VEN-S001"),
            question="请全面排查供应商 VEN-S001",
        )
    except AppError as exc:  # pragma: no cover
        raise AssertionError(f"should not raise: {exc}") from exc
    assert env["overallRiskLevel"] == "证据不足"


def test_emits_thought_and_observation():
    llm = ScriptedLLM(
        [
            _tool_call("po-query", {"supplierId": "VEN-S001"}, "c1"),
            LLMResponse(content='{"overallRiskLevel":"低风险","findings":[]}'),
        ]
    )
    events = []
    agent = TransactionRiskAgent(FakeMCP(), llm, max_steps=3)
    agent.run(
        skills=["p2p-three-way-match-skill"],
        subject=Subject(supplierId="VEN-S001"),
        question="请全面排查供应商 VEN-S001",
        emit=lambda t, p: events.append((t, p)),
    )
    types = [t for t, _ in events]
    assert "agent.thought" in types
    thought = next(p for t, p in events if t == "agent.thought")
    assert "查采购订单" in thought["thought"] or "思考" in thought["thought"] or thought["thought"]
    completed = next(p for t, p in events if t == "tool.completed")
    assert completed.get("observation")
    assert completed.get("label") == "查采购订单"
