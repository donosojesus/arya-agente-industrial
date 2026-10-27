"""Pantalla dividida: pasarela acotada hacia el agente y el CMMS, y recursos solo locales."""

from __future__ import annotations

import json
import re

import httpx

from arya_agent.api import create_agent_app
from arya_ui.app import STATIC_DIR, UiSettings, create_ui_app

from conftest import ADMIN_TOKEN, AGENT_KEY, HUMAN_TOKEN, TEST_TOKEN, ScriptedModel, assert_no_leak


async def test_proxy_reaches_only_what_the_screen_needs(agent_stack):
    s = await agent_stack(ScriptedModel(["P-101 está en marcha."]))
    agent_app = create_agent_app(s.agent, s.trace, s.memory, s.settings, run_watcher=False)
    agent_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=agent_app), base_url="http://agent")
    from arya_plant.control_api import create_control_app
    control_app = create_control_app(s.runtime, s.runtime.settings, manage_runtime=False)
    control_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=control_app), base_url="http://control")
    ui = create_ui_app(UiSettings(), agent=agent_client, cmms=s.cmms, control=control_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ui), base_url="http://ui") as client:
        assert (await client.get("/healthz")).json() == {"ok": True}
        assert (await client.get("/config.json")).json() == {"plant_view_port": 8080, "simulation_controls": False}
        status = (await client.get("/agent/api/v1/status")).json()
        assert status["agent"] == "ARYA" and status["process_write_tools"] == []
        answer = (await client.post("/agent/api/v1/chat", json={"message": "¿Cómo está la bomba?"})).json()
        assert answer["answer"] == "P-101 está en marcha."
        assert (await client.get("/agent/api/v1/trace")).json()["events"]
        assert (await client.post("/agent/api/v1/proactive", json={"enabled": True})).json() == {"enabled": True}
        assert (await client.post("/agent/api/v1/conversation/clear")).json() == {"cleared": True}
        orders = (await client.get("/cmms/api/v1/work-orders", params={"asset": "P-101"})).json()
        assert orders["count"] >= 4 and (await client.get("/cmms/api/v1/work-orders/WO-2026-0142")).status_code == 200
        # Aprobar exige el token humano, que solo viaja desde el navegador del presentador.
        draft = (await s.cmms.post("/api/v1/work-orders/drafts", headers={"Authorization": f"Bearer {AGENT_KEY}"}, json={
            "asset": "P-101", "title": "Prueba de aprobación", "problem": "Vibración elevada sostenida.", "probable_cause": "Por determinar",
            "recommended_action": "Inspeccionar el equipo en terreno.", "risk": "LOW", "evidence": ["Historian"]})).json()
        path = f"/cmms/api/v1/work-orders/{draft['id']}/approve"
        assert (await client.post(path, json={"approver": "Ana"})).status_code == 401
        approved = await client.post(path, json={"approver": "Ana"}, headers={"Authorization": f"Bearer {HUMAN_TOKEN}"})
        assert approved.status_code == 200 and approved.json()["status"] == "OPEN"
        # Controles de la simulacion: falla y vuelta a normal, con el token del presentador.
        token = {"Authorization": f"Bearer {TEST_TOKEN}"}
        assert (await client.post("/control/api/demo/inject-fault", json={"scenario": "bravo"})).status_code == 401
        injected = (await client.post("/control/api/demo/inject-fault", json={"scenario": "bravo"}, headers=token)).json()
        assert injected["mode"] == "DEGRADATION" and injected["scenario"] == "bravo"
        assert (await client.post("/control/api/demo/normal", json={}, headers=token)).json()["mode"] in ("RECOVERY", "NORMAL")  # sin degradacion acumulada se recupera al instante
        assert (await client.get("/control/api/demo/state", headers=token)).json()["mode"] in ("RECOVERY", "NORMAL")
        for path in ("/control/api/demo/reset", "/control/api/demo/schedule-fault", "/control/healthz"):
            assert (await client.post(path, json={}, headers=token)).status_code == 404  # RESET y programar quedan en el panel DEMO
        # Lo que la pantalla NO puede alcanzar: administracion, creacion de borradores, rutas arbitrarias.
        for method, url in (("POST", "/agent/api/v1/admin/reset"), ("POST", "/cmms/api/v1/admin/reset"), ("POST", "/cmms/api/v1/work-orders/drafts"),
                            ("GET", "/agent/healthz"), ("GET", "/agent/api/v1/../admin/reset"), ("GET", "/cmms/healthz"), ("POST", "/cmms/api/v1/work-orders")):
            response = await client.request(method, url, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}, json={})
            assert response.status_code in (404, 405), (method, url, response.status_code)
    await agent_client.aclose()
    await control_client.aclose()


async def test_unreachable_agent_is_reported_not_hidden():
    dead = httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=1.0)
    ui = create_ui_app(UiSettings(), agent=dead, cmms=dead)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ui), base_url="http://ui") as client:
        response = await client.get("/agent/api/v1/status")
        assert response.status_code == 502 and response.json()["error"] == "agent_unreachable"
        assert (await client.get("/cmms/api/v1/work-orders")).status_code == 502
        index = await client.get("/")
        assert index.status_code == 200 and "ARYA" in index.text  # la pantalla carga aunque el agente no este
    await dead.aclose()


def test_screen_assets_are_local_only():
    files = sorted(STATIC_DIR.iterdir())
    assert {f.name for f in files} == {"index.html", "arya.css", "arya.js", "inside.js", "voice.js", "factory.html", "factory.css", "factory.js"}
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert_no_leak(text)
        for url in re.findall(r"https?://[^\s\"')]+", text):
            assert url in ("http://", "http://localhost:8095"), url  # hostname local, o la escucha de voz local de Windows
        assert "@import" not in text and "url(" not in text
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for required in ("ARYA", "INSIDE THE AGENT", "APROBAR", "RECHAZAR", "ORDEN DE TRABAJO", "Nemotron", "POR DENTRO", "ARYA por dentro", "LIMPIAR", "CONTROLES DE LA SIMULACIÓN", "SIMULAR FALLA", "VOLVER A NORMAL", "HABLAR"):
        assert required in html
    js = (STATIC_DIR / "arya.js").read_text(encoding="utf-8")
    assert "innerHTML = \"\"" in js and ".innerHTML = e." not in js  # el texto del agente nunca se inserta como HTML
    voice = (STATIC_DIR / "voice.js").read_text(encoding="utf-8")
    assert "localService" in voice  # solo voces locales: nada de voces que requieran Internet
    inside = (STATIC_DIR / "inside.js").read_text(encoding="utf-8")
    # El tablero solo escribe texto del agente con textContent; el unico innerHTML es el armazon fijo de cada tarjeta.
    assert inside.count("innerHTML") == 1 and "No implementado en esta demo" in inside and "TOOL_MAP" in inside


async def test_screen_can_drive_the_simulation_without_a_browser_token(agent_stack):
    from arya_plant.control_api import create_control_app

    s = await agent_stack(ScriptedModel(["ok"]))
    control_app = create_control_app(s.runtime, s.runtime.settings, manage_runtime=False)
    control_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=control_app), base_url="http://control")
    dead = httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=1.0)
    ui = create_ui_app(UiSettings(control_token=TEST_TOKEN), agent=dead, cmms=dead, control=control_client)
    screen = {"Origin": "http://127.0.0.1:8090"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ui), base_url="http://ui") as client:
        assert (await client.get("/config.json")).json()["simulation_controls"] is True
        assert (await client.get("/control/api/demo/state")).json()["mode"] == "NORMAL"  # el servidor agrega el token
        # Otra pagina del mismo equipo, o una peticion sin Origin, no puede provocar la falla.
        for headers in ({}, {"Origin": "http://127.0.0.1:8080"}, {"Origin": "http://evil.example"}):
            assert (await client.post("/control/api/demo/inject-fault", json={}, headers=headers)).status_code == 403
        assert s.runtime.simulator.mode == "NORMAL"
        fault = await client.post("/control/api/demo/inject-fault", json={"scenario": "alpha"}, headers=screen)
        assert fault.status_code == 200 and fault.json()["mode"] == "DEGRADATION"
        back = await client.post("/control/api/demo/normal", json={}, headers={"Origin": "http://localhost:8090"})
        assert back.json()["mode"] in ("RECOVERY", "NORMAL")
        # Las demas acciones siguen fuera de la pantalla, y aprobar ordenes sigue exigiendo su propio token.
        assert (await client.post("/control/api/demo/reset", json={}, headers=screen)).status_code == 404
    await control_client.aclose()
    await dead.aclose()


async def test_factory_page_is_read_only_and_labels_projections():
    dead = httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=1.0)
    ui = create_ui_app(UiSettings(), agent=dead, cmms=dead, control=dead)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ui), base_url="http://ui") as client:
        page = await client.get("/factory")
        assert page.status_code == 200 and "Del agente a la AI Factory" in page.text
        for required in ("MEDIDO EN ESTA SALA", "PROYECCIÓN", "PowerEdge XE7745", "RTX PRO 6000", "Supuestos", "¿CÓMO LA PROTEGEMOS?",
                         "EN ARYA HOY", "REFERENCIA", "PowerProtect Data Manager", "Cyber Recovery", "CyberSense", "IEC 62443",
                         "VER EL STACK COMPLETO", "2-8-5-200", "PowerEdge R670", "PowerScale F710", "Spectrum-4 SN5610", "EN ESTE PILOTO",
                         "Caso de uso piloto", "Probar y validar", "PROTEGER", "DETECTAR", "RECUPERAR", "CrowdStrike Falcon",
                         "PowerScale Cybersecurity Suite", "AI Security and Resilience Datasheet",
                         "¿CÓMO SE CONECTA A SUS DATOS?", "Arquitectura medallón", "RAG", "MCP"):
            assert required in page.text
    screen_js = (STATIC_DIR / "arya.js").read_text(encoding="utf-8")
    auto = screen_js[screen_js.index("function autoTalk()"):].split("\n", 1)[0]
    assert 'setMode("talk")' in auto and "autoTalk();" not in auto  # un aviso saca la pantalla de REPOSO, sin recursion
    js = (STATIC_DIR / "factory.js").read_text(encoding="utf-8")
    assert "POST" not in js and "/control/" not in js  # solo lee: nunca actua sobre la simulacion
    await dead.aclose()


async def test_scenario_c_can_be_simulated_from_the_screen(agent_stack):
    s = await agent_stack(ScriptedModel(["ok"]))
    from arya_plant.control_api import create_control_app
    control_app = create_control_app(s.runtime, s.runtime.settings, manage_runtime=False)
    control_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=control_app), base_url="http://control")
    dead = httpx.AsyncClient(base_url="http://127.0.0.1:9", timeout=1.0)
    ui = create_ui_app(UiSettings(control_token=TEST_TOKEN), agent=dead, cmms=dead, control=control_client)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ui), base_url="http://ui") as client:
        fault = await client.post("/control/api/demo/inject-fault", json={"scenario": "charlie"}, headers={"Origin": "http://127.0.0.1:8090"})
        assert fault.status_code == 200 and fault.json()["scenario"] == "charlie" and fault.json()["fault_duration_s"] == 30.0
    assert s.runtime.simulator.snapshot().values["RUN.HISTORY_PROFILE"] == "H2"
    await dead.aclose()
