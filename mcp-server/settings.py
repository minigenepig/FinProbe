# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ERP_BASE_URL = os.environ.get("ERP_BASE_URL", "http://127.0.0.1:8081")
ERP_API_KEY = os.environ.get("ERP_API_KEY", "qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f")
ARTIFACT_DIR = Path(os.environ.get("ARTIFACT_DIR", REPO_ROOT / ".tmp" / "finprobe-artifacts"))
SAMPLE_SIZE = int(os.environ.get("MCP_SAMPLE_SIZE", "5"))
INLINE_LIMIT = int(os.environ.get("MCP_INLINE_LIMIT", "8"))
VENDOR_INLINE_LIMIT = int(os.environ.get("MCP_VENDOR_INLINE_LIMIT", "50"))
MAX_FETCH = int(os.environ.get("MCP_MAX_FETCH", "2000"))
SANDBOX_TIMEOUT_SEC = float(os.environ.get("MCP_SANDBOX_TIMEOUT", "5"))
