"""Configuracion del servicio plant mediante variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass

PLACEHOLDER_TOKENS = {"", "replace-with-a-generated-local-token", "changeme"}
MIN_TOKEN_LENGTH = 24


class ConfigError(Exception):
    pass


def _float(name: str, default: float, low: float, high: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        value = float(raw) if raw else default
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc
    if not (low <= value <= high):
        raise ConfigError(f"{name} must be between {low} and {high}")
    return value


def validate_token(token: str) -> str:
    token = token.strip()
    if token in PLACEHOLDER_TOKENS or len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            "DEMO_CONTROL_TOKEN is missing, is the placeholder, or is shorter than "
            f"{MIN_TOKEN_LENGTH} characters. Generate one locally with scripts/start-demo."
        )
    return token


@dataclass(frozen=True)
class PlantSettings:
    control_token: str
    opcua_endpoint: str = "opc.tcp://127.0.0.1:4840/arya/plant/"
    control_host: str = "127.0.0.1"
    control_port: int = 9001
    allowed_origins: tuple[str, ...] = ("http://127.0.0.1:8080", "http://localhost:8080")
    fault_duration_s: float = 180.0
    recovery_duration_s: float = 90.0
    tick_s: float = 0.5
    seed: int = 101

    @classmethod
    def from_env(cls) -> "PlantSettings":
        origins = tuple(
            o.strip().rstrip("/")
            for o in os.environ.get("CONTROL_ALLOWED_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080").split(",")
            if o.strip()
        )
        if "*" in origins:
            raise ConfigError("CONTROL_ALLOWED_ORIGINS must list explicit local origins, not '*'")
        return cls(
            control_token=validate_token(os.environ.get("DEMO_CONTROL_TOKEN", "")),
            opcua_endpoint=os.environ.get("OPCUA_ENDPOINT", "opc.tcp://127.0.0.1:4840/arya/plant/").strip(),
            control_host=os.environ.get("CONTROL_HOST", "127.0.0.1").strip(),
            control_port=int(_float("CONTROL_PORT", 9001, 1, 65535)),
            allowed_origins=origins,
            fault_duration_s=_float("FAULT_DURATION_SECONDS", 180.0, 30.0, 900.0),
            recovery_duration_s=_float("RECOVERY_SECONDS", 90.0, 10.0, 900.0),
            tick_s=_float("TICK_SECONDS", 0.5, 0.1, 2.0),
            seed=int(_float("SIM_SEED", 101, 0, 2**31 - 1)),
        )
