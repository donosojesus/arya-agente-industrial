"""Extremo a extremo con PROCESOS reales (los mismos comandos que usan los contenedores).

plant y plant-view se lanzan como procesos separados; se validan healthchecks,
preflight, scripts de control y la perdida/recuperacion de la conexion OPC UA.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from conftest import TEST_TOKEN, assert_no_leak, free_port

ROOT = Path(__file__).resolve().parents[1]
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def wait_until(predicate, timeout: float = 30.0, interval: float = 0.25, what: str = "condition"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            last = predicate()
            if last:
                return last
        except Exception as exc:  # el servicio aun no responde
            last = exc
        time.sleep(interval)
    raise AssertionError(f"{what} not reached in {timeout}s (last: {last!r})")


class Stack:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.opc_port, self.control_port, self.view_port = free_port(), free_port(), free_port()
        self.control = f"http://127.0.0.1:{self.control_port}"
        self.view = f"http://127.0.0.1:{self.view_port}"
        base = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONUNBUFFERED": "1"}
        # Igual que en Compose: el servidor escucha en 0.0.0.0 y el cliente usa otro nombre de host.
        self.plant_env = {
            **base,
            "DEMO_CONTROL_TOKEN": TEST_TOKEN,
            "OPCUA_ENDPOINT": f"opc.tcp://0.0.0.0:{self.opc_port}/arya/plant/",
            "CONTROL_HOST": "127.0.0.1",
            "CONTROL_PORT": str(self.control_port),
            "CONTROL_ALLOWED_ORIGINS": f"http://127.0.0.1:{self.view_port}",
            "PLANT_VIEW_URL": self.view,
        }
        self.view_env = {
            **base,
            "OPCUA_ENDPOINT": f"opc.tcp://127.0.0.1:{self.opc_port}/arya/plant/",
            "VIEW_HOST": "127.0.0.1",
            "VIEW_PORT": str(self.view_port),
            "STALE_AFTER_SECONDS": "2",
            "CONTROL_PUBLIC_PORT": str(self.control_port),
        }
        self.view_env.pop("DEMO_CONTROL_TOKEN", None)
        self.procs: dict[str, subprocess.Popen] = {}
        self.env_file = tmp_path / "demo.env"
        self.env_file.write_text(
            f"DEMO_CONTROL_TOKEN={TEST_TOKEN}\nCONTROL_PORT={self.control_port}\nSCADA_PORT={self.view_port}\n",
            encoding="utf-8",
        )

    def start(self, name: str) -> None:
        module, env = ("arya_plant", self.plant_env) if name == "plant" else ("arya_plant_view", self.view_env)
        log = open(self.tmp / f"{name}.log", "ab")
        self.procs[name] = subprocess.Popen([sys.executable, "-m", module], env=env, stdout=log, stderr=log, cwd=self.tmp)

    def stop(self, name: str) -> None:
        proc = self.procs.pop(name, None)
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    def run_module(self, module: str, *args: str) -> subprocess.CompletedProcess:
        env = self.plant_env if module.startswith("arya_plant.") else self.view_env
        return subprocess.run([sys.executable, "-m", module, *args], env=env, capture_output=True, text=True, timeout=60)

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "ARYA_ENV_FILE": str(self.env_file)}
        return subprocess.run(["bash", str(ROOT / "scripts" / name), *args], env=env, capture_output=True, text=True, timeout=30)

    def logs(self) -> str:
        return "".join(p.read_text(encoding="utf-8", errors="replace") for p in self.tmp.glob("*.log"))


@pytest.fixture
def stack(tmp_path):
    s = Stack(tmp_path)
    yield s
    for name in list(s.procs):
        s.stop(name)


def test_real_processes_end_to_end(stack: Stack):
    stack.start("plant")
    wait_until(lambda: httpx.get(f"{stack.control}/healthz", timeout=2).status_code == 200, what="plant healthy")
    stack.start("view")
    wait_until(lambda: httpx.get(f"{stack.view}/healthz", timeout=2).status_code == 200, what="view healthy")

    # --- healthchecks de contenedor (disponibilidad real) ---
    assert stack.run_module("arya_plant.healthcheck").returncode == 0
    assert stack.run_module("arya_plant_view.healthcheck").returncode == 0

    # --- la pantalla se sirve y la telemetria llega por OPC UA ---
    assert "THE PLANT" in httpx.get(stack.view).text
    latest = httpx.get(f"{stack.view}/api/telemetry/latest").json()
    assert latest["connection"]["state"] == "CONNECTED" and latest["snapshot"]["quality"] == "GOOD"
    run_1 = latest["snapshot"]["run_id"]

    # --- preflight: PLANT READY, nunca la demo completa ---
    result = stack.run_module("arya_plant.preflight")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PLANT READY" in result.stdout and "[FAIL]" not in result.stdout
    assert "READY FOR DEMO" not in result.stdout
    assert TEST_TOKEN not in result.stdout
    status = stack.run_module("arya_plant.status")
    assert status.returncode == 0 and run_1 in status.stdout and "P101.MOTOR_TEMP" in status.stdout
    assert TEST_TOKEN not in status.stdout

    # --- CORS: el origen del SCADA puede llamar a la API de control ---
    origin = f"http://127.0.0.1:{stack.view_port}"
    response = httpx.get(f"{stack.control}/api/demo/state", headers={**AUTH, "Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin

    # --- scripts del presentador ---
    if shutil.which("bash") and shutil.which("curl"):
        injected = stack.run_script("inject-fault.sh", "45")
        assert injected.returncode == 0 and "FALLA INYECTADA" in injected.stdout, injected.stdout + injected.stderr
        assert TEST_TOKEN not in injected.stdout + injected.stderr
        assert stack.run_script("inject-fault.sh").returncode == 1  # ya hay una falla activa
        assert stack.run_script("inject-fault.sh", "5; rm -rf /").returncode == 2  # argumento no numerico
    else:
        assert httpx.post(f"{stack.control}/api/demo/inject-fault", headers=AUTH).status_code == 200
    state = httpx.get(f"{stack.control}/api/demo/state", headers=AUTH).json()
    assert state["mode"] == "DEGRADATION" and state["run_id"] == run_1

    # Con una falla en curso el preflight NO declara la planta lista.
    result = stack.run_module("arya_plant.preflight")
    assert result.returncode == 1 and "PLANT NOT READY" in result.stdout and "reset-demo" in result.stdout

    if shutil.which("bash") and shutil.which("curl"):
        recovered = stack.run_script("normal-operation.sh")
        assert recovered.returncode == 0 and "FALLA RETIRADA" in recovered.stdout
        reset = stack.run_script("reset-demo.sh")
        assert reset.returncode == 0 and "PLANTA REINICIADA" in reset.stdout, reset.stdout + reset.stderr
    else:
        assert httpx.post(f"{stack.control}/api/demo/reset", headers=AUTH).status_code == 200
    run_2 = httpx.get(f"{stack.control}/api/demo/state", headers=AUTH).json()["run_id"]
    assert run_2 != run_1
    wait_until(lambda: httpx.get(f"{stack.view}/api/telemetry/latest").json()["snapshot"]["run_id"] == run_2,
               what="view shows the new run")

    # --- perdida de conexion: se detiene el proceso de la planta ---
    stack.stop("plant")
    data = wait_until(
        lambda: (d := httpx.get(f"{stack.view}/api/telemetry/latest").json())["snapshot"]["quality"] == "STALE" and d,
        what="stale data after plant stop",
    )
    assert data["connection"]["state"] == "DISCONNECTED" and data["connection"]["last_error"]
    assert data["snapshot"]["run_id"] == run_2 and data["snapshot"]["tags"]["P101.RPM"]["value"] > 1400
    assert httpx.get(f"{stack.view}/healthz").status_code == 503
    assert stack.run_module("arya_plant_view.healthcheck").returncode == 1
    assert stack.run_module("arya_plant.healthcheck").returncode == 1

    # --- recuperacion: la planta vuelve y el cliente reconecta solo ---
    stack.start("plant")
    wait_until(lambda: httpx.get(f"{stack.view}/healthz", timeout=2).status_code == 200, timeout=40, what="view recovered")
    data = httpx.get(f"{stack.view}/api/telemetry/latest").json()
    assert data["connection"]["state"] == "CONNECTED" and data["snapshot"]["quality"] == "GOOD"
    assert data["snapshot"]["run_id"] not in (run_1, run_2)

    # --- ni el token ni la causa real aparecen en los logs ---
    logs = stack.logs()
    assert TEST_TOKEN not in logs
    assert_no_leak(logs)


def test_plant_refuses_to_start_without_a_real_token(stack: Stack):
    for token in ("", "replace-with-a-generated-local-token", "short"):
        env = {**stack.plant_env, "DEMO_CONTROL_TOKEN": token}
        result = subprocess.run([sys.executable, "-m", "arya_plant"], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 2 and "CONFIG ERROR" in result.stderr
