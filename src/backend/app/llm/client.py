# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from ..config import Settings, get_settings


class LLMError(RuntimeError):
    def __init__(self, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    model: str

    def configured(self) -> bool: ...

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0,
    ) -> LLMResponse: ...


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.llm_model
        self.api_key = self.settings.llm_api_key
        self.base_url = self.settings.llm_base_url
        self.timeout = self.settings.llm_timeout_sec

    def configured(self) -> bool:
        return bool(self.api_key)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0,
    ) -> LLMResponse:
        if not self.configured():
            raise LLMError("未配置 FINPROBE_LLM_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY", retryable=False)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if "deepseek.com" in self.base_url:
            body["thinking"] = {"type": "disabled"}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(url, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise LLMError(f"无法连接 LLM: {exc}") from exc
        if resp.status_code >= 400:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = []
        for item in message.get("tool_calls") or []:
            fn = item.get("function") or {}
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                {
                    "id": item.get("id"),
                    "name": fn.get("name"),
                    "arguments": args,
                    "arguments_raw": args_raw,
                }
            )
        return LLMResponse(content=message.get("content"), tool_calls=tool_calls, raw=data)


def extract_json(text: str) -> dict[str, Any]:
    if not text:
        raise ValueError("empty LLM content")
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(stripped[start : end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError("LLM 输出不是 JSON 对象")