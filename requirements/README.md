Versiones fijadas y comprobadas con Python 3.12 (6 de octubre de 2026).

- `runtime.lock`: lo que instalan las imágenes Docker.
- `dev.lock`: lo anterior más las herramientas de prueba.

Dependencias directas: asyncua, fastapi, uvicorn (runtime); pytest, pytest-asyncio, httpx (pruebas).
Para regenerar: `uv pip compile --python-version 3.12` sobre esa lista.
