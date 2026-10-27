"""Control deterministico de alarmas con persistencia temporal e histeresis.

Las alarmas dependen solo de las senales y sus limites, nunca del estado
interno del escenario.
"""

from __future__ import annotations

from dataclasses import dataclass

LEVEL_NORMAL = "NORMAL"
LEVEL_WARNING = "WARNING"
LEVEL_ALARM = "ALARM"
_LEVEL_ORDER = {LEVEL_NORMAL: 0, LEVEL_WARNING: 1, LEVEL_ALARM: 2}


@dataclass(frozen=True)
class AlarmPoint:
    code: str  # p. ej. "P101.VIBRATION.HI"
    signal: str  # atributo de PumpSignals
    limit: float
    deadband: float  # la alarma se libera al alejarse del limite mas que esta banda
    level: str
    low: bool = False  # True: alarma por valor bajo (<= limite)


@dataclass(frozen=True)
class AlarmConfig:
    temp_warning: float = 75.0
    temp_alarm: float = 88.0
    temp_deadband: float = 2.0
    vibration_warning: float = 4.5
    vibration_alarm: float = 7.1
    vibration_deadband: float = 0.3
    flow_low_warning: float = 52.0
    flow_low_alarm: float = 45.0
    flow_deadband: float = 1.0
    on_delay_s: float = 2.0  # la condicion debe persistir para activar
    off_delay_s: float = 3.0  # y para liberar

    def points(self) -> tuple[AlarmPoint, ...]:
        return (
            AlarmPoint("P101.VIBRATION.HI", "vibration", self.vibration_warning, self.vibration_deadband, LEVEL_WARNING),
            AlarmPoint("P101.VIBRATION.HIHI", "vibration", self.vibration_alarm, self.vibration_deadband, LEVEL_ALARM),
            AlarmPoint("P101.MOTOR_TEMP.HI", "motor_temp", self.temp_warning, self.temp_deadband, LEVEL_WARNING),
            AlarmPoint("P101.MOTOR_TEMP.HIHI", "motor_temp", self.temp_alarm, self.temp_deadband, LEVEL_ALARM),
            AlarmPoint("P101.FLOW.LO", "flow", self.flow_low_warning, self.flow_deadband, LEVEL_WARNING, low=True),
            AlarmPoint("P101.FLOW.LOLO", "flow", self.flow_low_alarm, self.flow_deadband, LEVEL_ALARM, low=True),
        )


class AlarmEvaluator:
    def __init__(self, config: AlarmConfig | None = None) -> None:
        self.config = config or AlarmConfig()
        self._points = self.config.points()
        self.reset()

    def reset(self) -> None:
        self._active = {p.code: False for p in self._points}
        self._timer = {p.code: 0.0 for p in self._points}

    def update(self, signals: object, dt: float) -> tuple[str, list[str]]:
        """Evalua un paso de `dt` segundos. Devuelve (nivel, alarmas activas)."""
        for point in self._points:
            value = getattr(signals, point.signal)
            if self._active[point.code]:
                if point.low:
                    wants_change = value > point.limit + point.deadband
                else:
                    wants_change = value < point.limit - point.deadband
                delay = self.config.off_delay_s
            else:
                wants_change = value <= point.limit if point.low else value >= point.limit
                delay = self.config.on_delay_s
            if wants_change:
                self._timer[point.code] += dt
                if self._timer[point.code] >= delay:
                    self._active[point.code] = not self._active[point.code]
                    self._timer[point.code] = 0.0
            else:
                self._timer[point.code] = 0.0
        active = [p.code for p in self._points if self._active[p.code]]
        level = LEVEL_NORMAL
        for point in self._points:
            if self._active[point.code] and _LEVEL_ORDER[point.level] > _LEVEL_ORDER[level]:
                level = point.level
        return level, active
