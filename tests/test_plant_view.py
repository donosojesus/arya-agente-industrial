"""Prueba 9 y limites de plant-view: cliente OPC UA real, perdida y recuperacion de conexion."""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from arya_plant_view.api import create_view_app
from arya_plant_view.config import ViewSettings
from arya_otclient.poller import OpcUaPoller

from conftest import TEST_TOKEN, assert_no_leak, endpoint_for, free_port
from test_opcua_integration import EXPECTED_PROCESS_NODES, wait_for

SRC = Path(__file__).resolve().parents[1] / "src"
VIEW_SRC = SRC / "arya_plant_view"


@pytest.fixture
async def view_factory():
    pollers: list[OpcUaPoller] = []
    clients: list[httpx.AsyncClient] = []

    async def factory(endpoint: str, stale_after_s: float = 1.0):
        poller = OpcUaPoller(endpoint, sample_s=0.1, stale_after_s=stale_after_s, timeout_s=1.5)
        poller.start()
        pollers.append(poller)
        app = create_view_app(poller, ViewSettings(opcua_endpoint=endpoint), manage_poller=False)
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://view")
        clients.append(client)
        return client, poller

    yield factory
    for client in clients:
        await client.aclose()
    for poller in pollers:
        await poller.stop()


async def test_telemetry_comes_from_opcua_with_quality_and_timestamps(runtime_factory, view_factory):
    runtime = await runtime_factory()
    client, poller = await view_factory(runtime.settings.opcua_endpoint)
    await wait_for(poller.is_fresh)
    assert (await client.get("/healthz")).status_code == 200
    data = (await client.get("/api/telemetry/latest")).json()
    assert data["connection"]["state"] == "CONNECTED" and data["connection"]["last_error"] is None
    snap = data["snapshot"]
    assert snap["quality"] == "GOOD" and snap["run_id"] == runtime.simulator.run_id
    assert snap["seq"] % 2 == 0 and snap["age_s"] < 1.0
    assert snap["source_timestamp"].endswith("Z") and snap["received_at"].endswith("Z")
    assert set(snap["tags"]) == set(EXPECTED_PROCESS_NODES)
    for name, unit in EXPECTED_PROCESS_NODES.items():
        tag = snap["tags"][name]
        assert tag["status"] == "Good" and tag["unit"] == unit and tag["value"] is not None
    assert snap["tags"]["P101.ACTIVE_ALARMS"]["value"] == []
    config = (await client.get("/api/config")).json()
    assert config["location"] == "Notebook · Planta / OT simulada" and config["asset"] == "P-101"
    assert config["limits"]["P101.MOTOR_TEMP.HI"] == 75.0
    assert_no_leak((await client.get("/api/telemetry/latest")).text + (await client.get("/api/config")).text)


async def test_no_data_is_reported_as_no_data_not_zeros(view_factory):
    """Sin planta: no hay snapshot (null), se informa el error y el servicio no esta sano."""
    client, poller = await view_factory(endpoint_for(free_port()))
    await wait_for(lambda: poller.state.connection == "DISCONNECTED" and poller.state.last_error)
    data = (await client.get("/api/telemetry/latest")).json()
    assert data["snapshot"] is None
    assert data["connection"]["state"] == "DISCONNECTED" and data["connection"]["last_error"]
    assert (await client.get("/healthz")).status_code == 503


async def test_connection_loss_marks_stale_and_recovers(runtime_factory, view_factory):
    port = free_port()
    runtime = await runtime_factory(port=port)
    client, poller = await view_factory(runtime.settings.opcua_endpoint, stale_after_s=1.0)
    await wait_for(poller.is_fresh)
    first_run = runtime.simulator.run_id

    # --- se cae la planta (servidor OPC UA detenido) ---
    await runtime.stop()
    await wait_for(lambda: poller.state.connection == "DISCONNECTED", timeout=15)
    frozen = (await client.get("/api/telemetry/latest")).json()
    await asyncio.sleep(1.3)
    data = (await client.get("/api/telemetry/latest")).json()
    assert data["connection"]["state"] == "DISCONNECTED"
    assert data["connection"]["last_error"]  # se muestra el error
    snap = data["snapshot"]
    assert snap["quality"] == "STALE" and snap["age_s"] > 1.0
    # Conserva la ultima muestra real, sin sustituirla por ceros ni valores nuevos.
    assert snap["seq"] == frozen["snapshot"]["seq"] and snap["tags"] == frozen["snapshot"]["tags"]
    assert snap["tags"]["P101.MOTOR_TEMP"]["value"] > 50 and snap["run_id"] == first_run
    assert (await client.get("/healthz")).status_code == 503

    # --- vuelve la planta en el mismo endpoint (reinicio del contenedor) ---
    runtime2 = await runtime_factory(port=port)
    await wait_for(poller.is_fresh, timeout=20)
    data = (await client.get("/api/telemetry/latest")).json()
    assert data["connection"]["state"] == "CONNECTED" and data["connection"]["last_error"] is None
    assert data["connection"]["reconnects"] >= 1
    assert data["snapshot"]["quality"] == "GOOD"
    assert data["snapshot"]["run_id"] == runtime2.simulator.run_id != first_run
    assert (await client.get("/healthz")).status_code == 200


async def test_plant_view_has_no_route_that_modifies_the_process(runtime_factory, view_factory):
    runtime = await runtime_factory()
    client, poller = await view_factory(runtime.settings.opcua_endpoint)
    await wait_for(poller.is_fresh)
    methods = set()
    for route in client._transport.app.routes:
        methods |= set(getattr(route, "methods", None) or {"GET"})
    assert methods <= {"GET", "HEAD"}, methods
    run_id, mode = runtime.simulator.run_id, runtime.simulator.mode
    for path in ("/api/demo/inject-fault", "/api/demo/reset", "/api/demo/normal", "/api/telemetry/latest", "/"):
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            response = await client.request(method, path, headers={"Authorization": f"Bearer {TEST_TOKEN}"})
            assert response.status_code in (404, 405), (method, path, response.status_code)
    assert (runtime.simulator.run_id, runtime.simulator.mode) == (run_id, mode)


def test_plant_view_never_imports_the_simulator_nor_holds_the_token():
    sources = [p for name in ("arya_plant_view", "arya_otclient", "arya_ot_gateway", "arya_cmms") for p in (SRC / name).rglob("*.py")]
    assert len(sources) > 10
    for path in sources:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(from|import)\s+arya_plant(\.|\s|$)", source, re.M), path
        assert "DEMO_CONTROL_TOKEN" not in source, path
    # Comprobacion en ejecucion: importar el servicio no carga el paquete de la planta.
    code = (
        "import sys; import arya_plant_view.api, arya_otclient.poller, arya_plant_view.__main__, arya_ot_gateway.app; "
        "print([m for m in sys.modules if m == 'arya_plant' or m.startswith('arya_plant.')])"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=SRC, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_static_frontend_is_local_only_and_reveals_nothing():
    files = sorted((VIEW_SRC / "static").iterdir())
    assert {f.name for f in files} == {"index.html", "app.js", "style.css"}
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert_no_leak(text)
        # Sin CDN, fuentes remotas ni servicios externos.
        for url in re.findall(r"https?://[^\s\"')]+", text):
            assert url in ("http://www.w3.org/2000/svg", "http://"), url  # el espacio de nombres SVG es un identificador: no se descarga
        assert "@import" not in text and "url(" not in text
    html = (VIEW_SRC / "static" / "index.html").read_text(encoding="utf-8")
    for required in ("THE PLANT", "P-101", "Notebook · Planta / OT simulada", "NORMAL OPERATION",
                     "INJECT FAULT", "RESET DEMO", "Tendencias", "Alarmas activas"):
        assert required in html, required


async def test_static_files_are_served(runtime_factory, view_factory):
    runtime = await runtime_factory()
    client, _ = await view_factory(runtime.settings.opcua_endpoint)
    index = await client.get("/")
    assert index.status_code == 200 and "THE PLANT" in index.text
    compact = await client.get("/compact")  # misma pantalla en disposicion compacta
    assert compact.status_code == 200 and compact.text == index.text
    for path in ("/static/app.js", "/static/style.css"):
        response = await client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-cache"  # el navegador siempre revalida
