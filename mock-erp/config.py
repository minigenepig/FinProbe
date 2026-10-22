# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("ERP_DATA_DIR", ROOT / "data"))
HOST = os.environ.get("ERP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ERP_PORT", "8081"))
API_KEY = os.environ.get("ERP_API_KEY", "qh_live_5fc45e4c22871d81ef7d47ea7b69aa2f")
COMPANY_NAME = "启衡精密制造有限公司"
