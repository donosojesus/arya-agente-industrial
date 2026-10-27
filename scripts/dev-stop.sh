#!/usr/bin/env bash
# Detiene los procesos iniciados por dev-start.sh (solo esos, por su pid registrado).
source "$(dirname "$0")/_common.sh"
RUN_DIR="${ARYA_RUN_DIR:-$HOME/.cache/arya-industrial-demo}"
for name in demo-ui agent cmms ot-gateway plant-view plant; do
  pid_file="$RUN_DIR/$name.pid"
  if [ -f "$pid_file" ]; then
    pid="$(cat "$pid_file")"
    if kill -0 "$pid" 2>/dev/null && grep -q "arya_" "/proc/$pid/cmdline" 2>/dev/null; then
      kill "$pid" && echo "$name detenido (pid $pid)"
    else
      echo "$name no estaba en marcha"
    fi
    rm -f "$pid_file"
  else
    echo "$name no estaba en marcha"
  fi
done
