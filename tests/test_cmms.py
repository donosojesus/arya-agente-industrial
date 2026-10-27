"""CMMS ficticio: consulta, borradores del agente y aprobacion humana."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from arya_cmms.app import ConfigError, create_cmms_app
from arya_cmms.store import WorkOrderStore

SEED = str(Path(__file__).resolve().parents[1] / "data" / "work-orders" / "seed.json")
AGENT = {"Authorization": "Bearer agent-key-0123456789abcdefghij"}
HUMAN = {"Authorization": "Bearer human-token-0123456789abcdefgh"}
DRAFT = {
    "asset": "P101", "title": "Vibración y temperatura elevadas en P-101",
    "problem": "Vibración en 8,1 mm/s y temperatura de motor en 90 °C en aumento sostenido.",
    "probable_cause": "Degradación de la lubricación del rodamiento.",
    "recommended_action": "Aplicar bloqueo, inspeccionar y relubricar el rodamiento lado acople.",
    "risk": "MEDIUM", "evidence": ["Historian: vibración +300 % en 3 min", "WO-2026-0142", "SOP-MNT-014"],
}


@pytest.fixture
async def cmms(tmp_path):
    store = WorkOrderStore(str(tmp_path / "cmms.sqlite3"), SEED)
    app = create_cmms_app(store, AGENT["Authorization"][7:], HUMAN["Authorization"][7:], ["http://127.0.0.1:8080"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://cmms") as client:
        yield client, store, tmp_path
    store.close()


async def test_search_and_get_historical_orders(cmms):
    client, _, _ = cmms
    assert (await client.get("/healthz")).json() == {"ok": True, "work_orders": 5}
    p101 = (await client.get("/api/v1/work-orders", params={"asset": "P-101", "limit": 10})).json()
    assert p101["count"] == 4 and all(o["asset"] == "P-101" for o in p101["work_orders"])
    assert p101["work_orders"][0]["id"] == "WO-2026-0317"  # la mas reciente primero
    assert (await client.get("/api/v1/work-orders", params={"asset": "p101", "limit": 10})).json()["count"] == 4
    vib = (await client.get("/api/v1/work-orders", params={"asset": "P-101", "q": "vibracion alarma grasa degradada"})).json()
    assert vib["work_orders"][0]["id"] == "WO-2026-0142"  # busqueda sin tildes
    ranked = (await client.get("/api/v1/work-orders", params={"asset": "P-101", "q": "vibracion temperatura rodamiento"})).json()
    assert ranked["work_orders"][0]["id"] == "WO-2026-0142"  # la que mas menciona los terminos va primero
    flow = (await client.get("/api/v1/work-orders", params={"q": "caída de caudal"})).json()
    assert flow["work_orders"][0]["id"] == "WO-2026-0317"
    assert (await client.get("/api/v1/work-orders", params={"q": "zzzz inexistente"})).json()["count"] == 0
    one = (await client.get("/api/v1/work-orders/wo-2026-0142")).json()
    assert one["status"] == "CLOSED" and "lubricación insuficiente" in one["findings"]
    assert (await client.get("/api/v1/work-orders/WO-0000-0000")).status_code == 404
    assert (await client.get("/api/v1/work-orders", params={"limit": 0})).status_code == 422


async def test_agent_creates_only_drafts_and_cannot_approve(cmms):
    client, _, _ = cmms
    assert (await client.post("/api/v1/work-orders/drafts", json=DRAFT)).status_code == 401
    assert (await client.post("/api/v1/work-orders/drafts", json=DRAFT, headers=HUMAN)).status_code == 401
    for bad in ({**DRAFT, "risk": "EXTREME"}, {**DRAFT, "evidence": []}, {**DRAFT, "status": "OPEN"},
                {k: v for k, v in DRAFT.items() if k != "problem"}, {**DRAFT, "title": "x"}):
        assert (await client.post("/api/v1/work-orders/drafts", json=bad, headers=AGENT)).status_code == 422
    response = await client.post("/api/v1/work-orders/drafts", json=DRAFT, headers=AGENT)
    assert response.status_code == 201
    draft = response.json()
    assert draft["id"] == "WO-DRAFT-0031" and draft["status"] == "DRAFT_PENDING_APPROVAL"
    assert draft["asset"] == "P-101" and draft["created_by"] == "ARYA (AI agent)" and draft["requires_human_approval"] is True
    # La clave del agente NO sirve para aprobar, rechazar ni reiniciar.
    body = {"approver": "ARYA"}
    for path in (f"/api/v1/work-orders/{draft['id']}/approve", f"/api/v1/work-orders/{draft['id']}/reject", "/api/v1/admin/reset"):
        assert (await client.post(path, json=body, headers=AGENT)).status_code == 401
        assert (await client.post(path, json=body)).status_code == 401
    assert (await client.get(f"/api/v1/work-orders/{draft['id']}")).json()["status"] == "DRAFT_PENDING_APPROVAL"


async def test_human_approval_and_rejection(cmms):
    client, _, _ = cmms
    d1 = (await client.post("/api/v1/work-orders/drafts", json=DRAFT, headers=AGENT)).json()
    d2 = (await client.post("/api/v1/work-orders/drafts", json=DRAFT, headers=AGENT)).json()
    assert (d1["id"], d2["id"]) == ("WO-DRAFT-0031", "WO-DRAFT-0032")
    assert (await client.post(f"/api/v1/work-orders/{d1['id']}/approve", json={}, headers=HUMAN)).status_code == 422  # falta quien aprueba
    approved = (await client.post(f"/api/v1/work-orders/{d1['id']}/approve", json={"approver": "J. Donoso"}, headers=HUMAN)).json()
    assert approved["status"] == "OPEN" and approved["id"].startswith("WO-") and "DRAFT" not in approved["id"]
    assert approved["draft_id"] == "WO-DRAFT-0031" and approved["approved_by"] == "J. Donoso" and approved["requires_human_approval"] is False
    assert (await client.get(f"/api/v1/work-orders/{d1['id']}")).status_code == 404  # el borrador paso a ser la orden
    assert (await client.get(f"/api/v1/work-orders/{approved['id']}")).json()["status"] == "OPEN"
    assert (await client.post(f"/api/v1/work-orders/{approved['id']}/approve", json={"approver": "X Y"}, headers=HUMAN)).status_code == 409
    rejected = (await client.post(f"/api/v1/work-orders/{d2['id']}/reject", json={"approver": "J. Donoso", "comment": "Duplicada"}, headers=HUMAN)).json()
    assert rejected["status"] == "REJECTED" and rejected["decision_comment"] == "Duplicada"
    assert (await client.post("/api/v1/work-orders/WO-2026-0142/approve", json={"approver": "X Y"}, headers=HUMAN)).status_code == 409
    assert (await client.post("/api/v1/work-orders/NOPE/approve", json={"approver": "X Y"}, headers=HUMAN)).status_code == 404
    open_orders = (await client.get("/api/v1/work-orders", params={"status": "OPEN"})).json()
    assert open_orders["count"] == 1


async def test_orders_persist_and_reset_restores_the_initial_state(cmms):
    client, store, tmp_path = cmms
    await client.post("/api/v1/work-orders/drafts", json=DRAFT, headers=AGENT)
    reopened = WorkOrderStore(str(tmp_path / "cmms.sqlite3"), SEED)  # reinicio del servicio
    assert len(reopened.search(None, None, None, 100)) == 6
    reopened.close()
    assert (await client.post("/api/v1/admin/reset", headers=HUMAN)).json() == {"reset": True, "work_orders": 5}
    assert (await client.get("/api/v1/work-orders", params={"limit": 50})).json()["count"] == 5
    again = (await client.post("/api/v1/work-orders/drafts", json=DRAFT, headers=AGENT)).json()
    assert again["id"] == "WO-DRAFT-0031"  # numeracion reproducible tras el reset


def test_agent_and_human_credentials_must_differ(tmp_path):
    store = WorkOrderStore(":memory:", SEED)
    with pytest.raises(ConfigError):
        create_cmms_app(store, "same-key-0123456789abcdefghijk", "same-key-0123456789abcdefghijk", [])
    store.close()
