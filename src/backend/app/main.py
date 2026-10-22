# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.dashboard import router as dashboard_router
from .api.erp import router as erp_router
from .api.health import router as health_router
from .api.investigations import router as investigation_router
from .config import Settings, get_settings
from .errors import AppError, error_body
from .llm.client import OpenAICompatibleLLM
from .mcp_client.client import LocalDispatchMCPClient
from .orchestrator.lead import LeadOrchestrator
from .store.sqlite import InvestigationStore

logger = logging.getLogger("finprobe")


class InvestigationRunner:
    def __init__(self, orchestrator_factory: Callable[[], LeadOrchestrator], workers: int = 4) -> None:
        self._factory = orchestrator_factory
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="finprobe-lead")

    def submit(self, inv_id: str) -> None:
        orchestrator = self._factory()
        self._pool.submit(orchestrator.run, inv_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)


def create_app(
    settings: Settings | None = None,
    store: InvestigationStore | None = None,
    mcp=None,
    llm=None,
    runner: InvestigationRunner | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    store = store or InvestigationStore(settings)
    mcp = mcp or LocalDispatchMCPClient(settings)
    llm = llm or OpenAICompatibleLLM(settings)

    def make_orchestrator() -> LeadOrchestrator:
        return LeadOrchestrator(store, mcp, llm)

    runner = runner or InvestigationRunner(make_orchestrator)

    app = FastAPI(title="Finprobe", version="0.1.0")
    app.state.settings = settings
    app.state.store = store
    app.state.mcp = mcp
    app.state.llm = llm
    app.state.runner = runner

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.get("/")
    def root():
        return {
            "ok": True,
            "service": "Finprobe",
            "health": "/v1/health",
            "docs": "/docs",
            "investigations": "POST /v1/investigations",
        }

    app.include_router(health_router)
    app.include_router(investigation_router)
    app.include_router(erp_router)
    app.include_router(dashboard_router)

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(exc.body(), status_code=exc.http_status)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(error_body("VALIDATION", str(exc.errors()), False), status_code=400)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled: %s", exc)
        return JSONResponse(error_body("LLM_ERROR", f"内部错误: {exc}", True), status_code=500)

    @app.on_event("shutdown")
    def _shutdown() -> None:
        try:
            runner.shutdown()
        except Exception:
            pass

    return app


app = create_app()