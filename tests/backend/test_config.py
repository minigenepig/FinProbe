# -*- coding: utf-8 -*-
from src.backend.app.config import MOCK_ERP_API_KEY, Settings, get_settings


def test_mock_erp_key_is_fixed():
    assert MOCK_ERP_API_KEY == "qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f"
    assert Settings().erp_api_key == MOCK_ERP_API_KEY


def test_deepseek_env_aliases(monkeypatch):
    monkeypatch.delenv("FINPROBE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("FINPROBE_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("FINPROBE_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash")
    settings = get_settings()
    assert settings.llm_api_key == "sk-test-deepseek"
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-flash"
    assert settings.erp_api_key == MOCK_ERP_API_KEY