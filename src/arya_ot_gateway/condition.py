"""Historial de condicion de 6 meses de la P-101 y su arquitectura medallon (bronce, plata, oro).

El historial es SIMULADO y determinista: reproduce la fisica de la bomba de la ficha FT-P101-001 (curva
altura-caudal, corriente segun la carga, temperatura segun el ambiente), la operacion de la planta (carga
diaria, paradas de domingo, paradas programadas) y los incidentes ya registrados en el CMMS (mayo y julio).

Hay dos variantes. La sana no tiene degradacion. La otra agrega un desgaste incipiente en las ultimas
semanas, siempre bajo los limites de alarma. El nombre de la variante y su causa NO salen por la API de
lectura: el agente debe deducir la condicion de los datos, igual que en los escenarios A y B.

- Bronce: lo que llegaria del SCADA cada 10 minutos, con huecos de comunicacion y picos de sensor.
- Plata: solo la bomba en marcha, sin transitorios de arranque ni picos, normalizada a 62 m3/h y 20 C de
  ambiente, con el deficit de presion respecto de la curva del fabricante.
- Oro: indicadores diarios listos para tendencia y proyeccion.
"""

from __future__ import annotations

import math
import random
import sqlite3
import statistics
import time
from datetime import datetime, timedelta, timezone

LOCAL_TZ = timezone(timedelta(hours=-3))  # hora de la planta, fija para que los dias no dependan del contenedor
STEP_S = 600  # una muestra de bronce cada 10 minutos
DAYS = 183
VARIANTS = ("healthy", "incipient")
REFERENCE_VIBRATION = 1.9  # mm/s, medida en la mantencion preventiva (FT-P101-001)
ZONES = ((2.3, "A"), (4.5, "B"), (7.1, "C"))  # ISO 10816-3, grupo 2, base flexible
LIMITS = {"vibration": 4.5, "temp_rise": 55.0}  # 4,5 mm/s: inicio de zona C (advertencia del sistema de control)
WEAR_VIBRATION, WEAR_EXPONENT, WEAR_TEMPERATURE = 1.1, 1.6, 3.0  # desgaste al final del periodo (variante incipient)
FIELDS = ("vibration", "temp_norm", "temp_rise", "current_norm", "pressure_deficit_pct", "flow")


def expected_pressure(flow: float) -> float:
    """Presion de descarga segun la curva de FT-P101-001: H = 54 - 0,00208 Q^2 (m), mas 0,3 bar de aspiracion."""
    return (54.0 - 0.00208 * flow * flow) * 0.0981 + 0.3


def vibration_zone(value: float) -> str:
    for limit, zone in ZONES:
        if value < limit:
            return zone
    return "D"


def saturday_near(ts: float) -> float:
    """Medianoche (hora de la planta) del sabado mas cercano a ts."""
    day = datetime.fromtimestamp(ts, LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = (5 - day.weekday() + 3) % 7 - 3
    return (day + timedelta(days=delta)).timestamp()


def _local(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, LOCAL_TZ)


def _at(year: int, month: int, day: int, hour: float = 0.0) -> float:
    base = datetime(year, month, day, tzinfo=LOCAL_TZ)
    return (base + timedelta(hours=hour)).timestamp()


# ---------------------------------------------------------------------------------------------- bronce
def generate_bronze(variant: str, end_ts: float, days: int = DAYS, seed: int = 101) -> list[tuple]:
    """Filas (ts, motor_temp, vibration, current, discharge_pressure, flow, rpm, ambient_temp); None = sin dato."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}")
    rng = random.Random(seed)  # misma semilla en ambas variantes: solo cambia el desgaste
    end_ts = end_ts - (end_ts % STEP_S)
    start_ts = end_ts - days * 86400
    # Paradas programadas pasadas del Area 100, el sabado mas cercano a 132 y 41 dias antes del final
    # (las futuras estan en el CMMS y se calculan con la misma regla).
    planned_stops = [(d + 7 * 3600, d + 19 * 3600) for d in (saturday_near(end_ts - 132 * 86400), saturday_near(end_ts - 41 * 86400))]
    # Incidentes registrados en el CMMS dentro del periodo:
    cooling_issue = (_at(2026, 5, 18, 6), _at(2026, 5, 22, 14))  # WO-2026-0281, temperatura alta sin vibracion
    strainer_issue = (_at(2026, 7, 4, 0), _at(2026, 7, 9, 13))  # WO-2026-0317, cae caudal y presion, corriente menor
    wear_start = end_ts - 56 * 86400  # desgaste incipiente: ultimas 8 semanas (solo variante incipient)
    gaps: list[tuple[float, float]] = []
    for _ in range(7):  # cortes de comunicacion de 1 a 6 horas
        g0 = start_ts + rng.random() * (end_ts - start_ts)
        gaps.append((g0, g0 + rng.uniform(1, 6) * 3600))
    rows: list[tuple] = []
    demand = 0.0
    mech = 0.0
    was_running = False
    since_start = 0.0
    t = start_ts
    while t <= end_ts:
        lt = _local(t)
        hour = lt.hour + lt.minute / 60
        doy = lt.timetuple().tm_yday
        running = not (lt.weekday() == 6 and 6 <= hour < 12)  # domingo de 6:00 a 12:00 sin bombeo
        running = running and not any(a <= t < b for a, b in planned_stops)
        demand = 0.97 * demand + 0.24 * rng.gauss(0, 1)  # carga lenta: proceso de Ornstein-Uhlenbeck
        mech = 0.6 * mech + 0.8 * rng.gauss(0, 1)
        if running and not was_running:
            since_start = 0.0
        since_start += STEP_S
        was_running = running
        # Ambiente: invierno en julio (hemisferio sur) y ciclo diario.
        ambient = 14.0 + 5.0 * math.cos(2 * math.pi * (doy - 15) / 365) + 4.5 * math.sin(2 * math.pi * (hour - 9) / 24) + rng.gauss(0, 0.6)
        if not running:
            rows.append((t, ambient + 4.0, 0.15 + abs(rng.gauss(0, 0.05)), 0.0, 0.3, 0.0, 0.0, ambient))
            t += STEP_S
            continue
        flow = 62.0 + 2.5 * math.sin(2 * math.pi * (hour - 8) / 24) + 1.6 * demand
        if lt.weekday() == 5:
            flow -= 4.0  # sabado con menos produccion
        pressure_factor, current_extra, temp_extra, vib_extra, jitter = 1.0, 0.0, 0.0, 0.0, 0.0
        if strainer_issue[0] <= t < strainer_issue[1]:
            s = (t - strainer_issue[0]) / (strainer_issue[1] - strainer_issue[0])
            flow -= 9.0 * s
            pressure_factor -= 0.10 * s
            current_extra -= 0.9 * s
            vib_extra += 0.25 * s
            jitter += 0.10 * s
        if cooling_issue[0] <= t < cooling_issue[1]:
            temp_extra += 9.0 * (t - cooling_issue[0]) / (cooling_issue[1] - cooling_issue[0])
        if variant == "incipient" and t >= wear_start:
            w = ((t - wear_start) / (end_ts - wear_start)) ** WEAR_EXPONENT  # se acelera hacia el final
            vib_extra += WEAR_VIBRATION * w
            jitter += 0.06 * w
            temp_extra += WEAR_TEMPERATURE * w
            current_extra += 0.15 * w
        pressure = expected_pressure(flow) * pressure_factor + rng.gauss(0, 0.03)
        current = 11.5 + 0.08 * (flow - 62.0) + current_extra + rng.gauss(0, 0.06)
        motor_temp = 57.0 + 0.6 * (ambient - 20.0) + 0.15 * (flow - 62.0) + temp_extra + rng.gauss(0, 0.35)
        vibration = 1.92 + 0.012 * abs(flow - 72.0) * 0.4 + vib_extra + (0.05 + jitter) * mech
        rpm = 1480.0 - 0.8 * (flow - 62.0) / 1.6 + rng.gauss(0, 0.4)
        if since_start <= 1800:  # transitorio de arranque: el motor aun no llega a su temperatura
            motor_temp -= 6.0 * (1 - since_start / 1800)
            vibration += 0.6 * (1 - since_start / 1800)
        if rng.random() < 0.003:
            vibration *= rng.uniform(2.5, 4.0)  # pico de sensor
        if any(a <= t < b for a, b in gaps):
            rows.append((t, None, None, None, None, None, None, None))
        else:
            rows.append((t, motor_temp, max(0.0, vibration), current, pressure, flow, rpm, ambient))
        t += STEP_S
    return rows


# ---------------------------------------------------------------------------------------------- plata
def build_silver(bronze: list[tuple]) -> tuple[list[tuple], dict[str, int]]:
    """Filas (ts, vibration, temp_norm, temp_rise, current_norm, pressure_deficit_pct, flow) y lo descartado."""
    dropped = {"gaps": 0, "stopped": 0, "startup": 0, "spikes": 0}
    silver: list[tuple] = []
    recent_vib: list[float] = []
    last_stop_ts = None
    for ts, motor_temp, vib, current, pressure, flow, _rpm, ambient in bronze:
        if motor_temp is None:
            dropped["gaps"] += 1
            continue
        if flow < 20.0:
            dropped["stopped"] += 1
            last_stop_ts = ts
            continue
        if last_stop_ts is not None and ts - last_stop_ts <= 1800:
            dropped["startup"] += 1
            continue
        median = statistics.median(recent_vib) if len(recent_vib) >= 6 else None
        if median is not None and vib > 1.8 * median:
            dropped["spikes"] += 1
            continue
        recent_vib.append(vib)
        if len(recent_vib) > 36:
            recent_vib.pop(0)
        temp_norm = motor_temp - 0.6 * (ambient - 20.0) - 0.15 * (flow - 62.0)  # llevado a 20 C y 62 m3/h
        expected = expected_pressure(flow)
        silver.append((ts, vib, temp_norm, motor_temp - ambient, current - 0.08 * (flow - 62.0),
                       100.0 * (expected - pressure) / expected, flow))
    return silver, dropped


# ---------------------------------------------------------------------------------------------- oro
def _pct(values: list[float], q: float) -> float:
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def build_gold(bronze: list[tuple], silver: list[tuple]) -> list[dict[str, object]]:
    by_day: dict[str, list[tuple]] = {}
    for row in silver:
        by_day.setdefault(_local(row[0]).date().isoformat(), []).append(row)
    run_hours: dict[str, float] = {}
    starts: dict[str, int] = {}
    previous = None
    for ts, _t, _v, _c, _p, flow, _r, _a in bronze:
        day = _local(ts).date().isoformat()
        running = flow is not None and flow >= 20.0
        if running:
            run_hours[day] = run_hours.get(day, 0.0) + STEP_S / 3600
        if running and previous is False:
            starts[day] = starts.get(day, 0) + 1
        if flow is not None:
            previous = running
    gold = []
    for day in sorted(by_day):
        rows = by_day[day]
        if len(rows) < 24:  # menos de 4 horas de datos validos: el dia no es representativo
            continue
        col = lambda i: [r[i] for r in rows]  # noqa: E731
        vib = col(1)
        gold.append({
            "day": day, "samples": len(rows), "run_hours": round(run_hours.get(day, 0.0), 1), "starts": starts.get(day, 0),
            "vibration_p50": round(_pct(vib, 0.5), 3), "vibration_p95": round(_pct(vib, 0.95), 3),
            "temp_norm_p50": round(_pct(col(2), 0.5), 2), "temp_rise_p50": round(_pct(col(3), 0.5), 2),
            "current_norm_p50": round(_pct(col(4), 0.5), 3), "pressure_deficit_pct_p50": round(_pct(col(5), 0.5), 2),
            "flow_mean": round(statistics.fmean(col(6)), 1),
        })
    return gold


# ---------------------------------------------------------------------------------------------- analisis
GOLD_FIELD = {"vibration": "vibration_p95", "temp_norm": "temp_norm_p50", "current_norm": "current_norm_p50",
              "pressure_deficit_pct": "pressure_deficit_pct_p50"}


def compare_periods(gold: list[dict[str, object]], baseline_days: int, recent_days: int) -> dict[str, object]:
    """Compara el inicio del periodo (referencia) con las ultimas semanas, con la carga normalizada."""
    if len(gold) < baseline_days + recent_days:
        return {"ok": False, "message": "No hay suficientes dias de historial para comparar."}
    base, recent = gold[:baseline_days], gold[-recent_days:]
    out = {}
    for name, key in GOLD_FIELD.items():
        b = statistics.median(d[key] for d in base)
        r = statistics.median(d[key] for d in recent)
        out[name] = {"baseline": round(b, 3), "recent": round(r, 3), "change": round(r - b, 3),
                     "change_pct": round(100 * (r - b) / b, 1) if abs(b) > 0.05 else None}
    vib_recent = out["vibration"]["recent"]
    deficit = out["pressure_deficit_pct"]["recent"]
    hydraulic = ("en su curva: la parte hidráulica está sana" if abs(deficit) < 2.0 else
                 "bajo su curva: pérdida de desempeño hidráulico" if deficit > 0 else "sobre su curva")
    over = round(100 * (vib_recent - REFERENCE_VIBRATION) / REFERENCE_VIBRATION, 1)
    since = first_sustained_over(gold, "vibration_p95", 1.25 * REFERENCE_VIBRATION)
    temp_change = out["temp_norm"]["change"]
    summary = (f"Vibración p95 reciente {vib_recent:.2f} mm/s, zona {vibration_zone(vib_recent)}, {over:+.0f} % respecto de la referencia de "
               f"{REFERENCE_VIBRATION} mm/s; " + (f"sobre el umbral de seguimiento ({1.25 * REFERENCE_VIBRATION:.2f} mm/s) desde el {since}; " if since
               else f"bajo el umbral de seguimiento ({1.25 * REFERENCE_VIBRATION:.2f} mm/s); ") +
               f"temperatura de motor a igual carga {temp_change:+.1f} °C; presión {hydraulic}.")
    return {"ok": True, "summary": summary, "baseline_period": [base[0]["day"], base[-1]["day"]], "recent_period": [recent[0]["day"], recent[-1]["day"]],
            "signals": out, "vibration_zone_recent": vibration_zone(vib_recent),
            "hydraulic_status_recent": f"Presión {hydraulic} (déficit de {deficit:+.1f} % frente a la curva de FT-P101-001; se considera relevante desde 2 %).",
            "vibration_over_reference_pct": round(100 * (vib_recent - REFERENCE_VIBRATION) / REFERENCE_VIBRATION, 1),
            "reference_vibration": REFERENCE_VIBRATION,
            "follow_up_threshold": {"value_mm_s": round(1.25 * REFERENCE_VIBRATION, 2),
                                    "meaning": "Umbral de seguimiento de FT-P101-001 (25 % sobre la referencia). No es una alarma."},
            "over_follow_up_threshold_since": first_sustained_over(gold, "vibration_p95", 1.25 * REFERENCE_VIBRATION),
            "note": "Valores diarios de la capa oro: vibración p95; temperatura, corriente y déficit de presión llevados a 62 m³/h y 20 °C."}


def _linear(ys: list[float]) -> tuple[float, float]:
    n = len(ys)
    mx, my = (n - 1) / 2, statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in range(n))
    slope = sum((x - mx) * (y - my) for x, y in zip(range(n), ys)) / sxx
    return slope, my + slope * (n - 1 - mx)  # pendiente por dia y valor ajustado del ultimo dia


def project(gold: list[dict[str, object]], signal: str, limit: float, window_days: int = 42) -> dict[str, object]:
    """Cuando cruzaria el limite si la tendencia sigue: rango entre tres ajustes sobre la capa oro.

    - recta sobre las ultimas 6 semanas (la mas lenta si el desgaste se acelera),
    - recta sobre las ultimas 2 semanas,
    - curva exponencial del exceso sobre la referencia de las primeras semanas (la mas rapida).
    """
    key = GOLD_FIELD[signal]
    data = gold[-window_days:]
    if len(data) < 21 or len(gold) < window_days + 30:
        return {"ok": False, "message": "Se necesitan al menos 10 semanas de historial para proyectar."}
    ys = [float(d[key]) for d in data]
    baseline = statistics.median(float(d[key]) for d in gold[:30])
    last_day = datetime.fromisoformat(str(data[-1]["day"])).date()
    slope6, fit6 = _linear(ys)
    slope2, fit2 = _linear(ys[-14:])
    current = fit2
    result: dict[str, object] = {
        "ok": True, "signal": signal, "metric": key, "limit": limit, "window": [data[0]["day"], data[-1]["day"]],
        "baseline_first_30_days": round(baseline, 3), "current_fitted": round(current, 3),
        "slope_per_week_6w": round(7 * slope6, 4), "slope_per_week_2w": round(7 * slope2, 4),
        "method": "Rango entre tres ajustes sobre los indicadores diarios: recta de 6 semanas, recta de 2 semanas y curva exponencial del aumento sobre la referencia.",
        "caveat": "Proyecta cuándo se llegaría al límite si la tendencia sigue igual; no predice el momento de una falla.",
    }
    if current >= limit:
        result.update(trend="ya_sobre_el_limite", message="El valor ya está sobre el límite.")
        return result
    # Tendencia relevante: debe subir al menos un 3 % de la distancia al limite por semana en las ultimas 2 semanas.
    if 7 * slope2 < 0.03 * (limit - baseline) or slope6 <= 0:
        result.update(trend="sin_tendencia_relevante", message="No hay una tendencia de aumento relevante: con este ritmo no se llegaría al límite en los próximos meses.")
        return result
    estimates = {"recta_6_semanas": (limit - current) / slope6, "recta_2_semanas": (limit - current) / slope2}
    # Exponencial solo sobre los dias con un aumento claro (mas de 0,1 sobre la referencia), al menos 14.
    excess = [y - baseline for y in ys]
    tail = [e for e in excess[-28:] if e > 0.1]
    if len(tail) >= 14 and tail == [e for e in excess[-len(tail):]]:
        k, log_fit = _linear([math.log(e) for e in tail])
        if k > 0 and limit - baseline > 0:
            estimates["exponencial"] = (math.log(limit - baseline) - log_fit) / k
    days = sorted(d for d in estimates.values() if d > 0)
    early, late = days[0], days[-1]
    central = statistics.median(days)
    if central > 365:
        result.update(trend="sin_tendencia_relevante", message="Con el ritmo actual no se llegaría al límite en el próximo año.")
        return result
    as_date = lambda d: (last_day + timedelta(days=round(d))).isoformat()  # noqa: E731
    result.update(trend="creciente",
                  estimates_days={k: round(v, 1) for k, v in estimates.items()},
                  days_to_limit={"early": round(early), "central": round(central), "late": round(late)},
                  weeks_to_limit={"early": round(early / 7, 1), "central": round(central / 7, 1), "late": round(late / 7, 1)},
                  date_to_limit={"early": as_date(early), "central": as_date(central), "late": as_date(late)})
    return result


def first_sustained_over(gold: list[dict[str, object]], key: str, threshold: float, days: int = 7) -> str | None:
    """Primer dia desde el cual la mediana movil de 7 dias supera el umbral y no vuelve a bajar."""
    found = None
    for i in range(days - 1, len(gold)):
        window = [float(g[key]) for g in gold[i - days + 1:i + 1]]
        if statistics.median(window) > threshold:
            found = found or str(gold[i - days + 1]["day"])
        else:
            found = None
    return found


# ---------------------------------------------------------------------------------------------- almacenamiento
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cond_meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS cond_bronze (variant TEXT, ts REAL, motor_temp REAL, vibration REAL, current REAL,
  discharge_pressure REAL, flow REAL, rpm REAL, ambient_temp REAL, PRIMARY KEY (variant, ts));
CREATE TABLE IF NOT EXISTS cond_silver (variant TEXT, ts REAL, vibration REAL, temp_norm REAL, temp_rise REAL,
  current_norm REAL, pressure_deficit_pct REAL, flow REAL, PRIMARY KEY (variant, ts));
CREATE TABLE IF NOT EXISTS cond_gold (variant TEXT, day TEXT, samples INTEGER, run_hours REAL, starts INTEGER,
  vibration_p50 REAL, vibration_p95 REAL, temp_norm_p50 REAL, temp_rise_p50 REAL, current_norm_p50 REAL,
  pressure_deficit_pct_p50 REAL, flow_mean REAL, PRIMARY KEY (variant, day));
"""
GOLD_COLUMNS = ("day", "samples", "run_hours", "starts", "vibration_p50", "vibration_p95", "temp_norm_p50", "temp_rise_p50",
                "current_norm_p50", "pressure_deficit_pct_p50", "flow_mean")


class ConditionStore:
    """Tablas del medallon en la misma base SQLite del historian. Se regeneran si el historial quedo viejo."""

    def __init__(self, path: str, max_age_s: float = 86400.0) -> None:
        # Conexion propia al mismo archivo del historian (modo WAL): la generacion no se mezcla con el registro en vivo.
        self._db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        if path != ":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self.max_age_s = max_age_s

    def _meta(self, key: str) -> str | None:
        row = self._db.execute("SELECT value FROM cond_meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._db.execute("INSERT OR REPLACE INTO cond_meta VALUES (?, ?)", (key, value))

    @property
    def variant(self) -> str:
        return self._meta("variant") or "healthy"

    def set_variant(self, variant: str) -> None:
        if variant not in VARIANTS:
            raise ValueError(variant)
        self._set_meta("variant", variant)

    def ensure(self, now: float | None = None) -> bool:
        """Genera las dos variantes si faltan o tienen mas de un dia. Devuelve True si regenero."""
        now = now or time.time()
        generated = float(self._meta("generated_at") or 0)
        if generated and now - generated < self.max_age_s:
            return False
        self._db.execute("BEGIN")
        try:
            for table in ("cond_bronze", "cond_silver", "cond_gold"):
                self._db.execute(f"DELETE FROM {table}")
            for variant in VARIANTS:
                bronze = generate_bronze(variant, now)
                silver, dropped = build_silver(bronze)
                gold = build_gold(bronze, silver)
                self._db.executemany("INSERT INTO cond_bronze VALUES (?,?,?,?,?,?,?,?,?)", [(variant, *r) for r in bronze])
                self._db.executemany("INSERT INTO cond_silver VALUES (?,?,?,?,?,?,?,?)", [(variant, *r) for r in silver])
                self._db.executemany(f"INSERT INTO cond_gold VALUES ({','.join('?' * 12)})",
                                     [(variant, *[g[c] for c in GOLD_COLUMNS]) for g in gold])
                self._set_meta(f"dropped_{variant}", ",".join(f"{k}={v}" for k, v in dropped.items()))
            self._set_meta("generated_at", str(now))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return True

    def gold(self, days: int | None = None) -> list[dict[str, object]]:
        rows = self._db.execute(f"SELECT {', '.join(GOLD_COLUMNS)} FROM cond_gold WHERE variant = ? ORDER BY day", (self.variant,)).fetchall()
        gold = [dict(zip(GOLD_COLUMNS, r)) for r in rows]
        return gold[-days:] if days else gold

    def layers(self) -> dict[str, object]:
        v = self.variant
        count = lambda t: self._db.execute(f"SELECT COUNT(*) FROM {t} WHERE variant = ?", (v,)).fetchone()[0]  # noqa: E731
        first, last = self._db.execute("SELECT MIN(ts), MAX(ts) FROM cond_bronze WHERE variant = ?", (v,)).fetchone()
        dropped = dict(item.split("=") for item in (self._meta(f"dropped_{v}") or "").split(",") if "=" in item)
        return {"bronze_rows": count("cond_bronze"), "silver_rows": count("cond_silver"), "gold_days": count("cond_gold"),
                "silver_dropped": {k: int(x) for k, x in dropped.items()},
                "period": [_local(first).date().isoformat(), _local(last).date().isoformat()] if first else None,
                "bronze_step_minutes": STEP_S // 60, "simulated": True}
