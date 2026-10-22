# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from ..errors import AppError
from ..schemas import ChatMessage, CreateInvestigationRequest, InvestigationSnapshot, PostMessageRequest
from ..store.sqlite import now_iso
from ..orchestrator.routing import decide_route, infer_want_report

router = APIRouter()
TZ = timezone(timedelta(hours=8))
HEARTBEAT_SEC = 15


def _ok(payload: dict) -> dict:
    return {"ok": True, **payload}


def _snap(item: InvestigationSnapshot) -> dict:
    return item.model_dump()


@router.get("/v1/investigations")
def list_investigations(request: Request, limit: int = 50):
    items = request.app.state.store.list_recent(min(max(limit, 1), 200))
    return _ok({"investigations": items})


@router.post("/v1/investigations")
def create_investigation(body: CreateInvestigationRequest, request: Request):
    question = body.question.strip()
    if not question:
        raise AppError("VALIDATION", "question 不能为空")
    heuristic = decide_route(question, body.wantReport)
    want = infer_want_report(heuristic.mode, body.wantReport)
    store = request.app.state.store
    snap = store.create(question, want)
    request.app.state.runner.submit(snap.id)
    return JSONResponse(_ok({"investigation": _snap(store.get(snap.id))}), status_code=202)


@router.get("/v1/investigations/{inv_id}")
def get_investigation(inv_id: str, request: Request):
    snap = request.app.state.store.get(inv_id)
    return _ok({"investigation": _snap(snap)})


@router.post("/v1/investigations/{inv_id}/messages")
def post_message(inv_id: str, body: PostMessageRequest, request: Request):
    store = request.app.state.store
    snap = store.get(inv_id)
    if snap.status != "awaiting_user":
        raise AppError("CONFLICT", f"当前状态 {snap.status} 不接受澄清回答")
    content = body.content.strip()
    if not content:
        raise AppError("VALIDATION", "content 不能为空")

    def mutate(item: InvestigationSnapshot) -> None:
        item.question = f"{item.question}\n用户补充：{content}"
        item.messages = list(item.messages) + [ChatMessage(role="user", content=content, ts=now_iso())]
        item.status = "created"
        item.clarifyQuestion = None
        item.cancelled = False

    store.update(inv_id, mutate)
    request.app.state.runner.submit(inv_id)
    return _ok({"investigation": _snap(store.get(inv_id))})


@router.post("/v1/investigations/{inv_id}/cancel")
def cancel_investigation(inv_id: str, request: Request):
    store = request.app.state.store
    snap = store.get(inv_id)
    if snap.status in {"completed", "failed", "cancelled"}:
        raise AppError("CONFLICT", f"调查已结束（{snap.status}），无法取消")

    def mutate(item: InvestigationSnapshot) -> None:
        item.cancelled = True
        item.status = "cancelled"
        item.error = {"code": "CANCELLED", "message": "用户取消", "retryable": False}

    store.update(inv_id, mutate)
    store.append_event(inv_id, "status.changed", {"status": "cancelled"})
    return _ok({"investigation": _snap(store.get(inv_id))})


@router.get("/v1/investigations/{inv_id}/report")
def get_report(inv_id: str, request: Request):
    snap = request.app.state.store.get(inv_id)
    if not snap.report:
        if snap.status in {"reviewing", "follow_up", "reporting", "running"}:
            raise AppError("EVIDENCE_BLOCKED", "报告尚未生成")
        raise AppError("NOT_FOUND", "没有报告")
    draft = bool(snap.report.get("draft")) or not bool((snap.evidenceReview or {}).get("readyForReport"))
    return _ok({"report": snap.report, "markdown": snap.reportMarkdown, "draft": draft})


@router.get("/v1/investigations/{inv_id}/events")
async def stream_events(inv_id: str, request: Request, afterSeq: int | None = None):
    store = request.app.state.store
    store.get(inv_id)
    last_event_id = request.headers.get("last-event-id") or request.headers.get("Last-Event-ID")
    after_header = int(last_event_id) if last_event_id else 0
    after_query = afterSeq if afterSeq is not None else 0
    after = max(after_header, after_query)

    async def gen():
        seq = after
        last_beat = datetime.now(TZ)
        while True:
            if await request.is_disconnected():
                break
            events = await asyncio.to_thread(store.wait_after, inv_id, seq, 1.0)
            for event in events:
                seq = event["seq"]
                yield _sse(event)
                last_beat = datetime.now(TZ)
            snap = await asyncio.to_thread(store.get, inv_id)
            if snap.status in {"completed", "failed", "cancelled"} and seq >= snap.eventSeq:
                yield _sse({"seq": 0, "type": "heartbeat", "ts": now_iso(), "payload": {"status": snap.status}})
                break
            if (datetime.now(TZ) - last_beat).total_seconds() >= HEARTBEAT_SEC:
                yield _sse({"seq": 0, "type": "heartbeat", "ts": now_iso(), "payload": {}})
                last_beat = datetime.now(TZ)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: dict) -> str:
    payload = json.dumps(event, ensure_ascii=False)
    etype = event.get("type") or "message"
    seq = event.get("seq") or 0
    parts = []
    if seq:
        parts.append(f"id: {seq}")
    parts.append(f"event: {etype}")
    parts.append(f"data: {payload}")
    return "\n".join(parts) + "\n\n"