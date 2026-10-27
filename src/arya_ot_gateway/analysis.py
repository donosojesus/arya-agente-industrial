"""Calculos deterministas sobre series del historian (sin inventar datos)."""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timezone


def iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def downsample(times: list[float], values: list[float], max_points: int) -> list[dict[str, object]]:
    """Promedia por tramos iguales de tiempo para devolver como maximo `max_points` puntos."""
    if not times:
        return []
    if len(times) <= max_points:
        return [{"t": iso(t), "v": round(v, 3)} for t, v in zip(times, values)]
    start, span = times[0], max(times[-1] - times[0], 1e-9)
    buckets: dict[int, list[tuple[float, float]]] = {}
    for t, v in zip(times, values):
        buckets.setdefault(min(max_points - 1, int((t - start) / span * max_points)), []).append((t, v))
    return [
        {"t": iso(statistics.fmean(t for t, _ in items)), "v": round(statistics.fmean(v for _, v in items), 3)}
        for _, items in sorted(buckets.items())
    ]


def detect_onset(times: list[float], values: list[float]) -> dict[str, object] | None:
    """Momento en que la senal se aparta de su linea base y ya no vuelve.

    Linea base: el comienzo de la ventana (entre 20 y 60 muestras, un 10 %), para que no
    incluya el propio desvio cuando la falla ya lleva varios minutos. Desviacion:
    mas de max(4 sigma, 3 % de la base) sostenida hasta el final de la ventana.
    Devuelve None si no hay datos suficientes o no hay una desviacion sostenida.
    """
    n = len(values)
    if n < 60:
        return None
    base_n = max(20, min(60, n // 10))
    base = values[:base_n]
    mean = statistics.fmean(base)
    threshold = max(4.0 * statistics.pstdev(base), 0.03 * abs(mean), 1e-6)
    onset = None
    for i in range(n - 1, base_n - 1, -1):
        if abs(values[i] - mean) > threshold:
            onset = i
        else:
            break
    if onset is None or n - onset < 10:
        return None
    return {
        "started_at": iso(times[onset]),
        "seconds_ago": round(times[-1] - times[onset], 1),
        "direction": "up" if values[-1] > mean else "down",
        "baseline": round(mean, 3),
    }


def summarize(times: list[float], values: list[float]) -> dict[str, object]:
    first = statistics.fmean(values[: max(1, min(10, len(values)))])
    last = statistics.fmean(values[-max(1, min(10, len(values))):])
    change_pct = None if abs(first) < 1e-9 else round((last - first) / abs(first) * 100.0, 1)
    return {
        "samples": len(values),
        "from": iso(times[0]),
        "to": iso(times[-1]),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "mean": round(statistics.fmean(values), 3),
        "start_value": round(first, 3),
        "end_value": round(last, 3),
        "change_pct": change_pct,
        "trend": "stable" if change_pct is None or abs(change_pct) < 2.0 else ("rising" if change_pct > 0 else "falling"),
        "deviation": detect_onset(times, values),
    }


def correlation(a: list[float], b: list[float]) -> float | None:
    if len(a) < 30 or len(a) != len(b):
        return None
    try:
        value = statistics.correlation(a, b)
    except statistics.StatisticsError:
        return None  # alguna de las dos senales es constante
    return None if math.isnan(value) else round(value, 3)
