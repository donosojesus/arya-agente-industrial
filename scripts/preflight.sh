#!/usr/bin/env bash
# Verificacion previa de la etapa planta. Declara PLANT READY solo si todo esta correcto.
# No declara lista la demo completa: ARYA (agente) aun no existe.
source "$(dirname "$0")/_common.sh"
failures=0
ok()   { echo "[OK] $1"; }
fail() { echo "[FAIL] $1"; failures=$((failures + 1)); }

echo "ARYA Industrial Demo - preflight de la planta (equipo anfitrion)"
if [ -f "$ARYA_ENV_FILE" ]; then ok ".env presente"; else fail ".env no existe -> ejecute ./scripts/start-demo.sh --build"; fi

if find_docker; then
  ok "Motor Docker disponible ($DOCKER_BIN)"
else
  fail "El motor Docker no responde -> abra Docker Desktop"
  echo; echo "PLANT NOT READY"; exit 1
fi

for image in $ARYA_IMAGES; do
  if "$DOCKER_BIN" image inspect "$image" >/dev/null 2>&1; then ok "Imagen local $image"; else fail "Falta la imagen local $image"; fi
done

for service in $ARYA_SERVICES; do
  cid="$(compose ps -q "$service" 2>/dev/null | tr -d '\r' || true)"
  health="missing"
  [ -n "$cid" ] && health="$("$DOCKER_BIN" inspect -f '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid" 2>/dev/null | tr -d '\r' || echo missing)"
  if [ "$health" = "running/healthy" ]; then ok "Contenedor $service en marcha y healthy"; else fail "Contenedor $service: $health"; fi
done

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$(scada_url)/healthz" || true)"
if [ "$code" = "200" ]; then ok "SCADA accesible desde el notebook en $(scada_url)"; else fail "SCADA no accesible en $(scada_url) (HTTP ${code:-000})"; fi
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$(control_url)/api/demo/state" || true)"
if [ "$code" = "401" ]; then ok "API de control accesible en loopback y protegida (401 sin token)"; else fail "API de control en $(control_url): HTTP ${code:-000} (se esperaba 401 sin token)"; fi

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$(gateway_url)/healthz" || true)"
if [ "$code" = "200" ]; then ok "OT Gateway sano: recibe OPC UA y escribe en el historian"; else fail "OT Gateway en $(gateway_url): HTTP ${code:-000}"; fi
body="$(curl -s --max-time 5 "$(gateway_url)/api/v1/assets/P-101/history?signals=flow&minutes=5" || true)"
case "$body" in *'"samples":'*) ok "Historian: devuelve historia real del ensayo actual" ;; *) fail "Historian: sin muestras en los ultimos 5 minutos" ;; esac
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST "$(gateway_url)/api/v1/assets/P-101/tags" || true)"
if [ "$code" = "405" ]; then ok "OT Gateway de solo lectura (escritura rechazada: 405)"; else fail "OT Gateway acepto un POST (HTTP ${code:-000})"; fi
body="$(curl -s --max-time 5 "$(cmms_url)/api/v1/work-orders?asset=P-101&limit=50" || true)"
case "$body" in *'"WO-2026-0142"'*) ok "CMMS: ordenes historicas de P-101 disponibles" ;; *) fail "CMMS en $(cmms_url): no devuelve las ordenes historicas" ;; esac
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST -H 'Content-Type: application/json' -d '{}' "$(cmms_url)/api/v1/work-orders/drafts" || true)"
if [ "$code" = "401" ]; then ok "CMMS: crear borradores exige la clave del agente (401 sin clave)"; else fail "CMMS: borrador sin clave devolvio HTTP ${code:-000}"; fi
case "$body" in *'DRAFT_PENDING_APPROVAL'*) fail "CMMS: quedan borradores de un ensayo anterior -> ejecute reset-demo" ;; *) ok "CMMS: sin borradores pendientes (estado inicial)" ;; esac

code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$(demo_url)/healthz" || true)"
if [ "$code" = "200" ]; then ok "Pantalla dividida disponible en $(demo_url)"; else fail "Pantalla dividida en $(demo_url): HTTP ${code:-000}"; fi
body="$(curl -s --max-time 8 "$(demo_url)/agent/api/v1/status" || true)"
case "$body" in
  *'"ot_gateway_reachable":true'*'"cmms_reachable":true'*) ok "Agente ARYA en marcha: alcanza el gateway y el CMMS; sin herramientas de escritura al proceso" ;;
  *) fail "Agente ARYA: no responde o no alcanza el gateway/CMMS" ;;
esac
case "$body" in
  *'"reachable":true'*) ok "Nemotron: en linea" ;;
  *'"configured":true'*) echo "[--] Nemotron: configurado pero NO responde (no afecta a PLANT READY)" ;;
  *) echo "[--] Nemotron: no configurado todavia (pendiente GB10; no afecta a PLANT READY)" ;;
esac

echo
if ! compose exec -T plant python -m arya_plant.preflight --checks-only; then failures=$((failures + 1)); fi

echo
if [ "$failures" -eq 0 ]; then
  echo "PLANT READY"
  echo "Alcance: lado planta y agente en marcha. La demo completa requiere Nemotron conectado y voz: aun NO esta lista."
else
  echo "PLANT NOT READY"
  exit 1
fi
