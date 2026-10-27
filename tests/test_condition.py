"""Historial de condicion de 6 meses: medallon, comparacion, proyeccion y API del gateway."""

from __future__ import annotations

import time

import httpx
import pytest

from arya_ot_gateway import condition as cond
from arya_ot_gateway.app import create_gateway_app
from arya_ot_gateway.config import GatewaySettings
from arya_ot_gateway.historian import Historian
from arya_otclient.poller import OpcUaPoller

from conftest import assert_no_leak

NOW = time.mktime((2026, 10, 23, 12, 0, 0, 0, 0, -1))
P = "/api/v1/assets/P-101/condition"
TOKEN = "token-de-prueba"


@pytest.fixture(scope="module")
def layers():
    out = {}
    for variant in cond.VARIANTS:
        bronze = cond.generate_bronze(variant, NOW)
        silver, dropped = cond.build_silver(bronze)
        out[variant] = (bronze, silver, dropped, cond.build_gold(bronze, silver))
    return out


def test_generation_is_deterministic_and_covers_six_months(layers):
    bronze, silver, dropped, gold = layers["healthy"]
    assert cond.generate_bronze("healthy", NOW)[:50] == bronze[:50]
    assert len(bronze) == cond.DAYS * 144 + 1 and 180 <= len(gold) <= 184
    assert all(dropped[k] > 0 for k in ("gaps", "stopped", "startup", "spikes"))  # la plata limpia lo que trae el bronce
    assert len(silver) < len(bronze)
    assert any(g["starts"] for g in gold) and max(g["run_hours"] for g in gold) <= 24.0


def test_recorded_incidents_appear_in_the_history(layers):
    gold = {g["day"]: g for g in layers["healthy"][3]}
    assert gold["2026-05-21"]["temp_norm_p50"] > gold["2026-05-10"]["temp_norm_p50"] + 4  # WO-2026-0281
    assert gold["2026-07-08"]["pressure_deficit_pct_p50"] > 5 and gold["2026-07-08"]["current_norm_p50"] < 11.2  # WO-2026-0317
    assert abs(gold["2026-07-15"]["pressure_deficit_pct_p50"]) < 1  # despues de la limpieza del filtro


def test_healthy_history_has_no_relevant_trend(layers):
    gold = layers["healthy"][3]
    compare = cond.compare_periods(gold, 30, 14)
    assert compare["vibration_zone_recent"] == "A" and compare["over_follow_up_threshold_since"] is None
    for signal, limit in (("vibration", 4.5), ("temp_norm", 75.0), ("pressure_deficit_pct", 5.0)):
        assert cond.project(gold, signal, limit)["trend"] == "sin_tendencia_relevante"


def test_incipient_wear_stays_below_alarm_and_projects_a_range(layers):
    incipient, healthy = layers["incipient"][3], layers["healthy"][3]
    assert incipient[:100] == healthy[:100]  # la diferencia esta solo en las ultimas semanas
    assert max(g["vibration_p95"] for g in incipient) < 4.5  # nunca llega a la advertencia del sistema de control
    compare = cond.compare_periods(incipient, 30, 14)
    assert compare["vibration_zone_recent"] == "B" and compare["vibration_over_reference_pct"] > 25
    assert compare["over_follow_up_threshold_since"] is not None
    assert abs(compare["signals"]["pressure_deficit_pct"]["recent"]) < 1  # la parte hidraulica sigue en su curva
    proj = cond.project(incipient, "vibration", 4.5)
    weeks = proj["weeks_to_limit"]
    assert proj["trend"] == "creciente" and 1 < weeks["early"] < weeks["central"] < weeks["late"] < 12
    assert proj["date_to_limit"]["early"] < proj["date_to_limit"]["late"] and "no predice" in proj["caveat"]


def test_curve_matches_the_datasheet():
    assert round(cond.expected_pressure(62.0), 2) == 4.81
    assert cond.vibration_zone(2.0) == "A" and cond.vibration_zone(3.0) == "B" and cond.vibration_zone(5.0) == "C" and cond.vibration_zone(8) == "D"


async def test_gateway_condition_api_is_read_only_and_hides_the_variant(tmp_path):
    settings = GatewaySettings(opcua_endpoint="opc.tcp://127.0.0.1:9/none", historian_path=str(tmp_path / "h.sqlite3"))
    app = create_gateway_app(OpcUaPoller(settings.opcua_endpoint), Historian(settings.historian_path), settings, manage=False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as client:
        overview = (await client.get(f"{P}/overview")).json()
        assert overview["simulated"] is True and overview["medallion"]["gold_days"] > 150
        assert overview["comparison"]["vibration_zone_recent"] == "A"
        weekly = (await client.get(f"{P}/daily", params={"step": "week"})).json()
        assert 24 <= weekly["count"] <= 27 and "vibration_p95" in weekly["rows"][0]
        assert (await client.get(f"{P}/projection")).json()["trend"] == "sin_tendencia_relevante"
        assert (await client.post("/api/demo/condition", json={"variant": "incipient"})).status_code in (404, 405)
        app.state.condition.set_variant("incipient")  # lo que hace el gateway cuando la planta publica H2
        assert (await client.get(f"{P}/projection", params={"signal": "vibration"})).json()["trend"] == "creciente"
        for path in ("/overview", "/daily", "/compare", "/projection"):
            text = (await client.get(P + path)).text
            assert "incipient" not in text and "healthy" not in text and "variant" not in text  # la variante no se revela
            assert_no_leak(text)
