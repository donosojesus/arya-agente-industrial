"""Paso 1: hablar con el modelo. Una pregunta y una respuesta, sin herramientas.

El modelo solo ve los mensajes que le enviamos: todavía no puede consultar la planta.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE_URL = os.environ.get("NEMOTRON_BASE_URL", "http://127.0.0.1:8099/v1")
MODELO = os.environ.get("NEMOTRON_MODEL", "modelo-de-guion")
API_KEY = os.environ.get("NEMOTRON_API_KEY", "")

INSTRUCCIONES = "Eres ARYA, un asistente para la operación de la bomba P-101. Responde en español, en dos o tres frases."


def preguntar(mensajes: list[dict]) -> dict:
    """Envía la conversación completa al modelo y devuelve su respuesta tal como llega (JSON)."""
    cuerpo = {
        "model": MODELO,
        "messages": mensajes,
        "temperature": 0.2,  # poca variación: queremos datos, no creatividad
        "max_tokens": 300,  # tope de la respuesta, en tokens
        "chat_template_kwargs": {"enable_thinking": False},  # Nemotron: sin razonar antes (si tu servidor rechaza el campo, quítalo)
    }
    cabeceras = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    respuesta = httpx.post(f"{BASE_URL}/chat/completions", json=cuerpo, headers=cabeceras, timeout=60)
    respuesta.raise_for_status()
    return respuesta.json()


def main(pregunta: str) -> None:
    mensajes = [
        {"role": "system", "content": INSTRUCCIONES},  # las reglas fijas: van primero, en cada llamada
        {"role": "user", "content": pregunta},  # lo que pregunta el operador
    ]
    inicio = time.monotonic()
    datos = preguntar(mensajes)
    segundos = time.monotonic() - inicio
    uso = datos.get("usage") or {}
    print("ARYA:", datos["choices"][0]["message"]["content"])
    print(f"tiempo: {segundos:.1f} s · tokens de entrada: {uso.get('prompt_tokens', 'n/d')} · tokens de salida: {uso.get('completion_tokens', 'n/d')}")


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "¿Qué temperatura tiene ahora el motor de la P-101?")
