# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MOCK_ERP_API_KEY = "qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f"


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv_files() -> None:
    for name in (".env", ".env.local"):
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        raw = os.environ.get(name)
        if raw and raw.strip():
            return raw.strip()
    return default


def _llm_from_env() -> tuple[str, str, str]:
    api_key = _first_env("FINPROBE_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
    if os.environ.get("FINPROBE_LLM_BASE_URL"):
        base = os.environ["FINPROBE_LLM_BASE_URL"].strip().rstrip("/")
    elif os.environ.get("DEEPSEEK_BASE_URL") or os.environ.get("DEEPSEEK_API_KEY"):
        base = _first_env("DEEPSEEK_BASE_URL", default="https://api.deepseek.com").rstrip("/")
    else:
        base = "https://api.openai.com/v1"
    model = _first_env("FINPROBE_LLM_MODEL", "DEEPSEEK_MODEL")
    if not model:
        model = "deepseek-flash" if "deepseek.com" in base else "gpt-4.1"
    return api_key, base, model


@dataclass(frozen=True)
class Settings:
    repo_root: Path = REPO_ROOT
    host: str = "127.0.0.1"
    port: int = 8000
    erp_base_url: str = "http://127.0.0.1:8081"
    erp_api_key: str = MOCK_ERP_API_KEY
    session_dir: Path = REPO_ROOT / ".tmp" / "finprobe-sessions"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-flash"
    llm_timeout_sec: float = 120.0
    llm_healthcheck: bool = False
    max_follow_up_rounds: int = 2
    max_event_log: int = 500
    max_react_steps: int = 16
    company_name: str = "启衡精密制造有限公司"


def get_settings() -> Settings:
    load_dotenv_files()
    api_key, base, model = _llm_from_env()
    session = Path(_first_env("FINPROBE_SESSION_DIR", default=str(REPO_ROOT / ".tmp" / "finprobe-sessions")))
    return Settings(
        host=_first_env("FINPROBE_HOST", default="127.0.0.1"),
        port=int(_first_env("FINPROBE_PORT", default="8000")),
        erp_base_url=_first_env("ERP_BASE_URL", default="http://127.0.0.1:8081").rstrip("/"),
        erp_api_key=_first_env("ERP_API_KEY", "API_KEY", default=MOCK_ERP_API_KEY),
        session_dir=session,
        llm_api_key=api_key,
        llm_base_url=base,
        llm_model=model,
        llm_timeout_sec=float(_first_env("FINPROBE_LLM_TIMEOUT", default="120")),
        llm_healthcheck=_bool("FINPROBE_LLM_HEALTHCHECK", False),
    )