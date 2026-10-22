# -*- coding: utf-8 -*-
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "src" / "contracts"


def test_enums_cover_frozen_names():
    enums = json.loads((CONTRACTS / "enums.json").read_text(encoding="utf-8"))
    assert "vendor-query" in enums["mcpTools"]
    assert "artifact-get" in enums["mcpTools"]
    assert len(enums["mcpTools"]) == 9
    assert "evidence-validation-skill" in enums["skills"]
    assert "供应商主信息异常" in enums["riskTypes"]
    assert "少货多付 / 数量/金额异常" in enums["riskTypes"]
    assert "重复付款" in enums["riskTypes"]
    assert set(enums["riskLevels"]) == {"高风险", "中风险", "低风险", "证据不足"}
    assert "ERP_UNAVAILABLE" in enums["errorCodes"]
    assert "status.changed" in enums["eventTypes"]


def test_error_schema_shape():
    schema = json.loads((CONTRACTS / "errors.schema.json").read_text(encoding="utf-8"))
    assert schema["required"] == ["ok", "error"]


def test_investigation_schema_has_envelope_fields():
    schema = json.loads((CONTRACTS / "investigation.schema.json").read_text(encoding="utf-8"))
    for key in ("mode", "scope", "subject", "agents", "skills", "envelopes", "evidenceReview", "followUpRound"):
        assert key in schema["required"]