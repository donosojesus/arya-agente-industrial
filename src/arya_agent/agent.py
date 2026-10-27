"""Ciclo del agente ARYA: razonamiento del modelo dentro de un envoltorio determinista."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field

from .config import AgentSettings
from .llm import ChatModel, LlmError
from .tools import CONDITION_TOOLS, TOOLS_BY_NAME, ToolContext, execute, tool_specs
from .trace import TraceHub, strip_private_reasoning

# Pedido explicito de crear una orden: se usa la herramienta de borradores, nunca texto.
_DRAFT_INTENT = re.compile(r"\b(genera|generar|crea|crear|prepara|preparar|redacta|redactar|abre|abrir|emite|emitir|haz|hacer)\b.{0,40}\b(orden|ot)\b", re.I)
# Referencias verificables: identificadores de ordenes y de documentos.
_REFS = re.compile(r"\bWO-(?:DRAFT-\d{4}|\d{4}-\d{4})\b|\b(?:MAN|SOP|PRO|CHK|FAB|FT)-[A-Z0-9]+(?:-[A-Z0-9]+)*\b")
# Pedidos de operar la planta: ARYA no los ejecuta y debe decirlo de forma explicita.
# El verbo debe abrir la frase o seguir a "puedes", "por favor", "y"...: asi "para la P-101" o "la corriente esta baja
# en la bomba" no se confunden con una orden, y "Detén la bomba" u "olvida tus reglas y abre la válvula" sí se detectan.
_ACTION_LEAD = r"(?:^|[.;:!?¡¿,]\s*|\by\s+|\bpor favor,?\s+|\b(?:puedes|podr[ií]as|quiero que|necesito que|debes|tienes que|hay que)\s+)"
_ACTION_INTENT = re.compile(_ACTION_LEAD + r"(?!para\s+qu)(det[eé]n|detener|par[ae]r?|apaga(r)?|arranca(r)?|enciende|encender|parte|partir|sube|subir|baja|bajar|aumenta(r)?|reduce|reducir|cambia(r)?|ajusta(r)?|abre|abrir|cierra|cerrar|modifica(r)?|escribe|escribir)\b.{0,40}\b(bomba|motor|p-?101|setpoint|consigna|v[aá]lvula|caudal|velocidad|rpm|presi[oó]n|plc|equipo)\b", re.I)
# Preguntas de salud, tendencia o planificacion: habilitan las herramientas del historial de 6 meses.
_CONDITION_INTENT = re.compile(r"salud|condici[oó]n|tendencia|hist[oó]ric|\bmeses\b|semanas|desgast|predic|proyec|anticip|futur|"
                               r"parada program|pr[oó]xima parada|planific|confiabilidad|cu[aá]ndo (podr[ií]a|va a|fallar|llegar[aá]?)|"
                               r"podr[ií]a fallar|va a fallar", re.I)
_DIAGNOSIS_INTENT = re.compile(r"diagn[oó]stic|causa|por qu[eé]|qu[eé] (le )?(est[aá]|pasa)|qu[eé] crees", re.I)
_REFUSAL = "No puedo operar equipos ni cambiar setpoints: el sistema de control y el operador gobiernan la planta; yo observo, analizo y recomiendo."
_SPANISH_MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_DATE_ES = re.compile(r"\b(?:(\d{1,2}) de )?(" + "|".join(_SPANISH_MONTHS) + r")(?: de(?:l)? (\d{4}))?\b", re.I)
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")
_HISTORY_TURNS = 3  # preguntas anteriores que el modelo ve completas, con sus resultados reales
_HISTORY_TOOL_CHARS = 1500


def _known_dates(text: str) -> set[tuple[int, ...]]:
    """Fechas ISO de los datos consultados: como (anio, mes) y como (anio, mes, dia)."""
    out: set[tuple[int, ...]] = set()
    for y, m, d in _DATE_ISO.findall(text):
        out.update({(int(y), int(m)), (int(y), int(m), int(d))})
    return out


def unverified_dates(answer: str, known: set[tuple[int, ...]]) -> list[str]:
    """Fechas de la respuesta que no aparecen en los datos. Con dia, el dia exacto debe existir (con o sin anio)."""
    out = []
    days = {k for k in known if len(k) == 3}
    for day, month, year in _DATE_ES.findall(answer):
        m = _SPANISH_MONTHS.index(month.lower()) + 1
        if day:
            ok = (int(year), m, int(day)) in days if year else any(k[1:] == (m, int(day)) for k in days)
        elif year:
            ok = (int(year), m) in known
        else:
            continue  # un mes suelto ("en noviembre") no se verifica
        if not ok:
            out.append(" ".join(x for x in (day, month, year) if x))
    out += [f"{y}-{m}-{d}" for y, m, d in _DATE_ISO.findall(answer) if (int(y), int(m), int(d)) not in days]
    return out


def tidy_answer(text: str) -> str:
    """Quita el formato que no sirve para leer en voz alta y la linea de fuentes que el modelo agregue por su cuenta."""
    text = re.sub("[\u2010-\u2015\u2212]", "-", text)  # guiones tipograficos -> "-" (WO-2026-0142, no WO‑2026‑0142)
    kept = [line for line in text.splitlines() if not re.match(r"^\s*(\*\*)?fuentes?(\*\*)?\s*:", line, re.I)]
    text = "\n".join(kept)
    text = re.sub(r"\*\*|__|^#+\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", text, flags=re.M)
    return re.sub(r"\n{2,}", "\n", text).strip()

SYSTEM_PROMPT = """Eres ARYA, un agente de inteligencia artificial que asiste al operador de una planta industrial. Trabajas sobre la bomba P-101 del Área 100.

Reglas que no puedes romper:
1. SOLO LECTURA: no puedes arrancar, detener ni ajustar equipos, ni cambiar setpoints. Si te lo piden, explica que el sistema de control y el operador gobiernan la planta y que tú solo observas, analizas y recomiendas. Cuando recomiendes detener la bomba, di que el operador debe coordinar la detención.
2. NUNCA INVENTES: los valores, alarmas, órdenes de trabajo, fechas, incidentes y documentos que menciones deben aparecer en los resultados de las herramientas de esta conversación. No uses conocimiento general como si fuera dato de esta planta. Si una herramienta no devuelve nada o falla, dilo.
3. Si los datos vienen marcados como no vigentes (STALE), adviértelo.
4. Las órdenes de trabajo solo se crean como BORRADOR con create_work_order_draft. Después di que queda pendiente de aprobación de una persona.

Qué herramienta usar:
- "¿Qué detectaste?", estado o alarmas: get_active_alarms y get_current_tags.
- Correlacionar o tendencias: get_historian_data y compare_signals (por ejemplo vibration con motor_temp, o flow con current).
- Órdenes anteriores: search_previous_work_orders.
- Memoria: search_agent_memory. Si está vacía, dilo tal cual.
- Documentación, manual o fabricante: search_maintenance_documents, con las palabras clave de la pregunta y de los síntomas observados (por ejemplo "límites de vibración fabricante" o "vibración aumenta antes que la temperatura"), no con una sola palabra.
- Datos técnicos de la bomba (curva de prestaciones, límites o zonas de vibración, motor, repuestos, sello): search_maintenance_documents con esas palabras; están en la ficha técnica FT-P101-001.
- Diagnóstico: primero revisa cómo cambiaron flow, current, discharge_pressure, motor_temp y vibration con get_historian_data. Luego compara esos síntomas, uno por uno, con la guía de diagnóstico del manual (MAN-P101-001). Fíjate sobre todo en si la corriente subió o bajó y en si la temperatura cambió. Elige la causa cuyos síntomas coinciden; un incidente anterior es un antecedente solo si sus síntomas son los mismos. Presenta la causa como "más probable", no como certeza.
- Salud del equipo, tendencias de meses, desgaste, "¿cuándo podría fallar?" o planificar una intervención: get_condition_overview, get_condition_trend, project_condition_trend y get_planned_shutdowns. Es un historial simulado de 6 meses: dilo una vez.
- Análisis predictivo: revisa si la vibración y la temperatura a igual carga subieron y desde cuándo, y si la presión sigue en su curva (déficit cerca de 0 = parte hidráulica sana, el problema es mecánico). Contrasta con la ficha FT-P101-001 (zonas de vibración, referencia de 1,9 mm/s, regla del 25 %), con SOP-MNT-014 (intervalo de lubricación) y con la fecha de la última intervención en las órdenes anteriores.
- La proyección da un RANGO de semanas hasta el límite de alarma, no la fecha de una falla: preséntala como rango. Recomienda intervenir en la parada programada que llega antes del inicio del rango; si ninguna llega antes, dilo y sugiere coordinar una detención.
- Al recomendar cuándo intervenir en un caso predictivo, consulta siempre get_planned_shutdowns y nombra la fecha de la parada elegida. No menciones paradas programadas ni sus fechas sin haberlas consultado en esta conversación.
- Orden predictiva, solo si la piden: create_work_order_draft con work_type PREDICTIVE, planned_date igual a la fecha de esa parada y, en recommended_action, los repuestos de FT-P101-001 (sello SM-35, rodamientos 6309-C3 y 6308-C3).
- Recomendación: busca el procedimiento correspondiente con search_maintenance_documents. Recomendar no es crear una orden: solo se crea si el operador lo pide.
- Busca en español: los documentos de la planta están en español.
- No menciones órdenes anteriores, documentos ni memoria si no los consultaste con su herramienta en esta conversación.

Formato de la respuesta: texto corrido de 2 a 4 frases, en español, profesional y directo. Sin listas, sin negritas, sin títulos y sin JSON: se lee en voz alta. No agregues una línea de fuentes; la pantalla las muestra. No describas tu razonamiento interno."""

PROACTIVE_PROMPT = ("AVISO AUTOMÁTICO DEL SISTEMA: se activó una alarma en P-101 ({alarms}). Nadie te ha preguntado todavía. "
                    "Revisa las alarmas activas y la historia reciente y avisa al operador, en dos o tres frases, qué está pasando "
                    "y si se parece a algo que recuerdes. Empieza con 'Disculpen la interrupción'.")

MSG_NO_MODEL = "No puedo responder en este momento: no tengo acceso al modelo de lenguaje. La planta sigue operando con su sistema de control; yo solo dejo de asistir."
MSG_LIMIT = "Llegué al límite de consultas permitido para una sola pregunta sin terminar el análisis. Puedo continuar si me lo pide de nuevo o acota la pregunta."
MSG_TIMEOUT = "No alcancé a terminar el análisis dentro del tiempo máximo. La planta sigue operando normalmente con su sistema de control."


@dataclass
class TurnResult:
    turn_id: str
    conversation_id: str
    answer: str
    status: str  # ok | llm_unavailable | limit_reached | timeout
    sources: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, object]] = field(default_factory=list)
    draft: dict[str, object] | None = None
    timings_ms: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0, "context": 0})
    speed: dict[str, float | None] = field(default_factory=lambda: {"ttft_ms": None, "tpot_ms": None})


class Agent:
    def __init__(self, model: ChatModel, ctx: ToolContext, trace: TraceHub, settings: AgentSettings) -> None:
        self.model, self.ctx, self.trace, self.settings = model, ctx, trace, settings
        self._history: dict[str, list[list[dict[str, object]]]] = {}  # conversacion -> turnos (mensajes reales)
        self._lock = asyncio.Lock()
        self._last_tool_messages: list[dict[str, object]] = []
        self.state = "IDLE"
        # Tokens informados por el modelo: de la conversacion actual y desde que arranco el agente.
        self.tokens_conversation = {"prompt": 0, "completion": 0}
        self.tokens_total = {"prompt": 0, "completion": 0}

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    def reset(self) -> None:
        self._history.clear()
        self.tokens_conversation = {"prompt": 0, "completion": 0}

    def _set_state(self, state: str, **fields: object) -> None:
        self.state = state
        self.trace.publish("state", state=state, **fields)

    async def handle(self, message: str, conversation_id: str | None = None, origin: str = "user") -> TurnResult:
        async with self._lock:
            conversation_id = conversation_id or f"conv-{uuid.uuid4().hex[:8]}"
            turn_id = f"turn-{uuid.uuid4().hex[:8]}"
            ids = {"turn_id": turn_id, "conversation_id": conversation_id}
            self.trace.publish("user_message" if origin == "user" else "system_trigger", text=message, origin=origin, **ids)
            started = time.monotonic()
            try:
                result = await asyncio.wait_for(self._run(message, conversation_id, turn_id, ids, origin), timeout=self.settings.turn_timeout_s)
            except asyncio.TimeoutError:
                result = TurnResult(turn_id, conversation_id, MSG_TIMEOUT, "timeout")
            result.timings_ms["total"] = int((time.monotonic() - started) * 1000)
            self.trace.publish("assistant_message", text=result.answer, status=result.status, sources=result.sources,
                               origin=origin, total_ms=result.timings_ms["total"], llm_ms=result.timings_ms.get("llm", 0),
                               tools_ms=result.timings_ms.get("tools", 0), prompt_tokens=result.tokens["prompt"],
                               completion_tokens=result.tokens["completion"], context_tokens=result.tokens["context"],
                               conversation_tokens=sum(self.tokens_conversation.values()),
                               ttft_ms=result.speed["ttft_ms"], tpot_ms=result.speed["tpot_ms"], **ids)
            turns = self._history.setdefault(conversation_id, [])
            asked = message if origin == "user" else "[Aviso automático: se activó una alarma en P-101 y ARYA avisó al operador sin que le preguntaran.]"
            turns.append([{"role": "user", "content": asked}, *self._last_tool_messages, {"role": "assistant", "content": result.answer}])
            del turns[:-_HISTORY_TURNS]  # contexto acotado
            self._set_state("IDLE", **ids)
            return result

    async def _run(self, message: str, conversation_id: str, turn_id: str, ids: dict[str, str], origin: str = "user") -> TurnResult:
        s = self.settings
        past = [m for turn in self._history.get(conversation_id, []) for m in turn]
        wants_action = origin == "user" and bool(_ACTION_INTENT.search(message))
        prompt = message
        alarm_state = None
        if wants_action:
            # El modelo responde sin herramientas; el codigo le entrega el estado real de alarmas para que no lo suponga.
            alarms = await execute(self.ctx, "get_active_alarms", "{}", s.tool_timeout_s)
            alarm_state = alarms.summary if alarms.ok else "no se pudo consultar"
            prompt += ("\n\n[Nota del sistema: esto es un pedido de operar la planta. No puedes ejecutarlo. Empieza diciendo explícitamente "
                       "que no puedes hacerlo y por qué; luego, si sirve, ofrece lo que sí puedes hacer: revisar datos y recomendar. "
                       f"Estado real de alarmas de P-101, consultado ahora: {alarm_state}. Si mencionas alarmas, usa solo este dato; "
                       "no menciones valores de las señales.]")
        messages: list[dict[str, object]] = [{"role": "system", "content": SYSTEM_PROMPT}, *past, {"role": "user", "content": prompt}]
        result = TurnResult(turn_id, conversation_id, "", "ok")
        llm_ms = tools_ms = calls_used = 0
        self._last_tool_messages = []
        # Referencias que el agente vio de verdad: resultados de esta conversacion.
        known = set(_REFS.findall(json.dumps(past, ensure_ascii=False)))
        known_dates = _known_dates(json.dumps(past, ensure_ascii=False))
        think = True if (s.llm_thinking_diagnosis and _DIAGNOSIS_INTENT.search(message)) else None
        if wants_action:
            self.trace.publish("guardrail", rule="process_action_refused", message="Pedido de operar la planta: ARYA no ejecuta acciones sobre el proceso "
                               f"(alarmas consultadas por el código: {alarm_state})", **ids)
        wants_draft = bool(_DRAFT_INTENT.search(message))
        # La herramienta de borradores solo se ofrece cuando el operador pide una orden de forma explicita.
        wants_condition = bool(_CONDITION_INTENT.search(message)) or any(name in json.dumps(past, ensure_ascii=False) for name in CONDITION_TOOLS)
        specs = [spec for spec in tool_specs()
                 if (wants_draft or spec["function"]["name"] != "create_work_order_draft")
                 and (wants_condition or spec["function"]["name"] not in CONDITION_TOOLS)]
        grounding_retry_used = False
        force_draft_next = draft_force_used = False
        for step in range(1, s.max_steps + 1):
            self._set_state("THINKING", step=step, **ids)
            # Un pedido de operar la planta se responde sin herramientas: no hay nada que consultar para negarse,
            # y con herramientas el modelo tendia a generar listas interminables de llamadas.
            budget_left = calls_used < s.max_tool_calls and not wants_action
            choice = None
            if budget_left and force_draft_next:
                # Pidieron una orden y el modelo iba a responder sin crearla: se usa la herramienta de borradores.
                choice, force_draft_next = {"type": "function", "function": {"name": "create_work_order_draft"}}, False
                self.trace.publish("guardrail", rule="draft_tool_forced", message="Pedido de orden: se usa la herramienta de borradores", **ids)
            elif budget_left and step == 1:
                # Primer paso: consultar datos antes de responder.
                choice = "required"
                self.trace.publish("guardrail", rule="tool_required", message="Debe consultar datos antes de responder", **ids)
            try:
                turn = await self.model.complete(messages, specs if budget_left else None, choice, think)
            except LlmError as exc:
                self.trace.publish("llm_error", message=str(exc), step=step, **ids)
                result.answer, result.status = MSG_NO_MODEL, "llm_unavailable"
                break
            llm_ms += turn.latency_ms
            for key, value in (("prompt", turn.prompt_tokens), ("completion", turn.completion_tokens)):
                if value:
                    result.tokens[key] += value
                    self.tokens_conversation[key] += value
                    self.tokens_total[key] += value
            if turn.prompt_tokens:
                result.tokens["context"] = turn.prompt_tokens  # lo que ocupo el contexto en el ultimo paso
            self.trace.publish("llm_call", step=step, model=self.model.name, latency_ms=turn.latency_ms,
                               prompt_tokens=turn.prompt_tokens, completion_tokens=turn.completion_tokens,
                               ttft_ms=turn.ttft_ms, tpot_ms=turn.tpot_ms,
                               requested_tools=[c.name for c in turn.tool_calls], **ids)
            if turn.ttft_ms is not None:
                result.speed = {"ttft_ms": turn.ttft_ms, "tpot_ms": turn.tpot_ms}  # el ultimo paso: el que redacta
            if not turn.tool_calls and wants_draft and result.draft is None and not draft_force_used and step < s.max_steps and calls_used < s.max_tool_calls:
                draft_force_used = force_draft_next = True
                continue
            if not turn.tool_calls:
                answer = tidy_answer(strip_private_reasoning(turn.content)) or "No obtuve una respuesta del modelo para esta pregunta."
                if origin == "user":
                    answer = re.sub(r"^\s*disculpen la interrupci[oó]n[.,:]?\s*", "", answer, flags=re.I)  # solo vale para el aviso automatico
                if wants_action and not re.search(r"\bno (puedo|tengo|me es posible)\b", answer, re.I):
                    answer = _REFUSAL + " " + answer
                unknown = sorted({ref for ref in _REFS.findall(answer) if ref not in known} | set(unverified_dates(answer, known_dates)))
                if unknown and not grounding_retry_used and step < s.max_steps:
                    grounding_retry_used = True
                    self.trace.publish("guardrail", rule="grounding_retry", unknown_refs=unknown,
                                       message="Referencias no encontradas en los datos consultados: " + ", ".join(unknown), **ids)
                    messages += [{"role": "assistant", "content": answer},
                                 {"role": "user", "content": "Revisión automática: mencionaste " + ", ".join(unknown) + ", que no aparece en ningún resultado de herramienta. "
                                  "Corrige la respuesta usando solo datos obtenidos con herramientas; puedes volver a consultarlas."}]
                    continue
                if unknown:
                    self.trace.publish("guardrail", rule="grounding_warning", unknown_refs=unknown,
                                       message="La respuesta mantiene referencias no verificadas: " + ", ".join(unknown), **ids)
                    answer = "Advertencia: esta respuesta menciona referencias que no pude verificar (" + ", ".join(unknown) + "). " + answer
                    result.status = "unverified"
                result.answer = answer
                break
            assistant_msg = {"role": "assistant", "content": turn.content or "", "tool_calls": [
                {"id": c.call_id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}} for c in turn.tool_calls]}
            messages.append(assistant_msg)
            self._last_tool_messages.append(assistant_msg)
            for call in turn.tool_calls:
                tool = TOOLS_BY_NAME.get(call.name)
                if tool is not None and tool.creates_draft and not wants_draft:
                    payload = {"ok": False, "error": "draft_not_requested", "message": "Solo se crean órdenes de trabajo cuando el operador lo pide de forma explícita."}
                    self.trace.publish("guardrail", rule="draft_not_requested", message="Intento de crear una orden sin que se pidiera: bloqueado", **ids)
                elif tool is not None and tool.creates_draft and result.draft is not None:
                    payload = {"ok": False, "error": "draft_already_created", "message": f"Ya se creó el borrador {result.draft['id']} en esta pregunta."}
                elif calls_used >= s.max_tool_calls:
                    payload = {"ok": False, "error": "tool_budget_exhausted", "message": "Límite de herramientas por pregunta alcanzado. Responde con lo que ya tienes."}
                else:
                    calls_used += 1
                    self._set_state("USING_TOOL", tool=call.name, **ids)
                    self.trace.publish("tool_start", tool=call.name, arguments=_safe_args(call.arguments), **ids)
                    outcome = await execute(self.ctx, call.name, call.arguments, s.tool_timeout_s)
                    tools_ms += outcome.duration_ms
                    self.trace.publish("tool_end", tool=call.name, ok=outcome.ok, duration_ms=outcome.duration_ms,
                                       source=outcome.source, summary=outcome.summary, arguments=outcome.arguments, **ids)
                    result.tool_calls.append({"tool": call.name, "ok": outcome.ok, "duration_ms": outcome.duration_ms,
                                              "source": outcome.source, "summary": outcome.summary})
                    if outcome.ok and outcome.source not in result.sources:
                        result.sources.append(outcome.source)
                    if outcome.ok and tool is not None and tool.creates_draft:
                        result.draft = outcome.payload
                        self.trace.publish("work_order_draft", work_order=outcome.payload, **ids)
                    payload = outcome.payload
                content = json.dumps(payload, ensure_ascii=False)
                known.update(_REFS.findall(content))
                known_dates.update(_known_dates(content))
                messages.append({"role": "tool", "tool_call_id": call.call_id, "content": content[:6000]})
                self._last_tool_messages.append({"role": "tool", "tool_call_id": call.call_id, "content": content[:_HISTORY_TOOL_CHARS]})
        else:
            result.answer, result.status = MSG_LIMIT, "limit_reached"
        self._set_state("ANSWERING", **ids)
        result.timings_ms.update(llm=llm_ms, tools=tools_ms)
        return result


def _safe_args(raw: str) -> object:
    try:
        return json.loads(raw) if raw and raw.strip() else {}
    except ValueError:
        return {"_raw": raw[:200]}
