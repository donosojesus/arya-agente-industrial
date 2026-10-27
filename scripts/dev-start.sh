#!/usr/bin/env bash
# RESPALDO SIN DOCKER (WSL/Linux): arranca plant y plant-view como procesos locales.
# Requiere un Python 3.12 con requirements/dev.lock instalado (ver README, "Desarrollo y pruebas").
source "$(dirname "$0")/_common.sh"

ensure_env

PY="${ARYA_PYTHON:-}"
for candidate in "$ARYA_ROOT/.venv/bin/python" "$HOME/.venvs/arya-industrial-demo/bin/python"; do
  [ -z "$PY" ] && [ -x "$candidate" ] && PY="$candidate"
done
if [ -z "$PY" ]; then echo "No se encontro el entorno Python. Vea README, 'Desarrollo y pruebas'." >&2; exit 1; fi

RUN_DIR="${ARYA_RUN_DIR:-$HOME/.cache/arya-industrial-demo}"
mkdir -p "$RUN_DIR"
for name in plant plant-view ot-gateway cmms agent demo-ui; do
  if [ -f "$RUN_DIR/$name.pid" ] && kill -0 "$(cat "$RUN_DIR/$name.pid")" 2>/dev/null; then
    echo "$name ya esta en marcha (pid $(cat "$RUN_DIR/$name.pid")). Use ./scripts/dev-stop.sh primero." >&2; exit 1
  fi
done

opc_port="$(env_get OPCUA_PORT 4840)"; control_port="$(env_get CONTROL_PORT 9001)"; scada_port="$(env_get SCADA_PORT 8080)"
export PYTHONPATH="$ARYA_ROOT/src" PYTHONUNBUFFERED=1

DEMO_CONTROL_TOKEN="$(env_get DEMO_CONTROL_TOKEN)" \
OPCUA_ENDPOINT="opc.tcp://127.0.0.1:${opc_port}/arya/plant/" CONTROL_HOST=127.0.0.1 CONTROL_PORT="$control_port" \
CONTROL_ALLOWED_ORIGINS="http://127.0.0.1:${scada_port},http://localhost:${scada_port}" \
FAULT_DURATION_SECONDS="$(env_get FAULT_DURATION_SECONDS 180)" RECOVERY_SECONDS="$(env_get RECOVERY_SECONDS 90)" \
TICK_SECONDS="$(env_get TICK_SECONDS 0.5)" \
  nohup "$PY" -m arya_plant > "$RUN_DIR/plant.log" 2>&1 &
echo $! > "$RUN_DIR/plant.pid"

OPCUA_ENDPOINT="opc.tcp://127.0.0.1:${opc_port}/arya/plant/" VIEW_HOST=127.0.0.1 VIEW_PORT="$scada_port" \
SAMPLE_SECONDS="$(env_get SAMPLE_SECONDS 1)" STALE_AFTER_SECONDS="$(env_get STALE_AFTER_SECONDS 5)" \
CONTROL_PUBLIC_PORT="$control_port" \
  nohup "$PY" -m arya_plant_view > "$RUN_DIR/plant-view.log" 2>&1 &
echo $! > "$RUN_DIR/plant-view.pid"

OPCUA_ENDPOINT="opc.tcp://127.0.0.1:${opc_port}/arya/plant/" GATEWAY_HOST=127.0.0.1 GATEWAY_PORT="$(env_get GATEWAY_PORT 8081)" \
HISTORIAN_PATH="$RUN_DIR/historian.sqlite3" SAMPLE_SECONDS="$(env_get SAMPLE_SECONDS 1)" STALE_AFTER_SECONDS="$(env_get STALE_AFTER_SECONDS 5)" \
  nohup "$PY" -m arya_ot_gateway > "$RUN_DIR/ot-gateway.log" 2>&1 &
echo $! > "$RUN_DIR/ot-gateway.pid"

CMMS_HOST=127.0.0.1 CMMS_PORT="$(env_get CMMS_PORT 8082)" CMMS_DB_PATH="$RUN_DIR/cmms.sqlite3" \
CMMS_SEED_PATH="$ARYA_ROOT/data/work-orders/seed.json" CMMS_AGENT_KEY="$(env_get CMMS_AGENT_KEY)" \
CMMS_APPROVER_TOKEN="$(env_get CMMS_APPROVER_TOKEN)" CMMS_ALLOWED_ORIGINS="http://127.0.0.1:${scada_port},http://localhost:${scada_port}" \
  nohup "$PY" -m arya_cmms > "$RUN_DIR/cmms.log" 2>&1 &
echo $! > "$RUN_DIR/cmms.pid"

AGENT_HOST=127.0.0.1 AGENT_PORT="$(env_get AGENT_PORT 8091)" AGENT_NODE_LABEL="$(env_get AGENT_NODE_LABEL 'Notebook (desarrollo)')" \
NEMOTRON_BASE_URL="$(env_get NEMOTRON_BASE_URL)" NEMOTRON_MODEL="$(env_get NEMOTRON_MODEL)" NEMOTRON_API_KEY="$(env_get NEMOTRON_API_KEY)" \
GATEWAY_URL="$(gateway_url)" CMMS_URL="$(cmms_url)" CMMS_AGENT_KEY="$(env_get CMMS_AGENT_KEY)" AGENT_ADMIN_TOKEN="$(env_get AGENT_ADMIN_TOKEN)" \
AGENT_DATA_DIR="$RUN_DIR/agent" DOCUMENTS_DIR="$ARYA_ROOT/data/documents" AGENT_PROACTIVE="$(env_get AGENT_PROACTIVE off)" \
  nohup "$PY" -m arya_agent > "$RUN_DIR/agent.log" 2>&1 &
echo $! > "$RUN_DIR/agent.pid"

UI_HOST=127.0.0.1 UI_PORT="$(env_get UI_PORT 8090)" AGENT_URL="$(agent_url)" CMMS_URL="$(cmms_url)" CONTROL_URL="$(control_url)" DEMO_CONTROL_TOKEN="$(env_get DEMO_CONTROL_TOKEN)" PLANT_VIEW_PUBLIC_PORT="$scada_port" \
  nohup "$PY" -m arya_ui > "$RUN_DIR/demo-ui.log" 2>&1 &
echo $! > "$RUN_DIR/demo-ui.pid"

for _ in $(seq 1 40); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$(scada_url)/healthz" || true)" = "200" ] && [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$(gateway_url)/healthz" || true)" = "200" ] && [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$(cmms_url)/healthz" || true)" = "200" ]; then
    echo "Planta en marcha SIN Docker (modo respaldo)."
    echo "  DEMO:       $(demo_url)   (pantalla dividida: ./scripts/open-demo.sh)"
    echo "  SCADA:      $(scada_url)   (con controles: ./scripts/open-scada.sh)"
    echo "  Verificar:  ./scripts/dev-preflight.sh     Detener: ./scripts/dev-stop.sh"
    echo "  Logs:       $RUN_DIR"
    exit 0
  fi
  sleep 0.5
done
echo "La planta no quedo sana en 20 s. Revise los logs en $RUN_DIR" >&2
exit 1
