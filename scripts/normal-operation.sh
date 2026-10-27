#!/usr/bin/env bash
# Retira la falla: las senales vuelven gradualmente a lo normal (no es un reinicio).
source "$(dirname "$0")/_common.sh"
control_call POST /api/demo/normal '{}'
case "$CONTROL_CODE" in
  200)
    if [ "$(json_field "$CONTROL_BODY" mode)" = "RECOVERY" ]; then
      echo "FALLA RETIRADA. Los valores vuelven gradualmente; para reiniciar de inmediato use reset-demo."
    else
      echo "No habia una falla activa. La planta sigue en operacion normal."
    fi ;;
  401) echo "Token rechazado: revise DEMO_CONTROL_TOKEN en .env." >&2; exit 1 ;;
  000) echo "La API de control no responde en $(control_url). Esta arrancada la planta?" >&2; exit 1 ;;
  *) echo "Respuesta inesperada de la API de control: HTTP $CONTROL_CODE" >&2; exit 1 ;;
esac
