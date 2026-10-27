#!/usr/bin/env bash
# Arranca la planta ARYA. Con --build prepara las imagenes (requiere Internet la primera vez).
# Sin --build es un arranque OFFLINE: solo usa imagenes locales, no construye ni descarga.
source "$(dirname "$0")/_common.sh"

BUILD=0
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    *) echo "Uso: $0 [--build]" >&2; exit 2 ;;
  esac
done

ensure_env

require_docker

if [ "$BUILD" -eq 1 ]; then
  echo "Preparacion (con Internet): construyendo imagenes..."
  compose build --pull
else
  for image in $ARYA_IMAGES; do
    if ! "$DOCKER_BIN" image inspect "$image" >/dev/null 2>&1; then
      echo "Falta la imagen local $image." >&2
      echo "Ejecute una vez, con Internet: ./scripts/start-demo.sh --build" >&2
      exit 1
    fi
  done
fi

echo "Arrancando con imagenes locales (sin construir ni descargar)..."
compose up -d --no-build --pull never --wait --wait-timeout 120
echo
echo "Planta en marcha."
echo "  DEMO:       $(demo_url)   (pantalla dividida planta + ARYA: ./scripts/open-demo.sh)"
echo "  SCADA:      $(scada_url)   (para abrirlo con los controles habilitados: ./scripts/open-scada.sh)"
echo "  Gateway:    $(gateway_url)   (lectura para el agente)     CMMS: $(cmms_url)"
echo "  Verificar:  ./scripts/preflight.sh"
