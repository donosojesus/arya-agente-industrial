"""Paso 3: el ciclo y sus límites.

Con varias herramientas, el modelo puede necesitar más de una vuelta: consulta, mira
el resultado y decide si consulta otra cosa. El ciclo repite eso hasta que el modelo
responde con texto, o hasta que se alcanza un límite.
"""

from __future__ import annotations

import json
import os
import sys

import httpx

BASE_URL = os.environ.get("NEMOTRON_BASE_URL", "http://127.0.0.1:8099/v1")
MODELO = os.environ.get("NEMOTRON_MODEL", "modelo-de-guion")
API_KEY = os.environ.get("NEMOTRON_API_KEY", "")
GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8081")

MAX_VUELTAS = 6  # llamadas al modelo por pregunta
MAX_HERRAMIENTAS = 8  # herramientas ejecutadas por pregunta
MAX_CARACTERES = 6000  # lo que entra al contexto de cada resultado

INSTRUCCIONES = ("Eres ARYA, un asistente para la operación de la bomba P-101. Responde en español, en dos o tres frases. "
                 "Usa las herramientas para obtener datos reales; no inventes valores.")

SENALES = ["flow", "current", "discharge_pressure", "motor_temp", "vibration", "rpm"]
HERRAMIENTAS = [
    {"type": "function", "function": {
        "name": "get_current_tags",
        "description": "Valores actuales de la P-101: temperatura, vibración, corriente, presión, caudal y rpm.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_active_alarms",
        "description": "Alarmas activas de la bomba P-101, con su valor, su límite y desde cuándo.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "get_historian_data",
        "description": "Historia reciente de una o más señales: valor inicial y final, cambio y cuándo empezó la desviación.",
        "parameters": {"type": "object", "properties": {
            "signals": {"type": "array", "items": {"type": "string", "enum": SENALES}, "description": "Señales a consultar"},
            "minutes": {"type": "number", "minimum": 1, "maximum": 240, "description": "Ventana hacia atrás, en minutos"}},
            "required": ["signals"], "additionalProperties": False}}},
]


def leer(ruta: str, **parametros) -> dict:
    """Todas las herramientas de este paso son lecturas GET al gateway."""
    respuesta = httpx.get(f"{GATEWAY}{ruta}", params=parametros, timeout=8)
    respuesta.raise_for_status()
    return respuesta.json()


def get_current_tags() -> dict:
    return leer("/api/v1/assets/P-101/tags")


def get_active_alarms() -> dict:
    return leer("/api/v1/assets/P-101/alarms")


def get_historian_data(signals: list[str], minutes: float = 30) -> dict:
    datos = leer("/api/v1/assets/P-101/history", signals=",".join(signals), minutes=minutes, max_points=5)
    for resumen in (datos.get("signals") or {}).values():
        resumen.pop("points", None)  # el modelo recibe el resumen, no la serie completa
    return datos


EJECUTORES = {"get_current_tags": get_current_tags, "get_active_alarms": get_active_alarms, "get_historian_data": get_historian_data}


def ejecutar(llamada: dict) -> dict:
    """Ejecuta lo que pidió el modelo. Si algo falla, devuelve el error como dato: el ciclo nunca se cae."""
    nombre = llamada["function"]["name"]
    if nombre not in EJECUTORES:
        return {"error": f"La herramienta {nombre} no existe. Disponibles: {', '.join(EJECUTORES)}."}
    try:
        argumentos = json.loads(llamada["function"]["arguments"] or "{}")
        return EJECUTORES[nombre](**argumentos)
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}


def preguntar(mensajes: list[dict], herramientas: list[dict] | None = None) -> dict:
    cuerpo = {"model": MODELO, "messages": mensajes, "temperature": 0.2, "max_tokens": 300,
              "chat_template_kwargs": {"enable_thinking": False}}
    if herramientas:
        cuerpo["tools"] = herramientas
    cabeceras = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    respuesta = httpx.post(f"{BASE_URL}/chat/completions", json=cuerpo, headers=cabeceras, timeout=60)
    respuesta.raise_for_status()
    return respuesta.json()


def ciclo(pregunta: str) -> tuple[str, list[dict]]:
    """El ciclo del agente: preguntar, ejecutar lo pedido, volver a preguntar. Devuelve la respuesta y la conversación."""
    mensajes = [{"role": "system", "content": INSTRUCCIONES}, {"role": "user", "content": pregunta}]
    usadas = 0
    for vuelta in range(1, MAX_VUELTAS + 1):
        ofrecer = HERRAMIENTAS if usadas < MAX_HERRAMIENTAS else None  # sin presupuesto, solo puede responder
        mensaje = preguntar(mensajes, ofrecer)["choices"][0]["message"]
        llamadas = mensaje.get("tool_calls") or []
        if not llamadas:
            print(f"vuelta {vuelta} · el modelo responde con texto")
            mensajes.append({"role": "assistant", "content": mensaje.get("content") or ""})
            return mensaje.get("content") or "", mensajes
        mensajes.append({"role": "assistant", "content": mensaje.get("content") or "", "tool_calls": llamadas})
        for llamada in llamadas:
            print(f"vuelta {vuelta} · el modelo pide {llamada['function']['name']}({llamada['function']['arguments']})")
            if usadas >= MAX_HERRAMIENTAS:
                resultado = {"error": "Límite de herramientas alcanzado. Responde con lo que ya tienes."}
            else:
                usadas += 1
                resultado = ejecutar(llamada)
            texto = json.dumps(resultado, ensure_ascii=False)[:MAX_CARACTERES]
            print(f"           el programa devuelve {len(texto)} caracteres" + (" (error)" if "error" in resultado else ""))
            mensajes.append({"role": "tool", "tool_call_id": llamada["id"], "content": texto})
    return "Llegué al límite de llamadas al modelo sin terminar el análisis.", mensajes


if __name__ == "__main__":
    respuesta, conversacion = ciclo(" ".join(sys.argv[1:]) or "¿Qué está pasando con la P-101?")
    print("ARYA:", respuesta)
    print(f"mensajes en la conversación: {len(conversacion)}")
