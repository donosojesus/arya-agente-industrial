"""Servidor de la pantalla dividida y pasarela acotada hacia el agente y el CMMS."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__

STATIC_DIR = Path(__file__).parent / "static"

# Unicas rutas que la pantalla puede alcanzar. Nada de administracion ni de creacion de borradores.
AGENT_ROUTES = (
    ("GET", re.compile(r"^api/v1/(status|trace|feed)$")),
    ("POST", re.compile(r"^api/v1/(chat|proactive|conversation/clear)$")),
    ("POST", re.compile(r"^api/v1/work-orders/[A-Za-z0-9\-]{4,30}/sync$")),
)
CMMS_ROUTES = (
    ("GET", re.compile(r"^api/v1/work-orders(/[A-Za-z0-9\-]{4,30})?$")),
    ("GET", re.compile(r"^api/v1/planned-shutdowns$")),
    ("POST", re.compile(r"^api/v1/work-orders/[A-Za-z0-9\-]{4,30}/(approve|reject)$")),
)
# Grafico de evidencia del analisis predictivo: solo lectura de la capa oro del historial de 6 meses.
GATEWAY_ROUTES = (
    ("GET", re.compile(r"^api/v1/assets/P-101/condition/(daily|projection)$")),
)
# Controles de la simulacion visibles en la pantalla: falla y vuelta a normal. RESET y programar quedan en el panel DEMO.
CONTROL_ROUTES = (
    ("GET", re.compile(r"^api/demo/state$")),
    ("POST", re.compile(r"^api/demo/(inject-fault|normal)$")),
)
_FORWARD_HEADERS = ("authorization", "content-type", "last-event-id")


@dataclass(frozen=True)
class UiSettings:
    host: str = "127.0.0.1"
    port: int = 8090
    agent_url: str = "http://127.0.0.1:8091"
    cmms_url: str = "http://127.0.0.1:8082"
    control_url: str = "http://127.0.0.1:9001"
    control_token: str = ""  # si esta, la pantalla puede simular la falla y volver a normal sin pedir el token
    gateway_url: str = "http://127.0.0.1:8081"  # solo lectura: datos del grafico de evidencia
    plant_view_port: int = 8080

    @classmethod
    def from_env(cls) -> "UiSettings":
        env = os.environ.get
        return cls(host=env("UI_HOST", cls.host).strip(), port=int(env("UI_PORT", cls.port)),
                   agent_url=env("AGENT_URL", cls.agent_url).strip().rstrip("/"), cmms_url=env("CMMS_URL", cls.cmms_url).strip().rstrip("/"),
                   control_url=env("CONTROL_URL", cls.control_url).strip().rstrip("/"),
                   control_token=env("DEMO_CONTROL_TOKEN", "").strip(),
                   gateway_url=env("GATEWAY_URL", cls.gateway_url).strip().rstrip("/"),
                   plant_view_port=int(env("PLANT_VIEW_PUBLIC_PORT", cls.plant_view_port)))


def _allowed(routes, method: str, path: str) -> bool:
    return any(method == m and pattern.match(path) for m, pattern in routes)


def create_ui_app(settings: UiSettings, agent: httpx.AsyncClient | None = None, cmms: httpx.AsyncClient | None = None,
                  control: httpx.AsyncClient | None = None, gateway: httpx.AsyncClient | None = None) -> FastAPI:
    agent = agent or httpx.AsyncClient(base_url=settings.agent_url, timeout=httpx.Timeout(150.0, connect=3.0))
    cmms = cmms or httpx.AsyncClient(base_url=settings.cmms_url, timeout=httpx.Timeout(10.0, connect=3.0))
    control = control or httpx.AsyncClient(base_url=settings.control_url, timeout=httpx.Timeout(8.0, connect=3.0))
    gateway = gateway or httpx.AsyncClient(base_url=settings.gateway_url, timeout=httpx.Timeout(20.0, connect=3.0))
    app = FastAPI(title="ARYA demo screen", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def no_stale_assets(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    screen_origins = {f"http://127.0.0.1:{settings.port}", f"http://localhost:{settings.port}"}

    async def forward(client: httpx.AsyncClient, service: str, request: Request, path: str, extra_headers: dict[str, str] | None = None):
        headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_HEADERS}
        headers.update(extra_headers or {})
        try:
            if path.endswith("/feed"):  # eventos en vivo: se reenvian a medida que llegan
                upstream = await client.send(client.build_request("GET", "/" + path, params=request.query_params, headers=headers, timeout=None), stream=True)

                async def relay():
                    try:
                        async for chunk in upstream.aiter_raw():
                            yield chunk
                    except httpx.HTTPError:
                        return
                    finally:
                        await upstream.aclose()

                return StreamingResponse(relay(), status_code=upstream.status_code, media_type="text/event-stream",
                                         headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
            upstream = await client.request(request.method, "/" + path, params=request.query_params, headers=headers, content=await request.body())
        except httpx.HTTPError as exc:
            return JSONResponse({"error": f"{service}_unreachable", "message": f"No hay conexión con {service} ({type(exc).__name__})."}, status_code=502)
        return Response(upstream.content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type", "application/json"))

    @app.api_route("/agent/{path:path}", methods=["GET", "POST"])
    async def agent_proxy(path: str, request: Request):
        if not _allowed(AGENT_ROUTES, request.method, path):
            return JSONResponse({"error": "not_allowed"}, status_code=404)
        return await forward(agent, "agent", request, path)

    @app.api_route("/cmms/{path:path}", methods=["GET", "POST"])
    async def cmms_proxy(path: str, request: Request):
        if not _allowed(CMMS_ROUTES, request.method, path):
            return JSONResponse({"error": "not_allowed"}, status_code=404)
        return await forward(cmms, "cmms", request, path)

    @app.get("/gateway/{path:path}")
    async def gateway_proxy(path: str, request: Request):
        if not _allowed(GATEWAY_ROUTES, "GET", path):
            return JSONResponse({"error": "not_allowed"}, status_code=404)
        return await forward(gateway, "gateway", request, path)

    @app.api_route("/control/{path:path}", methods=["GET", "POST"])
    async def control_proxy(path: str, request: Request):
        # El token de control viaja desde el navegador del presentador; este servicio no lo guarda.
        if not _allowed(CONTROL_ROUTES, request.method, path):
            return JSONResponse({"error": "not_allowed"}, status_code=404)
        if settings.control_token and "authorization" not in request.headers:
            # El servidor de la pantalla agrega el token del presentador. Para las acciones exige que la
            # peticion venga de la propia pantalla (el navegador fija Origin y ninguna otra pagina puede falsearlo).
            if request.method == "POST" and request.headers.get("origin", "").rstrip("/") not in screen_origins:
                return JSONResponse({"error": "forbidden", "message": "Solo la pantalla de la demo puede usar estos controles."}, status_code=403)
            return await forward(control, "control", request, path, extra_headers={"Authorization": f"Bearer {settings.control_token}"})
        return await forward(control, "control", request, path)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/config.json")
    async def config():
        return JSONResponse({"plant_view_port": settings.plant_view_port, "simulation_controls": bool(settings.control_token)},
                            headers={"Cache-Control": "no-store"})

    @app.get("/factory")
    async def factory():
        """Del agente a la AI Factory: pagina independiente y de solo lectura (no toca la simulacion)."""
        return FileResponse(STATIC_DIR / "factory.html", headers={"Cache-Control": "no-store"})

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
