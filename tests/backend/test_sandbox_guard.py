# -*- coding: utf-8 -*-
import sys
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parents[2] / "mcp-server"
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))

from sandbox import execute_financial_analysis  # type: ignore  # noqa: E402


def test_records_default_empty_list():
    result = execute_financial_analysis("result={'n': len(records)}")
    assert result == {"n": 0}


def test_type_and_import_still_forbidden():
    try:
        execute_financial_analysis("x=type(1)\nresult=x")
        raise AssertionError("type should be forbidden")
    except Exception as exc:
        assert "type" in str(exc).lower() or "禁止" in str(exc)


def test_try_except_and_isinstance_allowed():
    code = """
def to_num(v):
    try:
        if v is None:
            return 0.0
        return float(v)
    except Exception:
        return 0.0

n = 0
for r in records:
    if isinstance(r, dict):
        n += 1
result = {"n": n, "v": to_num("12.5")}
"""
    result = execute_financial_analysis(code, datasets={"art": [{"a": 1}, {"b": 2}]})
    assert result == {"n": 2, "v": 12.5}
