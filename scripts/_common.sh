#!/usr/bin/env bash
# Funciones compartidas por los scripts de ARYA Industrial Demo. No ejecutar directamente.
set -euo pipefail

ARYA_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ARYA_ROOT"
ARYA_ENV_FILE="${ARYA_ENV_FILE:-$ARYA_ROOT/.env}"
ARYA_IMAGES="arya-industrial-demo/plant:0.1.0 arya-industrial-demo/plant-view:0.1.0 arya-industrial-demo/ot-gateway:0.1.0 arya-industrial-demo/cmms:0.1.0 arya-industrial-demo/agent:0.1.0 arya-industrial-demo/demo-ui:0.1.0"
ARYA_SERVICES="plant plant-view ot-gateway cmms agent demo-ui"
ARYA_SECRETS="DEMO_CONTROL_TOKEN CMMS_AGENT_KEY CMMS_APPROVER_TOKEN AGENT_ADMIN_TOKEN"

# Lee una clave de .env sin ejecutar su contenido.
env_get() {
  local key="$1" default="${2:-}" line value=""
  if [ -f "$ARYA_ENV_FILE" ]; then
    line="$(grep -E "^${key}=" "$ARYA_ENV_FILE" | tail -n 1 || true)"
    value="${line#*=}"
    value="${value%$'\r'}"
  fi
  printf '%s' "${value:-$default}"
}

# Crea .env si falta y genera localmente cualquier secreto ausente o sin definir. No los imprime.
ensure_env() {
  local key current token
  if [ ! -f "$ARYA_ENV_FILE" ]; then
    cp .env.example "$ARYA_ENV_FILE"
    chmod 600 "$ARYA_ENV_FILE" 2>/dev/null || true
    echo "Se creo .env (no se sube a Git)."
  fi
  for key in $ARYA_SECRETS; do
    current="$(env_get "$key")"
    case "$current" in ""|replace-*)
      token="$(head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')"
      if grep -q "^${key}=" "$ARYA_ENV_FILE"; then
        sed -i "s|^${key}=.*|${key}=${token}|" "$ARYA_ENV_FILE"
      else
        printf '%s=%s\n' "$key" "$token" >> "$ARYA_ENV_FILE"
      fi
      echo "Secreto $key generado localmente en .env (no se muestra)." ;;
    esac
  done
}

require_env() {
  if [ ! -f "$ARYA_ENV_FILE" ]; then
    echo "No existe .env. Ejecute primero: ./scripts/start-demo.sh --build" >&2
    exit 1
  fi
}

# Usa `docker` si su motor responde; en WSL sin integracion recurre a docker.exe de Docker Desktop.
DOCKER_BIN=""
find_docker() {
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    DOCKER_BIN="docker"
  elif command -v docker.exe >/dev/null 2>&1 && docker.exe info >/dev/null 2>&1; then
    DOCKER_BIN="docker.exe"
  else
    return 1
  fi
}

require_docker() {
  if ! find_docker; then
    echo "El motor Docker no responde. Abra Docker Desktop, espere a que diga 'Engine running' y reintente." >&2
    exit 1
  fi
}

# Compose lee ./.env por defecto (ruta relativa valida tambien para docker.exe desde WSL).
compose() {
  if [ "$ARYA_ENV_FILE" = "$ARYA_ROOT/.env" ]; then
    "$DOCKER_BIN" compose "$@"
  else
    "$DOCKER_BIN" compose --env-file "$ARYA_ENV_FILE" "$@"
  fi
}

gateway_url() { printf 'http://127.0.0.1:%s' "$(env_get GATEWAY_PORT 8081)"; }
agent_url() { printf 'http://127.0.0.1:%s' "$(env_get AGENT_PORT 8091)"; }
demo_url() { printf 'http://127.0.0.1:%s' "$(env_get UI_PORT 8090)"; }
# Abre una URL en el navegador del equipo (Windows desde WSL, o Linux/macOS).
open_url() {
  if command -v powershell.exe >/dev/null 2>&1; then powershell.exe -NoProfile -Command "Start-Process '$1'" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then open "$1"
  else return 1
  fi
}
cmms_url() { printf 'http://127.0.0.1:%s' "$(env_get CMMS_PORT 8082)"; }
control_url() { printf 'http://127.0.0.1:%s' "$(env_get CONTROL_PORT 9001)"; }
scada_url() { printf 'http://127.0.0.1:%s' "$(env_get SCADA_PORT 8080)"; }

# control_call METODO RUTA [JSON]: llama a la API local de control con el token de .env.
control_call() {
  local method="$1" path="$2" body="${3:-}" token out code
  require_env
  token="$(env_get DEMO_CONTROL_TOKEN)"
  if [ -z "$token" ]; then echo "DEMO_CONTROL_TOKEN no esta definido en .env" >&2; exit 1; fi
  out="$(mktemp)"
  # El token viaja solo en la cabecera, por stdin de curl, para no exponerlo en la lista de procesos.
  code="$(printf 'header = "Authorization: Bearer %s"\n' "$token" | curl -sS -o "$out" -w '%{http_code}' \
    --max-time 8 -K - -X "$method" -H 'Content-Type: application/json' ${body:+-d "$body"} \
    "$(control_url)$path" || true)"
  CONTROL_BODY="$(cat "$out")"; rm -f "$out"
  CONTROL_CODE="${code:-000}"
}

json_field() { printf '%s' "$1" | sed -n "s/.*\"$2\":\"\{0,1\}\([^,\"}]*\)\"\{0,1\}.*/\1/p"; }
