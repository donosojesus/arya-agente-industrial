# A · Mapa de archivos y comandos

## Dónde está cada cosa

| Carpeta o archivo | Qué contiene |
|---|---|
| `src/arya_plant/` | Simulador, alarmas, escenarios, servidor OPC UA y API de control |
| `src/arya_otclient/` | Cliente OPC UA compartido: lectura coherente del lote |
| `src/arya_ot_gateway/` | Gateway: historian, análisis, historial de 6 meses y medallón (`condition.py`) |
| `src/arya_cmms/` | CMMS: órdenes, aprobación humana y calendario de paradas |
| `src/arya_agent/` | El agente: `agent.py` (ciclo y guardrails), `llm.py` (modelo), `tools.py` (herramientas), `memory.py`, `documents.py`, `textsearch.py`, `trace.py`, `api.py` |
| `src/arya_ui/` | La pantalla de la demo y la ventana de la AI Factory |
| `src/arya_plant_view/` | La pantalla de operación de la planta |
| `tutorial/` | Los programas del tutorial de la Parte II y el servidor de guion |
| `data/documents/` | Los 10 documentos de la planta |
| `data/work-orders/seed.json` | Las órdenes históricas |
| `tests/` | Las 106 pruebas, incluidas las del tutorial (`test_tutorial.py`) |
| `scripts/` | Arranque, chequeo, fallas, reinicio, ensayos y actualización sin Internet |
| `docs/` | Arquitectura, validación y este libro |

## Comandos

| Comando | Qué hace |
|---|---|
| `./arya.sh` | Levanta todo y abre la pantalla |
| `./arya.sh status` / `down` | Estado / apagar |
| `./scripts/reset-demo.sh` | Todo a cero |
| `./scripts/inject-fault.sh [escenario]` | Simula una falla; el escenario puede ser `alpha`, `bravo` o `charlie` |
| `./scripts/normal-operation.sh` | Vuelve a normal |
| `./scripts/rehearse-agent.sh [opción]` | Ensayo con el modelo real; opciones: `--normal`, `--reglas` o `--predictivo` |
| `./scripts/preflight.sh` | Chequeo previo |
| `./scripts/update-offline.sh <servicio…>` | Actualiza el código sin Internet |
| `~/.venvs/arya-industrial-demo/bin/python -m pytest -q` | Corre las 106 pruebas |
| `~/.venvs/arya-industrial-demo/bin/python tutorial/modelo_guion.py` | Servidor de guion para el tutorial, sin GB10 |
| `~/.venvs/arya-industrial-demo/bin/python tutorial/paso0_entorno.py` | Comprueba el entorno del tutorial (paso 0) |
| `~/.venvs/arya-industrial-demo/bin/python docs/libro/build.py` | Regenera este libro |

## Parámetros del agente

Cada parámetro se lee de la variable de entorno que aparece en `from_env`. Cómo cambiarlos: capítulo 20.

@@code src/arya_agent/config.py AgentSettings
