# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Attach A2A (Agent2Agent) endpoints to the FastAPI app.

:func:`attach_a2a_routes` registers the dynamic
agent-card endpoint and the JSON-RPC endpoint so the same app serves A2A
alongside the adk_api routes, reachable by A2A clients and Gemini Enterprise A2A
registration.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import TaskStore
from a2a.types import AgentCapabilities, AgentExtension
from a2a.utils.constants import (
    AGENT_CARD_WELL_KNOWN_PATH,
    EXTENDED_AGENT_CARD_PATH,
)
from google.adk.a2a.converters.event_converter import convert_event_to_a2a_events
from google.adk.a2a.converters.from_adk_event import (
    convert_event_to_a2a_events as convert_event_to_a2a_events_impl,
)
from google.adk.a2a.executor.a2a_agent_executor import (
    A2aAgentExecutor,
    A2aAgentExecutorConfig,
)
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

if TYPE_CHECKING:
    from fastapi import FastAPI
    from google.adk.agents import BaseAgent
    from google.adk.runners import Runner

# URI advertised on the agent card describing the executor extension shipped
# by ADK. Kept as a module-level constant so callers can override or extend
# the capabilities list when needed.
_ADK_AGENT_EXECUTOR_EXTENSION_URI = (
    "https://google.github.io/adk-docs/a2a/a2a-extension/"
)

logger = logging.getLogger(__name__)


# The agent that addresses the user. Every other agent in the pipeline gathers
# material for it.
_USER_FACING_AUTHOR = "lunch_synthesizer"


def _carries_text(event) -> bool:
    parts = getattr(getattr(event, "content", None), "parts", None) or []
    return any(getattr(part, "text", None) for part in parts)


def _only_synthesizer_speaks(convert):
    """Wraps the ADK-to-A2A event converter, dropping sub-agent commentary.

    Each sub-agent's own answer is an event of its own, so a client receives the
    strategy analysis, the scheduling reply and the synthesis concatenated --
    one turn narrating itself multiple times with no separator between authors.

    Only text is withheld, and only on the way out. Sub-agent events still reach
    the session, which is where the synthesizer reads them.
    """

    def convert_from_one_voice(event, *args, **kwargs):
        withheld = event.author != _USER_FACING_AUTHOR and _carries_text(event)
        # Which author said what is invisible once the parts are merged into one
        # reply, and is the only way to tell a leak from a chatty synthesizer.
        logger.info(
            "a2a event: author=%s text=%s %s",
            event.author,
            _carries_text(event),
            "withheld" if withheld else "sent",
        )
        if withheld:
            return []
        return convert(event, *args, **kwargs)

    return convert_from_one_voice


def _build_executor(runner: Runner, agent_card):
    """Returns the A2A executor configured with single-voice event conversion."""
    config = A2aAgentExecutorConfig(
        event_converter=_only_synthesizer_speaks(convert_event_to_a2a_events),
        adk_event_converter=_only_synthesizer_speaks(convert_event_to_a2a_events_impl),
    )
    return A2aAgentExecutor(runner=runner, config=config)


def _default_capabilities() -> AgentCapabilities:
    """Returns the default A2A capabilities used by scaffolded projects.

    ``streaming`` is true because the ADK A2A route serves ``message/stream``
    on every hosting target this repo deploys to, Agent Runtime included.
    Callers needing a different value pass ``capabilities`` to
    :func:`attach_a2a_routes`; the a2a SDK gates ``message/stream`` on whatever
    the card says, so the two cannot drift.
    """
    extensions = [
        AgentExtension(
            uri=_ADK_AGENT_EXECUTOR_EXTENSION_URI,
            description=("Ability to use the new agent executor implementation"),
        ),
    ]
    return AgentCapabilities(streaming=True, extensions=extensions)


def _resolve_app_url(app_url: str | None) -> str:
    """Resolve the public base URL advertised inside the agent card.

    Falls back in order: explicit ``app_url``, the ``APP_URL`` env var, the
    Agent Runtime ``/api`` passthrough self-built from runtime env vars (valid
    on the first deploy, before the CLI knows the server-assigned engine ID),
    then a local default.
    """
    if app_url:
        return app_url
    if env_url := os.getenv("APP_URL"):
        return env_url

    agent_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    project = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    # Never defaulted: a guessed region yields a card URL that resolves and points
    # at the wrong place. Not GOOGLE_GENAI_LOCATION either -- that is "global",
    # which would build an invalid "global-aiplatform.googleapis.com" host.
    location = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION") or os.getenv(
        "GOOGLE_CLOUD_LOCATION"
    )
    if agent_engine_id and project and location:
        return (
            f"https://{location}-aiplatform.googleapis.com/reasoningEngines/v1"
            f"/projects/{project}/locations/{location}"
            f"/reasoningEngines/{agent_engine_id}/api"
        )
    if agent_engine_id and not location:
        logger.warning(
            "Running on Agent Runtime but neither GOOGLE_CLOUD_AGENT_ENGINE_LOCATION "
            "nor GOOGLE_CLOUD_LOCATION is set, so the agent card cannot advertise a "
            "reachable URL. Set APP_URL or one of those."
        )

    port = os.getenv("PORT", "8000")
    return f"http://localhost:{port}"


async def attach_a2a_routes(
    app: FastAPI,
    *,
    agent: BaseAgent,
    runner: Runner,
    task_store: TaskStore,
    rpc_path: str,
    capabilities: AgentCapabilities | None = None,
    agent_version: str | None = None,
    app_url: str | None = None,
) -> None:
    """Register A2A routes (JSON-RPC + agent-card endpoints) under ``rpc_path``.

    Builds a dynamic agent card from ``agent`` and mounts the routes on ``app``.
    The ``runner`` should share the session/artifact services with the
    standard ADK path. ``capabilities``, ``agent_version``, and ``app_url``
    override their defaults (streaming + ADK extension, ``AGENT_VERSION``,
    ``APP_URL``). Call once per app — typically in a FastAPI ``lifespan``, since
    the card is built asynchronously; repeated calls register duplicate routes.
    """
    resolved_app_url = _resolve_app_url(app_url)
    resolved_agent_version = agent_version or os.getenv("AGENT_VERSION", "0.1.0")
    resolved_capabilities = capabilities or _default_capabilities()

    agent_card = await AgentCardBuilder(
        agent=agent,
        capabilities=resolved_capabilities,
        rpc_url=f"{resolved_app_url}{rpc_path}",
        agent_version=resolved_agent_version,
    ).build()

    request_handler = DefaultRequestHandler(
        agent_executor=_build_executor(runner, agent_card),
        task_store=task_store,
    )

    a2a_app = A2AFastAPIApplication(agent_card=agent_card, http_handler=request_handler)
    a2a_app.add_routes_to_app(
        app,
        agent_card_url=f"{rpc_path}{AGENT_CARD_WELL_KNOWN_PATH}",
        rpc_url=rpc_path,
        extended_agent_card_url=f"{rpc_path}{EXTENDED_AGENT_CARD_PATH}",
    )
