"""Paso 0: comprobar que todo está funcionando antes de escribir el agente.

Revisa tres cosas: el gateway (la única puerta de lectura a la planta), una lectura
real de la bomba y el servidor del modelo (Nemotron o el servidor de guion).
"""

from __future__ import annotations

import os

import httpx

GATEWAY = os.environ.get("GATEWAY_URL", "http://127.0.0.1:8081")
MODELO = os.environ.get("NEMOTRON_BASE_URL", "http://127.0.0.1:8099/v1")
API_KEY = os.environ.get("NEMOTRON_API_KEY", "")


def revisar(nombre: str, prueba) -> bool:
    """Ejecuta una prueba e informa el resultado. Una falla no detiene las demás."""
    try:
        print(f"[ OK ] {nombre}: {prueba()}")
        return True
    except Exception as exc:
        print(f"[FALLA] {nombre}: {type(exc).__name__}: {exc}")
        return False


def gateway_sano() -> str:
    respuesta = httpx.get(f"{GATEWAY}/healthz", timeout=5)
    respuesta.raise_for_status()
    return f"conexión OPC UA {respuesta.json()['opcua_connection']}"


def lectura_de_la_bomba() -> str:
    respuesta = httpx.get(f"{GATEWAY}/api/v1/assets/P-101/tags", timeout=5)
    respuesta.raise_for_status()
    tags = respuesta.json()["tags"]
    vib, temp = tags["P101.VIBRATION"], tags["P101.MOTOR_TEMP"]
    return f"vibración {vib['value']:.2f} {vib['unit']}, temperatura del motor {temp['value']:.1f} {temp['unit']}"


def modelo_disponible() -> str:
    cabeceras = {"Authorization": f"Bearer {API_KEY}"} if API_KEY else {}
    respuesta = httpx.get(f"{MODELO}/models", headers=cabeceras, timeout=5)
    respuesta.raise_for_status()
    return "modelos: " + ", ".join(m["id"] for m in respuesta.json()["data"])


if __name__ == "__main__":
    resultados = [revisar("Gateway", gateway_sano), revisar("Lectura de la bomba", lectura_de_la_bomba),
                  revisar("Modelo", modelo_disponible)]
    print("Todo listo para el paso 1." if all(resultados) else "Corrige lo que falló antes de seguir.")
