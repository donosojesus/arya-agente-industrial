"""Prueba 8: validacion y autenticacion de los controles de demostracion."""

from __future__ import annotations

import httpx
import pytest
from asyncua import Client, ua

from arya_plant.config import ConfigError, PlantSettings, validate_token
from arya_plant.control_api import create_control_app
from arya_plant.tags import NAMESPACE_URI

from conftest import TEST_TOKEN, assert_no_leak

AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
ORIGIN = "http://127.0.0.1:8080"


@pytest.fixture
async def control(runtime_factory):
    runtime = await runtime_factory()
    app = create_control_app(runtime, runtime.settings, manage_runtime=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://control") as client:
        yield client, runtime


async def test_health_is_public_and_reports_real_state(control):
    client, runtime = control
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True and response.json()["opcua_server_started"] is True
    await runtime.stop()
    response = await client.get("/healthz")
    assert response.status_code == 503 and response.json()["ok"] is False


@pytest.mark.parametrize("path,method", [
    ("/api/demo/state", "GET"), ("/api/demo/inject-fault", "POST"),
    ("/api/demo/normal", "POST"), ("/api/demo/reset", "POST"),
])
async def test_every_control_route_requires_the_token(control, path, method):
    client, runtime = control
    run_id = runtime.simulator.run_id
    bad_headers = [
        {},
        {"Authorization": "Bearer wrong-token-0123456789abcdefghijkl"},
        {"Authorization": f"Basic {TEST_TOKEN}"},
        {"Authorization": TEST_TOKEN},
        {"Authorization": f"Bearer {TEST_TOKEN}x"},
        {"Authorization": "Bearer "},
        {"X-Token": TEST_TOKEN},
    ]
    for headers in bad_headers:
        response = await client.request(method, path, headers=headers)
        assert response.status_code == 401, headers
        assert TEST_TOKEN not in response.text
    # Ningun intento no autenticado altero el escenario.
    assert runtime.simulator.mode == "NORMAL" and runtime.simulator.run_id == run_id
    # El token tampoco se acepta como parametro de consulta.
    response = await client.request(method, f"{path}?token={TEST_TOKEN}")
    assert response.status_code == 401


async def test_inject_fault_validation(control):
    client, runtime = control
    for body in ({"duration_seconds": 5}, {"duration_seconds": 5000}, {"duration_seconds": "fast"},
                 {"duration_seconds": 60, "cause": "x"}, {"unexpected": True}, [1, 2]):
        response = await client.post("/api/demo/inject-fault", headers=AUTH, json=body)
        assert response.status_code == 422, body
    assert runtime.simulator.mode == "NORMAL"
    response = await client.post("/api/demo/inject-fault", headers=AUTH, content=b"{not json", )
    assert response.status_code == 422
    assert runtime.simulator.mode == "NORMAL"


async def test_inject_normal_reset_flow(control):
    client, runtime = control
    state = (await client.get("/api/demo/state", headers=AUTH)).json()
    assert state["mode"] == "NORMAL" and state["fault_progress"] == 0
    run_id = state["run_id"]

    # NORMAL OPERATION sin falla: no cambia nada y lo dice.
    response = await client.post("/api/demo/normal", headers=AUTH)
    assert response.status_code == 200 and "No active fault" in response.json()["message"]

    response = await client.post("/api/demo/inject-fault", headers=AUTH, json={"duration_seconds": 45})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "DEGRADATION" and body["fault_duration_s"] == 45 and body["run_id"] == run_id
    assert_no_leak(response.text)

    # Segunda inyeccion en el mismo ensayo: conflicto explicito.
    response = await client.post("/api/demo/inject-fault", headers=AUTH)
    assert response.status_code == 409

    # NORMAL OPERATION durante la falla: recuperacion gradual declarada, mismo ensayo.
    response = await client.post("/api/demo/normal", headers=AUTH, json={})
    assert response.status_code == 200
    assert response.json()["mode"] == "RECOVERY" and "gradually" in response.json()["message"]
    assert response.json()["run_id"] == run_id

    # RESET: nuevo run_id, estado inicial, visible de inmediato por OPC UA.
    response = await client.post("/api/demo/reset", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "NORMAL" and body["run_id"] != run_id and body["fault_progress"] == 0
    async with Client(runtime.settings.opcua_endpoint, timeout=4) as opc:
        idx = await opc.get_namespace_index(NAMESPACE_URI)
        assert await opc.get_node(ua.NodeId("RUN.ID", idx)).read_value() == body["run_id"]
    response = await client.post("/api/demo/reset", headers=AUTH, json={"extra": 1})
    assert response.status_code == 422


async def test_default_fault_duration_comes_from_settings(control):
    client, runtime = control
    response = await client.post("/api/demo/inject-fault", headers=AUTH)
    assert response.json()["fault_duration_s"] == runtime.settings.fault_duration_s == 180.0


async def test_cors_allows_only_local_scada_origins(control):
    client, _ = control
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization,content-type"}
    ok = await client.options("/api/demo/reset", headers={"Origin": ORIGIN, **preflight})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == ORIGIN
    assert "authorization" in ok.headers["access-control-allow-headers"].lower()
    ok = await client.options("/api/demo/reset", headers={"Origin": "http://localhost:8080", **preflight})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:8080"
    for origin in ("http://evil.example", "http://gb10.local:8080", "http://127.0.0.1:9999"):
        bad = await client.options("/api/demo/reset", headers={"Origin": origin, **preflight})
        assert bad.status_code == 400 and "access-control-allow-origin" not in bad.headers
    response = await client.get("/api/demo/state", headers={**AUTH, "Origin": ORIGIN})
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in response.headers


async def test_no_openapi_or_docs_are_exposed(control):
    client, _ = control
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await client.get(path)).status_code == 404


def test_token_configuration_is_validated(monkeypatch):
    for bad in ("", "replace-with-a-generated-local-token", "short", "x" * 23):
        with pytest.raises(ConfigError):
            validate_token(bad)
    assert validate_token("x" * 24) == "x" * 24
    monkeypatch.delenv("DEMO_CONTROL_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        PlantSettings.from_env()
    monkeypatch.setenv("DEMO_CONTROL_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("FAULT_DURATION_SECONDS", "10")
    with pytest.raises(ConfigError):
        PlantSettings.from_env()
    monkeypatch.setenv("FAULT_DURATION_SECONDS", "120")
    monkeypatch.setenv("CONTROL_ALLOWED_ORIGINS", "*")
    with pytest.raises(ConfigError):
        PlantSettings.from_env()
    monkeypatch.setenv("CONTROL_ALLOWED_ORIGINS", "http://127.0.0.1:8088/")
    settings = PlantSettings.from_env()
    assert settings.fault_duration_s == 120 and settings.allowed_origins == ("http://127.0.0.1:8088",)
    assert settings.control_host == "127.0.0.1"  # loopback por defecto
