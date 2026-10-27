"""Healthcheck del contenedor plant: `python -m arya_plant.healthcheck`.

Comprueba disponibilidad real: la API de control responde sana y un cliente
OPC UA real observa que el numero de secuencia de los lotes avanza.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from asyncua import Client

from .diagnostics import http_json, local_control_url, local_opcua_endpoint, read_batch


async def _opcua_advancing() -> bool:
    async with Client(local_opcua_endpoint(), timeout=3) as client:
        first = await read_batch(client)
        await asyncio.sleep(1.2)
        second = await read_batch(client)
    return first.statuses_good and second.statuses_good and second.seq != first.seq


def main() -> int:
    logging.disable(logging.CRITICAL)
    try:
        status, body = http_json(f"{local_control_url()}/healthz", timeout=3)
        if status != 200 or not isinstance(body, dict) or not body.get("ok"):
            print(f"unhealthy: control API status={status}")
            return 1
        if not asyncio.run(asyncio.wait_for(_opcua_advancing(), timeout=8)):
            print("unhealthy: OPC UA batches are not advancing")
            return 1
    except Exception as exc:  # healthcheck: cualquier fallo es "unhealthy"
        print(f"unhealthy: {type(exc).__name__}: {exc}")
        return 1
    print("healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
