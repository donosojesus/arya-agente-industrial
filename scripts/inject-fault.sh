#!/usr/bin/env bash
# Inyecta la falla de demostracion. Uso: inject-fault.sh [duracion_en_segundos] [alpha|bravo|charlie]
# charlie = escenario C (predictivo): la planta pasa a publicar el historial de 6 meses con desgaste.
source "$(dirname "$0")/_common.sh"
case "${1:-}" in alpha|bravo|charlie) set -- "" "$1" ;; esac
body='{}'
if [ "${1:-}" != "" ]; then
  case "$1" in *[!0-9.]*) echo "La duracion debe ser un numero de segundos (30 a 900)." >&2; exit 2 ;; esac
  body="{\"duration_seconds\": $1}"
fi
if [ "${2:-}" != "" ]; then
  case "$2" in alpha|bravo|charlie) ;; *) echo "El escenario debe ser alpha, bravo o charlie." >&2; exit 2 ;; esac
  if [ "$body" = '{}' ]; then body="{\"scenario\": \"$2\"}"; else body="${body%\}}, \"scenario\": \"$2\"}"; fi
fi
control_call POST /api/demo/inject-fault "$body"
case "$CONTROL_CODE" in
  200) echo "FALLA INYECTADA. Ensayo $(json_field "$CONTROL_BODY" run_id), duracion $(json_field "$CONTROL_BODY" fault_duration_s) s." ;;
  409) echo "No se puede inyectar ahora: hay una falla activa o la planta aun se recupera. Use reset-demo."; exit 1 ;;
  401) echo "Token rechazado: revise DEMO_CONTROL_TOKEN en .env." >&2; exit 1 ;;
  422) echo "Duracion no valida: debe estar entre 30 y 900 segundos." >&2; exit 1 ;;
  000) echo "La API de control no responde en $(control_url). Esta arrancada la planta?" >&2; exit 1 ;;
  *) echo "Respuesta inesperada de la API de control: HTTP $CONTROL_CODE" >&2; exit 1 ;;
esac
