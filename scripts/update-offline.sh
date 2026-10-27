#!/usr/bin/env bash
# Actualiza el CODIGO de uno o mas servicios SIN Internet, sobre su imagen local actual.
# No reinstala dependencias: sirve para cambios de codigo o documentos, no de requirements.
# Uso: ./scripts/update-offline.sh agent demo-ui
source "$(dirname "$0")/_common.sh"
require_env
require_docker
[ "$#" -gt 0 ] || { echo "Uso: $0 <servicio> [servicio...]   (servicios: $ARYA_SERVICES)" >&2; exit 2; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
for svc in "$@"; do
  dockerfile="docker/$svc.Dockerfile"
  [ -f "$dockerfile" ] || { echo "Servicio desconocido: $svc" >&2; exit 2; }
  image="arya-industrial-demo/$svc:0.1.0"
  "$DOCKER_BIN" image inspect "$image" >/dev/null 2>&1 || { echo "Falta la imagen $image: hay que construirla con Internet (start-demo --build)." >&2; exit 1; }
  { echo "FROM $image"; echo "USER root"; grep -E '^COPY (src|data)/' "$dockerfile"; echo "USER 10001"; } > "$tmp/$svc.Dockerfile"
  echo "Actualizando el codigo de $svc sobre su imagen local..."
  "$DOCKER_BIN" build -q -f "$tmp/$svc.Dockerfile" -t "$image" . >/dev/null
done
compose up -d --no-build --pull never --wait "$@"
echo "Listo: $* actualizado(s) sin Internet."
