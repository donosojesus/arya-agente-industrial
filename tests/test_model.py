"""Pruebas 1-5: modelo, escenario, reproducibilidad y reset (tiempo simulado)."""

from __future__ import annotations

import json
import statistics

import pytest

from arya_plant.alarms import AlarmConfig, AlarmEvaluator
from arya_plant.model import PumpModel, PumpParams, PumpSignals
from arya_plant.simulator import MODE_DEGRADATION, MODE_NORMAL, MODE_RECOVERY, PlantSimulator, ScenarioConflict

from conftest import assert_no_leak

DT = 0.5
ANALOG = ["P101.MOTOR_TEMP", "P101.VIBRATION", "P101.CURRENT", "P101.DISCHARGE_PRESSURE", "P101.FLOW", "P101.RPM"]


def new_sim(**kwargs) -> PlantSimulator:
    counter = iter(range(1, 1000))
    return PlantSimulator(run_id_factory=lambda: f"run-test-{next(counter)}", **kwargs)


def run(sim: PlantSimulator, seconds: float) -> list:
    return [sim.step() for _ in range(int(seconds / DT))]


def corr(xs, ys) -> float:
    return statistics.correlation(xs, ys)


# ----------------------------------------------------------------- 1. estado normal
def test_normal_state_is_stable_and_in_range():
    sim = new_sim()
    snaps = run(sim, 30 * 60)  # 30 minutos simulados
    bands = {
        "P101.MOTOR_TEMP": (53.0, 61.0),
        "P101.VIBRATION": (1.6, 2.4),
        "P101.CURRENT": (11.0, 12.0),
        "P101.DISCHARGE_PRESSURE": (4.6, 5.0),
        "P101.FLOW": (59.5, 64.5),
        "P101.RPM": (1476.0, 1484.0),
    }
    nominal = {"P101.MOTOR_TEMP": 57.0, "P101.VIBRATION": 2.0, "P101.CURRENT": 11.5,
               "P101.DISCHARGE_PRESSURE": 4.8, "P101.FLOW": 62.0, "P101.RPM": 1480.0}
    for tag, (low, high) in bands.items():
        series = [s.values[tag] for s in snaps]
        assert low <= min(series) and max(series) <= high, f"{tag} out of band: {min(series)}..{max(series)}"
        assert abs(statistics.fmean(series) - nominal[tag]) < 0.02 * nominal[tag] + 0.1
    assert {s.values["P101.ALARM_LEVEL"] for s in snaps} == {"NORMAL"}
    assert all(s.values["P101.ACTIVE_ALARMS"] == [] for s in snaps)
    assert {s.values["P101.STATUS"] for s in snaps} == {"RUNNING"}
    assert sim.mode == MODE_NORMAL


def test_normal_signals_are_smooth_and_correlated_not_independent_noise():
    sim = new_sim()
    snaps = run(sim, 30 * 60)
    series = {tag: [s.values[tag] for s in snaps] for tag in ANALOG}
    # Variaciones suaves: el cambio entre muestras es pequeno frente a la banda.
    max_step = {"P101.MOTOR_TEMP": 0.2, "P101.VIBRATION": 0.12, "P101.CURRENT": 0.12,
                "P101.DISCHARGE_PRESSURE": 0.04, "P101.FLOW": 0.6, "P101.RPM": 0.8}
    for tag, limit in max_step.items():
        steps = [abs(b - a) for a, b in zip(series[tag], series[tag][1:])]
        assert max(steps) <= limit, f"{tag} jumps {max(steps)} between samples"
    # Correlacion fisica: a velocidad fija, mas caudal => mas corriente y menos presion.
    assert corr(series["P101.FLOW"], series["P101.CURRENT"]) > 0.9
    assert corr(series["P101.FLOW"], series["P101.DISCHARGE_PRESSURE"]) < -0.9
    assert corr(series["P101.FLOW"], series["P101.RPM"]) < -0.8


# ----------------------------------------------------------------- 2. evolucion de la falla
def test_fault_evolution_is_gradual_and_correlated():
    sim = new_sim()
    base = run(sim, 120)
    sim.inject_fault()
    fault = run(sim, 180)
    hold = run(sim, 180)  # severidad completa: la temperatura termina de subir

    def mean(snaps, tag):
        return statistics.fmean(s.values[tag] for s in snaps)

    b = {tag: mean(base, tag) for tag in ANALOG}
    end = {tag: mean(hold[-60:], tag) for tag in ANALOG}
    assert end["P101.VIBRATION"] > 7.1 and end["P101.MOTOR_TEMP"] > 88.0
    assert 1.05 < end["P101.CURRENT"] / b["P101.CURRENT"] < 1.20  # sube ligeramente
    assert 0.88 < end["P101.FLOW"] / b["P101.FLOW"] < 0.97  # baja moderadamente
    assert 0.88 < end["P101.DISCHARGE_PRESSURE"] / b["P101.DISCHARGE_PRESSURE"] < 0.97
    assert abs(end["P101.RPM"] / b["P101.RPM"] - 1.0) < 0.01  # rpm aproximadamente constante

    # Gradual: sin saltos, y creciente por tramos de 30 s.
    vib = [s.values["P101.VIBRATION"] for s in fault]
    temp = [s.values["P101.MOTOR_TEMP"] for s in fault + hold]
    assert max(abs(b2 - a) for a, b2 in zip(vib, vib[1:])) < 0.35
    assert max(abs(b2 - a) for a, b2 in zip(temp, temp[1:])) < 0.4
    blocks = [statistics.fmean(vib[i:i + 60]) for i in range(0, len(vib), 60)]
    assert all(later > earlier for earlier, later in zip(blocks, blocks[1:]))

    # Retraso termico: la temperatura alcanza el 50 % de su subida despues que la vibracion.
    def half_rise_time(series, start, final):
        target = start + 0.5 * (final - start)
        return next(i for i, v in enumerate(series) if v >= target) * DT

    all_vib = [s.values["P101.VIBRATION"] for s in fault + hold]
    t_vib = half_rise_time(all_vib, b["P101.VIBRATION"], end["P101.VIBRATION"])
    t_temp = half_rise_time(temp, b["P101.MOTOR_TEMP"], end["P101.MOTOR_TEMP"])
    assert t_temp - t_vib > 10.0, f"thermal lag too small: vib {t_vib}s temp {t_temp}s"
    # La bomba sigue RUNNING: no se simula un disparo de proteccion.
    assert {s.values["P101.STATUS"] for s in fault + hold} == {"RUNNING"}


# ----------------------------------------------------------------- 3. transiciones
def test_transitions_normal_degradation_warning_alarm():
    sim = new_sim()
    timeline = [(sim.mode, s.values["P101.ALARM_LEVEL"]) for s in run(sim, 60)]
    sim.inject_fault()
    t0 = sim.model.time_s
    first_seen: dict[str, float] = {}
    for _ in range(int(360 / DT)):
        snap = sim.step()
        timeline.append((sim.mode, snap.values["P101.ALARM_LEVEL"]))
        first_seen.setdefault(snap.values["P101.ALARM_LEVEL"], sim.model.time_s - t0)

    collapsed = [timeline[0]]
    for item in timeline[1:]:
        if item != collapsed[-1]:
            collapsed.append(item)
    assert collapsed == [
        (MODE_NORMAL, "NORMAL"),
        (MODE_DEGRADATION, "NORMAL"),
        (MODE_DEGRADATION, "WARNING"),
        (MODE_DEGRADATION, "ALARM"),
    ], collapsed  # sin oscilaciones: cada estado aparece una sola vez
    # Evolucion de alrededor de tres minutos con la duracion por defecto (180 s).
    assert 45 <= first_seen["WARNING"] <= 110
    assert 120 <= first_seen["ALARM"] <= 185
    assert sim.fault_duration_s == 180.0


def test_fault_duration_is_configurable_and_validated():
    fast = new_sim(fault_duration_s=60)
    fast.inject_fault()
    levels = [s.values["P101.ALARM_LEVEL"] for s in run(fast, 70)]
    assert "ALARM" in levels
    sim = new_sim()
    for bad in (0, 5, 29.9, 901, -1):
        with pytest.raises(ValueError):
            sim.inject_fault(bad)
    assert sim.mode == MODE_NORMAL
    sim.inject_fault(45)
    with pytest.raises(ScenarioConflict):
        sim.inject_fault()


def test_alarms_use_persistence_and_hysteresis():
    cfg = AlarmConfig()
    ev = AlarmEvaluator(cfg)

    def sig(vibration=2.0, temp=57.0):
        return PumpSignals(temp, vibration, 11.5, 4.8, 62.0, 1480.0)

    # Senal que cruza el limite en muestras alternas: nunca persiste, no hay alarma.
    for i in range(201):  # termina en una muestra bajo el limite
        level, active = ev.update(sig(vibration=4.6 if i % 2 else 4.4), DT)
        assert level == "NORMAL" and active == []
    # Sostenida: se activa solo tras el retardo de activacion.
    seen = [ev.update(sig(vibration=4.6), DT)[0] for _ in range(6)]
    assert seen[:3] == ["NORMAL"] * 3 and seen[-1] == "WARNING"
    # Dentro de la banda muerta (limite - deadband <= valor < limite) no se libera.
    for _ in range(100):
        assert ev.update(sig(vibration=4.3), DT)[0] == "WARNING"
    # Por debajo de la banda muerta se libera tras el retardo de liberacion.
    seen = [ev.update(sig(vibration=4.0), DT)[0] for _ in range(8)]
    assert seen[0] == "WARNING" and seen[-1] == "NORMAL"
    # Temperatura: niveles independientes y el nivel global es el mayor.
    for _ in range(10):
        level, active = ev.update(sig(temp=89.0), DT)
    assert level == "ALARM" and active == ["P101.MOTOR_TEMP.HI", "P101.MOTOR_TEMP.HIHI"]


def test_normal_operation_during_fault_recovers_gradually_not_instantly():
    sim = new_sim()
    sim.inject_fault()
    run(sim, 300)
    hot = sim.snapshot().values
    assert hot["P101.ALARM_LEVEL"] == "ALARM" and hot["P101.MOTOR_TEMP"] > 88
    run_id = sim.run_id
    assert sim.normal_operation() is True
    after_one = sim.step().values
    # No normaliza instantaneamente: temperatura y alarma siguen altas.
    assert after_one["P101.MOTOR_TEMP"] > hot["P101.MOTOR_TEMP"] - 1.0
    assert after_one["P101.ALARM_LEVEL"] == "ALARM"
    assert sim.mode == MODE_RECOVERY and sim.run_id == run_id
    run(sim, 300)
    cool = sim.snapshot().values
    assert sim.mode == MODE_NORMAL and sim.run_id == run_id
    assert cool["P101.ALARM_LEVEL"] == "NORMAL" and cool["P101.ACTIVE_ALARMS"] == []
    assert abs(cool["P101.MOTOR_TEMP"] - 57.0) < 3.0 and abs(cool["P101.VIBRATION"] - 2.0) < 0.4
    assert sim.normal_operation() is False  # sin falla activa no hace nada


# ----------------------------------------------------------------- 4. reproducibilidad
def scripted_run(sim: PlantSimulator) -> list[dict]:
    out = [s.values for s in run(sim, 30)]
    sim.inject_fault()
    out += [s.values for s in run(sim, 240)]
    return out


def test_same_parameters_give_identical_evolution():
    assert scripted_run(new_sim()) == scripted_run(new_sim())


def test_different_seed_gives_different_noise_but_same_scenario():
    a = scripted_run(new_sim())
    b = scripted_run(new_sim(params=PumpParams(seed=7)))
    assert a != b
    assert a[-1]["P101.ALARM_LEVEL"] == b[-1]["P101.ALARM_LEVEL"] == "ALARM"


def test_model_is_independent_of_wall_clock():
    """El modelo solo avanza por pasos; no hay lecturas de reloj en model/alarms/simulator."""
    import inspect

    import arya_plant.alarms as alarms
    import arya_plant.model as model

    for module in (model, alarms):
        source = inspect.getsource(module)
        assert "import time" not in source and "datetime" not in source
    m = PumpModel()
    for _ in range(10):
        m.step()
    assert m.time_s == 10 * m.params.dt


# ----------------------------------------------------------------- 5. reset deterministico
def test_reset_restores_initial_state_and_repeats_the_same_sequence():
    sim = new_sim()
    initial = sim.snapshot()
    first = scripted_run(sim)
    first_run_id = sim.run_id
    assert sim.snapshot().values["P101.ALARM_LEVEL"] == "ALARM"

    sim.reset()
    after = sim.snapshot()
    assert sim.run_id != first_run_id  # nuevo run_id
    assert after.values == initial.values and after.sim_time_s == 0.0
    assert sim.mode == MODE_NORMAL and sim.fault_duration_s is None
    assert after.values["P101.ALARM_LEVEL"] == "NORMAL"

    second = scripted_run(sim)
    assert second == first  # misma evolucion respecto al tiempo simulado
    assert scripted_run(new_sim()) == first  # e igual a una instancia nueva


# ----------------------------------------------------------------- causa real oculta
def test_public_views_do_not_reveal_the_fault_cause():
    sim = new_sim()
    sim.inject_fault()
    run(sim, 200)
    assert_no_leak(json.dumps(sim.snapshot().values))
    assert_no_leak(json.dumps(sim.scenario_state()))
    assert "fault_id" in sim.ground_truth_for_evaluation()  # existe, pero solo internamente
