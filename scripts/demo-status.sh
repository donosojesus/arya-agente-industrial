#!/usr/bin/env bash
# Muestra el estado de los contenedores y un resumen de la planta.
source "$(dirname "$0")/_common.sh"
require_env
require_docker
compose ps
echo
compose exec -T plant python -m arya_plant.status
