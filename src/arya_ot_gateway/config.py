"""Configuracion del servicio ot-gateway mediante variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GatewaySettings:
    opcua_endpoint: str = "opc.tcp://127.0.0.1:4840/arya/plant/"
    host: str = "127.0.0.1"
    port: int = 8081
    historian_path: str = "/data/historian.sqlite3"
    sample_s: float = 1.0
    stale_after_s: float = 5.0
    retention_days: float = 7.0

    @classmethod
    def from_env(cls) -> "GatewaySettings":
        return cls(
            opcua_endpoint=os.environ.get("OPCUA_ENDPOINT", cls.opcua_endpoint).strip(),
            host=os.environ.get("GATEWAY_HOST", cls.host).strip(),
            port=int(os.environ.get("GATEWAY_PORT", cls.port)),
            historian_path=os.environ.get("HISTORIAN_PATH", cls.historian_path).strip(),
            sample_s=min(5.0, max(0.5, float(os.environ.get("SAMPLE_SECONDS", cls.sample_s)))),
            stale_after_s=min(60.0, max(2.0, float(os.environ.get("STALE_AFTER_SECONDS", cls.stale_after_s)))),
            retention_days=min(90.0, max(0.1, float(os.environ.get("HISTORIAN_RETENTION_DAYS", cls.retention_days)))),
        )
