"""Resumen de estado para el presentador: `python -m arya_plant.status`."""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from asyncua import Client

from .diagnostics import http_json, local_control_url, local_opcua_endpoint, read_batch
from .tags import PROCESS_TAGS


async def _batch():
    async with Client(local_opcua_endpoint(), timeout=4) as client:
        return await read_batch(client)


def main() -> int:
    logging.disable(logging.CRITICAL)
    token = os.environ.get("DEMO_CONTROL_TOKEN", "")
    view = os.environ.get("PLANT_VIEW_URL", "http://plant-view:8080").rstrip("/")
    rc = 0
    try:
        _, state = http_json(f"{local_control_url()}/api/demo/state", token=token)
        print(f"Ensayo      : {state['run_id']}")
        print(f"Escenario   : {state['mode']}  (avance de la falla: {state['fault_progress'] * 100:.0f} %)")
        print(f"Tiempo sim. : {state['sim_time_s']:.0f} s")
    except Exception as exc:
        rc = 1
        print(f"Control     : SIN RESPUESTA ({type(exc).__name__}: {exc})")
    try:
        batch = asyncio.run(asyncio.wait_for(_batch(), timeout=10))
        print("OPC UA      : lectura correcta")
        for tag in PROCESS_TAGS:
            value = batch.values[tag.name]
            if isinstance(value, list):
                value = ", ".join(value) if value else "(ninguna)"
            print(f"  {tag.name:<24} {value} {tag.unit or ''}".rstrip())
    except Exception as exc:
        rc = 1
        print(f"OPC UA      : SIN RESPUESTA ({type(exc).__name__}: {exc})")
    try:
        _, latest = http_json(f"{view}/api/telemetry/latest")
        snap = latest.get("snapshot") or {}
        print(f"SCADA       : conexión {latest['connection']['state']}, calidad {snap.get('quality')}")
    except Exception as exc:
        rc = 1
        print(f"SCADA       : SIN RESPUESTA ({type(exc).__name__}: {exc})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
