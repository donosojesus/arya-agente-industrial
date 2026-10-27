"""Segundo escenario de falla, alarmas por bajo caudal y falla programada (tiempo simulado)."""

from __future__ import annotations

import json
import statistics

import pytest

from arya_plant.simulator import PlantSimulator, ScenarioConflict

from conftest import assert_no_leak

DT = 0.5


def new_sim(**kwargs) -> PlantSimulator:
    counter = iter(range(1, 1000))
    return PlantSimulator(run_id_factory=lambda: f"run-test-{next(counter)}", **kwargs)


def run(sim, seconds):
    return [sim.step() for _ in range(int(seconds / DT))]


def mean(snaps, tag):
    return statistics.fmean(s.values[tag] for s in snaps)


def test_scenario_bravo_has_a_different_signature_from_alpha():
    results = {}
    for scenario in ("alpha", "bravo"):
        sim = new_sim()
        base = run(sim, 120)
        sim.inject_fault(scenario=scenario)
        run(sim, 180)
        end = run(sim, 180)[-60:]
        results[scenario] = {tag: (mean(base, tag), mean(end, tag)) for tag in base[0].values if tag.endswith(("TEMP", "VIBRATION", "CURRENT", "PRESSURE", "FLOW", "RPM"))}
        results[scenario]["alarms"] = set(sim.snapshot().values["P101.ACTIVE_ALARMS"])
        results[scenario]["level"] = sim.snapshot().values["P101.ALARM_LEVEL"]
        assert sim.snapshot().values["P101.STATUS"] == "RUNNING"
    a, b = results["alpha"], results["bravo"]
    # alpha: vibracion y temperatura altas; el caudal baja poco y no hay alarma de caudal.
    assert a["alarms"] == {"P101.VIBRATION.HI", "P101.VIBRATION.HIHI", "P101.MOTOR_TEMP.HI", "P101.MOTOR_TEMP.HIHI"}
    assert a["P101.CURRENT"][1] > a["P101.CURRENT"][0] * 1.05
    # bravo: cae el caudal y la presion, la corriente BAJA, la temperatura casi no cambia.
    assert b["alarms"] == {"P101.FLOW.LO", "P101.FLOW.LOLO"} and b["level"] == "ALARM"
    assert b["P101.FLOW"][1] < b["P101.FLOW"][0] * 0.70
    assert b["P101.DISCHARGE_PRESSURE"][1] < b["P101.DISCHARGE_PRESSURE"][0] * 0.88
    assert b["P101.CURRENT"][1] < b["P101.CURRENT"][0] * 0.92
    assert abs(b["P101.MOTOR_TEMP"][1] - b["P101.MOTOR_TEMP"][0]) < 6.0
    assert b["P101.VIBRATION"][1] < 4.3  # sube algo, sin llegar a alarma
    assert abs(b["P101.RPM"][1] / b["P101.RPM"][0] - 1) < 0.01


def test_bravo_transitions_without_chatter_and_recovers():
    sim = new_sim()
    run(sim, 30)
    sim.inject_fault(scenario="bravo")
    t0, levels, first = sim.model.time_s, [], {}
    for _ in range(int(400 / DT)):
        level = sim.step().values["P101.ALARM_LEVEL"]
        first.setdefault(level, sim.model.time_s - t0)
        if not levels or levels[-1] != level:
            levels.append(level)
    assert levels == ["NORMAL", "WARNING", "ALARM"], levels
    assert 55 <= first["WARNING"] <= 105 and 110 <= first["ALARM"] <= 165
    sim.normal_operation()
    run(sim, 300)
    assert sim.mode == "NORMAL" and sim.snapshot().values["P101.ACTIVE_ALARMS"] == []
    assert abs(sim.snapshot().values["P101.FLOW"] - 62.0) < 2.5


def test_second_fault_requires_a_healthy_plant():
    sim = new_sim()
    sim.inject_fault(scenario="alpha")
    run(sim, 200)
    with pytest.raises(ScenarioConflict):
        sim.inject_fault(scenario="bravo")
    sim.normal_operation()
    run(sim, 10)
    with pytest.raises(ScenarioConflict):  # aun en recuperacion
        sim.inject_fault(scenario="bravo")
    run(sim, 300)
    sim.inject_fault(scenario="bravo")  # ya en NORMAL: permitido, mismo ensayo
    assert sim.scenario_state()["scenario"] == "bravo"
    with pytest.raises(ValueError):
        new_sim().inject_fault(scenario="delta")


def test_scheduled_fault_starts_on_its_own_and_reset_cancels_it():
    sim = new_sim()
    sim.schedule_fault(120, scenario="bravo", duration_s=60)
    state = sim.scenario_state()
    assert state["mode"] == "NORMAL" and state["scheduled_fault"] == {"scenario": "bravo", "duration_s": 60.0, "starts_in_s": 120.0}
    run(sim, 119)
    assert sim.mode == "NORMAL"
    run(sim, 2)
    assert sim.mode == "DEGRADATION" and sim.scenario_state()["scheduled_fault"] is None
    assert sim.fault_started_at_s == pytest.approx(120.0, abs=0.6) and sim.fault_duration_s == 60.0
    # Programada durante una falla: espera a que la planta vuelva a NORMAL.
    sim2 = new_sim()
    sim2.inject_fault(scenario="alpha", duration_s=30)
    sim2.schedule_fault(20, scenario="bravo")
    run(sim2, 60)
    assert sim2.scenario_state()["scenario"] == "alpha" and sim2.scenario_state()["scheduled_fault"] is not None
    sim2.normal_operation()
    run(sim2, 200)
    assert sim2.mode == "DEGRADATION" and sim2.scenario_state()["scenario"] == "bravo"
    # RESET cancela; cancel_schedule tambien.
    sim3 = new_sim()
    sim3.schedule_fault(30)
    sim3.reset()
    run(sim3, 60)
    assert sim3.mode == "NORMAL"
    sim3.schedule_fault(30)
    assert sim3.cancel_schedule() is True and sim3.cancel_schedule() is False
    for bad in (0, -5, 5 * 3600):
        with pytest.raises(ValueError):
            sim3.schedule_fault(bad)


def test_scheduled_run_is_reproducible():
    def scripted():
        sim = new_sim()
        sim.schedule_fault(40, scenario="bravo")
        return [s.values for s in run(sim, 260)]
    assert scripted() == scripted()


def test_ground_truth_differs_per_scenario_and_stays_internal():
    truths = {}
    for scenario in ("alpha", "bravo"):
        sim = new_sim()
        assert sim.ground_truth_for_evaluation() is None  # sin falla no hay causa
        sim.inject_fault(scenario=scenario)
        run(sim, 200)
        truths[scenario] = sim.ground_truth_for_evaluation()["fault_id"]
        public = json.dumps(sim.snapshot().values) + json.dumps(sim.scenario_state())
        assert_no_leak(public)
        for word in ("strainer", "filtro", "cavita", "clog", "obstru"):
            assert word not in public.lower()
    assert truths["alpha"] != truths["bravo"]


def test_scenario_c_publishes_the_history_profile_until_reset():
    sim = new_sim()
    assert sim.snapshot().values["RUN.HISTORY_PROFILE"] == "H1"
    sim.inject_fault(scenario="charlie")
    assert sim.fault_duration_s == 30.0
    run(sim, 200)
    values = sim.snapshot().values
    assert values["RUN.HISTORY_PROFILE"] == "H2" and values["P101.ALARM_LEVEL"] == "NORMAL"  # sin alarmas: es predictivo
    assert 2.8 < values["P101.VIBRATION"] < 3.8
    sim.normal_operation()
    run(sim, 400)
    assert sim.snapshot().values["RUN.HISTORY_PROFILE"] == "H2"  # la historia no se borra al intervenir
    sim.reset()
    assert sim.snapshot().values["RUN.HISTORY_PROFILE"] == "H1"
