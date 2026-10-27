"""Punto de entrada del servicio plant-view: `python -m arya_plant_view`."""

from __future__ import annotations

import logging
import sys

import uvicorn

from .api import create_view_app
from .config import ViewSettings
from arya_otclient.poller import OpcUaPoller


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.CRITICAL)
    settings = ViewSettings.from_env()
    poller = OpcUaPoller(settings.opcua_endpoint, settings.sample_s, settings.stale_after_s)
    app = create_view_app(poller, settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
