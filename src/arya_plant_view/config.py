"""Configuracion del servicio plant-view mediante variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ViewSettings:
    opcua_endpoint: str = "opc.tcp://127.0.0.1:4840/arya/plant/"
    host: str = "127.0.0.1"
    port: int = 8080
    sample_s: float = 1.0
    stale_after_s: float = 5.0
    control_port: int = 9001  # solo para que el navegador del presentador sepa donde esta la API de control

    @classmethod
    def from_env(cls) -> "ViewSettings":
        return cls(
            opcua_endpoint=os.environ.get("OPCUA_ENDPOINT", cls.opcua_endpoint).strip(),
            host=os.environ.get("VIEW_HOST", cls.host).strip(),
            port=int(os.environ.get("VIEW_PORT", cls.port)),
            sample_s=min(5.0, max(0.2, float(os.environ.get("SAMPLE_SECONDS", cls.sample_s)))),
            stale_after_s=min(60.0, max(2.0, float(os.environ.get("STALE_AFTER_SECONDS", cls.stale_after_s)))),
            control_port=int(os.environ.get("CONTROL_PUBLIC_PORT", cls.control_port)),
        )
