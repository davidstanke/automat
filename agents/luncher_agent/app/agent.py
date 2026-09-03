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

import logging
import os
import re
from typing import Any, Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx
from google import genai
from google.genai import types
from google.genai.types import (
    HttpRetryOptions,
    ThinkingConfig,
    ThinkingLevel,
)

from google.adk.a2a.agent.config import A2aRemoteAgentConfig, RequestInterceptor
from google.adk.agents import Agent
from google.adk.agents.context import Context
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps.app import App
from google.adk.events.event import Event
from google.adk.models.google_llm import Gemini
from google.adk.workflow import JoinNode, Workflow, node

from .app_utils.genai_transport import GenaiApiTransport
from .proposal_builder import (
    ROLE_DESCRIPTION as SYNTHESIZER_INSTRUCTION,
    format_lunch_proposal_tool,
)

# Defaults to Python's own unset level. LOG_LEVEL=INFO adds the per-event A2A
# author lines, which show whether a turn was filtered. An unknown level raises
# here rather than quietly falling back.
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "WARNING").upper())
logger = logging.getLogger(__name__)

# Load environment variables
# override=True: a stale shell export must not beat .env.
load_dotenv(override=True)

# Gemini Enterprise Agent Platform (GEAP) & GCP Project configuration
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL_LOCATION = os.getenv("GOOGLE_GENAI_LOCATION", "global")
# Pinned version. Override via GOOGLE_GENAI_MODEL. Served from global endpoint.
MODEL = os.getenv("GOOGLE_GENAI_MODEL", "gemini-3.8-flash")
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

logger.info("Using Gemini model '%s' in location '%s'", MODEL, MODEL_LOCATION)


def _extract_part_text(part: Any) -> str:
    """Extracts raw text string from an A2A message part."""
    if hasattr(part, "text"):
        return part.text or ""
    if hasattr(part, "root") and hasattr(part.root, "text"):
        return part.root.text or ""
    return ""


async def isolate_context_hook(ctx: Any, a2a_request: Any, params: Any) -> tuple[Any, Any]:
    """Strips leaked cross-agent context from A2A message parts.

    Ensures parallel sub-agents (e.g. strategy_agent and scheduling_agent)
    only receive the user's direct prompt without other agents' outputs.
    """
    cleaned_parts = []
    for part in a2a_request.parts:
        text = _extract_part_text(part)
        if "[scheduling_agent] said:" in text or "[strategy_agent] said:" in text or "For context:" in text:
            continue
        cleaned_parts.append(part)
    if cleaned_parts:
        a2a_request.parts = cleaned_parts
    return a2a_request, params


def format_agent_runtime_url(
    engine_id_or_resource: str,
    project_id: str | None = None,
    location: str | None = None,
    app_name: str = "app",
) -> str:
    """Constructs the A2A agent card URL from an Agent Runtime / Reasoning Engine unique ID."""
    clean_id = engine_id_or_resource.strip()
    if clean_id.startswith("projects/"):
        parts = clean_id.split("/")
        loc = parts[3] if len(parts) > 3 else (location or "us-central1")
        resource_path = clean_id
    else:
        proj = (
            project_id
            or os.getenv("GOOGLE_CLOUD_PROJECT_ID")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        env_loc = (
            location
            or os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION")
            or os.getenv("GOOGLE_CLOUD_REGION")
            or os.getenv("REGION")
            or os.getenv("GOOGLE_CLOUD_LOCATION")
        )
        if not env_loc or env_loc == "global":
            env_loc = "us-central1"
        loc = env_loc
        resource_path = f"projects/{proj}/locations/{loc}/reasoningEngines/{clean_id}"
    return (
        f"https://{loc}-aiplatform.googleapis.com/reasoningEngines/v1/"
        f"{resource_path}/api/a2a/{app_name}/.well-known/agent-card.json"
    )


def discover_sub_agent(
    agent_name: str,
    default_local_url: str,
    description: str,
    app_name: str = "app",
) -> RemoteA2aAgent:
    """Instantiates a RemoteA2aAgent using Agent Runtime Engine ID, URL, or local fallback.

    Checks:
    1. Agent Runtime unique IDs: {AGENT_NAME}_ENGINE_ID, {AGENT_NAME}_RUNTIME_ID,
       and common aliases (e.g. STRATEGY_AGENT_ENGINE_ID, STRAT_AGENT_ENGINE_ID).
    2. Direct URL env vars: {AGENT_NAME}_URL, {AGENT_NAME}_AGENT_URL.
    3. Falls back to default_local_url for local offline development.
    """
    name_upper = agent_name.upper()
    stem = name_upper.replace("_AGENT", "")
    stems = [stem]
    if stem.startswith("STRAT") and "STRAT" not in stems:
        stems.append("STRAT")
    if stem.startswith("STRAT") and "STRATEGY" not in stems:
        stems.append("STRATEGY")
    if stem.startswith("SCHED") and "SCHED" not in stems:
        stems.append("SCHED")
    if stem.startswith("SCHED") and "SCHEDULING" not in stems:
        stems.append("SCHEDULING")
    if stem.startswith("CATER") and "CATER" not in stems:
        stems.append("CATER")
    if stem.startswith("CATER") and "CATERING" not in stems:
        stems.append("CATERING")

    engine_id_vars = []
    for s in stems:
        for suffix in ("_AGENT_ENGINE_ID", "_AGENT_RUNTIME_ID", "_ENGINE_ID", "_RUNTIME_ID"):
            var = f"{s}{suffix}"
            if var not in engine_id_vars:
                engine_id_vars.append(var)

    engine_id = None
    engine_var_used = None
    for var in engine_id_vars:
        val = os.getenv(var)
        if val:
            engine_id = val
            engine_var_used = var
            break

    if engine_id:
        agent_url = format_agent_runtime_url(engine_id, app_name=app_name)
        logger.info(
            "Connecting '%s' via %s (%s): %s",
            agent_name,
            engine_var_used,
            engine_id,
            agent_url,
        )
    else:
        url_vars = []
        for s in stems:
            for suffix in ("_AGENT_URL", "_URL"):
                var = f"{s}{suffix}"
                if var not in url_vars:
                    url_vars.append(var)

        explicit_url = None
        url_var_used = None
        for var in url_vars:
            val = os.getenv(var)
            if val:
                explicit_url = val
                url_var_used = var
                break

        agent_url = explicit_url or default_local_url
        if os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID") and not explicit_url:
            logger.warning(
                "Running in Agent Runtime cloud container, but no Engine ID or URL configured for '%s'. "
                "Defaulting to %s, which may not be reachable.",
                agent_name,
                agent_url,
            )
        logger.info(
            "Connecting '%s' via %s: %s",
            agent_name,
            url_var_used if explicit_url else f"default ({engine_id_vars[0]} unset)",
            agent_url,
        )

    if "aiplatform.googleapis.com" in agent_url:
        # An Agent Runtime peer. Its endpoint rejects a bearer header built from
        # ADC under Agent Identity, so the request goes through the genai
        # client's transport instead -- see app_utils.genai_transport.
        client = httpx.AsyncClient(
            transport=GenaiApiTransport.from_url(agent_url), timeout=120.0
        )
        logger.info("  '%s' authenticates via GenaiApiTransport", agent_name)
    else:
        # Local development unauthenticated client
        client = httpx.AsyncClient(timeout=120.0)
        logger.info("  '%s' uses local unauthenticated transport", agent_name)

    return RemoteA2aAgent(
        name=agent_name,
        description=description,
        agent_card=agent_url,
        httpx_client=client,
        timeout=120.0,
        config=A2aRemoteAgentConfig(
            request_interceptors=[RequestInterceptor(before_request=isolate_context_hook)]
        ),
    )


# Discover sub-agents (Strategy Agent and Scheduling Agent)
strategy_agent = discover_sub_agent(
    agent_name="strategy_agent",
    default_local_url="http://localhost:8081/a2a/app/.well-known/agent-card.json",
    description=(
        "Analyzes GeniCo corporate strategy and product initiative roadmaps (e.g. OmniChef, "
        "VisionSphere, PowerGrid Home). Consult this agent for strategic context and launch schedules."
    ),
)

scheduling_agent = discover_sub_agent(
    agent_name="scheduling_agent",
    default_local_url="http://localhost:8082/a2a/app/.well-known/agent-card.json",
    description=(
        "Helps coordinate meeting times and availability across team members interactively."
    ),
)

default_retry_policy = HttpRetryOptions(
    attempts=5,
    initial_delay=2.0,
    max_delay=30.0,
    http_status_codes=[429, 500, 503],
)

class IntentClassification(BaseModel):
    intent: Literal["plan", "book"] = Field(
        description="The classified intent: 'plan' for planning/finding lunch times, 'book' for selecting/booking a specific slot."
    )


def _extract_text_from_input(content: Any) -> str:
    if isinstance(content, str):
        return content
    if hasattr(content, "parts") and content.parts:
        return " ".join(
            part.text for part in content.parts if getattr(part, "text", None)
        )
    if isinstance(content, dict):
        return str(content)
    return str(content) if content is not None else ""


def classify_intent_fast_path(user_prompt: str) -> Literal["plan", "book"] | None:
    """Fast deterministic intent classification (<0.1ms) for common unambiguous prompts."""
    text = user_prompt.lower().strip()
    if not text:
        return "plan"

    # Direct booking intent patterns
    # e.g., "book slot 2", "confirm Tuesday 12:00", "reserve option 1", "let's go with slot 1", "take slot 2"
    booking_keywords = (
        "book",
        "confirm",
        "reserve",
        "choose",
        "select",
        "i'll take slot",
        "take slot",
        "let's book",
        "lets book",
        "let's go with",
        "lets go with",
        "lock in",
        "finalize",
    )
    if any(k in text for k in booking_keywords) and not any(p in text for p in ("plan", "suggest", "available", "availability")):
        return "book"

    if re.search(r"\b(book|reserve|confirm)\s+(slot|option|\d{1,2}:\d{2})", text):
        return "book"

    # Direct planning intent patterns
    # e.g., "plan a team lunch", "schedule a lunch for Friday", "find available time slots", "when can the team meet"
    planning_prefixes = (
        "plan",
        "find",
        "schedule a",
        "schedule lunch",
        "coordinate",
        "what time",
        "what times",
        "when can",
        "who is",
        "who's",
        "show available",
        "check availability",
        "suggest",
    )
    if any(text.startswith(prefix) for prefix in planning_prefixes):
        return "plan"

    if re.search(r"\b(lunch|meeting|availability|available slots|time slots)\b", text) and not re.search(r"\b(book|confirmed|reserved)\b", text):
        return "plan"

    return None


@node(name="intent_router")
async def intent_router(ctx: Context, node_input: Any) -> Event:
    """Routes user messages between the planning and booking branches."""
    user_prompt = _extract_text_from_input(node_input)
    if not user_prompt.strip():
        return Event(output=node_input, route="plan")

    fast_route = classify_intent_fast_path(user_prompt)
    if fast_route is not None:
        logger.info("Fast-path routed intent for %r -> %s", user_prompt[:40], fast_route)
        return Event(output=node_input, route=fast_route)

    try:
        client = genai.Client(vertexai=True, location=MODEL_LOCATION)
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are an intent router for a team lunch coordination system. "
                    "Classify the user message into one of two intents:\n"
                    "- 'plan': The user wants to plan, schedule, coordinate, or find options for a team lunch.\n"
                    "- 'book': The user wants to select, confirm, or book a specific slot or proposal.\n"
                    "Default to 'plan' if ambiguous or general chat."
                ),
                response_mime_type="application/json",
                response_schema=IntentClassification,
            ),
        )
        parsed = IntentClassification.model_validate_json(response.text)
        route = parsed.intent
    except Exception as e:
        logger.warning("Intent router LLM failed, defaulting to 'plan': %s", e)
        lower = user_prompt.lower().strip()
        if any(w in lower for w in ("book", "confirm", "reserve", "choose", "select")):
            route = "book"
        else:
            route = "plan"

    return Event(output=node_input, route=route)


@node(name="booking_handler", rerun_on_resume=True)
async def booking_handler(ctx: Context, node_input: Any) -> Any:
    """Delegates booking and selection turns directly to scheduling_agent."""
    return await ctx.run_node(
        scheduling_agent,
        node_input=node_input,
        use_as_output=True,
    )


# Proposal Synthesizer: synthesize corporate strategy and schedule into a structured Markdown proposal
synthesizer_agent = Agent(
    model=Gemini(
        model=MODEL,
        # Not MINIMAL: this agent reconciles sub-agent outputs and carries
        # the roster and per-slot free counts across verbatim. At MINIMAL it
        # intermittently rewrites the attendee list rather than copying it.
        thinking_config=ThinkingConfig(thinking_level=ThinkingLevel.LOW),
        retry_options=default_retry_policy,
        client_kwargs={"location": MODEL_LOCATION},
    ),
    name="lunch_synthesizer",
    description="Synthesizes corporate strategy objectives and scheduling options into a team lunch proposal.",
    instruction=SYNTHESIZER_INSTRUCTION,
    tools=[format_lunch_proposal_tool],
)

join_info_gatherer = JoinNode(name="join_info_gatherer")

# Root Orchestrator: ADK 2.0 Workflow coordinating intent routing, parallel data gathering, and booking
luncher_agent = Workflow(
    name="luncher_agent",
    description="The centralized Luncher Orchestrator that coordinates strategy-aligned team lunch meetings.",
    edges=[
        ("START", intent_router),
        (
            intent_router,
            {
                "plan": (strategy_agent, scheduling_agent),
                "book": booking_handler,
            },
        ),
        ((strategy_agent, scheduling_agent), join_info_gatherer),
        (join_info_gatherer, synthesizer_agent),
    ],
)

root_agent = luncher_agent

app = App(
    name="luncher_agent",
    root_agent=root_agent,
)


