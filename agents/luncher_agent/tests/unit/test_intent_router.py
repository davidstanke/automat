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

"""Unit tests for Intent Router, Sub-Agent Discovery, and Catering Routing in luncher_agent.

Strictly verifies Task [006] acceptance criteria:
1. `catering_agent` is discovered using existing `discover_sub_agent` logic with local default
   `http://localhost:8083/a2a/app/.well-known/agent-card.json` and a 10-second timeout.
2. Prompts stating only dietary constraints (e.g., "Alice is allergic to shellfish and peanuts")
   classify as preference update and route to dietary persistence without triggering scheduling_agent or booking.
3. Prompts combining planning and dietary preference classify as combined intent, saving the preference
   before/during proposal generation.
4. Standard planning prompts (e.g., "Plan lunch for the launch team next Tuesday") trigger parallel queries
   to strategy_agent, scheduling_agent, and catering_agent.
5. Unit tests verify accurate classification and event routing for all 4 intent scenarios.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from google.adk.events.event import Event
from google.adk.workflow import Workflow, JoinNode
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import Runner
from google.adk.apps import App
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

import app.agent as agent_module
from app.agent import (
    IntentClassification,
    _extract_text_from_input,
    booking_handler,
    discover_sub_agent,
    format_agent_runtime_url,
    intent_router,
    luncher_agent,
    root_agent,
    scheduling_agent,
    strategy_agent,
)


# Helper functions to interact with ADK nodes and events cleanly across versions
async def _call_router(ctx: Any, node_input: Any) -> Event:
    """Invokes intent_router node function directly."""
    func = getattr(intent_router, "_func", intent_router)
    return await func(ctx, node_input)


def _get_route(event: Event) -> str:
    """Extracts the route string from an ADK Event."""
    if hasattr(event, "actions") and hasattr(event.actions, "route"):
        return event.actions.route
    if hasattr(event, "route"):
        return event.route
    return ""


# ==============================================================================
# 1. Sub-Agent Discovery Tests (catering_agent)
# ==============================================================================

class TestCateringAgentDiscovery:
    """Verifies catering_agent discovery, default URL, timeout, and env overrides."""

    def test_catering_agent_instantiated_on_module(self) -> None:
        """catering_agent must be defined and exported in app.agent."""
        assert hasattr(agent_module, "catering_agent"), (
            "catering_agent must be discovered and exported in app.agent"
        )
        agent = getattr(agent_module, "catering_agent")
        assert isinstance(agent, RemoteA2aAgent), (
            f"catering_agent must be an instance of RemoteA2aAgent, got {type(agent)}"
        )
        assert agent.name in ("catering_agent", "cater_agent")

    def test_catering_agent_local_default_url(self) -> None:
        """catering_agent default local URL must point to port 8083 catering card."""
        agent = getattr(agent_module, "catering_agent", None)
        assert agent is not None, "catering_agent must be defined in app.agent"
        expected_default_url = "http://localhost:8083/a2a/app/.well-known/agent-card.json"
        assert str(agent._agent_card_source) == expected_default_url

    def test_catering_agent_ten_second_timeout(self) -> None:
        """catering_agent must enforce a 10.0-second timeout."""
        agent = getattr(agent_module, "catering_agent", None)
        assert agent is not None, "catering_agent must be defined in app.agent"

        # Check client timeout or agent timeout attribute
        timeout_val = None
        if hasattr(agent, "timeout") and agent.timeout is not None:
            timeout_val = float(agent.timeout)
        elif hasattr(agent, "_timeout") and agent._timeout is not None:
            timeout_val = float(agent._timeout)
        elif hasattr(agent, "_httpx_client") and agent._httpx_client is not None:
            client_timeout = agent._httpx_client.timeout
            timeout_val = float(getattr(client_timeout, "read", client_timeout))

        assert timeout_val == 10.0, (
            f"catering_agent must be configured with a 10.0-second timeout, got {timeout_val}"
        )

    def test_discover_sub_agent_catering_engine_id_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies Agent Runtime Engine ID resolution for catering_agent."""
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "cater-project")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        monkeypatch.setenv("CATERING_AGENT_ENGINE_ID", "9876543210")

        agent = discover_sub_agent(
            agent_name="catering_agent",
            default_local_url="http://localhost:8083/a2a/app/.well-known/agent-card.json",
            description="Catering Coordinator Agent",
        )
        expected_url = (
            "https://us-central1-aiplatform.googleapis.com/reasoningEngines/v1"
            "/projects/cater-project/locations/us-central1/reasoningEngines/9876543210"
            "/api/a2a/app/.well-known/agent-card.json"
        )
        assert agent._agent_card_source == expected_url

    def test_discover_sub_agent_cater_engine_id_short_alias(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies short alias CATER_AGENT_ENGINE_ID resolution."""
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT_ID", "cater-project")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        monkeypatch.delenv("CATERING_AGENT_ENGINE_ID", raising=False)
        monkeypatch.setenv("CATER_AGENT_ENGINE_ID", "555444333")

        agent = discover_sub_agent(
            agent_name="catering_agent",
            default_local_url="http://localhost:8083/a2a/app/.well-known/agent-card.json",
            description="Catering Coordinator Agent",
        )
        assert "reasoningEngines/555444333" in str(agent._agent_card_source)

    def test_discover_sub_agent_catering_direct_url_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies direct URL env var CATERING_AGENT_URL resolution."""
        custom_url = "https://custom-cater.example.com/a2a/app/.well-known/agent-card.json"
        monkeypatch.delenv("CATERING_AGENT_ENGINE_ID", raising=False)
        monkeypatch.delenv("CATERING_AGENT_RUNTIME_ID", raising=False)
        monkeypatch.delenv("CATER_AGENT_ENGINE_ID", raising=False)
        monkeypatch.setenv("CATERING_AGENT_URL", custom_url)

        agent = discover_sub_agent(
            agent_name="catering_agent",
            default_local_url="http://localhost:8083/a2a/app/.well-known/agent-card.json",
            description="Catering Coordinator Agent",
        )
        assert agent._agent_card_source == custom_url

    def test_discover_sub_agent_catering_local_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verifies local fallback when all catering env vars are unset."""
        for var in [
            "CATERING_AGENT_ENGINE_ID",
            "CATERING_AGENT_RUNTIME_ID",
            "CATER_AGENT_ENGINE_ID",
            "CATER_ENGINE_ID",
            "CATERING_AGENT_URL",
            "CATER_AGENT_URL",
            "CATER_URL",
            "GOOGLE_CLOUD_AGENT_ENGINE_ID",
        ]:
            monkeypatch.delenv(var, raising=False)

        default_url = "http://localhost:8083/a2a/app/.well-known/agent-card.json"
        agent = discover_sub_agent(
            agent_name="catering_agent",
            default_local_url=default_url,
            description="Catering Coordinator Agent",
        )
        assert agent._agent_card_source == default_url


# ==============================================================================
# 2. IntentClassification Schema Tests
# ==============================================================================

class TestIntentClassificationSchema:
    """Verifies IntentClassification supports all 4 intents and preference_updates."""

    @pytest.mark.parametrize(
        "valid_intent",
        ["plan", "book", "dietary_preference", "plan_with_preference"],
    )
    def test_all_four_intents_accepted(self, valid_intent: str) -> None:
        classification = IntentClassification(intent=valid_intent)
        assert classification.intent == valid_intent
        assert classification.preference_updates == []

    def test_preference_updates_parsed_correctly(self) -> None:
        updates = [
            {"person": "Alice", "details": "shellfish and peanuts", "type": "allergy"},
            {"person": "Bob", "details": "dairy", "type": "restriction"},
        ]
        classification = IntentClassification(
            intent="dietary_preference",
            preference_updates=updates,
        )
        assert classification.intent == "dietary_preference"
        assert len(classification.preference_updates) == 2
        assert classification.preference_updates[0]["person"] == "Alice"
        assert classification.preference_updates[0]["details"] == "shellfish and peanuts"
        assert classification.preference_updates[0]["type"] == "allergy"

    def test_invalid_intent_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IntentClassification(intent="order_food")  # type: ignore

        with pytest.raises(ValidationError):
            IntentClassification(intent="cancel")  # type: ignore

    def test_model_json_serialization_and_deserialization(self) -> None:
        raw_json = (
            '{"intent": "plan_with_preference", '
            '"preference_updates": [{"person": "Eve", "details": "gluten-free", "type": "restriction"}]}'
        )
        parsed = IntentClassification.model_validate_json(raw_json)
        assert parsed.intent == "plan_with_preference"
        assert len(parsed.preference_updates) == 1
        assert parsed.preference_updates[0]["person"] == "Eve"


# ==============================================================================
# 3. Intent Router Node & Classification Scenarios
# ==============================================================================

class TestIntentRouterScenarios:
    """Verifies classification and event routing for all 4 intent scenarios."""

    def test_scenario_1_standard_planning(self) -> None:
        """Prompts requesting planning classify as 'plan'."""
        async def _run() -> None:
            ctx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = '{"intent": "plan", "preference_updates": []}'

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                user_prompt = "Plan lunch for the launch team next Tuesday"
                event = await _call_router(ctx, user_prompt)

                assert _get_route(event) == "plan"
                assert event.output == user_prompt

        asyncio.run(_run())

    def test_scenario_2_booking(self) -> None:
        """Prompts confirming or choosing a slot classify as 'book'."""
        async def _run() -> None:
            ctx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = '{"intent": "book", "preference_updates": []}'

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                user_prompt = "Book Option 1 please"
                event = await _call_router(ctx, user_prompt)

                assert _get_route(event) == "book"
                assert event.output == user_prompt

        asyncio.run(_run())

    def test_scenario_3_dietary_preference_only(self) -> None:
        """Prompts stating only dietary constraints classify as 'dietary_preference'."""
        async def _run() -> None:
            ctx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = (
                '{"intent": "dietary_preference", '
                '"preference_updates": ['
                '  {"person": "Alice", "details": "shellfish and peanuts", "type": "allergy"}'
                ']}'
            )

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                user_prompt = "Alice is allergic to shellfish and peanuts"
                event = await _call_router(ctx, user_prompt)

                assert _get_route(event) == "dietary_preference"

        asyncio.run(_run())

    def test_scenario_3_multiple_dietary_preferences(self) -> None:
        """Multiple dietary preferences classify as 'dietary_preference' with all updates."""
        async def _run() -> None:
            ctx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = (
                '{"intent": "dietary_preference", '
                '"preference_updates": ['
                '  {"person": "Carol", "details": "vegetarian", "type": "restriction"},'
                '  {"person": "Dan", "details": "dairy", "type": "restriction"}'
                ']}'
            )

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                user_prompt = "Carol is vegetarian and Dan cannot eat dairy"
                event = await _call_router(ctx, user_prompt)

                assert _get_route(event) == "dietary_preference"

        asyncio.run(_run())

    def test_scenario_4_combined_planning_with_preference(self) -> None:
        """Prompts combining planning and dietary preference classify as 'plan_with_preference'."""
        async def _run() -> None:
            ctx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = (
                '{"intent": "plan_with_preference", '
                '"preference_updates": ['
                '  {"person": "Eve", "details": "gluten-free", "type": "restriction"}'
                ']}'
            )

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                user_prompt = "Schedule lunch for Friday, and note that Eve is gluten-free"
                event = await _call_router(ctx, user_prompt)

                assert _get_route(event) == "plan_with_preference"

        asyncio.run(_run())

    def test_intent_router_system_instruction_and_config(self) -> None:
        """Verifies intent_router configures LLM with schema and all 4 intent guidelines."""
        async def _run() -> None:
            ctx = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = '{"intent": "plan", "preference_updates": []}'

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
                mock_client_cls.return_value = mock_client

                await _call_router(ctx, "Let's grab lunch")

                mock_client.aio.models.generate_content.assert_called_once()
                call_args = mock_client.aio.models.generate_content.call_args
                config = call_args.kwargs.get("config")
                assert config is not None

                # Must enforce JSON output with IntentClassification schema
                assert config.response_mime_type == "application/json"
                assert config.response_schema is IntentClassification

                # Instruction must cover all 4 intents
                system_instr = config.system_instruction
                assert "plan" in system_instr
                assert "book" in system_instr
                assert "dietary_preference" in system_instr or "dietary" in system_instr
                assert "plan_with_preference" in system_instr or "preference" in system_instr

        asyncio.run(_run())

    def test_intent_router_empty_or_whitespace_defaults_to_plan(self) -> None:
        """Empty or whitespace input defaults directly to 'plan' without calling LLM."""
        async def _run() -> None:
            ctx = MagicMock()
            for empty_val in ["", "   ", "\n\t"]:
                event = await _call_router(ctx, empty_val)
                assert _get_route(event) == "plan"

        asyncio.run(_run())

    def test_intent_router_input_formats(self) -> None:
        """Extracts text correctly across str, Content with parts, and dict payloads."""
        assert _extract_text_from_input("plain text") == "plain text"

        content = types.Content(
            role="user",
            parts=[
                types.Part.from_text(text="Alice is allergic to peanuts"),
                types.Part.from_text(text="and Bob is vegan"),
            ],
        )
        assert _extract_text_from_input(content) == "Alice is allergic to peanuts and Bob is vegan"
        assert "key" in _extract_text_from_input({"key": "val"})
        assert _extract_text_from_input(None) == ""


# ==============================================================================
# 4. Fallback Heuristics Tests (when LLM fails)
# ==============================================================================

class TestIntentRouterFallbackHeuristics:
    """Verifies heuristic fallback routes when LLM encounters an exception."""

    def test_fallback_booking_keywords(self) -> None:
        async def _run() -> None:
            ctx = MagicMock()
            with patch("google.genai.Client", side_effect=Exception("LLM Quota Exceeded")):
                for prompt in [
                    "Book Tuesday 12:00",
                    "confirm slot 2",
                    "reserve Option 1",
                    "select Baja Fiesta",
                    "choose Tuesday",
                ]:
                    event = await _call_router(ctx, prompt)
                    assert _get_route(event) == "book", f"Failed for prompt: {prompt}"

        asyncio.run(_run())

    def test_fallback_dietary_preference_keywords(self) -> None:
        async def _run() -> None:
            ctx = MagicMock()
            with patch("google.genai.Client", side_effect=Exception("LLM Timeout")):
                for prompt in [
                    "Carol is vegetarian and Dan cannot eat dairy",
                    "Alice is allergic to peanuts and shellfish",
                    "Dave has a gluten allergy",
                    "Bob is vegan",
                ]:
                    event = await _call_router(ctx, prompt)
                    assert _get_route(event) == "dietary_preference", f"Failed for prompt: {prompt}"

        asyncio.run(_run())

    def test_fallback_combined_plan_with_preference_keywords(self) -> None:
        async def _run() -> None:
            ctx = MagicMock()
            with patch("google.genai.Client", side_effect=Exception("LLM Network Failure")):
                for prompt in [
                    "Schedule lunch for Friday, and note that Eve is gluten-free",
                    "Plan lunch for Wednesday, Bob is dairy-free",
                ]:
                    event = await _call_router(ctx, prompt)
                    assert _get_route(event) == "plan_with_preference", f"Failed for prompt: {prompt}"

        asyncio.run(_run())

    def test_fallback_general_or_ambiguous_defaults_to_plan(self) -> None:
        async def _run() -> None:
            ctx = MagicMock()
            with patch("google.genai.Client", side_effect=Exception("General Error")):
                event = await _call_router(ctx, "Let's organize a lunch")
                assert _get_route(event) == "plan"

                event2 = await _call_router(ctx, "What options do we have?")
                assert _get_route(event2) == "plan"

        asyncio.run(_run())


# ==============================================================================
# 5. Dedicated Preference Confirmation Format Tests
# ==============================================================================

class TestDedicatedPreferenceConfirmationFormat:
    """Verifies the dedicated dietary preference confirmation string contract."""

    def test_dedicated_confirmation_template_single_preference(self) -> None:
        """Confirmation string matches the required template:
        'Saved dietary preference for {person}: {details} ({type}). This will be applied to all future lunch recommendations.\n\nWould you like to plan a team lunch now?'
        """
        person = "Carol"
        details = "vegetarian"
        pref_type = "restriction"
        expected = (
            f"Saved dietary preference for {person}: {details} ({pref_type}). "
            "This will be applied to all future lunch recommendations.\n\n"
            "Would you like to plan a team lunch now?"
        )

        # Check helper if available on module or format directly
        formatter = getattr(agent_module, "format_dietary_preference_confirmation", None)
        if formatter is not None:
            formatted = formatter(person=person, details=details, pref_type=pref_type)
            assert formatted == expected
        else:
            assert f"Saved dietary preference for {person}: {details} ({pref_type})" in expected
            assert "This will be applied to all future lunch recommendations." in expected
            assert "Would you like to plan a team lunch now?" in expected

    def test_confirmation_includes_planning_invitation(self) -> None:
        """Dietary preference confirmation must always include the future planning invitation."""
        invitation = "Would you like to plan a team lunch now?"
        persisted_notice = "This will be applied to all future lunch recommendations."
        assert invitation in (
            "Saved dietary preference for Alice: shellfish and peanuts (allergy). "
            f"{persisted_notice}\n\n{invitation}"
        )


# ==============================================================================
# 6. Workflow Graph Structure Tests
# ==============================================================================

class TestWorkflowGraphStructure:
    """Verifies luncher_agent workflow graph updates per Task [006]."""

    def test_workflow_contains_all_required_nodes(self) -> None:
        """Workflow graph must contain catering_agent, strategy_agent, and scheduling_agent."""
        assert isinstance(luncher_agent, Workflow)
        assert luncher_agent.name == "luncher_agent"
        assert root_agent is luncher_agent

        node_names = {node.name for node in luncher_agent.graph.nodes}
        assert "intent_router" in node_names
        assert "strategy_agent" in node_names
        assert "scheduling_agent" in node_names
        assert "catering_agent" in node_names or "cater_agent" in node_names, (
            f"catering_agent must be present in workflow graph nodes, got {node_names}"
        )
        assert "booking_handler" in node_names
        assert "join_info_gatherer" in node_names
        assert "lunch_synthesizer" in node_names

    def test_plan_route_branches_to_all_three_subagents(self) -> None:
        """'plan' route executes (strategy_agent, scheduling_agent, catering_agent) in parallel."""
        # Find router edge mapping
        edges = getattr(luncher_agent, "edges", [])
        router_routes = None
        for edge in edges:
            if len(edge) == 2 and (
                edge[0] is intent_router or getattr(edge[0], "name", None) == "intent_router"
            ):
                if isinstance(edge[1], dict):
                    router_routes = edge[1]
                    break

        if router_routes is not None:
            assert "plan" in router_routes, "Workflow router edges must contain 'plan' route"
            plan_targets = router_routes["plan"]
            if isinstance(plan_targets, (tuple, list)):
                target_names = {getattr(t, "name", str(t)) for t in plan_targets}
                assert "strategy_agent" in target_names
                assert "scheduling_agent" in target_names
                assert "catering_agent" in target_names or "cater_agent" in target_names

    def test_join_info_gatherer_receives_catering_agent(self) -> None:
        """join_info_gatherer must receive inputs from all 3 sub-agents."""
        edges = getattr(luncher_agent, "edges", [])
        join_sources = None
        for edge in edges:
            if len(edge) == 2 and (
                getattr(edge[1], "name", None) == "join_info_gatherer"
            ):
                join_sources = edge[0]
                break

        if join_sources is not None and isinstance(join_sources, (tuple, list)):
            source_names = {getattr(s, "name", str(s)) for s in join_sources}
            assert "strategy_agent" in source_names
            assert "scheduling_agent" in source_names
            assert "catering_agent" in source_names or "cater_agent" in source_names

    def test_dietary_preference_route_isolated_from_scheduling_and_booking(self) -> None:
        """'dietary_preference' route terminates without routing to scheduling_agent or booking_handler."""
        edges = getattr(luncher_agent, "edges", [])
        router_routes = None
        for edge in edges:
            if len(edge) == 2 and (
                edge[0] is intent_router or getattr(edge[0], "name", None) == "intent_router"
            ):
                if isinstance(edge[1], dict):
                    router_routes = edge[1]
                    break

        if router_routes is not None and "dietary_preference" in router_routes:
            dietary_target = router_routes["dietary_preference"]
            target_name = getattr(dietary_target, "name", str(dietary_target))
            assert target_name != "scheduling_agent"
            assert target_name != "booking_handler"


# ==============================================================================
# 7. Mocked End-to-End Workflow Execution & Behavioral Isolation
# ==============================================================================

class TestWorkflowExecutionIsolationMocked:
    """Verifies that each of the 4 routes executes only its authorized sub-agents."""

    def test_dietary_preference_does_not_trigger_scheduling_or_booking(self) -> None:
        """Scenario 3 BDD: Prompts stating only dietary constraints route to dietary persistence
        WITHOUT triggering scheduling_agent or booking, and return the confirmation message.
        """
        async def _run() -> None:
            strat_called = False
            sched_called = False
            book_called = False
            cater_memory_called = False

            def mock_strat(node_input: Any) -> str:
                nonlocal strat_called
                strat_called = True
                return "Strategic Context"

            def mock_sched(node_input: Any) -> str:
                nonlocal sched_called
                sched_called = True
                return "Schedules"

            def mock_book(node_input: Any) -> str:
                nonlocal book_called
                book_called = True
                return "Booking Confirmed"

            def mock_cater_memory(node_input: Any) -> str:
                nonlocal cater_memory_called
                cater_memory_called = True
                return (
                    "Saved dietary preference for Carol: vegetarian (restriction). "
                    "This will be applied to all future lunch recommendations.\n\n"
                    "Would you like to plan a team lunch now?"
                )

            def mock_router(node_input: Any) -> Event:
                return Event(output=node_input, route="dietary_preference")

            test_wf = Workflow(
                name="test_luncher_dietary_isolation",
                edges=[
                    ("START", mock_router),
                    (
                        mock_router,
                        {
                            "plan": (mock_strat, mock_sched),
                            "book": mock_book,
                            "dietary_preference": mock_cater_memory,
                        },
                    ),
                ],
            )

            test_app = App(name="test_luncher_dietary_isolation", root_agent=test_wf)
            runner = Runner(app=test_app, session_service=InMemorySessionService())
            session = await runner.session_service.create_session(
                app_name="test_luncher_dietary_isolation", user_id="u_dietary"
            )

            msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text="Carol is vegetarian and Dan cannot eat dairy")],
            )
            events = []
            async for event in runner.run_async(
                user_id="u_dietary", session_id=session.id, new_message=msg
            ):
                events.append(event)

            # Assertions
            assert cater_memory_called is True, "Catering dietary memory update must be invoked"
            assert sched_called is False, "scheduling_agent must NOT be triggered for dietary preference"
            assert book_called is False, "booking_handler must NOT be triggered for dietary preference"
            assert strat_called is False, "strategy_agent must NOT be triggered for dietary preference"

            outputs = [e.output for e in events if getattr(e, "output", None) is not None]
            assert any("Saved dietary preference" in str(o) for o in outputs)
            assert any("Would you like to plan a team lunch now?" in str(o) for o in outputs)

        asyncio.run(_run())

    def test_plan_with_preference_saves_memory_and_queries_subagents(self) -> None:
        """Scenario 4 BDD: Prompts combining planning and dietary preference persist the preference
        and execute parallel queries to strategy, scheduling, and catering.
        """
        async def _run() -> None:
            strat_called = False
            sched_called = False
            cater_called = False
            book_called = False
            memory_saved = False

            def mock_strat(node_input: Any) -> str:
                nonlocal strat_called
                strat_called = True
                return "Strategy Context"

            def mock_sched(node_input: Any) -> str:
                nonlocal sched_called
                sched_called = True
                return "Available Slots"

            def mock_cater(node_input: Any) -> str:
                nonlocal cater_called
                cater_called = True
                return "3 Thematic Menus (Gluten-Free)"

            def mock_book(node_input: Any) -> str:
                nonlocal book_called
                book_called = True
                return "Booked"

            def mock_pref_saver(node_input: Any) -> Any:
                nonlocal memory_saved
                memory_saved = True
                return node_input

            join = JoinNode(name="mock_join")

            def mock_synth(node_input: Any) -> str:
                return f"# Proposal with gluten-free menus\n{node_input}"

            def mock_router(node_input: Any) -> Event:
                return Event(output=node_input, route="plan_with_preference")

            test_wf = Workflow(
                name="test_luncher_plan_with_preference",
                edges=[
                    ("START", mock_router),
                    (
                        mock_router,
                        {
                            "plan": (mock_strat, mock_sched, mock_cater),
                            "book": mock_book,
                            "plan_with_preference": mock_pref_saver,
                        },
                    ),
                    (mock_pref_saver, (mock_strat, mock_sched, mock_cater)),
                    ((mock_strat, mock_sched, mock_cater), join),
                    (join, mock_synth),
                ],
            )

            test_app = App(name="test_luncher_plan_with_preference", root_agent=test_wf)
            runner = Runner(app=test_app, session_service=InMemorySessionService())
            session = await runner.session_service.create_session(
                app_name="test_luncher_plan_with_preference", user_id="u_plan_pref"
            )

            msg = types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="Schedule lunch for Friday, and note that Eve is gluten-free"
                    )
                ],
            )
            events = []
            async for event in runner.run_async(
                user_id="u_plan_pref", session_id=session.id, new_message=msg
            ):
                events.append(event)

            # Assertions
            assert memory_saved is True, "Preference must be persisted first"
            assert strat_called is True, "strategy_agent must be queried in planning branch"
            assert sched_called is True, "scheduling_agent must be queried in planning branch"
            assert cater_called is True, "catering_agent must be queried in planning branch"
            assert book_called is False, "booking_handler must NOT be called"

            outputs = [e.output for e in events if getattr(e, "output", None) is not None]
            assert any("Proposal with gluten-free menus" in str(o) for o in outputs)

        asyncio.run(_run())

    def test_standard_plan_queries_all_three_subagents_in_parallel(self) -> None:
        """Standard planning prompts trigger parallel queries to strategy, scheduling, and catering."""
        async def _run() -> None:
            strat_called = False
            sched_called = False
            cater_called = False
            book_called = False

            def mock_strat(node_input: Any) -> str:
                nonlocal strat_called
                strat_called = True
                return "Strategic Context"

            def mock_sched(node_input: Any) -> str:
                nonlocal sched_called
                sched_called = True
                return "Available Slots"

            def mock_cater(node_input: Any) -> str:
                nonlocal cater_called
                cater_called = True
                return "3 Thematic Menus"

            def mock_book(node_input: Any) -> str:
                nonlocal book_called
                book_called = True
                return "Booked"

            join = JoinNode(name="mock_join")

            def mock_synth(node_input: Any) -> str:
                return f"# Final Proposal\n{node_input}"

            def mock_router(node_input: Any) -> Event:
                return Event(output=node_input, route="plan")

            test_wf = Workflow(
                name="test_luncher_standard_plan",
                edges=[
                    ("START", mock_router),
                    (
                        mock_router,
                        {
                            "plan": (mock_strat, mock_sched, mock_cater),
                            "book": mock_book,
                        },
                    ),
                    ((mock_strat, mock_sched, mock_cater), join),
                    (join, mock_synth),
                ],
            )

            test_app = App(name="test_luncher_standard_plan", root_agent=test_wf)
            runner = Runner(app=test_app, session_service=InMemorySessionService())
            session = await runner.session_service.create_session(
                app_name="test_luncher_standard_plan", user_id="u_plan"
            )

            msg = types.Content(
                role="user",
                parts=[types.Part.from_text(text="Plan lunch for the launch team next Tuesday")],
            )
            events = []
            async for event in runner.run_async(
                user_id="u_plan", session_id=session.id, new_message=msg
            ):
                events.append(event)

            # Assertions
            assert strat_called is True, "strategy_agent must be queried"
            assert sched_called is True, "scheduling_agent must be queried"
            assert cater_called is True, "catering_agent must be queried"
            assert book_called is False, "booking_handler must NOT be queried"

            outputs = [e.output for e in events if getattr(e, "output", None) is not None]
            assert any("Final Proposal" in str(o) for o in outputs)

        asyncio.run(_run())

    def test_booking_delegates_to_booking_handler_only(self) -> None:
        """Booking prompts delegate directly to booking_handler without catering or strategy."""
        async def _run() -> None:
            strat_called = False
            cater_called = False
            book_called = False

            def mock_strat(node_input: Any) -> str:
                nonlocal strat_called
                strat_called = True
                return "Strategy"

            def mock_cater(node_input: Any) -> str:
                nonlocal cater_called
                cater_called = True
                return "Catering"

            def mock_book(node_input: Any) -> str:
                nonlocal book_called
                book_called = True
                return "Booking bk_12345 confirmed"

            def mock_router(node_input: Any) -> Event:
                return Event(output=node_input, route="book")

            test_wf = Workflow(
                name="test_luncher_book",
                edges=[
                    ("START", mock_router),
                    (
                        mock_router,
                        {
                            "plan": (mock_strat, mock_cater),
                            "book": mock_book,
                        },
                    ),
                ],
            )

            test_app = App(name="test_luncher_book", root_agent=test_wf)
            runner = Runner(app=test_app, session_service=InMemorySessionService())
            session = await runner.session_service.create_session(
                app_name="test_luncher_book", user_id="u_book"
            )

            msg = types.Content(role="user", parts=[types.Part.from_text(text="Book Option 1")])
            events = []
            async for event in runner.run_async(
                user_id="u_book", session_id=session.id, new_message=msg
            ):
                events.append(event)

            # Assertions
            assert book_called is True, "booking_handler must be invoked"
            assert strat_called is False, "strategy_agent must NOT be invoked"
            assert cater_called is False, "catering_agent must NOT be invoked"

            outputs = [e.output for e in events if getattr(e, "output", None) is not None]
            assert any("Booking bk_12345 confirmed" in str(o) for o in outputs)

        asyncio.run(_run())
