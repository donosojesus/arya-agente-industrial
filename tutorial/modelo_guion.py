"""Servidor de guion: imita la API de un modelo de lenguaje sin ser un modelo.

Sirve para seguir el tutorial sin una GB10 ni ningún modelo instalado. No razona:
aplica tres reglas fijas, siempre en este orden, y marca sus textos con [guion]
para que nadie los confunda con una respuesta real.

  1. Si le ofrecen get_active_alarms y todavía no la pidió, la pide.
  2. Si le ofrecen get_historian_data y todavía no la pidió, la pide.
  3. Si no, responde con un texto que dice qué consultó.

Uso:  python tutorial/modelo_guion.py      (escucha en http://127.0.0.1:8099/v1)
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PUERTO = int(os.environ.get("GUION_PORT", "8099"))
GUION = (("get_active_alarms", {}), ("get_historian_data", {"signals": ["vibration", "motor_temp"], "minutes": 10}))


def responder(cuerpo: dict) -> dict:
    """Elige la respuesta según las reglas del guion: pedir una herramienta o responder con texto."""
    ofrecidas = [h["function"]["name"] for h in cuerpo.get("tools") or []]
    pedidas = [ll["function"]["name"] for m in cuerpo["messages"] if m["role"] == "assistant" for ll in m.get("tool_calls") or []]
    for nombre, argumentos in GUION:
        if nombre in ofrecidas and nombre not in pedidas:
            llamada = {"id": f"call_{len(pedidas) + 1}", "type": "function",
                       "function": {"name": nombre, "arguments": json.dumps(argumentos)}}
            return {"role": "assistant", "content": None, "tool_calls": [llamada]}
    if pedidas:
        texto = f"[guion] Consulté {', '.join(pedidas)}. Un modelo real redactaría aquí la respuesta con esos datos."
    else:
        texto = "[guion] No soy un modelo: no conozco la planta ni puedo consultarla. Un modelo real respondería con lo que aprendió al entrenarse."
    return {"role": "assistant", "content": texto}


class Manejador(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/v1/models":
            self._json({"object": "list", "data": [{"id": "modelo-de-guion", "object": "model"}]})
        else:
            self._json({"error": "ruta desconocida"}, 404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json({"error": "ruta desconocida"}, 404)
            return
        cuerpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        mensaje = responder(cuerpo)
        fin = "tool_calls" if mensaje.get("tool_calls") else "stop"
        self._json({"object": "chat.completion", "model": cuerpo.get("model", "modelo-de-guion"),
                    "choices": [{"index": 0, "message": mensaje, "finish_reason": fin}]})

    def _json(self, datos: dict, estado: int = 200) -> None:
        crudo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def log_message(self, *args) -> None:  # silencio: los pasos del tutorial imprimen lo importante
        pass


if __name__ == "__main__":
    print(f"Servidor de guion en http://127.0.0.1:{PUERTO}/v1  (Ctrl+C para detenerlo)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador).serve_forever()
