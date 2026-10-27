"""Preflight de la etapa planta: `python -m arya_plant.preflight`.

Valida con clientes reales (OPC UA y HTTP) que la planta esta lista. Solo
declara PLANT READY: el agente ARYA y el resto de la demo no existen aun.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from asyncua import Client, ua

from .diagnostics import http_json, local_control_url, local_opcua_endpoint, read_batch
from .tags import NAMESPACE_URI, PROCESS_TAGS

_results: list[bool] = []


def check(ok: bool, text: str, hint: str = "") -> bool:
    _results.append(bool(ok))
    print(f"[{'OK' if ok else 'FAIL'}] {text}" + (f"  -> {hint}" if hint and not ok else ""))
    return bool(ok)


async def _opcua_checks() -> str | None:
    run_id = None
    async with Client(local_opcua_endpoint(), timeout=4) as client:
        idx = await client.get_namespace_index(NAMESPACE_URI)
        check(True, f"OPC UA: conexión y namespace {NAMESPACE_URI} (ns={idx})")
        first = await read_batch(client)
        check(first.statuses_good, "OPC UA: todos los tags del lote con estado Good")
        missing = [t.name for t in PROCESS_TAGS if first.values.get(t.name) is None]
        check(not missing, f"OPC UA: {len(PROCESS_TAGS)} tags de proceso legibles", f"faltan {missing}")
        stamps = first.source_timestamps
        ts = next(iter(stamps)) if len(stamps) == 1 else None
        check(len(stamps) == 1 and ts is not None, "OPC UA: lote coherente con un único timestamp de origen")
        if ts is not None:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - ts).total_seconds()
            check(abs(age) < 5, f"OPC UA: timestamp de origen UTC reciente ({age:.1f} s)")
        await asyncio.sleep(1.5)
        second = await read_batch(client)
        check(second.seq != first.seq, "OPC UA: los lotes avanzan (simulación en marcha)")
        node = client.get_node(ua.NodeId("P101.MOTOR_TEMP", idx))
        try:
            await node.write_value(0.0)
            check(False, "OPC UA: escritura de cliente rechazada", "el servidor ACEPTÓ una escritura")
        except ua.UaStatusCodeError as exc:
            check(True, f"OPC UA: escritura de cliente rechazada ({ua.StatusCode(exc.code).name})")
        run_id = str(second.values.get("RUN.ID"))
        level = second.values.get("P101.ALARM_LEVEL")
        check(level == "NORMAL", f"Proceso: nivel de alarma NORMAL (actual: {level})", "ejecutar reset-demo")
    return run_id


def main() -> int:
    logging.disable(logging.CRITICAL)
    token = os.environ.get("DEMO_CONTROL_TOKEN", "")
    control = local_control_url()
    view = os.environ.get("PLANT_VIEW_URL", "http://plant-view:8080").rstrip("/")
    print("ARYA Industrial Demo - preflight de la planta")

    try:
        status, body = http_json(f"{control}/healthz")
        check(status == 200 and isinstance(body, dict) and bool(body.get("ok")), "Control: /healthz sano")
        status, _ = http_json(f"{control}/api/demo/state")
        check(status == 401, f"Control: sin token responde 401 (obtuvo {status})")
        status, state = http_json(f"{control}/api/demo/state", token=token)
        check(status == 200, f"Control: token local aceptado (obtuvo {status})", "revisar DEMO_CONTROL_TOKEN en .env")
        mode = state.get("mode") if isinstance(state, dict) else None
        check(mode == "NORMAL", f"Escenario: modo NORMAL (actual: {mode})", "ejecutar reset-demo")
    except Exception as exc:
        check(False, f"Control: API accesible ({type(exc).__name__}: {exc})")

    run_id = None
    try:
        run_id = asyncio.run(asyncio.wait_for(_opcua_checks(), timeout=20))
    except Exception as exc:
        check(False, f"OPC UA: servidor accesible ({type(exc).__name__}: {exc})")

    try:
        status, _ = http_json(f"{view}/healthz")
        check(status == 200, f"SCADA: /healthz sano (obtuvo {status})")
        status, latest = http_json(f"{view}/api/telemetry/latest")
        latest = latest if isinstance(latest, dict) else {}
        conn = (latest.get("connection") or {}).get("state")
        snap = latest.get("snapshot") or {}
        check(conn == "CONNECTED", f"SCADA: cliente OPC UA conectado (estado: {conn})")
        check(snap.get("quality") == "GOOD", f"SCADA: calidad de datos GOOD (actual: {snap.get('quality')})")
        tags = snap.get("tags") or {}
        check(all(t.name in tags for t in PROCESS_TAGS), "SCADA: todos los tags de proceso presentes")
        check(
            run_id is not None and snap.get("run_id") == run_id,
            "SCADA: muestra el mismo ensayo (run_id) que el servidor OPC UA",
        )
    except Exception as exc:
        check(False, f"SCADA: plant-view accesible en {view} ({type(exc).__name__}: {exc})")

    if "--checks-only" in sys.argv[1:]:
        # Lo invoca scripts/preflight, que emite el veredicto final junto con sus propias verificaciones.
        return 0 if all(_results) else 1
    print()
    if all(_results):
        print("PLANT READY")
        print("Alcance: planta, OPC UA y pantalla. ARYA (agente) aún no está implementado.")
        return 0
    print(f"PLANT NOT READY ({_results.count(False)} verificación(es) fallida(s))")
    return 1


if __name__ == "__main__":
    sys.exit(main())
