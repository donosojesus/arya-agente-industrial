"""Adaptador del modelo de lenguaje.

`OpenAICompatModel` habla el protocolo "chat completions" con llamadas a
herramientas. Confirmado el 19 de octubre contra el NIM de la GB10
(nvidia/nemotron-3-nano, puerto 30081): devuelve `tool_calls` nativos y el
razonamiento en un campo aparte (`reasoning_content`), que aqui se descarta.
El razonamiento se puede apagar con `chat_template_kwargs.enable_thinking`:
con el apagado cada paso tarda menos de un segundo; encendido, unos 15 s.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx


class LlmError(Exception):
    """El modelo no esta disponible o respondio algo inutilizable."""


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: str  # JSON tal como lo entrego el modelo


@dataclass
class ModelTurn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    ttft_ms: int | None = None  # tiempo hasta el primer token (solo con streaming)
    tpot_ms: float | None = None  # tiempo por token de salida despues del primero (solo con streaming)


class ChatModel(Protocol):
    name: str

    async def complete(self, messages: list[dict[str, object]], tools: list[dict[str, object]] | None,
                       tool_choice: object = None) -> ModelTurn: ...

    async def health(self) -> dict[str, object]: ...


class OpenAICompatModel:
    def __init__(self, base_url: str, model: str, api_key: str = "", timeout_s: float = 45.0,
                 temperature: float = 0.2, max_tokens: int = 700, client: httpx.AsyncClient | None = None,
                 thinking: bool | None = None, stream: bool = False) -> None:
        self.base_url, self.name = base_url.rstrip("/"), model
        self._stream = stream
        self.stream_fallbacks = 0
        self._temperature, self._max_tokens = temperature, max_tokens
        self._thinking = thinking  # None: no se envia el parametro
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout_s, connect=5.0), headers=headers)

    async def complete(self, messages, tools, tool_choice=None, thinking=None):
        # Con una herramienta exigida ("required" o una funcion por nombre), el servidor del modelo (vLLM/NIM) entrega en
        # streaming los argumentos vacios (p. ej. {"query": ""}); esas llamadas van en el modo normal. Los pasos libres,
        # que redactan la respuesta, siguen en streaming y miden TTFT/TPOT.
        forced = bool(tools) and tool_choice not in (None, "auto", "none")
        if self._stream and not forced:
            try:
                return await self._complete_stream(messages, tools, tool_choice, thinking)
            except LlmError:
                raise
            except Exception:
                # Cualquier problema con el streaming: se repite la peticion en el modo normal (sin TTFT/TPOT).
                self.stream_fallbacks += 1
        return await self._complete_plain(messages, tools, tool_choice, thinking)

    def _payload(self, messages, tools, tool_choice, thinking) -> dict[str, object]:
        payload: dict[str, object] = {"model": self.name, "messages": messages, "temperature": self._temperature,
                                      "max_tokens": self._max_tokens, "stream": False}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        think = self._thinking if thinking is None else thinking
        if think is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": think}
            if think:
                payload["max_tokens"] = max(self._max_tokens, 3000)
        return payload

    async def _complete_stream(self, messages, tools, tool_choice, thinking) -> ModelTurn:
        payload = self._payload(messages, tools, tool_choice, thinking)
        payload.update(stream=True, stream_options={"include_usage": True})
        started = time.monotonic()
        first = None
        content: list[str] = []
        calls: dict[int, dict[str, str]] = {}
        usage: dict[str, object] = {}
        try:
            async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", "replace")
                    if response.status_code == 400 and "json_invalid" in body:
                        raise ValueError("json_invalid")  # se reintenta en el modo normal, que tiene su propio reintento
                    raise LlmError(f"el modelo respondio HTTP {response.status_code}: {body[:200]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            first = first or time.monotonic()
                            content.append(delta["content"])
                        for tc in delta.get("tool_calls") or []:
                            first = first or time.monotonic()
                            slot = calls.setdefault(int(tc.get("index", 0)), {"id": "", "name": "", "arguments": ""})
                            slot["id"] = tc.get("id") or slot["id"]
                            fn = tc.get("function") or {}
                            slot["name"] += fn.get("name") or ""
                            slot["arguments"] += fn.get("arguments") or ""
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError, httpx.WriteError) as exc:
            raise RuntimeError(type(exc).__name__) from exc  # el modo normal reintenta
        except httpx.HTTPError as exc:
            raise LlmError(f"no se pudo contactar el modelo: {type(exc).__name__}") from exc
        ended = time.monotonic()
        tool_calls = [ToolCall(c["id"] or f"call_{i}", c["name"], c["arguments"] or "{}") for i, c in sorted(calls.items())]
        if first is None and not tool_calls and not content:
            raise ValueError("respuesta vacia en streaming")
        completion = usage.get("completion_tokens")
        ttft = int(((first or ended) - started) * 1000)
        tpot = round((ended - first) * 1000 / (completion - 1), 1) if first and completion and completion > 1 else None
        return ModelTurn("".join(content), tool_calls, int((ended - started) * 1000), usage.get("prompt_tokens"), completion, ttft, tpot)

    async def _complete_plain(self, messages, tools, tool_choice, thinking) -> ModelTurn:
        payload: dict[str, object] = {"model": self.name, "messages": messages, "temperature": self._temperature,
                                      "max_tokens": self._max_tokens, "stream": False}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
            if tool_choice not in (None, "auto", "none"):
                # Una herramienta exigida (p. ej. el borrador de orden) puede llevar argumentos largos: con poco margen
                # el JSON queda cortado y el servidor responde HTTP 400 "Invalid JSON: EOF while parsing".
                payload["max_tokens"] = max(self._max_tokens, 1600)
        think = self._thinking if thinking is None else thinking
        if think is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": think}
            if think:
                payload["max_tokens"] = max(self._max_tokens, 3000)  # el razonamiento consume tokens antes de responder
        started = time.monotonic()
        response = None
        for attempt in (1, 2):
            try:
                response = await self._client.post(f"{self.base_url}/chat/completions", json=payload)
            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError, httpx.WriteError) as exc:
                # Corte de conexion (p. ej. el servidor cerro una conexion reutilizada): un reintento.
                if attempt == 2:
                    raise LlmError(f"no se pudo contactar el modelo: {type(exc).__name__}") from exc
                await asyncio.sleep(0.5)
                continue
            except httpx.HTTPError as exc:  # tiempo de espera agotado u otros: sin reintento, para no duplicar la espera
                raise LlmError(f"no se pudo contactar el modelo: {type(exc).__name__}") from exc
            if response.status_code == 400 and ("json_invalid" in response.text or "Invalid JSON" in response.text) and attempt == 1:
                # El modelo escribio mal el JSON de una herramienta y el servidor lo rechazo: se pide de nuevo.
                response = None
                continue
            break
        if response is None:
            raise LlmError("el modelo devolvio dos veces una llamada a herramienta mal formada")
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            raise LlmError(f"el modelo respondio HTTP {response.status_code}: {response.text[:200]}")
        try:
            body = response.json()
            message = body["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmError("respuesta del modelo con formato inesperado") from exc
        calls = []
        for i, call in enumerate(message.get("tool_calls") or []):
            fn = call.get("function") or {}
            args = fn.get("arguments")
            calls.append(ToolCall(call.get("id") or f"call_{i}", str(fn.get("name", "")),
                                  args if isinstance(args, str) else json.dumps(args or {})))
        usage = body.get("usage") or {}
        return ModelTurn(message.get("content") or "", calls, latency, usage.get("prompt_tokens"), usage.get("completion_tokens"))

    async def health(self):
        started = time.monotonic()
        context = None
        try:
            response = await self._client.get(f"{self.base_url}/models", timeout=4.0)
            ok = response.status_code == 200
            detail = None if ok else f"HTTP {response.status_code}"
            if ok:
                try:
                    match = [m for m in response.json().get("data", []) if m.get("id") == self.name]
                    context = match[0].get("max_model_len") if match else None
                except (ValueError, AttributeError, TypeError):
                    context = None
        except httpx.HTTPError as exc:
            ok, detail = False, type(exc).__name__
        return {"configured": True, "reachable": ok, "model": self.name, "detail": detail, "context_limit": context,
                "latency_ms": int((time.monotonic() - started) * 1000)}

    async def aclose(self) -> None:
        await self._client.aclose()


class NoModel:
    """Sin modelo configurado: el agente lo informa; nunca improvisa respuestas."""

    name = ""

    async def complete(self, messages, tools, tool_choice=None, thinking=None):
        raise LlmError("no hay un modelo de lenguaje configurado (NEMOTRON_BASE_URL vacio)")

    async def health(self):
        return {"configured": False, "reachable": False, "model": None, "detail": "NEMOTRON_BASE_URL no configurado"}
