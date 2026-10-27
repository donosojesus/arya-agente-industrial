"""Punto de entrada de la pantalla de demostracion: `python -m arya_ui`."""

from __future__ import annotations

import logging
import sys

import uvicorn

from .app import UiSettings, create_ui_app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = UiSettings.from_env()
    uvicorn.run(create_ui_app(settings), host=settings.host, port=settings.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
