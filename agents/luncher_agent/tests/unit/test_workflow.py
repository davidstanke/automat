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

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from google.adk.workflow import Workflow, JoinNode
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.apps import App
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

from app.agent import (
    IntentClassification,
    _extract_text_from_input,
    booking_handler,
    intent_router,
    luncher_agent,
    root_agent,
)


def test_extract_text_from_input() -> None:
    assert _extract_text_from_input("simple text") == "simple text"
    
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text="part 1"), types.Part.from_text(text="part 2")],
    )
    assert _extract_text_from_input(content) == "part 1 part 2"
    assert _extract_text_from_input({"key": "val"}) == "{'key': 'val'}"
    assert _extract_text_from_input(None) == ""


def test_intent_router_empty_input() -> None:
    async def _run():
        ctx = MagicMock()
        event = await intent_router._func(ctx, "")
        assert isinstance(event, Event)
        assert event.actions.route == "plan"

    asyncio.run(_run())


def test_intent_router_llm_success() -> None:
    async def _run():
        ctx = MagicMock()
        
        mock_response = MagicMock()
        mock_response.text = '{"intent": "book"}'

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            event = await intent_router._func(ctx, "Book Option 1 please")
            assert event.actions.route == "book"

    asyncio.run(_run())


def test_intent_router_llm_fallback_booking_keyword() -> None:
    async def _run():
        ctx = MagicMock()
        
        with patch("google.genai.Client", side_effect=Exception("API Error")):
            event = await intent_router._func(ctx, "Book Tuesday 12:00")
            assert event.actions.route == "book"

            event_plan = await intent_router._func(ctx, "Let's organize a lunch")
            assert event_plan.actions.route == "plan"

    asyncio.run(_run())


def test_workflow_structure() -> None:
    assert isinstance(luncher_agent, Workflow)
    assert luncher_agent.name == "luncher_agent"
    assert root_agent is luncher_agent
    
    node_names = {node.name for node in luncher_agent.graph.nodes}
    assert "intent_router" in node_names
    assert "strategy_agent" in node_names
    assert "scheduling_agent" in node_names
    assert "booking_handler" in node_names
    assert "join_info_gatherer" in node_names
    assert "lunch_synthesizer" in node_names


def test_workflow_execution_mocked() -> None:
    async def _run():
        def mock_strat(node_input):
            return "Strategic priorities: OmniChef Launch"

        def mock_sched(node_input):
            return "Team (3): Alice, Bob, Charlie\n1. Tue 12:00 (3 of 3 free)"

        def mock_synth(node_input):
            return f"# Proposal\n{node_input}"

        def mock_router(node_input):
            return Event(output=node_input, route="plan")

        def mock_book(node_input):
            return "Booking confirmed"

        join = JoinNode(name="mock_join")

        test_wf = Workflow(
            name="test_luncher",
            edges=[
                ("START", mock_router),
                (
                    mock_router,
                    {
                        "plan": (mock_strat, mock_sched),
                        "book": mock_book,
                    },
                ),
                ((mock_strat, mock_sched), join),
                (join, mock_synth),
            ],
        )

        test_app = App(name="test_luncher", root_agent=test_wf)
        runner = Runner(app=test_app, session_service=InMemorySessionService())
        session = await runner.session_service.create_session(app_name="test_luncher", user_id="u1")
        
        msg = types.Content(role="user", parts=[types.Part.from_text(text="Plan lunch")])
        events = []
        async for event in runner.run_async(user_id="u1", session_id=session.id, new_message=msg):
            events.append(event)

        outputs = [e.output for e in events if getattr(e, "output", None) is not None]
        assert any("Proposal" in str(o) for o in outputs)

    asyncio.run(_run())
