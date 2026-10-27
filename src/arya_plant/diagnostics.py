"""Utilidades de diagnostico usadas por healthcheck, preflight y demo-status.

Usan un cliente OPC UA real contra el servidor de la planta y HTTP estandar.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from asyncua import Client, ua

from .tags import BATCH_TAGS, NAMESPACE_URI, SEQ_NODE


def local_opcua_endpoint() -> str:
    """Endpoint para conectarse desde el propio contenedor/equipo."""
    endpoint = os.environ.get("OPCUA_ENDPOINT", "opc.tcp://127.0.0.1:4840/arya/plant/")
    return endpoint.replace("//0.0.0.0:", "//127.0.0.1:")


def local_control_url() -> str:
    return f"http://127.0.0.1:{os.environ.get('CONTROL_PORT', '9001')}"


def http_json(url: str, token: str | None = None, timeout: float = 4.0) -> tuple[int, object]:
    """GET que devuelve (status, json|None) sin lanzar por codigos HTTP de error."""
    request = urllib.request.Request(url)
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return status, None


@dataclass
class Batch:
    seq: int
    values: dict[str, object]
    statuses_good: bool
    source_timestamps: set[datetime | None]


async def read_batch(client: Client, attempts: int = 4) -> Batch:
    """Lee un lote coherente: [SEQ, tags..., SEQ] en una sola peticion Read."""
    idx = await client.get_namespace_index(NAMESPACE_URI)
    names = [SEQ_NODE] + [t.name for t in BATCH_TAGS] + [SEQ_NODE]
    nodes = [client.get_node(ua.NodeId(name, idx)) for name in names]
    for _ in range(attempts):
        dvs = await client.read_attributes(nodes, ua.AttributeIds.Value)
        first, last = dvs[0].Value.Value, dvs[-1].Value.Value
        if first == last and first % 2 == 0:
            body = dvs[1:-1]
            return Batch(
                seq=first,
                values={name: dv.Value.Value for name, dv in zip(names[1:-1], body)},
                statuses_good=all(dv.StatusCode.is_good() for dv in body),
                source_timestamps={dv.SourceTimestamp for dv in body},
            )
    raise RuntimeError("could not read a coherent OPC UA batch")
