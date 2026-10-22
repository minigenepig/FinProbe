# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Status = Literal[
    "created",
    "routing",
    "locating",
    "running",
    "awaiting_user",
    "reviewing",
    "follow_up",
    "reporting",
    "completed",
    "failed",
    "cancelled",
]

Mode = Literal["clarify", "policy_qa", "lookup", "single", "cross"]
Scope = Literal["policy", "lookup", "document", "supplier", "population"]
RiskLevel = Literal["高风险", "中风险", "低风险", "证据不足"]


class Subject(BaseModel):
    model_config = {"extra": "allow"}

    supplierId: str | None = None
    supplierName: str | None = None
    poId: str | None = None
    grId: str | None = None
    invoiceId: str | None = None
    paymentId: str | None = None
    taxNo: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "clarify"]
    content: str
    ts: str


class CreateInvestigationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    wantReport: bool | None = None


class PostMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class InvestigationSnapshot(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    status: Status
    eventSeq: int = 0
    question: str
    wantReport: bool = False
    mode: str | None = None
    scope: str | None = None
    subject: Subject = Field(default_factory=Subject)
    agents: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    reason: str | None = None
    clarifyQuestion: str | None = None
    answer: str | None = None
    envelopes: list[dict[str, Any]] = Field(default_factory=list)
    evidenceReview: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    reportMarkdown: str | None = None
    followUpRound: int = 0
    overallRiskLevel: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    createdAt: str
    updatedAt: str
    cancelled: bool = False
    locateQueries: list[dict[str, Any]] = Field(default_factory=list)


class RouteObject(BaseModel):
    mode: Mode
    scope: Scope
    subject: Subject
    agents: list[str]
    skills: list[str]
    reason: str
    clarifyQuestion: str | None = None
    wantReport: bool | None = None