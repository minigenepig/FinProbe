# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from src.backend.app.config import Settings
from src.backend.app.llm.client import LLMResponse
from src.backend.app.mcp_client.client import MCPClient, MCPResult, TOOL_NAMES
from src.backend.app.store.sqlite import InvestigationStore


class FakeLLM:
    model = "fake"

    def __init__(self, configured: bool = True) -> None:
        self._configured = configured
        self.calls = []

    def configured(self) -> bool:
        return self._configured

    def chat(self, messages, tools=None, temperature=0) -> LLMResponse:
        self.calls.append({"messages": messages, "tools": tools})
        return LLMResponse(content='{"mode":"lookup","answer":"ok"}')


class FakeMCP(MCPClient):
    def list_tools(self):
        return [{"name": n, "description": n, "inputSchema": {"type": "object", "properties": {}}} for n in TOOL_NAMES]

    def call(self, name, arguments=None):
        return MCPResult(
            ok=True,
            tool=name,
            arguments=arguments or {},
            payload={"ok": True, "tool": name, "totalCount": 0},
            total_count=0,
        )

    def health(self):
        return {"ok": True, "tools": list(TOOL_NAMES), "transport": "fake"}


class NoopRunner:
    def __init__(self) -> None:
        self.submitted = []

    def submit(self, inv_id: str) -> None:
        self.submitted.append(inv_id)

    def shutdown(self) -> None:
        return None


@pytest.fixture
def tmp_store(tmp_path: Path) -> InvestigationStore:
    settings = Settings(session_dir=tmp_path)
    return InvestigationStore(settings, db_path=tmp_path / "t.db")


@pytest.fixture
def api_client(tmp_store):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from src.backend.app.main import create_app

    settings = tmp_store.settings
    mcp = FakeMCP()
    llm = FakeLLM()
    runner = NoopRunner()
    app = create_app(settings=settings, store=tmp_store, mcp=mcp, llm=llm, runner=runner)
    app.state.runner = runner
    client = TestClient(app)
    client.runner = runner
    return client