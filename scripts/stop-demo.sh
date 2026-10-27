#!/usr/bin/env bash
# Detiene y retira SOLO los contenedores y la red del proyecto arya-industrial-demo.
# No borra imagenes ni toca recursos de otros proyectos.
source "$(dirname "$0")/_common.sh"
require_env
require_docker
compose down
echo "Planta detenida. Las imagenes locales se conservan para el arranque offline."
