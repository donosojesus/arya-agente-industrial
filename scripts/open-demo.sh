#!/usr/bin/env bash
# Abre la pantalla dividida (planta + ARYA) con los controles del presentador y la aprobacion habilitados.
# Los tokens viajan en el fragmento de la URL (#...), que el navegador no envia a ningun servidor.
source "$(dirname "$0")/_common.sh"
require_env
url="$(demo_url)/#approver=$(env_get CMMS_APPROVER_TOKEN)&control=$(env_get DEMO_CONTROL_TOKEN)"
if open_url "$url"; then echo "Pantalla de demostracion abierta en $(demo_url)"
else echo "Abra manualmente $(demo_url)"; fi
