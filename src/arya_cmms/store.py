"""Almacen SQLite de ordenes de trabajo."""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

STATUS_DRAFT = "DRAFT_PENDING_APPROVAL"
STATUS_OPEN = "OPEN"
STATUS_REJECTED = "REJECTED"
STATUS_CLOSED = "CLOSED"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_orders (
  id TEXT PRIMARY KEY, asset TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
  created_by TEXT NOT NULL, body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def norm_asset(asset: str) -> str:
    compact = asset.upper().replace("-", "").replace(" ", "")
    return f"{compact[0]}-{compact[1:]}" if len(compact) > 1 and compact[0].isalpha() and compact[1:].isdigit() else asset.upper()


class WorkOrderStore:
    def __init__(self, path: str, seed_path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._seed_path = seed_path
        if self._db.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0] == 0:
            self.reset()

    def close(self) -> None:
        self._db.close()

    def reset(self) -> int:
        """Vuelve al estado inicial: solo las ordenes historicas del archivo semilla."""
        seed = json.loads(Path(self._seed_path).read_text(encoding="utf-8"))
        self._db.execute("DELETE FROM work_orders")
        self._db.execute("DELETE FROM counters")
        for order in seed:
            self._insert({**order, "created_by": "historical-record", "created_at": order["opened_at"] + "T08:00:00Z"})
        self._db.execute("INSERT INTO counters VALUES ('draft', 30)")
        self._db.execute("INSERT INTO counters VALUES ('order', 411)")
        return len(seed)

    def _insert(self, order: dict[str, object]) -> None:
        self._db.execute(
            "INSERT INTO work_orders VALUES (?,?,?,?,?,?)",
            (order["id"], order["asset"], order["status"], order["created_at"], order["created_by"], json.dumps(order, ensure_ascii=False)),
        )

    def _next(self, name: str) -> int:
        self._db.execute("UPDATE counters SET value = value + 1 WHERE name = ?", (name,))
        return self._db.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()[0]

    def get(self, order_id: str) -> dict[str, object] | None:
        row = self._db.execute("SELECT body FROM work_orders WHERE id = ?", (order_id.strip().upper(),)).fetchone()
        return json.loads(row[0]) if row else None

    def search(self, asset: str | None, query: str | None, status: str | None, limit: int) -> list[dict[str, object]]:
        orders = [json.loads(r[0]) for r in self._db.execute("SELECT body FROM work_orders ORDER BY created_at DESC")]
        if asset:
            orders = [o for o in orders if o["asset"] == norm_asset(asset)]
        if status:
            orders = [o for o in orders if o["status"] == status]
        if query:
            words = [w for w in _norm(query).split() if len(w) > 2]
            scored = []
            for order in orders:
                text = _norm(" ".join(str(order.get(k, "")) for k in ("title", "problem", "findings", "actions", "probable_cause", "recommended_action")))
                score = sum(min(text.count(w), 3) for w in words)  # mas menciones, mas relevante
                if score:
                    scored.append((score, order))
            scored.sort(key=lambda item: -item[0])
            orders = [o for _, o in scored]
        return orders[:limit]

    def create_draft(self, fields: dict[str, object]) -> dict[str, object]:
        work_type = fields.get("work_type") or "CORRECTIVE"
        order = {
            **{k: v for k, v in fields.items() if k != "work_type" and v is not None},
            "id": f"WO-DRAFT-{self._next('draft'):04d}",
            "asset": norm_asset(str(fields["asset"])),
            "type": work_type,
            "status": STATUS_DRAFT,
            "created_at": _now(),
            "created_by": "ARYA (AI agent)",
            "requires_human_approval": True,
        }
        self._insert(order)
        return order

    def decide(self, order_id: str, approve: bool, approver: str, comment: str | None) -> dict[str, object] | None:
        order = self.get(order_id)
        if order is None or order["status"] != STATUS_DRAFT:
            return order
        old_id = order["id"]
        if approve:
            year = datetime.now(timezone.utc).year
            order.update(id=f"WO-{year}-{self._next('order'):04d}", status=STATUS_OPEN, draft_id=old_id, approved_by=approver, approved_at=_now())
        else:
            order.update(status=STATUS_REJECTED, rejected_by=approver, rejected_at=_now())
        if comment:
            order["decision_comment"] = comment
        order["requires_human_approval"] = False
        self._db.execute("DELETE FROM work_orders WHERE id = ?", (old_id,))
        self._insert(order)
        return order
