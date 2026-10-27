"""API del agente ARYA: conversacion, traza en vivo, decisiones humanas y aviso proactivo."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .agent import PROACTIVE_PROMPT, Agent
from .config import AgentSettings
from .memory import AgentMemory
from .tools import ASSET, TOOLS, ToolError, _request
from .trace import TraceHub

log = logging.getLogger("arya.agent")
DEFAULT_CONVERSATION = "demo"
_LEVELS = {"NORMAL": 0, "WARNING": 1, "ALARM": 2}


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=600)
    conversation_id: str | None = Field(default=None, max_length=60)


class SyncRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    work_order_id: str = Field(min_length=4, max_length=30)


class ProactiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ProactiveWatcher:
    """Vigila las alarmas por el gateway y, si esta habilitado, hace que ARYA avise sin que le pregunten."""

    def __init__(self, agent: Agent, settings: AgentSettings) -> None:
        self.agent, self.settings = agent, settings
        self.enabled = settings.proactive
        self.armed = False  # se arma al ver la planta en NORMAL: un aviso por incidente
        self.triggers = 0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="arya-proactive")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _alarms(self) -> dict[str, object] | None:
        try:
            data = await _request(self.agent.ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/alarms", "el gateway OT")
        except ToolError:
            return None
        return data if data.get("data_quality") == "GOOD" else None

    async def _run(self) -> None:
        threshold = _LEVELS.get(self.settings.proactive_level, 1)
        while True:
            try:
                data = await self._alarms()
                if data is not None:
                    level = _LEVELS.get(str(data.get("alarm_level")), 0)
                    if level == 0:
                        self.armed = True
                    elif self.armed and level >= threshold:
                        self.armed = False
                        if self.enabled:
                            await asyncio.sleep(self.settings.proactive_settle_s)  # deja juntar algo de historia
                            fresh = await self._alarms() or data
                            codes = ", ".join(a["code"] for a in fresh.get("active_alarms", [])) or "alarma activa"
                            self.triggers += 1
                            await self.agent.handle(PROACTIVE_PROMPT.format(alarms=codes), DEFAULT_CONVERSATION, origin="proactive")
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("proactive watcher error")
            await asyncio.sleep(self.settings.proactive_poll_s)


def create_agent_app(agent: Agent, trace: TraceHub, memory: AgentMemory, settings: AgentSettings, run_watcher: bool = True) -> FastAPI:
    watcher = ProactiveWatcher(agent, settings)
    health_cache: dict[str, object] = {"at": 0.0, "value": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if run_watcher:
            watcher.start()
        trace.publish("system", message="Agente iniciado", node=settings.node_label)
        try:
            yield
        finally:
            await watcher.stop()

    app = FastAPI(title="ARYA agent", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.watcher = watcher

    async def reachable(client: httpx.AsyncClient, path: str) -> bool:
        try:
            return (await client.get(path, timeout=3.0)).status_code == 200
        except httpx.HTTPError:
            return False

    async def status_body() -> dict[str, object]:
        if time.monotonic() - float(health_cache["at"]) > 4.0:
            llm, gateway, cmms = await asyncio.gather(agent.model.health(), reachable(agent.ctx.gateway, "/healthz"), reachable(agent.ctx.cmms, "/healthz"))
            health_cache.update(at=time.monotonic(), value={"llm": llm, "ot_gateway_reachable": gateway, "cmms_reachable": cmms})
        return {
            "agent": "ARYA", "version": __version__, "node": settings.node_label, "state": agent.state, "busy": agent.busy,
            **health_cache["value"],
            "documents": len(agent.ctx.documents.documents), "memory_incidents": memory.count(),
            "tools": [t.name for t in TOOLS], "process_write_tools": [],  # no existen herramientas de escritura al proceso
            "proactive": {"enabled": watcher.enabled, "level": settings.proactive_level, "triggers": watcher.triggers},
            "limits": {"max_steps": settings.max_steps, "max_tool_calls": settings.max_tool_calls, "tool_timeout_s": settings.tool_timeout_s,
                       "turn_timeout_s": settings.turn_timeout_s},
            "last_event_seq": trace.last_seq,
            "tokens": {"conversation": dict(agent.tokens_conversation), "since_start": dict(agent.tokens_total)},
        }

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "state": agent.state}  # el proceso del agente vive; el modelo se informa en /status

    @app.get("/api/v1/status")
    async def status():
        return await status_body()

    @app.post("/api/v1/chat")
    async def chat(body: ChatRequest):
        if agent.busy:
            raise HTTPException(status_code=409, detail={"error": "busy", "message": "ARYA está respondiendo otra consulta."})
        result = await agent.handle(body.message, body.conversation_id or DEFAULT_CONVERSATION)
        return {"turn_id": result.turn_id, "conversation_id": result.conversation_id, "answer": result.answer, "status": result.status,
                "sources": result.sources, "tool_calls": result.tool_calls, "work_order_draft": result.draft, "timings_ms": result.timings_ms,
                "tokens": result.tokens, "speed": result.speed}

    @app.get("/api/v1/trace")
    async def trace_events(since: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=1000)):
        return {"last_seq": trace.last_seq, "events": trace.since(since, limit)}

    @app.get("/api/v1/feed")
    async def feed(request: Request, since: int = Query(0, ge=0), last_event_id: str | None = Header(default=None)):
        start = max(since, int(last_event_id) if last_event_id and last_event_id.isdigit() else 0)

        async def stream():
            queue = trace.subscribe()
            try:
                sent = start
                for event in trace.since(start):
                    sent = event["seq"]
                    yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            return
                        yield ": keepalive\n\n"
                        continue
                    if event["seq"] > sent:
                        sent = event["seq"]
                        yield f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            finally:
                trace.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.post("/api/v1/work-orders/{draft_id}/sync")
    async def sync_decision(draft_id: str, body: SyncRequest):
        """La interfaz avisa que una persona decidio; el agente lo VERIFICA en el CMMS antes de recordarlo."""
        try:
            order = await _request(agent.ctx.cmms, "GET", f"/api/v1/work-orders/{body.work_order_id}", "el CMMS")
        except ToolError as exc:
            raise HTTPException(status_code=502, detail={"error": exc.code, "message": exc.message}) from exc
        same = order.get("draft_id") == draft_id.upper() or order.get("id") == draft_id.upper()
        if not same or order.get("status") not in ("OPEN", "REJECTED"):
            raise HTTPException(status_code=409, detail={"error": "not_decided", "message": "El CMMS no registra una decisión humana para ese borrador."})
        remembered = memory.record_decision(draft_id.upper(), order)
        trace.publish("human_decision", draft_id=draft_id.upper(), work_order_id=order["id"], status=order["status"],
                      decided_by=order.get("approved_by") or order.get("rejected_by"), remembered=remembered)
        return {"work_order_id": order["id"], "status": order["status"], "remembered": remembered}

    @app.post("/api/v1/conversation/clear")
    async def clear_conversation():
        """Empieza una conversacion nueva: borra el contexto de corto plazo y limpia las pantallas.

        No borra la memoria de largo plazo, ni las ordenes del CMMS, ni el registro de auditoria.
        """
        if agent.busy:
            raise HTTPException(status_code=409, detail={"error": "busy", "message": "ARYA está respondiendo; espere a que termine."})
        agent.reset()
        trace.publish("conversation_cleared", message="Conversación reiniciada por el presentador")
        return {"cleared": True}

    @app.post("/api/v1/proactive")
    async def proactive(body: ProactiveRequest):
        watcher.enabled = body.enabled
        trace.publish("system", message=f"Aviso proactivo {'activado' if body.enabled else 'desactivado'}")
        return {"enabled": watcher.enabled}

    @app.post("/api/v1/admin/reset")
    async def reset(authorization: str | None = Header(default=None)):
        if not settings.admin_token:
            raise HTTPException(status_code=503, detail="reset disabled: AGENT_ADMIN_TOKEN not configured")
        scheme, _, presented = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(presented.strip().encode(), settings.admin_token.encode()):
            raise HTTPException(status_code=401, detail="missing or invalid credential")
        if agent.busy:
            raise HTTPException(status_code=409, detail="agent is busy")
        memory.clear()
        agent.reset()
        trace.clear()
        watcher.armed = False
        return {"reset": True}

    return app
