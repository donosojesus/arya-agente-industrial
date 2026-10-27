#!/usr/bin/env bash
# Reinicia la demo: simulacion al estado inicial (nuevo run_id) y CMMS a sus ordenes historicas.
# El historian conserva la historia; las consultas usan por defecto solo el ensayo actual.
source "$(dirname "$0")/_common.sh"
control_call POST /api/demo/reset '{}'
case "$CONTROL_CODE" in
  200) echo "PLANTA REINICIADA. Nuevo ensayo: $(json_field "$CONTROL_BODY" run_id)." ;;
  401) echo "Token rechazado: revise DEMO_CONTROL_TOKEN en .env." >&2; exit 1 ;;
  000) echo "La API de control no responde en $(control_url). Esta arrancada la planta?" >&2; exit 1 ;;
  *) echo "Respuesta inesperada de la API de control: HTTP $CONTROL_CODE" >&2; exit 1 ;;
esac

code="$(printf 'header = "Authorization: Bearer %s"\n' "$(env_get CMMS_APPROVER_TOKEN)" | curl -sS -o /dev/null -w '%{http_code}' \
  --max-time 8 -K - -X POST "$(cmms_url)/api/v1/admin/reset" 2>/dev/null || true)"
case "$code" in
  200) echo "CMMS REINICIADO a las ordenes historicas." ;;
  *) echo "AVISO: el CMMS no se reinicio (HTTP ${code:-000})." ;;
esac

code="$(printf 'header = "Authorization: Bearer %s"\n' "$(env_get AGENT_ADMIN_TOKEN)" | curl -sS -o /dev/null -w '%{http_code}' \
  --max-time 8 -K - -X POST "$(agent_url)/api/v1/admin/reset" 2>/dev/null || true)"
case "$code" in
  200) echo "ARYA REINICIADA: memoria, conversacion y traza en blanco." ;;
  *) echo "AVISO: ARYA no se reinicio (HTTP ${code:-000})." ;;
esac
