"""Punto de entrada del agente: `python -m arya_agent`."""

from __future__ import annotations

import logging
import os
import sys

import httpx
import uvicorn

from .agent import Agent
from .api import create_agent_app
from .config import AgentSettings
from .documents import DocumentIndex
from .llm import NoModel, OpenAICompatModel
from .memory import AgentMemory
from .tools import ToolContext
from .trace import TraceHub


def build(settings: AgentSettings):
    if settings.llm_base_url and settings.llm_model:
        model = OpenAICompatModel(settings.llm_base_url, settings.llm_model, settings.llm_api_key, settings.llm_timeout_s,
                                  settings.llm_temperature, settings.llm_max_tokens, thinking=settings.llm_thinking,
                                  stream=settings.llm_stream)
    else:
        model = NoModel()
    timeout = httpx.Timeout(settings.tool_timeout_s, connect=3.0)
    ctx = ToolContext(
        gateway=httpx.AsyncClient(base_url=settings.gateway_url, timeout=timeout),
        cmms=httpx.AsyncClient(base_url=settings.cmms_url, timeout=timeout),
        cmms_agent_key=settings.cmms_agent_key,
        documents=DocumentIndex(settings.documents_dir),
        memory=AgentMemory(os.path.join(settings.data_dir, "memory.sqlite3")),
    )
    trace = TraceHub(os.path.join(settings.data_dir, "trace.jsonl"))
    agent = Agent(model, ctx, trace, settings)
    return create_agent_app(agent, trace, ctx.memory, settings)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = AgentSettings.from_env()
    app = build(settings)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
