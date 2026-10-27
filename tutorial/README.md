# Tutorial: ARYA mínima, paso a paso

Programas cortos que acompañan la Parte II del libro "ARYA, de cero a agente" (`docs/libro/`). Cada uno agrega una sola pieza al anterior y se ejecuta contra la planta real, a través del gateway.

| Archivo | Paso | Qué hace |
|---|---|---|
| `paso0_entorno.py` | 0 | Comprueba el gateway, una lectura de la bomba y el modelo |
| `paso1_hablar.py` | 1 | Una pregunta al modelo, sin herramientas |
| `paso2_herramienta.py` | 2 | Una herramienta, de ida y vuelta |
| `paso3_ciclo.py` | 3 | El ciclo del agente con sus límites |
| `modelo_guion.py` | — | Servidor que imita la API del modelo con reglas fijas, para practicar sin GB10 |

Uso, desde la carpeta del proyecto y con la demo levantada (`./arya.sh`):

```bash
~/.venvs/arya-industrial-demo/bin/python tutorial/modelo_guion.py      # en otra terminal, si no hay GB10
~/.venvs/arya-industrial-demo/bin/python tutorial/paso0_entorno.py
```

Con Nemotron, exporta `NEMOTRON_BASE_URL`, `NEMOTRON_MODEL` y `NEMOTRON_API_KEY` (por ejemplo `set -a; . ./.env; set +a`). Sin ellas, los programas usan el servidor de guion en `127.0.0.1:8099`.

Las pruebas de `tests/test_tutorial.py` ejecutan cada paso contra una planta real, un gateway y el servidor de guion.
