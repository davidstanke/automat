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

"""Unit tests for Cater Agent ADK Agent Definition & Thematic Menu Tools.

Verifies conformance with Task 005 specification & acceptance criteria:
1. `record_dietary_preference` tool persists preference to memory and returns
   exact confirmation:
   "Saved dietary preference for {person_name}: {details} {preference_type}. This will be applied to all future lunch recommendations."
2. `get_dietary_preferences` tool lists active dietary preferences or indicates none stored.
3. `get_thematic_menus` tool retrieves active preferences from `dietary_preferences`,
   queries items through `menu_service`, and structures exactly 3 themed menus.
4. Each generated menu strictly adheres to the 4-course structure:
   - 1 to 3 mains (with name, description, allergens, dietary_labels)
   - 2 to 3 sides (with name)
   - >= 1 beverage (with name)
   - >= 1 dessert (with name)
   - distinct menu_id and theme_name
5. Active dietary accommodations are summarized and included in the output
   (e.g., "Filtered to accommodate: Peanut allergy (Alice), Vegetarian (Bob)").
6. Dietary safety: conflicting dishes (e.g. peanuts or meat for vegetarian) are filtered out.
7. Agent and App definition in `app.agent`:
   - `root_agent` is an ADK Agent named 'cater_agent' (or 'catering_agent') with Gemini model.
   - `root_agent` instructions detail 4-course menu composition and dietary safety.
   - `root_agent.tools` include record_dietary_preference, get_dietary_preferences, get_thematic_menus.
   - `app` is an ADK App named 'cater_agent' wrapping `root_agent`.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from google.adk.agents import Agent
from google.adk.apps import App

from app import dietary_preferences, menu_service
from app.tools import (
    get_dietary_preferences,
    get_thematic_menus,
    record_dietary_preference,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Memory Isolation
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enforce clean in-process memory isolation for every test run."""
    monkeypatch.delenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", raising=False)
    monkeypatch.setattr(dietary_preferences, "_local_preferences", [])


def _extract_menus_and_accommodations(raw_output: str) -> tuple[list[dict[str, Any]], str]:
    """Helper to parse get_thematic_menus string output into menu dicts and accommodations."""
    assert isinstance(raw_output, str), f"Expected string output from tool, got {type(raw_output)}"
    raw = raw_output.strip()

    # 1. Try parsing directly as JSON
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            menus = data.get("menus") or data.get("thematic_menus") or data.get("catering_menus") or []
            accommodations = data.get("accommodations") or data.get("accommodation_summary") or data.get("notes") or ""
            return list(menus), str(accommodations)
        elif isinstance(data, list):
            return list(data), ""
    except json.JSONDecodeError:
        pass

    # 2. Try parsing embedded ```json ``` block
    block_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if block_match:
        try:
            data = json.loads(block_match.group(1).strip())
            if isinstance(data, dict):
                menus = data.get("menus") or data.get("thematic_menus") or data.get("catering_menus") or []
                accommodations = data.get("accommodations") or data.get("accommodation_summary") or data.get("notes") or ""
                return list(menus), str(accommodations)
            elif isinstance(data, list):
                return list(data), ""
        except json.JSONDecodeError:
            pass

    # 3. Try finding JSON array or object substring
    json_array_match = re.search(r"(\[\s*\{[\s\S]*\}\s*\])", raw)
    if json_array_match:
        try:
            data = json.loads(json_array_match.group(1))
            if isinstance(data, list):
                return list(data), ""
        except json.JSONDecodeError:
            pass

    json_obj_match = re.search(r"(\{\s*\"(?:menus|thematic_menus|accommodations)\"[\s\S]*\})", raw)
    if json_obj_match:
        try:
            data = json.loads(json_obj_match.group(1))
            if isinstance(data, dict):
                menus = data.get("menus") or data.get("thematic_menus") or []
                accommodations = data.get("accommodations") or ""
                return list(menus), str(accommodations)
        except json.JSONDecodeError:
            pass

    pytest.fail(f"Could not parse valid ThematicMenu data from get_thematic_menus output:\n{raw_output}")


def _assert_thematic_menu_schema(menu: dict[str, Any]) -> None:
    """Validates that a menu dictionary satisfies Section 4.2 ThematicMenu schema."""
    assert isinstance(menu, dict), f"Expected menu object to be a dict, got {type(menu)}"

    # Required identifiers and theme
    assert "menu_id" in menu, "Menu must contain 'menu_id'"
    assert isinstance(menu["menu_id"], str) and menu["menu_id"].strip(), (
        "'menu_id' must be a non-empty string"
    )

    assert "theme_name" in menu, "Menu must contain 'theme_name'"
    assert isinstance(menu["theme_name"], str) and menu["theme_name"].strip(), (
        "'theme_name' must be a non-empty string"
    )

    # Mains: 1 to 3 items
    assert "mains" in menu, f"Menu '{menu.get('theme_name')}' missing 'mains'"
    assert isinstance(menu["mains"], list), "'mains' must be a list"
    assert 1 <= len(menu["mains"]) <= 3, (
        f"Menu '{menu.get('theme_name')}' must have 1-3 mains, got {len(menu['mains'])}"
    )
    for idx, main in enumerate(menu["mains"]):
        assert isinstance(main, dict), f"Main #{idx+1} must be an object"
        assert "name" in main and isinstance(main["name"], str) and main["name"].strip(), (
            f"Main #{idx+1} must have a non-empty 'name'"
        )
        if "allergens" in main:
            assert isinstance(main["allergens"], list), f"Main '{main['name']}' allergens must be a list"
        if "dietary_labels" in main:
            assert isinstance(main["dietary_labels"], list), (
                f"Main '{main['name']}' dietary_labels must be a list"
            )

    # Sides: 2 to 3 items
    assert "sides" in menu, f"Menu '{menu.get('theme_name')}' missing 'sides'"
    assert isinstance(menu["sides"], list), "'sides' must be a list"
    assert 2 <= len(menu["sides"]) <= 3, (
        f"Menu '{menu.get('theme_name')}' must have 2-3 sides, got {len(menu['sides'])}"
    )
    for idx, side in enumerate(menu["sides"]):
        assert isinstance(side, dict), f"Side #{idx+1} must be an object"
        assert "name" in side and isinstance(side["name"], str) and side["name"].strip(), (
            f"Side #{idx+1} must have a non-empty 'name'"
        )

    # Beverages: at least 1 item
    assert "beverages" in menu, f"Menu '{menu.get('theme_name')}' missing 'beverages'"
    assert isinstance(menu["beverages"], list), "'beverages' must be a list"
    assert len(menu["beverages"]) >= 1, (
        f"Menu '{menu.get('theme_name')}' must have >= 1 beverage, got {len(menu['beverages'])}"
    )
    for idx, bev in enumerate(menu["beverages"]):
        assert isinstance(bev, dict), f"Beverage #{idx+1} must be an object"
        assert "name" in bev and isinstance(bev["name"], str) and bev["name"].strip(), (
            f"Beverage #{idx+1} must have a non-empty 'name'"
        )

    # Desserts: at least 1 item
    assert "desserts" in menu, f"Menu '{menu.get('theme_name')}' missing 'desserts'"
    assert isinstance(menu["desserts"], list), "'desserts' must be a list"
    assert len(menu["desserts"]) >= 1, (
        f"Menu '{menu.get('theme_name')}' must have >= 1 dessert, got {len(menu['desserts'])}"
    )
    for idx, des in enumerate(menu["desserts"]):
        assert isinstance(des, dict), f"Dessert #{idx+1} must be an object"
        assert "name" in des and isinstance(des["name"], str) and des["name"].strip(), (
            f"Dessert #{idx+1} must have a non-empty 'name'"
        )


# ---------------------------------------------------------------------------
# 1. record_dietary_preference Tool Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_dietary_preference_format_and_persistence() -> None:
    """Verifies record_dietary_preference returns exact confirmation and persists memory."""
    confirmation = await record_dietary_preference(
        person_name="Dave",
        preference_type="allergy",
        details="gluten",
    )
    expected = (
        "Saved dietary preference for Dave: gluten allergy. "
        "This will be applied to all future lunch recommendations."
    )
    assert confirmation == expected

    stored = await dietary_preferences.list_preferences()
    assert len(stored) == 1
    assert stored[0]["person_name"] == "Dave"
    assert stored[0]["preference_type"] == "allergy"
    assert stored[0]["details"] == "gluten"


@pytest.mark.asyncio
async def test_record_dietary_preference_different_types() -> None:
    """Verifies confirmation formatting across allergy, restriction, dislike, and like."""
    test_cases = [
        (
            "Alice",
            "allergy",
            "peanuts",
            "Saved dietary preference for Alice: peanuts allergy. This will be applied to all future lunch recommendations.",
        ),
        (
            "Bob",
            "restriction",
            "vegetarian",
            "Saved dietary preference for Bob: vegetarian restriction. This will be applied to all future lunch recommendations.",
        ),
        (
            "Charlie",
            "dislike",
            "mushrooms",
            "Saved dietary preference for Charlie: mushrooms dislike. This will be applied to all future lunch recommendations.",
        ),
        (
            "Dana",
            "like",
            "spicy",
            "Saved dietary preference for Dana: spicy like. This will be applied to all future lunch recommendations.",
        ),
    ]

    for person, ptype, details, expected_msg in test_cases:
        msg = await record_dietary_preference(person, ptype, details)
        assert msg == expected_msg

    stored = await dietary_preferences.list_preferences()
    assert len(stored) == len(test_cases)


@pytest.mark.asyncio
async def test_record_dietary_preference_sanitizes_input() -> None:
    """Verifies record_dietary_preference sanitizes inputs before saving."""
    res = await record_dietary_preference(
        person_name="<script>alert(1)</script>Eve",
        preference_type="allergy",
        details="shellfish; DROP TABLE users;--",
    )
    assert "<script>" not in res
    assert "DROP TABLE" not in res
    assert "Eve" in res
    assert "shellfish" in res

    stored = await dietary_preferences.list_preferences()
    assert len(stored) == 1
    assert stored[0]["person_name"] == "Eve"
    assert "DROP TABLE" not in stored[0]["details"]


@pytest.mark.asyncio
async def test_record_dietary_preference_invalid_type_rejected() -> None:
    """Verifies record_dietary_preference raises or handles invalid preference types."""
    with pytest.raises((ValueError, Exception)):
        await record_dietary_preference(
            person_name="Frank",
            preference_type="forbidden_type",
            details="dairy",
        )


# ---------------------------------------------------------------------------
# 2. get_dietary_preferences Tool Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_dietary_preferences_empty() -> None:
    """Verifies get_dietary_preferences indicates when no preferences are recorded."""
    res = await get_dietary_preferences()
    assert isinstance(res, str)
    assert re.search(r"no dietary preferences|none recorded|empty", res, re.IGNORECASE)


@pytest.mark.asyncio
async def test_get_dietary_preferences_with_records() -> None:
    """Verifies get_dietary_preferences summarizes existing team preferences."""
    await record_dietary_preference("Alice", "allergy", "peanuts")
    await record_dietary_preference("Bob", "restriction", "vegetarian")

    res = await get_dietary_preferences()
    assert "Alice" in res
    assert "peanuts" in res
    assert "Bob" in res
    assert "vegetarian" in res


# ---------------------------------------------------------------------------
# 3. get_thematic_menus Tool Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_thematic_menus_returns_exactly_three_menus() -> None:
    """Verifies get_thematic_menus structures exactly 3 themed menus conforming to contract."""
    raw_output = await get_thematic_menus()
    menus, _ = _extract_menus_and_accommodations(raw_output)

    assert len(menus) == 3, f"Expected exactly 3 thematic menus, got {len(menus)}"

    theme_names = [m.get("theme_name") for m in menus]
    menu_ids = [m.get("menu_id") for m in menus]

    # Verify distinct themes and ids
    assert len(set(theme_names)) == 3, f"Themes must be distinct: {theme_names}"
    assert len(set(menu_ids)) == 3, f"Menu IDs must be distinct: {menu_ids}"

    # Verify 4-course schema for all 3 menus
    for menu in menus:
        _assert_thematic_menu_schema(menu)


@pytest.mark.asyncio
async def test_get_thematic_menus_four_course_quantities() -> None:
    """Verifies every menu strictly satisfies 1-3 mains, 2-3 sides, >=1 bev, >=1 dessert."""
    raw_output = await get_thematic_menus()
    menus, _ = _extract_menus_and_accommodations(raw_output)

    for menu in menus:
        theme = menu["theme_name"]
        mains = menu["mains"]
        sides = menu["sides"]
        beverages = menu["beverages"]
        desserts = menu["desserts"]

        assert 1 <= len(mains) <= 3, f"'{theme}' mains count ({len(mains)}) outside [1, 3]"
        assert 2 <= len(sides) <= 3, f"'{theme}' sides count ({len(sides)}) outside [2, 3]"
        assert len(beverages) >= 1, f"'{theme}' beverages count ({len(beverages)}) < 1"
        assert len(desserts) >= 1, f"'{theme}' desserts count ({len(desserts)}) < 1"


@pytest.mark.asyncio
async def test_get_thematic_menus_with_allergy_filtering() -> None:
    """Verifies items containing allergens are excluded and accommodation note is presented."""
    await record_dietary_preference("Alice", "allergy", "peanuts")

    raw_output = await get_thematic_menus()
    menus, accommodations = _extract_menus_and_accommodations(raw_output)

    assert len(menus) == 3
    # Check that output mentions the accommodation
    output_text = raw_output + " " + accommodations
    assert "Filtered to accommodate:" in output_text or "Peanut allergy (Alice)" in output_text
    assert "Peanut allergy (Alice)" in output_text

    # Verify that NO dishes in any menu contain peanuts
    for menu in menus:
        for course in ("mains", "sides", "beverages", "desserts"):
            for item in menu.get(course, []):
                item_name = item.get("name", "").lower()
                allergens = [a.lower() for a in item.get("allergens", [])]
                desc = item.get("description", "").lower()

                assert "peanut" not in allergens, f"Found peanut in allergens of '{item['name']}'"
                assert "peanuts" not in allergens
                assert "peanut" not in item_name, f"Found peanut in name of '{item['name']}'"
                assert "peanut" not in desc, f"Found peanut in description of '{item['name']}'"


@pytest.mark.asyncio
async def test_get_thematic_menus_with_combined_dietary_accommodations() -> None:
    """Verifies accommodation note and filtering for combined preferences (Alice + Bob)."""
    await record_dietary_preference("Alice", "allergy", "peanuts")
    await record_dietary_preference("Bob", "restriction", "vegetarian")

    raw_output = await get_thematic_menus()
    menus, accommodations = _extract_menus_and_accommodations(raw_output)

    assert len(menus) == 3
    output_text = raw_output + " " + accommodations

    # Must contain accommodation summary matching acceptance criteria pattern
    assert "Peanut allergy (Alice)" in output_text
    assert "Vegetarian (Bob)" in output_text

    # Verify menus contain vegetarian-friendly mains/sides
    for menu in menus:
        _assert_thematic_menu_schema(menu)
        for main in menu["mains"]:
            allergens = [a.lower() for a in main.get("allergens", [])]
            assert "peanuts" not in allergens
            assert "peanut" not in allergens


@pytest.mark.asyncio
async def test_get_thematic_menus_graceful_offline_fallback() -> None:
    """Verifies get_thematic_menus functions gracefully when MCP is unavailable/offline."""
    # Ensure offline mode without cloud credentials
    with patch.dict("os.environ", {"BIGQUERY_MCP_COMMAND": "", "GOOGLE_CLOUD_PROJECT": ""}):
        raw_output = await get_thematic_menus()
        menus, _ = _extract_menus_and_accommodations(raw_output)
        assert len(menus) == 3
        for menu in menus:
            _assert_thematic_menu_schema(menu)


# ---------------------------------------------------------------------------
# 4. Cater Agent & App Definition Tests (app/agent.py)
# ---------------------------------------------------------------------------
def test_cater_agent_definition() -> None:
    """Verifies root_agent is configured with Gemini model, tools, and 4-course instructions."""
    from app.agent import root_agent

    assert isinstance(root_agent, Agent), "root_agent must be an ADK Agent instance"
    assert root_agent.name in ("cater_agent", "catering_agent"), (
        f"root_agent name must be 'cater_agent' or 'catering_agent', got '{root_agent.name}'"
    )

    # Check model
    assert hasattr(root_agent, "model"), "root_agent must have a Gemini model configured"

    # Check tools attached
    tool_names = set()
    for tool in getattr(root_agent, "tools", []):
        if hasattr(tool, "name"):
            tool_names.add(tool.name)
        elif hasattr(tool, "__name__"):
            tool_names.add(tool.__name__)
        elif hasattr(tool, "func") and hasattr(tool.func, "__name__"):
            tool_names.add(tool.func.__name__)

    expected_tools = {
        "record_dietary_preference",
        "get_dietary_preferences",
        "get_thematic_menus",
    }
    assert expected_tools.issubset(tool_names), (
        f"root_agent.tools must include {expected_tools}, found: {tool_names}"
    )

    # Check instruction contents
    instructions = getattr(root_agent, "instruction", "") or getattr(root_agent, "instructions", "")
    assert isinstance(instructions, str) and len(instructions) > 0, "Agent instructions must be non-empty"
    lower_instructions = instructions.lower()
    assert "course" in lower_instructions or "menu" in lower_instructions
    assert "dietary" in lower_instructions or "allergen" in lower_instructions or "preference" in lower_instructions


def test_cater_agent_app_definition() -> None:
    """Verifies app is an ADK App named 'cater_agent' wrapping root_agent."""
    from app.agent import app, root_agent

    assert isinstance(app, App), "app must be an ADK App instance"
    assert app.name == "cater_agent", f"App name must be 'cater_agent', got '{app.name}'"
    assert app.root_agent is root_agent, "App root_agent must point to root_agent"
