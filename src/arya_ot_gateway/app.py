"""API HTTP de solo lectura del OT Gateway (para el lado de IA y para diagnostico).

Todas las rutas son GET. Los datos vivos vienen del cliente OPC UA; la historia,
del historian. Si no hay datos o estan desactualizados, la respuesta lo dice de
forma explicita: nunca se rellenan valores.
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from arya_otclient.contract import PROCESS_NODES
from arya_otclient.poller import OpcUaPoller

from . import __version__
from .analysis import correlation, downsample, iso, summarize
from .config import GatewaySettings
from .historian import SIGNALS, TAG_TO_SIGNAL, Historian
from . import condition as cond

log = logging.getLogger("arya.gateway")
ASSET = "P-101"
ALARM_TEXT = {
    "P101.VIBRATION.HI": ("WARNING", "Vibración alta"),
    "P101.VIBRATION.HIHI": ("ALARM", "Vibración muy alta"),
    "P101.MOTOR_TEMP.HI": ("WARNING", "Temperatura de motor alta"),
    "P101.MOTOR_TEMP.HIHI": ("ALARM", "Temperatura de motor muy alta"),
    "P101.FLOW.LO": ("WARNING", "Caudal bajo"),
    "P101.FLOW.LOLO": ("ALARM", "Caudal muy bajo"),
}


class Recorder:
    """Pasa al historian cada muestra nueva y de buena calidad recibida por OPC UA."""

    def __init__(self, poller: OpcUaPoller, historian: Historian, sample_s: float) -> None:
        self.poller, self.historian, self.sample_s = poller, historian, sample_s
        self._task: asyncio.Task | None = None
        self.last_write_monotonic: float | None = None
        self.errors = 0

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="arya-gateway-recorder")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def alive(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        while True:
            try:
                sample = self.poller.state.sample
                if sample is not None and sample.all_good and self.poller.is_fresh() and sample.source_timestamp:
                    if self.historian.record(sample.source_timestamp.timestamp(), sample.run_id, sample.seq, sample.tags):
                        self.last_write_monotonic = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.errors += 1
                log.exception("historian write failed")
            await asyncio.sleep(self.sample_s / 2)


def _asset(asset: str) -> None:
    if asset.upper().replace("-", "") != "P101":
        raise HTTPException(status_code=404, detail={"error": "unknown_asset", "message": f"Unknown asset. Known: {ASSET}"})


def _signal(name: str) -> str:
    key = name.strip()
    key = TAG_TO_SIGNAL.get(key.upper(), key.lower())
    if key not in SIGNALS:
        raise HTTPException(
            status_code=422,
            detail={"error": "unknown_signal", "message": f"Unknown signal '{name}'.", "valid_signals": list(SIGNALS)},
        )
    return key


def create_gateway_app(
    poller: OpcUaPoller, historian: Historian, settings: GatewaySettings, manage: bool = True
) -> FastAPI:
    recorder = Recorder(poller, historian, settings.sample_s)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if manage:
            poller.start()
        recorder.start()
        try:
            yield
        finally:
            await recorder.stop()
            if manage:
                await poller.stop()

    app = FastAPI(title="ARYA OT Gateway", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.recorder = recorder

    def live() -> dict[str, object]:
        view = poller.public_view()
        if view["snapshot"] is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "no_plant_data",
                    "message": "The gateway has not received any data from the plant OPC UA server.",
                    "opcua_connection": view["connection"]["state"],
                    "last_error": view["connection"]["last_error"],
                },
            )
        return view

    def quality_block(view: dict[str, object]) -> dict[str, object]:
        snap, conn = view["snapshot"], view["connection"]
        block = {
            "data_quality": snap["quality"],
            "source_timestamp": snap["source_timestamp"],
            "age_seconds": snap["age_s"],
            "opcua_connection": conn["state"],
            "run_id": snap["run_id"],
        }
        if snap["quality"] != "GOOD":
            block["warning"] = "Data is NOT current: these are the last values received before the connection problem."
            block["last_error"] = conn["last_error"]
        return block

    def window(minutes: float, scope: str) -> tuple[float, str | None]:
        run_id = None
        if scope == "current_run":
            sample = poller.state.sample
            if sample is None:
                raise HTTPException(status_code=503, detail={"error": "no_plant_data", "message": "Current run is unknown: no plant data received yet."})
            run_id = sample.run_id
        return time.time() - minutes * 60.0, run_id

    @app.get("/healthz")
    async def healthz():
        fresh = poller.is_fresh()
        age = None if recorder.last_write_monotonic is None else time.monotonic() - recorder.last_write_monotonic
        ok = bool(fresh and recorder.alive() and age is not None and age < max(10.0, 5 * settings.sample_s))
        body = {
            "ok": ok, "opcua_connection": poller.state.connection, "has_fresh_sample": fresh,
            "recorder_alive": recorder.alive(), "last_historian_write_age_s": None if age is None else round(age, 1),
            "historian_errors": recorder.errors,
        }
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/api/v1/signals")
    async def signals():
        return {"asset": ASSET, "signals": [{"signal": name, "tag": tag, "unit": unit} for name, (tag, unit) in SIGNALS.items()]}

    @app.get("/api/v1/assets/{asset}/tags")
    async def current_tags(asset: str):
        _asset(asset)
        view = live()
        tags = view["snapshot"]["tags"]
        return {
            "asset": ASSET,
            **quality_block(view),
            "tags": {
                name: {"signal": TAG_TO_SIGNAL.get(name), "value": tags[name]["value"], "unit": tags[name]["unit"], "status": tags[name]["status"]}
                for name in PROCESS_NODES
            },
        }

    @app.get("/api/v1/assets/{asset}/status")
    async def equipment_status(asset: str):
        _asset(asset)
        view = live()
        tags = view["snapshot"]["tags"]
        return {
            "asset": ASSET,
            "description": "Bomba centrífuga de proceso, Área 100",
            **quality_block(view),
            "operating_status": tags["P101.STATUS"]["value"],
            "alarm_level": tags["P101.ALARM_LEVEL"]["value"],
            "active_alarm_count": len(tags["P101.ACTIVE_ALARMS"]["value"] or []),
        }

    @app.get("/api/v1/assets/{asset}/alarms")
    async def active_alarms(asset: str):
        _asset(asset)
        view = live()
        snap = view["snapshot"]
        alarms = []
        for code in snap["tags"]["P101.ACTIVE_ALARMS"]["value"] or []:
            level, text = ALARM_TEXT.get(code, ("WARNING", code))
            tag = code.rsplit(".", 1)[0]
            alarms.append({
                "code": code, "priority": level, "description": text, "tag": tag,
                "current_value": snap["tags"].get(tag, {}).get("value"), "unit": snap["tags"].get(tag, {}).get("unit"),
                "limit": poller.state.limits.get(code), "active_since": iso(historian.active_since(snap["run_id"], code)),
            })
        return {"asset": ASSET, **quality_block(view), "alarm_level": snap["tags"]["P101.ALARM_LEVEL"]["value"],
                "active_alarms": alarms, "configured_limits": poller.state.limits}

    @app.get("/api/v1/assets/{asset}/history")
    async def history(
        asset: str,
        signals: str = Query(..., min_length=1, max_length=200, description="Lista separada por comas"),
        minutes: float = Query(30.0, ge=1, le=1440),
        max_points: int = Query(40, ge=5, le=500),
        scope: Literal["current_run", "all"] = "current_run",
    ):
        _asset(asset)
        names = list(dict.fromkeys(_signal(s) for s in signals.split(",") if s.strip()))
        if not names:
            raise HTTPException(status_code=422, detail={"error": "no_signals", "valid_signals": list(SIGNALS)})
        since, run_id = window(minutes, scope)
        rows = historian.series(names, since, run_id)
        result: dict[str, object] = {"asset": ASSET, "source": "historian", "window_minutes": minutes, "scope": scope, "run_id": run_id, "signals": {}}
        if not rows:
            result["message"] = "The historian has no samples for this window."
            return result
        times = [r[0] for r in rows]
        result["note"] = f"History available covers {round((times[-1] - times[0]) / 60.0, 1)} of the requested {minutes} minutes."
        for i, name in enumerate(names, start=1):
            pairs = [(t, r[i]) for t, r in zip(times, rows) if r[i] is not None]
            ts, vs = [p[0] for p in pairs], [p[1] for p in pairs]
            if not vs:
                result["signals"][name] = {"unit": SIGNALS[name][1], "message": "no samples"}
                continue
            result["signals"][name] = {"tag": SIGNALS[name][0], "unit": SIGNALS[name][1], **summarize(ts, vs), "points": downsample(ts, vs, max_points)}
        return result

    @app.get("/api/v1/assets/{asset}/compare")
    async def compare(
        asset: str,
        signal_a: str = Query(..., max_length=60),
        signal_b: str = Query(..., max_length=60),
        minutes: float = Query(30.0, ge=1, le=1440),
        scope: Literal["current_run", "all"] = "current_run",
    ):
        _asset(asset)
        a, b = _signal(signal_a), _signal(signal_b)
        if a == b:
            raise HTTPException(status_code=422, detail={"error": "same_signal", "message": "Choose two different signals."})
        since, run_id = window(minutes, scope)
        rows = [r for r in historian.series([a, b], since, run_id) if r[1] is not None and r[2] is not None]
        result: dict[str, object] = {"asset": ASSET, "source": "historian", "window_minutes": minutes, "scope": scope, "run_id": run_id}
        if len(rows) < 30:
            result["message"] = f"Not enough historian samples to compare ({len(rows)} found, 30 needed)."
            return result
        times, va, vb = [r[0] for r in rows], [r[1] for r in rows], [r[2] for r in rows]
        sa, sb = summarize(times, va), summarize(times, vb)
        result[a] = {"unit": SIGNALS[a][1], **sa}
        result[b] = {"unit": SIGNALS[b][1], **sb}
        result["correlation"] = correlation(va, vb)
        da, db = sa["deviation"], sb["deviation"]
        if da and db:
            lead = round(db["seconds_ago"] - da["seconds_ago"], 1)  # >0: b comenzo antes que a
            result["which_deviated_first"] = b if lead > 0 else a
            result["lead_seconds"] = abs(lead)
        return result

    @app.get("/api/v1/assets/{asset}/alarm-events")
    async def alarm_events(asset: str, minutes: float = Query(60.0, ge=1, le=1440), scope: Literal["current_run", "all"] = "current_run"):
        _asset(asset)
        since, run_id = window(minutes, scope)
        events = [
            {"time": iso(ts), "run_id": rid, "code": code, "state": state, "description": ALARM_TEXT.get(code, ("", code))[1]}
            for ts, rid, code, state in historian.alarm_events(since, run_id)
        ]
        return {"asset": ASSET, "source": "historian", "window_minutes": minutes, "scope": scope, "events": events}

    # ------------------------------------------------------------------ condicion de 6 meses (medallon)
    store = cond.ConditionStore(historian.path)
    app.state.condition = store
    condition_lock = asyncio.Lock()

    async def gold() -> list[dict[str, object]]:
        async with condition_lock:
            await asyncio.to_thread(store.ensure)  # genera la primera vez o si el historial tiene mas de un dia
        # La planta publica por OPC UA que perfil de historial acompaña al ensayo (H2 = escenario C).
        sample = poller.state.sample
        if sample is not None:
            store.set_variant("incipient" if sample.history_profile == "H2" else "healthy")
        return store.gold()

    def simulated() -> dict[str, object]:
        return {"simulated": True, "note": "Historial de 6 meses SIMULADO a partir del modelo de la bomba y su ficha técnica (FT-P101-001)."}

    @app.get("/api/v1/assets/{asset}/condition/overview")
    async def condition_overview(asset: str):
        _asset(asset)
        days = await gold()
        compare = cond.compare_periods(days, 30, 14)
        projection = cond.project(days, "vibration", 4.5)
        keep = ("trend", "limit", "weeks_to_limit", "date_to_limit", "message", "caveat")
        return {"asset": ASSET, **simulated(), "medallion": store.layers(), "comparison": compare,
                "vibration_projection": {"limit_meaning": "4,5 mm/s: inicio de la zona C (ISO 10816-3) y advertencia del sistema de control",
                                         **{k: projection[k] for k in keep if k in projection}},
                "vibration_zones": {"A": "< 2,3 mm/s", "B": "2,3 a 4,5 mm/s", "C": "4,5 a 7,1 mm/s", "D": "> 7,1 mm/s"},
                "source_document": "FT-P101-001"}

    @app.get("/api/v1/assets/{asset}/condition/daily")
    async def condition_daily(asset: str, days: int = Query(180, ge=7, le=200), step: Literal["day", "week"] = "week"):
        _asset(asset)
        rows = (await gold())[-days:]
        if step == "week":
            weeks = []
            for i in range(0, len(rows), 7):
                chunk = rows[i:i + 7]
                weeks.append({"from": chunk[0]["day"], "to": chunk[-1]["day"],
                              **{k: round(statistics.median(float(c[k]) for c in chunk), 3) for k in
                                 ("vibration_p95", "temp_norm_p50", "current_norm_p50", "pressure_deficit_pct_p50", "flow_mean")},
                              "run_hours": round(sum(float(c["run_hours"]) for c in chunk), 1), "starts": sum(int(c["starts"]) for c in chunk)})
            rows = weeks
        return {"asset": ASSET, **simulated(), "layer": "oro", "step": step, "count": len(rows), "rows": rows}

    @app.get("/api/v1/assets/{asset}/condition/compare")
    async def condition_compare(asset: str, baseline_days: int = Query(30, ge=7, le=90), recent_days: int = Query(14, ge=7, le=60)):
        _asset(asset)
        return {"asset": ASSET, **simulated(), **cond.compare_periods(await gold(), baseline_days, recent_days)}

    @app.get("/api/v1/assets/{asset}/condition/projection")
    async def condition_projection(asset: str, signal: Literal["vibration", "temp_norm", "pressure_deficit_pct"] = "vibration",
                                   limit: float | None = Query(None, gt=0, le=200)):
        _asset(asset)
        default = {"vibration": (4.5, "inicio de la zona C (ISO 10816-3) y advertencia del sistema de control"),
                   "temp_norm": (75.0, "advertencia de temperatura de motor"),
                   "pressure_deficit_pct": (5.0, "déficit de presión respecto de la curva usado como criterio de la planta")}[signal]
        result = cond.project(await gold(), signal, limit if limit is not None else default[0])
        return {"asset": ASSET, **simulated(), "limit_meaning": default[1] if limit is None else "límite indicado en la consulta", **result}

    @app.get("/api/v1/historian/stats")
    async def historian_stats():
        stats = historian.stats()
        return {"samples": stats["samples"], "first_sample": iso(stats["first_ts"]), "last_sample": iso(stats["last_ts"])}

    return app
