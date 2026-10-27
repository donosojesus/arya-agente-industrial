"""Healthcheck del contenedor ot-gateway: sano solo si recibe OPC UA y escribe en el historian."""

from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    url = f"http://127.0.0.1:{os.environ.get('GATEWAY_PORT', '8081')}/healthz"
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
