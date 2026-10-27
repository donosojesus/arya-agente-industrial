"""Simulador de la planta: modelo fisico + alarmas + escenario de demo.

Es sincrono y no depende del tiempo real: cada `step()` avanza un paso fijo de
tiempo simulado. El reloj y el transporte viven en `runtime.py`.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .alarms import AlarmConfig, AlarmEvaluator
from .model import PumpModel, PumpParams
from .scenarios import DEFAULT_SCENARIO, SCENARIOS
from .tags import LIMIT_TAGS, PROCESS_TAGS

MODE_NORMAL = "NORMAL"
MODE_DEGRADATION = "DEGRADATION"
MODE_RECOVERY = "RECOVERY"

MIN_FAULT_DURATION_S = 30.0
MAX_FAULT_DURATION_S = 900.0
MAX_SCHEDULE_DELAY_S = 4 * 3600.0
SCENARIO_IDS = tuple(SCENARIOS)

_DECIMALS = {t.name: t.decimals for t in PROCESS_TAGS}


class ScenarioConflict(Exception):
    """El comando no aplica en el estado actual del escenario."""


@dataclass(frozen=True)
class Snapshot:
    """Lote publico de un instante de simulacion (lo unico que sale por OPC UA)."""

    run_id: str
    sim_time_s: float
    values: dict[str, object]


def default_run_id() -> str:
    now = datetime.now(timezone.utc)
    return f"run-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


class PlantSimulator:
    def __init__(
        self,
        params: PumpParams | None = None,
        alarm_config: AlarmConfig | None = None,
        fault_duration_s: float = 180.0,
        recovery_duration_s: float = 90.0,
        run_id_factory: Callable[[], str] = default_run_id,
    ) -> None:
        self._validate_duration(fault_duration_s)
        self.model = PumpModel(params)
        self.alarms = AlarmEvaluator(alarm_config)
        self.default_fault_duration_s = float(fault_duration_s)
        self.recovery_duration_s = float(recovery_duration_s)
        self._run_id_factory = run_id_factory
        self._start_run()

    # ------------------------------------------------------------------ comandos
    def _start_run(self) -> None:
        self.model.reset()
        self.alarms.reset()
        self.run_id = self._run_id_factory()
        self.mode = MODE_NORMAL
        self.scenario_id: str | None = None
        self.history_profile = "H1"  # H2: historial con desgaste (escenario C); se mantiene hasta el proximo RESET
        self.fault_duration_s: float | None = None
        self.fault_started_at_s: float | None = None
        self._scheduled: dict[str, object] | None = None
        self._alarm_level, self._active_alarms = self.alarms.update(self.model.signals(), 0.0)

    @staticmethod
    def _validate_duration(duration_s: float) -> None:
        if not (MIN_FAULT_DURATION_S <= duration_s <= MAX_FAULT_DURATION_S):
            raise ValueError(
                f"fault duration must be between {MIN_FAULT_DURATION_S:.0f} and {MAX_FAULT_DURATION_S:.0f} seconds"
            )

    def reset(self) -> None:
        """Reinicializa explicitamente la simulacion y asigna un nuevo run_id."""
        self._start_run()

    def _resolve(self, duration_s: float | None, scenario: str | None) -> tuple[float, str]:
        scenario_id = scenario or DEFAULT_SCENARIO
        if scenario_id not in SCENARIOS:
            raise ValueError(f"unknown scenario; valid: {', '.join(SCENARIO_IDS)}")
        own = SCENARIOS[scenario_id].duration_s
        duration = (own or self.default_fault_duration_s) if duration_s is None else float(duration_s)
        self._validate_duration(duration)
        return duration, scenario_id

    def inject_fault(self, duration_s: float | None = None, scenario: str | None = None) -> None:
        duration, scenario_id = self._resolve(duration_s, scenario)
        if self.mode == MODE_DEGRADATION:
            raise ScenarioConflict("a fault is already active in this run; use RESET DEMO to start over")
        if self.mode == MODE_RECOVERY:
            raise ScenarioConflict("the plant is still recovering; wait until it is NORMAL or use RESET DEMO")
        self.model.start_degradation(duration, SCENARIOS[scenario_id].profile)
        self.mode = MODE_DEGRADATION
        self.scenario_id = scenario_id
        if scenario_id == "charlie":
            self.history_profile = "H2"
        self.fault_duration_s = duration
        self.fault_started_at_s = self.model.time_s

    def schedule_fault(self, delay_s: float, duration_s: float | None = None, scenario: str | None = None) -> None:
        """Programa una falla para dentro de `delay_s` segundos simulados.

        Si al llegar el momento la planta no esta en NORMAL, espera a que lo este.
        RESET cancela la programacion.
        """
        if not (0 < delay_s <= MAX_SCHEDULE_DELAY_S):
            raise ValueError(f"delay must be between 1 and {MAX_SCHEDULE_DELAY_S:.0f} seconds")
        duration, scenario_id = self._resolve(duration_s, scenario)
        self._scheduled = {"at_s": self.model.time_s + float(delay_s), "duration_s": duration, "scenario": scenario_id}

    def cancel_schedule(self) -> bool:
        had = self._scheduled is not None
        self._scheduled = None
        return had

    def normal_operation(self) -> bool:
        """Retira la condicion de falla. Devuelve False si no habia nada que retirar.

        No normaliza las senales de inmediato: la severidad decrece gradualmente y
        la temperatura baja segun su inercia termica. Solo RESET reinicializa.
        """
        if self.mode != MODE_DEGRADATION:
            return False
        self.model.start_recovery(self.recovery_duration_s)
        self.mode = MODE_RECOVERY
        return True

    # ------------------------------------------------------------------ avance
    def step(self) -> Snapshot:
        self.model.step()
        self._alarm_level, self._active_alarms = self.alarms.update(self.model.signals(), self.model.params.dt)
        if self.mode == MODE_RECOVERY and self.model.severity == 0.0:
            self.mode = MODE_NORMAL
        pending = self._scheduled
        if pending is not None and self.mode == MODE_NORMAL and self.model.time_s >= pending["at_s"]:
            self._scheduled = None
            self.inject_fault(pending["duration_s"], pending["scenario"])
        return self.snapshot()

    def snapshot(self) -> Snapshot:
        s = self.model.signals()
        raw = {
            "P101.MOTOR_TEMP": s.motor_temp,
            "P101.VIBRATION": s.vibration,
            "P101.CURRENT": s.current,
            "P101.DISCHARGE_PRESSURE": s.discharge_pressure,
            "P101.FLOW": s.flow,
            "P101.RPM": s.rpm,
        }
        values: dict[str, object] = {name: round(value, _DECIMALS[name]) for name, value in raw.items()}
        # No se simula un disparo de proteccion: la bomba sigue RUNNING con alarma.
        values["P101.STATUS"] = "RUNNING"
        values["RUN.HISTORY_PROFILE"] = self.history_profile
        values["P101.ALARM_LEVEL"] = self._alarm_level
        values["P101.ACTIVE_ALARMS"] = list(self._active_alarms)
        return Snapshot(run_id=self.run_id, sim_time_s=round(self.model.time_s, 3), values=values)

    def limits(self) -> dict[str, float]:
        c = self.alarms.config
        values = {
            "P101.MOTOR_TEMP.HI": c.temp_warning,
            "P101.MOTOR_TEMP.HIHI": c.temp_alarm,
            "P101.VIBRATION.HI": c.vibration_warning,
            "P101.VIBRATION.HIHI": c.vibration_alarm,
            "P101.FLOW.LO": c.flow_low_warning,
            "P101.FLOW.LOLO": c.flow_low_alarm,
        }
        assert set(values) == {t.name for t in LIMIT_TAGS}
        return values

    # ------------------------------------------------------------------ presentador
    def scenario_state(self) -> dict[str, object]:
        """Estado del escenario para el presentador. No incluye la causa de la falla."""
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "sim_time_s": round(self.model.time_s, 3),
            "scenario": self.scenario_id,
            "history_profile": self.history_profile,
            "fault_progress": round(self.model.severity, 4),
            "fault_duration_s": self.fault_duration_s,
            "fault_started_at_s": self.fault_started_at_s,
            "alarm_level": self._alarm_level,
            "scheduled_fault": None
            if self._scheduled is None
            else {
                "scenario": self._scheduled["scenario"],
                "duration_s": self._scheduled["duration_s"],
                "starts_in_s": round(max(0.0, self._scheduled["at_s"] - self.model.time_s), 1),
            },
        }

    def ground_truth_for_evaluation(self) -> dict[str, object] | None:
        """Causa real del escenario inyectado en este ensayo (None si no hubo falla).

        No se publica por ningun transporte; uso exclusivo de evaluacion.
        """
        if self.scenario_id is None:
            return None
        return {**SCENARIOS[self.scenario_id].ground_truth, "scenario": self.scenario_id, "run_id": self.run_id}
