# -*- coding: utf-8 -*-
from src.backend.app.orchestrator.routing import aggregate_risk_level, decide_route, infer_want_report, payment_must_wait


def test_travel_policy_not_payment():
    route = decide_route("差旅住宿标准是多少？")
    assert route.mode == "policy_qa"
    assert route.skills == ["internal-policy-qa-skill"]
    assert "PaymentRiskAgent" not in route.agents
    assert infer_want_report(route.mode, None) is False


def test_clarify_one_question_when_missing_id():
    route = decide_route("帮我查一下风险")
    assert route.mode == "clarify"
    assert route.clarifyQuestion
    assert "？" in route.clarifyQuestion or "请" in route.clarifyQuestion


def test_po_three_way_single():
    route = decide_route("PO-01332 三单是否匹配？")
    assert route.subject.poId == "PO-01332"
    assert "p2p-three-way-match-skill" in route.skills
    assert route.mode in {"single", "cross"}
    assert infer_want_report(route.mode, None) is True


def test_lookup_po_no_report():
    route = decide_route("帮我看一下 PO-00005 是什么。")
    assert route.mode == "lookup"
    assert route.skills == ["general-query-skill"]
    assert infer_want_report(route.mode, None) is False


def test_full_supplier_cross():
    route = decide_route("请全面排查供应商 VEN-0044")
    assert route.mode == "cross"
    assert route.scope == "supplier"
    assert "supplier-profile-audit-skill" in route.skills
    assert "p2p-three-way-match-skill" in route.skills
    assert "payment-audit-skill" in route.skills


def test_population_relation():
    route = decide_route("有没有关联供应商或重复建档？")
    assert route.scope == "population"
    assert route.skills == ["supplier-relation-audit-skill"]
    assert "PaymentRiskAgent" not in route.agents


def test_payment_wait_rule():
    route = decide_route("PO-01332 从采购到付款全面排查")
    assert payment_must_wait(route.subject) is True
    route2 = decide_route("INV-004207 是否重复付款？")
    assert payment_must_wait(route2.subject) is False


def test_explicit_want_report_override():
    route = decide_route("差旅住宿标准是多少？", want_report=True)
    assert route.mode == "policy_qa"
    assert infer_want_report(route.mode, True) is True

def test_supplier_name_not_swallow_verbs():
    route = decide_route("全面排查宁波恒远物流有限公司")
    assert route.subject.supplierName == "宁波恒远物流有限公司"
    assert route.mode == "cross"
    assert route.scope == "supplier"


def test_confirmed_mid_not_diluted():
    assert aggregate_risk_level(["低风险", "中风险", "低风险"]) == "中风险"
    assert aggregate_risk_level(["高风险", "证据不足"]) == "高风险"
