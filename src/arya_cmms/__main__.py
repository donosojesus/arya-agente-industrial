"""Punto de entrada del servicio cmms: `python -m arya_cmms`."""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

from .app import ConfigError, app_from_env


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        app = app_from_env()
    except ConfigError as exc:
        print(f"CONFIG ERROR: {exc}", file=sys.stderr)
        return 2
    uvicorn.run(app, host=os.environ.get("CMMS_HOST", "127.0.0.1"), port=int(os.environ.get("CMMS_PORT", "8082")), log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
