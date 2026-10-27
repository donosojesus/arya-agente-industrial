"""Traza operacional del agente: eventos estructurados para la interfaz y para auditoria.

Registra que se pidio, que herramienta se uso, cuanto tardo y con que resultado.
No registra razonamiento interno del modelo ni secretos.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

_THINK = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)


def strip_private_reasoning(text: str | None) -> str:
    """Elimina bloques <think>...</think> que algunos modelos emiten antes de responder."""
    return _THINK.sub("", text or "").strip()


class TraceHub:
    def __init__(self, log_path: str | None = None, capacity: int = 2000) -> None:
        self._events: deque[dict[str, object]] = deque(maxlen=capacity)
        self._seq = 0
        self._subscribers: set[asyncio.Queue] = set()
        self._log = None
        if log_path:
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            self._log = open(log_path, "a", encoding="utf-8")

    def publish(self, kind: str, **fields: object) -> dict[str, object]:
        self._seq += 1
        event = {"seq": self._seq, "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                 "type": kind, **fields}
        self._events.append(event)
        if self._log:
            self._log.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._log.flush()
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._subscribers.discard(queue)  # cliente demasiado lento: se reconectara
        return event

    def since(self, seq: int, limit: int = 500) -> list[dict[str, object]]:
        return [e for e in self._events if e["seq"] > seq][-limit:]

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def clear(self) -> None:
        self._events.clear()
        self.publish("system", message="Traza reiniciada")

    @property
    def last_seq(self) -> int:
        return self._seq
