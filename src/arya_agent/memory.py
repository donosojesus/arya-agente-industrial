"""Memoria persistente del agente: incidentes investigados, ordenes creadas y decisiones humanas."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .textsearch import Bm25Index

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  asset TEXT NOT NULL, run_id TEXT, work_order_id TEXT, body TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class AgentMemory:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def clear(self) -> None:
        self._db.execute("DELETE FROM incidents")

    def record_incident(self, asset: str, run_id: str | None, work_order: dict[str, object]) -> int:
        """Se llama cuando el agente crea un borrador de orden: deja registro de lo investigado."""
        body = {
            "kind": "incident_investigated",
            "problem": work_order.get("problem"),
            "probable_cause": work_order.get("probable_cause"),
            "recommended_action": work_order.get("recommended_action"),
            "evidence": work_order.get("evidence"),
            "work_order_id": work_order.get("id"),
            "work_order_status": work_order.get("status"),
            "human_decision": "PENDING",
        }
        now = _now()
        cur = self._db.execute(
            "INSERT INTO incidents (created_at, updated_at, asset, run_id, work_order_id, body) VALUES (?,?,?,?,?,?)",
            (now, now, asset, run_id, work_order.get("id"), json.dumps(body, ensure_ascii=False)),
        )
        return int(cur.lastrowid)

    def record_decision(self, draft_id: str, work_order: dict[str, object]) -> bool:
        """Actualiza el incidente con la decision humana leida del CMMS (fuente de verdad)."""
        row = self._db.execute("SELECT id, body FROM incidents WHERE work_order_id = ?", (draft_id,)).fetchone()
        if row is None:
            return False
        body = json.loads(row[1])
        status = str(work_order.get("status"))
        body.update(
            work_order_id=work_order.get("id"),
            work_order_status=status,
            human_decision={"OPEN": "APPROVED", "REJECTED": "REJECTED"}.get(status, "PENDING"),
            decided_by=work_order.get("approved_by") or work_order.get("rejected_by"),
            decision_comment=work_order.get("decision_comment"),
        )
        self._db.execute(
            "UPDATE incidents SET body = ?, work_order_id = ?, updated_at = ? WHERE id = ?",
            (json.dumps(body, ensure_ascii=False), work_order.get("id"), _now(), row[0]),
        )
        return True

    def _all(self) -> list[dict[str, object]]:
        rows = self._db.execute("SELECT id, created_at, asset, run_id, body FROM incidents ORDER BY id DESC").fetchall()
        return [{"memory_id": r[0], "recorded_at": r[1], "asset": r[2], "run_id": r[3], **json.loads(r[4])} for r in rows]

    def search(self, query: str | None, limit: int = 5) -> list[dict[str, object]]:
        items = self._all()
        if not query or not items:
            return items[:limit]
        index = Bm25Index([json.dumps(i, ensure_ascii=False) for i in items])
        hits = [items[i] for i, _ in index.search(query, limit)]
        return hits or items[:limit]  # sin coincidencias: lo mas reciente, que suele ser lo pedido

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0]
