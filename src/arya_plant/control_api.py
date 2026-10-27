"""API local de controles de demostracion (uso exclusivo del presentador).

Se publica solo en loopback del notebook y exige un token Bearer. No expone la
causa de la falla.
"""

from __future__ import annotations

import hmac
import logging
from typing import Literal
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .config import PlantSettings
from .runtime import PlantRuntime

from .simulator import MAX_FAULT_DURATION_S, MAX_SCHEDULE_DELAY_S, MIN_FAULT_DURATION_S, ScenarioConflict

log = logging.getLogger("arya.plant.control")

class InjectFaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: float | None = Field(default=None, ge=MIN_FAULT_DURATION_S, le=MAX_FAULT_DURATION_S)
    scenario: Literal["alpha", "bravo", "charlie"] | None = None

class ScheduleFaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delay_seconds: float = Field(gt=0, le=MAX_SCHEDULE_DELAY_S)
    duration_seconds: float | None = Field(default=None, ge=MIN_FAULT_DURATION_S, le=MAX_FAULT_DURATION_S)
    scenario: Literal["alpha", "bravo", "charlie"] | None = None

class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

def create_control_app(runtime: PlantRuntime, settings: PlantSettings, manage_runtime: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if manage_runtime:
            await runtime.start()
        try:
            yield
        finally:
            if manage_runtime:
                await runtime.stop()

    app = FastAPI(
        title="ARYA plant - demo control API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=False,
        max_age=600,
    )

    def require_token(authorization: str | None = Header(default=None)) -> None:
        scheme, _, presented = (authorization or "").partition(" ")
        valid = scheme.lower() == "bearer" and hmac.compare_digest(
            presented.strip().encode("utf-8"), settings.control_token.encode("utf-8")
        )
        if not valid:
            raise HTTPException(
                status_code=401,
                detail="missing or invalid demo control token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def state(message: str) -> dict[str, object]:
        return {"message": message, **runtime.simulator.scenario_state()}

    @app.get("/healthz")
    async def healthz():
        health = runtime.health()
        return JSONResponse(health, status_code=200 if health["ok"] else 503)

    @app.get("/api/demo/state", dependencies=[Depends(require_token)])
    async def demo_state():
        return state("ok")

    @app.post("/api/demo/inject-fault", dependencies=[Depends(require_token)])
    async def inject_fault(body: InjectFaultRequest | None = None):
        try:
            runtime.simulator.inject_fault(body.duration_seconds if body else None, body.scenario if body else None)
        except ScenarioConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        log.info("demo control: INJECT FAULT run_id=%s", runtime.simulator.run_id)
        return state("Fault injected. Signals will evolve gradually over the configured duration.")

    @app.post("/api/demo/schedule-fault", dependencies=[Depends(require_token)])
    async def schedule_fault(body: ScheduleFaultRequest):
        runtime.simulator.schedule_fault(body.delay_seconds, body.duration_seconds, body.scenario)
        log.info("demo control: SCHEDULE FAULT run_id=%s in %.0fs", runtime.simulator.run_id, body.delay_seconds)
        return state("Fault scheduled. It starts on its own once the delay elapses and the plant is NORMAL.")

    @app.post("/api/demo/cancel-schedule", dependencies=[Depends(require_token)])
    async def cancel_schedule(body: EmptyRequest | None = None):
        had = runtime.simulator.cancel_schedule()
        return state("Scheduled fault cancelled." if had else "There was no scheduled fault.")

    @app.post("/api/demo/normal", dependencies=[Depends(require_token)])
    async def normal_operation(body: EmptyRequest | None = None):
        changed = runtime.simulator.normal_operation()
        log.info("demo control: NORMAL OPERATION run_id=%s changed=%s", runtime.simulator.run_id, changed)
        if changed:
            return state(
                "Fault condition removed. Signals return to normal gradually (thermal inertia); "
                "alarms clear when values fall below their limits. Use RESET DEMO to reinitialize immediately."
            )
        return state("No active fault to remove; the plant keeps its current evolution.")

    @app.post("/api/demo/reset", dependencies=[Depends(require_token)])
    async def reset_demo(body: EmptyRequest | None = None):
        runtime.simulator.reset()
        await runtime.publish_now()
        log.info("demo control: RESET DEMO new run_id=%s", runtime.simulator.run_id)
        return state("Simulation reinitialized to the initial state with a new run_id.")

    return app
