# -*- coding: utf-8 -*-
from src.backend.app.errors import AppError
from src.backend.app.llm.client import LLMResponse
from src.backend.app.orchestrator.lead import LeadOrchestrator
from src.backend.app.schemas import Subject
from tests.backend.conftest import FakeLLM, FakeMCP


class SilentLLM(FakeLLM):
    def chat(self, messages, tools=None, temperature=0) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        return LLMResponse(content="not-json")


def test_transaction_failure_does_not_drop_supplier_envelope(tmp_store):
    orch = LeadOrchestrator(tmp_store, FakeMCP(), SilentLLM())
    orch.supplier.run = lambda **kw: {
        "skill": "supplier-profile-audit-skill",
        "agent": "SupplierRiskAgent",
        "overallRiskLevel": "中风险",
        "subject": {"supplierId": "VEN-S001"},
        "queries": [{"tool": "vendor-query", "ok": True, "args": {"supplierId": "VEN-S001"}}],
        "findings": [{"riskType": "供应商主信息异常", "riskLevel": "中风险"}],
    }

    def boom(**kw):
        raise AppError("LLM_ERROR", "TransactionRiskAgent 超过最大 ReAct 步数", retryable=True)

    orch.transaction.run = boom
    orch.payment.run = lambda **kw: {
        "skill": "payment-audit-skill",
        "agent": "PaymentRiskAgent",
        "overallRiskLevel": "低风险",
        "subject": {"supplierId": "VEN-S001"},
        "queries": [],
        "findings": [{"riskType": "重复付款", "riskLevel": "低风险"}],
    }
    orch.evidence.run = lambda **kw: {
        "readyForReport": True,
        "ruleFindings": [],
        "semanticFindings": [],
        "evidenceSufficient": True,
        "followUpTasks": [],
    }
    orch.report.run = lambda **kw: {
        "report": {
            "summary": "供应商主信息中风险，交易域证据不足",
            "overallRiskLevel": "中风险",
            "findings": [],
        },
        "markdown": "ok",
        "draft": False,
    }

    snap = tmp_store.create("请全面排查供应商 VEN-S001", True)
    orch.run(snap.id)
    got = tmp_store.get(snap.id)
    assert got.status == "completed"
    agents = {env.get("agent"): env for env in got.envelopes}
    assert agents["SupplierRiskAgent"]["overallRiskLevel"] == "中风险"
    assert agents["TransactionRiskAgent"]["overallRiskLevel"] == "证据不足"
    assert agents["TransactionRiskAgent"].get("degraded") is True
    assert "PaymentRiskAgent" in agents
    assert got.overallRiskLevel == "中风险"
    assert got.error is None
