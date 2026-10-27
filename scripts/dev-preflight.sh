#!/usr/bin/env bash
# Preflight del modo respaldo sin Docker: mismas verificaciones OPC UA/HTTP, sin contenedores.
source "$(dirname "$0")/_common.sh"
require_env
PY="${ARYA_PYTHON:-}"
for candidate in "$ARYA_ROOT/.venv/bin/python" "$HOME/.venvs/arya-industrial-demo/bin/python"; do
  [ -z "$PY" ] && [ -x "$candidate" ] && PY="$candidate"
done
if [ -z "$PY" ]; then echo "No se encontro el entorno Python." >&2; exit 1; fi
echo "(modo respaldo sin Docker: no se verifican contenedores ni healthchecks de Compose)"
PYTHONPATH="$ARYA_ROOT/src" DEMO_CONTROL_TOKEN="$(env_get DEMO_CONTROL_TOKEN)" \
OPCUA_ENDPOINT="opc.tcp://127.0.0.1:$(env_get OPCUA_PORT 4840)/arya/plant/" \
CONTROL_PORT="$(env_get CONTROL_PORT 9001)" PLANT_VIEW_URL="$(scada_url)" \
  "$PY" -m arya_plant.preflight
