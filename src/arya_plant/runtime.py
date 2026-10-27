"""Une el simulador con el reloj real y el servidor OPC UA."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from .config import PlantSettings
from .model import PumpParams
from .opcua_server import PlantOpcUaServer
from .simulator import PlantSimulator

log = logging.getLogger("arya.plant.runtime")


class PlantRuntime:
    def __init__(self, settings: PlantSettings, steps_per_tick: int = 1) -> None:
        """`steps_per_tick` > 1 acelera el tiempo simulado; se usa solo en pruebas."""
        self.settings = settings
        self.steps_per_tick = steps_per_tick
        self.simulator = PlantSimulator(
            params=PumpParams(dt=settings.tick_s, seed=settings.seed),
            fault_duration_s=settings.fault_duration_s,
            recovery_duration_s=settings.recovery_duration_s,
        )
        self.opcua = PlantOpcUaServer(settings.opcua_endpoint)
        self._task: asyncio.Task | None = None
        self.last_publish_monotonic: float | None = None
        self.publish_errors = 0

    async def start(self) -> None:
        await self.opcua.start(self.simulator.snapshot(), self.simulator.limits())
        self.last_publish_monotonic = time.monotonic()
        self._task = asyncio.create_task(self._loop(), name="arya-plant-loop")
        log.info("plant started run_id=%s tick=%.2fs", self.simulator.run_id, self.settings.tick_s)

    async def publish_now(self) -> None:
        """Publica el estado actual (p. ej. justo despues de un RESET)."""
        await self.opcua.publish(self.simulator.snapshot(), datetime.now(timezone.utc))

    async def _loop(self) -> None:
        tick = self.settings.tick_s
        next_deadline = time.monotonic()
        while True:
            next_deadline += tick
            delay = next_deadline - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            elif -delay > 5 * tick:
                # Tras una pausa larga (suspension del equipo) no se recupera el
                # tiempo perdido con una rafaga: el tiempo simulado simplemente continua.
                next_deadline = time.monotonic()
            try:
                for _ in range(self.steps_per_tick):
                    snapshot = self.simulator.step()
                await self.opcua.publish(snapshot, datetime.now(timezone.utc))
                self.last_publish_monotonic = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.publish_errors += 1
                log.exception("plant tick failed")

    def health(self) -> dict[str, object]:
        age = None if self.last_publish_monotonic is None else time.monotonic() - self.last_publish_monotonic
        loop_alive = self._task is not None and not self._task.done()
        max_age = max(3.0, 4 * self.settings.tick_s)
        ok = bool(self.opcua.started and loop_alive and age is not None and age <= max_age)
        return {
            "ok": ok,
            "opcua_server_started": self.opcua.started,
            "simulation_loop_alive": loop_alive,
            "last_publish_age_s": None if age is None else round(age, 3),
            "publish_errors": self.publish_errors,
        }

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.opcua.stop()
