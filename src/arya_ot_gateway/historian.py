"""Historian local en SQLite (modo WAL). Guarda solo muestras realmente recibidas."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SIGNALS = {
    "motor_temp": ("P101.MOTOR_TEMP", "°C"),
    "vibration": ("P101.VIBRATION", "mm/s"),
    "current": ("P101.CURRENT", "A"),
    "discharge_pressure": ("P101.DISCHARGE_PRESSURE", "bar"),
    "flow": ("P101.FLOW", "m³/h"),
    "rpm": ("P101.RPM", "rpm"),
}
TAG_TO_SIGNAL = {tag: name for name, (tag, _) in SIGNALS.items()}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  ts REAL NOT NULL, run_id TEXT NOT NULL, seq INTEGER NOT NULL,
  motor_temp REAL, vibration REAL, current REAL, discharge_pressure REAL, flow REAL, rpm REAL,
  status TEXT, alarm_level TEXT, active_alarms TEXT,
  PRIMARY KEY (run_id, seq)
);
CREATE INDEX IF NOT EXISTS samples_ts ON samples (ts);
CREATE TABLE IF NOT EXISTS alarm_events (
  ts REAL NOT NULL, run_id TEXT NOT NULL, code TEXT NOT NULL, state TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS alarm_events_ts ON alarm_events (ts);
"""


class Historian:
    def __init__(self, path: str, retention_days: float = 7.0) -> None:
        self.path = path
        self.retention_s = retention_days * 86400.0
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)
        self._last_key: tuple[str, int] | None = None
        self._last_alarms: tuple[str, set[str]] | None = None
        self._last_purge = 0.0
        self.samples_written = 0

    @property
    def db(self) -> sqlite3.Connection:
        return self._db

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------ escritura
    def record(self, ts: float, run_id: str, seq: int, tags: dict[str, dict[str, object]]) -> bool:
        """Guarda una muestra nueva. Devuelve False si ya estaba guardada."""
        if self._last_key == (run_id, seq):
            return False
        self._last_key = (run_id, seq)
        active = list(tags["P101.ACTIVE_ALARMS"]["value"] or [])
        values = [tags[tag]["value"] for tag, _ in SIGNALS.values()]
        cur = self._db.execute(
            "INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (ts, run_id, seq, *values, tags["P101.STATUS"]["value"], tags["P101.ALARM_LEVEL"]["value"], json.dumps(active)),
        )
        if cur.rowcount == 0:
            return False
        self.samples_written += 1
        # Eventos de alarma: transiciones observadas entre muestras consecutivas del mismo ensayo.
        previous = self._last_alarms[1] if self._last_alarms and self._last_alarms[0] == run_id else set()
        current = set(active)
        for code in sorted(current - previous):
            self._db.execute("INSERT INTO alarm_events VALUES (?,?,?,?)", (ts, run_id, code, "ACTIVE"))
        for code in sorted(previous - current):
            self._db.execute("INSERT INTO alarm_events VALUES (?,?,?,?)", (ts, run_id, code, "CLEARED"))
        self._last_alarms = (run_id, current)
        if ts - self._last_purge > 3600:
            self._last_purge = ts
            self._db.execute("DELETE FROM samples WHERE ts < ?", (ts - self.retention_s,))
            self._db.execute("DELETE FROM alarm_events WHERE ts < ?", (ts - self.retention_s,))
        return True

    # ------------------------------------------------------------------ lectura
    def series(self, signals: list[str], since_ts: float, run_id: str | None) -> list[tuple]:
        columns = ", ".join(signals)
        query = f"SELECT ts, {columns} FROM samples WHERE ts >= ?"  # nombres validados contra SIGNALS
        params: list[object] = [since_ts]
        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)
        return self._db.execute(query + " ORDER BY ts", params).fetchall()

    def alarm_events(self, since_ts: float, run_id: str | None) -> list[tuple]:
        query = "SELECT ts, run_id, code, state FROM alarm_events WHERE ts >= ?"
        params: list[object] = [since_ts]
        if run_id is not None:
            query += " AND run_id = ?"
            params.append(run_id)
        return self._db.execute(query + " ORDER BY ts", params).fetchall()

    def active_since(self, run_id: str, code: str) -> float | None:
        row = self._db.execute(
            "SELECT ts FROM alarm_events WHERE run_id = ? AND code = ? AND state = 'ACTIVE' ORDER BY ts DESC LIMIT 1",
            (run_id, code),
        ).fetchone()
        return row[0] if row else None

    def stats(self) -> dict[str, object]:
        count, first, last = self._db.execute("SELECT COUNT(*), MIN(ts), MAX(ts) FROM samples").fetchone()
        return {"samples": count, "first_ts": first, "last_ts": last, "now": time.time()}
