"""Configuracion del agente mediante variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentSettings:
    host: str = "127.0.0.1"
    port: int = 8091
    node_label: str = "Notebook (desarrollo)"  # donde corre el agente; lo muestra la interfaz
    llm_base_url: str = ""  # p. ej. http://<gb10>:30081/v1 ; vacio = sin modelo configurado
    llm_model: str = ""
    llm_api_key: str = ""
    llm_timeout_s: float = 45.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 700
    llm_thinking: bool = False  # razonamiento del modelo: apagado = respuestas en segundos
    llm_thinking_diagnosis: bool = False  # encenderlo solo en preguntas de diagnostico
    llm_stream: bool = True  # streaming: permite medir TTFT y TPOT; si falla, se usa el modo normal
    gateway_url: str = "http://127.0.0.1:8081"
    cmms_url: str = "http://127.0.0.1:8082"
    cmms_agent_key: str = ""
    admin_token: str = ""
    documents_dir: str = "/app/data/documents"
    data_dir: str = "/data"
    tool_timeout_s: float = 8.0
    max_steps: int = 6  # llamadas al modelo por turno
    max_tool_calls: int = 8  # herramientas por turno
    turn_timeout_s: float = 120.0
    proactive: bool = False
    proactive_level: str = "WARNING"  # nivel que dispara el aviso automatico
    proactive_settle_s: float = 15.0
    proactive_poll_s: float = 3.0

    @classmethod
    def from_env(cls) -> "AgentSettings":
        env = os.environ.get
        return cls(
            host=env("AGENT_HOST", cls.host).strip(),
            port=int(env("AGENT_PORT", cls.port)),
            node_label=env("AGENT_NODE_LABEL", cls.node_label).strip(),
            llm_base_url=env("NEMOTRON_BASE_URL", "").strip().rstrip("/"),
            llm_model=env("NEMOTRON_MODEL", "").strip(),
            llm_api_key=env("NEMOTRON_API_KEY", "").strip(),
            llm_timeout_s=float(env("LLM_TIMEOUT_SECONDS", cls.llm_timeout_s)),
            llm_temperature=float(env("LLM_TEMPERATURE", cls.llm_temperature)),
            llm_max_tokens=int(env("LLM_MAX_TOKENS", cls.llm_max_tokens)),
            llm_thinking=env("LLM_THINKING", "off").strip().lower() in ("on", "true", "1"),
            llm_thinking_diagnosis=env("LLM_THINKING", "off").strip().lower() == "diagnosis",
            llm_stream=env("LLM_STREAM", "on").strip().lower() in ("on", "true", "1"),
            gateway_url=env("GATEWAY_URL", cls.gateway_url).strip().rstrip("/"),
            cmms_url=env("CMMS_URL", cls.cmms_url).strip().rstrip("/"),
            cmms_agent_key=env("CMMS_AGENT_KEY", "").strip(),
            admin_token=env("AGENT_ADMIN_TOKEN", "").strip(),
            documents_dir=env("DOCUMENTS_DIR", cls.documents_dir).strip(),
            data_dir=env("AGENT_DATA_DIR", cls.data_dir).strip(),
            tool_timeout_s=float(env("TOOL_TIMEOUT_SECONDS", cls.tool_timeout_s)),
            max_steps=int(env("AGENT_MAX_STEPS", cls.max_steps)),
            max_tool_calls=int(env("AGENT_MAX_TOOL_CALLS", cls.max_tool_calls)),
            turn_timeout_s=float(env("AGENT_TURN_TIMEOUT_SECONDS", cls.turn_timeout_s)),
            proactive=env("AGENT_PROACTIVE", "off").strip().lower() in ("on", "true", "1"),
            proactive_level=env("AGENT_PROACTIVE_LEVEL", cls.proactive_level).strip().upper(),
            proactive_settle_s=float(env("AGENT_PROACTIVE_SETTLE_SECONDS", cls.proactive_settle_s)),
        )
