# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from ..config import Settings, get_settings
from ..errors import AppError
from ..schemas import ChatMessage, InvestigationSnapshot, Subject

TZ = timezone(timedelta(hours=8))


def now_iso() -> str:
    return datetime.now(TZ).replace(microsecond=0).isoformat()


class InvestigationStore:
    def __init__(self, settings: Settings | None = None, db_path: Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.session_dir = Path(db_path).parent if db_path else self.settings.session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path or (self.session_dir / "finprobe.db")
        self._lock = threading.RLock()
        self._conds: dict[str, threading.Condition] = {}
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _cond(self, inv_id: str) -> threading.Condition:
        return self._conds.setdefault(inv_id, threading.Condition(self._lock))

    def _init(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS investigations (
                id TEXT PRIMARY KEY,
                snapshot TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                investigation_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                type TEXT NOT NULL,
                ts TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY (investigation_id, seq)
            );
            CREATE TABLE IF NOT EXISTS id_seq (
                day TEXT PRIMARY KEY,
                n INTEGER NOT NULL
            );
            """
        )
        self._conn.commit()

    def next_id(self) -> str:
        day = datetime.now(TZ).strftime("%Y%m%d")
        with self._lock:
            row = self._conn.execute("SELECT n FROM id_seq WHERE day=?", (day,)).fetchone()
            n = int(row["n"]) + 1 if row else 1
            self._conn.execute(
                "INSERT INTO id_seq(day, n) VALUES(?, ?) ON CONFLICT(day) DO UPDATE SET n=excluded.n",
                (day, n),
            )
            self._conn.commit()
            return f"INVST-{day}-{n:03d}"

    def next_report_id(self) -> str:
        day = datetime.now(TZ).strftime("%Y%m%d")
        key = f"RPT-{day}"
        with self._lock:
            row = self._conn.execute("SELECT n FROM id_seq WHERE day=?", (key,)).fetchone()
            n = int(row["n"]) + 1 if row else 1
            self._conn.execute(
                "INSERT INTO id_seq(day, n) VALUES(?, ?) ON CONFLICT(day) DO UPDATE SET n=excluded.n",
                (key, n),
            )
            self._conn.commit()
            return f"RPT-{day}-{n:03d}"

    def create(self, question: str, want_report: bool) -> InvestigationSnapshot:
        ts = now_iso()
        inv_id = self.next_id()
        snap = InvestigationSnapshot(
            id=inv_id,
            status="created",
            eventSeq=0,
            question=question,
            wantReport=want_report,
            subject=Subject(),
            messages=[ChatMessage(role="user", content=question, ts=ts)],
            createdAt=ts,
            updatedAt=ts,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO investigations(id, snapshot, created_at, updated_at) VALUES(?,?,?,?)",
                (inv_id, snap.model_dump_json(), ts, ts),
            )
            self._conn.commit()
        return snap

    def list_recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT snapshot FROM investigations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        out = []
        for row in rows:
            snap = InvestigationSnapshot.model_validate_json(row["snapshot"])
            out.append(
                {
                    "id": snap.id,
                    "status": snap.status,
                    "question": snap.question,
                    "overallRiskLevel": snap.overallRiskLevel,
                    "mode": snap.mode,
                    "updatedAt": snap.updatedAt,
                }
            )
        return out

    def get(self, inv_id: str) -> InvestigationSnapshot:

        with self._lock:
            row = self._conn.execute(
                "SELECT snapshot FROM investigations WHERE id=?", (inv_id,)
            ).fetchone()
        if not row:
            raise AppError("NOT_FOUND", f"调查不存在: {inv_id}")
        return InvestigationSnapshot.model_validate_json(row["snapshot"])

    def save(self, snap: InvestigationSnapshot) -> InvestigationSnapshot:
        snap.updatedAt = now_iso()
        with self._lock:
            self._conn.execute(
                "UPDATE investigations SET snapshot=?, updated_at=? WHERE id=?",
                (snap.model_dump_json(), snap.updatedAt, snap.id),
            )
            self._conn.commit()
        return snap

    def update(self, inv_id: str, mutator: Callable[[InvestigationSnapshot], None]) -> InvestigationSnapshot:
        with self._lock:
            snap = self.get(inv_id)
            mutator(snap)
            return self.save(snap)

    def append_event(self, inv_id: str, event_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ts = now_iso()
        body = payload or {}
        with self._lock:
            snap = self.get(inv_id)
            seq = snap.eventSeq + 1
            event = {"seq": seq, "type": event_type, "ts": ts, "payload": body}
            self._conn.execute(
                "INSERT INTO events(investigation_id, seq, type, ts, payload) VALUES(?,?,?,?,?)",
                (inv_id, seq, event_type, ts, json.dumps(body, ensure_ascii=False)),
            )
            # trim
            self._conn.execute(
                """
                DELETE FROM events WHERE investigation_id=? AND seq <= (
                    SELECT MAX(seq) FROM events WHERE investigation_id=?
                ) - ?
                """,
                (inv_id, inv_id, self.settings.max_event_log),
            )
            snap.eventSeq = seq
            snap.updatedAt = ts
            self._conn.execute(
                "UPDATE investigations SET snapshot=?, updated_at=? WHERE id=?",
                (snap.model_dump_json(), ts, inv_id),
            )
            self._conn.commit()
            self._cond(inv_id).notify_all()
            return event

    def events_after(self, inv_id: str, after_seq: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT seq, type, ts, payload FROM events WHERE investigation_id=? AND seq>? ORDER BY seq ASC",
                (inv_id, after_seq),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "seq": row["seq"],
                    "type": row["type"],
                    "ts": row["ts"],
                    "payload": json.loads(row["payload"]),
                }
            )
        return out

    def wait_after(self, inv_id: str, after_seq: int, timeout: float) -> list[dict[str, Any]]:
        cond = self._cond(inv_id)
        with cond:
            events = self.events_after(inv_id, after_seq)
            if events:
                return events
            snap = self.get(inv_id)
            if snap.status in {"completed", "failed", "cancelled"}:
                return []
            cond.wait(timeout)
            return self.events_after(inv_id, after_seq)

    def is_cancelled(self, inv_id: str) -> bool:
        return bool(self.get(inv_id).cancelled) or self.get(inv_id).status == "cancelled"