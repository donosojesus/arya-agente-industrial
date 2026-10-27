# 14 · Paso 8 · La traza

Un agente que no se puede observar no se puede mejorar, ni explicar a un cliente. ARYA publica cada paso en una traza.

## La traza

Cada evento recibe un número de secuencia y su hora. Se guarda en memoria (los últimos 2 000), en un archivo en disco y se reparte a las pantallas conectadas. Una pantalla demasiado lenta se desconecta, en vez de frenar al agente:

@@code src/arya_agent/trace.py TraceHub.publish

Cada evento lleva su tipo, su hora y los datos del paso:

| Evento | Cuándo | Qué incluye |
|---|---|---|
| `user_message` | Llega una pregunta | El texto |
| `state` | Cambia el estado | LISTA, PENSANDO, USANDO HERRAMIENTA, RESPONDIENDO (en el código: `IDLE`, `THINKING`, `USING_TOOL`, `ANSWERING`) |
| `llm_call` | Responde el modelo | Paso, latencia, tokens de entrada y salida, TTFT, TPOT, herramientas pedidas |
| `tool_start` / `tool_end` | Se ejecuta una herramienta | Argumentos, fuente, resumen, duración, si funcionó |
| `guardrail` | Se activa una regla | Cuál y por qué |
| `assistant_message` | Sale la respuesta | Texto, fuentes, tiempos y tokens |

La traza nunca incluye el razonamiento interno del modelo: se elimina antes de publicarla.

## Tres formas de verla

1. **"Inside the agent"**: la tabla bajo la planta en la pantalla de la demo, en vivo por SSE (*server-sent events*).
2. **"Por dentro"**: un tablero que enciende cada componente del agente (modelo, prompt, contexto, memoria, RAG, herramientas, guardrails) a medida que se usa, con la franja de tokens, TTFT y TPOT.
3. **Un registro JSONL** en disco, para revisar después.

@@img docs/img/por-dentro-prueba-de-diseno.png El tablero "Por dentro": cada bloque se enciende cuando el agente lo usa. Es una prueba de diseño hecha con el modelo de guion de las pruebas, no con Nemotron (por eso dice «scripted-test-model»): las herramientas, las fuentes y los tiempos son reales; el texto de la respuesta, no.

## Los tokens

El agente cuenta los tokens de cada respuesta, de la conversación y del total. Esa cifra conecta con el dimensionamiento: una pregunta de diagnóstico típica usa entre 4 000 y 10 000 tokens de entrada y unos 150 a 230 de salida. Con eso, la calculadora de la AI Factory estima cuántas GPU harían falta para N agentes en M plantas.
