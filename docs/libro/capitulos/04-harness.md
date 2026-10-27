# 4 · El harness

El modelo de lenguaje es una pieza del agente, no el agente. Todo lo que lo rodea, y que lo convierte en algo útil y seguro, se llama **harness** (en español, arnés). En ARYA, el harness son unas 1 500 líneas de Python, y el modelo se usa tal cual, sin modificarlo.

@@img docs/img/libro/harness.svg Modelo + harness = agente. Cada pieza del harness tiene su capítulo en la Parte II.

## Las piezas, una por una

| Pieza | Qué hace | Sin ella | Capítulo |
|---|---|---|---|
| Prompt de sistema | Le da al modelo su rol, sus reglas y una guía de qué herramienta usar | El modelo no sabe qué se espera de él | 11 |
| Herramientas | Funciones que el modelo puede pedir, con argumentos validados | El modelo solo puede conversar | 8 y 10 |
| Ciclo con límites | Repite consultar y observar hasta responder, con topes | Una pregunta podría no terminar nunca | 9 |
| Guardrails | Reglas que el código hace cumplir aunque el modelo no obedezca | Todo depende de que el modelo siga las instrucciones | 12 |
| Memoria y RAG | Conversación reciente, incidentes anteriores y manuales, con su cita | Cada pregunta empieza de cero, sin documentos | 13 |
| Traza | Registra cada paso: herramienta, fuente, tiempo y tokens | Nadie puede auditar ni depurar el agente | 14 |
| Aprobación humana | Separa crear un borrador de aprobarlo | El agente decidiría solo | 15 |
| Aviso automático | Interviene cuando se activa una alarma | El agente solo habla si le preguntan | 16 |

Ninguna de estas piezas es inteligencia artificial: es programación corriente. Esa es la idea central de este libro: **lo que hace confiable a un agente es el harness, y el harness se puede leer, probar y auditar como cualquier otro programa.**

@@img docs/img/anatomia-arya.png La anatomía de ARYA, tal como se presenta en la demo: el modelo, sus piezas y el ciclo. MCP aparece marcado como no implementado. La figura es del 20 de octubre: hoy son 14 herramientas, y el prompt tiene 4 reglas numeradas (capítulo 11).

## Por qué un harness propio y no un framework

Existen frameworks que resuelven el ciclo del agente, como LangChain, CrewAI o AutoGen. ARYA no usa ninguno, por tres razones:

1. **Funcionar sin Internet y con pocas dependencias.** El sistema completo depende de seis librerías conocidas: FastAPI, uvicorn, httpx, asyncua, Pydantic y pytest.
2. **Que cada decisión sea visible y auditable.** Con ≈ 1 500 líneas propias, se puede leer todo el agente en una tarde.
3. **Que los límites estén donde uno los ve.** Cuántos pasos, cuántas herramientas, cuánto tiempo y qué pasa si algo falla están en un solo archivo de configuración.

La contrapartida es que algunas cosas que un framework trae resueltas hubo que escribirlas, y probarlas. El capítulo 21 explica cómo.

## Del tutorial a ARYA

La Parte II construye el harness en el mismo orden de la tabla. Los primeros pasos usan programas cortos de la carpeta `tutorial/`, que se ejecutan contra la planta real; después, cada capítulo muestra cómo resuelve ARYA esa pieza en su código.

| Programa del tutorial | Paso | Qué agrega | Dónde está en ARYA |
|---|---|---|---|
| `paso0_entorno.py` | 0 | Comprobar que la planta, el gateway y el modelo responden | `scripts/preflight.sh` |
| `paso1_hablar.py` | 1 | Hablar con el modelo | `src/arya_agent/llm.py` |
| `paso2_herramienta.py` | 2 | Una herramienta, de ida y vuelta | `src/arya_agent/tools.py` |
| `paso3_ciclo.py` | 3 | El ciclo con sus límites | `src/arya_agent/agent.py` |
| `modelo_guion.py` | — | Imitar al modelo para practicar sin hardware | `tests/conftest.py` (`ScriptedModel`) |
