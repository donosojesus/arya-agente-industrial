"""Punto de entrada del servicio ot-gateway: `python -m arya_ot_gateway`."""

from __future__ import annotations

import logging
import sys

import uvicorn

from arya_otclient.poller import OpcUaPoller

from .app import create_gateway_app
from .config import GatewaySettings
from .historian import Historian


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("asyncua").setLevel(logging.CRITICAL)
    settings = GatewaySettings.from_env()
    historian = Historian(settings.historian_path, settings.retention_days)
    poller = OpcUaPoller(settings.opcua_endpoint, settings.sample_s, settings.stale_after_s)
    app = create_gateway_app(poller, historian, settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
