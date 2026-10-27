"""API REST del CMMS ficticio."""

from __future__ import annotations

import hmac
import logging
import os
from typing import Literal

import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .store import STATUS_DRAFT, WorkOrderStore

log = logging.getLogger("arya.cmms")
MIN_KEY_LENGTH = 24


class ConfigError(Exception):
    pass


def _key(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if len(value) < MIN_KEY_LENGTH or value.startswith("replace-"):
        raise ConfigError(f"{name} is missing or too short. Generate it with scripts/start-demo.")
    return value


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    asset: str = Field(min_length=2, max_length=20)
    title: str = Field(min_length=5, max_length=120)
    problem: str = Field(min_length=10, max_length=800)
    probable_cause: str = Field(min_length=5, max_length=500)
    recommended_action: str = Field(min_length=10, max_length=800)
    risk: Literal["LOW", "MEDIUM", "HIGH"]
    evidence: list[str] = Field(min_length=1, max_length=8)
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    work_type: Literal["CORRECTIVE", "PREDICTIVE", "PREVENTIVE"] = "CORRECTIVE"
    planned_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    approver: str = Field(min_length=2, max_length=60)
    comment: str | None = Field(default=None, max_length=300)


LOCAL_TZ = timezone(timedelta(hours=-3))


def _saturday_near(ts: float) -> datetime:
    day = datetime.fromtimestamp(ts, LOCAL_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return day + timedelta(days=(5 - day.weekday() + 3) % 7 - 3)


def shutdown_calendar(now: float) -> list[dict[str, object]]:
    """Paradas trimestrales (la ultima unas 6 semanas atras) y una parada parcial en unas 2 semanas.

    Usa la misma regla que el historial simulado del gateway, de modo que coinciden en cualquier fecha.
    """
    q1, q2 = _saturday_near(now - 132 * 86400), _saturday_near(now - 41 * 86400)
    partial, q3 = _saturday_near(now + 14 * 86400), q2 + timedelta(days=91)
    today = datetime.fromtimestamp(now, LOCAL_TZ).date()
    rows = [(q1, 12, "Parada programada trimestral del Área 100"), (q2, 12, "Parada programada trimestral del Área 100"),
            (partial, 8, "Parada parcial del Área 100: mantención de válvulas de la línea 2; P-101 disponible para intervención"),
            (q3, 12, "Parada programada trimestral del Área 100")]
    out = []
    for day, hours, title in rows:
        out.append({"date": day.date().isoformat(), "start": "07:00", "duration_h": hours, "title": title,
                    "status": "REALIZADA" if day.date() < today else "PROGRAMADA",
                    "days_from_today": (day.date() - today).days})
    return out


def create_cmms_app(store: WorkOrderStore, agent_key: str, approver_token: str, allowed_origins: list[str]) -> FastAPI:
    if hmac.compare_digest(agent_key, approver_token):
        raise ConfigError("CMMS_AGENT_KEY and CMMS_APPROVER_TOKEN must be different")
    app = FastAPI(title="ARYA demo CMMS", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"], allow_credentials=False, max_age=600,
    )

    def bearer(expected: str):
        def check(authorization: str | None = Header(default=None)) -> None:
            scheme, _, presented = (authorization or "").partition(" ")
            if scheme.lower() != "bearer" or not hmac.compare_digest(presented.strip().encode(), expected.encode()):
                raise HTTPException(status_code=401, detail="missing or invalid credential", headers={"WWW-Authenticate": "Bearer"})
        return check

    require_agent, require_human = bearer(agent_key), bearer(approver_token)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "work_orders": len(store.search(None, None, None, 10_000))}

    @app.get("/api/v1/work-orders")
    async def search(
        asset: str | None = Query(None, max_length=20), q: str | None = Query(None, max_length=200),
        status: Literal["DRAFT_PENDING_APPROVAL", "OPEN", "REJECTED", "CLOSED"] | None = None,
        limit: int = Query(5, ge=1, le=50),
    ):
        orders = store.search(asset, q, status, limit)
        return {"source": "CMMS", "count": len(orders), "work_orders": orders}

    @app.get("/api/v1/planned-shutdowns")
    async def planned_shutdowns(asset: str | None = Query(None, max_length=20)):
        """Calendario de paradas del Area 100 (P-101 incluida), calculado respecto de hoy."""
        return {"source": "CMMS · calendario de paradas", "area": "Área 100", "today": datetime.now(LOCAL_TZ).date().isoformat(),
                "shutdowns": shutdown_calendar(time.time())}

    @app.get("/api/v1/work-orders/{order_id}")
    async def get(order_id: str):
        order = store.get(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Work order {order_id} does not exist."})
        return order

    @app.post("/api/v1/work-orders/drafts", status_code=201, dependencies=[Depends(require_agent)])
    async def create_draft(body: DraftRequest):
        order = store.create_draft(body.model_dump())
        log.info("draft created id=%s asset=%s", order["id"], order["asset"])
        return order

    async def decide(order_id: str, body: DecisionRequest, approve: bool):
        current = store.get(order_id)
        if current is None:
            raise HTTPException(status_code=404, detail={"error": "not_found", "message": f"Work order {order_id} does not exist."})
        if current["status"] != STATUS_DRAFT:
            raise HTTPException(status_code=409, detail={"error": "not_a_draft", "message": f"Work order is {current['status']}; only drafts can be decided."})
        order = store.decide(order_id, approve, body.approver, body.comment)
        log.info("draft %s -> %s by a human approver", order_id, order["status"])
        return order

    @app.post("/api/v1/work-orders/{order_id}/approve", dependencies=[Depends(require_human)])
    async def approve(order_id: str, body: DecisionRequest):
        return await decide(order_id, body, True)

    @app.post("/api/v1/work-orders/{order_id}/reject", dependencies=[Depends(require_human)])
    async def reject(order_id: str, body: DecisionRequest):
        return await decide(order_id, body, False)

    @app.post("/api/v1/admin/reset", dependencies=[Depends(require_human)])
    async def reset():
        count = store.reset()
        log.info("CMMS reset to %d historical work orders", count)
        return {"reset": True, "work_orders": count}

    return app


def app_from_env() -> FastAPI:
    store = WorkOrderStore(os.environ.get("CMMS_DB_PATH", "/data/cmms.sqlite3"), os.environ.get("CMMS_SEED_PATH", "/app/data/work-orders/seed.json"))
    origins = [o.strip().rstrip("/") for o in os.environ.get("CMMS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return create_cmms_app(store, _key("CMMS_AGENT_KEY"), _key("CMMS_APPROVER_TOKEN"), origins)
