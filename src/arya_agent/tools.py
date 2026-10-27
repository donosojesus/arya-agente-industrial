"""Herramientas del agente: contrato explicito, validacion, timeout, errores controlados y registro.

Todas las herramientas sobre el proceso son de LECTURA. La unica que crea algo
es `create_work_order_draft`, y solo crea un BORRADOR en el CMMS que una persona
debe aprobar. No existe ninguna herramienta que escriba en la planta.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .documents import DocumentIndex
from .memory import AgentMemory

Signal = Literal["motor_temp", "vibration", "current", "discharge_pressure", "flow", "rpm"]
ASSET = "P-101"


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NoArgs(_Args):
    pass


class HistoryArgs(_Args):
    signals: list[Signal] = Field(default_factory=lambda: ["flow", "current", "discharge_pressure", "motor_temp", "vibration"],
                                  min_length=1, max_length=6, description="Señales a consultar; por defecto, todas las de proceso")
    minutes: float = Field(default=30, ge=1, le=240, description="Ventana hacia atrás, en minutos")


class CompareArgs(_Args):
    signal_a: Signal
    signal_b: Signal
    minutes: float = Field(default=30, ge=1, le=240)


class SearchArgs(_Args):
    query: str = Field(min_length=2, max_length=200, description="Qué buscar, en palabras simples")


class MemoryArgs(_Args):
    query: str | None = Field(default=None, max_length=200, description="Opcional; vacío devuelve lo más reciente")


class WorkOrderIdArgs(_Args):
    work_order_id: str = Field(min_length=4, max_length=30)


class DraftArgs(_Args):
    title: str = Field(min_length=5, max_length=120)
    problem: str = Field(min_length=10, max_length=800, description="Qué se observa, con valores")
    probable_cause: str = Field(min_length=5, max_length=500)
    recommended_action: str = Field(min_length=10, max_length=800)
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    evidence: list[str] = Field(min_length=1, max_length=8, description="Fuentes usadas: historian, órdenes, documentos")
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    work_type: Literal["CORRECTIVE", "PREDICTIVE", "PREVENTIVE"] = Field(
        "CORRECTIVE", description="PREDICTIVE si se basa en una tendencia, antes de una falla")
    planned_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha sugerida AAAA-MM-DD, por ejemplo una parada programada")


class TrendArgs(_Args):
    weeks: int = Field(26, ge=4, le=26, description="Semanas hacia atrás, máximo 26")


class ProjectionArgs(_Args):
    signal: Literal["vibration", "temp_norm", "pressure_deficit_pct"] = Field(
        "vibration", description="vibration, temp_norm (temperatura de motor a igual carga) o pressure_deficit_pct (déficit frente a la curva)")


@dataclass
class ToolContext:
    gateway: httpx.AsyncClient  # base_url = OT gateway
    cmms: httpx.AsyncClient  # base_url = CMMS
    cmms_agent_key: str
    documents: DocumentIndex
    memory: AgentMemory


@dataclass
class ToolOutcome:
    name: str
    ok: bool
    payload: dict[str, object]  # lo que recibe el modelo
    duration_ms: int
    source: str
    summary: str  # texto breve para la traza
    arguments: dict[str, object]


async def _request(client: httpx.AsyncClient, method: str, path: str, service: str, **kwargs) -> dict[str, object]:
    try:
        response = await client.request(method, path, **kwargs)
    except httpx.TimeoutException as exc:
        raise ToolError("timeout", f"{service} no respondió a tiempo.") from exc
    except httpx.HTTPError as exc:
        raise ToolError("unreachable", f"No se pudo contactar {service} ({type(exc).__name__}).") from exc
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        message = detail.get("message") if isinstance(detail, dict) else (detail if isinstance(detail, str) else None)
        code = detail.get("error") if isinstance(detail, dict) else None
        raise ToolError(code or f"http_{response.status_code}", message or f"{service} respondió HTTP {response.status_code}.")
    return body


def _quality_note(data: dict[str, object]) -> str:
    return "" if data.get("data_quality") == "GOOD" else " · DATOS NO VIGENTES"


# ----------------------------------------------------------------- manejadores
async def _current_tags(ctx: ToolContext, args: NoArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/tags", "el gateway OT")
    t = data["tags"]
    summary = (f"T={t['P101.MOTOR_TEMP']['value']} °C, vib={t['P101.VIBRATION']['value']} mm/s, "
               f"Q={t['P101.FLOW']['value']} m³/h, I={t['P101.CURRENT']['value']} A" + _quality_note(data))
    return data, "OPC UA (vía gateway OT)", summary


async def _equipment_status(ctx: ToolContext, args: NoArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/status", "el gateway OT")
    return data, "OPC UA (vía gateway OT)", f"{data['operating_status']}, nivel {data['alarm_level']}" + _quality_note(data)


async def _active_alarms(ctx: ToolContext, args: NoArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/alarms", "el gateway OT")
    codes = [a["code"] for a in data["active_alarms"]]
    return data, "OPC UA (vía gateway OT)", (", ".join(codes) if codes else "sin alarmas activas") + _quality_note(data)


async def _historian(ctx: ToolContext, args: HistoryArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/history", "el historian",
                          params={"signals": ",".join(args.signals), "minutes": args.minutes, "max_points": 5})
    parts = []
    for name, info in (data.get("signals") or {}).items():
        info.pop("points", None)  # el modelo recibe el resumen, no la serie
        if "change_pct" in info:
            parts.append(f"{name} {info['start_value']}→{info['end_value']} ({info['change_pct']:+}%)")
    return data, "Historian", "; ".join(parts) or str(data.get("message", "sin muestras"))


async def _compare(ctx: ToolContext, args: CompareArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/compare", "el historian",
                          params={"signal_a": args.signal_a, "signal_b": args.signal_b, "minutes": args.minutes})
    if "correlation" in data:
        summary = f"correlación {data['correlation']}"
        if data.get("which_deviated_first"):
            summary += f"; primero se desvió {data['which_deviated_first']} ({data['lead_seconds']} s antes)"
    else:
        summary = str(data.get("message", "sin datos suficientes"))
    return data, "Historian", summary


async def _documents(ctx: ToolContext, args: SearchArgs):
    hits = ctx.documents.search(args.query, 3)
    data = {"source": "Documentación de planta", "query": args.query, "results": hits}
    if not hits:
        data["message"] = "No se encontró documentación relacionada."
    ids = list(dict.fromkeys(h["document_id"] for h in hits))
    return data, "Documentos: " + (", ".join(ids) if ids else "sin resultados"), ", ".join(f"{h['document_id']} · {h['section']}" for h in hits) or "sin resultados"


async def _work_orders(ctx: ToolContext, args: MemoryArgs):
    params: dict[str, object] = {"asset": ASSET, "limit": 4}
    if args.query:
        params["q"] = args.query
    data = await _request(ctx.cmms, "GET", "/api/v1/work-orders", "el CMMS", params=params)
    if args.query and data["count"] == 0:  # sin coincidencias de texto: el historial reciente del equipo
        data = await _request(ctx.cmms, "GET", "/api/v1/work-orders", "el CMMS", params={"asset": ASSET, "limit": 4})
        data["note"] = "Sin coincidencias de texto; se devuelven las órdenes más recientes del equipo."
    ids = [o["id"] for o in data["work_orders"]]
    return data, "CMMS: " + (", ".join(ids) if ids else "sin órdenes"), ", ".join(ids) or "sin órdenes"


async def _work_order(ctx: ToolContext, args: WorkOrderIdArgs):
    data = await _request(ctx.cmms, "GET", f"/api/v1/work-orders/{args.work_order_id}", "el CMMS")
    return data, f"CMMS: {data['id']}", f"{data['id']} · {data['status']}"


async def _memory(ctx: ToolContext, args: MemoryArgs):
    items = ctx.memory.search(args.query, 5)
    data = {"source": "Memoria del agente", "count": len(items), "incidents": items}
    if not items:
        data["message"] = "La memoria no tiene incidentes registrados todavía."
    return data, "Memoria del agente", f"{len(items)} incidente(s) recordado(s)"


async def _create_draft(ctx: ToolContext, args: DraftArgs):
    order = await _request(ctx.cmms, "POST", "/api/v1/work-orders/drafts", "el CMMS",
                           json={"asset": ASSET, **args.model_dump()}, headers={"Authorization": f"Bearer {ctx.cmms_agent_key}"})
    run_id = None
    try:
        run_id = (await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/status", "el gateway OT")).get("run_id")
    except ToolError:
        pass  # la memoria se guarda igual, sin ensayo asociado
    ctx.memory.record_incident(ASSET, run_id, order)
    order["note"] = "BORRADOR creado. NO está aprobado: requiere aprobación de una persona."
    return order, f"CMMS: {order['id']}", f"{order['id']} · {order['status']}"


CONDITION_SOURCE = "Historian · capa oro (6 meses simulados)"


async def _condition_overview(ctx: ToolContext, args: NoArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/condition/overview", "el gateway OT")
    c = data.get("comparison") or {}
    summary = (f"zona {c.get('vibration_zone_recent')} · vibración {c.get('vibration_over_reference_pct')} % sobre la referencia"
               if c.get("ok") else "sin comparación disponible")
    return data, CONDITION_SOURCE, summary


async def _condition_trend(ctx: ToolContext, args: TrendArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/condition/daily", "el gateway OT",
                          params={"days": args.weeks * 7, "step": "week"})
    return data, CONDITION_SOURCE, f"{data['count']} semanas de indicadores"


async def _condition_projection(ctx: ToolContext, args: ProjectionArgs):
    data = await _request(ctx.gateway, "GET", f"/api/v1/assets/{ASSET}/condition/projection", "el gateway OT", params={"signal": args.signal})
    if data.get("trend") == "creciente":
        w = data["weeks_to_limit"]
        summary = f"{args.signal}: límite {data['limit']} en {w['early']} a {w['late']} semanas"
    else:
        summary = f"{args.signal}: {data.get('trend') or data.get('message')}"
    return data, CONDITION_SOURCE + " · proyección", summary


async def _planned_shutdowns(ctx: ToolContext, args: NoArgs):
    data = await _request(ctx.cmms, "GET", "/api/v1/planned-shutdowns", "el CMMS", params={"asset": ASSET})
    future = [s["date"] for s in data.get("shutdowns", []) if s.get("status") == "PROGRAMADA"]
    return data, "CMMS · calendario de paradas", "próximas: " + (", ".join(future) or "ninguna")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[_Args]
    handler: Callable[[ToolContext, _Args], Awaitable[tuple[dict[str, object], str, str]]]
    creates_draft: bool = False


TOOLS: tuple[Tool, ...] = (
    Tool("get_current_tags", "Valores actuales de P-101 (temperatura, vibración, corriente, presión, caudal, rpm) con su calidad.", NoArgs, _current_tags),
    Tool("get_equipment_status", "Estado de operación de P-101 y nivel de alarma actual.", NoArgs, _equipment_status),
    Tool("get_active_alarms", "Alarmas activas de P-101 con valor, límite y desde cuándo, y los límites configurados.", NoArgs, _active_alarms),
    Tool("get_historian_data", "Historia de una o más señales: valor inicial y final, cambio porcentual, tendencia y cuándo comenzó la desviación.", HistoryArgs, _historian),
    Tool("compare_signals", "Compara dos señales en el historian: correlación y cuál se desvió primero.", CompareArgs, _compare),
    Tool("search_maintenance_documents", "Busca en manuales, procedimientos y la ficha técnica de la planta. Usa varias palabras clave, por ejemplo: límites de vibración fabricante, repuestos sello, curva presión de descarga, procedimiento de lubricación. Devuelve fragmentos con el identificador del documento.", SearchArgs, _documents),
    Tool("search_previous_work_orders", "Busca órdenes de trabajo anteriores de P-101 en el CMMS.", MemoryArgs, _work_orders),
    Tool("get_work_order", "Lee una orden de trabajo del CMMS por su identificador.", WorkOrderIdArgs, _work_order),
    Tool("search_agent_memory", "Consulta la memoria del agente: incidentes que investigó antes, órdenes que creó y qué decidieron las personas.", MemoryArgs, _memory),
    Tool("get_condition_overview", "Salud de P-101 en 6 meses: zona de vibración, comparación de las últimas 2 semanas con el inicio del periodo a igual carga, y capas del historial.", NoArgs, _condition_overview),
    Tool("get_condition_trend", "Tendencia semanal de 6 meses de P-101: vibración, temperatura y corriente a igual carga, déficit de presión frente a la curva, horas y arranques.", TrendArgs, _condition_trend),
    Tool("project_condition_trend", "Proyecta, con un rango, cuándo una señal llegaría a su límite si la tendencia sigue. No predice la falla.", ProjectionArgs, _condition_projection),
    Tool("get_planned_shutdowns", "Calendario de paradas programadas del Área 100 (pasadas y próximas) del CMMS.", NoArgs, _planned_shutdowns),
    Tool("create_work_order_draft", "Crea un BORRADOR de orden de trabajo para P-101. Queda pendiente de aprobación humana; no se ejecuta.", DraftArgs, _create_draft, creates_draft=True),
)
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
# Solo se ofrecen al modelo cuando la pregunta es de salud, tendencia o planificación (ver agent.py).
CONDITION_TOOLS = frozenset({"get_condition_overview", "get_condition_trend", "project_condition_trend", "get_planned_shutdowns"})


def tool_specs() -> list[dict[str, object]]:
    """Definiciones en el formato de llamadas a herramientas del protocolo chat completions."""
    specs = []
    for tool in TOOLS:
        schema = tool.args_model.model_json_schema()
        schema.pop("title", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        specs.append({"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": schema}})
    return specs


async def execute(ctx: ToolContext, name: str, raw_arguments: str, timeout_s: float) -> ToolOutcome:
    """Ejecuta una herramienta dentro del envoltorio determinista. Nunca lanza: devuelve el resultado o el error."""
    started = time.monotonic()

    def failed(code: str, message: str, args: dict[str, object]) -> ToolOutcome:
        return ToolOutcome(name, False, {"ok": False, "error": code, "message": message}, int((time.monotonic() - started) * 1000),
                           "—", f"ERROR · {message}", args)

    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return failed("unknown_tool", f"La herramienta '{name}' no existe. Disponibles: {', '.join(TOOLS_BY_NAME)}.", {})
    try:
        parsed = json.loads(raw_arguments) if raw_arguments and raw_arguments.strip() else {}
        if not isinstance(parsed, dict):
            raise ValueError("los argumentos deben ser un objeto JSON")
        args = tool.args_model.model_validate(parsed)
    except (ValueError, ValidationError) as exc:
        detail = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()) if isinstance(exc, ValidationError) else str(exc)
        return failed("invalid_arguments", f"Argumentos no válidos: {detail}"[:400], parsed if isinstance(locals().get("parsed"), dict) else {})
    clean = args.model_dump(exclude_none=True)
    try:
        data, source, summary = await asyncio.wait_for(tool.handler(ctx, args), timeout=timeout_s)
    except asyncio.TimeoutError:
        return failed("timeout", f"La herramienta superó el tiempo máximo de {timeout_s:.0f} s.", clean)
    except ToolError as exc:
        return failed(exc.code, exc.message, clean)
    except Exception as exc:  # error no previsto: controlado, sin detalles internos al modelo
        return failed("internal_error", f"Error interno de la herramienta ({type(exc).__name__}).", clean)
    return ToolOutcome(name, True, {"ok": True, **data}, int((time.monotonic() - started) * 1000), source, summary, clean)
