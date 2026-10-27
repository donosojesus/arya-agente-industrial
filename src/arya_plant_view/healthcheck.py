"""Healthcheck del contenedor plant-view: `python -m arya_plant_view.healthcheck`.

Sano solo si el cliente OPC UA esta conectado y recibe muestras recientes.
"""

from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    url = f"http://127.0.0.1:{os.environ.get('VIEW_PORT', '8080')}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            if response.status == 200:
                print("healthy")
                return 0
            print(f"unhealthy: status {response.status}")
    except Exception as exc:
        print(f"unhealthy: {type(exc).__name__}: {exc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
