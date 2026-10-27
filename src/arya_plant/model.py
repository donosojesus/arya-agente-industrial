"""Modelo fisico simplificado de la bomba centrifuga P-101.

El modelo no conoce relojes de pared ni transporte: avanza un paso fijo `dt`
de tiempo simulado por cada llamada a `step()`. Con la misma semilla y la misma
secuencia de llamadas produce exactamente la misma evolucion.

Las senales no son ruidos independientes: derivan de tres variables latentes
suaves (demanda hidraulica, excitacion mecanica y ambiente) y de la severidad
de la degradacion, de modo que permanecen correlacionadas.

Los valores son ficticios y demostrativos; no son limites normativos.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class PumpParams:
    dt: float = 0.5  # paso de integracion en segundos simulados
    seed: int = 101

    # Punto de operacion normal
    temp_nominal: float = 57.0  # degC
    vibration_nominal: float = 2.0  # mm/s RMS
    current_nominal: float = 11.5  # A
    pressure_nominal: float = 4.8  # bar
    flow_nominal: float = 62.0  # m3/h
    rpm_nominal: float = 1480.0  # rpm

    # Constantes de tiempo (s)
    tau_thermal: float = 25.0  # inercia termica del motor
    tau_demand: float = 20.0
    tau_mech: float = 5.0
    tau_ambient: float = 120.0

    # Sensibilidad a las variables latentes (por unidad de desviacion estandar)
    flow_per_demand: float = 0.60
    pressure_per_demand: float = -0.035  # a velocidad fija, mas caudal => menos altura
    current_per_demand: float = 0.12
    rpm_per_demand: float = -0.8  # mas carga => algo mas de deslizamiento
    temp_per_demand: float = 0.4
    temp_per_ambient: float = 0.6
    vibration_jitter: float = 0.06



@dataclass(frozen=True)
class FaultProfile:
    """Efecto de una degradacion a severidad 1.0 sobre cada senal."""

    vibration_gain: float = 0.0
    vibration_jitter: float = 0.0
    temp_gain: float = 0.0  # sobre la temperatura de equilibrio
    current_gain: float = 0.0
    flow_loss: float = 0.0  # fraccion
    pressure_loss: float = 0.0  # fraccion
    rpm_drop: float = 0.0


NO_FAULT = FaultProfile()


@dataclass(frozen=True)
class PumpSignals:
    motor_temp: float
    vibration: float
    current: float
    discharge_pressure: float
    flow: float
    rpm: float


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class PumpModel:
    def __init__(self, params: PumpParams | None = None) -> None:
        self.params = params or PumpParams()
        self.reset()

    def reset(self) -> None:
        """Vuelve al estado inicial y reinicia la secuencia pseudoaleatoria."""
        self._rng = random.Random(self.params.seed)
        self.steps = 0
        self.severity = 0.0  # 0 = sano, 1 = degradacion completa
        self.profile = NO_FAULT
        self._severity_rate = 0.0  # variacion de severidad por segundo
        self._x_demand = 0.0
        self._x_mech = 0.0
        self._x_ambient = 0.0
        self._motor_temp = self._temp_equilibrium()

    @property
    def time_s(self) -> float:
        return self.steps * self.params.dt

    def start_degradation(self, duration_s: float, profile: FaultProfile) -> None:
        """La severidad crece linealmente hasta 1.0 en `duration_s` (desde 0)."""
        if duration_s <= 0:
            raise ValueError("duration_s must be positive")
        if self.severity != 0.0:
            raise ValueError("a degradation can only start from a healthy state")
        self.profile = profile
        self._severity_rate = 1.0 / duration_s

    def start_recovery(self, duration_s: float) -> None:
        """La severidad decrece linealmente; `duration_s` es el tiempo desde 1.0 hasta 0."""
        if duration_s <= 0:
            raise ValueError("duration_s must be positive")
        self._severity_rate = -1.0 / duration_s

    def _ou(self, x: float, tau: float) -> float:
        """Proceso de Ornstein-Uhlenbeck discretizado de forma exacta (varianza 1)."""
        a = math.exp(-self.params.dt / tau)
        return _clamp(a * x + math.sqrt(1.0 - a * a) * self._rng.gauss(0.0, 1.0), -3.0, 3.0)

    def _temp_equilibrium(self) -> float:
        p = self.params
        return (
            p.temp_nominal
            + self.profile.temp_gain * self.severity
            + p.temp_per_demand * self._x_demand
            + p.temp_per_ambient * self._x_ambient
        )

    def step(self) -> None:
        p = self.params
        self.severity = _clamp(self.severity + self._severity_rate * p.dt, 0.0, 1.0)
        if self.severity == 0.0 and self._severity_rate < 0.0:
            self._severity_rate = 0.0  # recuperacion completada
        # Siempre se extraen los tres valores en el mismo orden (determinismo).
        self._x_demand = self._ou(self._x_demand, p.tau_demand)
        self._x_mech = self._ou(self._x_mech, p.tau_mech)
        self._x_ambient = self._ou(self._x_ambient, p.tau_ambient)
        # Inercia termica: respuesta de primer orden hacia la temperatura de equilibrio.
        alpha = 1.0 - math.exp(-p.dt / p.tau_thermal)
        self._motor_temp += (self._temp_equilibrium() - self._motor_temp) * alpha
        self.steps += 1

    def signals(self) -> PumpSignals:
        p = self.params
        f = self.profile
        s = self.severity
        vibration = (
            p.vibration_nominal
            + f.vibration_gain * s
            + (p.vibration_jitter + f.vibration_jitter * s) * self._x_mech
        )
        return PumpSignals(
            motor_temp=self._motor_temp,
            vibration=max(0.0, vibration),
            current=p.current_nominal + f.current_gain * s + p.current_per_demand * self._x_demand,
            discharge_pressure=p.pressure_nominal * (1.0 - f.pressure_loss * s)
            + p.pressure_per_demand * self._x_demand,
            flow=p.flow_nominal * (1.0 - f.flow_loss * s) + p.flow_per_demand * self._x_demand,
            rpm=p.rpm_nominal - f.rpm_drop * s + p.rpm_per_demand * self._x_demand,
        )
