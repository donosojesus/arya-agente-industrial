"""Punto de entrada del servicio plant: `python -m arya_plant`."""

from __future__ import annotations

import logging
import sys

import uvicorn

from .config import ConfigError, PlantSettings
from .control_api import create_control_app
from .runtime import PlantRuntime


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    try:
        settings = PlantSettings.from_env()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    runtime = PlantRuntime(settings)
    app = create_control_app(runtime, settings)
    uvicorn.run(app, host=settings.control_host, port=settings.control_port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
