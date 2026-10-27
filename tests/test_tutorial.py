"""Pruebas del tutorial del libro: cada paso corre de verdad contra una planta, un gateway y el servidor de guion."""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import uvicorn

from conftest import free_port

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "tutorial"


@pytest.fixture
async def tutorial(runtime_factory, tmp_path):
    """Planta real + gateway HTTP en un puerto libre + servidor de guion, como en el paso 0."""
    from arya_ot_gateway.app import create_gateway_app
    from arya_ot_gateway.config import GatewaySettings
    from arya_ot_gateway.historian import Historian
    from arya_otclient.poller import OpcUaPoller

    runtime = await runtime_factory(tick_s=0.1, steps_per_tick=20)
    endpoint = runtime.settings.opcua_endpoint
    settings = GatewaySettings(opcua_endpoint=endpoint, historian_path=str(tmp_path / "historian.sqlite3"), sample_s=0.05, stale_after_s=1.0)
    historian = Historian(settings.historian_path)
    poller = OpcUaPoller(endpoint, sample_s=0.05, stale_after_s=1.0, timeout_s=1.5)
    app = create_gateway_app(poller, historian, settings, manage=False)
    poller.start()
    app.state.recorder.start()
    gw_port, model_port = free_port(), free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=gw_port, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    model = await asyncio.create_subprocess_exec(sys.executable, str(TUTORIAL / "modelo_guion.py"),
                                                 env={**os.environ, "GUION_PORT": str(model_port)}, stdout=asyncio.subprocess.PIPE)
    await model.stdout.readline()  # espera el aviso de que el servidor de guion escucha
    for _ in range(200):
        if server.started and historian.samples_written >= 3:
            break
        await asyncio.sleep(0.05)
    env = {**os.environ, "GATEWAY_URL": f"http://127.0.0.1:{gw_port}", "NEMOTRON_BASE_URL": f"http://127.0.0.1:{model_port}/v1",
           "NEMOTRON_MODEL": "modelo-de-guion", "NEMOTRON_API_KEY": ""}

    async def run(script: str, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec(sys.executable, str(TUTORIAL / script), *args, env=env,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
        assert proc.returncode == 0, out.decode()
        return out.decode()

    yield SimpleNamespace(run=run, runtime=runtime, poller=poller)
    model.terminate()
    await model.wait()
    server.should_exit = True
    await serving
    await app.state.recorder.stop()
    await poller.stop()
    historian.close()


async def test_paso0_checks_gateway_plant_and_model(tutorial):
    out = await tutorial.run("paso0_entorno.py")
    assert out.count("[ OK ]") == 3 and "Todo listo para el paso 1." in out and "vibración" in out


async def test_paso1_talks_to_the_model_without_tools(tutorial):
    out = await tutorial.run("paso1_hablar.py")
    assert "ARYA: [guion] No soy un modelo" in out and "tokens de entrada: n/d" in out


async def test_paso2_executes_the_tool_the_model_asks_for(tutorial):
    tutorial.runtime.simulator.inject_fault(scenario="alpha")
    for _ in range(600):
        sample = tutorial.poller.state.sample
        if sample is not None and sample.tags["P101.ALARM_LEVEL"]["value"] == "ALARM":
            break
        await asyncio.sleep(0.05)
    out = await tutorial.run("paso2_herramienta.py")
    assert "→ el modelo pide: get_active_alarms({})" in out and "caracteres de datos reales" in out
    assert "ARYA: [guion] Consulté get_active_alarms." in out


async def test_paso3_loops_until_the_model_answers(tutorial):
    out = await tutorial.run("paso3_ciclo.py")
    assert "vuelta 1 · el modelo pide get_active_alarms({})" in out
    assert 'vuelta 2 · el modelo pide get_historian_data({"signals": ["vibration", "motor_temp"], "minutes": 10})' in out
    assert "vuelta 3 · el modelo responde con texto" in out and "mensajes en la conversación: 7" in out


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TUTORIAL / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_paso3_limits_stop_a_model_that_never_answers(monkeypatch, capsys):
    paso3 = _load("paso3_ciclo")
    offered, executed = [], []
    call = {"id": "c", "type": "function", "function": {"name": "get_current_tags", "arguments": "{}"}}
    monkeypatch.setattr(paso3, "preguntar", lambda mensajes, herramientas=None: offered.append(herramientas) or
                        {"choices": [{"message": {"content": None, "tool_calls": [call, call, call]}}]})
    monkeypatch.setattr(paso3, "ejecutar", lambda llamada: executed.append(llamada) or {"ok": True})
    answer, _ = paso3.ciclo("bucle")
    assert answer == "Llegué al límite de llamadas al modelo sin terminar el análisis."
    assert len(offered) == paso3.MAX_VUELTAS and len(executed) == paso3.MAX_HERRAMIENTAS
    assert offered[-1] is None  # sin presupuesto, ya no se ofrecen herramientas


def test_paso3_executor_returns_errors_as_data():
    paso3 = _load("paso3_ciclo")
    unknown = paso3.ejecutar({"function": {"name": "open_valve", "arguments": "{}"}})
    broken = paso3.ejecutar({"function": {"name": "get_historian_data", "arguments": "no es json"}})
    assert "no existe" in unknown["error"] and broken["error"].startswith("JSONDecodeError")
