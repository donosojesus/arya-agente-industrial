"""Cliente OPC UA con lectura coherente por lotes y reconexion automatica.

Nunca fabrica datos: si la conexion se pierde conserva la ultima muestra real
recibida, marcada como STALE, junto con el error observado.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from asyncua import Client, ua

from .contract import HISTORY_PROFILE_NODE, LIMIT_NODES, NAMESPACE_URI, PROCESS_NODES, RUN_ID_NODE, SEQ_NODE, SIM_TIME_NODE

log = logging.getLogger("arya.view.opcua")

STATE_CONNECTING = "CONNECTING"
STATE_CONNECTED = "CONNECTED"
STATE_DISCONNECTED = "DISCONNECTED"

QUALITY_GOOD = "GOOD"
QUALITY_BAD = "BAD"
QUALITY_STALE = "STALE"


class IncoherentBatch(Exception):
    """El lote cambio durante la lectura en todos los intentos."""


def _iso(ts: datetime | None) -> str | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def is_coherent(first_seq: object, last_seq: object) -> bool:
    """Un lote es coherente si la secuencia no cambio y es par (no en actualizacion)."""
    return isinstance(first_seq, int) and first_seq == last_seq and first_seq % 2 == 0


@dataclass
class Sample:
    run_id: str
    history_profile: str
    seq: int
    sim_time_s: float
    source_timestamp: datetime | None
    received_monotonic: float
    received_at: datetime
    tags: dict[str, dict[str, object]]
    all_good: bool


@dataclass
class TelemetryState:
    endpoint: str
    connection: str = STATE_CONNECTING
    connection_since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_error: str | None = None
    last_error_at: datetime | None = None
    reconnects: int = 0
    incoherent_retries: int = 0
    sample: Sample | None = None
    metadata: dict[str, dict[str, object]] = field(default_factory=dict)
    limits: dict[str, float] = field(default_factory=dict)

    def set_connection(self, state: str) -> None:
        if state != self.connection:
            self.connection = state
            self.connection_since = datetime.now(timezone.utc)

    def record_error(self, exc: BaseException) -> None:
        self.last_error = f"{type(exc).__name__}: {exc}".strip().rstrip(":")
        self.last_error_at = datetime.now(timezone.utc)


class OpcUaPoller:
    def __init__(self, endpoint: str, sample_s: float = 1.0, stale_after_s: float = 5.0, timeout_s: float = 4.0) -> None:
        self.state = TelemetryState(endpoint=endpoint)
        self.sample_s = sample_s
        self.stale_after_s = stale_after_s
        self.timeout_s = timeout_s
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="arya-view-opcua")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        backoff = 0.5
        while True:
            client = Client(self.state.endpoint, timeout=self.timeout_s)
            try:
                self.state.set_connection(STATE_CONNECTING)
                await asyncio.wait_for(client.connect(), timeout=self.timeout_s + 2)
                try:
                    idx = await client.get_namespace_index(NAMESPACE_URI)
                    await self._read_metadata(client, idx)
                    names = [SEQ_NODE, *PROCESS_NODES, RUN_ID_NODE, SIM_TIME_NODE, HISTORY_PROFILE_NODE, SEQ_NODE]
                    nodes = [client.get_node(ua.NodeId(name, idx)) for name in names]
                    self.state.set_connection(STATE_CONNECTED)
                    self.state.last_error = None
                    log.info("connected to %s", self.state.endpoint)
                    backoff = 0.5
                    while True:
                        started = time.monotonic()
                        await self._read_once(client, names, nodes)
                        await asyncio.sleep(max(0.05, self.sample_s - (time.monotonic() - started)))
                finally:
                    try:
                        await asyncio.wait_for(client.disconnect(), timeout=2)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.state.connection == STATE_CONNECTED:
                    log.warning("OPC UA connection lost: %s: %s", type(exc).__name__, exc)
                self.state.record_error(exc)
                self.state.set_connection(STATE_DISCONNECTED)
                self.state.reconnects += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 5.0)

    # ------------------------------------------------------------------ lectura
    async def _read_metadata(self, client: Client, idx: int) -> None:
        metadata: dict[str, dict[str, object]] = {}
        for name in (*PROCESS_NODES, *LIMIT_NODES):
            node = client.get_node(ua.NodeId(name, idx))
            description = await node.read_description()
            unit = None
            for prop in await node.get_properties():
                if (await prop.read_browse_name()).Name == "EngineeringUnits":
                    unit = (await prop.read_value()).DisplayName.Text
            metadata[name] = {"description": description.Text, "unit": unit}
        limit_nodes = [client.get_node(ua.NodeId(name, idx)) for name in LIMIT_NODES]
        values = await client.read_values(limit_nodes)
        self.state.metadata = metadata
        self.state.limits = {name: float(value) for name, value in zip(LIMIT_NODES, values)}

    async def _read_once(self, client: Client, names: list[str], nodes: list, attempts: int = 4) -> None:
        for attempt in range(attempts):
            dvs = await asyncio.wait_for(
                client.read_attributes(nodes, ua.AttributeIds.Value), timeout=self.timeout_s
            )
            if is_coherent(dvs[0].Value.Value, dvs[-1].Value.Value):
                self.state.sample = self._to_sample(names, dvs)
                return
            self.state.incoherent_retries += 1
            await asyncio.sleep(0.02 * (attempt + 1))
        raise IncoherentBatch(f"batch changed during {attempts} consecutive reads")

    def _to_sample(self, names: list[str], dvs: list) -> Sample:
        body = dict(zip(names[1:-1], dvs[1:-1]))
        tags: dict[str, dict[str, object]] = {}
        for name in PROCESS_NODES:
            dv = body[name]
            good = dv.StatusCode.is_good() and dv.Value is not None
            value = dv.Value.Value if dv.Value is not None else None
            tags[name] = {
                "value": list(value) if isinstance(value, (list, tuple)) else value,
                "unit": self.state.metadata.get(name, {}).get("unit"),
                "status": "Good" if good else dv.StatusCode.name,
                "source_timestamp": _iso(dv.SourceTimestamp),
            }
        stamps = {dv.SourceTimestamp for dv in body.values()}
        all_good = all(dv.StatusCode.is_good() for dv in body.values()) and len(stamps) == 1
        return Sample(
            run_id=str(body[RUN_ID_NODE].Value.Value),
            history_profile=str(body[HISTORY_PROFILE_NODE].Value.Value) if HISTORY_PROFILE_NODE in body and body[HISTORY_PROFILE_NODE].Value else "H1",
            seq=int(dvs[0].Value.Value),
            sim_time_s=float(body[SIM_TIME_NODE].Value.Value),
            source_timestamp=body[PROCESS_NODES[0]].SourceTimestamp,
            received_monotonic=time.monotonic(),
            received_at=datetime.now(timezone.utc),
            tags=tags,
            all_good=all_good,
        )

    # ------------------------------------------------------------------ vista publica
    def is_fresh(self) -> bool:
        sample = self.state.sample
        return (
            self.state.connection == STATE_CONNECTED
            and sample is not None
            and time.monotonic() - sample.received_monotonic <= self.stale_after_s
        )

    def public_view(self) -> dict[str, object]:
        state = self.state
        sample = state.sample
        snapshot = None
        if sample is not None:
            age = time.monotonic() - sample.received_monotonic
            if state.connection != STATE_CONNECTED or age > self.stale_after_s:
                quality = QUALITY_STALE
            elif not sample.all_good:
                quality = QUALITY_BAD
            else:
                quality = QUALITY_GOOD
            snapshot = {
                "run_id": sample.run_id,
                "seq": sample.seq,
                "sim_time_s": sample.sim_time_s,
                "source_timestamp": _iso(sample.source_timestamp),
                "received_at": _iso(sample.received_at),
                "age_s": round(age, 2),
                "quality": quality,
                "tags": sample.tags,
            }
        return {
            "server_time": _iso(datetime.now(timezone.utc)),
            "connection": {
                "state": state.connection,
                "since": _iso(state.connection_since),
                "endpoint": state.endpoint,
                "last_error": state.last_error,
                "last_error_at": _iso(state.last_error_at),
                "reconnects": state.reconnects,
            },
            "snapshot": snapshot,
        }
