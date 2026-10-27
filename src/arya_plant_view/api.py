"""API HTTP de solo lectura y archivos estaticos del SCADA inicial.

No existe ninguna ruta que modifique el proceso y este servicio no conoce el
token de control.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import ViewSettings
from arya_otclient.contract import NAMESPACE_URI, PROCESS_NODES
from arya_otclient.poller import OpcUaPoller

STATIC_DIR = Path(__file__).parent / "static"
_NO_STORE = {"Cache-Control": "no-store"}


def create_view_app(poller: OpcUaPoller, settings: ViewSettings, manage_poller: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if manage_poller:
            poller.start()
        try:
            yield
        finally:
            if manage_poller:
                await poller.stop()

    app = FastAPI(
        title="ARYA plant-view", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.middleware("http")
    async def no_stale_assets(request, call_next):
        # El navegador debe revalidar siempre: tras actualizar la demo no puede quedar un JS/CSS antiguo.
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    @app.get("/healthz")
    async def healthz():
        fresh = poller.is_fresh()
        body = {"ok": fresh, "opcua_connection": poller.state.connection, "has_fresh_sample": fresh}
        return JSONResponse(body, status_code=200 if fresh else 503, headers=_NO_STORE)

    @app.get("/api/telemetry/latest")
    async def latest():
        return JSONResponse(poller.public_view(), headers=_NO_STORE)

    @app.get("/api/config")
    async def config():
        return JSONResponse(
            {
                "asset": "P-101",
                "location": "Notebook · Planta / OT simulada",
                "namespace_uri": NAMESPACE_URI,
                "tags": [{"name": name, **poller.state.metadata.get(name, {})} for name in PROCESS_NODES],
                "limits": poller.state.limits,
                "sample_seconds": settings.sample_s,
                "stale_after_seconds": settings.stale_after_s,
                "control_port": settings.control_port,
            },
            headers=_NO_STORE,
        )

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_STORE)

    @app.get("/compact")
    async def compact():
        """Misma pantalla en disposicion compacta, para ocupar media pantalla junto al agente."""
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_STORE)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
