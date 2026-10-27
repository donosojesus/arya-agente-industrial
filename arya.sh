#!/usr/bin/env bash
# ARYA Industrial Demo - atajo unico para subir, bajar y revisar todo.
#   ./arya.sh            sube todo y abre la pantalla
#   ./arya.sh up         igual, sin abrir el navegador
#   ./arya.sh status     estado de los contenedores y preflight
#   ./arya.sh open       abre la pantalla dividida con los tokens cargados
#   ./arya.sh factory    abre en otra ventana "Del agente a la AI Factory"
#   ./arya.sh reset      planta, CMMS y ARYA al estado inicial
#   ./arya.sh down       detiene los contenedores de ARYA (libera recursos)
set -uo pipefail

PROJECT="$(cd "$(dirname "$0")" && pwd)"
DOCKER_DESKTOP='C:\Program Files\Docker\Docker\Docker Desktop.exe'

if [ ! -d "$PROJECT/scripts" ]; then
  echo "No encuentro el proyecto en: $PROJECT" >&2
  exit 1
fi
cd "$PROJECT"

docker_ok() { docker info >/dev/null 2>&1 || docker.exe info >/dev/null 2>&1; }

ensure_docker() {
  if docker_ok; then return 0; fi
  echo "Docker no esta en marcha. Abriendo Docker Desktop..."
  powershell.exe -NoProfile -Command "Start-Process '$DOCKER_DESKTOP'" >/dev/null 2>&1 || {
    echo "No pude abrir Docker Desktop. Abralo a mano y reintente." >&2; return 1; }
  for i in $(seq 1 60); do
    if docker_ok; then echo "Docker listo."; return 0; fi
    sleep 3
  done
  echo "Docker no respondio en 3 minutos. Revise Docker Desktop y reintente." >&2
  return 1
}

# Escucha de voz local (Windows): scripts/voice-listener.ps1 en http://localhost:8095
voice_ok() { powershell.exe -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://localhost:8095/health).StatusCode } catch { 0 }" 2>/dev/null | tr -d '\r' | grep -q '^200$'; }
voice_start() {
  if voice_ok; then echo "Escucha de voz: ya en marcha."; return 0; fi
  local script; script="$(wslpath -w "$PROJECT/scripts/voice-listener.ps1")"
  powershell.exe -NoProfile -Command "Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File','$script'" >/dev/null 2>&1
  for i in $(seq 1 10); do sleep 1; if voice_ok; then echo "Escucha de voz: en marcha (boton HABLAR)."; return 0; fi; done
  echo "Escucha de voz: no arranco (revise que haya un microfono y el permiso de microfono en Windows)."
}
voice_stop() {
  powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { \$_.CommandLine -like '*voice-listener.ps1*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1 || true
  echo "Escucha de voz: detenida."
}

urls() {
  echo
  echo "  Pantalla de demostracion : http://127.0.0.1:8090"
  echo "  ARYA por dentro          : http://127.0.0.1:8090/?mode=inside"
  echo "  Planta, pantalla completa: http://127.0.0.1:8080"
  echo "  Del agente a la AI Factory: http://127.0.0.1:8090/factory"
}

case "${1:-all}" in
  all|up)
    ensure_docker || exit 1
    ./scripts/start-demo.sh || exit 1
    echo
    ./scripts/preflight.sh | grep -E "FAIL|Nemotron|^PLANT" || true
    voice_start
    urls
    if [ "${1:-all}" = "all" ]; then ./scripts/open-demo.sh; fi
    ;;
  status)
    if ! docker_ok; then echo "Docker no esta en marcha: la demo esta abajo."; exit 1; fi
    docker ps --filter label=com.arya.project=arya-industrial-demo --format '{{.Names}}  {{.Status}}' 2>/dev/null || true
    echo
    ./scripts/preflight.sh | grep -E "FAIL|Nemotron|^PLANT" || true
    if voice_ok; then echo "Escucha de voz: en marcha."; else echo "Escucha de voz: detenida (se inicia con: arya.sh up)."; fi
    urls
    ;;
  open) ./scripts/open-demo.sh ;;
  factory) powershell.exe -NoProfile -Command "Start-Process msedge -ArgumentList '--new-window','http://127.0.0.1:8090/factory'" >/dev/null 2>&1 || echo "Abra http://127.0.0.1:8090/factory en una ventana nueva"; echo "AI Factory: http://127.0.0.1:8090/factory" ;;
  reset) ./scripts/reset-demo.sh ;;
  down)
    voice_stop
    if docker_ok; then ./scripts/stop-demo.sh; else echo "Docker no esta en marcha: no hay nada que detener."; fi
    echo "Para liberar mas memoria, cierre Docker Desktop desde su icono (Quit Docker Desktop)."
    ;;
  *) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
