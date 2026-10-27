from __future__ import annotations

import socket

import pytest

from arya_plant.config import PlantSettings
from arya_plant.runtime import PlantRuntime

TEST_TOKEN = "test-token-0123456789abcdefghijklmnop"
# Palabras que delatarian la causa real de la falla en una interfaz publica.
FORBIDDEN_WORDS = ("lubric", "bearing", "rodamiento", "ground_truth", "ground truth", "friction", "fricci")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def endpoint_for(port: int) -> str:
    return f"opc.tcp://127.0.0.1:{port}/arya/plant/"


def make_settings(port: int, tick_s: float = 0.1, **overrides) -> PlantSettings:
    return PlantSettings(control_token=TEST_TOKEN, opcua_endpoint=endpoint_for(port), tick_s=tick_s, **overrides)


@pytest.fixture
async def runtime_factory():
    """Crea plantas reales (simulador + servidor OPC UA) en puertos libres."""
    created: list[PlantRuntime] = []

    async def factory(port: int | None = None, steps_per_tick: int = 1, tick_s: float = 0.1) -> PlantRuntime:
        runtime = PlantRuntime(make_settings(port or free_port(), tick_s), steps_per_tick=steps_per_tick)
        await runtime.start()
        created.append(runtime)
        return runtime

    yield factory
    for runtime in created:
        await runtime.stop()


def assert_no_leak(text: str) -> None:
    lowered = text.lower()
    for word in FORBIDDEN_WORDS:
        assert word not in lowered, f"public output leaks the fault cause: {word!r}"


# --------------------------------------------------------------------------- agente
import asyncio  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import httpx  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
AGENT_KEY = "agent-key-0123456789abcdefghij"
HUMAN_TOKEN = "human-token-0123456789abcdefgh"
ADMIN_TOKEN = "admin-token-0123456789abcdefgh"


class ScriptedModel:
    """Modelo de reemplazo SOLO para pruebas: sigue un guion fijo de llamadas a herramientas.

    Permite probar el ciclo del agente, sus limites y la traza sin un modelo real.
    Nunca se usa en la demo.
    """

    name = "scripted-test-model"

    def __init__(self, script, delay_s: float = 0.0, repeat_last: bool = False) -> None:
        self.script, self.delay_s, self.repeat_last = list(script), delay_s, repeat_last
        self.calls: list[dict[str, object]] = []

    async def complete(self, messages, tools, tool_choice=None, thinking=None):
        from arya_agent.llm import ModelTurn, ToolCall

        self.calls.append({"messages": json.loads(json.dumps(messages)), "tools": tools, "tool_choice": tool_choice, "thinking": thinking})
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        step = self.script[0] if (self.repeat_last and len(self.script) == 1) else self.script.pop(0)
        if isinstance(step, str):
            return ModelTurn(step, [], 12, 100, 20)
        calls = [ToolCall(f"call_{len(self.calls)}_{i}", name, args if isinstance(args, str) else json.dumps(args))
                 for i, (name, args) in enumerate(step)]
        return ModelTurn("", calls, 15, 120, 30)

    async def health(self):
        return {"configured": True, "reachable": True, "model": self.name, "detail": None}


@pytest.fixture
async def agent_stack(runtime_factory, tmp_path):
    """Planta real (OPC UA) + gateway con historian + CMMS + agente, todo en proceso."""
    from arya_agent.agent import Agent
    from arya_agent.config import AgentSettings
    from arya_agent.documents import DocumentIndex
    from arya_agent.memory import AgentMemory
    from arya_agent.tools import ToolContext
    from arya_agent.trace import TraceHub
    from arya_cmms.app import create_cmms_app
    from arya_cmms.store import WorkOrderStore
    from arya_ot_gateway.app import create_gateway_app
    from arya_ot_gateway.config import GatewaySettings
    from arya_ot_gateway.historian import Historian
    from arya_otclient.poller import OpcUaPoller

    cleanup = []

    async def factory(model, steps_per_tick: int = 1, **overrides):
        runtime = await runtime_factory(tick_s=0.1, steps_per_tick=steps_per_tick)
        endpoint = runtime.settings.opcua_endpoint
        gw_settings = GatewaySettings(opcua_endpoint=endpoint, historian_path=str(tmp_path / "historian.sqlite3"), sample_s=0.05, stale_after_s=1.0)
        historian = Historian(gw_settings.historian_path)
        poller = OpcUaPoller(endpoint, sample_s=0.05, stale_after_s=1.0, timeout_s=1.5)
        gw_app = create_gateway_app(poller, historian, gw_settings, manage=False)
        poller.start()
        gw_app.state.recorder.start()
        store = WorkOrderStore(str(tmp_path / "cmms.sqlite3"), str(ROOT / "data" / "work-orders" / "seed.json"))
        cmms_app = create_cmms_app(store, AGENT_KEY, HUMAN_TOKEN, [])
        gateway = httpx.AsyncClient(transport=httpx.ASGITransport(app=gw_app), base_url="http://gateway")
        cmms = httpx.AsyncClient(transport=httpx.ASGITransport(app=cmms_app), base_url="http://cmms")
        memory = AgentMemory(str(tmp_path / "memory.sqlite3"))
        ctx = ToolContext(gateway, cmms, AGENT_KEY, DocumentIndex(str(ROOT / "data" / "documents")), memory)
        trace = TraceHub(str(tmp_path / "trace.jsonl"))
        settings = AgentSettings(data_dir=str(tmp_path), admin_token=ADMIN_TOKEN, **overrides)
        agent = Agent(model, ctx, trace, settings)

        async def close():
            await gateway.aclose()
            await cmms.aclose()
            await gw_app.state.recorder.stop()
            await poller.stop()
            historian.close()
            store.close()
            memory.close()

        cleanup.append(close)
        for _ in range(200):  # espera la primera muestra en el historian
            if historian.samples_written >= 3:
                break
            await asyncio.sleep(0.05)
        return SimpleNamespace(runtime=runtime, agent=agent, ctx=ctx, trace=trace, memory=memory, settings=settings,
                               historian=historian, poller=poller, cmms=cmms, gateway=gateway, tmp=tmp_path)

    yield factory
    for close in cleanup:
        await close()
