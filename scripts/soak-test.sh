#!/usr/bin/env bash
# Prueba de resistencia: deja la demo corriendo N horas y registra cada minuto la salud de cada
# servicio y la memoria de cada contenedor. Por defecto NO inyecta fallas: la planta queda normal.
# Uso: ./scripts/soak-test.sh [horas] [--with-faults]   (por defecto 3 h; con --with-faults, un ciclo
#      de falla y recuperacion cada 20 minutos)
#      ./scripts/soak-test.sh --summary <archivo.csv>
# No usa el modelo de lenguaje: mide la estabilidad de la planta, la pantalla, el historian, el CMMS y el agente.
source "$(dirname "$0")/_common.sh"

summary() {
  local file="$1"
  echo "Resumen de $file"
  # Hay una fila por contenedor y minuto: la salud se cuenta una vez por minuto.
  awk -F, 'NR>1 && !($1 in seen) { seen[$1]=1; n++; for (i=3;i<=8;i++) if ($i!="200") bad[i]++ }
    NR==1 { for (i=3;i<=8;i++) name[i]=$i }
    END {
      printf "  muestras: %d (una por minuto)\n", n
      for (i=3;i<=8;i++) printf "  %-10s fallas: %d\n", name[i], bad[i]+0
    }' "$file"
  echo "  memoria por contenedor (MiB, primera -> ultima muestra):"
  awk -F, 'NR>1 && $9!="" { if (!($9 in f)) f[$9]=$10; l[$9]=$10 } END { for (c in f) printf "    %-18s %7.1f -> %7.1f\n", c, f[c], l[c] }' "$file" | sort
  local gaps; gaps="$(awk -F, 'NR>1 && !($1 in seen) { seen[$1]=1; if (prev && $1-prev>150) g++; prev=$1 } END { print g+0 }' "$file")"
  echo "  pausas de mas de 2,5 min entre muestras (equipo suspendido u ocupado): $gaps"
}

if [ "${1:-}" = "--summary" ]; then summary "$2"; exit 0; fi
with_faults=0
for arg in "$@"; do [ "$arg" = "--with-faults" ] && with_faults=1; done
hours="${1:-3}"; [ "$hours" = "--with-faults" ] && hours="${2:-3}"
case "$hours" in ""|*[!0-9.]*) echo "Uso: $0 [horas]" >&2; exit 2 ;; esac
require_env; require_docker
mkdir -p "$HOME/.cache/arya-industrial-demo"
out="$HOME/.cache/arya-industrial-demo/soak-$(date +%Y%m%d-%H%M).csv"
echo "epoch,hora,plant,plant-view,ot-gateway,cmms,agent,demo-ui,contenedor,mem_mib" > "$out"
end=$(( $(date +%s) + $(awk -v h="$hours" 'BEGIN { printf "%d", h * 3600 }') ))
cycle_every=1200; next_cycle=$(( $(date +%s) + 60 )); recover_at=0
echo "Prueba de resistencia de $hours h ($([ "$with_faults" -eq 1 ] && echo 'con fallas cada 20 min' || echo 'sin fallas')). Registro: $out"
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" || true; }
while [ "$(date +%s)" -lt "$end" ]; do
  now=$(date +%s)
  if [ "$with_faults" -eq 1 ] && [ "$now" -ge "$next_cycle" ]; then ./scripts/inject-fault.sh >/dev/null 2>&1 || true; recover_at=$(( now + 360 )); next_cycle=$(( now + cycle_every )); fi
  if [ "$recover_at" -gt 0 ] && [ "$now" -ge "$recover_at" ]; then ./scripts/normal-operation.sh >/dev/null 2>&1 || true; recover_at=0; fi
  row="$now,$(date +%H:%M:%S),$(code "$(control_url)/healthz"),$(code "$(scada_url)/healthz"),$(code "$(gateway_url)/healthz"),$(code "$(cmms_url)/healthz"),$(code "$(agent_url)/healthz"),$(code "$(demo_url)/healthz")"
  "$DOCKER_BIN" stats --no-stream --format '{{.Name}},{{.MemUsage}}' 2>/dev/null | tr -d '\r' | grep '^arya-' | while IFS=, read -r name mem; do
    value="$(printf '%s' "${mem%% /*}" | awk '/GiB/ { sub("GiB",""); print $1*1024; next } /MiB/ { sub("MiB",""); print $1; next } /KiB/ { sub("KiB",""); print $1/1024 }')"
    echo "$row,$name,$value" >> "$out"
  done
  sleep 60
done
[ "$with_faults" -eq 1 ] && { ./scripts/normal-operation.sh >/dev/null 2>&1 || true; }
summary "$out"
