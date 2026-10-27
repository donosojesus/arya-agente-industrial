"""Healthcheck del contenedor de la pantalla de demostracion."""

from __future__ import annotations

import os
import sys
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{os.environ.get('UI_PORT', '8090')}/healthz", timeout=3) as response:
            if response.status == 200:
                print("healthy")
                return 0
    except Exception as exc:
        print(f"unhealthy: {type(exc).__name__}: {exc}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
