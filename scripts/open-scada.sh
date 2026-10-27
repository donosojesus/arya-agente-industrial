#!/usr/bin/env bash
# Abre el SCADA en el navegador con los controles del presentador habilitados.
# El token viaja en el fragmento de la URL (#token=...), que el navegador no envia al servidor.
source "$(dirname "$0")/_common.sh"
require_env
url="$(scada_url)/#token=$(env_get DEMO_CONTROL_TOKEN)"
if open_url "$url"; then echo "SCADA abierto en $(scada_url)"
else echo "Abra manualmente $(scada_url) y pegue el token de .env en la pantalla."; fi
