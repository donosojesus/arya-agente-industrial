"""Paso 2: la primera herramienta.

El modelo no puede leer la planta, pero puede pedir que alguien la lea por él. Este
programa le ofrece una herramienta, ejecuta lo que pide y le devuelve el resultado.
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

INSTRUCCIONES = ("Eres ARYA, un asistente para la operación de la bomba P-101. Responde en español, en dos o tres frases. "
                 "Usa las herramientas para obtener datos reales; no inventes valores.")

# La herramienta, descrita para el modelo: nombre, para qué sirve y qué argumentos acepta (ninguno).
HERRAMIENTAS = [{
    "type": "function",
    "function": {
        "name": "get_active_alarms",
        "description": "Alarmas activas de la bomba P-101, con su valor, su límite y desde cuándo.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}]


def get_active_alarms() -> dict:
    """La herramienta en sí: una lectura GET al gateway. No escribe nada en ninguna parte."""
    respuesta = httpx.get(f"{GATEWAY}/api/v1/assets/P-101/alarms", timeout=8)
    respuesta.raise_for_status()
    return respuesta.json()


def preguntar(mensajes: list[dict], herramientas: list[dict] | None = None) -> dict:
    """Igual que en el paso 1, pero ahora puede ofrecer herramientas."""
    cuerpo = {"model": MODELO, "messages": mensajes, "temperature": 0.2, "max_tokens": 300,
              "chat_template_kwargs": {"enable_thinking": False}}
    if herramientas:
        cuerpo["tools"] = herramientas
    cabeceras = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    respuesta = httpx.post(f"{BASE_URL}/chat/completions", json=cuerpo, headers=cabeceras, timeout=60)
    respuesta.raise_for_status()
    return respuesta.json()


def main(pregunta: str) -> None:
    mensajes = [{"role": "system", "content": INSTRUCCIONES}, {"role": "user", "content": pregunta}]

    # 1. Primera llamada: el modelo ve la pregunta y la herramienta, y decide.
    mensaje = preguntar(mensajes, HERRAMIENTAS)["choices"][0]["message"]
    llamadas = mensaje.get("tool_calls") or []
    if not llamadas:
        print("ARYA (sin consultar nada):", mensaje["content"])
        return

    # 2. El pedido del modelo queda en la conversación, y el programa lo ejecuta.
    mensajes.append({"role": "assistant", "content": mensaje.get("content") or "", "tool_calls": llamadas})
    for llamada in llamadas:
        nombre = llamada["function"]["name"]
        print(f"→ el modelo pide: {nombre}({llamada['function']['arguments']})")
        resultado = get_active_alarms() if nombre == "get_active_alarms" else {"error": f"La herramienta {nombre} no existe."}
        texto = json.dumps(resultado, ensure_ascii=False)
        print(f"← el programa responde con {len(texto)} caracteres de datos reales")
        mensajes.append({"role": "tool", "tool_call_id": llamada["id"], "content": texto})

    # 3. Segunda llamada: con el dato a la vista, el modelo redacta la respuesta.
    final = preguntar(mensajes, HERRAMIENTAS)["choices"][0]["message"]
    print("ARYA:", final["content"])


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "¿Hay alarmas activas en la P-101?")
