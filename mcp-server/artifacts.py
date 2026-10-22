# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from settings import ARTIFACT_DIR


class ArtifactStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or ARTIFACT_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, records: list[dict[str, Any]], source_tool: str, query: dict[str, Any]) -> dict[str, Any]:
        artifact_id = "art_" + uuid.uuid4().hex[:12]
        payload = {
            "artifactId": artifact_id,
            "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "sourceTool": source_tool,
            "query": query,
            "recordCount": len(records),
            "records": records,
        }
        path = self.root / f"{artifact_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        fields: list[str] = []
        if records:
            fields = list(records[0].keys())
        return {
            "artifactId": artifact_id,
            "path": str(path),
            "recordCount": len(records),
            "fields": fields,
        }

    def load(self, artifact_id: str) -> dict[str, Any]:
        path = self.root / f"{artifact_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"artifact not found: {artifact_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def slice(
        self,
        artifact_id: str,
        offset: int = 0,
        limit: int = 5,
        ids: list[str] | None = None,
        id_field: str | None = None,
    ) -> dict[str, Any]:
        payload = self.load(artifact_id)
        records = payload.get("records") or []
        if ids:
            id_set = set(ids)
            guessed = id_field or _guess_id_field(records)
            records = [r for r in records if str(r.get(guessed)) in id_set]
        offset = max(int(offset or 0), 0)
        limit = min(max(int(limit or 5), 1), 50)
        return {
            "artifactId": artifact_id,
            "sourceTool": payload.get("sourceTool"),
            "query": payload.get("query"),
            "recordCount": payload.get("recordCount"),
            "offset": offset,
            "limit": limit,
            "returnedCount": min(limit, max(len(records) - offset, 0)),
            "data": records[offset : offset + limit],
        }


def _guess_id_field(records: list[dict[str, Any]]) -> str:
    if not records:
        return "id"
    keys = records[0].keys()
    for candidate in (
        "invoiceId",
        "poId",
        "grId",
        "paymentId",
        "approvalId",
        "id",
        "docId",
    ):
        if candidate in keys:
            return candidate
    return next(iter(keys))
