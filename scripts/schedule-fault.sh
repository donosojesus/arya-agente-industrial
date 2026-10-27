#!/usr/bin/env bash
# Programa una falla que empezara sola. Uso: schedule-fault.sh <minutos> [alpha|bravo]
#                                            schedule-fault.sh cancel
source "$(dirname "$0")/_common.sh"
if [ "${1:-}" = "cancel" ]; then
  control_call POST /api/demo/cancel-schedule '{}'
  [ "$CONTROL_CODE" = "200" ] && echo "Programacion cancelada (si habia alguna)." && exit 0
  echo "No se pudo cancelar: HTTP $CONTROL_CODE" >&2; exit 1
fi
minutes="${1:-}"; scenario="${2:-bravo}"
case "$minutes" in ""|*[!0-9.]*) echo "Uso: $0 <minutos> [alpha|bravo]   |   $0 cancel" >&2; exit 2 ;; esac
case "$scenario" in alpha|bravo) ;; *) echo "El escenario debe ser alpha o bravo." >&2; exit 2 ;; esac
seconds="$(awk -v m="$minutes" 'BEGIN { printf "%.0f", m * 60 }')"
control_call POST /api/demo/schedule-fault "{\"delay_seconds\": $seconds, \"scenario\": \"$scenario\"}"
case "$CONTROL_CODE" in
  200) echo "FALLA PROGRAMADA: escenario $scenario en $minutes min. Empezara sola cuando la planta este en NORMAL." ;;
  401) echo "Token rechazado: revise DEMO_CONTROL_TOKEN en .env." >&2; exit 1 ;;
  422) echo "Valor no valido: los minutos deben estar entre 1 y 240." >&2; exit 1 ;;
  000) echo "La API de control no responde en $(control_url)." >&2; exit 1 ;;
  *) echo "Respuesta inesperada: HTTP $CONTROL_CODE" >&2; exit 1 ;;
esac
