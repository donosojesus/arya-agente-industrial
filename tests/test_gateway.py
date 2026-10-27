"""OT Gateway: historian real (SQLite) alimentado por un cliente OPC UA real."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from arya_ot_gateway.analysis import correlation, detect_onset, downsample
from arya_ot_gateway.app import create_gateway_app
from arya_ot_gateway.config import GatewaySettings
from arya_ot_gateway.historian import Historian
from arya_otclient.poller import OpcUaPoller

from conftest import assert_no_leak, endpoint_for, free_port
from test_opcua_integration import wait_for

P = "/api/v1/assets/P-101"


@pytest.fixture
async def gateway_factory(tmp_path):
    created = []

    async def factory(endpoint: str, stale_after_s: float = 1.0):
        settings = GatewaySettings(opcua_endpoint=endpoint, historian_path=str(tmp_path / "historian.sqlite3"), sample_s=0.05, stale_after_s=stale_after_s)
        historian = Historian(settings.historian_path)
        poller = OpcUaPoller(endpoint, sample_s=0.05, stale_after_s=stale_after_s, timeout_s=1.5)
        app = create_gateway_app(poller, historian, settings, manage=False)
        poller.start()
        app.state.recorder.start()
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw")
        created.append((client, poller, app, historian))
        return client, poller, historian

    yield factory
    for client, poller, app, historian in created:
        await client.aclose()
        await app.state.recorder.stop()
        await poller.stop()
        historian.close()


async def test_live_endpoints_come_from_opcua(runtime_factory, gateway_factory):
    runtime = await runtime_factory()
    client, poller, _ = await gateway_factory(runtime.settings.opcua_endpoint)
    await wait_for(lambda: client._transport.app.state.recorder.last_write_monotonic is not None)
    assert (await client.get("/healthz")).status_code == 200
    tags = (await client.get(f"{P}/tags")).json()
    assert tags["data_quality"] == "GOOD" and tags["run_id"] == runtime.simulator.run_id and "warning" not in tags
    assert tags["tags"]["P101.MOTOR_TEMP"]["unit"] == "°C" and tags["tags"]["P101.MOTOR_TEMP"]["signal"] == "motor_temp"
    assert 50 < tags["tags"]["P101.MOTOR_TEMP"]["value"] < 65
    status = (await client.get("/api/v1/assets/p101/status")).json()  # el nombre del activo es flexible
    assert status["operating_status"] == "RUNNING" and status["alarm_level"] == "NORMAL" and status["active_alarm_count"] == 0
    alarms = (await client.get(f"{P}/alarms")).json()
    assert alarms["active_alarms"] == [] and alarms["configured_limits"]["P101.FLOW.LO"] == 52.0
    assert (await client.get("/api/v1/assets/P-999/tags")).status_code == 404


async def test_history_compare_and_alarm_events_after_a_fault(runtime_factory, gateway_factory):
    runtime = await runtime_factory(tick_s=0.1, steps_per_tick=20)  # 2 s simulados por tick
    client, poller, historian = await gateway_factory(runtime.settings.opcua_endpoint)
    await wait_for(lambda: historian.samples_written >= 40)  # linea base en operacion normal
    runtime.simulator.inject_fault()
    await wait_for(lambda: poller.state.sample.tags["P101.ALARM_LEVEL"]["value"] == "ALARM", timeout=30)
    await asyncio.sleep(2.5)

    history = (await client.get(f"{P}/history", params={"signals": "vibration,P101.MOTOR_TEMP", "minutes": 5, "max_points": 20})).json()
    assert history["source"] == "historian" and history["run_id"] == runtime.simulator.run_id
    vib, temp = history["signals"]["vibration"], history["signals"]["motor_temp"]
    assert vib["unit"] == "mm/s" and vib["trend"] == "rising" and vib["change_pct"] > 100
    assert vib["max"] > 7.1 and vib["start_value"] < 2.6 and len(vib["points"]) <= 20
    assert temp["trend"] == "rising" and temp["end_value"] > temp["start_value"] + 15
    assert vib["deviation"]["direction"] == "up" and temp["deviation"]["direction"] == "up"
    assert vib["deviation"]["seconds_ago"] > temp["deviation"]["seconds_ago"]  # la vibracion se desvio antes

    cmp = (await client.get(f"{P}/compare", params={"signal_a": "motor_temp", "signal_b": "vibration", "minutes": 5})).json()
    assert cmp["correlation"] > 0.8 and cmp["which_deviated_first"] == "vibration" and cmp["lead_seconds"] > 0
    flat = (await client.get(f"{P}/compare", params={"signal_a": "flow", "signal_b": "current", "minutes": 5})).json()
    assert flat["flow"]["trend"] == "falling" and flat["correlation"] < -0.5

    alarms = (await client.get(f"{P}/alarms")).json()
    codes = {a["code"] for a in alarms["active_alarms"]}
    assert "P101.VIBRATION.HIHI" in codes
    hihi = next(a for a in alarms["active_alarms"] if a["code"] == "P101.VIBRATION.HIHI")
    assert hihi["priority"] == "ALARM" and hihi["limit"] == 7.1 and hihi["current_value"] > 7.1 and hihi["active_since"]
    events = (await client.get(f"{P}/alarm-events", params={"minutes": 5})).json()["events"]
    order = [e["code"] for e in events if e["state"] == "ACTIVE"]
    assert order.index("P101.VIBRATION.HI") < order.index("P101.VIBRATION.HIHI")

    # Por defecto solo el ensayo actual: tras RESET la historia del ensayo anterior no se mezcla.
    old_run = runtime.simulator.run_id
    runtime.simulator.reset()
    await runtime.publish_now()
    await wait_for(lambda: poller.state.sample.run_id != old_run)
    await asyncio.sleep(0.5)
    fresh = (await client.get(f"{P}/history", params={"signals": "vibration", "minutes": 5})).json()
    assert fresh["signals"]["vibration"]["max"] < 3.0
    everything = (await client.get(f"{P}/history", params={"signals": "vibration", "minutes": 5, "scope": "all"})).json()
    assert everything["signals"]["vibration"]["max"] > 7.1
    assert_no_leak(str(history) + str(cmp) + str(alarms) + str(events))


async def test_validation_and_read_only(runtime_factory, gateway_factory):
    runtime = await runtime_factory()
    client, poller, historian = await gateway_factory(runtime.settings.opcua_endpoint)
    await wait_for(lambda: historian.samples_written >= 3)
    for params in ({"signals": "nope"}, {"signals": "flow", "minutes": 0}, {"signals": "flow", "minutes": 99999},
                   {"signals": "flow", "max_points": 1}, {"signals": "flow", "scope": "x"}, {"signals": "flow; DROP TABLE samples"}):
        response = await client.get(f"{P}/history", params=params)
        assert response.status_code == 422, params
    bad = (await client.get(f"{P}/history", params={"signals": "nope"})).json()
    assert "flow" in bad["detail"]["valid_signals"]
    assert (await client.get(f"{P}/compare", params={"signal_a": "flow", "signal_b": "flow"})).status_code == 422
    short = (await client.get(f"{P}/compare", params={"signal_a": "flow", "signal_b": "rpm", "minutes": 1})).json()
    assert "Not enough" in short["message"] and "correlation" not in short  # no se inventa una correlacion
    methods = set()
    for route in client._transport.app.routes:
        methods |= set(getattr(route, "methods", None) or {"GET"})
    assert methods <= {"GET", "HEAD"}
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await client.request(method, f"{P}/tags")).status_code == 405
    assert historian.samples_written >= 3  # la tabla sigue ahi


async def test_no_data_and_stale_data_are_reported_explicitly(runtime_factory, gateway_factory):
    # Sin planta: 503 con explicacion, no valores.
    client, poller, _ = await gateway_factory(endpoint_for(free_port()))
    await wait_for(lambda: poller.state.connection == "DISCONNECTED")
    response = await client.get(f"{P}/tags")
    assert response.status_code == 503 and response.json()["detail"]["error"] == "no_plant_data"
    assert (await client.get(f"{P}/history", params={"signals": "flow"})).status_code == 503
    assert (await client.get("/healthz")).status_code == 503

    # Con planta que luego se cae: ultimo valor real, marcado STALE y con advertencia.
    runtime = await runtime_factory()
    client2, poller2, historian2 = await gateway_factory(runtime.settings.opcua_endpoint, stale_after_s=1.0)
    await wait_for(lambda: historian2.samples_written >= 5)
    await runtime.stop()
    await wait_for(lambda: poller2.state.connection == "DISCONNECTED", timeout=15)
    await asyncio.sleep(1.2)
    written = historian2.samples_written
    tags = (await client2.get(f"{P}/tags")).json()
    assert tags["data_quality"] == "STALE" and "NOT current" in tags["warning"] and tags["last_error"]
    assert tags["tags"]["P101.RPM"]["value"] > 1400
    await asyncio.sleep(0.5)
    assert historian2.samples_written == written  # el historian no fabrica muestras sin conexion
    assert (await client2.get("/healthz")).status_code == 503


def test_analysis_helpers():
    times = [float(i) for i in range(200)]
    flat = [10.0 + (0.01 if i % 2 else -0.01) for i in range(200)]
    assert detect_onset(times, flat) is None  # sin desviacion no se reporta inicio
    ramp = flat[:100] + [10.0 + 0.1 * (i - 100) for i in range(100, 200)]
    onset = detect_onset(times, ramp)
    assert onset["direction"] == "up" and 90 <= 199 - onset["seconds_ago"] <= 106
    assert detect_onset(times[:20], ramp[:20]) is None  # pocos datos
    # Falla que ya lleva mucho rato: la linea base sigue siendo el comienzo, no el desvio.
    long_times = [float(i) for i in range(1000)]
    long_vals = [10.0 + (0.01 if i % 2 else -0.01) for i in range(60)] + [10.0 + 0.05 * (i - 60) for i in range(60, 1000)]
    late = detect_onset(long_times, long_vals)
    assert late is not None and 60 <= 999 - late["seconds_ago"] <= 75
    assert correlation(flat[:10], flat[:10]) is None and correlation([1.0] * 50, list(map(float, range(50)))) is None
    points = downsample(times, ramp, 10)
    assert len(points) == 10 and points[0]["v"] < points[-1]["v"]


def test_historian_persists_across_restarts_and_deduplicates(tmp_path):
    path = str(tmp_path / "h.sqlite3")
    tags = {"P101.MOTOR_TEMP": {"value": 57.0}, "P101.VIBRATION": {"value": 2.0}, "P101.CURRENT": {"value": 11.5},
            "P101.DISCHARGE_PRESSURE": {"value": 4.8}, "P101.FLOW": {"value": 62.0}, "P101.RPM": {"value": 1480.0},
            "P101.STATUS": {"value": "RUNNING"}, "P101.ALARM_LEVEL": {"value": "NORMAL"}, "P101.ACTIVE_ALARMS": {"value": []}}
    h = Historian(path)
    assert h.record(1000.0, "run-a", 2, tags) is True and h.record(1000.0, "run-a", 2, tags) is False
    alarmed = {**tags, "P101.ACTIVE_ALARMS": {"value": ["P101.FLOW.LO"]}}
    h.record(1001.0, "run-a", 4, alarmed)
    h.record(1002.0, "run-a", 6, tags)
    h.close()
    h2 = Historian(path)  # reinicio del servicio: los datos siguen
    assert h2.stats()["samples"] == 3
    assert h2.record(1000.0, "run-a", 2, tags) is False  # tampoco duplica tras reiniciar
    assert [(e[2], e[3]) for e in h2.alarm_events(0, "run-a")] == [("P101.FLOW.LO", "ACTIVE"), ("P101.FLOW.LO", "CLEARED")]
    assert h2.series(["flow"], 0, "run-b") == []
    h2.close()
