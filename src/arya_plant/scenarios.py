"""Escenarios de falla y su causa real (ground truth). SOLO uso interno del simulador.

Los identificadores publicos ("alpha", "bravo") son neutros a proposito: la
causa real no debe salir por OPC UA, por las APIs, por la pantalla ni por los
logs. Este modulo no debe importarse desde el transporte ni desde plant-view.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import FaultProfile


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    profile: FaultProfile
    ground_truth: dict[str, str]
    duration_s: float | None = None  # duracion propia del escenario si no se indica otra


SCENARIOS: dict[str, Scenario] = {
    # Sube vibracion y, con retraso, temperatura; corriente algo mayor; caudal y presion bajan poco.
    "alpha": Scenario(
        "alpha",
        FaultProfile(
            vibration_gain=6.5, vibration_jitter=0.18, temp_gain=40.0, current_gain=1.4,
            flow_loss=0.08, pressure_loss=0.07, rpm_drop=4.0,
        ),
        {
            "fault_id": "bearing_lubrication_degradation",
            "component": "P-101 drive-end bearing",
            "description": "Progressive loss of bearing lubrication increasing friction and vibration.",
        },
    ),
    # Cae el caudal y la presion; la corriente BAJA (menos carga hidraulica); temperatura casi igual;
    # la vibracion sube poco pero se vuelve irregular.
    "bravo": Scenario(
        "bravo",
        FaultProfile(
            vibration_gain=1.6, vibration_jitter=0.25, temp_gain=3.0, current_gain=-1.7,
            flow_loss=0.36, pressure_loss=0.19, rpm_drop=-3.0,
        ),
        {
            "fault_id": "suction_strainer_clogging",
            "component": "P-101 suction strainer STR-101",
            "description": "Progressive clogging of the suction strainer starving the pump and causing incipient cavitation.",
        },
    ),
    # Desgaste incipiente (analisis predictivo): sin alarmas. En vivo, la bomba queda en los valores con que termina
    # el historial de 6 meses con desgaste del gateway (vibracion ~3,2 mm/s, motor +3 C, corriente algo mayor).
    "charlie": Scenario(
        "charlie",
        FaultProfile(vibration_gain=1.2, vibration_jitter=0.06, temp_gain=3.0, current_gain=0.12),
        {
            "fault_id": "incipient_bearing_wear_overdue_lubrication",
            "component": "P-101 drive-end bearing",
            "description": "Incipient bearing wear after the 4-month relubrication interval was missed; still below alarm limits.",
        },
        duration_s=30.0,
    ),
}

DEFAULT_SCENARIO = "alpha"
