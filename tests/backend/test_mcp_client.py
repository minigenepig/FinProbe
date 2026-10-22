# -*- coding: utf-8 -*-
from src.backend.app.mcp_client.client import TOOL_NAMES, LocalDispatchMCPClient, schemas_to_openai


def test_openai_tools_keep_hyphen_names():
    schemas = [{"name": n, "description": n, "inputSchema": {"type": "object", "properties": {}}} for n in TOOL_NAMES]
    tools = schemas_to_openai(schemas)
    names = [t["function"]["name"] for t in tools]
    assert names == list(TOOL_NAMES)
    assert "vendor-query" in names


def test_local_client_lists_nine_tools():
    client = LocalDispatchMCPClient()
    names = [s["name"] for s in client.list_tools()]
    assert names == list(TOOL_NAMES)

def test_gr_query_schema_has_supplier_id():
    client = LocalDispatchMCPClient()
    schema = next(item for item in client.list_tools() if item["name"] == "gr-query")
    assert "supplierId" in schema["inputSchema"]["properties"]
    assert "禁止按 PO 循环" in schema["description"]


def test_financial_analysis_schema_forbids_import_and_type():
    client = LocalDispatchMCPClient()
    schema = next(item for item in client.list_tools() if item["name"] == "financial-analysis")
    desc = schema["description"]
    assert "import" in desc
    assert "type" in desc
    assert "to_number" in desc
    assert "result=" in desc


def test_public_event_has_observation():
    from src.backend.app.mcp_client.client import MCPResult

    result = MCPResult(
        ok=True,
        tool="po-query",
        arguments={"supplierId": "VEN-S001"},
        payload={"ok": True, "summary": {"nearThresholdCount": 2, "taxRateCounts": {"0.13": 30}}},
        total_count=36,
        artifact_id="art_1",
    )
    event = result.public_event()
    assert event["label"] == "查采购订单"
    assert "VEN-S001" in event["target"]
    assert "36" in event["observation"]
    assert "近红线" in event["observation"]
